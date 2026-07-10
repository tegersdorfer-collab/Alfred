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


# ── Positive: Musik (Spotify) ─────────────────────────────────────────────────

def test_music_play():
    assert _m("musik an") == ("spotify", {"action": "play"})
    assert _m("musik weiter") == ("spotify", {"action": "play"})
    assert _m("spiel musik") == ("spotify", {"action": "play"})
    assert _m("mach die musik wieder an") == ("spotify", {"action": "play"})


def test_music_pause():
    assert _m("musik pause") == ("spotify", {"action": "pause"})
    assert _m("stopp die musik") == ("spotify", {"action": "pause"})
    assert _m("mach die musik aus") == ("spotify", {"action": "pause"})


def test_music_next_prev():
    assert _m("nächstes lied") == ("spotify", {"action": "next"})
    assert _m("nächster song") == ("spotify", {"action": "next"})
    assert _m("musik zurück") == ("spotify", {"action": "previous"})


def test_music_single_word_commands():
    assert _m("pause") == ("spotify", {"action": "pause"})
    assert _m("skip") == ("spotify", {"action": "next"})
    assert _m("next") == ("spotify", {"action": "next"})


# ── Negativ: Musik kapert keine Konversation ─────────────────────────────────

def test_pause_in_sentence_not_music():
    assert match("ich mach mal pause") is None
    assert match("lass uns eine pause machen") is None


def test_weiter_in_conversation_not_music():
    assert match("weiter gehts mit dem projekt") is None
    assert match("erzähl weiter") is None


def test_music_question_never_matches():
    assert match("läuft gerade musik?") is None
    assert match("welches lied ist das?") is None


def test_music_statement_not_command():
    assert match("die musik ist aus") is None
    assert match("ich höre gerade musik und mach dann weiter") is None


def test_music_with_query_goes_to_agent():
    # „von" signalisiert eine Such-Anfrage → Agent (braucht Web-API-Suche)
    assert match("mach die musik von queen an") is None
    assert match("spiel bohemian rhapsody von queen") is None
