"""Tests für die geteilten API-Serialisierungs-Helfer (web/routers/_helpers.py).

_jsonable wird quer über fast alle Endpoints genutzt (Datetime/Decimal → JSON-safe),
war aber ungetestet. Ebenso die Event-/Health-Dict-Mapper.
"""

import os
import sys
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.routers._helpers import _jsonable, _event_dict, _health_dict


# ── _jsonable ─────────────────────────────────────────────────────────────────

def test_jsonable_primitives_passthrough():
    assert _jsonable(5) == 5
    assert _jsonable("x") == "x"
    assert _jsonable(None) is None
    assert _jsonable(True) is True


def test_jsonable_datetime_and_date():
    assert _jsonable(datetime(2026, 7, 9, 14, 30)) == "2026-07-09T14:30:00"
    assert _jsonable(date(2026, 7, 9)) == "2026-07-09"


def test_jsonable_decimal_to_float():
    r = _jsonable(Decimal("3.14"))
    assert isinstance(r, float) and r == 3.14


def test_jsonable_nested_structure():
    obj = {"a": [1, date(2026, 1, 1)], "b": {"c": Decimal("2.5")}}
    assert _jsonable(obj) == {"a": [1, "2026-01-01"], "b": {"c": 2.5}}


def test_jsonable_list_of_dicts():
    rows = [{"d": datetime(2026, 1, 1)}, {"d": datetime(2026, 1, 2)}]
    assert _jsonable(rows) == [{"d": "2026-01-01T00:00:00"}, {"d": "2026-01-02T00:00:00"}]


# ── _event_dict ───────────────────────────────────────────────────────────────

def test_event_dict_timed():
    e = SimpleNamespace(title="Meeting", start=datetime(2026, 7, 9, 15, 0),
                        all_day=False, calendar="iCloud", location="Büro",
                        uid="u1", source="ics")
    d = _event_dict(e)
    assert d["title"] == "Meeting"
    assert d["start"] == "09.07. 15:00"
    assert d["start_iso"] == "2026-07-09T15:00:00"
    assert d["all_day"] is False


def test_event_dict_all_day_has_no_time():
    e = SimpleNamespace(title="Urlaub", start=datetime(2026, 7, 9, 0, 0),
                        all_day=True, calendar="iCloud", location=None)
    d = _event_dict(e)
    assert d["start"] == "09.07."  # keine Uhrzeit bei Ganztags
    assert d["uid"] is None and d["source"] is None  # getattr-Fallback


# ── _health_dict ──────────────────────────────────────────────────────────────

def test_health_dict_dual_sleep_keys():
    h = SimpleNamespace(date=date(2026, 7, 9), steps=8000, active_calories=500,
                        exercise_minutes=45, sleep_duration=7.5, sleep_deep=1.2,
                        resting_hr=52, hrv=60, weight=80.0)
    d = _health_dict(h)
    # Beide Schlüssel für Kompatibilität (Dashboard 'sleep', iOS 'sleep_duration')
    assert d["sleep"] == 7.5 and d["sleep_duration"] == 7.5
    assert d["date"] == "2026-07-09"
