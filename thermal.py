"""
Thermal Manager – hält Mac warm aber nicht heiß.

Strategie: Proportional-Controller (P-Controller)
- Messe Temperatur alle N Sekunden
- Berechne wie weit wir vom Ziel entfernt sind
- Passe Sleep-Zeit zwischen Inference-Calls proportional an
- Ziel: Chip warm (~THERMAL_TARGET_CELSIUS), Gehäuse warm aber nicht heiß

Austauschbar: Implementiere ThermalStrategy um Algorithmus zu wechseln.
"""
import asyncio
import logging
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import config

log = logging.getLogger(__name__)


@dataclass
class ThermalState:
    temp_celsius: float
    sleep_seconds: float
    throttled: bool
    paused: bool


class ThermalStrategy(ABC):
    """Interface für Throttling-Algorithmen. Tauschbar."""

    @abstractmethod
    def compute_sleep(self, current_temp: float, target: float, max_temp: float) -> float:
        """Gibt empfohlene Sleep-Zeit in Sekunden zurück."""
        ...

    @abstractmethod
    def should_pause(self, current_temp: float, max_temp: float) -> bool:
        """True = Inference komplett pausieren."""
        ...


class ProportionalStrategy(ThermalStrategy):
    """
    P-Controller: Sleep proportional zur Übertemperatur.
    Kein Sleep wenn unter Ziel, maximaler Sleep wenn über Max.
    """

    def __init__(self, min_sleep: float = 0.0, max_sleep: float = 30.0):
        self.min_sleep = min_sleep
        self.max_sleep = max_sleep

    def compute_sleep(self, current_temp: float, target: float, max_temp: float) -> float:
        if current_temp <= target:
            return self.min_sleep  # Volle Geschwindigkeit

        overshoot = current_temp - target
        range_size = max_temp - target
        # max_temp <= target (Fehlkonfiguration) → über Ziel = sofort maximal bremsen,
        # ohne Division durch Null.
        ratio = 1.0 if range_size <= 0 else min(overshoot / range_size, 1.0)

        return self.min_sleep + ratio * (self.max_sleep - self.min_sleep)

    def should_pause(self, current_temp: float, max_temp: float) -> bool:
        return current_temp >= max_temp


class ThermalMonitor:
    """
    Liest macOS-Temperatur und berechnet Throttling.
    Nutzt 'osx-cpu-temp' falls installiert, sonst powermetrics (braucht sudo).
    """

    def __init__(
        self,
        strategy: ThermalStrategy | None = None,
        target: float | None = None,
        max_temp: float | None = None,
    ):
        self.target   = target   or config.THERMAL_TARGET_CELSIUS
        self.max_temp = max_temp or config.THERMAL_MAX_CELSIUS
        self.strategy = strategy or ProportionalStrategy(
            min_sleep=config.IDLE_MIN_SLEEP_S,
            max_sleep=config.IDLE_MAX_SLEEP_S,
        )
        self._last_temp: float = 50.0
        self._last_read: float = 0.0
        self._read_interval: float = 10.0  # Sekunden zwischen Messungen

    def _read_temp_osx_cpu_temp(self) -> float | None:
        """Liest Temperatur via osx-cpu-temp (kein sudo nötig)."""
        try:
            result = subprocess.run(
                ["osx-cpu-temp"],
                capture_output=True, text=True, timeout=2
            )
            # Output: "50.2°C"
            raw = result.stdout.strip().replace("°C", "").replace(",", ".")
            return float(raw)
        except Exception:
            return None

    def _read_temp_smc(self) -> float | None:
        """Liest Temperatur via smc tool (kein sudo nötig)."""
        try:
            result = subprocess.run(
                ["smc", "-k", "TC0P", "-r"],
                capture_output=True, text=True, timeout=2
            )
            # Output enthält Temperaturwert
            for part in result.stdout.split():
                try:
                    val = float(part)
                    if 20 < val < 120:
                        return val
                except ValueError:
                    continue
        except Exception:
            return None

    def _read_temp_psutil(self) -> float | None:
        """Fallback: psutil (funktioniert auf macOS eingeschränkt)."""
        try:
            import psutil
            temps = psutil.sensors_temperatures()
            if temps:
                for readings in temps.values():
                    for r in readings:
                        if 20 < r.current < 120:
                            return r.current
        except Exception:
            pass
        return None

    def get_temperature(self) -> float:
        """Gibt aktuelle CPU-Temperatur zurück. Cached für 10 Sekunden."""
        now = time.time()
        if now - self._last_read < self._read_interval:
            return self._last_temp

        temp = (
            self._read_temp_osx_cpu_temp()
            or self._read_temp_smc()
            or self._read_temp_psutil()
        )

        if temp is not None:
            self._last_temp = temp
        self._last_read = now
        return self._last_temp

    def get_state(self) -> ThermalState:
        temp = self.get_temperature()
        sleep = self.strategy.compute_sleep(temp, self.target, self.max_temp)
        paused = self.strategy.should_pause(temp, self.max_temp)
        throttled = sleep > self.strategy.min_sleep if isinstance(
            self.strategy, ProportionalStrategy) else sleep > 0

        return ThermalState(
            temp_celsius=temp,
            sleep_seconds=sleep,
            throttled=throttled,
            paused=paused,
        )

    async def wait(self) -> None:
        """
        Warte die thermisch berechnete Zeit.
        Rufe das vor/nach jedem Inference-Call im Idle Loop auf.
        """
        state = self.get_state()
        if state.sleep_seconds > 0:
            await asyncio.sleep(state.sleep_seconds)

    async def wait_until_cool(self) -> None:
        """Blockiert bis Temperatur unter Max fällt."""
        while True:
            state = self.get_state()
            if not state.paused:
                return
            log.warning(f"🌡️ Zu heiß ({state.temp_celsius:.1f}°C) – warte...")
            await asyncio.sleep(30)
