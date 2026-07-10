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
    # "welches lied ist das?" fragt nach Identifikation, nicht nach dem
    # Wiedergabe-Status → kein Fast-Path. ("läuft gerade musik?" ist dagegen ein
    # echter Status-Query, siehe test_music_status.)
    assert match("welches lied ist das?") is None


def test_music_statement_not_command():
    assert match("die musik ist aus") is None
    assert match("ich höre gerade musik und mach dann weiter") is None


def test_music_play_with_source_goes_to_agent():
    # „mach die musik von queen an" — Steuer-Phrasierung mit Quelle: bleibt beim
    # Agenten (nur „spiel [X]" wird als Suche deterministisch gefangen).
    assert match("mach die musik von queen an") is None


# ── Positive: Status & Spiel (deterministisch statt unzuverlässiges gemma) ────

def test_music_status():
    assert _m("was läuft gerade") == ("spotify", {"action": "status"})
    assert _m("was läuft gerade?") == ("spotify", {"action": "status"})  # Frage → trotzdem Status
    assert _m("was spielt gerade") == ("spotify", {"action": "status"})
    assert _m("läuft gerade musik?") == ("spotify", {"action": "status"})
    assert _m("welches lied läuft") == ("spotify", {"action": "status"})


def test_spiel_query():
    assert _m("spiel kids von mgmt") == ("spotify", {"action": "spiel", "query": "kids von mgmt"})
    assert _m("spiele bohemian rhapsody") == ("spotify", {"action": "spiel", "query": "bohemian rhapsody"})


def test_spiel_playlist_type_hint():
    assert _m("spiel die playlist focus mix") == (
        "spotify", {"action": "spiel", "query": "die playlist focus mix", "typ": "playlist"})


# ── Negativ: Status/Spiel kapern keine Konversation ──────────────────────────

def test_status_not_general_laeuft():
    assert match("wie läuft dein tag?") is None      # 'läuft' ohne was/musik/welches
    assert match("wie läuft es bei dir") is None


def test_spiel_control_words_not_query():
    # reine Steuerkommandos landen im play/pause-Pfad oder beim Agenten, nicht als Suche
    assert _m("spiel musik") == ("spotify", {"action": "play"})   # Musik-Kontext → play
    assert match("spiel weiter") is None                          # reines Steuerwort, kein Query


# ── Positive: UI-Automatik-Entry (gemma wählt computer_task sonst unzuverlässig) ─

def test_computer_task_routing():
    fc = match("bediene die app notizen und erstelle eine neue notiz")
    assert fc is not None
    assert fc.tool == "computer_task"
    assert "notizen" in fc.args["goal"].lower()


def test_computer_task_steuere():
    fc = match("steuere die app safari")
    assert fc and fc.tool == "computer_task"


# ── Negativ: kein Fehlalarm ───────────────────────────────────────────────────

def test_uiauto_needs_app_word():
    assert match("bediene dich am buffet") is None      # kein 'app'
    assert match("steuere die heizung") is None          # kein 'app'


def test_uiauto_question_not_command():
    assert match("welche app soll ich bedienen?") is None


# ── Positive: Ventilator ──────────────────────────────────────────────────────

def test_fan_on_off():
    assert _m("ventilator an") == ("ventilator", {"action": "an"})
    assert _m("ventilator aus") == ("ventilator", {"action": "aus"})
    assert _m("mach den ventilator an") == ("ventilator", {"action": "an"})


def test_fan_speed():
    assert _m("ventilator stärker") == ("ventilator", {"action": "staerker"})
    assert _m("ventilator schwächer") == ("ventilator", {"action": "schwaecher"})
    assert _m("mach den ventilator schneller") == ("ventilator", {"action": "staerker"})


def test_fan_negatives():
    assert match("läuft der ventilator?") is None            # Frage
    assert match("ich hätte gern einen ventilator") is None  # kein Kommando-Verb, zu lang
