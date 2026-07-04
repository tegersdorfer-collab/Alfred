"""Unit-Tests für core/ui_state.py::UIStateBus (Multi-Slot-Layout, Publish/Subscribe)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio

from core.ui_state import UIStateBus


class TestUIStateBus:
    def test_initial_current_ist_ruhezustand(self):
        bus = UIStateBus()
        assert bus.current == {"layout": None, "slots": {}, "ts": 0.0}

    def test_show_widget_setzt_default_layout_und_slot(self):
        bus = UIStateBus()
        bus.show_widget("sleep", {"nights": []})
        assert bus.current["layout"] == "single"
        assert bus.current["slots"]["main"] == {"widget": "sleep", "payload": {"nights": []}}
        assert bus.current["ts"] > 0

    def test_show_widget_mit_explizitem_slot(self):
        bus = UIStateBus()
        bus.show_widget("sleep", {"nights": []}, slot="side")
        assert bus.current["slots"] == {"side": {"widget": "sleep", "payload": {"nights": []}}}

    def test_close_widget_entfernt_einzelnen_slot(self):
        bus = UIStateBus()
        bus.show_widget("sleep", {}, slot="main")
        bus.show_widget("sleep", {}, slot="side")
        bus.close_widget("main")
        assert "main" not in bus.current["slots"]
        assert "side" in bus.current["slots"]
        assert bus.current["layout"] == "single"

    def test_close_widget_letzter_slot_geht_zurueck_in_ruhezustand(self):
        bus = UIStateBus()
        bus.show_widget("sleep", {}, slot="main")
        bus.close_widget("main")
        assert bus.current["layout"] is None
        assert bus.current["slots"] == {}

    def test_arrange_screen_wechselt_layout(self):
        bus = UIStateBus()
        bus.arrange_screen("split2")
        assert bus.current["layout"] == "split2"
        assert bus.current["slots"] == {}

    def test_arrange_screen_verwirft_nicht_passende_slots(self):
        bus = UIStateBus()
        bus.show_widget("sleep", {}, slot="main")
        bus.show_widget("sleep", {}, slot="side")
        bus.arrange_screen("single")  # "single" kennt nur "main"
        assert "side" not in bus.current["slots"]
        assert "main" in bus.current["slots"]

    def test_arrange_screen_unbekanntes_layout_wirft(self):
        bus = UIStateBus()
        try:
            bus.arrange_screen("nicht-existent")
            assert False, "sollte ValueError werfen"
        except ValueError:
            pass

    def test_clear_setzt_ruhezustand_zurueck(self):
        bus = UIStateBus()
        bus.show_widget("sleep", {"nights": []})
        bus.clear()
        assert bus.current["layout"] is None
        assert bus.current["slots"] == {}

    def test_subscriber_bekommt_show_widget_event(self):
        async def run():
            bus = UIStateBus()
            q = bus.subscribe()
            bus.show_widget("sleep", {"nights": []})
            evt = q.get_nowait()
            assert evt["slots"]["main"]["widget"] == "sleep"

        asyncio.run(run())

    def test_subscriber_bekommt_clear_event(self):
        async def run():
            bus = UIStateBus()
            q = bus.subscribe()
            bus.clear()
            evt = q.get_nowait()
            assert evt["layout"] is None
            assert evt["slots"] == {}

        asyncio.run(run())

    def test_unsubscribe_entfernt_listener(self):
        bus = UIStateBus()
        q = bus.subscribe()
        bus.unsubscribe(q)
        bus.show_widget("sleep", {"nights": []})
        assert q.empty()

    def test_unsubscribe_unbekannte_queue_wirft_nicht(self):
        bus = UIStateBus()
        bus.unsubscribe(asyncio.Queue())

    def test_volle_queue_verwirft_event_statt_zu_blockieren(self):
        async def run():
            bus = UIStateBus()
            q = bus.subscribe()
            for i in range(60):
                bus.show_widget("sleep", {"night": i})
            assert q.full()

        asyncio.run(run())
