"""Adaptive Trainingsplan-Generierung: pure Validierung + LLM-Orchestrierung."""
import logging
from datetime import date, datetime

log = logging.getLogger("alfred.plan")

DEFAULT_PLAN = {
    "lower": [
        {"name": "Squat", "weight": 100, "reps": 5, "sets": 4, "rpe": 8},
        {"name": "Romanian Deadlift", "weight": 80, "reps": 8, "sets": 3, "rpe": 7},
        {"name": "Leg Press", "weight": 140, "reps": 10, "sets": 3, "rpe": 8},
        {"name": "Leg Curl", "weight": 50, "reps": 12, "sets": 3, "rpe": 8},
        {"name": "Calf Raise", "weight": 60, "reps": 15, "sets": 4, "rpe": 9},
    ],
    "upper": [
        {"name": "Bench Press", "weight": 80, "reps": 6, "sets": 4, "rpe": 8},
        {"name": "Overhead Press", "weight": 50, "reps": 8, "sets": 3, "rpe": 7},
        {"name": "Barbell Row", "weight": 70, "reps": 8, "sets": 4, "rpe": 7},
        {"name": "Dumbbell Curl", "weight": 16, "reps": 10, "sets": 3, "rpe": 8},
        {"name": "Tricep Pushdown", "weight": 35, "reps": 12, "sets": 3, "rpe": 8},
        {"name": "Lateral Raise", "weight": 10, "reps": 15, "sets": 3, "rpe": 9},
    ],
}


def _clamp_int(v, lo: int, hi: int, default: int) -> int:
    try:
        v = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def normalize_plan(raw) -> dict | None:
    """Validiert/säubert LLM-JSON zu {lower:[...], upper:[...]}. None wenn ungültig."""
    if not isinstance(raw, dict):
        return None
    out = {}
    for slot in ("lower", "upper"):
        items = raw.get(slot)
        if not isinstance(items, list):
            return None
        cleaned = []
        for it in items:
            if not isinstance(it, dict):
                continue
            name = (it.get("name") or "").strip()
            if not name:
                continue
            ex = {"name": name,
                  "sets": _clamp_int(it.get("sets"), 1, 6, 3),
                  "reps": _clamp_int(it.get("reps"), 1, 30, 8)}
            w = it.get("weight")
            try:
                if w is not None:
                    ex["weight"] = float(w)
            except (TypeError, ValueError):
                pass
            rpe = it.get("rpe")
            if rpe is not None:
                ex["rpe"] = _clamp_int(rpe, 1, 10, 7)
            cleaned.append(ex)
        if not cleaned:
            return None
        out[slot] = cleaned
    return out


def needs_regen(plan: dict | None, today: date) -> bool:
    """True wenn kein Plan vorhanden oder der aktive Plan ≥42 Tage alt ist."""
    if not plan:
        return True
    created = plan.get("created_at")
    if isinstance(created, datetime):
        d = created.date()
    elif isinstance(created, date):
        d = created
    elif created:
        d = date.fromisoformat(str(created)[:10])
    else:
        return True
    return (today - d).days >= 42
