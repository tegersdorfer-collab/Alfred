"""Tests für die AlphaProgression-Kernlogik und Profil-/Satz-Helfer (domains/fitness.py).

suggest_next_weight ist das Herz der Gewichtsempfehlung — bisher ungetestet. db.query
wird gemockt, damit kein PostgreSQL nötig ist.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains import fitness
from domains.fitness import merge_profile, normalize_set, suggest_next_weight, DEFAULT_PROFILE


# ── merge_profile ─────────────────────────────────────────────────────────────

def test_merge_profile_only_allowed_keys():
    merged = merge_profile(dict(DEFAULT_PROFILE), {"goal": "strength", "hacker": "x"})
    assert merged["goal"] == "strength"
    assert "hacker" not in merged


def test_merge_profile_keeps_untouched():
    merged = merge_profile({**DEFAULT_PROFILE, "notes": "alt"}, {"equipment": "home"})
    assert merged["equipment"] == "home"
    assert merged["notes"] == "alt"


# ── normalize_set ─────────────────────────────────────────────────────────────

def test_normalize_set_clamps_reps():
    assert normalize_set({"exercise": "Curl", "reps": 999})["reps"] == 30
    assert normalize_set({"exercise": "Curl", "reps": -5})["reps"] == 0


def test_normalize_set_requires_exercise():
    assert normalize_set({"reps": 5}) is None
    assert normalize_set({"exercise": "  "}) is None


def test_normalize_set_invalid_weight_becomes_none():
    assert normalize_set({"exercise": "Curl", "weight_kg": "schwer"})["weight_kg"] is None


def test_normalize_set_rpe_range():
    assert normalize_set({"exercise": "Curl", "rpe": 50})["rpe"] == 10


# ── suggest_next_weight (db.query gemockt) ────────────────────────────────────

@pytest.fixture
def mock_rows(monkeypatch):
    def install(rows):
        monkeypatch.setattr(fitness.db, "query", lambda *a, **k: rows)
    return install


def _sets(weight, reps, date="2026-07-01", n=3):
    return [{"weight_kg": weight, "reps": reps, "set_index": i, "date": date}
            for i in range(1, n + 1)]


def test_no_data_returns_none(mock_rows):
    mock_rows([])
    assert suggest_next_weight("Bench Press")["suggestion"] is None


def test_all_sets_full_increases_weight_upper(mock_rows):
    mock_rows(_sets(50.0, 8))  # alle 3 Sätze ≥ reps_target(8)
    r = suggest_next_weight("Bench Press")
    assert r["suggestion_kg"] == 52.5  # Oberkörper → +2.5


def test_all_sets_full_increases_weight_lower(mock_rows):
    mock_rows(_sets(100.0, 8))
    r = suggest_next_weight("Barbell Squat")
    assert r["suggestion_kg"] == 105.0  # Unterkörper → +5


def test_triceps_pushdown_is_upper_not_lower(mock_rows):
    # Regressionstest: "Press Down" (Trizeps) darf NICHT als Unterkörper +5 bekommen
    mock_rows(_sets(30.0, 8))
    r = suggest_next_weight("Triceps Press Down")
    assert r["suggestion_kg"] == 32.5  # +2.5, nicht +5


def test_partial_sets_keeps_weight(mock_rows):
    # 1 von 3 Sätzen voll → ratio 0.33 <0.5? nein, 0.33 → <0.5 Zweig? ratio=0.33<0.5 → -5%
    # Wir wollen den "gleich bleiben"-Zweig: 2/3 voll → ratio 0.66
    rows = [{"weight_kg": 40.0, "reps": 8, "set_index": 1, "date": "2026-07-01"},
            {"weight_kg": 40.0, "reps": 8, "set_index": 2, "date": "2026-07-01"},
            {"weight_kg": 40.0, "reps": 3, "set_index": 3, "date": "2026-07-01"}]
    mock_rows(rows)
    r = suggest_next_weight("Bench Press")
    assert r["suggestion_kg"] == 40.0  # gleich bleiben


def test_mostly_failed_reduces_weight(mock_rows):
    rows = [{"weight_kg": 40.0, "reps": 2, "set_index": i, "date": "2026-07-01"}
            for i in range(1, 4)]
    mock_rows(rows)
    r = suggest_next_weight("Bench Press")
    assert r["suggestion_kg"] < 40.0  # -5%, auf 2.5er gerundet


def test_only_last_session_counts(mock_rows):
    # Jüngste Session (voll) bestimmt Vorschlag, ältere (schwächere) ignoriert
    rows = _sets(50.0, 8, date="2026-07-05") + _sets(45.0, 2, date="2026-06-01")
    mock_rows(rows)
    r = suggest_next_weight("Bench Press")
    assert r["last_weight_kg"] == 50.0
    assert r["suggestion_kg"] == 52.5
