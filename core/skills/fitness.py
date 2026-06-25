"""
Fitness-Tools — aus core/skills.py extrahiert (verhaltensgleich).
Registriert sich via @T.register beim Import (durch core/skills/__init__.py).
"""
import logging
from datetime import date, datetime

from core import tools as T
from core.timeparse import parse_datetime, parse_date
from core.skill_context import CTX
from domains import habits, fitness, nutrition, journal, goals, weather, tasks as tasks_d

log = logging.getLogger("core.skills")


@T.register("log_workout", "Protokolliert ein absolviertes Training.",
    {"title": {"type": "string"},
     "type": {"type": "string", "description": "strength | run | mobility | other"},
     "duration_min": {"type": "integer"},
     "distance_km": {"type": "number"},
     "notes": {"type": "string"}},
    ["title"], "fitness")
async def _log_workout(title: str, type: str = "strength", duration_min: int = None,
                       distance_km: float = None, notes: str = None):
    fitness.log_workout(title=title, type_=type, duration_min=duration_min,
                        distance_km=distance_km, notes=notes)
    extra = f", {distance_km}km" if distance_km else ""
    return f"Training protokolliert: {title} ({type}{extra})."

@T.register("log_workout_detailed",
    "Protokolliert ein Krafttraining MIT einzelnen Übungen und Sätzen. "
    "Nutze dies wenn Timo Übungen/Sätze/Gewichte nennt oder einen Trainings-Dump liefert.",
    {"title": {"type": "string"},
     "exercises": {"type": "array", "description": "Liste von Übungen mit Sätzen",
        "items": {"type": "object", "properties": {
            "name": {"type": "string"},
            "sets": {"type": "array", "items": {"type": "object", "properties": {
                "reps": {"type": "integer"}, "weight_kg": {"type": "number"}}}}}}}},
    ["title", "exercises"], "fitness")
async def _log_workout_detailed(title: str, exercises: list):
    flat_sets = []
    for ex in exercises or []:
        name = ex.get("name")
        for i, s in enumerate(ex.get("sets", []), 1):
            flat_sets.append({"exercise": name, "set_index": i,
                              "reps": s.get("reps"), "weight_kg": s.get("weight_kg")})
    fitness.log_workout(title=title, type_="strength", sets=flat_sets)
    n_ex = len(exercises or [])
    return f"Training '{title}' mit {n_ex} Übungen und {len(flat_sets)} Sätzen protokolliert."

@T.register("recent_workouts", "Zeigt die letzten Trainings.", {}, [], "fitness")
async def _recent_workouts():
    ws = fitness.recent_workouts(limit=8)
    if not ws:
        return "Noch keine Trainings protokolliert."
    return "\n".join(
        f"{w['date']}: {w['title']} ({w['type']}"
        + (f", {w['distance_km']}km" if w['distance_km'] else "")
        + (f", {w['duration_min']}min" if w['duration_min'] else "") + ")"
        for w in ws
    )

@T.register("suggest_next_weight",
    "Schlägt das optimale Trainingsgewicht für eine Übung vor basierend auf den letzten Sessions (AlphaProgression).",
    {"exercise": {"type": "string", "description": "Name der Übung (z.B. 'Bench Press', 'Squat')"},
     "reps_target": {"type": "integer", "description": "Ziel-Wiederholungen pro Satz (default 8)"}},
    ["exercise"], "fitness")
def _suggest_next_weight(exercise: str, reps_target: int = 8):
    from domains.fitness import suggest_next_weight
    r = suggest_next_weight(exercise, reps_target=reps_target)
    if not r.get("suggestion_kg"):
        return r.get("reason", "Keine Daten.")
    return (f"{exercise}: zuletzt {r['last_weight_kg']}kg ({r['last_date']}) → "
            f"empfohlen **{r['suggestion_kg']}kg**\nGrund: {r['reason']}")

@T.register("progression_report",
    "Zeigt Progressionsbericht für alle Übungen der letzten N Tage.",
    {"days": {"type": "integer", "description": "Zeitraum in Tagen (default 30)"}},
    [], "fitness")
def _progression_report(days: int = 30):
    from domains.fitness import progression_report
    items = progression_report(days)
    if not items:
        return "Keine Progressionsdaten gefunden."
    lines = [f"**{r['exercise']}**: {r.get('last_weight_kg')}kg → {r.get('suggestion_kg')}kg ({r.get('reason','')})"
             for r in items]
    return f"Progressionsbericht ({days} Tage):\n" + "\n".join(lines)

@T.register("log_body_measurement",
    "Speichert Körpermessungen (Umfänge, Gewicht, Körperfett). Alle Werte optional.",
    {
        "weight_kg": {"type": "number", "description": "Gewicht in kg"},
        "waist_cm":  {"type": "number", "description": "Taillenumfang in cm"},
        "chest_cm":  {"type": "number", "description": "Brustumfang in cm"},
        "hips_cm":   {"type": "number", "description": "Hüftumfang in cm"},
        "bicep_cm":  {"type": "number", "description": "Bizepsumfang in cm"},
        "thigh_cm":  {"type": "number", "description": "Oberschenkelumfang in cm"},
        "neck_cm":   {"type": "number", "description": "Halsumfang in cm"},
        "body_fat":  {"type": "number", "description": "Körperfett in %"},
        "notes":     {"type": "string", "description": "Notizen"},
    },
    [], "fitness")
def _log_body_measurement(weight_kg=None, waist_cm=None, chest_cm=None, hips_cm=None,
                           bicep_cm=None, thigh_cm=None, neck_cm=None, body_fat=None, notes=None):
    from domains.body import log_measurement
    mid = log_measurement(weight_kg=weight_kg, waist_cm=waist_cm, chest_cm=chest_cm,
                          hips_cm=hips_cm, bicep_cm=bicep_cm, thigh_cm=thigh_cm,
                          neck_cm=neck_cm, body_fat=body_fat, notes=notes)
    return f"Körpermessung gespeichert (ID {mid})."

@T.register("body_progress",
    "Zeigt Fortschritt der Körpermessungen über die letzten Wochen.",
    {"weeks": {"type": "integer", "description": "Anzahl Wochen (default 8)"}},
    [], "fitness")
def _body_progress(weeks: int = 8):
    from domains.body import progress_summary
    return progress_summary(weeks)
