"""Unit-Tests für die pure Plan-Logik (ohne DB/LLM)."""
import sys, os
from datetime import date, datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domains.plan_generator import normalize_plan, needs_regen, DEFAULT_PLAN, pick_variant

TODAY = date(2026, 6, 26)


class TestNormalizePlan:
    def _valid_raw(self):
        return {
            "lowerA": [{"name": "Squat", "weight": 100, "reps": 5, "sets": 4, "rpe": 8}],
            "lowerB": [{"name": "Deadlift", "weight": 120, "reps": 5, "sets": 3}],
            "upperA": [{"name": "Bench", "weight": 80, "reps": 6, "sets": 4}],
            "upperB": [{"name": "Overhead Press", "weight": 50, "reps": 8, "sets": 3}],
        }

    def test_valid_ab_plan_passes(self):
        out = normalize_plan(self._valid_raw())
        assert out["lowerA"][0]["name"] == "Squat"
        assert out["upperB"][0]["name"] == "Overhead Press"
        assert set(out.keys()) == {"lowerA", "lowerB", "upperA", "upperB"}

    def test_missing_upperA_returns_none(self):
        raw = self._valid_raw(); del raw["upperA"]
        assert normalize_plan(raw) is None

    def test_missing_lowerB_falls_back_to_lowerA(self):
        raw = self._valid_raw(); del raw["lowerB"]
        out = normalize_plan(raw)
        assert out["lowerB"] == out["lowerA"]

    def test_not_a_dict_returns_none(self):
        assert normalize_plan(None) is None
        assert normalize_plan("nope") is None

    def test_exercise_without_name_dropped(self):
        raw = self._valid_raw()
        raw["lowerA"] = [{"name": "", "reps": 5, "sets": 4},
                         {"name": "Squat", "reps": 5, "sets": 4}]
        out = normalize_plan(raw)
        assert len(out["lowerA"]) == 1 and out["lowerA"][0]["name"] == "Squat"

    def test_empty_lowerA_returns_none(self):
        raw = self._valid_raw(); raw["lowerA"] = [{"name": "", "reps": 5}]
        assert normalize_plan(raw) is None

    def test_sets_reps_clamped(self):
        raw = self._valid_raw()
        raw["lowerA"] = [{"name": "Squat", "reps": 999, "sets": 99}]
        out = normalize_plan(raw)
        assert out["lowerA"][0]["sets"] == 6 and out["lowerA"][0]["reps"] == 30


class TestPickVariant:
    def test_even_is_a(self):
        assert pick_variant(0) == "A"
        assert pick_variant(2) == "A"

    def test_odd_is_b(self):
        assert pick_variant(1) == "B"
        assert pick_variant(3) == "B"


class TestNeedsRegen:
    def test_no_plan_needs_regen(self):
        assert needs_regen(None, TODAY) is True

    def test_fresh_plan_no_regen(self):
        plan = {"created_at": datetime(2026, 6, 20, 10, 0)}
        assert needs_regen(plan, TODAY) is False

    def test_old_plan_needs_regen(self):
        plan = {"created_at": datetime(2026, 5, 1, 10, 0)}  # > 42 Tage
        assert needs_regen(plan, TODAY) is True

    def test_exactly_42_days_regen(self):
        plan = {"created_at": datetime.combine(TODAY - timedelta(days=42), datetime.min.time())}
        assert needs_regen(plan, TODAY) is True

    def test_missing_created_at_needs_regen(self):
        assert needs_regen({}, TODAY) is True


class TestBuildPrompt:
    def test_prompt_contains_profile_and_schema(self):
        from domains.plan_generator import build_prompt
        p = build_prompt(
            {"goal": "muscle", "equipment": "home", "experience": "advanced", "notes": "Knie schonen"},
            ["Squat", "Bench Press"], {"legs": 12, "chest": 8})
        assert "muscle" in p and "home" in p and "advanced" in p
        assert "Knie schonen" in p
        assert "Squat" in p          # Vermeidungs-Hinweis enthält letzte Übungen
        assert "lower" in p and "upper" in p   # Schema
