"""Autonomer Fahrmodus für den X5-Droid — wandern & Hindernissen ausweichen.

Verhalten: vorwärts fahren; wird der vordere IR-Sensor über die Schwelle
ausgelöst (Objekt nah), anhalten → zurücksetzen → drehen → weiter. Läuft als
asyncio-Hintergrund-Task in Mantis' Event-Loop, start-/stoppbar per Tool.

Sicherheit:
- Fahrbefehle sind zeitbegrenzt (auto-stopp nach `fwd_secs`), etwas länger als das
  Loop-Intervall → kontinuierliche Fahrt, aber bei Absturz/Cancel stoppt der Droid
  von selbst in <1 s.
- Globaler Auto-Stopp nach `max_seconds`, falls jemand ihn laufen lässt.
- Bei jedem BLE-Fehler: Loop endet, Motoren werden gebremst.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from .manager import MANAGER

log = logging.getLogger("tools.robot")


class Autonomy:
    def __init__(self, manager=None) -> None:
        self.mgr = manager or MANAGER
        self._task: Optional[asyncio.Task] = None
        self.status = "aus"

        # Tunables
        self.front = "ir0"       # welcher Sensor vorne ist (empirisch prüfen)
        self.threshold = 60      # Sensorwert ab dem ein Hindernis gilt (Ruhe≈13)
        self.power = 0.45
        self.max_seconds = 300   # globaler Sicherheits-Auto-Stopp

        # Manöver-Timings (als Attribute → in Tests auf 0 setzbar)
        self.fwd_secs = 0.7
        self.fwd_interval = 0.35
        self.back_secs = 0.5
        self.back_pause = 0.55
        self.turn_secs = 0.6
        self.turn_pause = 0.65

        self._turn_dir = "rechts"

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def status_line(self) -> str:
        state = "AKTIV" if self.running else "aus"
        return (f"Autonomie: {state} · Status '{self.status}' · "
                f"Schwelle {self.threshold} · Front-Sensor {self.front}")

    # ── Steuerung ────────────────────────────────────────────────────────────
    async def start(self) -> str:
        if self.running:
            return "Autonomie läuft bereits."
        self._task = asyncio.create_task(self._loop())
        return (f"🧭 Autonomie gestartet (Hindernis-Schwelle {self.threshold}, "
                f"Auto-Stopp nach {self.max_seconds}s).")

    async def stop(self) -> str:
        was_running = self.running
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self.status = "aus"
        try:
            await self.mgr.stop()
        except Exception:
            pass
        return "🛑 Autonomie gestoppt." if was_running else "Autonomie war nicht aktiv (Motoren gestoppt)."

    # ── ein Schritt (testbar) ────────────────────────────────────────────────
    async def _front_value(self) -> Optional[int]:
        s = await self.mgr.sensors()
        if s is None:
            return None
        return getattr(s, self.front, s.ir0)

    async def step(self) -> str:
        """Eine Wahrnehmen-Entscheiden-Handeln-Iteration. Gibt die Aktion zurück."""
        front = await self._front_value()
        if front is None:
            self.status = "warte auf Sensoren"
            return "no-data"
        if front > self.threshold:
            await self._avoid()
            return "avoid"
        self.status = "fährt"
        await self.mgr.drive("vor", self.power, self.fwd_secs)
        return "forward"

    async def _avoid(self) -> None:
        self.status = "weicht aus"
        await self.mgr.stop()
        await self.mgr.drive("zurueck", self.power, self.back_secs)
        await asyncio.sleep(self.back_pause)
        # Drehrichtung abwechseln, um nicht in Ecken festzuhängen
        self._turn_dir = "links" if self._turn_dir == "rechts" else "rechts"
        await self.mgr.drive(self._turn_dir, self.power, self.turn_secs)
        await asyncio.sleep(self.turn_pause)

    # ── Loop ─────────────────────────────────────────────────────────────────
    async def _loop(self) -> None:
        start = time.monotonic()
        try:
            while True:
                if time.monotonic() - start > self.max_seconds:
                    self.status = "auto-stopp (Zeit)"
                    break
                action = await self.step()
                if action == "no-data":
                    await asyncio.sleep(0.3)
                elif action == "forward":
                    await asyncio.sleep(self.fwd_interval)
                # nach 'avoid' direkt weiter (hat selbst schon pausiert)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("Autonomie-Loop-Fehler: %s", e)
            self.status = f"fehler: {e}"
        finally:
            try:
                await self.mgr.stop()
            except Exception:
                pass


# Prozessweiter Singleton.
AUTO = Autonomy()
