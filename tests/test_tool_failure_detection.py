"""Unit-Tests: core.tools.execute() erkennt wiederholt fehlschlagende Tools und
meldet das auf dem StatusBus (Fehler-Selbstheilung Stufe 1 — Erkennung +
Sichtbarkeit im Desktop-HUD, kein automatisches Auto-Fixing)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from unittest.mock import patch

from core import tools as T


async def _boom(**kwargs):
    raise RuntimeError("kaputt")


async def _ok(**kwargs):
    return "alles gut"


def _register_fake(name: str, handler):
    T.REGISTRY[name] = T.Tool(name=name, description="Fake", parameters={},
                               handler=handler, category="test")


class TestRepeatedFailureDetection:
    def setup_method(self):
        self.saved = dict(T.REGISTRY)
        T.REGISTRY.clear()
        T._tool_failure_counts.clear()

    def teardown_method(self):
        T.REGISTRY.clear()
        T.REGISTRY.update(self.saved)
        T._tool_failure_counts.clear()

    def test_emittiert_nicht_bei_einzelnem_fehlschlag(self):
        _register_fake("broken_tool", _boom)
        with patch("core.tools.BUS") as mock_bus:
            asyncio.run(T.execute("broken_tool", {}))
        mock_bus.emit.assert_not_called()

    def test_emittiert_nach_schwellwert_aufeinanderfolgender_fehlschlaege(self):
        _register_fake("broken_tool", _boom)
        with patch("core.tools.BUS") as mock_bus:
            for _ in range(T._FAILURE_THRESHOLD):
                asyncio.run(T.execute("broken_tool", {}))
        mock_bus.emit.assert_called_once()
        args = mock_bus.emit.call_args
        assert args.args[0] == "tool_failure"
        assert "broken_tool" in args.args[1]

    def test_erfolg_setzt_zaehler_zurueck(self):
        _register_fake("flaky_tool", _boom)
        asyncio.run(T.execute("flaky_tool", {}))
        asyncio.run(T.execute("flaky_tool", {}))
        T.REGISTRY["flaky_tool"] = T.Tool(name="flaky_tool", description="Fake", parameters={},
                                          handler=_ok, category="test")
        asyncio.run(T.execute("flaky_tool", {}))  # Erfolg → Zähler zurückgesetzt
        T.REGISTRY["flaky_tool"] = T.Tool(name="flaky_tool", description="Fake", parameters={},
                                          handler=_boom, category="test")
        with patch("core.tools.BUS") as mock_bus:
            asyncio.run(T.execute("flaky_tool", {}))  # nur 1 Fehlschlag seit Reset
        mock_bus.emit.assert_not_called()

    def test_verschiedene_tools_zaehlen_unabhaengig(self):
        _register_fake("tool_a", _boom)
        _register_fake("tool_b", _boom)
        with patch("core.tools.BUS") as mock_bus:
            asyncio.run(T.execute("tool_a", {}))
            asyncio.run(T.execute("tool_b", {}))
        mock_bus.emit.assert_not_called()
