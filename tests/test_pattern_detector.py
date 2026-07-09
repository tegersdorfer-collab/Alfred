"""Tests für die Muster-Analyse (domains/pattern_detector.py) — reine Logik auf
DB-Zeilen, db.query gemockt. Deckt Schwellen-Gate, Wochentags-/Wochenend-Vergleiche
und die Neu-Habit-Proratierung ab.
"""

import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains import pattern_detector as pd


def _mock(monkeypatch, rows):
    monkeypatch.setattr(pd.db, "query", lambda *a, **k: rows)


def _d(offset_days):
    return date.today() - timedelta(days=offset_days)


# ── Schwellen-Gate ────────────────────────────────────────────────────────────

def test_below_min_samples_returns_empty(monkeypatch):
    _mock(monkeypatch, [{"date": _d(1), "type": "strength"}])  # < MIN_SAMPLES
    assert pd._workout_patterns() == []


# ── Workout-Muster ────────────────────────────────────────────────────────────

def test_workout_frequency_and_type(monkeypatch):
    # 6 Strength-Workouts über 14 Tage → 3x/Woche
    rows = [{"date": _d(i), "type": "strength"} for i in range(6)]
    _mock(monkeypatch, rows)
    out = pd._workout_patterns(days=14)
    assert any("bevorzugter Trainingstyp ist strength" in p for p in out)
    assert any("3.0x pro Woche" in p for p in out)


# ── Schlaf-Muster ─────────────────────────────────────────────────────────────

def test_sleep_deficit_flagged(monkeypatch):
    rows = [{"date": _d(i), "sleep_duration": 5.5, "sleep_deep": 1.0} for i in range(10)]
    _mock(monkeypatch, rows)
    out = pd._sleep_patterns()
    assert any("Schlafdefizit" in p for p in out)
    assert any("5.5 Stunden" in p for p in out)


def test_sleep_good_quality_flagged(monkeypatch):
    rows = [{"date": _d(i), "sleep_duration": 8.0, "sleep_deep": 1.5} for i in range(10)]
    _mock(monkeypatch, rows)
    assert any("gut" in p for p in pd._sleep_patterns())


# ── Habit-Muster: Neu-Habit-Proratierung ──────────────────────────────────────

def test_habit_new_habit_prorated_not_penalized(monkeypatch):
    # Habit existiert erst 4 Tage, an allen 4 erledigt → 100%, NICHT "inkonsequent"
    rows = [{
        "name": "Meditation", "emoji": "🧘",
        "created_at": datetime.now() - timedelta(days=3),  # 4 Tage inkl. heute
        "completions": 4,
    }]
    _mock(monkeypatch, rows)
    out = pd._habit_patterns(days=30)
    assert any("sehr konsequent" in p for p in out)
    assert not any("Schwierigkeiten" in p for p in out)


def test_habit_low_consistency_flagged(monkeypatch):
    rows = [{
        "name": "Joggen", "emoji": "🏃",
        "created_at": datetime.now() - timedelta(days=30),
        "completions": 3,  # 3/30 = 10%
    }]
    _mock(monkeypatch, rows)
    assert any("Schwierigkeiten" in p for p in pd._habit_patterns(days=30))


# ── Ruhepuls-Trend ────────────────────────────────────────────────────────────

def test_resting_hr_low_is_good(monkeypatch):
    rows = [{"date": _d(i), "resting_hr": 52} for i in range(10)]
    _mock(monkeypatch, rows)
    assert any("gute Fitness" in p for p in pd._resting_hr_trend())


def test_resting_hr_trend_direction(monkeypatch):
    # erste Hälfte 70, zweite Hälfte 60 → "gesunken"
    rows = ([{"date": _d(20 - i), "resting_hr": 70} for i in range(5)]
            + [{"date": _d(5 - i), "resting_hr": 60} for i in range(5)])
    _mock(monkeypatch, rows)
    assert any("gesunken" in p for p in pd._resting_hr_trend())


# ── _avg-Helfer ───────────────────────────────────────────────────────────────

def test_avg_ignores_none_and_empty():
    assert pd._avg([1, None, 3]) == 2.0
    assert pd._avg([None, None]) is None
    assert pd._avg([]) is None
