"""Unit-Tests für core/ui_state.py::UIStateBus (Publish/Subscribe, kein DB nötig)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio

from core.ui_state import UIStateBus


class TestUIStateBus:
    def test_initial_current_ist_none(self):
        bus = UIStateBus()
        assert bus.current is None

    def test_show_widget_setzt_current(self):
        bus = UIStateBus()
        bus.show_widget("sleep", {"nights": []})
        assert bus.current["widget"] == "sleep"
        assert bus.current["payload"] == {"nights": []}
        assert "ts" in bus.current

    def test_clear_setzt_current_zurueck(self):
        bus = UIStateBus()
        bus.show_widget("sleep", {"nights": []})
        bus.clear()
        assert bus.current is None

    def test_subscriber_bekommt_show_widget_event(self):
        async def run():
            bus = UIStateBus()
            q = bus.subscribe()
            bus.show_widget("sleep", {"nights": []})
            evt = q.get_nowait()
            assert evt["widget"] == "sleep"

        asyncio.run(run())

    def test_subscriber_bekommt_clear_event(self):
        async def run():
            bus = UIStateBus()
            q = bus.subscribe()
            bus.clear()
            evt = q.get_nowait()
            assert evt == {"widget": None}

        asyncio.run(run())

    def test_unsubscribe_entfernt_listener(self):
        bus = UIStateBus()
        q = bus.subscribe()
        bus.unsubscribe(q)
        bus.show_widget("sleep", {"nights": []})
        assert q.empty()

    def test_unsubscribe_unbekannte_queue_wirft_nicht(self):
        bus = UIStateBus()
        bus.unsubscribe(asyncio.Queue())  # nie subscribed — darf nicht crashen

    def test_volle_queue_verwirft_event_statt_zu_blockieren(self):
        async def run():
            bus = UIStateBus()
            q = bus.subscribe()
            for i in range(60):  # maxsize=50 — Queue läuft über
                bus.show_widget("sleep", {"night": i})
            assert q.full()

        asyncio.run(run())
