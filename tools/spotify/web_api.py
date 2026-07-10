"""Spotify-Web-API — nur für die Suche („spiel [X]").

Client-Credentials-Flow: braucht SPOTIFY_CLIENT_ID/SECRET aus der .env
(kostenlose App auf developer.spotify.com), aber KEINEN User-Login und kein
Premium. Der Token wird bis kurz vor Ablauf gecacht. Playback selbst läuft
lokal über applescript.py — offline fällt also nur die Suche aus.

Tests patchen _http_post_token/_http_get_search (Muster wie tools/flipper).
"""
from __future__ import annotations

import time

import httpx

from settings import cfg

_TOKEN_URL = "https://accounts.spotify.com/api/token"
_SEARCH_URL = "https://api.spotify.com/v1/search"
_TYPES = ("track", "album", "playlist", "artist")  # zugleich Präferenz-Reihenfolge


class SpotifySearchError(RuntimeError):
    """Suche/Token-Abruf fehlgeschlagen (offline, falsche Credentials, …)."""


_token: str | None = None
_token_expires: float = 0.0


def credentials_missing() -> bool:
    return not (cfg.SPOTIFY_CLIENT_ID and cfg.SPOTIFY_CLIENT_SECRET)


async def _http_post_token() -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(_TOKEN_URL, data={"grant_type": "client_credentials"},
                              auth=(cfg.SPOTIFY_CLIENT_ID, cfg.SPOTIFY_CLIENT_SECRET))
    if r.status_code != 200:
        raise SpotifySearchError(f"Token-Abruf fehlgeschlagen (HTTP {r.status_code})")
    return r.json()


async def _http_get_search(params: dict, token: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(_SEARCH_URL, params=params,
                             headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        raise SpotifySearchError(f"Suche fehlgeschlagen (HTTP {r.status_code})")
    return r.json()


async def _get_token() -> str:
    global _token, _token_expires
    if _token and time.time() < _token_expires - 60:
        return _token
    data = await _http_post_token()
    _token = data["access_token"]
    _token_expires = time.time() + float(data.get("expires_in", 3600))
    return _token


def _display_name(kind: str, item: dict) -> str:
    if kind == "track":
        artists = ", ".join(a.get("name", "") for a in item.get("artists", []))
        return f"{item.get('name', '?')} — {artists}" if artists else item.get("name", "?")
    return item.get("name", "?")


async def search(query: str, typ: str | None = None) -> tuple[str, str] | None:
    """Beste Übereinstimmung → (URI, Anzeigename) oder None ohne Treffer.

    typ erzwingt einen Ergebnistyp (z.B. 'playlist'); ohne typ gilt die
    Präferenz track > album > playlist > artist.
    """
    kinds = (typ,) if typ in _TYPES else _TYPES
    token = await _get_token()
    data = await _http_get_search(
        {"q": query, "type": ",".join(kinds), "limit": 3, "market": "DE"}, token)
    for kind in kinds:
        items = (data.get(kind + "s") or {}).get("items") or []
        # Spotify liefert gelegentlich null-Einträge in Listen — überspringen.
        for item in items:
            if item and item.get("uri"):
                return item["uri"], _display_name(kind, item)
    return None
