"""Tests für den Alpha-Progression-Parser (domains/alphaprogression.py):
Link-Extraktion und HTML-Workout-Parsing. Rein, kein Netzwerk.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.alphaprogression import extract_link, parse_page


# ── extract_link ──────────────────────────────────────────────────────────────

def test_extract_link_with_country_code():
    url = extract_link("Schau mal https://alphaprogression.com/de/AbC123 an")
    assert url == "https://alphaprogression.com/de/AbC123"


def test_extract_link_without_country_code():
    assert extract_link("https://alphaprogression.com/XyZ789") == "https://alphaprogression.com/XyZ789"


def test_extract_link_none():
    assert extract_link("kein link hier, nur text") is None


# ── parse_page ────────────────────────────────────────────────────────────────

_SAMPLE_HTML = """
<html><body>
<h1>Push Day</h1>
<div>Bankdrücken · Langhantel</div>
<div>3 Sätze · 10 Wdh</div>
<div>Dips &shy;· Körpergewicht</div>
<div>4 Sätze · 12 Wdh</div>
</body></html>
"""


def test_parse_page_extracts_title_and_exercises():
    data = parse_page(_SAMPLE_HTML)
    assert data is not None
    assert data["title"] == "Push Day"
    assert len(data["exercises"]) == 2
    first = data["exercises"][0]
    assert first["name"] == "Bankdrücken"
    assert first["equipment"] == "Langhantel"
    assert first["sets"] == 3 and first["reps"] == 10


def test_parse_page_second_exercise():
    ex = parse_page(_SAMPLE_HTML)["exercises"][1]
    assert ex["name"] == "Dips"
    assert ex["sets"] == 4 and ex["reps"] == 12


def test_parse_page_no_exercises_returns_none():
    assert parse_page("<html><body><h1>Leer</h1><p>nichts</p></body></html>") is None


def test_parse_page_singular_satz():
    # "1 Satz" (Singular) muss auch matchen
    html = "<h1>T</h1><div>Plank · Matte</div><div>1 Satz · 60 Wdh</div>"
    data = parse_page(html)
    assert data["exercises"][0]["sets"] == 1


def test_parse_page_default_title():
    html = "<div>Kniebeuge · Langhantel</div><div>5 Sätze · 5 Wdh</div>"
    assert parse_page(html)["title"] == "Workout"  # kein <h1> → Fallback
