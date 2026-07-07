"""X5-Droid-Steuerung für Mantis (Clementoni RoboMaker, BLE-Name 'EVRobot2').

Protokoll siehe docs/robot/protocol.md (per Reverse-Engineering der App ermittelt).
- `protocol`  — reine Logik: Paket-Builder + Sensor-Parser (kein BLE, unit-testbar)
- `driver`    — asynchroner BLE-Treiber (bleak) mit High-Level-Aktionen
"""

from .driver import X5Robot, connect
from . import protocol

__all__ = ["X5Robot", "connect", "protocol"]
