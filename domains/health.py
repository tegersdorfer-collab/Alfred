"""
Health-Domäne (jarvis-nativ).
Quelle: iCloud Health.json (vom iOS-Shortcut geschrieben) – direkt gelesen,
KEINE Abhängigkeit von der ai-dashboard. Schreibt in jarvis.health_data.
"""
import json
import logging
import os
from datetime import date, datetime, timedelta

from core import db
import config

log = logging.getLogger(__name__)

# Mapping Health.json-Key → (Spalte, Transform)
_R2 = lambda v: round(v * 100) / 100
_R1 = lambda v: round(v * 10) / 10
_MAP = {
    "stepCount":            ("steps",            lambda v: round(v)),
    "activeCalories":       ("active_calories",  lambda v: round(v)),
    "exerciseMinutes":      ("exercise_minutes", lambda v: round(v)),
    "restingHeartRate":     ("resting_hr",       lambda v: round(v)),
    "heartRateVariability": ("hrv",              _R2),
    "vo2Max":               ("vo2max",           _R2),
    "oxygenSaturation":     ("blood_oxygen",     lambda v: round(v * 100 * 100) / 100),
    "weight":               ("weight",           _R2),
    "bmi":                  ("bmi",              _R2),
    "bodyFat":              ("body_fat",         lambda v: round(v * 100 * 100) / 100),
    "walkingDistance":      ("distance",         lambda v: round((v / 1000) * 100) / 100),
    "dietaryEnergy":        ("calories",         lambda v: round(v)),
    "dietaryProtein":       ("protein",          _R1),
    "dietaryCarbohydrates": ("carbs",            _R1),
    "dietaryFatTotal":      ("fat",              _R1),
    "wristTemperature":     ("body_temp",        _R2),
}

_COLS = ["steps", "active_calories", "exercise_minutes", "stand_hours", "distance",
         "weight", "body_fat", "bmi", "resting_hr", "hrv", "vo2max",
         "sleep_duration", "sleep_deep", "sleep_rem", "sleep_core", "sleep_awake",
         "blood_oxygen", "body_temp", "calories", "protein", "carbs", "fat", "water"]


def _health_json_path() -> str:
    return os.path.expanduser(config.HEALTH_JSON_PATH)


def import_from_icloud() -> int:
    """Liest Health.json und upsertet alle enthaltenen Tage. Gibt Anzahl Tage zurück."""
    path = _health_json_path()
    if not os.path.exists(path):
        log.warning(f"Health.json nicht gefunden: {path}")
        return 0
    with open(path) as f:
        data = json.load(f)

    days: dict[str, dict] = {}

    def setv(d, field, value):
        days.setdefault(d, {})[field] = value

    for key, (col, fn) in _MAP.items():
        for e in data.get(key, []) or []:
            try:
                setv(e["date"], col, fn(e["value"]))
            except Exception:
                pass

    # Schlaf (Minuten → Stunden) + Stadien
    for e in data.get("sleepTime", []) or []:
        try:
            d = e["date"]
            setv(d, "sleep_duration", _R2(e["value"] / 60))
            st = e.get("stages") or {}
            if st:
                setv(d, "sleep_deep",  _R2(st.get("deep", 0) / 60))
                setv(d, "sleep_rem",   _R2(st.get("rem", 0) / 60))
                setv(d, "sleep_core",  _R2(st.get("core", 0) / 60))
                setv(d, "sleep_awake", _R2(st.get("awake", 0) / 60))
        except Exception:
            pass

    n = 0
    for d, fields in days.items():
        if not fields:
            continue
        cols = list(fields.keys())
        updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols)
        sql = (f"INSERT INTO health_data (date, {', '.join(cols)}, updated_at) "
               f"VALUES (%s, {', '.join(['%s']*len(cols))}, NOW()) "
               f"ON CONFLICT (date) DO UPDATE SET {updates}, updated_at=NOW()")
        db.execute(sql, tuple([d] + [fields[c] for c in cols]))
        n += 1
    log.info(f"🩺 Health-Import: {n} Tage aus iCloud aktualisiert")
    return n


def recent(days: int = 7) -> list[dict]:
    return db.query(
        "SELECT * FROM health_data WHERE date >= CURRENT_DATE - %s ORDER BY date DESC",
        (days,),
    )


def latest() -> dict | None:
    return db.query_one("SELECT * FROM health_data ORDER BY date DESC LIMIT 1")


def history(days: int = 30) -> list[dict]:
    return db.query(
        "SELECT * FROM health_data WHERE date >= CURRENT_DATE - %s ORDER BY date",
        (days,),
    )
