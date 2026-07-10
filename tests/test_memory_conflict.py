"""Tests für die Memory-Konfliktauflösung (memory/conflict.py) — reine Logik mit
Fake-LZG und Fake-Judge, kein LLM/DB. Deckt das Distanz-Band und supersede ab.
"""

import asyncio
import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory import conflict


@dataclass
class FakeMem:
    id: int
    content: str


class FakeLZG:
    """find_similar gibt vorbereitete (Mem, distance)-Paare zurück; supersede zählt."""

    def __init__(self, candidates):
        self._candidates = candidates
        self.superseded: list[tuple[int, int]] = []

    def find_similar(self, embedding, threshold, top_k):
        # Nur Kandidaten innerhalb der Schwelle (wie das echte find_similar)
        return [(m, d) for (m, d) in self._candidates if d <= threshold]

    def supersede(self, old_id, new_id, factor=0.4):
        self.superseded.append((old_id, new_id))


def _judge_always(v):
    async def _j(old, new):
        return v
    return _j


def test_supersedes_when_judge_says_yes():
    lzg = FakeLZG([(FakeMem(1, "Timo wohnt in München"), 0.20)])
    n = asyncio.run(conflict.resolve(lzg, new_id=99, new_text="Timo wohnt in Berlin",
                                     new_embedding=[0.0], judge=_judge_always(True)))
    assert n == 1
    assert lzg.superseded == [(1, 99)]


def test_no_supersede_when_judge_says_no():
    lzg = FakeLZG([(FakeMem(1, "Timo mag Kaffee"), 0.20)])
    n = asyncio.run(conflict.resolve(lzg, 99, "Timo mag Tee", [0.0], _judge_always(False)))
    assert n == 0 and lzg.superseded == []


def test_near_identical_skipped_as_confirmation():
    # Distanz < CONFLICT_MIN_DIST → Bestätigung, nicht Konflikt (Judge egal)
    lzg = FakeLZG([(FakeMem(1, "Timo wohnt in Berlin"), 0.05)])
    n = asyncio.run(conflict.resolve(lzg, 99, "Timo wohnt in Berlin!", [0.0], _judge_always(True)))
    assert n == 0 and lzg.superseded == []


def test_too_distant_not_returned_by_search():
    # Distanz > CONFLICT_MAX_DIST → gar nicht erst Kandidat
    lzg = FakeLZG([(FakeMem(1, "völlig anderes Thema"), 0.50)])
    n = asyncio.run(conflict.resolve(lzg, 99, "Timo wohnt in Berlin", [0.0], _judge_always(True)))
    assert n == 0


def test_self_is_skipped():
    lzg = FakeLZG([(FakeMem(99, "der neue Fakt selbst"), 0.20)])
    n = asyncio.run(conflict.resolve(lzg, 99, "der neue Fakt selbst", [0.0], _judge_always(True)))
    assert n == 0  # eigene ID nie abwerten


def test_multiple_candidates_mixed():
    lzg = FakeLZG([
        (FakeMem(1, "wohnt in München"), 0.20),   # im Band → wird beurteilt
        (FakeMem(2, "fast identisch"), 0.05),      # zu nah → übersprungen
        (FakeMem(3, "wohnt in Hamburg"), 0.30),    # im Band → wird beurteilt
    ])
    n = asyncio.run(conflict.resolve(lzg, 99, "wohnt in Berlin", [0.0], _judge_always(True)))
    assert n == 2
    assert set(lzg.superseded) == {(1, 99), (3, 99)}


def test_judge_error_is_swallowed():
    async def _bad(old, new):
        raise RuntimeError("judge kaputt")
    lzg = FakeLZG([(FakeMem(1, "wohnt in München"), 0.20)])
    n = asyncio.run(conflict.resolve(lzg, 99, "wohnt in Berlin", [0.0], _bad))
    assert n == 0  # Fehler geschluckt, kein Crash


def test_search_error_returns_zero():
    class BadLZG(FakeLZG):
        def find_similar(self, *a, **k):
            raise RuntimeError("DB weg")
    n = asyncio.run(conflict.resolve(BadLZG([]), 99, "x", [0.0], _judge_always(True)))
    assert n == 0
