"""
Kalender-Domäne (jarvis-nativ).
Quelle: Google/iCloud ICS-Abo-URL(s) – direkt gefetcht & geparst mit korrekter
Zeitzone. Plus jarvis-eigene Events aus calendar_events. KEINE ai-dashboard-Abhängigkeit.
Synchron (mit Cache) damit alle bestehenden Aufrufstellen es nutzen können.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from icalendar import Calendar as ICal

from core import db
import config

log = logging.getLogger(__name__)

_TZ = ZoneInfo(getattr(config, "OWNER_TIMEZONE", "Europe/Berlin"))
_cache: dict = {"ts": None, "events": []}
_CACHE_TTL = 600  # 10 Min


def _to_local(dt) -> tuple[datetime, bool]:
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_TZ).replace(tzinfo=None), False
    return datetime(dt.year, dt.month, dt.day), True   # reines date → ganztags


def _fetch_ics(days_ahead: int = 60) -> list[dict]:
    urls = [u.strip() for u in (config.CALENDAR_ICS_URLS or "").split(",") if u.strip()]
    if not urls:
        return []
    horizon = datetime.now() + timedelta(days=days_ahead)
    past = datetime.now() - timedelta(days=1)
    out = []
    with httpx.Client(timeout=15, follow_redirects=True) as client:
        for url in urls:
            try:
                r = client.get(url)
                cal = ICal.from_ical(r.text)
            except Exception as e:
                log.warning(f"ICS-Fetch fehlgeschlagen: {e}")
                continue
            for comp in cal.walk("VEVENT"):
                try:
                    start, all_day = _to_local(comp.get("dtstart").dt)
                    if start < past or start > horizon:
                        continue
                    end = None
                    if comp.get("dtend"):
                        end, _ = _to_local(comp.get("dtend").dt)
                    out.append({
                        "title": str(comp.get("summary", "")),
                        "start": start, "end": end, "all_day": all_day,
                        "location": str(comp.get("location", "")) or None,
                        "calendar": "iCloud", "source": "ics",
                    })
                except Exception:
                    continue
    return out


def upcoming(days: int = 7) -> list[dict]:
    now = datetime.now()
    if _cache["ts"] and (now - _cache["ts"]).total_seconds() < _CACHE_TTL:
        ics = _cache["events"]
    else:
        ics = _fetch_ics()
        _cache["ts"] = now
        _cache["events"] = ics

    horizon = now + timedelta(days=days)
    events = [e for e in ics if e["start"] >= now - timedelta(hours=12) and e["start"] <= horizon]

    try:
        rows = db.query(
            "SELECT title, start_ts, end_ts, all_day, location FROM calendar_events "
            "WHERE start_ts >= %s AND start_ts <= %s",
            (now - timedelta(hours=12), horizon),
        )
        for r in rows:
            s = r["start_ts"]
            if getattr(s, "tzinfo", None):
                s = s.astimezone(_TZ).replace(tzinfo=None)
            events.append({"title": r["title"], "start": s, "end": r["end_ts"],
                           "all_day": r["all_day"], "location": r["location"],
                           "calendar": "Jarvis", "source": "jarvis"})
    except Exception as e:
        log.debug(f"Jarvis-Events: {e}")

    events.sort(key=lambda e: e["start"])
    return events[:25]


def create_event(title: str, start: datetime, end: datetime = None,
                 location: str = None, notes: str = None, all_day: bool = False) -> str:
    uid = f"jarvis-{uuid.uuid4()}"
    if end is None and not all_day:
        end = start + timedelta(hours=1)
    db.execute(
        "INSERT INTO calendar_events (uid, title, start_ts, end_ts, all_day, location, notes) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (uid, title, start, end, all_day, location, notes),
    )
    return uid
