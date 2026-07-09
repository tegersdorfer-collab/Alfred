"""
Goals — API-Router. Aus web/api.py extrahiert (verhaltensgleich).
Endpoints sind Closures über `orch`; build_router(orch) liefert den APIRouter.
"""
import logging
from pathlib import Path

from fastapi import APIRouter, Request

from core.timeparse import parse_date
from domains import goals

from web.routers._helpers import _jsonable

log = logging.getLogger("mantis.api")
WEB_DIR = Path(__file__).parent.parent


def build_router(orch=None) -> APIRouter:
    router = APIRouter()

    @router.get("/api/goals")
    def get_goals(status: str = "active"):
        return _jsonable(goals.list_goals(status))

    @router.post("/api/goals")
    async def create_goal(req: Request):
        d = await req.json()
        dl = parse_date(d["deadline"]) if d.get("deadline") else None
        gid = goals.create_goal(title=d["title"], category=d.get("category", "general"),
                                target_value=d.get("target_value"), unit=d.get("unit"),
                                deadline=dl, notes=d.get("notes"))
        return {"id": gid}

    @router.post("/api/goals/{gid}/progress")
    async def goal_progress(gid: int, req: Request):
        d = await req.json()
        goals.update_progress(gid, current_value=d.get("current_value"),
                              progress_pct=d.get("progress_pct"), status=d.get("status"))
        return {"ok": True}

    @router.delete("/api/goals/{gid}")
    def goal_delete(gid: int):
        goals.delete_goal(gid); return {"ok": True}

    return router
