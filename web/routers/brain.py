"""
Brain — API-Router. Aus web/api.py extrahiert (verhaltensgleich).
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

    @router.get("/api/brain/notes")
    def brain_notes(category: str = "", limit: int = 200):
        if category and category in _brain.CATEGORIES:
            notes = _brain.get_by_category(category, limit=limit)
        else:
            notes = _brain.get_all(limit=limit)
        return [_brain.note_to_dict(n) for n in notes]

    @router.post("/api/brain/notes")
    async def brain_create(req: Request):
        d = await req.json()
        emb_fn = orch.lzg_embed if orch else None
        # to_thread: add_note blockiert (DB + Embedding) und lzg_embed darf
        # nicht auf dem Event-Loop-Thread laufen (würde den Loop einfrieren).
        note_id = await asyncio.to_thread(
            _brain.add_note,
            title=d.get("title", "Neue Notiz"),
            content=d.get("content", ""),
            category=d.get("category", "inbox"),
            tags=d.get("tags", []),
            pinned=d.get("pinned", False),
            embedding_fn=emb_fn,
        )
        note = _brain.get_note(note_id)
        return _brain.note_to_dict(note)

    @router.get("/api/brain/notes/{note_id}")
    def brain_get(note_id: int):
        note = _brain.get_note(note_id)
        if not note:
            return JSONResponse({"error": "Not found"}, status_code=404)
        return _brain.note_to_dict(note)

    @router.put("/api/brain/notes/{note_id}")
    async def brain_update(note_id: int, req: Request):
        d = await req.json()
        emb_fn = orch.lzg_embed if (orch and "content" in d) else None
        ok = await asyncio.to_thread(
            _brain.update_note,
            note_id,
            title=d.get("title"),
            content=d.get("content"),
            category=d.get("category"),
            tags=d.get("tags"),
            status=d.get("status"),
            pinned=d.get("pinned"),
            embedding_fn=emb_fn,
        )
        if not ok:
            return JSONResponse({"error": "Not found"}, status_code=404)
        return _brain.note_to_dict(_brain.get_note(note_id))

    @router.delete("/api/brain/notes/{note_id}")
    def brain_delete(note_id: int):
        _brain.delete_note(note_id)
        return {"ok": True}

    @router.get("/api/brain/graph")
    def brain_graph():
        return _brain.get_graph_data()

    @router.get("/api/brain/backlinks/{note_id}")
    def brain_backlinks(note_id: int):
        """Alle Notizen die auf note_id verlinken (eingehende Links)."""
        rows = db.query(
            """SELECT n.id, n.title, n.category FROM brain_notes n
               JOIN brain_links l ON l.from_id = n.id
               WHERE l.to_id = %s ORDER BY n.updated_at DESC""",
            (note_id,),
        )
        return [{"id": r["id"], "title": r["title"], "category": r["category"]} for r in rows]

    @router.get("/api/brain/search")
    def brain_search(q: str, limit: int = 20):
        # Sync-Endpoint → läuft im FastAPI-Threadpool, lzg_embed ist hier sicher.
        emb_fn = orch.lzg_embed if orch else None
        results = _brain.search_notes(q, limit=limit, embedding_fn=emb_fn)
        return [_brain.note_to_dict(n) for n in results]

    @router.get("/api/brain/daily")
    def brain_daily():
        note = _brain.ensure_today_daily()
        return _brain.note_to_dict(note)

    @router.post("/api/brain/inbox/sort")
    async def brain_inbox_sort():
        if not orch:
            return JSONResponse({"error": "Orchestrator nicht verfügbar"}, status_code=503)
        changes = await _brain.sort_all_inbox(orch.bg_llm)
        return {"sorted": len(changes), "changes": changes}

    @router.get("/api/brain/categories")
    def brain_categories():
        counts = {}
        for cat in _brain.CATEGORIES:
            row = db.query_one(
                "SELECT COUNT(*) as n FROM brain_notes WHERE category=%s AND status='active'",
                (cat,),
            )
            counts[cat] = row["n"] if row else 0
        return {"categories": _brain.CATEGORY_LABELS, "counts": counts}

    @router.get("/api/brain/quotes")
    def brain_quotes(limit: int = 50):
        return _jsonable(_brain.get_quotes(limit=limit))

    @router.post("/api/brain/quotes")
    async def brain_add_quote(req: Request):
        body = await req.json()
        q = _brain.add_quote(
            text=body.get("text", ""),
            source=body.get("source", ""),
            tags=body.get("tags"),
        )
        return _jsonable(q)

    @router.post("/api/brain/quotes/{note_id}/thought")
    async def brain_add_thought(note_id: int, req: Request):
        body = await req.json()
        ok = _brain.add_thought_to_quote(note_id, body.get("thought", ""))
        return {"ok": ok}

    return router
