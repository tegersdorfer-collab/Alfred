"""Tests für die Spotify-Steuerung (tools/spotify/ + core/skills/spotify.py) — ohne echtes Spotify.

Der osascript-Aufruf und die Web-API-HTTP-Helfer werden gemockt; geprüft werden
Script-Erzeugung, Edge-Cases (gestoppter Player, fehlende Credentials) und die
Antwort-Formatierung des registrierten Tools.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.spotify import applescript as sp


def _patch_osa(calls, reply=""):
    """Ersetzt den osascript-Subprozess. reply: str oder Callable(script)->str."""
    async def fake(script: str) -> str:
        calls.append(script)
        return reply(script) if callable(reply) else reply
    sp._osascript = fake


# ── AppleScript-Treiber ───────────────────────────────────────────────────────

def test_playback_commands_build_correct_scripts():
    calls: list = []
    _patch_osa(calls)
    asyncio.run(sp.play())
    asyncio.run(sp.pause())
    asyncio.run(sp.next_track())
    asyncio.run(sp.previous_track())
    assert calls == [
        'tell application "Spotify" to play',
        'tell application "Spotify" to pause',
        'tell application "Spotify" to next track',
        'tell application "Spotify" to previous track',
    ]


def test_volume_is_clamped():
    calls: list = []
    _patch_osa(calls)
    asyncio.run(sp.set_volume(150))
    asyncio.run(sp.set_volume(-5))
    assert calls == [
        'tell application "Spotify" to set sound volume to 100',
        'tell application "Spotify" to set sound volume to 0',
    ]


def test_get_volume_parses_int():
    calls: list = []
    _patch_osa(calls, reply="63")
    assert asyncio.run(sp.get_volume()) == 63


def test_play_uri_escapes_quotes():
    calls: list = []
    _patch_osa(calls)
    asyncio.run(sp.play_uri('spotify:track:abc"def'))
    assert calls == ['tell application "Spotify" to play track "spotify:track:abcdef"']


def test_current_track_when_stopped_returns_none():
    """Live beobachtet: bei 'stopped' wirft 'current track' Fehler -1728 —
    der Treiber muss den State VORHER prüfen und None liefern."""
    calls: list = []
    _patch_osa(calls, reply="stopped")
    assert asyncio.run(sp.current_track()) is None
    assert len(calls) == 1  # kein zweiter Aufruf, der crashen würde


def test_current_track_playing():
    def reply(script):
        if "player state" in script:
            return "playing"
        return "Kids\nMGMT\nOracular Spectacular"
    calls: list = []
    _patch_osa(calls, reply=reply)
    t = asyncio.run(sp.current_track())
    assert t is not None
    assert (t.title, t.artist, t.album, t.state) == ("Kids", "MGMT", "Oracular Spectacular", "playing")

from settings import cfg
from tools.spotify import web_api


def _reset_webapi():
    web_api._token = None
    web_api._token_expires = 0.0


def _patch_http(search_json, token_calls=None):
    async def fake_token():
        if token_calls is not None:
            token_calls.append(1)
        return {"access_token": "tok123", "expires_in": 3600}

    async def fake_search(params, token):
        assert token == "tok123"
        fake_search.last_params = params
        return search_json
    web_api._http_post_token = fake_token
    web_api._http_get_search = fake_search
    return fake_search


# ── Web-API-Suche ─────────────────────────────────────────────────────────────

def test_credentials_missing_detection():
    old = (cfg.SPOTIFY_CLIENT_ID, cfg.SPOTIFY_CLIENT_SECRET)
    try:
        cfg.SPOTIFY_CLIENT_ID, cfg.SPOTIFY_CLIENT_SECRET = "", ""
        assert web_api.credentials_missing() is True
        cfg.SPOTIFY_CLIENT_ID, cfg.SPOTIFY_CLIENT_SECRET = "id", "secret"
        assert web_api.credentials_missing() is False
    finally:
        cfg.SPOTIFY_CLIENT_ID, cfg.SPOTIFY_CLIENT_SECRET = old


def test_search_prefers_track_and_formats_name():
    _reset_webapi()
    _patch_http({
        "tracks": {"items": [{"uri": "spotify:track:t1", "name": "Kids",
                              "artists": [{"name": "MGMT"}]}]},
        "albums": {"items": [{"uri": "spotify:album:a1", "name": "Oracular"}]},
    })
    uri, name = asyncio.run(web_api.search("kids"))
    assert uri == "spotify:track:t1"
    assert name == "Kids — MGMT"


def test_search_type_hint_playlist():
    _reset_webapi()
    fake = _patch_http({
        "playlists": {"items": [{"uri": "spotify:playlist:p1", "name": "Focus Mix"}]},
    })
    uri, name = asyncio.run(web_api.search("focus", typ="playlist"))
    assert uri == "spotify:playlist:p1"
    assert name == "Focus Mix"
    assert fake.last_params["type"] == "playlist"


def test_search_no_results_returns_none():
    _reset_webapi()
    _patch_http({"tracks": {"items": []}, "albums": {"items": []},
                 "playlists": {"items": []}, "artists": {"items": []}})
    assert asyncio.run(web_api.search("qqqxyz")) is None


def test_token_is_cached():
    _reset_webapi()
    token_calls: list = []
    _patch_http({"tracks": {"items": [{"uri": "spotify:track:t1", "name": "A",
                                       "artists": [{"name": "B"}]}]}}, token_calls)
    asyncio.run(web_api.search("a"))
    asyncio.run(web_api.search("a"))
    assert len(token_calls) == 1  # zweiter Call nutzt den gecachten Token
