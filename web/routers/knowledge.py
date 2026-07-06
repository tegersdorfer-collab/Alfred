"""
Knowledge — API-Router. Aus web/api.py extrahiert (verhaltensgleich).
Endpoints sind Closures über `orch`; build_router(orch) liefert den APIRouter.
"""
import asyncio
import json
import logging
import os
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse

import config
from core import db, tools as T, backup
from core.status import BUS
from core.skill_factory import delete_skill, create_skill, SKILLS_DIR
from core.timeparse import parse_datetime, parse_date
from core.jsonutil import extract_json
from domains import habits, fitness, nutrition, journal, goals, weather, tasks as tasks_d, calendar as cal_d
from domains import second_brain as _brain
from domains.task_executor import classify, learn_from_rejection, suggest_one
from domains.self_modify import write_file

from web.routers._helpers import _has_body, _jsonable, _health_dict, _event_dict

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
