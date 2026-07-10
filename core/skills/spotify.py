"""Spotify-Steuerung — Playback lokal per AppleScript, Suche über die Web-API.

Registriert sich via @T.register beim Import (durch core/skills/__init__.py).
Play/Pause/Next/Volume/Status brauchen weder Key noch Netz; nur „spiel [X]"
(Suche) braucht SPOTIFY_CLIENT_ID/SECRET in der .env (kostenlose App auf
developer.spotify.com, kein User-Login).
"""

import logging

from core import tools as T
from tools.spotify import applescript as sp
from tools.spotify import web_api

log = logging.getLogger("core.skills")

_SETUP_HINT = (
    "🎧 Für „spiel [X]“ fehlen noch Spotify-API-Zugangsdaten: auf "
    "developer.spotify.com eine kostenlose App anlegen und SPOTIFY_CLIENT_ID + "
    "SPOTIFY_CLIENT_SECRET in die .env eintragen. Play/Pause/Next/Lautstärke "
    "funktionieren auch ohne."
)


@T.register(
    "spotify",
    "Steuert Spotify auf dem Mac: play/pause/next/previous, Lautstärke (volume 0-100), "
    "status = was läuft gerade, spiel = sucht Song/Album/Playlist/Künstler und spielt "
    "das beste Ergebnis ab. Nutze dies wenn Timo Musik hören, pausieren, wechseln, "
    "lauter/leiser stellen oder wissen will was gerade läuft.",
    {
        "action": {
            "type": "string",
            "enum": ["play", "pause", "next", "previous", "volume", "status", "spiel"],
            "description": "play/pause/next/previous = Playback, volume = Lautstärke setzen, "
                           "status = aktueller Track, spiel = suchen und abspielen",
        },
        "query": {"type": "string",
                  "description": "nur für spiel: Song/Album/Playlist/Künstler-Name"},
        "volume": {"type": "integer", "description": "nur für volume: Ziel-Lautstärke 0-100"},
        "typ": {
            "type": "string",
            "enum": ["track", "album", "playlist", "artist"],
            "description": "nur für spiel: optionaler Typ-Hinweis "
                           "(z.B. playlist wenn Timo 'die Playlist X' sagt)",
        },
    },
    ["action"],
    "spotify",
)
async def _spotify(action: str, query: str = "", volume: int = -1, typ: str = ""):
    a = (action or "").strip().lower()
    try:
        if a == "play":
            await sp.play()
            return "▶️ Musik läuft"
        if a == "pause":
            await sp.pause()
            return "⏸️ Pausiert"
        if a == "next":
            await sp.next_track()
            t = await sp.current_track()
            return f"⏭️ {t.title} — {t.artist}" if t else "⏭️ Nächster Track"
        if a == "previous":
            await sp.previous_track()
            t = await sp.current_track()
            return f"⏮️ {t.title} — {t.artist}" if t else "⏮️ Vorheriger Track"
        if a == "volume":
            if volume is None or volume < 0:
                return "❌ Bitte volume 0-100 angeben."
            v = max(0, min(100, int(volume)))
            await sp.set_volume(v)
            return f"🔊 Lautstärke {v} %"
        if a == "status":
            t = await sp.current_track()
            if t is None:
                return "🔇 Gerade läuft nichts."
            suffix = " (pausiert)" if t.state == "paused" else ""
            return f"🎵 {t.title} — {t.artist} · {t.album}{suffix}"
        if a == "spiel":
            return await _spiel(query, typ)
        return (f"❌ Unbekannte Spotify-Aktion '{action}'. Möglich: play, pause, next, "
                f"previous, volume, status, spiel.")
    except sp.SpotifyError as e:
        log.warning("spotify fehlgeschlagen: %s", e)
        return f"❌ Spotify nicht steuerbar: {e}. Ist Spotify installiert und gestartet?"


async def _spiel(query: str, typ: str = "") -> str:
    if not (query or "").strip():
        return "❌ Was soll ich spielen? Bitte query angeben."
    if web_api.credentials_missing():
        return _SETUP_HINT
    try:
        hit = await web_api.search(query.strip(), typ=(typ or None))
    except web_api.SpotifySearchError as e:
        log.warning("spotify-suche fehlgeschlagen: %s", e)
        return f"❌ Spotify-Suche gerade nicht möglich: {e}"
    if hit is None:
        return f"🤷 Nichts gefunden zu ‚{query}'."
    uri, name = hit
    await sp.play_uri(uri)
    return f"▶️ {name}"
