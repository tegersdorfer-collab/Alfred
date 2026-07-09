"""Dauerhafter Verbindungs-Manager für den X5-Droid.

BLE-Connect ist langsam und exklusiv — daher hält Mantis genau *eine* langlebige
Verbindung offen (lazy aufgebaut beim ersten Befehl), mit Auto-Reconnect und
gecachtem Sensor-Stream. Wird von den Mantis-Tools in core/skills/robot.py genutzt.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from . import driver
from . import protocol as P

log = logging.getLogger("tools.robot")


class RobotManager:
    """Singleton-artiger Halter für die eine X5-Verbindung."""

    def __init__(self) -> None:
        self._robot: Optional[driver.X5Robot] = None
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._robot is not None and self._robot.is_connected

    async def _ensure(self) -> driver.X5Robot:
        """Verbindung sicherstellen (verbinden oder wiederverbinden)."""
        async with self._lock:
            if self.connected:
                return self._robot  # type: ignore[return-value]
            # Absturz-Schutz: fehlt auf macOS die Bluetooth-Berechtigung, würde der
            # BLE-Zugriff den GANZEN Prozess killen (SIGABRT). Lieber sauber ablehnen.
            from .platform_check import bluetooth_entitlement_ok, entitlement_hint
            if not bluetooth_entitlement_ok():
                raise RuntimeError(entitlement_hint())
            log.info("Verbinde mit X5 (%s) ...", P.DEVICE_NAME)
            self._robot = await driver.connect()
            log.info("X5 verbunden.")
            return self._robot

    async def _run(self, method: str, *args) -> None:
        """High-Level-Aktion ausführen, bei BLE-Fehler einmal neu verbinden."""
        for attempt in (1, 2):
            robot = await self._ensure()
            try:
                await getattr(robot, method)(*args)
                return
            except Exception as e:
                log.warning("Roboter-Aktion '%s' fehlgeschlagen (Versuch %d): %s", method, attempt, e)
                self._robot = None  # Reconnect beim nächsten Versuch erzwingen
                if attempt == 2:
                    raise

    # ── von den Tools genutzte High-Level-Aktionen ───────────────────────────
    async def drive(self, action: str, power: float, secs: float) -> str:
        mapping = {
            "vor": ("forward", "fährt vorwärts"),
            "zurueck": ("backward", "fährt rückwärts"),
            "links": ("turn_left", "dreht links"),
            "rechts": ("turn_right", "dreht rechts"),
        }
        if action not in mapping:
            return f"❌ Unbekannte Fahraktion '{action}'."
        method, label = mapping[action]
        await self._run(method, power, secs)
        return f"🤖 {label} ({power:.0%}, {secs:.1f}s)"

    async def stop(self) -> str:
        await self._run("stop")
        return "🛑 gestoppt"

    async def gripper(self, open_: bool) -> str:
        await self._run("grip_open" if open_ else "grip_close")
        return "✋ Greifer auf" if open_ else "🤏 Greifer zu"

    async def sound(self, sound_id: int) -> str:
        await self._run("play_sound", sound_id)
        return f"🔊 Sound {sound_id}"

    async def sensors(self) -> Optional[P.Sensors]:
        await self._ensure()
        return self._robot.sensors if self._robot else None

    async def disconnect(self) -> None:
        if self._robot is not None:
            await self._robot.disconnect()
            self._robot = None


# Prozessweiter Singleton — von den Mantis-Tools importiert.
MANAGER = RobotManager()
