"""Unit-Tests für die pure Plan-Logik (ohne DB/LLM)."""
import sys, os
from datetime import date, datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domains.plan_generator import normalize_plan, needs_regen, DEFAULT_PLAN

TODAY = date(2026, 6, 26)


class TestNormalizePlan:
    def test_valid_plan_passes(self):
        raw = {"lower": [{"name": "Squat", "weight": 100, "reps": 5, "sets": 4, "rpe": 8}],
               "upper": [{"name": "Bench", "weight": 80, "reps": 6, "sets": 4}]}
        out = normalize_plan(raw)
        assert out["lower"][0]["name"] == "Squat"
        assert out["upper"][0]["sets"] == 4
        assert out["upper"][0]["reps"] == 6

    def test_missing_upper_returns_none(self):
        assert normalize_plan({"lower": [{"name": "Squat", "reps": 5, "sets": 4}]}) is None

    def test_not_a_dict_returns_none(self):
        assert normalize_plan(None) is None
        assert normalize_plan("nope") is None

    def test_exercise_without_name_dropped(self):
        raw = {"lower": [{"name": "", "reps": 5, "sets": 4}, {"name": "Squat", "reps": 5, "sets": 4}],
               "upper": [{"name": "Bench", "reps": 6, "sets": 4}]}
        out = normalize_plan(raw)
        assert len(out["lower"]) == 1
        assert out["lower"][0]["name"] == "Squat"

    def test_all_exercises_invalid_returns_none(self):
        raw = {"lower": [{"name": "", "reps": 5}], "upper": [{"name": "Bench", "reps": 6, "sets": 4}]}
        assert normalize_plan(raw) is None

    def test_sets_reps_clamped(self):
        raw = {"lower": [{"name": "Squat", "reps": 999, "sets": 99}],
               "upper": [{"name": "Bench", "reps": 6, "sets": 4}]}
        out = normalize_plan(raw)
        assert out["lower"][0]["sets"] == 6     # 1..6
        assert out["lower"][0]["reps"] == 30    # 1..30

    def test_default_plan_is_valid(self):
        assert normalize_plan(DEFAULT_PLAN) is not None


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
