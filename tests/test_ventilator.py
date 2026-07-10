"""Tests für die Ventilator-IR-Steuerung (core/skills/ventilator.py) — ohne Flipper.

Klont das Lampen-Test-Muster: der Serial-tx wird gemockt. Zusätzlich geprüft:
der 'noch nicht angelernt'-Pfad (Platzhalter-Codes in remotes.json).
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.flipper import driver, manager
from core.skills import ventilator


def _patch_tx(calls):
    async def fake_ir_tx(protocol, address, command):
        calls.append((protocol, address, command))
        return ">: "
    driver.ir_tx = fake_ir_tx  # type: ignore[assignment]


_LEARNED = {
    "ventilator": {
        "label": "Ventilator", "learned": True,
        "signals": {
            "an":         {"protocol": "NECext", "address": "1234", "command": "AA01"},
            "aus":        {"protocol": "NECext", "address": "1234", "command": "AB02"},
            "staerker":   {"protocol": "NECext", "address": "1234", "command": "AC03"},
            "schwaecher": {"protocol": "NECext", "address": "1234", "command": "AD04"},
        },
    }
}


def _patch_learned():
    manager.load_remotes = lambda: _LEARNED
    ventilator.load_remotes = lambda: _LEARNED


def test_not_learned_message():
    # echte remotes.json hat Platzhalter (learned:false) → freundliche Meldung, kein Senden
    import importlib
    from tools.flipper import manager as m
    importlib.reload(m)  # echte load_remotes zurück
    ventilator.load_remotes = m.load_remotes
    calls = []
    _patch_tx(calls)
    out = asyncio.run(ventilator._ventilator("an"))
    assert "angelernt" in out.lower() and calls == []


def test_on_off_when_learned():
    _patch_learned()
    calls = []
    _patch_tx(calls)
    asyncio.run(ventilator._ventilator("an"))
    assert calls[-1] == ("NECext", "1234", "AA01")
    asyncio.run(ventilator._ventilator("aus"))
    assert calls[-1] == ("NECext", "1234", "AB02")


def test_aliases():
    _patch_learned()
    calls = []
    _patch_tx(calls)
    asyncio.run(ventilator._ventilator("anmachen"))     # → an
    assert calls[-1] == ("NECext", "1234", "AA01")
    asyncio.run(ventilator._ventilator("schneller"))    # → staerker
    assert calls[-1] == ("NECext", "1234", "AC03")


def test_steps_repeat():
    _patch_learned()
    calls = []
    _patch_tx(calls)
    asyncio.run(ventilator._ventilator("schwaecher", schritte=3))
    assert calls == [("NECext", "1234", "AD04")] * 3


def test_unknown_action():
    _patch_learned()
    _patch_tx([])
    out = asyncio.run(ventilator._ventilator("tanzen"))
    assert "❌" in out
