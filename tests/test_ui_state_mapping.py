"""Unit-Tests für core/ui_state.py: Tool→Widget-Zuordnung + Schlaf-Daten-Shaping."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from core.ui_state import (
    WIDGET_MAP,
    widget_type_for_tool,
    sleep_widget_payload,
    maybe_update_ui,
    UI_BUS,
)


class TestWidgetTypeForTool:
    def test_get_health_mappt_auf_sleep(self):
        assert widget_type_for_tool("get_health") == "sleep"

    def test_unbekanntes_tool_liefert_none(self):
        assert widget_type_for_tool("create_task") is None

    def test_widget_map_enthaelt_nur_get_health(self):
        # Phase 2: bewusst nur EIN Eintrag, Rest folgt in Phase 3
        assert WIDGET_MAP == {"get_health": "sleep"}


def _fake_health_row(d, hours, deep):
    return SimpleNamespace(date=d, sleep_duration=hours, sleep_deep=deep)


class FakeDashboard:
    def __init__(self, rows):
        self._rows = rows

    def get_recent_health(self, days=7):
        return self._rows


class TestSleepWidgetPayload:
    def test_formt_naechte_aus_health_summaries(self):
        dash = FakeDashboard([
            _fake_health_row(date(2026, 7, 2), 7.5, 1.2),
            _fake_health_row(date(2026, 7, 3), 6.8, 0.9),
        ])
        payload = sleep_widget_payload(dash, days=7)
        assert payload == {
            "widget": "sleep",
            "nights": [
                {"date": "2026-07-02", "hours": 7.5, "deep_hours": 1.2},
                {"date": "2026-07-03", "hours": 6.8, "deep_hours": 0.9},
            ],
        }

    def test_fehlende_werte_bleiben_none(self):
        dash = FakeDashboard([_fake_health_row(date(2026, 7, 4), None, None)])
        payload = sleep_widget_payload(dash, days=7)
        assert payload["nights"] == [{"date": "2026-07-04", "hours": None, "deep_hours": None}]

    def test_keine_daten_liefert_leere_liste(self):
        dash = FakeDashboard([])
        payload = sleep_widget_payload(dash, days=7)
        assert payload == {"widget": "sleep", "nights": []}

    def test_days_wird_durchgereicht(self):
        calls = []

        class RecordingDashboard:
            def get_recent_health(self, days=7):
                calls.append(days)
                return []

        sleep_widget_payload(RecordingDashboard(), days=14)
        assert calls == [14]


class TestMaybeUpdateUiZurueckZumRuhezustand:
    def setup_method(self):
        UI_BUS.clear()

    def teardown_method(self):
        UI_BUS.clear()

    def test_leere_tool_liste_geht_zurueck_in_ruhezustand(self):
        UI_BUS.show_widget("sleep", {}, slot="main")
        maybe_update_ui([])
        assert UI_BUS.current["layout"] is None
        assert UI_BUS.current["slots"] == {}

    def test_kein_gemapptes_tool_geht_zurueck_in_ruhezustand(self):
        UI_BUS.show_widget("sleep", {}, slot="main")
        maybe_update_ui(["create_task"])
        assert UI_BUS.current["layout"] is None
        assert UI_BUS.current["slots"] == {}

    def test_get_health_setzt_weiterhin_sleep_widget(self):
        dash = FakeDashboard([_fake_health_row(date(2026, 7, 4), 7.0, 1.0)])
        with patch("core.container.services.get", return_value=dash):
            maybe_update_ui(["get_health"])
        assert UI_BUS.current["layout"] == "single"
        assert UI_BUS.current["slots"]["main"] == {
            "widget": "sleep",
            "payload": {
                "widget": "sleep",
                "nights": [{"date": "2026-07-04", "hours": 7.0, "deep_hours": 1.0}],
            },
        }

    def test_explizites_ui_tool_wird_nicht_von_clear_ueberschrieben(self):
        from core.skills import ui as ui_skills
        import asyncio
        asyncio.run(ui_skills._arrange_screen("split2"))
        maybe_update_ui(["arrange_screen"])
        assert UI_BUS.current["layout"] == "split2"
