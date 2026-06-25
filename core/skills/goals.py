"""
Goals-Tools — aus core/skills.py extrahiert (verhaltensgleich).
Registriert sich via @T.register beim Import (durch core/skills/__init__.py).
"""
import logging
from datetime import date, datetime

from core import tools as T
from core.timeparse import parse_datetime, parse_date
from core.skill_context import CTX
from domains import habits, fitness, nutrition, journal, goals, weather, tasks as tasks_d

log = logging.getLogger("core.skills")


@T.register("create_goal", "Legt ein neues Ziel an.",
    {"title": {"type": "string"},
     "category": {"type": "string", "description": "fitness | career | finance | personal"},
     "target_value": {"type": "number"}, "unit": {"type": "string"},
     "deadline": {"type": "string", "description": "Datum, optional"}},
    ["title"], "goals")
async def _create_goal(title: str, category: str = "general", target_value: float = None,
                       unit: str = None, deadline: str = None):
    dl = parse_date(deadline) if deadline else None
    goals.create_goal(title=title, category=category, target_value=target_value,
                      unit=unit, deadline=dl)
    return f"Ziel angelegt: {title}"

@T.register("update_goal", "Aktualisiert den Fortschritt eines Ziels (sucht per Titel).",
    {"query": {"type": "string"},
     "progress_pct": {"type": "integer", "description": "Fortschritt 0-100"},
     "current_value": {"type": "number"},
     "status": {"type": "string", "description": "active | done | paused | dropped"}},
    ["query"], "goals")
async def _update_goal(query: str, progress_pct: int = None,
                       current_value: float = None, status: str = None):
    g = goals.find_goal(query)
    if not g:
        return f"Ziel '{query}' nicht gefunden."
    goals.update_progress(g["id"], current_value=current_value,
                          progress_pct=progress_pct, status=status)
    return f"Ziel '{g['title']}' aktualisiert."

@T.register("list_goals", "Listet aktive Ziele mit Fortschritt.", {}, [], "goals")
async def _list_goals():
    gs = goals.list_goals()
    if not gs:
        return "Keine aktiven Ziele."
    return "\n".join(
        f"{g['title']} ({g['category']}): {g['progress_pct']}%"
        + (f" – {g['current_value']}/{g['target_value']} {g['unit'] or ''}" if g['target_value'] else "")
        for g in gs
    )
