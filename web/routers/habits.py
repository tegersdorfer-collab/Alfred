"""
Habits — API-Router. Aus web/api.py extrahiert (verhaltensgleich).
Endpoints sind Closures über `orch`; build_router(orch) liefert den APIRouter.
"""
import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core import db
from domains import habits

from web.routers._helpers import _has_body

log = logging.getLogger("mantis.api")
WEB_DIR = Path(__file__).parent.parent


def build_router(orch=None) -> APIRouter:
    router = APIRouter()

    @router.get("/api/habits")
    def get_habits(days: int = 30):
        return habits.habit_overview(days)

    @router.post("/api/habits")
    async def create_habit(req: Request):
        d = await req.json()
        name = (d.get("name") or "").strip()
        if not name:
            return JSONResponse({"error": "Name fehlt"}, 400)
        hid = habits.create_habit(name=name, emoji=d.get("emoji", "✅"),
                                  cadence=d.get("cadence", "daily"),
                                  target_per_week=d.get("target_per_week", 7),
                                  color=d.get("color", "#0ea5e9"),
                                  category=d.get("category", "day"))
        return {"id": hid}

    @router.post("/api/habits/reorder")
    async def reorder_habits(req: Request):
        """Body: [{id: 1, sort_order: 0}, ...]"""
        items = await req.json()
        for item in items:
            db.execute("UPDATE habits SET sort_order = %s WHERE id = %s",
                        (item["sort_order"], item["id"]))
        return {"ok": True}

    @router.patch("/api/habits/{hid}")
    async def update_habit(hid: int, req: Request):
        d = await req.json()
        # Allowlist: only known column names — never interpolate user-controlled keys
        _ALLOWED = {"category": "category = %s", "name": "name = %s", "emoji": "emoji = %s"}
        fields, vals = [], []
        for key, sql_fragment in _ALLOWED.items():
            if key in d:
                fields.append(sql_fragment)
                vals.append(d[key])
        if fields:
            vals.append(hid)
            db.execute("UPDATE habits SET " + ", ".join(fields) + " WHERE id = %s", tuple(vals))
        return {"ok": True}

    @router.post("/api/habits/{hid}/log")
    async def log_habit(hid: int, req: Request):
        d = await req.json() if await _has_body(req) else {}
        habits.log_habit(hid, done=d.get("done", True))
        return {"ok": True, "streak": habits.streak(hid)}

    @router.delete("/api/habits/{hid}")
    def del_habit(hid: int):
        habits.delete_habit(hid); return {"ok": True}

    @router.post("/api/habits/{hid}/unlog")
    def unlog_habit(hid: int):
        habits.unlog_habit(hid); return {"ok": True, "streak": habits.streak(hid)}

    @router.get("/api/habits/commit")
    def habits_commit(days: int = 30):
        return habits.commit_history(days)

    return router
