"""
Health-Tools — aus core/skills.py extrahiert (verhaltensgleich).
Registriert sich via @T.register beim Import (durch core/skills/__init__.py).
"""
import logging
from datetime import date, datetime

from core import tools as T
from core.timeparse import parse_datetime, parse_date
from core.skill_context import CTX
from domains import habits, fitness, nutrition, journal, goals, weather, tasks as tasks_d

log = logging.getLogger("core.skills")


@T.register("get_health", "Timos Gesundheitsdaten der letzten Tage (Schlaf, Schritte, HRV, Gewicht).",
    {"days": {"type": "integer"}}, [], "health")
async def _get_health(days: int = 3):
    if not CTX.dashboard:
        return "Health nicht verfügbar."
    health = CTX.dashboard.get_recent_health(days=days)
    return "\n".join(h.format() for h in health) if health else "Keine Gesundheitsdaten."
