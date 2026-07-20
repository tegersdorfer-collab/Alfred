import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.skilltree.signals import collect_from_health, collect_signals


class _H:
    def __init__(self, d, exercise_minutes=None, steps=None):
        self.date = d
        self.exercise_minutes = exercise_minutes
        self.steps = steps


class _FakeDash:
    def __init__(self, rows):
        self._rows = rows
    def get_recent_health(self, days=90):
        return self._rows


def test_health_exercise_becomes_training_signal():
    rows = [_H("2026-07-18", exercise_minutes=45, steps=9000)]
    sigs = collect_from_health(rows)
    kinds = {s["kind"] for s in sigs}
    assert "training" in kinds
    train = next(s for s in sigs if s["kind"] == "training")
    assert train["axis"] == "koerper"
    assert train["ts"] == "2026-07-18"
    assert train["source"] == "health"
    assert train["value"] > 0

def test_health_zero_exercise_no_training_signal():
    rows = [_H("2026-07-18", exercise_minutes=0, steps=0)]
    assert all(s["kind"] != "training" for s in collect_from_health(rows))

def test_collect_signals_pulls_from_dashboard():
    dash = _FakeDash([_H("2026-07-18", exercise_minutes=30, steps=8000)])
    sigs = collect_signals(dash, date(2026, 7, 20))
    assert any(s["kind"] == "training" for s in sigs)
    assert all({"axis", "kind", "value", "ts", "source"} <= set(s) for s in sigs)
