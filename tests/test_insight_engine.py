"""Tests für das Parsing der Insight-LLM-Antwort (domains/insight_engine.py).
Reine Logik, kein LLM/DB.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.insight_engine import _parse_insight_line


def test_full_line_mantis():
    r = _parse_insight_line("Trainingsplan erstellen | HRV-Abfall erkannt | MANTIS")
    assert r == ("Trainingsplan erstellen", "HRV-Abfall erkannt", "mantis")


def test_user_assignee():
    r = _parse_insight_line("Arzttermin machen | Schlaf schlecht | USER")
    assert r[2] == "user"


def test_missing_assignee_defaults_mantis():
    title, notes, assignee = _parse_insight_line("Recherche X | weil Y")
    assert title == "Recherche X" and notes == "weil Y" and assignee == "mantis"


def test_title_only():
    title, notes, assignee = _parse_insight_line("Nur ein Titel")
    assert title == "Nur ein Titel" and notes is None and assignee == "mantis"


def test_empty_returns_none():
    assert _parse_insight_line("") is None
    assert _parse_insight_line("   \n  ") is None


def test_only_separator_returns_none():
    assert _parse_insight_line(" | nur begründung ") is None  # kein Titel


def test_first_line_only():
    r = _parse_insight_line("Titel | Grund | MANTIS\nignorierte zweite Zeile")
    assert r[0] == "Titel"


def test_assignee_case_insensitive_substring():
    # "MANTIS" irgendwo im dritten Teil → mantis
    assert _parse_insight_line("T | G | eher mantis übernimmt")[2] == "mantis"
