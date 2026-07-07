"""Tests für die Autonomie-Entscheidungslogik (tools/robot/autonomy.py) via Fake-Manager."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.robot.autonomy import Autonomy
from tools.robot.protocol import Sensors


class FakeManager:
    def __init__(self, ir0=13, ir1=13):
        self._ir0, self._ir1 = ir0, ir1
        self.calls: list = []

    async def sensors(self):
        return Sensors(self._ir0, self._ir1, 13, 13, b"")

    async def drive(self, action, power, secs):
        self.calls.append(("drive", action, power, secs))

    async def stop(self):
        self.calls.append(("stop",))


def _fast(a: Autonomy) -> Autonomy:
    a.threshold = 60
    a.back_pause = a.turn_pause = 0.0  # keine echten Wartezeiten im Test
    return a


def test_forward_when_clear():
    fm = FakeManager(ir0=13)
    a = _fast(Autonomy(manager=fm))
    assert asyncio.run(a.step()) == "forward"
    assert ("drive", "vor", a.power, a.fwd_secs) in fm.calls


def test_avoid_when_obstacle():
    fm = FakeManager(ir0=200)
    a = _fast(Autonomy(manager=fm))
    assert asyncio.run(a.step()) == "avoid"
    assert ("stop",) in fm.calls
    assert any(c[:2] == ("drive", "zurueck") for c in fm.calls)
    assert any(c[0] == "drive" and c[1] in ("links", "rechts") for c in fm.calls)


def test_front_sensor_is_configurable():
    # Objekt nur vor ir1; mit front=ir1 muss ausgewichen werden
    fm = FakeManager(ir0=13, ir1=200)
    a = _fast(Autonomy(manager=fm))
    a.front = "ir1"
    assert asyncio.run(a.step()) == "avoid"
    # mit front=ir0 (ir0 niedrig) würde er fahren
    fm2 = FakeManager(ir0=13, ir1=200)
    a2 = _fast(Autonomy(manager=fm2))
    a2.front = "ir0"
    assert asyncio.run(a2.step()) == "forward"


def test_turn_direction_alternates():
    fm = FakeManager(ir0=200)
    a = _fast(Autonomy(manager=fm))
    asyncio.run(a.step())
    first = [c[1] for c in fm.calls if c[0] == "drive" and c[1] in ("links", "rechts")][0]
    fm.calls.clear()
    asyncio.run(a.step())
    second = [c[1] for c in fm.calls if c[0] == "drive" and c[1] in ("links", "rechts")][0]
    assert first != second  # abwechselnd, um nicht in Ecken festzuhängen


def test_avoid_backs_up_when_rear_clear():
    fm = FakeManager(ir0=200, ir1=13)  # vorne Hindernis, hinten frei
    a = _fast(Autonomy(manager=fm))
    asyncio.run(a.step())
    assert any(c[:2] == ("drive", "zurueck") for c in fm.calls)


def test_avoid_skips_backup_when_rear_blocked():
    fm = FakeManager(ir0=200, ir1=200)  # vorne UND hinten Hindernis
    a = _fast(Autonomy(manager=fm))
    asyncio.run(a.step())
    assert not any(c[:2] == ("drive", "zurueck") for c in fm.calls)  # nicht rückwärts
    assert any(c[0] == "drive" and c[1] in ("links", "rechts") for c in fm.calls)  # aber drehen


def test_no_data_when_sensors_none():
    class NoSensors(FakeManager):
        async def sensors(self):
            return None

    a = _fast(Autonomy(manager=NoSensors()))
    assert asyncio.run(a.step()) == "no-data"
