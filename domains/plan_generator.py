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


def build_prompt(profile: dict, last_exercises: list[str], muscle_volume: dict) -> str:
    avoid = ", ".join(last_exercises) if last_exercises else "—"
    vol = ", ".join(f"{k}:{v}" for k, v in (muscle_volume or {}).items() if v)
    return (
        "Du bist ein Personal Trainer. Erstelle einen 6-Wochen-Trainingsplan für einen "
        "Push/Pull-freien Split mit genau zwei Krafttagen: LOWER (Beine/Rumpf) und UPPER "
        "(Oberkörper). Joggen ist separat und NICHT Teil des Plans.\n\n"
        f"Profil:\n- Ziel: {profile.get('goal')}\n- Equipment: {profile.get('equipment')}\n"
        f"- Erfahrung: {profile.get('experience')}\n- Hinweise: {profile.get('notes') or 'keine'}\n\n"
        f"Trainiertes Volumen (letzte 30 Tage, Sätze je Muskel): {vol or 'wenig Daten'}\n"
        f"Übungen des letzten Plans (bitte variieren, möglichst NICHT wiederholen): {avoid}\n\n"
        "Wähle pro Tag 5–6 Übungen passend zu Ziel, Equipment und Erfahrung. "
        "Realistische Startgewichte in kg. Antworte AUSSCHLIESSLICH mit JSON in genau diesem Schema:\n"
        '{"lower":[{"name":"...","weight":100,"reps":5,"sets":4,"rpe":8}],'
        '"upper":[{"name":"...","weight":80,"reps":6,"sets":4,"rpe":8}]}'
    )


async def generate_and_save(chat_llm, bg_llm=None) -> dict | None:
    """Generiert einen Plan via LLM (Claude→qwen Fallback), validiert, speichert.
    Gibt den gespeicherten Plan zurück oder None (dann bleibt der alte Plan aktiv)."""
    from domains import fitness
    from core.jsonutil import extract_json

    profile = fitness.get_training_profile()
    last = fitness.active_plan()
    last_ex: list[str] = []
    if last and isinstance(last.get("plan_json"), dict):
        for slot in ("lower", "upper"):
            last_ex += [e.get("name") for e in last["plan_json"].get(slot, []) if e.get("name")]
    muscle = fitness.muscle_volume(30)
    prompt = build_prompt(profile, last_ex, muscle)

    plan = None
    for llm in (chat_llm, bg_llm):
        if not llm:
            continue
        try:
            txt = await llm.chat(messages=[{"role": "user", "content": prompt}],
                                 temperature=0.4, max_tokens=1200, format="json")
            plan = normalize_plan(extract_json(txt, default=None))
            if plan:
                break
        except Exception:
            log.exception("Plan-LLM fehlgeschlagen, versuche Fallback")
            plan = None

    if not plan:
        log.warning("Plan-Generierung lieferte keinen gültigen Plan — alter Plan bleibt aktiv")
        return None

    for slot in ("lower", "upper"):
        for ex in plan[slot]:
            fitness.ensure_exercise(ex["name"])
    fitness.save_training_plan(name="Alfred-Block", goal=profile.get("goal", "muscle"),
                               weeks=6, plan=plan)
    log.info("Neuer Trainingsplan generiert und gespeichert")
    return plan
