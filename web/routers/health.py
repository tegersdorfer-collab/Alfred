"""
Health — API-Router. Aus web/api.py extrahiert (verhaltensgleich).
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

    @router.get("/api/health")
    def health(days: int = 14):
        if not orch:
            return []
        return [_health_dict(h) for h in orch._dashboard.get_recent_health(days=days)]

    @router.post("/api/health/import")
    async def health_import():
        import domains.health as _h
        _h._last_updated = None  # Cache-Bypass: manueller Import soll immer schreiben
        n = await asyncio.to_thread(_h.import_health)
        return {"ok": True, "days": n}

    @router.post("/api/health/push")
    async def health_push(req: Request):
        """Swift-App pusht HealthKit-Daten direkt (keine Pull-Abhängigkeit mehr)."""
        import domains.health as _h
        try:
            data = await req.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "Invalid JSON"}, status_code=400)
        _h._last_updated = None  # Push überschreibt immer (neueste Daten vom Gerät)
        n = await asyncio.to_thread(_h.process_health_data, data)
        return {"ok": True, "written": n == 1}

    @router.post("/api/health/manual")
    async def health_manual(req: Request):
        d = await req.json()
        allowed = {"hrv", "resting_hr", "weight", "sleep_duration", "steps", "body_fat"}
        fields = {k: v for k, v in d.items() if k in allowed and v is not None}
        if not fields:
            return {"ok": False, "error": "Keine gültigen Felder"}
        date_str = d.get("date") or __import__("datetime").date.today().isoformat()
        cols = list(fields.keys())
        updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols)
        sql = (f"INSERT INTO health_data (date, {', '.join(cols)}, updated_at) "
               f"VALUES (%s, {', '.join(['%s']*len(cols))}, NOW()) "
               f"ON CONFLICT (date) DO UPDATE SET {updates}, updated_at=NOW()")
        db.execute(sql, tuple([date_str] + [fields[c] for c in cols]))
        return {"ok": True}

    @router.get("/api/body/measurements")
    def body_measurements(days: int = 90):
        from domains.body import get_recent
        return _jsonable(get_recent(days))

    @router.post("/api/body/measurements")
    async def body_log(req: Request):
        from domains.body import log_measurement
        body = await req.json()
        mid = log_measurement(**{k: v for k, v in body.items() if k != "date"})
        return {"id": mid}

    @router.get("/api/body/progress")
    def body_progress(weeks: int = 8):
        from domains.body import progress_summary
        return {"summary": progress_summary(weeks)}

    return router
