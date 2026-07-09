"""
Calendar — API-Router. Aus web/api.py extrahiert (verhaltensgleich).
Endpoints sind Closures über `orch`; build_router(orch) liefert den APIRouter.
"""
import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.timeparse import parse_datetime
from domains import calendar as cal_d

from web.routers._helpers import _event_dict

log = logging.getLogger("mantis.api")
WEB_DIR = Path(__file__).parent.parent


def build_router(orch=None) -> APIRouter:
    router = APIRouter()

    @router.get("/api/calendar")
    def calendar(days: int = 14):
        if not orch:
            return []
        return [_event_dict(e) for e in orch._dashboard.get_upcoming_events(days)]

    @router.post("/api/calendar")
    async def create_event(req: Request):
        d = await req.json()

        from datetime import datetime as dt_
        def _parse(s):
            if not s: return None
            # ISO datetime (from <input type="datetime-local">)
            for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
                try: return dt_.strptime(s, fmt)
                except ValueError: pass
            return parse_datetime(s)
        s = _parse(d["start"])
        e = _parse(d["end"]) if d.get("end") else None
        if not s:
            return JSONResponse({"error": "Ungültiges Datum"}, status_code=400)
        orch._dashboard.create_event(title=d["title"], start=s, end=e,
                                     location=d.get("location"), notes=d.get("notes"))
        return {"ok": True}

    @router.put("/api/calendar/{uid}")
    async def update_event(uid: str, req: Request):

        from datetime import datetime as dt_
        d = await req.json()
        def _parse(s):
            if not s: return None
            for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
                try: return dt_.strptime(s, fmt)
                except ValueError: pass
            return None
        cal_d.update_event(uid,
            title=d.get("title"), start=_parse(d.get("start")),
            end=_parse(d.get("end")), location=d.get("location"), notes=d.get("notes"))
        return {"ok": True}

    @router.delete("/api/calendar/{uid}")
    def delete_event(uid: str):

        cal_d.delete_event(uid)
        return {"ok": True}

    return router
