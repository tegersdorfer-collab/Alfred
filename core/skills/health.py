"""
Health-Tools — aus core/skills.py extrahiert (verhaltensgleich).
Registriert sich via @T.register beim Import (durch core/skills/__init__.py).
"""
import logging

from core import tools as T
from core.skill_context import CTX

log = logging.getLogger("core.skills")


@T.register("get_health", "Timos Gesundheitsdaten der letzten Tage (Schlaf, Schritte, HRV, Gewicht).",
    {"days": {"type": "integer"}}, [], "health")
async def _get_health(days: int = 3):
    if not CTX.dashboard:
        return "Health nicht verfügbar."
    health = CTX.dashboard.get_recent_health(days=days)
    return "\n".join(h.format() for h in health) if health else "Keine Gesundheitsdaten."


# Feld-Shape wie web.routers._helpers._health_dict (kanonisch) — hier inline
# gehalten, damit der Skill nicht in die Web-Schicht importieren muss.
def _row(h):
    return {"date": str(h.date), "steps": h.steps, "active_calories": h.active_calories,
            "exercise_minutes": h.exercise_minutes, "sleep_duration": h.sleep_duration,
            "sleep_deep": h.sleep_deep, "resting_hr": h.resting_hr, "hrv": h.hrv,
            "weight": h.weight, "blood_oxygen": getattr(h, "blood_oxygen", None)}


@T.register("get_health_scores",
    "Health-Scores (Recovery/Sleep/Activity) als Klartext — für 'wie ist meine "
    "recovery / mein gesundheitszustand heute'.", {}, [], "health")
async def _get_health_scores():
    if not CTX.dashboard:
        return "Health nicht verfügbar."
    from domains.health_scores import compute_body_trend, health_narrative, score_history
    rows = [_row(h) for h in CTX.dashboard.get_recent_health(days=90)]
    hist = score_history(rows)
    if not hist:
        return "Noch keine Gesundheitsdaten."
    return health_narrative(hist[-1], compute_body_trend(rows))
