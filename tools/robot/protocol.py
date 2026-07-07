"""Reines X5-Protokoll — Konstanten, Paket-Builder, Sensor-Parser. Kein BLE.

Quelle: Reverse-Engineering der App it.clementoni.robomaker (siehe
docs/robot/protocol.md). Alles hier ist pure Logik und ohne Hardware testbar.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── BLE-Kanäle (Charakteristik-UUIDs) ────────────────────────────────────────
DEVICE_NAME = "EVRobot2"
CH_SENSORS = "5e366294-5436-4356-a009-7ccd1e03526d"  # Handle 15, notify
CH_MOTORS = "165aecf8-ed44-45e7-aae4-63789234a30f"   # Handle 18, write
CH_AUDIO = "cc9151df-c5eb-477a-a793-287a5500fc81"    # Handle 20, write

# ── Motor-Befehlscodes (aus der App: .cctor) ─────────────────────────────────
BACKWARD = 0
FORWARD = 1
BRAKE = 2

# Physische Zuordnung (empirisch bestätigt): Antriebsmotoren spiegelverkehrt.
#   Motor 0 = linkes Rad:  0x00 -> vorwärts, 0x01 -> rückwärts
#   Motor 1 = rechtes Rad: 0x01 -> vorwärts, 0x00 -> rückwärts
#   Motor 2 = Greifer:     0x01 -> auf,      0x00 -> zu
LEFT_FWD, LEFT_BACK = BACKWARD, FORWARD
RIGHT_FWD, RIGHT_BACK = FORWARD, BACKWARD
GRIP_OPEN, GRIP_CLOSE = FORWARD, BACKWARD

MAX_SECS = 2.55  # time-Byte ist auf 2.55 s gedeckelt (0 = Dauerlauf bis nächster Befehl)


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _pow_byte(power: float) -> int:
    """Leistung 0.0..1.0 -> 0..255."""
    return int(_clamp(power, 0.0, 1.0) * 255)


def _time_byte(secs: float) -> int:
    """Laufzeit in Sekunden -> 0..255 (Sekunden*100, gedeckelt auf 2.55 s)."""
    return int(_clamp(secs, 0.0, MAX_SECS) * 100)


def motor_triplet(cmd: int, power: float, secs: float) -> bytes:
    """Ein Motor: [cmd, power, time] (3 Bytes)."""
    return bytes([cmd & 0xFF, _pow_byte(power), _time_byte(secs)])


def motors(m0: tuple, m1: tuple, m2: tuple) -> bytes:
    """9-Byte-Motorpaket für CH_MOTORS. Jedes m = (cmd, power, secs)."""
    return b"".join(motor_triplet(*m) for m in (m0, m1, m2))


# ── High-Level-Rezepte → jeweils fertiges 9-Byte-Paket ───────────────────────
def forward(power: float = 0.4, secs: float = 0.0) -> bytes:
    return motors((LEFT_FWD, power, secs), (RIGHT_FWD, power, secs), (BRAKE, 0, 0))


def backward(power: float = 0.4, secs: float = 0.0) -> bytes:
    return motors((LEFT_BACK, power, secs), (RIGHT_BACK, power, secs), (BRAKE, 0, 0))


def turn_left(power: float = 0.4, secs: float = 0.0) -> bytes:
    """Auf der Stelle nach links drehen (CCW): links rückwärts, rechts vorwärts."""
    return motors((LEFT_BACK, power, secs), (RIGHT_FWD, power, secs), (BRAKE, 0, 0))


def turn_right(power: float = 0.4, secs: float = 0.0) -> bytes:
    """Auf der Stelle nach rechts drehen (CW): links vorwärts, rechts rückwärts."""
    return motors((LEFT_FWD, power, secs), (RIGHT_BACK, power, secs), (BRAKE, 0, 0))


def stop() -> bytes:
    """Alle Motoren bremsen."""
    return motors((BRAKE, 0, 0), (BRAKE, 0, 0), (BRAKE, 0, 0))


def grip_open(power: float = 1.0, secs: float = 1.0) -> bytes:
    return motors((BRAKE, 0, 0), (BRAKE, 0, 0), (GRIP_OPEN, power, secs))


def grip_close(power: float = 1.0, secs: float = 1.0) -> bytes:
    return motors((BRAKE, 0, 0), (BRAKE, 0, 0), (GRIP_CLOSE, power, secs))


def sound(sound_id: int) -> bytes:
    """1-Byte-Paket für CH_AUDIO. Gültige IDs 0x01..0x0f (>=0x16 trennt die Verbindung!)."""
    return bytes([sound_id & 0xFF])


# ── Sensor-Stream (Notify auf CH_SENSORS) ────────────────────────────────────
@dataclass(frozen=True)
class Sensors:
    """9-Byte-Sensorframe: 4x uint16 LE + Terminator. Höher = Objekt näher."""

    ir0: int       # vorderer/hinterer IR-Sensor (Ruhewert ~13)
    ir1: int       # zweiter IR-Sensor
    pressure: int  # Greifer-Drucksensor (_sensor_pression)
    ch3: int       # bisher konstant
    raw: bytes

    IDLE = 13  # Ruhewert eines IR-Kanals, wenn nichts in Reichweite


def parse_sensors(data: bytes) -> Sensors | None:
    """Sensorframe dekodieren. Gibt None bei unerwarteter Länge zurück."""
    if data is None or len(data) < 8:
        return None
    u16 = lambda i: int.from_bytes(data[i : i + 2], "little")
    return Sensors(u16(0), u16(2), u16(4), u16(6), bytes(data))
