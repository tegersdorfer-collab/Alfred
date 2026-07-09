"""Flipper-Zero-Serial-CLI-Treiber — Mantis spricht die eingebaute CLI über USB.

Der Flipper meldet sich als USB-CDC-Serial-Gerät (`/dev/cu.usbmodemflip_*`). Seine
CLI nimmt Befehle mit `\\r\\n` entgegen und antwortet bis zum Prompt `>: `. USB-CDC
ignoriert die Baudrate, daher genügt ein rohes `os.open` auf dem tty — kein pyserial.

Blockierendes Serial-IO läuft über `asyncio.to_thread`, damit Mantis' Event-Loop frei
bleibt. Für IR brauchen wir nur zwei Befehle: `ir rx` (lernen) und `ir tx` (senden).
"""

from __future__ import annotations

import asyncio
import glob
import logging
import os
import select
import time
from typing import Optional

log = logging.getLogger("tools.flipper")

DEVICE_GLOB = "/dev/cu.usbmodemflip_*"
_PROMPT = b">: "


def find_port() -> Optional[str]:
    """Ersten angeschlossenen Flipper-Serial-Port finden (oder None)."""
    ports = sorted(glob.glob(DEVICE_GLOB))
    return ports[0] if ports else None


def _talk(cmd: str, read_secs: float) -> str:
    """Blockierend (im Thread!): einen CLI-Befehl schicken und die Antwort lesen."""
    port = find_port()
    if port is None:
        raise RuntimeError("Kein Flipper gefunden — hängt er per USB am Mac?")
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        def rd(t: float) -> bytes:
            end = time.time() + t
            buf = b""
            while time.time() < end:
                r, _, _ = select.select([fd], [], [], 0.15)
                if r:
                    try:
                        buf += os.read(fd, 4096)
                    except OSError:
                        pass
                elif buf.endswith(_PROMPT):
                    break  # Antwort komplett (Prompt wieder da)
            return buf

        time.sleep(0.15)
        os.write(fd, b"\r\n")
        time.sleep(0.1)
        rd(0.4)  # Banner/alten Prompt wegspülen
        os.write(fd, (cmd + "\r\n").encode())
        return rd(read_secs).decode("utf-8", "replace")
    finally:
        os.close(fd)


async def talk(cmd: str, read_secs: float = 2.0) -> str:
    """Einen Flipper-CLI-Befehl asynchron ausführen und die Antwort zurückgeben."""
    return await asyncio.to_thread(_talk, cmd, read_secs)


async def ir_tx(protocol: str, address: str, command: str) -> str:
    """Ein IR-Signal senden (Adresse/Befehl hex-formatiert, z.B. 'EF00' / 'FC03')."""
    return await talk(f"ir tx {protocol} {address} {command}")
