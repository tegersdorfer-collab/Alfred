"""Unit-Test: Autopilot._send() emittiert auf den globalen StatusBus, damit
proaktive Nachrichten (Morgen-Briefing, Smart Notifications, ...) auch im
Desktop-HUD als Alert sichtbar werden, nicht nur via Telegram/Push."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from core.autopilot import Autopilot


def _make_autopilot() -> Autopilot:
    return Autopilot(
        llm=MagicMock(),
        lzg=MagicMock(),
        dashboard=MagicMock(),
        reminders=MagicMock(),
        channel=MagicMock(send=AsyncMock()),
        proactive=MagicMock(),
        tracker=MagicMock(),
        identity="Mantis",
    )


class TestSendEmitsStatusBus:
    def test_send_emittiert_autopilot_event(self):
        ap = _make_autopilot()
        with patch("core.autopilot.db.execute"), patch("core.autopilot.log_event"), \
             patch("core.autopilot.BUS") as mock_bus:
            asyncio.run(ap._send("Guten Morgen! Dein Schlaf war heute Nacht sehr gut.", kind="morning_briefing"))
        mock_bus.emit.assert_called_once_with(
            "autopilot", "Guten Morgen! Dein Schlaf war heute Nacht sehr gut.", detail="morning_briefing"
        )

    def test_zu_kurze_nachricht_emittiert_nichts(self):
        ap = _make_autopilot()
        with patch("core.autopilot.BUS") as mock_bus:
            asyncio.run(ap._send("Hi.", kind="proactive"))
        mock_bus.emit.assert_not_called()

    def test_leerer_text_emittiert_nichts(self):
        ap = _make_autopilot()
        with patch("core.autopilot.BUS") as mock_bus:
            asyncio.run(ap._send("", kind="proactive"))
        mock_bus.emit.assert_not_called()
