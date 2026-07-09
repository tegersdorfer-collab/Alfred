"""Tests für ProactiveTracker (proactive.py): Nacht-Modus-Fenster (22:30–06:30),
Tageswechsel-Reset und Sende-Zählung. Reine Logik, kein LLM/DB nötig.
"""

import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proactive import ProactiveTracker


def _dt(h, m=0):
    return datetime(2026, 7, 9, h, m)


# ── Nacht-Modus ───────────────────────────────────────────────────────────────

def test_is_night_blocks_late_evening():
    assert ProactiveTracker._is_night(_dt(23, 0)) is True
    assert ProactiveTracker._is_night(_dt(22, 30)) is True  # Grenze inklusiv


def test_is_night_blocks_early_morning():
    assert ProactiveTracker._is_night(_dt(3, 0)) is True
    assert ProactiveTracker._is_night(_dt(6, 29)) is True


def test_is_night_allows_daytime():
    assert ProactiveTracker._is_night(_dt(6, 30)) is False  # Ende exklusiv → erlaubt
    assert ProactiveTracker._is_night(_dt(12, 0)) is False
    assert ProactiveTracker._is_night(_dt(22, 29)) is False


# ── Tageswechsel-Reset ────────────────────────────────────────────────────────

def test_count_resets_on_new_day():
    t = ProactiveTracker()
    t._count = 5
    t._today = date(2020, 1, 1)  # künstlich alter Tag
    assert t.count_today == 0     # Zugriff triggert Reset


def test_count_persists_same_day():
    t = ProactiveTracker()
    t._today = date.today()
    t._count = 3
    assert t.count_today == 3


# ── record_sent ───────────────────────────────────────────────────────────────

def test_record_sent_increments_and_stamps():
    t = ProactiveTracker()
    t._today = date.today()
    t._count = 0
    before = datetime.now()
    t.record_sent()
    assert t._count == 1
    assert t._last_sent is not None and t._last_sent >= before


# ── Intervall-Gate (can_send) ─────────────────────────────────────────────────

def test_can_send_blocked_when_recent(monkeypatch):
    t = ProactiveTracker()
    t._today = date.today()
    monkeypatch.setattr(t, "_check_stale_ignore", lambda: None)
    monkeypatch.setattr(t, "_interval", lambda: 3600)
    monkeypatch.setattr(t, "_is_night", staticmethod(lambda now: False))
    t._last_sent = datetime.now()  # gerade eben gesendet
    assert t.can_send() is False   # Mindestabstand nicht erreicht
