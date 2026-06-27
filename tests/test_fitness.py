"""Unit-Tests für Fitness-Domäne (guess_muscle, CSV-Parse-Helfer)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domains.fitness import guess_muscle, _num, _dur_to_min, _time_to_sec


class TestGuessMusle:
    def test_bench_press_is_chest(self):
        assert guess_muscle("Bench Press") == "chest"

    def test_squat_is_legs(self):
        assert guess_muscle("Squat") == "legs"

    def test_lat_pulldown_is_back(self):
        assert guess_muscle("Lat Pulldown") == "back"

    def test_shoulder_press_is_shoulders(self):
        assert guess_muscle("Shoulder Press") == "shoulders"

    def test_bicep_curl_is_arms(self):
        assert guess_muscle("Bicep Curl") == "arms"

    def test_plank_is_core(self):
        assert guess_muscle("Plank") == "core"

    def test_running_is_cardio(self):
        assert guess_muscle("Running") == "cardio"

    def test_unknown_is_other(self):
        assert guess_muscle("Moonwalk Dance") == "other"

    def test_german_kniebeuge_is_legs(self):
        assert guess_muscle("Kniebeuge") == "legs"

    def test_workout_type_contributes(self):
        # "cardio" nur im workout_type-Argument
        assert guess_muscle("Unbekannte Übung", "cardio") == "cardio"

    def test_case_insensitive(self):
        assert guess_muscle("BENCH PRESS") == "chest"

    def test_hyphen_normalized(self):
        assert guess_muscle("Pull-Up") == "back"


class TestNumHelper:
    def test_integer_string(self):
        assert _num("42") == 42.0

    def test_comma_decimal(self):
        assert _num("3,5") == 3.5

    def test_plus_prefix(self):
        assert _num("+10") == 10.0

    def test_empty_returns_none(self):
        assert _num("") is None

    def test_none_returns_none(self):
        assert _num(None) is None

    def test_non_numeric_returns_none(self):
        assert _num("abc") is None


class TestDurToMin:
    def test_plain_minutes(self):
        assert _dur_to_min("45") == 45

    def test_hours_keyword(self):
        assert _dur_to_min("1.5hr") == 90

    def test_seconds(self):
        assert _dur_to_min("120sec") == 2

    def test_hr_colon_format(self):
        assert _dur_to_min("1hr:30") == 90

    def test_empty_returns_none(self):
        assert _dur_to_min("") is None


class TestTimeToSec:
    def test_colon_format(self):
        assert _time_to_sec("1:30", "MINS") == 90

    def test_hours(self):
        assert _time_to_sec("2", "HOURS") == 7200

    def test_secs(self):
        assert _time_to_sec("90", "SECS") == 90

    def test_mins(self):
        assert _time_to_sec("5", "MINS") == 300

    def test_empty_returns_none(self):
        assert _time_to_sec("", "MINS") is None


class TestMergeProfile:
    def test_patch_overrides_only_allowed_keys(self):
        from domains.fitness import merge_profile, DEFAULT_PROFILE
        cur = dict(DEFAULT_PROFILE)
        out = merge_profile(cur, {"goal": "strength", "hacker": "x"})
        assert out["goal"] == "strength"
        assert "hacker" not in out

    def test_unset_keys_keep_current(self):
        from domains.fitness import merge_profile
        cur = {"goal": "muscle", "equipment": "gym", "experience": "advanced", "notes": "knie"}
        out = merge_profile(cur, {"equipment": "home"})
        assert out["equipment"] == "home"
        assert out["goal"] == "muscle"
        assert out["notes"] == "knie"

    def test_empty_patch_returns_current(self):
        from domains.fitness import merge_profile, DEFAULT_PROFILE
        assert merge_profile(dict(DEFAULT_PROFILE), {}) == DEFAULT_PROFILE


class TestNormalizeSet:
    def test_full_set(self):
        from domains.fitness import normalize_set
        s = normalize_set({"exercise": "Squat", "set_index": 2, "reps": 5,
                           "weight_kg": 100, "rpe": 8, "is_warmup": True, "is_failure": False})
        assert s["exercise"] == "Squat" and s["reps"] == 5 and s["weight_kg"] == 100.0
        assert s["rpe"] == 8 and s["is_warmup"] is True and s["is_failure"] is False

    def test_defaults_and_clamps(self):
        from domains.fitness import normalize_set
        s = normalize_set({"exercise": "Bench", "reps": 999, "rpe": 50})
        assert s["reps"] == 30 and s["rpe"] == 10
        assert s["is_warmup"] is False and s["is_failure"] is False
        assert s["weight_kg"] is None

    def test_missing_exercise_returns_none(self):
        from domains.fitness import normalize_set
        assert normalize_set({"reps": 5}) is None
