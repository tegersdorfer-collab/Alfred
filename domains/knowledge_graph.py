"""Föderierter Wissensgraph — reine Projektion, kein I/O.

Vereint die drei Stores (Notizen, Entitäten, Fakten) zu EINEM Graphen, ohne sie
physisch zu mergen: jede Quelle behält ihre Spezial-Semantik (Vergessen, PARA,
Typisierung), hier entsteht nur die gemeinsame Lese-Sicht. Ein dünner Sammler
(web/routers/knowledge.py bzw. core.skills) zieht die Daten und ruft unified_graph.
"""
from __future__ import annotations

import re

NOTE_COLORS = {
    "context": "#4fc3f7", "inbox": "#aaa", "project": "#ff8a65", "area": "#81c784",
    "resource": "#ce93d8", "daily": "#fff176", "quote": "#f9a825", "archive": "#555",
}
ENTITY_COLOR = "#26c6da"
FACT_COLOR = "#ffb74d"


def _short(s: str, n: int = 30) -> str:
    s = s or ""
    return s[:n] + "…" if len(s) > n else s


def find_mentions(notes: list[dict], entities: list[dict]) -> list[dict]:
    """Auto-Linking: welche Notiz erwähnt welche Entität (Name/Alias, wortgenau,
    case-insensitiv). → [{"note_id", "entity_id"}]. Reine Funktion."""
    patterns = []
    for e in entities:
        names = [e.get("name", "")] + list(e.get("aliases") or [])
        terms = [re.escape(t) for t in names if t]
        if terms:
            patterns.append((e["id"], re.compile(r"\b(" + "|".join(terms) + r")\b", re.IGNORECASE)))
    mentions = []
    for n in notes:
        text = f"{n.get('title', '')} {n.get('content', '')}"
        for eid, pat in patterns:
            if pat.search(text):
                mentions.append({"note_id": n["id"], "entity_id": eid})
    return mentions


def similar_edges(candidates: list[dict], max_dist: float = 0.35) -> list[dict]:
    """Embedding-Nachbarn zu ungerichteten Ähnlichkeits-Kanten verdichten:
    Selbstkanten raus, symmetrische Duplikate zusammenfassen, Distanz-Schwelle."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for c in candidates:
        a, b = c["from_id"], c["to_id"]
        if a == b or c.get("dist", 0.0) > max_dist:
            continue
        key = (a, b) if a < b else (b, a)
        if key in seen:
            continue
        seen.add(key)
        out.append({"from_id": key[0], "to_id": key[1]})
    return out


def unified_graph(
    notes: list[dict],
    entities: list[dict],
    facts: list[dict],
    note_links: list[dict],
    relations: list[dict],
    mentions: list[dict],
    similar: list[dict] | None = None,
    fact_mentions: list[dict] | None = None,
    kinds: set[str] | None = None,
) -> dict:
    """→ {"nodes": [...], "edges": [...]} mit knoten-`kind` (note|entity|fact) und
    kanten-`kind` (link|relation|mention). Knoten-IDs sind namensraum-getaggt
    (note:/entity:/fact:), Kanten mit fehlendem Endknoten werden verworfen.
    `kinds` filtert die Knotenarten (und damit ihre Kanten)."""
    def want(kind: str) -> bool:
        return kinds is None or kind in kinds

    nodes: list[dict] = []
    present: set[str] = set()

    if want("note"):
        for n in notes:
            nid = f"note:{n['id']}"
            nodes.append({"id": nid, "kind": "note", "label": _short(n.get("title", "")),
                          "group": n.get("category", "inbox"),
                          "color": NOTE_COLORS.get(n.get("category"), "#888"),
                          "size": 18 if n.get("pinned") else 12})
            present.add(nid)
    if want("entity"):
        for e in entities:
            nid = f"entity:{e['id']}"
            nodes.append({"id": nid, "kind": "entity", "label": e.get("name", ""),
                          "group": e.get("type", "entity"), "color": ENTITY_COLOR, "size": 14})
            present.add(nid)
    if want("fact"):
        for f in facts:
            nid = f"fact:{f['id']}"
            nodes.append({"id": nid, "kind": "fact", "label": _short(f.get("content", "")),
                          "group": f.get("category", "fact"), "color": FACT_COLOR, "size": 10})
            present.add(nid)

    edges: list[dict] = []

    def add_edge(frm: str, to: str, kind: str, label: str | None = None) -> None:
        if frm in present and to in present:
            edge = {"from": frm, "to": to, "kind": kind}
            if label:
                edge["label"] = label
            edges.append(edge)

    for link in note_links:
        add_edge(f"note:{link['from_id']}", f"note:{link['to_id']}", "link")
    for rel in relations:
        add_edge(f"entity:{rel['subject_id']}", f"entity:{rel['object_id']}", "relation",
                 rel.get("predicate"))
    for men in mentions:
        add_edge(f"note:{men['note_id']}", f"entity:{men['entity_id']}", "mention")
    for sim in similar or []:
        add_edge(f"note:{sim['from_id']}", f"note:{sim['to_id']}", "similar")
    for fm in fact_mentions or []:
        add_edge(f"fact:{fm['fact_id']}", f"entity:{fm['entity_id']}", "mention")

    return {"nodes": nodes, "edges": edges}
