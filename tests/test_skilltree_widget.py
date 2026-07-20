import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ui_state import skilltree_widget_payload


class _H:
    def __init__(self, d, exercise_minutes=None):
        self.date = d
        self.exercise_minutes = exercise_minutes
        self.steps = None


class _Dash:
    def get_recent_health(self, days=90):
        return [_H(f"2026-07-{d:02d}", exercise_minutes=60) for d in range(10, 20)]


def test_widget_payload_shape():
    p = skilltree_widget_payload(_Dash())
    assert p["widget"] == "skilltree"
    assert {a["axis"] for a in p["axes"]} == {"koerper", "wissen", "schaffen", "geist", "disziplin"}
