"""
Geteilte Serialisierungs-Helfer für die API-Router.
Aus web/api.py extrahiert, damit alle Router-Module sie teilen können.
"""
from datetime import date, datetime

from fastapi import Request


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


def _event_dict(e):
    return {"title": e.title,
            "start": e.start.strftime("%d.%m. %H:%M") if not e.all_day else e.start.strftime("%d.%m."),
            "start_iso": e.start.isoformat(), "all_day": e.all_day,
            "calendar": e.calendar, "location": e.location,
            "uid": getattr(e, "uid", None), "source": getattr(e, "source", None)}
