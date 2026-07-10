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
