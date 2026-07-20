import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.skilltree.service import build_skilltree_state


class _H:
    def __init__(self, d, exercise_minutes=None):
        self.date = d
        self.exercise_minutes = exercise_minutes
        self.steps = None


class _FakeDash:
    def __init__(self, rows):
        self._rows = rows
    def get_recent_health(self, days=90):
        return self._rows


def test_state_has_all_axes_even_when_empty():
    state = build_skilltree_state(_FakeDash([]), date(2026, 7, 20), quest_since="2026-07-14")
    axes = {a["axis"] for a in state["axes"]}
    assert axes == {"koerper", "wissen", "schaffen", "geist", "disziplin"}
    assert all(a["level"] == 0 for a in state["axes"])  # keine Daten → ehrlich Level 0

def test_state_reflects_training_in_body_axis():
    rows = [_H(f"2026-07-{d:02d}", exercise_minutes=60) for d in range(10, 20)]
    state = build_skilltree_state(_FakeDash(rows), date(2026, 7, 20), quest_since="2026-07-14")
    body = next(a for a in state["axes"] if a["axis"] == "koerper")
    assert body["xp"] > 0 and body["level"] >= 0

def test_state_includes_quests_with_progress():
    rows = [_H(f"2026-07-{d:02d}", exercise_minutes=60) for d in range(15, 19)]
    state = build_skilltree_state(_FakeDash(rows), date(2026, 7, 20), quest_since="2026-07-14")
    assert isinstance(state["quests"], list)
    for q in state["quests"]:
        assert "progress" in q and "pct" in q["progress"]
