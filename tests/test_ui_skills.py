"""Unit-Tests für core/skills/ui.py: explizite UI-Tools (show_widget/arrange_screen/close_widget)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from core.ui_state import UI_BUS
import core.skills.ui as ui_skills


def _fake_health_row(d, hours, deep):
    return SimpleNamespace(date=d, sleep_duration=hours, sleep_deep=deep)


class FakeDashboard:
    def __init__(self, rows):
        self._rows = rows

    def get_recent_health(self, days=7):
        return self._rows


class TestShowWidget:
    def setup_method(self):
        UI_BUS.clear()

    def teardown_method(self):
        UI_BUS.clear()

    def test_zeigt_bekanntes_widget_im_main_slot(self):
        dash = FakeDashboard([_fake_health_row(date(2026, 7, 4), 7.0, 1.0)])
        with patch("core.container.services.get", return_value=dash):
            result = asyncio.run(ui_skills._show_widget("sleep"))
        assert "sleep" in result
        assert UI_BUS.current["slots"]["main"]["widget"] == "sleep"

    def test_zeigt_widget_in_explizitem_slot(self):
        dash = FakeDashboard([])
        with patch("core.container.services.get", return_value=dash):
            asyncio.run(ui_skills._show_widget("sleep", slot="side"))
        assert "side" in UI_BUS.current["slots"]

    def test_unbekannter_widget_typ_liefert_fehlermeldung_statt_crash(self):
        result = asyncio.run(ui_skills._show_widget("unbekannt"))
        assert result.startswith("FEHLER")
        assert UI_BUS.current["slots"] == {}

    def test_kein_dashboard_liefert_fehlermeldung(self):
        with patch("core.container.services.get", return_value=None):
            result = asyncio.run(ui_skills._show_widget("sleep"))
        assert result.startswith("FEHLER")


class TestArrangeScreen:
    def setup_method(self):
        UI_BUS.clear()

    def teardown_method(self):
        UI_BUS.clear()

    def test_setzt_bekanntes_layout(self):
        result = asyncio.run(ui_skills._arrange_screen("split2"))
        assert "split2" in result
        assert UI_BUS.current["layout"] == "split2"

    def test_unbekanntes_layout_liefert_fehlermeldung_statt_crash(self):
        result = asyncio.run(ui_skills._arrange_screen("nicht-existent"))
        assert result.startswith("FEHLER")


class TestCloseWidget:
    def setup_method(self):
        UI_BUS.clear()

    def teardown_method(self):
        UI_BUS.clear()

    def test_schliesst_slot(self):
        UI_BUS.show_widget("sleep", {}, slot="main")
        result = asyncio.run(ui_skills._close_widget("main"))
        assert "main" in result
        assert "main" not in UI_BUS.current["slots"]

    def test_default_slot_ist_main(self):
        UI_BUS.show_widget("sleep", {}, slot="main")
        asyncio.run(ui_skills._close_widget())
        assert "main" not in UI_BUS.current["slots"]
