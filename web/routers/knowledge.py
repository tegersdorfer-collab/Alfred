"""
Knowledge — API-Router. Aus web/api.py extrahiert (verhaltensgleich).
Endpoints sind Closures über `orch`; build_router(orch) liefert den APIRouter.
"""
import logging
from pathlib import Path

from fastapi import APIRouter, Request

from core import db
from domains.knowledge_graph import find_mentions, similar_edges, unified_graph

from web.routers._helpers import _jsonable

log = logging.getLogger("mantis.api")
WEB_DIR = Path(__file__).parent.parent


def build_router(orch=None) -> APIRouter:
    router = APIRouter()

    @router.get("/api/memories")
    def memories():
        rows = db.query("SELECT id, content, category, confidence, created_at FROM memories ORDER BY created_at DESC LIMIT 100")
        return _jsonable(rows)

    @router.post("/api/memories")
    async def add_memory(req: Request):
        d = await req.json()
        if orch:
            emb = await orch.embed_llm.embed(d["content"])
            orch.lzg.save(content=d["content"], embedding=emb,
                          category=d.get("category", "fact"), confidence=d.get("confidence", 0.85))
        return {"ok": True}

    @router.delete("/api/memories/{mid}")
    def del_memory(mid: int):
        db.execute("DELETE FROM memories WHERE id=%s", (mid,)); return {"ok": True}

    @router.get("/api/knowledge")
    def knowledge_graph():
        """Wissens-Graph: alle Entitäten und Relationen."""
        entities = db.query("SELECT id, name, type, description FROM kg_entities ORDER BY type, name")
        relations = db.query("""
            SELECT r.id, s.name AS subject, r.predicate, o.name AS object,
                   r.context, r.confidence
            FROM kg_relations r
            JOIN kg_entities s ON r.subject_id = s.id
            JOIN kg_entities o ON r.object_id   = o.id
            ORDER BY r.confidence DESC, r.created_at DESC
        """)
        return {"entities": _jsonable(entities), "relations": _jsonable(relations)}

    @router.delete("/api/knowledge/entity/{eid}")
    def del_kg_entity(eid: int):
        db.execute("DELETE FROM kg_entities WHERE id=%s", (eid,)); return {"ok": True}

    @router.delete("/api/knowledge/relation/{rid}")
    def del_kg_relation(rid: int):
        db.execute("DELETE FROM kg_relations WHERE id=%s", (rid,)); return {"ok": True}

    @router.get("/api/knowledge/graph")
    def unified_knowledge_graph(kinds: str = "note,entity,fact", limit: int = 400):
        """Vereinter Wissensgraph: Notizen + Entitäten + Fakten in EINEM Bild.
        Notiz→Entität-Kanten (mentions) werden automatisch erkannt. `kinds` filtert."""
        kind_set = {k.strip() for k in kinds.split(",") if k.strip()}
        notes = db.query(
            "SELECT id, title, category, pinned, content FROM brain_notes "
            "WHERE status='active' ORDER BY updated_at DESC LIMIT %s", (limit,))
        entities = db.query("SELECT id, name, type, aliases FROM kg_entities LIMIT %s", (limit,))
        facts = db.query(
            "SELECT id, content, category FROM memories ORDER BY created_at DESC LIMIT %s", (limit,))
        note_ids = {n["id"] for n in notes}
        links = [link for link in db.query("SELECT from_id, to_id FROM brain_links")
                 if link["from_id"] in note_ids and link["to_id"] in note_ids]
        relations = db.query("SELECT subject_id, object_id, predicate FROM kg_relations")
        mentions = find_mentions(notes, entities)
        fact_mentions = [{"fact_id": m["note_id"], "entity_id": m["entity_id"]}
                         for m in find_mentions(facts, entities)]
        # Ähnlichkeits-Kanten: je Notiz die 3 nächsten via Embedding (pgvector).
        # Robust gekapselt — ohne pgvector/Embeddings bleibt der Graph einfach ohne.
        similar: list[dict] = []
        try:
            sim_rows = db.query(
                """
                SELECT a.id AS from_id, b.id AS to_id, (a.embedding <=> b.embedding) AS dist
                FROM brain_notes a
                CROSS JOIN LATERAL (
                    SELECT id, embedding FROM brain_notes
                    WHERE id <> a.id AND embedding IS NOT NULL AND status='active'
                    ORDER BY a.embedding <=> embedding LIMIT 3
                ) b
                WHERE a.embedding IS NOT NULL AND a.status='active'
                """
            )
            similar = similar_edges(
                [{"from_id": r["from_id"], "to_id": r["to_id"], "dist": float(r["dist"])}
                 for r in sim_rows if r["from_id"] in note_ids and r["to_id"] in note_ids])
        except Exception as e:  # noqa: BLE001
            log.info("Ähnlichkeits-Kanten übersprungen: %s", e)
        graph = unified_graph(notes, entities, facts, links, relations, mentions,
                              similar=similar, fact_mentions=fact_mentions, kinds=kind_set or None)
        return _jsonable(graph)

    @router.get("/api/knowledge/heatmap")
    def knowledge_heatmap():
        """Wie oft taucht jede Entität in Beziehungen UND in Chat-Nachrichten auf."""
        entities = db.query("SELECT id, name, type FROM kg_entities WHERE name != 'Timo' ORDER BY name")
        out = []
        for e in entities:
            rel_count = db.query_one(
                "SELECT COUNT(*) c FROM kg_relations WHERE subject_id=%s OR object_id=%s",
                (e["id"], e["id"]),
            )["c"]
            chat_count = db.query_one(
                "SELECT COUNT(*) c FROM chat_messages WHERE content ILIKE %s",
                (f"%{e['name']}%",),
            )["c"]
            out.append({
                "name": e["name"], "type": e["type"],
                "relations": rel_count, "mentions": chat_count,
                "score": rel_count + chat_count,
            })
        out.sort(key=lambda x: x["score"], reverse=True)
        return out

    return router
