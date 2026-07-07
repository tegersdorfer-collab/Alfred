"""Roboter-Tools — Mantis steuert den X5-Droid (Clementoni RoboMaker, BLE 'EVRobot2').

Registriert sich via @T.register beim Import (durch core/skills/__init__.py).
Protokoll/Treiber: tools/robot/ (siehe docs/robot/protocol.md).
Hält eine dauerhafte BLE-Verbindung über tools/robot/manager.MANAGER.
"""

import logging

from core import tools as T
from tools.robot.manager import MANAGER

log = logging.getLogger("core.skills")


@T.register(
    "robot_control",
    "Steuert Timos physischen X5-Roboter (fährt, dreht, greift, macht Geräusche). "
    "Nutze dies wenn Timo den Roboter bewegen lassen will. Fahrbefehle stoppen nach "
    "'sekunden' automatisch. Erste Aktion baut die BLE-Verbindung auf (dauert kurz).",
    {
        "action": {
            "type": "string",
            "enum": ["vor", "zurueck", "links", "rechts", "stopp",
                     "greifer_auf", "greifer_zu", "sound"],
            "description": "vor/zurueck = fahren, links/rechts = auf der Stelle drehen, "
                           "stopp = anhalten, greifer_auf/zu, sound = Geräusch abspielen",
        },
        "power": {"type": "number", "description": "Fahrleistung 0.1–1.0 (Standard 0.5)"},
        "sekunden": {"type": "number", "description": "Fahrdauer in Sekunden, max 2.55 (Standard 1.0)"},
        "sound_id": {"type": "integer", "description": "Sound-ID 1–15 (nur bei action=sound)"},
    },
    ["action"],
    "robot",
)
async def _robot_control(action: str, power: float = 0.5, sekunden: float = 1.0, sound_id: int = 1):
    power = max(0.1, min(1.0, power))
    sekunden = max(0.0, min(2.55, sekunden))
    try:
        if action == "stopp":
            return await MANAGER.stop()
        if action == "greifer_auf":
            return await MANAGER.gripper(open_=True)
        if action == "greifer_zu":
            return await MANAGER.gripper(open_=False)
        if action == "sound":
            return await MANAGER.sound(int(sound_id))
        return await MANAGER.drive(action, power, sekunden)
    except Exception as e:
        log.warning("robot_control fehlgeschlagen: %s", e)
        return f"❌ Roboter nicht erreichbar: {e}. Ist der X5 an und keine andere App verbunden?"


@T.register(
    "robot_sensors",
    "Liest die Sensoren des X5-Roboters aus: zwei Infrarot-Abstandssensoren (ir0/ir1) "
    "und den Greifer-Drucksensor. Höherer Wert = Objekt näher; Ruhewert ~13. Nutze dies "
    "um zu wissen was der Roboter 'sieht' oder ob der Greifer etwas hält.",
    {},
    [],
    "robot",
)
async def _robot_sensors():
    try:
        s = await MANAGER.sensors()
    except Exception as e:
        return f"❌ Roboter nicht erreichbar: {e}"
    if s is None:
        return "Noch keine Sensordaten (Roboter verbindet gerade)."
    naeher = lambda v: " (nah!)" if v > 60 else ""
    return (f"IR vorne/hinten: ir0={s.ir0}{naeher(s.ir0)}, ir1={s.ir1}{naeher(s.ir1)} · "
            f"Greifer-Druck={s.pressure} · (höher=näher, Ruhe≈13)")
