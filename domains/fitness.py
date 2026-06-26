"""
Fitness-Domäne: Workouts, Übungen, Sätze, Trainingspläne.
Eigene Fitness-App-Datenschicht (handy-first im Dashboard).
"""
import json
from datetime import date, timedelta

from core import db


CYCLE = ["lower", "jog", "upper"]
CYCLE_LABEL = {"lower": "Lower Body", "jog": "Joggen", "upper": "Upper Body"}


def _event_date(ev: dict):
    """Normalisiert das date-Feld eines Events auf ein date-Objekt."""
    d = ev.get("date")
    if isinstance(d, date):
        return d
    if isinstance(d, str) and d:
        return date.fromisoformat(d[:10])
    return None


def next_slot_from_events(events: list[dict]) -> str:
    """events newest-first, je {slot, kind}. Nächster Slot; Rest übersprungen."""
    for e in events:
        if e.get("kind") == "rest":
            continue
        slot = e.get("slot")
        if slot in CYCLE:
            return CYCLE[(CYCLE.index(slot) + 1) % len(CYCLE)]
        return CYCLE[0]
    return CYCLE[0]


def cycle_state(events: list[dict], today: date) -> dict:
    """Liefert {slot, done_today, next_label}. events newest-first, je {slot, kind, date}."""
    last = next((e for e in events if e.get("kind") != "rest"), None)
    if last and _event_date(last) == today and last.get("slot") in CYCLE:
        slot = last["slot"]
        done_today = True
    else:
        slot = next_slot_from_events(events)
        done_today = False
    after = CYCLE[(CYCLE.index(slot) + 1) % len(CYCLE)]
    return {"slot": slot, "done_today": done_today, "next_label": CYCLE_LABEL[after]}


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
    "cardio": ["running", "lauf", "joggen", "cycling", "stationary bike", "treadmill",
               "rad", "bike", "schwimm", "cardio", "rowing erg", "elliptical"],
    "legs": ["squat", "kniebeuge", "leg press", "leg extension", "leg curl", "lying leg",
             "split squat", "hack squat", "lunge", "calf", "wadenheben", " bein",
             "beinpresse", "hip adduction", "hip abduction", "romanian", "rdl"],
    "back": ["row", "rudern", "pulldown", "lat ", "pull-up", "pull up", "pullup", "klimmzug",
             "latzug", "deadlift", "kreuzheben", "shrug", "face pull", "single arm lat",
             "t-bar", "bent-over", "high row", " rücken", "rückenstrecker",
             "reverse butterfly", "reverse fly", "reverse flys", "butterfly reverse",
             "hyperextension", "back extension"],
    "chest": ["bench press", "bankdrück", "bank drück", "flachbankdrück", "flach bank drück",
              "chest press", "chest fly", "chest", "brust", "butterfly", "fly", "flys",
              "dips", "pec", "incline press", "push-up", "pushup"],
    "shoulders": ["shoulder press", "overhead press", "military", "ohp", "lateral raise",
                  "seitheben", "lateral raises", "shoulder", "schulter", "delt",
                  "front raise", "arnold press"],
    "arms": ["curl", "bizeps", "biceps", "triceps", "trizeps", "pushdown",
             "skull crusher", "preacher", "wrist curl", "unterarme", "forearm", "farmers"],
    "core": ["crunch", "plank", "sit up", "situp", "sit-up", "ab ", "abs", "bauch",
             "leg raise", "hanging leg", "knee raise", "core", "russian twist", "twister"],
}


def guess_muscle(exercise_name: str, workout_type: str = "") -> str:
    # Soft-Hyphen + HTML-Entities entfernen, dann Bindestriche zu Leerzeichen normalisieren
    cleaned = (exercise_name + " " + workout_type)
    cleaned = cleaned.replace("­", "").replace("&shy;", "").replace("-", " ")
    t = " " + cleaned.lower() + " "
    for grp, kws in _MUSCLE_KEYWORDS.items():
        if any(k in t for k in kws):
            return grp
    return "other"


# ── CSV-Import (Gym-App-Export, strukturiert – kein LLM nötig) ────────────────

import re as _re
from datetime import datetime as _dt

_WHDR = _re.compile(r'^"(.+?)";"(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})\s*h";"(.+?)"\s*$')
_EHDR = _re.compile(r'^"(\d+)\.\s*(.+?)"\s*$')


def _num(s: str):
    s = (s or "").strip().replace(",", ".").lstrip("+")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _dur_to_min(s: str):
    s = (s or "").strip().lower()
    try:
        if ":" in s and "hr" in s:
            h, m = s.replace("hr", "").strip().split(":")
            return int(h) * 60 + int(m)
        n = float(_re.findall(r"[\d.]+", s)[0])
        if "hr" in s:   return round(n * 60)
        if "sec" in s:  return max(0, round(n / 60))
        return round(n)   # min
    except Exception:
        return None


def _time_to_sec(v: str, unit: str):
    v = (v or "").strip()
    if ":" in v:
        p = v.split(":")
        try:
            return int(p[0]) * 60 + int(p[1])
        except Exception:
            return None
    n = _num(v)
    if n is None:
        return None
    if unit == "HOURS": return int(n * 3600)
    if unit == "SECS":  return int(n)
    return int(n * 60)  # MINS


def import_workout_csv(text: str) -> dict:
    """Parst einen strukturierten Gym-App-Export (mehrere Workouts) deterministisch."""
    lines = text.replace("\r\n", "\n").split("\n")
    workouts_added = sets_added = skipped = 0
    cur_w = None          # {date,title,duration,exercises:[{name,sets:[...]}], cardio:bool}
    cur_ex = None
    cur_cols = None       # ("KG","REPS") etc.

    def flush():
        nonlocal workouts_added, sets_added, skipped, cur_w
        if not cur_w:
            return
        d = cur_w["date"]; title = cur_w["title"]
        exists = db.query_one("SELECT id FROM workouts WHERE date=%s AND title=%s", (d, title))
        if exists:
            skipped += 1; cur_w = None; return
        # Typ + Gesamtdistanz
        is_cardio = all(guess_muscle(e["name"]) == "cardio" for e in cur_w["exercises"]) and cur_w["exercises"]
        total_km = sum((s.get("distance_km") or 0) for e in cur_w["exercises"] for s in e["sets"]) or None
        flat = []
        for e in cur_w["exercises"]:
            for i, s in enumerate(e["sets"], 1):
                flat.append({"exercise": e["name"], "set_index": i, **s})
        log_workout(title=title, type_="cardio" if is_cardio else "strength",
                    duration_min=cur_w["duration"], distance_km=total_km,
                    on_date=d, sets=flat)
        workouts_added += 1
        sets_added += len(flat)
        cur_w = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        mw = _WHDR.match(line)
        if mw:
            flush()
            cur_w = {"date": _dt.strptime(mw.group(2), "%Y-%m-%d").date(),
                     "title": mw.group(1)[:120], "duration": _dur_to_min(mw.group(4)),
                     "exercises": []}
            cur_ex = None; cur_cols = None
            continue
        me = _EHDR.match(line)
        if me and cur_w is not None:
            name = me.group(2).split(" · ")[0].strip()[:80]
            cur_ex = {"name": name, "sets": []}
            cur_w["exercises"].append(cur_ex)
            cur_cols = None
            continue
        if line.startswith("#;"):
            parts = line.split(";")
            cur_cols = (parts[1].strip().upper() if len(parts) > 1 else "KG",
                        parts[2].strip().upper() if len(parts) > 2 else "REPS")
            continue
        # Satzzeile
        if cur_ex is not None and _re.match(r"^\d+;", line):
            p = line.split(";")
            if len(p) < 3:
                continue
            unit1 = (cur_cols or ("KG", "REPS"))[0]
            unit2 = (cur_cols or ("KG", "REPS"))[1]
            s = {}
            if unit1 == "KM":
                s["distance_km"] = _num(p[1])
                s["duration_s"] = _time_to_sec(p[2], unit2)
            else:  # KG
                s["weight_kg"] = _num(p[1])
                if unit2 == "REPS":
                    r = _num(p[2]); s["reps"] = int(r) if r is not None else None
                else:
                    s["duration_s"] = _time_to_sec(p[2], unit2)
            cur_ex["sets"].append(s)
    flush()
    return {"workouts": workouts_added, "sets": sets_added, "skipped": skipped}


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


# ── AlphaProgression: smarte Gewichtsprogression ─────────────────────────────

def suggest_next_weight(exercise_name: str, sets_target: int = 3, reps_target: int = 8) -> dict:
    """
    Schlägt das nächste Trainingsgewicht vor basierend auf den letzten 4 Sessions.
    Logik: Wenn alle Sätze der letzten Session vollständig (≥ reps_target) → +2.5kg (Oberkörper) / +5kg (Unterkörper).
    Wenn <70% der Sätze vollständig → gleiches Gewicht. Wenn <50% → -5%.
    """
    rows = db.query(
        """SELECT ws.weight_kg, ws.reps, ws.set_index, w.date
           FROM workout_sets ws
           JOIN exercises e ON ws.exercise_id = e.id
           JOIN workouts w ON ws.workout_id = w.id
           WHERE e.name ILIKE %s AND ws.weight_kg IS NOT NULL
           ORDER BY w.date DESC, ws.set_index ASC
           LIMIT 20""",
        (f"%{exercise_name}%",),
    )
    if not rows:
        return {"exercise": exercise_name, "suggestion": None, "reason": "Keine Daten vorhanden."}

    # Letzte Session isolieren
    last_date = rows[0]["date"]
    last_sets  = [r for r in rows if r["date"] == last_date]
    if not last_sets:
        return {"exercise": exercise_name, "suggestion": None, "reason": "Keine Sätze gefunden."}

    last_weight  = last_sets[0]["weight_kg"]
    full_sets    = sum(1 for s in last_sets if (s["reps"] or 0) >= reps_target)
    ratio        = full_sets / max(len(last_sets), 1)

    lower_body   = any(kw in exercise_name.lower() for kw in
                       ["squat", "deadlift", "leg", "lunge", "press down", "romanian"])
    increment    = 5.0 if lower_body else 2.5

    if ratio >= 0.9:
        next_weight = last_weight + increment
        reason = f"Alle Sätze vollständig ({full_sets}/{len(last_sets)}) → +{increment}kg"
    elif ratio >= 0.5:
        next_weight = last_weight
        reason = f"Teilweise vollständig ({full_sets}/{len(last_sets)}) → gleich bleiben"
    else:
        next_weight = round(last_weight * 0.95 / 2.5) * 2.5
        reason = f"Zu viele unvollständige Sätze ({full_sets}/{len(last_sets)}) → -5%"

    return {
        "exercise": exercise_name,
        "last_weight_kg": last_weight,
        "suggestion_kg": next_weight,
        "ratio": round(ratio, 2),
        "reason": reason,
        "last_date": str(last_date),
    }


def progression_report(days: int = 30) -> list[dict]:
    """Fortschrittsbericht: Für alle Übungen der letzten N Tage → Progression berechnen."""
    exercises = db.query(
        """SELECT DISTINCT e.name FROM exercises e
           JOIN workout_sets ws ON ws.exercise_id = e.id
           JOIN workouts w ON ws.workout_id = w.id
           WHERE w.date >= CURRENT_DATE - %s AND ws.weight_kg IS NOT NULL
           ORDER BY e.name""",
        (days,),
    )
    results = []
    for ex in exercises:
        s = suggest_next_weight(ex["name"])
        if s.get("suggestion_kg"):
            results.append(s)
    return results
