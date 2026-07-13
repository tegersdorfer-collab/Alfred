"""Tests für die Luhmann-Folgezettel-ID-Vergabe (domains/second_brain.next_zettel_id)
— reine Stringlogik, keine DB."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.second_brain import next_zettel_id


def test_first_top_level_is_1():
    assert next_zettel_id([]) == "1"


def test_next_top_level_is_max_plus_1():
    assert next_zettel_id(["1", "2"]) == "3"
    assert next_zettel_id(["1", "3", "2"]) == "4"


def test_first_child_of_number_is_letter():
    # Elternteil endet auf Zahl → Kind ist Buchstabe.
    assert next_zettel_id(["1"], parent="1") == "1a"


def test_next_letter_sibling():
    assert next_zettel_id(["1", "1a"], parent="1") == "1b"
    assert next_zettel_id(["1", "1a", "1b"], parent="1") == "1c"


def test_first_child_of_letter_is_number():
    # Elternteil endet auf Buchstabe → Kind ist Zahl.
    assert next_zettel_id(["1a"], parent="1a") == "1a1"
    assert next_zettel_id(["1a", "1a1"], parent="1a") == "1a2"


def test_letter_overflow_after_z():
    assert next_zettel_id(["1", "1z"], parent="1") == "1aa"


def test_children_of_other_parents_ignored():
    # "2a" darf die Kind-Vergabe von "1" nicht beeinflussen.
    assert next_zettel_id(["1", "1a", "2", "2a", "2b"], parent="1") == "1b"
