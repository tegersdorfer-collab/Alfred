"""Tests für die reinen Helfer der Memory-Schicht (kein DB/LLM nötig):
- Regex-Fakten-Extraktion + Jaccard-Dedup (memory/extractor.py)
- Temporal-Heuristik "fragt nach Aktuellem?" (memory/lzg.py)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory.extractor import _regex_candidates, _jaccard
from memory.lzg import LZG


# ── Regex-Fakten ──────────────────────────────────────────────────────────────

def test_regex_extracts_name_and_city():
    facts = _regex_candidates("Hallo, ich heiße Timo und ich wohne in Nürnberg.")
    texts = [f["text"] for f in facts]
    assert any("Timo" in t and "Name" in t for t in texts)
    assert any("Nürnberg" in t for t in texts)
    assert all(f["category"] == "identity" for f in facts)


def test_regex_max_two_facts():
    text = ("ich heiße Timo. ich wohne in Berlin. ich arbeite als Entwickler. "
            "ich will abnehmen. ich esse gerne Pasta.")
    assert len(_regex_candidates(text)) <= 2


def test_regex_no_false_positive():
    assert _regex_candidates("Wie ist das Wetter heute?") == []


def test_regex_dedup_same_fact():
    # Zwei identische Name-Nennungen → nur ein Fakt
    facts = _regex_candidates("ich heiße Timo, ja ich heiße Timo")
    names = [f for f in facts if "Name" in f["text"]]
    assert len(names) == 1


# ── Jaccard ───────────────────────────────────────────────────────────────────

def test_jaccard_identical_is_one():
    assert _jaccard("timo wohnt in berlin", "timo wohnt in berlin") == 1.0


def test_jaccard_disjoint_is_zero():
    assert _jaccard("apfel birne", "auto haus") == 0.0


def test_jaccard_empty_is_zero():
    assert _jaccard("", "irgendwas") == 0.0


def test_jaccard_partial_overlap():
    # {timo, wohnt, in, berlin} vs {timo, wohnt, in, muenchen} → 3/5
    assert abs(_jaccard("timo wohnt in berlin", "timo wohnt in muenchen") - 0.6) < 1e-9


# ── Temporal-Heuristik ────────────────────────────────────────────────────────

def test_temporal_recent_true_for_now_words():
    assert LZG._is_temporal_recent("Was mache ich heute?") is True
    assert LZG._is_temporal_recent("wo wohne ich aktuell") is True


def test_temporal_recent_false_for_history_words():
    assert LZG._is_temporal_recent("wo habe ich letzten März gewohnt") is False
    assert LZG._is_temporal_recent("was war früher") is False


def test_temporal_recent_defaults_to_true():
    # Weder klar aktuell noch historisch → bevorzugt Aktuelles
    assert LZG._is_temporal_recent("wo wohnt Timo") is True
