"""Test für die keep_alive-Normalisierung des Ollama-Backends.

Ollama parst einen String wie "-1" als Dauer OHNE Einheit → HTTP 400. Reine
Integer-Strings müssen als int übergeben werden. ("0" ist ein Go-Sonderfall und
funktioniert, "-1" nicht — deshalb generell normalisieren.)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.backends.ollama import _normalize_keep_alive


def test_negative_one_string_to_int():
    assert _normalize_keep_alive("-1") == -1
    assert isinstance(_normalize_keep_alive("-1"), int)


def test_zero_string_to_int():
    assert _normalize_keep_alive("0") == 0


def test_positive_int_string():
    assert _normalize_keep_alive("300") == 300


def test_duration_string_kept():
    assert _normalize_keep_alive("5m") == "5m"
    assert _normalize_keep_alive("1h") == "1h"


def test_int_passthrough():
    assert _normalize_keep_alive(-1) == -1
    assert _normalize_keep_alive(0) == 0
