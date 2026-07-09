"""Tests für die Batch-Link-Auflösung im Second Brain (domains/second_brain.py).

Verifiziert, dass mehrere Notizen ihre [[Wiki-Links]] mit EINER DB-Query bekommen
(kein N+1) und korrekt der richtigen Notiz zugeordnet werden. db.query gemockt.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains import second_brain as sb


def _row(nid, title="T", cat="inbox"):
    return {
        "id": nid, "title": title, "content": "c", "category": cat,
        "tags": [], "status": "active", "pinned": False,
        "created_at": datetime(2026, 7, 1), "updated_at": datetime(2026, 7, 1),
    }


def test_rows_to_notes_empty_no_query(monkeypatch):
    calls = []
    monkeypatch.setattr(sb._db, "query", lambda *a, **k: calls.append(a) or [])
    assert sb._rows_to_notes([]) == []
    assert calls == []  # bei leerer Liste gar keine Query


def test_rows_to_notes_single_link_query(monkeypatch):
    """Drei Notizen → genau EINE Link-Query (kein N+1)."""
    call_count = [0]

    def fake_query(sql, params=()):
        call_count[0] += 1
        assert "ANY(%s)" in sql  # Batch-Query mit ID-Array
        return [{"from_id": 1, "to_id": 2}, {"from_id": 1, "to_id": 3},
                {"from_id": 2, "to_id": 3}]

    monkeypatch.setattr(sb._db, "query", fake_query)
    notes = sb._rows_to_notes([_row(1), _row(2), _row(3)])
    assert call_count[0] == 1  # nur eine Query für alle drei
    by_id = {n.id: n for n in notes}
    assert sorted(by_id[1].links) == [2, 3]
    assert by_id[2].links == [3]
    assert by_id[3].links == []  # Notiz ohne ausgehende Links


def test_build_note_maps_fields():
    n = sb._build_note(_row(7, title="Titel", cat="project"), [9])
    assert n.id == 7 and n.title == "Titel" and n.category == "project"
    assert n.links == [9]
    assert n.status == "active" and n.pinned is False


def test_build_note_defaults_for_missing_optional_fields():
    row = {"id": 1, "title": "t", "content": "c", "category": "inbox",
           "created_at": datetime(2026, 1, 1), "updated_at": datetime(2026, 1, 1)}
    n = sb._build_note(row, [])
    assert n.tags == [] and n.status == "active" and n.pinned is False


def test_note_to_dict_roundtrip():
    n = sb._build_note(_row(3, title="X"), [4])
    d = sb.note_to_dict(n)
    assert d["id"] == 3 and d["links"] == [4]
    assert d["created_at"] == datetime(2026, 7, 1).isoformat()
