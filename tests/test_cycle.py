"""Unit-Tests für die pure Zyklus-Logik (ohne DB)."""
import sys, os
from datetime import date, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domains.fitness import next_slot_from_events, cycle_state, CYCLE_LABEL

TODAY = date(2026, 6, 26)
YDAY = TODAY - timedelta(days=1)


class TestNextSlot:
    def test_empty_starts_lower(self):
        assert next_slot_from_events([]) == "lower"

    def test_after_lower_is_jog(self):
        assert next_slot_from_events([{"slot": "lower", "kind": "workout"}]) == "jog"

    def test_after_jog_is_upper(self):
        assert next_slot_from_events([{"slot": "jog", "kind": "jog"}]) == "upper"

    def test_after_upper_wraps_to_lower(self):
        assert next_slot_from_events([{"slot": "upper", "kind": "workout"}]) == "lower"

    def test_rest_is_skipped(self):
        events = [{"slot": "lower", "kind": "rest"},
                  {"slot": "lower", "kind": "workout"}]
        # letzter Nicht-Rest ist lower → next ist jog
        assert next_slot_from_events(events) == "jog"

    def test_only_rest_starts_lower(self):
        assert next_slot_from_events([{"slot": "upper", "kind": "rest"}]) == "lower"


class TestCycleState:
    def test_done_today_when_last_event_today(self):
        events = [{"slot": "lower", "kind": "workout", "date": TODAY}]
        s = cycle_state(events, TODAY)
        assert s["done_today"] is True
        assert s["slot"] == "lower"
        assert s["next_label"] == CYCLE_LABEL["jog"]

    def test_pending_when_last_event_yesterday(self):
        events = [{"slot": "lower", "kind": "workout", "date": YDAY}]
        s = cycle_state(events, TODAY)
        assert s["done_today"] is False
        assert s["slot"] == "jog"

    def test_empty_is_pending_lower(self):
        s = cycle_state([], TODAY)
        assert s == {"slot": "lower", "done_today": False, "next_label": CYCLE_LABEL["jog"]}

    def test_rest_today_keeps_pending(self):
        events = [{"slot": "jog", "kind": "rest", "date": TODAY},
                  {"slot": "lower", "kind": "workout", "date": YDAY}]
        s = cycle_state(events, TODAY)
        # Rest heute zählt nicht als erledigt → jog bleibt pending
        assert s["done_today"] is False
        assert s["slot"] == "jog"
