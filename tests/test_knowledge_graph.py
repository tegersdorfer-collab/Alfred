"""Tests für die föderierte Wissensgraph-Projektion
(domains/knowledge_graph.unified_graph) — reine Funktion, keine DB."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.knowledge_graph import find_mentions, similar_edges, unified_graph

NOTES = [{"id": 1, "title": "Auto", "category": "inbox", "pinned": False},
         {"id": 2, "title": "Reise", "category": "project", "pinned": True}]
ENTITIES = [{"id": 5, "name": "Timo", "type": "person"},
            {"id": 6, "name": "Berlin", "type": "place"}]
FACTS = [{"id": 9, "content": "Timo mag Kaffee", "category": "preference"}]


def _ids(g):
    return {n["id"] for n in g["nodes"]}


def test_nodes_are_namespaced_by_kind():
    g = unified_graph(NOTES, ENTITIES, FACTS, [], [], [])
    assert _ids(g) == {"note:1", "note:2", "entity:5", "entity:6", "fact:9"}
    kinds = {n["id"]: n["kind"] for n in g["nodes"]}
    assert kinds["note:1"] == "note" and kinds["entity:5"] == "entity" and kinds["fact:9"] == "fact"


def test_note_link_edge():
    g = unified_graph(NOTES, [], [], [{"from_id": 1, "to_id": 2}], [], [])
    assert {"from": "note:1", "to": "note:2", "kind": "link"} in g["edges"]


def test_relation_edge_carries_predicate_label():
    g = unified_graph([], ENTITIES, [], [], [{"subject_id": 5, "object_id": 6, "predicate": "wohnt_in"}], [])
    edge = g["edges"][0]
    assert edge["from"] == "entity:5" and edge["to"] == "entity:6"
    assert edge["kind"] == "relation" and edge["label"] == "wohnt_in"


def test_mention_edge_bridges_note_and_entity():
    g = unified_graph(NOTES, ENTITIES, [], [], [], [{"note_id": 1, "entity_id": 5}])
    assert {"from": "note:1", "to": "entity:5", "kind": "mention"} in g["edges"]


def test_similarity_edge_between_notes():
    g = unified_graph(NOTES, [], [], [], [], [], similar=[{"from_id": 1, "to_id": 2}])
    assert {"from": "note:1", "to": "note:2", "kind": "similar"} in g["edges"]


def test_similar_edges_dedupes_symmetric_and_applies_threshold():
    cands = [
        {"from_id": 1, "to_id": 2, "dist": 0.1},
        {"from_id": 2, "to_id": 1, "dist": 0.1},   # symmetrisches Duplikat
        {"from_id": 1, "to_id": 1, "dist": 0.0},   # Selbstkante
        {"from_id": 1, "to_id": 3, "dist": 0.9},   # über Schwelle
    ]
    assert similar_edges(cands, max_dist=0.35) == [{"from_id": 1, "to_id": 2}]


def test_kind_filter_drops_nodes_and_their_edges():
    # Nur Entitäten → Mention-Kante (braucht note:1) fällt weg.
    g = unified_graph(NOTES, ENTITIES, FACTS, [], [], [{"note_id": 1, "entity_id": 5}], kinds={"entity"})
    assert _ids(g) == {"entity:5", "entity:6"}
    assert g["edges"] == []


def test_dangling_edge_to_missing_node_is_dropped():
    # Erwähnung zeigt auf nicht vorhandene Entität → keine Kante.
    g = unified_graph(NOTES, [], [], [], [], [{"note_id": 1, "entity_id": 999}])
    assert g["edges"] == []


# ── find_mentions: Auto-Linking (Entitäts-Erwähnungen im Notiztext) ───────────

MNOTES = [{"id": 1, "title": "Trip", "content": "War mit Timo in Berlin."},
          {"id": 2, "title": "Leer", "content": "Nichts hier."}]
MENTS = [{"id": 5, "name": "Timo", "aliases": []},
         {"id": 6, "name": "Berlin", "aliases": ["Hauptstadt"]}]


def test_find_mentions_detects_names():
    m = find_mentions(MNOTES, MENTS)
    assert {"note_id": 1, "entity_id": 5} in m
    assert {"note_id": 1, "entity_id": 6} in m
    assert not any(x["note_id"] == 2 for x in m)


def test_find_mentions_is_case_insensitive_and_uses_aliases():
    notes = [{"id": 3, "title": "x", "content": "in der hauptstadt gewesen"}]
    assert {"note_id": 3, "entity_id": 6} in find_mentions(notes, MENTS)


def test_find_mentions_respects_word_boundaries():
    # 'Tim' darf NICHT in 'Timo' matchen.
    notes = [{"id": 4, "title": "x", "content": "Timonium"}]
    assert find_mentions(notes, [{"id": 7, "name": "Tim", "aliases": []}]) == []
