"""Tests für die deterministische Fast-Path-Schicht (core/fast_commands.py).

Wichtiger als jeden Befehl zu fangen ist, Konversation NICHT zu kapern — daher
liegt der Fokus auf den Negativfällen.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.fast_commands import match


def _m(text):
    fc = match(text)
    return (fc.tool, fc.args) if fc else None


# ── Positive: Lampe ───────────────────────────────────────────────────────────

def test_lamp_on_short():
    assert _m("lampe an") == ("lampe", {"action": "an"})
    assert _m("licht an") == ("lampe", {"action": "an"})


def test_lamp_off_short():
    assert _m("licht aus") == ("lampe", {"action": "aus"})


def test_lamp_on_with_verb():
    assert _m("mach die lampe an") == ("lampe", {"action": "an"})
    assert _m("schalte das licht an") == ("lampe", {"action": "an"})


def test_lamp_off_with_verb():
    assert _m("schalt die schreibtischlampe aus") == ("lampe", {"action": "aus"})


def test_lamp_colors():
    assert _m("mach die lampe blau") == ("lampe", {"action": "blau"})
    assert _m("lampe grün") == ("lampe", {"action": "gruen"})
    assert _m("stell das licht auf warmweiß") == ("lampe", {"action": "warmweiss"})


def test_lamp_brightness():
    assert _m("mach die lampe heller") == ("lampe", {"action": "heller"})
    assert _m("licht dunkler") == ("lampe", {"action": "dunkler"})


# ── Positive: Roboter-Not-Stopp ───────────────────────────────────────────────

def test_robot_stop():
    assert _m("roboter stopp") == ("robot_control", {"action": "stopp"})
    assert _m("stopp den roboter") == ("robot_control", {"action": "stopp"})


def test_hard_stop_keyword():
    assert _m("notaus") == ("robot_control", {"action": "stopp"})
    assert _m("nothalt") == ("robot_control", {"action": "stopp"})


# ── Negativ: KEINE Fast-Path (Konversation nicht kapern) ──────────────────────

def test_question_never_matches():
    assert match("ist die lampe an?") is None
    assert match("kannst du das licht anmachen?") is None  # Frage → Agent


def test_statement_not_command():
    assert match("die lampe ist aus") is None          # kein Kommando-Verb, kurz aber Aussage
    assert match("ich finde die lampe zu hell hier drüben") is None


def test_bare_stop_not_robot():
    assert match("stopp mal, das stimmt so nicht") is None  # 'stopp' ohne Roboter


def test_unrelated_conversation():
    assert match("erzähl mir was über lampen") is None   # 'lampen' != 'lampe'
    assert match("wie fühlst du dich heute?") is None
    assert match("mach mir bitte einen guten vorschlag fürs abendessen") is None


def test_empty():
    assert match("") is None
