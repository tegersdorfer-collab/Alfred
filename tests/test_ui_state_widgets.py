"""Unit-Tests für die neuen Widget-Payload-Builder in core/ui_state.py (Phase 4)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from core.ui_state import (
    training_widget_payload,
    tasks_widget_payload,
    calendar_widget_payload,
    nutrition_widget_payload,
    habits_widget_payload,
    system_widget_payload,
    brain_widget_payload,
    build_widget_payload,
    WIDGET_TYPES,
    WIDGET_MAP,
)


class TestTrainingWidgetPayload:
    def test_formt_workouts(self):
        rows = [
            {"date": date(2026, 7, 1), "title": "Push Day", "duration_min": 60, "distance_km": None},
            {"date": date(2026, 7, 3), "title": "5km Lauf", "duration_min": 30, "distance_km": 5.0},
        ]
        with patch("domains.fitness.recent_workouts", return_value=rows):
            payload = training_widget_payload(limit=8)
        assert payload == {
            "workouts": [
                {"date": "2026-07-01", "title": "Push Day", "duration_min": 60, "distance_km": None},
                {"date": "2026-07-03", "title": "5km Lauf", "duration_min": 30, "distance_km": 5.0},
            ]
        }

    def test_keine_workouts_liefert_leere_liste(self):
        with patch("domains.fitness.recent_workouts", return_value=[]):
            payload = training_widget_payload()
        assert payload == {"workouts": []}


class TestTasksWidgetPayload:
    def test_formt_offene_aufgaben(self):
        rows = [
            {"title": "Steuererklärung", "priority": "high", "progress_pct": 40},
            {"title": "Wäsche waschen", "priority": "low", "progress_pct": 0},
        ]
        with patch("domains.tasks.list_tasks", return_value=rows):
            payload = tasks_widget_payload(limit=8)
        assert payload == {
            "tasks": [
                {"title": "Steuererklärung", "priority": "high", "progress_pct": 40},
                {"title": "Wäsche waschen", "priority": "low", "progress_pct": 0},
            ]
        }

    def test_begrenzt_auf_limit(self):
        rows = [{"title": f"Task {i}", "priority": "medium", "progress_pct": 0} for i in range(20)]
        with patch("domains.tasks.list_tasks", return_value=rows):
            payload = tasks_widget_payload(limit=3)
        assert len(payload["tasks"]) == 3


def _fake_event(title, start, all_day=False, location=None):
    return SimpleNamespace(title=title, start=start, all_day=all_day, location=location)


class FakeDashboard:
    def __init__(self, events=None, rows=None):
        self._events = events or []
        self._rows = rows or []

    def get_upcoming_events(self, days=7):
        return self._events

    def get_recent_health(self, days=7):
        return self._rows


class TestCalendarWidgetPayload:
    def test_formt_termine(self):
        dash = FakeDashboard(events=[
            _fake_event("Zahnarzt", datetime(2026, 7, 5, 14, 0), location="Praxis Müller"),
        ])
        payload = calendar_widget_payload(dash, days=7)
        assert payload == {
            "events": [
                {"title": "Zahnarzt", "start": "2026-07-05T14:00:00", "all_day": False, "location": "Praxis Müller"},
            ]
        }


class TestNutritionWidgetPayload:
    def test_formt_makro_summen(self):
        with patch("domains.nutrition.day_totals",
                   return_value={"kcal": 1800, "protein": 120, "carbs": 200, "fat": 60, "n": 3}):
            payload = nutrition_widget_payload()
        assert payload == {"kcal": 1800, "protein": 120, "carbs": 200, "fat": 60}


class TestHabitsWidgetPayload:
    def test_formt_gewohnheiten(self):
        rows = [
            {"emoji": "🏋", "name": "Training", "today_done": True, "streak": 5},
            {"emoji": "📖", "name": "Lesen", "today_done": False, "streak": 0},
        ]
        with patch("domains.habits.habit_overview", return_value=rows):
            payload = habits_widget_payload()
        assert payload == {
            "habits": [
                {"emoji": "🏋", "name": "Training", "today_done": True, "streak": 5},
                {"emoji": "📖", "name": "Lesen", "today_done": False, "streak": 0},
            ]
        }


class TestSystemWidgetPayload:
    def test_formt_system_status(self):
        fake_mem = SimpleNamespace(percent=42.5)
        with patch("psutil.cpu_percent", return_value=13.2), \
             patch("psutil.virtual_memory", return_value=fake_mem), \
             patch("core.ui_state._ollama_reachable", return_value=True):
            payload = system_widget_payload()
        assert payload == {"cpu_pct": 13.2, "ram_pct": 42.5, "ollama_ok": True}

    def test_ollama_nicht_erreichbar(self):
        fake_mem = SimpleNamespace(percent=10.0)
        with patch("psutil.cpu_percent", return_value=5.0), \
             patch("psutil.virtual_memory", return_value=fake_mem), \
             patch("core.ui_state._ollama_reachable", return_value=False):
            payload = system_widget_payload()
        assert payload["ollama_ok"] is False


class TestBrainWidgetPayload:
    def test_formt_notizen(self):
        rows = [
            SimpleNamespace(title="Projekt X Deadline", category="project",
                             updated_at=datetime(2026, 7, 4, 10, 0)),
            SimpleNamespace(title="Buch-Idee", category="inbox",
                             updated_at=datetime(2026, 7, 3, 9, 0)),
        ]
        with patch("domains.second_brain.get_all", return_value=rows):
            payload = brain_widget_payload(limit=8)
        assert payload == {
            "notes": [
                {"title": "Projekt X Deadline", "category": "project", "updated_at": "2026-07-04T10:00:00"},
                {"title": "Buch-Idee", "category": "inbox", "updated_at": "2026-07-03T09:00:00"},
            ]
        }

    def test_begrenzt_auf_limit(self):
        rows = [
            SimpleNamespace(title=f"Note {i}", category="inbox", updated_at=datetime(2026, 7, 1))
            for i in range(20)
        ]
        with patch("domains.second_brain.get_all", return_value=rows):
            payload = brain_widget_payload(limit=3)
        assert len(payload["notes"]) == 3


class TestWidgetMapAndTypes:
    def test_widget_map_enthaelt_alle_sechs_typen(self):
        assert WIDGET_MAP == {
            "get_health": "sleep",
            "recent_workouts": "training",
            "list_tasks": "tasks",
            "get_calendar": "calendar",
            "nutrition_today": "nutrition",
            "list_habits": "habits",
        }

    def test_widget_types_enthaelt_alle_acht(self):
        assert WIDGET_TYPES == {
            "sleep", "training", "tasks", "calendar", "nutrition", "habits", "system", "brain",
        }


class TestBuildWidgetPayload:
    def test_unbekannter_typ_liefert_none(self):
        assert build_widget_payload("unbekannt") is None

    def test_standalone_typ_ohne_dashboard(self):
        with patch("domains.nutrition.day_totals",
                   return_value={"kcal": 500, "protein": 10, "carbs": 50, "fat": 10}):
            payload = build_widget_payload("nutrition")
        assert payload == {"kcal": 500, "protein": 10, "carbs": 50, "fat": 10}

    def test_dashboard_typ_ohne_verfuegbares_dashboard_liefert_none(self):
        with patch("core.container.services.get", return_value=None):
            assert build_widget_payload("sleep") is None

    def test_dashboard_typ_mit_dashboard(self):
        dash = FakeDashboard(rows=[])
        with patch("core.container.services.get", return_value=dash):
            payload = build_widget_payload("sleep")
        assert payload == {"widget": "sleep", "nights": []}
