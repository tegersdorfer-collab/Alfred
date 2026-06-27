"""
Nutrition — API-Router. Aus web/api.py extrahiert (verhaltensgleich).
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


def _sum_food_items(data: dict) -> dict:
    """Summiert die vom Vision-Modell geschätzten Einzelkomponenten zu Gesamt-Makros.
    Robuster als das Modell selbst rechnen zu lassen. Fällt auf Top-Level-Werte zurück,
    falls keine 'items' geliefert wurden (altes flaches Format)."""
    if not isinstance(data, dict):
        return {}
    items = data.get("items")
    out = {
        "food_name": data.get("food_name") or data.get("name") or "Mahlzeit",
        "portion": data.get("portion") or "",
        "confidence": data.get("confidence"),
    }
    if isinstance(items, list) and items:
        def _s(key: str) -> float:
            total = 0.0
            for it in items:
                if isinstance(it, dict):
                    try:
                        total += float(it.get(key) or 0)
                    except (TypeError, ValueError):
                        pass
            return round(total, 1)
        out.update(calories=_s("calories"), protein=_s("protein"),
                   carbs=_s("carbs"), fat=_s("fat"), items=items)
    else:
        for k in ("calories", "protein", "carbs", "fat"):
            try:
                out[k] = float(data.get(k) or 0)
            except (TypeError, ValueError):
                out[k] = 0
    return out


def build_router(orch=None) -> APIRouter:
    router = APIRouter()

    @router.get("/api/nutrition")
    def nutrition_day(date_str: str = None):
        d = date.fromisoformat(date_str) if date_str else date.today()
        return {"meals": _jsonable(nutrition.meals_for(d)), "totals": _jsonable(nutrition.day_totals(d))}

    @router.post("/api/nutrition/analyze-photo")
    async def analyze_food_photo(req: Request):
        """
        Empfängt multipart/form-data mit 'image' (JPEG) und optionalem 'text'.
        Schickt Bild an lokales Vision-Modell → gibt Makro-Schätzung zurück.
        """
        import base64 as _b64
        import re as _re
        try:
            form = await req.form()
            image_file = form.get("image")
            annotation = form.get("text") or ""
            if not image_file:
                return JSONResponse({"error": "kein Bild"}, 400)
            image_bytes = await image_file.read()
        except Exception as e:
            return JSONResponse({"error": f"Upload-Fehler: {e}"}, 400)

        try:
            import ollama as _ollama
            b64 = _b64.standard_b64encode(image_bytes).decode()
            _client = _ollama.AsyncClient(host=config.OLLAMA_BASE_URL)
            vision_model = getattr(config, "VISION_MODEL", "qwen3-vl:8b")
            prompt = (
                "Du bist ein Ernährungsexperte. Schätze die Nährwerte dieses Essens/Getränks "
                "so genau wie möglich.\n"
                + (f"Zusatzinfo vom Nutzer: {annotation}.\n" if annotation else "")
                + "Gehe so vor:\n"
                "1. Zerlege das Gericht in seine einzelnen Komponenten (z.B. Reis, Hähnchen, Soße).\n"
                "2. Schätze für JEDE Komponente das Gewicht in Gramm — nutze Teller, Besteck oder "
                "Hand als Größenreferenz. Lieber realistisch großzügig als zu klein.\n"
                "3. Berechne pro Komponente kcal/Protein/Kohlenhydrate/Fett anhand üblicher Nährwerte.\n"
                "Antworte NUR mit JSON (kein Text davor/danach), Einheiten kcal und Gramm:\n"
                '{"items":[{"name":"...","grams":0,"calories":0,"protein":0,"carbs":0,"fat":0}],'
                '"food_name":"Gesamtgericht","portion":"z.B. 1 großer Teller","confidence":0.0}'
            )
            resp = await _client.chat(
                model=vision_model,
                messages=[{"role": "user", "content": prompt, "images": [b64]}],
                options={"num_predict": 600, "temperature": 0.2, "num_ctx": 8192},
                keep_alive=0,
                format="json",
            )
            raw = (resp.message.content or "").strip()
            data = extract_json(raw, default={})
            return {"ok": True, "result": _sum_food_items(data)}
        except Exception as e:
            log.error(f"Vision-Analyse fehlgeschlagen: {e}")
            return JSONResponse({"ok": False, "error": str(e)}, 500)

    @router.post("/api/nutrition/log-meal")
    async def log_meal_from_app(req: Request):
        """Mahlzeit von iOS-App speichern."""
        d = await req.json()
        mid = nutrition.log_meal(
            description=d.get("name", "Mahlzeit"),
            meal_type="snack",
            calories=d.get("calories"),
            protein_g=d.get("protein"),
            carbs_g=d.get("carbs"),
            fat_g=d.get("fat"),
        )
        return {"ok": True, "id": mid}

    @router.get("/api/nutrition/history")
    def nutrition_history(days: int = 14):
        return _jsonable(nutrition.history(days))

    @router.post("/api/nutrition")
    async def add_meal(req: Request):
        d = await req.json()
        mid = nutrition.log_meal(description=d["description"], meal_type=d.get("meal_type", "snack"),
                                 calories=d.get("calories"), protein_g=d.get("protein_g"),
                                 carbs_g=d.get("carbs_g"), fat_g=d.get("fat_g"))
        return {"id": mid}

    @router.get("/api/nutrition/goals")
    def nutrition_goals():
        """Adaptiver Kalorie-Rechner für Bulk.
        Basis: BMR × Aktivitätsfaktor + Surplus.
        Anpassung: Gewichtstrend aus DB vs. Zielrate → ±kcal akkumuliert in settings.
        """
        HEIGHT_CM = 192
        AGE = 19
        WEIGHT_KG = 84        # Stargewicht / Fallback
        TARGET_WEIGHT = 90
        BULK_SURPLUS = 300
        ACTIVITY_FACTOR = 1.65
        TARGET_KG_PER_WEEK = 0.25   # sauberer Bulk
        ADJUST_STEP = 150            # kcal pro Anpassungsschritt
        MAX_ADJUSTMENT = 600         # maximale Gesamtabweichung vom Basis-Ziel

        # Aktuelles Gewicht: neuester DB-Eintrag
        w_row = db.query_one(
            "SELECT weight, date FROM health_data WHERE weight IS NOT NULL ORDER BY date DESC LIMIT 1"
        )
        current_weight = w_row["weight"] if w_row else WEIGHT_KG

        # BMR mit aktuellem Gewicht
        bmr = 10 * current_weight + 6.25 * HEIGHT_CM - 5 * AGE + 5
        tdee_base = bmr * ACTIVITY_FACTOR

        # Aktivitäts-Bonus heutiger Tag vs. 7-Tage-Schnitt
        act_rows = db.query(
            "SELECT active_calories FROM health_data "
            "WHERE date >= CURRENT_DATE - 7 AND active_calories IS NOT NULL ORDER BY date DESC LIMIT 7"
        )
        avg_active = sum(r["active_calories"] for r in act_rows) / len(act_rows) if act_rows else 350
        today_row = db.query_one("SELECT active_calories FROM health_data WHERE date = CURRENT_DATE")
        today_active = (today_row or {}).get("active_calories") or avg_active
        activity_bonus = max(0, today_active - avg_active)

        # ── Gewichtstrend-Analyse (lineare Regression) ───────────────────────
        w_rows = db.query(
            "SELECT date, weight FROM health_data WHERE weight IS NOT NULL "
            "AND date >= CURRENT_DATE - 60 ORDER BY date ASC"
        )
        trend_status = "insufficient_data"
        actual_kg_per_week = None
        trend_adjustment = int(db.get_setting("bulk_kcal_adjustment") or 0)

        if len(w_rows) >= 2:
            # Tage seit erstem Eintrag als x, Gewicht als y
            from datetime import date as _date
            dates = [r["date"] if isinstance(r["date"], _date) else _date.fromisoformat(str(r["date"])) for r in w_rows]
            weights = [float(r["weight"]) for r in w_rows]
            x0 = dates[0]
            xs = [(d - x0).days for d in dates]
            n = len(xs)
            mx = sum(xs) / n
            my = sum(weights) / n
            denom = sum((xi - mx) ** 2 for xi in xs)
            if denom > 0:
                slope_per_day = sum((xs[i] - mx) * (weights[i] - my) for i in range(n)) / denom
                actual_kg_per_week = round(slope_per_day * 7, 3)
                span_days = (dates[-1] - dates[0]).days

                if span_days >= 14:
                    diff = actual_kg_per_week - TARGET_KG_PER_WEEK
                    if diff < -0.05:       # zu langsam → mehr essen
                        trend_status = "too_slow"
                        new_adj = min(trend_adjustment + ADJUST_STEP, MAX_ADJUSTMENT)
                    elif diff > 0.1:       # zu schnell → weniger essen
                        trend_status = "too_fast"
                        new_adj = max(trend_adjustment - ADJUST_STEP, -MAX_ADJUSTMENT)
                    else:
                        trend_status = "on_track"
                        new_adj = trend_adjustment

                    # Nur speichern wenn sich etwas geändert hat
                    if new_adj != trend_adjustment:
                        db.set_setting("bulk_kcal_adjustment", str(new_adj))
                        trend_adjustment = new_adj
                else:
                    trend_status = "not_enough_span"

        tdee = tdee_base + activity_bonus
        kcal_goal = round(tdee + BULK_SURPLUS + trend_adjustment)

        # Makros: 2.2g P/kg, 1.0g F/kg, Rest Carbs
        protein_g = round(current_weight * 2.2)
        fat_g = round(current_weight * 1.0)
        carbs_g = round((kcal_goal - protein_g * 4 - fat_g * 9) / 4)

        return {
            "kcal": kcal_goal,
            "protein": protein_g,
            "carbs": max(carbs_g, 50),
            "fat": fat_g,
            "meta": {
                "bmr": round(bmr),
                "current_weight": current_weight,
                "activity_factor": ACTIVITY_FACTOR,
                "tdee_base": round(tdee_base),
                "activity_bonus": round(activity_bonus),
                "tdee": round(tdee),
                "surplus": BULK_SURPLUS,
                "trend_adjustment": trend_adjustment,
                "trend_status": trend_status,
                "actual_kg_per_week": actual_kg_per_week,
                "target_kg_per_week": TARGET_KG_PER_WEEK,
            }
        }

    @router.post("/api/nutrition/goals/reset-adjustment")
    def reset_bulk_adjustment():
        """Setzt die akkumulierte Kalorie-Anpassung zurück."""
        db.set_setting("bulk_kcal_adjustment", "0")
        return {"ok": True}

    return router
