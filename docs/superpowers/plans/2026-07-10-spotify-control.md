# Spotify-Steuerung Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mantis steuert Spotify auf dem Mac (Play/Pause/Next/Prev/Volume/Status lokal via AppleScript) und kann per Web-API-Suche „Spiel [X]" ausführen.

**Architecture:** Treiber in `tools/spotify/` (AppleScript-Wrapper + Web-API-Suche), Tool-Registrierung in `core/skills/spotify.py` via `@T.register`, deterministische Fast-Paths in `core/fast_commands.py` — exakt nach Flipper-Vorbild. Spec: `docs/2026-07-10-spotify-control-design.md`.

**Tech Stack:** Python 3.14, asyncio, `osascript` via `asyncio.create_subprocess_exec`, httpx (bereits Dependency), pydantic-settings, pytest.

## Global Constraints

- Python: `python3.14`; Tests: `python3.14 -m pytest -q`; Lint: `python3.14 -m ruff check .` (nur F + E9, line-length 120)
- Docstrings, Kommentare und User-sichtbare Strings auf Deutsch, Emoji-Stil wie bestehende Tools (▶️ ⏸️ 🎵 ❌)
- Tests laufen OHNE echtes Spotify/Netz: Modul-Funktionen werden direkt gepatcht (Muster `tests/test_flipper.py`: `driver.ir_tx = fake`)
- Tests beginnen mit dem `sys.path.insert(0, …)`-Header wie alle bestehenden Tests
- Commits: prägnante deutsche Message + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Fast-Path-Designprinzip: **Fehlalarme sind schlimmer als Auslassungen** — Regeln eng halten
- `.env` nie ins Repo; neue Variablen nur in `settings.py` (Defaults leer) + `.env.example`
- Verifiziert am 2026-07-10: AppleScript funktioniert trotz Spicetify (`player state` → „stopped", Bundle-ID `com.spotify.client`); bei Status „stopped" wirft `current track` Fehler −1728 → vorher State prüfen

---

### Task 1: AppleScript-Treiber `tools/spotify/applescript.py`

**Files:**
- Create: `tools/spotify/__init__.py` (leer)
- Create: `tools/spotify/applescript.py`
- Test: `tests/test_spotify.py` (neu)

**Interfaces:**
- Consumes: nichts (Blatt-Modul)
- Produces (von Task 3 genutzt):
  - `class SpotifyError(RuntimeError)`
  - `async def play() -> None`, `pause()`, `playpause()`, `next_track()`, `previous_track()`
  - `async def set_volume(v: int) -> None` (klemmt auf 0–100), `async def get_volume() -> int`
  - `async def play_uri(uri: str) -> None`
  - `@dataclass TrackInfo(title: str, artist: str, album: str, state: str)` und `async def current_track() -> TrackInfo | None` (None wenn Player „stopped")
  - intern: `async def _osascript(script: str) -> str` — der EINZIGE Subprozess-Aufruf, Tests patchen genau diese Funktion

- [ ] **Step 1: Failing Tests schreiben** — `tests/test_spotify.py` anlegen:

```python
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
```

- [ ] **Step 2: Tests laufen lassen, Scheitern verifizieren**

Run: `cd ~/Mantis && python3.14 -m pytest tests/test_spotify.py -q`
Expected: FAIL / ERROR mit `ModuleNotFoundError: No module named 'tools.spotify'`

- [ ] **Step 3: Implementierung** — `tools/spotify/__init__.py` leer anlegen, dann `tools/spotify/applescript.py`:

```python
"""Spotify-Steuerung über AppleScript (osascript) — voll lokal.

Der Spotify-Desktop-Client exponiert eine AppleScript-Schnittstelle für Playback,
Lautstärke und aktuellen Track (auch mit Spicetify gepatcht — das ändert nur die
UI-Schicht, nicht das Scripting-Interface). Kein API-Key, kein Netz nötig.

Alle Befehle laufen über _osascript(); Tests patchen genau diese Funktion.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass


class SpotifyError(RuntimeError):
    """osascript schlug fehl (Spotify fehlt, Scripting-Fehler, …)."""


async def _osascript(script: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", script,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise SpotifyError(err.decode().strip() or f"osascript exit {proc.returncode}")
    return out.decode().strip()


def _tell(cmd: str) -> str:
    return f'tell application "Spotify" to {cmd}'


async def play() -> None:
    await _osascript(_tell("play"))


async def pause() -> None:
    await _osascript(_tell("pause"))


async def playpause() -> None:
    await _osascript(_tell("playpause"))


async def next_track() -> None:
    await _osascript(_tell("next track"))


async def previous_track() -> None:
    await _osascript(_tell("previous track"))


async def set_volume(v: int) -> None:
    await _osascript(_tell(f"set sound volume to {max(0, min(100, int(v)))}"))


async def get_volume() -> int:
    return int(await _osascript(_tell("sound volume")))


async def play_uri(uri: str) -> None:
    """Spielt eine Spotify-URI (Track/Album/Playlist) — startet Spotify falls zu."""
    safe = uri.replace('"', "").replace("\\", "")
    await _osascript(_tell(f'play track "{safe}"'))


@dataclass
class TrackInfo:
    title: str
    artist: str
    album: str
    state: str  # playing | paused


async def current_track() -> TrackInfo | None:
    """Aktueller Track oder None wenn nichts läuft.

    Wichtig: bei Player-Status „stopped" wirft `current track` AppleScript-Fehler
    −1728 (live verifiziert) — daher wird der State zuerst geprüft.
    """
    state = await _osascript(_tell("player state as text"))
    if state not in ("playing", "paused"):
        return None
    raw = await _osascript(_tell(
        "name of current track & linefeed & artist of current track "
        "& linefeed & album of current track"
    ))
    parts = (raw.split("\n") + ["", "", ""])[:3]
    return TrackInfo(title=parts[0], artist=parts[1], album=parts[2], state=state)
```

- [ ] **Step 4: Tests laufen lassen, Bestehen verifizieren**

Run: `cd ~/Mantis && python3.14 -m pytest tests/test_spotify.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
cd ~/Mantis && git add tools/spotify/ tests/test_spotify.py \
  && git commit -m "feat: Spotify-AppleScript-Treiber (Playback, Volume, Track-Info)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Web-API-Suche `tools/spotify/web_api.py` + Settings

**Files:**
- Create: `tools/spotify/web_api.py`
- Modify: `settings.py` (nach dem `BRAVE_API_KEY`-Block, ~Zeile 95)
- Modify: `.env.example` (SPOTIFY-Block ergänzen)
- Test: `tests/test_spotify.py` (erweitern)

**Interfaces:**
- Consumes: `from settings import cfg` (`cfg.SPOTIFY_CLIENT_ID`, `cfg.SPOTIFY_CLIENT_SECRET`)
- Produces (von Task 3 genutzt):
  - `class SpotifySearchError(RuntimeError)`
  - `def credentials_missing() -> bool`
  - `async def search(query: str, typ: str | None = None) -> tuple[str, str] | None` — `(uri, anzeigename)` oder None; `typ` ∈ {track, album, playlist, artist} erzwingt den Ergebnistyp, sonst Präferenz track > album > playlist > artist
  - intern: `async def _http_post_token() -> dict`, `async def _http_get_search(params: dict, token: str) -> dict` — Tests patchen genau diese beiden

- [ ] **Step 1: Failing Tests ergänzen** — an `tests/test_spotify.py` anhängen:

```python
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
```

- [ ] **Step 2: Tests laufen lassen, Scheitern verifizieren**

Run: `cd ~/Mantis && python3.14 -m pytest tests/test_spotify.py -q`
Expected: FAIL mit `ImportError: cannot import name 'web_api'` (o.ä.)

- [ ] **Step 3: Settings erweitern** — in `settings.py` nach dem `BRAVE_API_KEY`-Block einfügen:

```python
    # ── Spotify (nur für die Suche in „spiel [X]"; Playback läuft lokal) ─────
    # Kostenlose App auf developer.spotify.com anlegen; leer = Suche deaktiviert,
    # Play/Pause/Volume/Status funktionieren trotzdem (reines AppleScript).
    SPOTIFY_CLIENT_ID: str = ""
    SPOTIFY_CLIENT_SECRET: str = ""
```

Und in `.env.example` analog zum bestehenden Stil ergänzen:

```
# Spotify-Suche für „spiel [X]" (developer.spotify.com, kostenlos; optional)
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
```

- [ ] **Step 4: Implementierung** — `tools/spotify/web_api.py`:

```python
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
```

- [ ] **Step 5: Tests laufen lassen, Bestehen verifizieren**

Run: `cd ~/Mantis && python3.14 -m pytest tests/test_spotify.py -q`
Expected: alle Tests grün (11 passed)

- [ ] **Step 6: Commit**

```bash
cd ~/Mantis && git add tools/spotify/web_api.py settings.py .env.example tests/test_spotify.py \
  && git commit -m "feat: Spotify-Web-API-Suche (Client-Credentials, Token-Cache)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Tool-Registrierung `core/skills/spotify.py`

**Files:**
- Create: `core/skills/spotify.py`
- Modify: `core/skills/__init__.py` (Import `spotify` in der `from . import (…)`-Liste ergänzen, nach `flipper`)
- Modify: `core/tools.py` (`_CATEGORY_KEYWORDS`: Eintrag `"spotify"` nach `"flipper"`)
- Test: `tests/test_spotify.py` (erweitern)

**Interfaces:**
- Consumes: `tools.spotify.applescript` (Task 1), `tools.spotify.web_api` (Task 2), `core.tools.register`
- Produces: registriertes Tool `spotify` (Kategorie `spotify`), Handler `_spotify(action, query="", volume=-1, typ="")` — von Task 4 (Fast-Paths) per Tool-Name `"spotify"` mit `{"action": …}` aufgerufen

- [ ] **Step 1: Failing Tests ergänzen** — an `tests/test_spotify.py` anhängen:

```python
# ── Registriertes Tool ────────────────────────────────────────────────────────

def test_skill_status_stopped():
    calls: list = []
    _patch_osa(calls, reply="stopped")
    from core.skills.spotify import _spotify
    assert asyncio.run(_spotify("status")) == "🔇 Gerade läuft nichts."


def test_skill_status_playing():
    def reply(script):
        return "playing" if "player state" in script else "Kids\nMGMT\nOracular"
    _patch_osa([], reply=reply)
    from core.skills.spotify import _spotify
    assert asyncio.run(_spotify("status")) == "🎵 Kids — MGMT · Oracular"


def test_skill_pause_and_volume():
    calls: list = []
    _patch_osa(calls)
    from core.skills.spotify import _spotify
    assert asyncio.run(_spotify("pause")) == "⏸️ Pausiert"
    assert asyncio.run(_spotify("volume", volume=40)) == "🔊 Lautstärke 40 %"
    assert asyncio.run(_spotify("volume")) == "❌ Bitte volume 0-100 angeben."


def test_skill_spiel_without_credentials_gives_setup_hint():
    from core.skills import spotify as skill
    old = (cfg.SPOTIFY_CLIENT_ID, cfg.SPOTIFY_CLIENT_SECRET)
    try:
        cfg.SPOTIFY_CLIENT_ID, cfg.SPOTIFY_CLIENT_SECRET = "", ""
        out = asyncio.run(skill._spotify("spiel", query="kids"))
        assert "developer.spotify.com" in out
    finally:
        cfg.SPOTIFY_CLIENT_ID, cfg.SPOTIFY_CLIENT_SECRET = old


def test_skill_spiel_plays_best_hit():
    _reset_webapi()
    calls: list = []
    _patch_osa(calls)
    _patch_http({"tracks": {"items": [{"uri": "spotify:track:t1", "name": "Kids",
                                       "artists": [{"name": "MGMT"}]}]}})
    from core.skills import spotify as skill
    old = (cfg.SPOTIFY_CLIENT_ID, cfg.SPOTIFY_CLIENT_SECRET)
    try:
        cfg.SPOTIFY_CLIENT_ID, cfg.SPOTIFY_CLIENT_SECRET = "id", "secret"
        out = asyncio.run(skill._spotify("spiel", query="kids"))
    finally:
        cfg.SPOTIFY_CLIENT_ID, cfg.SPOTIFY_CLIENT_SECRET = old
    assert out == "▶️ Kids — MGMT"
    assert calls[-1] == 'tell application "Spotify" to play track "spotify:track:t1"'


def test_skill_osascript_error_is_friendly():
    async def broken(script):
        raise sp.SpotifyError("kaputt")
    sp._osascript = broken
    from core.skills.spotify import _spotify
    out = asyncio.run(_spotify("play"))
    assert out.startswith("❌ Spotify nicht steuerbar")


def test_spotify_tool_is_registered():
    import core.skills  # noqa: F401 — löst Registrierung aus
    from core import tools as T
    assert "spotify" in T.REGISTRY
    assert T.REGISTRY["spotify"].category == "spotify"
```

- [ ] **Step 2: Tests laufen lassen, Scheitern verifizieren**

Run: `cd ~/Mantis && python3.14 -m pytest tests/test_spotify.py -q`
Expected: FAIL mit `ModuleNotFoundError: No module named 'core.skills.spotify'`

- [ ] **Step 3: Implementierung** — `core/skills/spotify.py`:

```python
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
```

- [ ] **Step 4: Verdrahtung** — in `core/skills/__init__.py` den Import ergänzen (`flipper,` → `flipper,\n    spotify,`). In `core/tools.py` in `_CATEGORY_KEYWORDS` nach dem `"flipper"`-Eintrag:

```python
    "spotify":      ["musik", "spotify", "song", "playlist", "lautstärke", "lauter",
                     "leiser", "abspielen", "pausier", "was läuft", "nächstes lied",
                     "spiel mal", "spiel was", "spiel etwas", "spiel mir",
                     "spiel den", "spiel die", "spiel das"],
```

(Bewusst KEIN nacktes `"spiel"`/`"lied"` — Substring-Matching würde „beispiel"/„mitglied" treffen.)

- [ ] **Step 5: Tests laufen lassen, Bestehen verifizieren**

Run: `cd ~/Mantis && python3.14 -m pytest tests/test_spotify.py -q`
Expected: alle grün (18 passed)

- [ ] **Step 6: Gesamte Suite + Lint**

Run: `cd ~/Mantis && python3.14 -m pytest -q && python3.14 -m ruff check .`
Expected: 665 passed (647 + 18), ruff ohne Findings

- [ ] **Step 7: Commit**

```bash
cd ~/Mantis && git add core/skills/spotify.py core/skills/__init__.py core/tools.py tests/test_spotify.py \
  && git commit -m "feat: spotify-Tool registriert (play/pause/next/volume/status/spiel)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Deterministische Fast-Paths für Musik

**Files:**
- Modify: `core/fast_commands.py` (Wortlisten nach `_HARD_STOP`, Musik-Block in `match()` zwischen Roboter- und Lampen-Block)
- Test: `tests/test_fast_commands.py` (erweitern)

**Interfaces:**
- Consumes: Tool-Name `"spotify"` mit `{"action": "play"|"pause"|"next"|"previous"}` (Task 3); `core/message_handler.py:162` führt Matches unverändert über `skills.T.execute` aus — dort ist NICHTS zu ändern
- Produces: erweiterte `match()`-Regeln

- [ ] **Step 1: Failing Tests ergänzen** — an `tests/test_fast_commands.py` anhängen:

```python
# ── Positive: Musik (Spotify) ─────────────────────────────────────────────────

def test_music_play():
    assert _m("musik an") == ("spotify", {"action": "play"})
    assert _m("musik weiter") == ("spotify", {"action": "play"})
    assert _m("spiel musik") == ("spotify", {"action": "play"})
    assert _m("mach die musik wieder an") == ("spotify", {"action": "play"})


def test_music_pause():
    assert _m("musik pause") == ("spotify", {"action": "pause"})
    assert _m("stopp die musik") == ("spotify", {"action": "pause"})
    assert _m("mach die musik aus") == ("spotify", {"action": "pause"})


def test_music_next_prev():
    assert _m("nächstes lied") == ("spotify", {"action": "next"})
    assert _m("nächster song") == ("spotify", {"action": "next"})
    assert _m("musik zurück") == ("spotify", {"action": "previous"})


def test_music_single_word_commands():
    assert _m("pause") == ("spotify", {"action": "pause"})
    assert _m("skip") == ("spotify", {"action": "next"})
    assert _m("next") == ("spotify", {"action": "next"})


# ── Negativ: Musik kapert keine Konversation ─────────────────────────────────

def test_pause_in_sentence_not_music():
    assert match("ich mach mal pause") is None
    assert match("lass uns eine pause machen") is None


def test_weiter_in_conversation_not_music():
    assert match("weiter gehts mit dem projekt") is None
    assert match("erzähl weiter") is None


def test_music_question_never_matches():
    assert match("läuft gerade musik?") is None
    assert match("welches lied ist das?") is None


def test_music_statement_not_command():
    assert match("die musik ist aus") is None
    assert match("ich höre gerade musik und mach dann weiter") is None


def test_music_with_query_goes_to_agent():
    # „von" signalisiert eine Such-Anfrage → Agent (braucht Web-API-Suche)
    assert match("mach die musik von queen an") is None
    assert match("spiel bohemian rhapsody von queen") is None
```

- [ ] **Step 2: Tests laufen lassen, Scheitern verifizieren**

Run: `cd ~/Mantis && python3.14 -m pytest tests/test_fast_commands.py -q`
Expected: die neuen Musik-Tests FAILen, alle bestehenden bleiben grün

- [ ] **Step 3: Implementierung** — in `core/fast_commands.py` nach den `_HARD_STOP`-Definitionen:

```python
_MUSIC = {"musik", "spotify", "lied", "song"}
_MUSIC_NEXT = {"nächstes", "nächster", "nächste", "skip", "next", "überspringen", "überspring"}
_MUSIC_PREV = {"vorheriges", "vorheriger", "vorherige", "zurück", "previous"}
_MUSIC_PAUSE = {"pause", "pausiere", "pausieren", "stopp", "stop", "aus", "ausmachen"}
_MUSIC_PLAY = {"an", "play", "weiter", "abspielen", "spiel", "spiele", "anmachen"}
```

Und in `match()` NACH dem Roboter-Block, VOR dem Lampen-Block:

```python
    # ── Musik (Spotify) ───────────────────────────────────────────────────────
    if w & _MUSIC:
        # Nur echte Kommandos: kurz ("musik an") oder Kommando-Verb in über-
        # schaubarer Länge ("mach die musik aus"). "von" signalisiert eine
        # Such-Anfrage ("spiel musik von queen") → Agent mit Web-API-Suche.
        if "von" not in w and (len(w) <= 3 or (w & _CMD_VERBS and len(w) <= 6)):
            if w & _MUSIC_NEXT:
                return FastCommand("spotify", {"action": "next"}, "musik-next")
            if w & _MUSIC_PREV:
                return FastCommand("spotify", {"action": "previous"}, "musik-previous")
            if w & _MUSIC_PAUSE:
                return FastCommand("spotify", {"action": "pause"}, "musik-pause")
            if w & _MUSIC_PLAY:
                return FastCommand("spotify", {"action": "play"}, "musik-play")
    elif len(w) == 1:
        # Ein-Wort-Befehle sind auch ohne Musik-Kontextwort eindeutig.
        if w & {"pause"}:
            return FastCommand("spotify", {"action": "pause"}, "musik-pause")
        if w & {"skip", "next"}:
            return FastCommand("spotify", {"action": "next"}, "musik-next")
```

**Achtung Reihenfolge:** `_MUSIC_NEXT`/`_MUSIC_PREV` VOR `_MUSIC_PAUSE`/`_MUSIC_PLAY` prüfen — „nächstes lied" enthält kein Play-Wort, aber „musik weiter" darf nicht versehentlich als next enden. Der Roboter-Block muss davor bleiben („roboter stopp" ≠ Musik).

- [ ] **Step 4: Tests laufen lassen, Bestehen verifizieren**

Run: `cd ~/Mantis && python3.14 -m pytest tests/test_fast_commands.py tests/test_spotify.py -q`
Expected: alle grün, inkl. der alten Negativ-Fälle (`test_bare_stop_not_robot` etc.)

- [ ] **Step 5: Commit**

```bash
cd ~/Mantis && git add core/fast_commands.py tests/test_fast_commands.py \
  && git commit -m "feat: Fast-Paths für Musiksteuerung (play/pause/next/prev, eng gefasst)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Live-Verifikation, Doku, Push

**Files:**
- Modify: `ROADMAP.md` (Spotify-Steuerung als erledigt vermerken, Stil des Dokuments folgen)
- Kein neuer Code — Verifikation am laufenden System

**Interfaces:**
- Consumes: alles aus Task 1–4, `./start.sh`, Log `/tmp/mantis_out.log`, Chat-API Port 7779

- [ ] **Step 1: Volle Suite + Lint**

Run: `cd ~/Mantis && python3.14 -m pytest -q && python3.14 -m ruff check .`
Expected: alle Tests grün, ruff sauber

- [ ] **Step 2: Neustart + Boot-Check**

Run: `cd ~/Mantis && ./start.sh && sleep 8 && grep "Tools verf" /tmp/mantis_out.log | tail -1`
Expected: Boot-Zeile erscheint, Tool-Anzahl um 1 höher als zuvor (spotify registriert)

- [ ] **Step 3: Live-Test Fast-Path über die Chat-API** (echtes Spotify!)

Run: `curl -s -X POST http://127.0.0.1:7779/api/chat -H "Content-Type: application/json" -d '{"text":"musik an"}'`
Expected: Antwort `▶️ Musik läuft`, Spotify beginnt hörbar zu spielen (bzw. bleibt bei leerem Kontext still — dann Status prüfen). Danach:

Run: `curl -s -X POST http://127.0.0.1:7779/api/chat -H "Content-Type: application/json" -d '{"text":"was läuft gerade"}'`
Expected: 🎵-Status mit Titel — Künstler (über den Agenten, kein Fast-Path)

Run: `curl -s -X POST http://127.0.0.1:7779/api/chat -H "Content-Type: application/json" -d '{"text":"musik aus"}'`
Expected: `⏸️ Pausiert`, Musik stoppt hörbar. Log gegenprüfen: `grep "Fast-Path musik" /tmp/mantis_out.log`

- [ ] **Step 4: „spiel [X]"-Pfad prüfen** — je nach Credentials-Stand:

Run: `curl -s -X POST http://127.0.0.1:7779/api/chat -H "Content-Type: application/json" -d '{"text":"spiel kids von mgmt"}'`
Expected: OHNE Credentials → 🎧-Setup-Hinweis (developer.spotify.com). MIT Credentials → `▶️ Kids — MGMT` und Spotify spielt den Track.

- [ ] **Step 5: ROADMAP aktualisieren + committen**

`ROADMAP.md`: Spotify-Steuerung unter Erledigt/Features eintragen (ein Satz, Datum 2026-07-10, Verweis auf Spec). Dann:

```bash
cd ~/Mantis && git add ROADMAP.md docs/superpowers/plans/2026-07-10-spotify-control.md \
  && git commit -m "docs: Spotify-Steuerung in ROADMAP + Implementierungsplan

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Push + CI**

```bash
cd ~/Mantis && git push && gh run watch $(gh run list -L1 --json databaseId --jq '.[0].databaseId') --exit-status
```

Expected: CI (lint + pytest) grün

- [ ] **Step 7: Memory aktualisieren** — in `~/.claude/projects/-Users-timoegersdorfer/memory/jarvis-project.md` die Spotify-Steuerung als neues Feature ergänzen (Tool `spotify`, Fast-Paths, Credentials-Stand).
