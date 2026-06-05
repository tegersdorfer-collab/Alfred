"""
Jarvis Dashboard API – läuft IM Jarvis-Prozess (geteilter State mit dem Agent).
Voll interaktiv: REST für alle Domänen + 2-Wege-Chat (SSE-Streaming) + Live-Feeds.
"""
import asyncio
import json
import logging
import os
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import config
from core import db, tools as T
from domains import habits, fitness, nutrition, journal, goals, weather, tasks as tasks_d

log = logging.getLogger("jarvis.api")
WEB_DIR = Path(__file__).parent


def create_app(orch=None) -> FastAPI:
    app = FastAPI(title="Jarvis Dashboard", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    # ── Status / Overview ────────────────────────────────────────────────────
    @app.get("/api/status")
    def status():
        pid = None; running = False
        try:
            pid = int(open("/tmp/jarvis.pid").read().strip())
            os.kill(pid, 0); running = True
        except Exception:
            pass
        return {"running": running or orch is not None, "pid": pid,
                "model": config.OLLAMA_MODEL, "tools": len(T.REGISTRY),
                "time": datetime.now().strftime("%H:%M:%S")}

    @app.get("/api/overview")
    def overview():
        out = {}
        try:
            h = orch._dashboard.get_recent_health(days=2) if orch else []
            out["health"] = [_health_dict(x) for x in h]
        except Exception:
            out["health"] = []
        try:
            out["habits"] = habits.habit_overview()
        except Exception:
            out["habits"] = []
        try:
            out["tasks"] = _jsonable(tasks_d.list_tasks("open"))
        except Exception:
            out["tasks"] = []
        try:
            out["events"] = [_event_dict(e) for e in orch._dashboard.get_upcoming_events(7)] if orch else []
        except Exception:
            out["events"] = []
        try:
            out["goals"] = goals.list_goals()
        except Exception:
            out["goals"] = []
        try:
            out["nutrition"] = nutrition.day_totals()
        except Exception:
            out["nutrition"] = {}
        try:
            out["fitness"] = fitness.weekly_volume()
        except Exception:
            out["fitness"] = {}
        return out

    @app.get("/api/weather")
    async def api_weather():
        return await weather.get_weather()

    # ── Health ────────────────────────────────────────────────────────────────
    @app.get("/api/health")
    def health(days: int = 14):
        if not orch:
            return []
        return [_health_dict(h) for h in orch._dashboard.get_recent_health(days=days)]

    # ── Habits ──────────────────────────────────────────────────────────────────
    @app.get("/api/habits")
    def get_habits():
        return habits.habit_overview()

    @app.post("/api/habits")
    async def create_habit(req: Request):
        d = await req.json()
        name = (d.get("name") or "").strip()
        if not name:
            return JSONResponse({"error": "Name fehlt"}, 400)
        hid = habits.create_habit(name=name, emoji=d.get("emoji", "✅"),
                                  cadence=d.get("cadence", "daily"),
                                  target_per_week=d.get("target_per_week", 7),
                                  color=d.get("color", "#0ea5e9"))
        return {"id": hid}

    @app.post("/api/habits/{hid}/log")
    async def log_habit(hid: int, req: Request):
        d = await req.json() if await _has_body(req) else {}
        habits.log_habit(hid, done=d.get("done", True))
        return {"ok": True, "streak": habits.streak(hid)}

    @app.delete("/api/habits/{hid}")
    def del_habit(hid: int):
        habits.delete_habit(hid); return {"ok": True}

    @app.post("/api/habits/{hid}/unlog")
    def unlog_habit(hid: int):
        habits.unlog_habit(hid); return {"ok": True, "streak": habits.streak(hid)}

    @app.get("/api/habits/commit")
    def habits_commit(days: int = 30):
        return habits.commit_history(days)

    # ── Tasks (jarvis-nativ: Arten, Unteraufgaben, Fortschritt, Archiv) ──────────
    @app.get("/api/tasks")
    def get_tasks(status: str = "open"):
        return _jsonable(tasks_d.list_tasks(status))

    @app.post("/api/tasks")
    async def create_task(req: Request):
        d = await req.json()
        from core.timeparse import parse_datetime
        due = parse_datetime(d["due"]) if d.get("due") else None
        tid = tasks_d.create_task(title=d["title"], priority=d.get("priority", "medium"),
                                  kind=d.get("kind", "task"), due=due,
                                  notes=d.get("notes"), parent_id=d.get("parent_id"))
        return {"id": tid}

    @app.post("/api/tasks/{tid}/complete")
    def complete_task(tid: int):
        tasks_d.complete_task(tid); return {"ok": True}

    @app.post("/api/tasks/{tid}/progress")
    async def task_progress(tid: int, req: Request):
        d = await req.json()
        tasks_d.set_progress(tid, int(d.get("progress_pct", 0))); return {"ok": True}

    @app.post("/api/tasks/{tid}/status")
    async def task_status(tid: int, req: Request):
        d = await req.json()
        tasks_d.set_status(tid, d.get("status", "todo")); return {"ok": True}

    @app.post("/api/tasks/{tid}/archive")
    def task_archive(tid: int):
        tasks_d.archive_task(tid); return {"ok": True}

    @app.delete("/api/tasks/{tid}")
    def task_delete(tid: int):
        tasks_d.delete_task(tid); return {"ok": True}

    # ── Kalender ─────────────────────────────────────────────────────────────────
    @app.get("/api/calendar")
    def calendar(days: int = 14):
        if not orch:
            return []
        return [_event_dict(e) for e in orch._dashboard.get_upcoming_events(days)]

    @app.post("/api/calendar")
    async def create_event(req: Request):
        d = await req.json()
        from core.timeparse import parse_datetime
        s = parse_datetime(d["start"])
        e = parse_datetime(d["end"]) if d.get("end") else None
        orch._dashboard.create_event(title=d["title"], start=s, end=e, location=d.get("location"))
        return {"ok": True}

    # ── Fitness ──────────────────────────────────────────────────────────────────
    @app.get("/api/workouts")
    def workouts(limit: int = 20):
        return _jsonable(fitness.recent_workouts(limit))

    @app.post("/api/workouts")
    async def add_workout(req: Request):
        d = await req.json()
        wid = fitness.log_workout(
            title=d["title"], type_=d.get("type", "strength"),
            duration_min=d.get("duration_min"), distance_km=d.get("distance_km"),
            notes=d.get("notes"), rpe=d.get("rpe"), sets=d.get("sets"))
        return {"id": wid}

    @app.get("/api/fitness/volume")
    def volume():
        return _jsonable(fitness.weekly_volume())

    @app.get("/api/fitness/volume_by_day")
    def volume_by_day(days: int = 14):
        return _jsonable(fitness.volume_by_day(days))

    @app.get("/api/fitness/muscles")
    def muscles(days: int = 7):
        return fitness.muscle_volume(days)

    @app.get("/api/fitness/exercises")
    def exercises():
        return _jsonable(fitness.list_exercises())

    @app.get("/api/fitness/plan")
    def get_plan():
        return _jsonable(fitness.active_plan()) or {}

    @app.post("/api/fitness/import")
    async def import_workout(req: Request):
        """Text-Dump eines Trainings → KI parst in strukturierte Workouts/Sätze."""
        d = await req.json()
        dump = d.get("text", "").strip()
        if not dump:
            return JSONResponse({"error": "kein Text"}, 400)
        if not orch:
            return JSONResponse({"error": "kein Kern"}, 503)
        import json as _json
        prompt = (
            "Parse diesen Trainings-Dump in JSON. Format:\n"
            '{"title":"...","type":"strength|run|mobility","duration_min":null,'
            '"distance_km":null,"exercises":[{"name":"...","sets":[{"reps":10,"weight_kg":60}]}]}\n'
            "Nur JSON, kein Text drumherum.\n\nDump:\n" + dump + "\n\nJSON:"
        )
        raw = await orch.llm.chat(messages=[{"role": "user", "content": prompt}],
                                  temperature=0.2, max_tokens=900)
        try:
            s, e = raw.find("{"), raw.rfind("}") + 1
            data = _json.loads(raw[s:e])
        except Exception as ex:
            return JSONResponse({"error": f"Parsing fehlgeschlagen: {ex}", "raw": raw[:300]}, 422)
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

    # ── Ernährung ────────────────────────────────────────────────────────────────
    @app.get("/api/nutrition")
    def nutrition_day(date_str: str = None):
        d = date.fromisoformat(date_str) if date_str else date.today()
        return {"meals": _jsonable(nutrition.meals_for(d)), "totals": _jsonable(nutrition.day_totals(d))}

    @app.get("/api/nutrition/history")
    def nutrition_history(days: int = 14):
        return _jsonable(nutrition.history(days))

    @app.post("/api/nutrition")
    async def add_meal(req: Request):
        d = await req.json()
        mid = nutrition.log_meal(description=d["description"], meal_type=d.get("meal_type", "snack"),
                                 calories=d.get("calories"), protein_g=d.get("protein_g"),
                                 carbs_g=d.get("carbs_g"), fat_g=d.get("fat_g"))
        return {"id": mid}

    # ── Journal ──────────────────────────────────────────────────────────────────
    @app.get("/api/journal")
    def get_journal(limit: int = 30):
        return _jsonable(journal.recent_entries(limit))

    @app.post("/api/journal")
    async def add_journal(req: Request):
        d = await req.json()
        jid = journal.add_entry(content=d["content"], mood=d.get("mood"),
                                energy=d.get("energy"), tags=d.get("tags"))
        return {"id": jid}

    @app.get("/api/journal/mood")
    def mood(days: int = 30):
        return _jsonable(journal.mood_trend(days))

    # ── Ziele ────────────────────────────────────────────────────────────────────
    @app.get("/api/goals")
    def get_goals(status: str = "active"):
        return _jsonable(goals.list_goals(status))

    @app.post("/api/goals")
    async def create_goal(req: Request):
        d = await req.json()
        from core.timeparse import parse_date
        dl = parse_date(d["deadline"]) if d.get("deadline") else None
        gid = goals.create_goal(title=d["title"], category=d.get("category", "general"),
                                target_value=d.get("target_value"), unit=d.get("unit"),
                                deadline=dl, notes=d.get("notes"))
        return {"id": gid}

    @app.post("/api/goals/{gid}/progress")
    async def goal_progress(gid: int, req: Request):
        d = await req.json()
        goals.update_progress(gid, current_value=d.get("current_value"),
                              progress_pct=d.get("progress_pct"), status=d.get("status"))
        return {"ok": True}

    @app.delete("/api/goals/{gid}")
    def goal_delete(gid: int):
        goals.delete_goal(gid); return {"ok": True}

    # ── Memory ───────────────────────────────────────────────────────────────────
    @app.get("/api/memories")
    def memories():
        rows = db.query("SELECT id, content, category, confidence, created_at FROM memories ORDER BY created_at DESC LIMIT 100")
        return _jsonable(rows)

    @app.post("/api/memories")
    async def add_memory(req: Request):
        d = await req.json()
        if orch:
            emb = await orch.llm.embed(d["content"])
            orch.lzg.save(content=d["content"], embedding=emb,
                          category=d.get("category", "fact"), confidence=d.get("confidence", 0.85))
        return {"ok": True}

    @app.delete("/api/memories/{mid}")
    def del_memory(mid: int):
        db.execute("DELETE FROM memories WHERE id=%s", (mid,)); return {"ok": True}

    # ── Jarvis Mind (Events, Reflexionen, Agenda) ────────────────────────────────
    @app.get("/api/mind")
    def mind():
        return {
            "events": _jsonable(db.query("SELECT type, summary, created_at FROM events_log ORDER BY created_at DESC LIMIT 60")),
            "reflections": _jsonable(db.query("SELECT kind, content, created_at FROM reflections ORDER BY created_at DESC LIMIT 20")),
            "notes": db.get_setting("meta_notes", []),
            "agenda": _jsonable(db.query("SELECT kind, title, status, created_at FROM agenda ORDER BY created_at DESC LIMIT 20")),
        }

    # ── Tools-Katalog ────────────────────────────────────────────────────────────
    @app.get("/api/tools")
    def tools_list():
        return [{"name": t.name, "category": t.category, "description": t.description}
                for t in T.REGISTRY.values()]

    # ── Analytics ────────────────────────────────────────────────────────────────
    @app.get("/api/analytics")
    def analytics():
        out = {}
        if orch:
            try:
                out["health"] = [_health_dict(h) for h in orch._dashboard.get_recent_health(days=30)]
            except Exception:
                out["health"] = []
        out["mood"] = _jsonable(journal.mood_trend(30))
        out["workouts_30d"] = db.query_one("SELECT COUNT(*) c FROM workouts WHERE date >= CURRENT_DATE - 30") or {"c": 0}
        out["habits"] = habits.habit_overview(30)
        return _jsonable(out)

    # ── Settings ─────────────────────────────────────────────────────────────────
    @app.get("/api/settings")
    def get_settings():
        return {
            "weather_city": db.get_setting("weather_city", "Berlin"),
            "proactive_interval": db.get_setting("proactive_interval_override", config.PROACTIVE_INTERVAL),
            "meta_notes": db.get_setting("meta_notes", []),
        }

    @app.post("/api/settings")
    async def set_settings(req: Request):
        d = await req.json()
        for k, v in d.items():
            db.set_setting(k, v)
        return {"ok": True}

    # ── Chat (2-Wege mit dem echten Agent) ────────────────────────────────────────
    @app.get("/api/chat/history")
    def chat_history(limit: int = 50):
        rows = db.query("SELECT role, content, channel, created_at FROM chat_messages ORDER BY created_at DESC LIMIT %s", (limit,))
        return _jsonable(list(reversed(rows)))

    @app.post("/api/chat")
    async def chat(req: Request):
        d = await req.json()
        if not orch:
            return {"response": "Jarvis-Kern nicht verbunden."}
        resp, trace = await orch.dashboard_respond(d["text"])
        return {"response": resp, "tools": [t["tool"] for t in trace]}

    @app.get("/api/chat/stream")
    async def chat_stream(text: str):
        if not orch:
            return JSONResponse({"error": "kein Kern"}, 503)
        q: asyncio.Queue = asyncio.Queue()

        async def cb(full):
            await q.put({"partial": full})

        async def run():
            try:
                resp, trace = await orch.dashboard_respond(text, stream_cb=cb)
                await q.put({"done": resp, "tools": [t["tool"] for t in trace]})
            except Exception as e:
                await q.put({"done": f"Fehler: {e}", "tools": []})

        task = asyncio.create_task(run())

        async def gen():
            try:
                while True:
                    item = await q.get()
                    yield f"data: {json.dumps(item)}\n\n"
                    if "done" in item:
                        break
            finally:
                if not task.done():
                    task.cancel()

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ── Live Event-Feed (SSE) ─────────────────────────────────────────────────────
    @app.get("/api/feed/stream")
    async def feed_stream():
        async def gen():
            last_id = 0
            row = db.query_one("SELECT MAX(id) m FROM events_log")
            last_id = (row["m"] or 0) if row else 0
            while True:
                rows = db.query("SELECT id, type, summary, created_at FROM events_log WHERE id > %s ORDER BY id", (last_id,))
                for r in rows:
                    last_id = r["id"]
                    yield f"data: {json.dumps(_jsonable(r))}\n\n"
                await asyncio.sleep(1.5)
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ── Index ─────────────────────────────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    def index():
        return HTMLResponse(
            (WEB_DIR / "index.html").read_text(),
            headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
        )

    @app.get("/sw.js")
    def service_worker():
        from fastapi.responses import Response
        return Response(
            (WEB_DIR / "sw.js").read_text(),
            media_type="application/javascript",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/manifest.json")
    def manifest():
        return JSONResponse({
            "name": "Jarvis", "short_name": "Jarvis",
            "start_url": "/", "display": "standalone",
            "background_color": "#0a0f1e", "theme_color": "#0a0f1e",
            "icons": [{"src": "https://em-content.zobj.net/source/apple/391/robot_1f916.png",
                       "sizes": "160x160", "type": "image/png"}],
        })

    return app


# ── Helfer ────────────────────────────────────────────────────────────────────

async def _has_body(req: Request) -> bool:
    try:
        body = await req.body()
        return len(body) > 0
    except Exception:
        return False


def _jsonable(obj):
    if isinstance(obj, list):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    from decimal import Decimal
    if isinstance(obj, Decimal):
        return float(obj)
    return obj


def _health_dict(h):
    return {"date": str(h.date), "steps": h.steps, "active_calories": h.active_calories,
            "exercise_minutes": h.exercise_minutes, "sleep": h.sleep_duration,
            "sleep_deep": h.sleep_deep, "resting_hr": h.resting_hr, "hrv": h.hrv,
            "weight": h.weight}


def _task_dict(t):
    return {"id": t.id, "title": t.title, "status": t.status, "priority": t.priority,
            "due": t.due_date.strftime("%d.%m") if t.due_date else None}


def _event_dict(e):
    return {"title": e.title,
            "start": e.start.strftime("%d.%m. %H:%M") if not e.all_day else e.start.strftime("%d.%m."),
            "start_iso": e.start.isoformat(), "all_day": e.all_day,
            "calendar": e.calendar, "location": e.location}
