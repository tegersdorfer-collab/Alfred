"""
Fitness-Domäne: Workouts, Übungen, Sätze, Trainingspläne.
Eigene Fitness-App-Datenschicht (handy-first im Dashboard).
"""
import json
from datetime import date, timedelta

from core import db


# ── Übungen ──────────────────────────────────────────────────────────────────

def ensure_exercise(name: str, category: str = "strength",
                    muscle: str | None = None, unit: str = "reps") -> int:
    row = db.query_one("SELECT id FROM exercises WHERE LOWER(name)=LOWER(%s)", (name,))
    if row:
        return row["id"]
    if not muscle:
        muscle = guess_muscle(name)
    return db.insert_returning(
        "INSERT INTO exercises (name, category, muscle, unit) VALUES (%s,%s,%s,%s) RETURNING id",
        (name, category, muscle, unit),
    )


def list_exercises() -> list[dict]:
    return db.query("SELECT * FROM exercises ORDER BY category, name")


# ── Workouts ─────────────────────────────────────────────────────────────────

def log_workout(title: str, type_: str = "strength", duration_min: int | None = None,
                distance_km: float | None = None, notes: str | None = None,
                rpe: int | None = None, on_date: date | None = None,
                sets: list[dict] | None = None) -> int:
    d = on_date or date.today()
    wid = db.insert_returning(
        """INSERT INTO workouts (date, title, type, duration_min, distance_km, notes, rpe)
           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (d, title, type_, duration_min, distance_km, notes, rpe),
    )
    for i, s in enumerate(sets or [], 1):
        ex_id = ensure_exercise(s["exercise"]) if s.get("exercise") else None
        db.execute(
            """INSERT INTO workout_sets (workout_id, exercise_id, set_index, reps, weight_kg, distance_km, duration_s)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (wid, ex_id, s.get("set_index", i), s.get("reps"), s.get("weight_kg"),
             s.get("distance_km"), s.get("duration_s")),
        )
    return wid


def recent_workouts(limit: int = 20) -> list[dict]:
    workouts = db.query(
        "SELECT * FROM workouts ORDER BY date DESC, id DESC LIMIT %s", (limit,)
    )
    for w in workouts:
        w["sets"] = db.query(
            """SELECT ws.*, e.name AS exercise FROM workout_sets ws
               LEFT JOIN exercises e ON e.id = ws.exercise_id
               WHERE ws.workout_id = %s ORDER BY ws.set_index""",
            (w["id"],),
        )
    return workouts


def weekly_volume() -> dict:
    """Trainings-Volumen der letzten 7 Tage."""
    start = date.today() - timedelta(days=6)
    rows = db.query(
        """SELECT type, COUNT(*) n, COALESCE(SUM(duration_min),0) mins,
                  COALESCE(SUM(distance_km),0) km
           FROM workouts WHERE date >= %s GROUP BY type""",
        (start,),
    )
    total = db.query_one("SELECT COUNT(*) c FROM workouts WHERE date >= %s", (start,))
    return {"by_type": rows, "total": total["c"] if total else 0}


def volume_by_day(days: int = 14) -> list[dict]:
    """Trainingsdauer/Distanz pro Tag (für Chart)."""
    rows = db.query(
        """SELECT date, COUNT(*) n, COALESCE(SUM(duration_min),0) mins,
                  COALESCE(SUM(distance_km),0) km
           FROM workouts WHERE date >= CURRENT_DATE - %s GROUP BY date ORDER BY date""",
        (days,),
    )
    by = {str(r["date"]): r for r in rows}
    out = []
    for i in range(days - 1, -1, -1):
        d = str(date.today() - timedelta(days=i))
        r = by.get(d)
        out.append({"date": d, "mins": int(r["mins"]) if r else 0,
                    "km": float(r["km"]) if r else 0, "n": r["n"] if r else 0})
    return out


# Muskelgruppen-Mapping (für Körper-Visualisierung)
MUSCLE_GROUPS = ["chest", "back", "shoulders", "arms", "legs", "core", "cardio"]

_MUSCLE_KEYWORDS = {
    "chest": ["bench", "bankdrücken", "brust", "push", "dips", "fliegende", "chest"],
    "back": ["rudern", "row", "klimmzug", "pull", "latzug", "kreuzheben", "deadlift", "rücken", "back"],
    "shoulders": ["schulter", "shoulder", "press", "seitheben", "overhead", "ohp", "military"],
    "arms": ["bizeps", "trizeps", "curl", "arm", "biceps", "triceps"],
    "legs": ["squat", "kniebeuge", "bein", "leg", "lunge", "wadenheben", "beinpresse", "leg press"],
    "core": ["bauch", "core", "plank", "crunch", "sit-up", "ab "],
    "cardio": ["lauf", "run", "joggen", "cardio", "rad", "bike", "schwimm", "row erg"],
}


def guess_muscle(exercise_name: str, workout_type: str = "") -> str:
    t = (exercise_name + " " + workout_type).lower()
    for grp, kws in _MUSCLE_KEYWORDS.items():
        if any(k in t for k in kws):
            return grp
    return "other"


def muscle_volume(days: int = 7) -> dict:
    """Volumen je Muskelgruppe der letzten N Tage (Sätze + Workout-Typen)."""
    counts = {g: 0 for g in MUSCLE_GROUPS}
    counts["other"] = 0
    # Aus Sätzen
    sets = db.query(
        """SELECT e.name, e.muscle, w.type FROM workout_sets ws
           JOIN workouts w ON w.id = ws.workout_id
           LEFT JOIN exercises e ON e.id = ws.exercise_id
           WHERE w.date >= CURRENT_DATE - %s""",
        (days,),
    )
    for s in sets:
        grp = s.get("muscle") or guess_muscle(s.get("name") or "", s.get("type") or "")
        counts[grp] = counts.get(grp, 0) + 1
    # Workouts ohne Sätze (z.B. Läufe) nach Typ
    wos = db.query(
        """SELECT type, title FROM workouts w
           WHERE date >= CURRENT_DATE - %s
           AND NOT EXISTS (SELECT 1 FROM workout_sets ws WHERE ws.workout_id=w.id)""",
        (days,),
    )
    for w in wos:
        grp = guess_muscle(w.get("title") or "", w.get("type") or "")
        counts[grp] = counts.get(grp, 0) + 1
    return counts


# ── Trainingspläne ───────────────────────────────────────────────────────────

def save_training_plan(name: str, goal: str, weeks: int, plan: dict) -> int:
    db.execute("UPDATE training_plans SET active = FALSE WHERE active = TRUE")
    return db.insert_returning(
        "INSERT INTO training_plans (name, goal, weeks, plan_json, active) VALUES (%s,%s,%s,%s,TRUE) RETURNING id",
        (name, goal, weeks, json.dumps(plan)),
    )


def active_plan() -> dict | None:
    return db.query_one("SELECT * FROM training_plans WHERE active=TRUE ORDER BY id DESC LIMIT 1")
