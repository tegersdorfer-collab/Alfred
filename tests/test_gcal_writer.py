"""Tests für den reinen Event-Body-Aufbau (domains/gcal_writer.py::_build_event_body).
Keine Google-API. Deckt die Ganztags- vs. getaktet-Formatregeln ab.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.gcal_writer import _build_event_body

_TZ = "Europe/Berlin"


def test_timed_event_uses_datetime_and_tz():
    start = datetime(2026, 7, 9, 15, 0)
    end = datetime(2026, 7, 9, 16, 30)
    body = _build_event_body("Meeting", start, end, None, None, False, _TZ)
    assert body["start"] == {"dateTime": "2026-07-09T15:00:00", "timeZone": _TZ}
    assert body["end"] == {"dateTime": "2026-07-09T16:30:00", "timeZone": _TZ}
    assert body["summary"] == "Meeting"


def test_timed_event_default_end_plus_one_hour():
    start = datetime(2026, 7, 9, 15, 0)
    body = _build_event_body("X", start, None, None, None, False, _TZ)
    assert body["end"]["dateTime"] == "2026-07-09T16:00:00"


def test_all_day_uses_date_not_datetime():
    start = datetime(2026, 7, 9, 0, 0)
    body = _build_event_body("Urlaub", start, None, None, None, True, _TZ)
    assert body["start"] == {"date": "2026-07-09"}
    # Ganztags ohne Ende → Ende = Start + 1 Tag (exklusiv)
    assert body["end"] == {"date": "2026-07-10"}
    assert "timeZone" not in body["start"]


def test_all_day_with_explicit_end():
    body = _build_event_body("Reise", datetime(2026, 7, 9), datetime(2026, 7, 12),
                             None, None, True, _TZ)
    assert body["end"] == {"date": "2026-07-12"}


def test_location_and_description_optional():
    body = _build_event_body("T", datetime(2026, 7, 9, 9), None, "Büro", "Notiz", False, _TZ)
    assert body["location"] == "Büro" and body["description"] == "Notiz"


def test_empty_location_omitted():
    body = _build_event_body("T", datetime(2026, 7, 9, 9), None, "", "", False, _TZ)
    assert "location" not in body and "description" not in body
