"""Skilltree — API-Router (Muster wie web/routers/health.py).

Reiner Adapter über domains.skilltree.service. quest_since = Montag der laufenden
Woche (Wochen-Quests). orch=None → leere Achsen (kein Crash, ehrlich leer).
"""
import logging
from datetime import date, timedelta

from fastapi import APIRouter

from domains.skilltree.config import AXES
from domains.skilltree.service import build_skilltree_state

log = logging.getLogger("mantis.api")


def _empty_state() -> dict:
    return {"axes": [{"axis": a["key"], "label": a["label"], "xp": 0.0, "level": 0, "trend": 0.0}
                     for a in AXES], "nodes": [], "quests": []}


def _week_start(today: date) -> str:
    return (today - timedelta(days=today.weekday())).isoformat()


def build_router(orch=None) -> APIRouter:
    router = APIRouter()

    @router.get("/api/skilltree")
    def skilltree():
        """Achsen-Level + freigeschaltete Nodes + adaptive Wochen-Quests."""
        if not orch or not getattr(orch, "_dashboard", None):
            return _empty_state()
        today = date.today()
        return build_skilltree_state(orch._dashboard, today, quest_since=_week_start(today))

    return router
