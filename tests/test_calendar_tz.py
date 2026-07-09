"""Tests für die Zeitzonen-/Ganztags-Normalisierung (domains/calendar.py::_to_local).
Rein, kein Netzwerk. Nutzt die konfigurierte Zeitzone des Moduls (_TZ).
"""

import os
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains import calendar as cal
from domains.calendar import _to_local


def test_aware_datetime_converted_to_local_naive():
    # 12:00 UTC → lokale Zeit, tz-naiv, kein Ganztags
    dt = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    local, all_day = _to_local(dt)
    assert all_day is False
    assert local.tzinfo is None
    # Erwartete lokale Zeit über dieselbe tz herleiten (robust gegen DST/Config)
    expected = dt.astimezone(cal._TZ).replace(tzinfo=None)
    assert local == expected


def test_naive_datetime_assumed_utc():
    naive = datetime(2026, 1, 15, 10, 0)  # kein tzinfo → als UTC interpretiert
    local, all_day = _to_local(naive)
    assert all_day is False
    expected = naive.replace(tzinfo=timezone.utc).astimezone(cal._TZ).replace(tzinfo=None)
    assert local == expected


def test_pure_date_is_all_day_midnight():
    d = date(2026, 7, 9)
    local, all_day = _to_local(d)
    assert all_day is True
    assert local == datetime(2026, 7, 9, 0, 0)
    assert local.tzinfo is None


def test_returns_naive_datetime_for_comparison():
    # Wichtig: _fetch_ics vergleicht mit naiven datetime.now() — Ergebnis muss naiv sein
    dt = datetime(2026, 7, 9, 8, 0, tzinfo=timezone.utc)
    local, _ = _to_local(dt)
    # darf nicht mit einem naiven datetime crashen (kein tz-aware/naive-Mix)
    assert (local < datetime(2027, 1, 1)) is True
