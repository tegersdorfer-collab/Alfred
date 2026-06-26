"""
Fitness — API-Router. Aus web/api.py extrahiert (verhaltensgleich).
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

    @router.get("/api/workouts")
    def workouts(limit: int = 20):
        return _jsonable(fitness.recent_workouts(limit))

    @router.post("/api/workouts")
    async def add_workout(req: Request):
        d = await req.json()
        wid = fitness.log_workout(
            title=d["title"], type_=d.get("type", "strength"),
            duration_min=d.get("duration_min"), distance_km=d.get("distance_km"),
            notes=d.get("notes"), rpe=d.get("rpe"), sets=d.get("sets"))
        t = (d.get("type") or "").lower()
        if t in ("lower", "upper"):
            fitness.record_cycle_event(t, "workout")
            habits.log_sport_done()
        return {"id": wid}

    @router.get("/api/fitness/volume")
    def volume():
        return _jsonable(fitness.weekly_volume())

    @router.get("/api/fitness/volume_by_day")
    def volume_by_day(days: int = 14):
        return _jsonable(fitness.volume_by_day(days))

    @router.get("/api/fitness/muscles")
    def muscles(days: int = 7):
        return fitness.muscle_volume(days)

    @router.get("/api/fitness/exercises")
    def exercises():
        return _jsonable(fitness.list_exercises())

    @router.get("/api/fitness/plan")
    def get_plan():
        return _jsonable(fitness.active_plan()) or {}

    @router.get("/api/fitness/today-plan")
    def today_plan():
        """Heutiger Trainingsplan: abschluss-basierter Zyklus LOWER → JOGGEN → UPPER,
        moduliert über HRV+Schlaf (Intensität) und Progressive Overload."""
        from datetime import date as _date
        import math as _math

        events = fitness.recent_cycle_events(limit=12)
        state = fitness.cycle_state(events, _date.today())
        day_type = state["slot"]
        done_today = state["done_today"]

        health = db.query_one("SELECT * FROM health_data ORDER BY date DESC LIMIT 1") or {}
        hrv = float(health.get("hrv_avg") or 0)
        sleep_h = float(health.get("sleep_hours") or 0)
        hrv_score = min(hrv / 70.0, 1.2) if hrv > 0 else 1.0
        sleep_score = min(sleep_h / 8.0, 1.1) if sleep_h > 0 else 1.0
        intensity = round(max(0.85, min(1.05, (hrv_score + sleep_score) / 2.0)), 2)

        alfred_note = ""
        if hrv > 0 and sleep_h > 0 and day_type != "jog":
            if intensity >= 1.0:
                alfred_note = f"HRV {hrv:.0f}, Schlaf {sleep_h:.1f}h — top Werte, Gewichte leicht erhöhen."
            elif intensity <= 0.88:
                alfred_note = f"HRV {hrv:.0f}, Schlaf {sleep_h:.1f}h — Erholung niedrig, Gewichte reduzieren."
            else:
                alfred_note = f"HRV {hrv:.0f}, Schlaf {sleep_h:.1f}h — normale Session."

        def last_set(exercise_name: str) -> dict | None:
            return db.query_one(
                """SELECT ws.weight_kg, ws.reps FROM workout_sets ws
                   JOIN exercises e ON e.id = ws.exercise_id
                   WHERE LOWER(e.name) = LOWER(%s)
                   ORDER BY ws.id DESC LIMIT 1""",
                (exercise_name,),
            )

        def build_sets(exercise_name: str, default_weight: float, default_reps: int,
                       working_count: int = 3, rpe_target: int = 7) -> dict:
            prev = last_set(exercise_name)
            if prev and prev.get("weight_kg"):
                base_w = float(prev["weight_kg"]) * intensity
                base_r = prev.get("reps") or default_reps
            else:
                base_w = default_weight * intensity
                base_r = default_reps
            w = _math.floor(base_w / 2.5) * 2.5
            warmup = [
                {"weight": round(w * 0.4, 1), "reps": 12},
                {"weight": round(w * 0.6, 1), "reps": 8},
                {"weight": round(w * 0.8, 1), "reps": 5},
            ]
            working = [{"weight": w, "reps": base_r, "rpe_target": rpe_target}] * working_count
            return {"name": exercise_name, "warmup_sets": warmup, "working_sets": working}

        if day_type == "lower":
            exercises_list = [
                build_sets("Squat", 100, 5, working_count=4, rpe_target=8),
                build_sets("Romanian Deadlift", 80, 8, working_count=3, rpe_target=7),
                build_sets("Leg Press", 140, 10, working_count=3, rpe_target=8),
                build_sets("Leg Curl", 50, 12, working_count=3, rpe_target=8),
                build_sets("Calf Raise", 60, 15, working_count=4, rpe_target=9),
            ]
        elif day_type == "upper":
            exercises_list = [
                build_sets("Bench Press", 80, 6, working_count=4, rpe_target=8),
                build_sets("Overhead Press", 50, 8, working_count=3, rpe_target=7),
                build_sets("Barbell Row", 70, 8, working_count=4, rpe_target=7),
                build_sets("Dumbbell Curl", 16, 10, working_count=3, rpe_target=8),
                build_sets("Tricep Pushdown", 35, 12, working_count=3, rpe_target=8),
                build_sets("Lateral Raise", 10, 15, working_count=3, rpe_target=9),
            ]
        else:  # jog
            exercises_list = []
            alfred_note = "Heute: Joggen — läuft über Strava."

        return {
            "day_type": day_type,
            "day_label": fitness.CYCLE_LABEL[day_type],
            "intensity_factor": intensity,
            "done_today": done_today,
            "next_label": state["next_label"],
            "alfred_message": alfred_note or f"Heute: {fitness.CYCLE_LABEL[day_type]}.",
            "health": {
                "hrv": hrv or None,
                "sleep_hours": sleep_h or None,
                "date": str(health.get("date", "")),
            },
            "exercises": exercises_list,
        }

    @router.post("/api/fitness/log-rpe")
    async def log_rpe(req: Request):
        """RPE-Feedback nach einer Übung speichern."""
        d = await req.json()
        workout_id = d.get("workout_id")
        exercise_name = d.get("exercise")
        rpe = d.get("rpe")
        if workout_id and rpe is not None:
            db.execute(
                "UPDATE workout_sets SET rpe = %s WHERE workout_id = %s AND exercise_id = "
                "(SELECT id FROM exercises WHERE LOWER(name) = LOWER(%s) LIMIT 1)",
                (rpe, workout_id, exercise_name or ""),
            )
        return {"ok": True}

    @router.post("/api/fitness/import")
    async def import_workout(req: Request):
        """Trainings-Import. Strukturierter Gym-App-Export → deterministischer Parser;
        freier Text → KI-Parsing."""
        d = await req.json()
        dump = d.get("text", "").strip()
        if not dump:
            return JSONResponse({"error": "kein Text"}, 400)

        # Strukturiertes Gym-App-CSV erkennen (kein LLM nötig, schnell)
        if "#;KG;REPS" in dump or "#;KM;" in dump or "#;KG;SECS" in dump:
            try:
                res = await asyncio.to_thread(fitness.import_workout_csv, dump)
                return {"ok": True, **res}
            except Exception:
                log.exception("CSV-Parsing fehlgeschlagen")
                return JSONResponse({"error": "CSV-Parsing fehlgeschlagen."}, 422)

        if not orch:
            return JSONResponse({"error": "kein Kern"}, 503)

        prompt = (
            "Parse diesen Trainings-Dump in JSON. Format:\n"
            '{"title":"...","type":"strength|run|mobility","duration_min":null,'
            '"distance_km":null,"exercises":[{"name":"...","sets":[{"reps":10,"weight_kg":60}]}]}\n'
            "Nur JSON, kein Text drumherum.\n\nDump:\n" + dump + "\n\nJSON:"
        )
        raw = await orch.chat_llm.chat(messages=[{"role": "user", "content": prompt}],
                                  temperature=0.2, max_tokens=900, format="json")
        data = extract_json(raw, default=None)
        if not isinstance(data, dict):
            return JSONResponse({"error": "Parsing fehlgeschlagen", "raw": raw[:300]}, 422)
        flat = []
        for ex in data.get("exercises", []):
            for i, st in enumerate(ex.get("sets", []), 1):
                flat.append({"exercise": ex.get("name"), "set_index": i,
                             "reps": st.get("reps"), "weight_kg": st.get("weight_kg")})
        wid = fitness.log_workout(
            title=data.get("title", "Training"), type_=data.get("type", "strength"),
            duration_min=data.get("duration_min"), distance_km=data.get("distance_km"),
            sets=flat)
        return {"id": wid, "parsed": data}

    @router.post("/api/fitness/jog-done")
    async def jog_done(req: Request):
        """Markiert den heutigen Jog-Tag als erledigt (idempotent pro Tag)."""
        try:
            d = await req.json()
        except Exception:
            d = {}
        if fitness.jog_done_today_exists():
            return {"ok": True, "already": True}
        fitness.record_cycle_event("jog", "jog")
        habits.log_sport_done()
        return {"ok": True, "source": (d or {}).get("source", "manual")}

    @router.post("/api/fitness/rest-day")
    async def rest_day(req: Request):
        """Schiebt einen Ruhetag ein — Zeiger bleibt auf dem aktuellen Slot."""
        from datetime import date as _date
        events = fitness.recent_cycle_events(limit=12)
        state = fitness.cycle_state(events, _date.today())
        fitness.record_cycle_event(state["slot"], "rest")
        return {"ok": True, "slot": state["slot"]}

    return router
