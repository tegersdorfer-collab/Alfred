"""
Insights — API-Router. Aus web/api.py extrahiert (verhaltensgleich).
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

log = logging.getLogger("alfred.api")
WEB_DIR = Path(__file__).parent.parent


def build_router(orch=None) -> APIRouter:
    router = APIRouter()

    @router.get("/api/review")
    def review(period: str = "week"):
        days = 7 if period == "month_compare" else (30 if period == "month" else 7)
        health = db.query(
            "SELECT date, steps, sleep_duration, resting_hr, hrv FROM health_data "
            "WHERE date >= CURRENT_DATE - %s ORDER BY date", (days,)
        )
        prev_health = db.query(
            "SELECT steps, sleep_duration, resting_hr, hrv FROM health_data "
            "WHERE date >= CURRENT_DATE - %s AND date < CURRENT_DATE - %s", (days * 2, days)
        )
        def _avg(rows, key):
            vals = [r[key] for r in rows if r.get(key) is not None]
            return round(sum(vals) / len(vals), 1) if vals else None

        cur_avg = {k: _avg(health, k) for k in ("steps", "sleep_duration", "resting_hr", "hrv")}
        prev_avg = {k: _avg(prev_health, k) for k in ("steps", "sleep_duration", "resting_hr", "hrv")}

        tasks_done = db.query_one(
            "SELECT COUNT(*) c FROM tasks WHERE status='done' AND completed_at >= NOW() - (%s || ' days')::interval",
            (days,),
        )["c"]
        mood_rows = db.query(
            "SELECT mood, energy FROM journal_entries WHERE date >= CURRENT_DATE - %s", (days,)
        )
        avg_mood = _avg(mood_rows, "mood")
        avg_energy = _avg(mood_rows, "energy")

        return {
            "period": period, "days": days,
            "health": {"current": cur_avg, "previous": prev_avg},
            "tasks_done": tasks_done,
            "mood_avg": avg_mood, "energy_avg": avg_energy,
            "journal_entries": len(mood_rows),
        }

    @router.get("/api/mind")
    def mind():
        return {
            "events": _jsonable(db.query("SELECT type, summary, created_at FROM events_log ORDER BY created_at DESC LIMIT 60")),
            "reflections": _jsonable(db.query("SELECT kind, content, created_at FROM reflections ORDER BY created_at DESC LIMIT 20")),
            "notes": db.get_setting("meta_notes", []),
            "agenda": _jsonable(db.query("SELECT kind, title, status, created_at FROM agenda ORDER BY created_at DESC LIMIT 20")),
        }

    @router.get("/api/timeline")
    def timeline(date: str | None = None, limit: int = 200):
        """Alle Events eines Tages, nach Stunde gruppiert. date=ISO-Datum, default=heute."""
        from datetime import date as _date
        day = date or str(_date.today())
        rows = db.query(
            """
            SELECT id, type, summary, detail, created_at
            FROM events_log
            WHERE DATE(created_at AT TIME ZONE 'Europe/Berlin') = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (day, limit),
        )
        hours: dict[str, list] = {}
        for r in _jsonable(rows):
            ts = r.get("created_at", "")
            hour = ts[11:13] if len(ts) >= 13 else "00"
            hours.setdefault(hour, []).append(r)
        return {
            "date": day,
            "hours": [
                {"hour": h, "events": evts}
                for h, evts in sorted(hours.items(), reverse=True)
            ],
            "total": len(rows),
        }

    return router
