"""Tests für das Health-Feld-Mapping (domains/health.py::map_health_fields) —
reine Umrechnungs-/Fallback-Logik, keine DB. Bisher ungetestet.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.health import map_health_fields


def test_empty_input_no_fields():
    assert map_health_fields({}) == {}


def test_none_values_skipped():
    assert map_health_fields({"steps": None, "weight": None}) == {}


def test_steps_rounded_to_int():
    assert map_health_fields({"steps": 8342.7})["steps"] == 8343  # round()


def test_spo2_fraction_normalized_to_percent():
    # 0-1-Skala → *100
    assert map_health_fields({"oxygenSaturation": 0.97})["blood_oxygen"] == 97.0


def test_spo2_percent_kept_as_is():
    # schon 0-100 → unverändert
    assert map_health_fields({"oxygenSaturationPercent": 96})["blood_oxygen"] == 96.0


def test_sleep_minutes_to_hours():
    f = map_health_fields({"sleep": {"totalMinutes": 450, "deepMinutes": 90}})
    assert f["sleep_duration"] == 7.5
    assert f["sleep_deep"] == 1.5


def test_flat_sleep_duration_when_no_nested():
    # Flaches Schema in Stunden, wenn kein sleep-Objekt
    assert map_health_fields({"sleepDuration": 6.8})["sleep_duration"] == 6.8


def test_nested_sleep_wins_over_flat():
    f = map_health_fields({"sleep": {"totalMinutes": 480}, "sleepDuration": 3.0})
    assert f["sleep_duration"] == 8.0  # 480min, nicht der flache Wert


def test_sleep_awake_is_inbed_minus_asleep():
    f = map_health_fields({"sleep": {"inBedMinutes": 500, "totalMinutes": 460}})
    assert f["sleep_awake"] == round((500 - 460) / 60 * 100) / 100  # ~0.67h


def test_weight_key_fallback():
    assert map_health_fields({"weight": 80.123})["weight"] == 80.12  # _R2
    assert map_health_fields({"weightKg": 75.0})["weight"] == 75.0


def test_resting_hr_key_fallbacks():
    assert map_health_fields({"restingHr": 52})["resting_hr"] == 52
    assert map_health_fields({"resting_hr": 48})["resting_hr"] == 48
    assert map_health_fields({"restingHeartRate": 50})["resting_hr"] == 50


def test_hrv_key_fallback():
    assert map_health_fields({"heartRateVariability": 45.6})["hrv"] == 45.6


def test_bad_value_type_skipped():
    # nicht-numerischer Wert → _safe fängt ab → Feld fehlt
    assert "steps" not in map_health_fields({"steps": "viele"})
