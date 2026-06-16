"""
Kalender-Domäne (alfred-nativ).
Quelle: Google/iCloud ICS-Abo-URL(s) – direkt gefetcht & geparst mit korrekter
Zeitzone. Plus alfred-eigene Events aus calendar_events. KEINE ai-dashboard-Abhängigkeit.
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
from domains import gcal_writer

log = logging.getLogger(__name__)

_TZ = ZoneInfo(getattr(config, "OWNER_TIMEZONE", "Europe/Berlin"))
_cache: dict = {"ts": None, "events": []}


def invalidate_cache() -> None:
    """Cache manuell invalidieren (z.B. nach Neustart oder Zeitkorrektur)."""
    _cache["ts"] = None
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
    # Ganztags-Events: ab Tagesbeginn; Uhrzeittermine: ab jetzt minus 30min (laufende Termine)
    cutoff = now - timedelta(minutes=30)
    events = [e for e in ics if e["start"] >= cutoff and e["start"] <= horizon]

    alfred_events = []
    try:
        rows = db.query(
            "SELECT uid, title, start_ts, end_ts, all_day, location FROM calendar_events "
            "WHERE start_ts >= %s AND start_ts <= %s",
            (cutoff, horizon),
        )
        for r in rows:
            s = r["start_ts"]
            if getattr(s, "tzinfo", None):
                s = s.astimezone(_TZ).replace(tzinfo=None)
            alfred_events.append({"uid": r["uid"], "title": r["title"], "start": s,
                                  "end": r["end_ts"], "all_day": r["all_day"],
                                  "location": r["location"],
                                  "calendar": "Alfred", "source": "alfred"})
    except Exception as e:
        log.debug(f"Alfred-Events: {e}")

    # ICS-Duplikate entfernen: Alfred-Events die via Google Cal zurücksynchronisiert wurden
    def _is_duplicate(ics_ev: dict) -> bool:
        t = ics_ev["start"]
        title_lower = ics_ev["title"].lower()
        for je in alfred_events:
            if je["title"].lower() == title_lower:
                diff = abs((je["start"] - t).total_seconds())
                if diff < 300:  # gleicher Titel + max 5min Abweichung
                    return True
        return False

    events = [e for e in events if not _is_duplicate(e)]
    events += alfred_events
    events.sort(key=lambda e: e["start"])
    return events[:25]


def find_event(query: str) -> dict | None:
    """Findet einen Event per Titelsuche – zuerst in Alfred-DB, dann Google Calendar."""
    rows = db.query(
        "SELECT uid, title, start_ts, end_ts, all_day, location, gcal_id "
        "FROM calendar_events WHERE LOWER(title) LIKE %s ORDER BY start_ts LIMIT 1",
        (f"%{query.lower()}%",),
    )
    if rows:
        return rows[0]
    # Fallback: Google Calendar direkt durchsuchen
    if gcal_writer.is_available():
        gcal_hits = gcal_writer.find_by_title(query)
        if gcal_hits:
            e = gcal_hits[0]
            return {"uid": None, "gcal_id": e["id"], "title": e.get("summary", ""),
                    "source": "gcal"}
    return None


def update_event(uid: str | None, title: str = None, start: datetime = None,
                 end: datetime = None, location: str = None, notes: str = None,
                 gcal_id: str | None = None) -> bool:
    """Aktualisiert einen Alfred-Event (DB + Google Calendar)."""
    if not uid:
        # Termin existiert nur in Google Calendar, nicht in der Alfred-DB
        if gcal_id and gcal_writer.is_available():
            return bool(gcal_writer.update_event(
                gcal_id, title=title, start=start, end=end,
                location=location, description=notes,
            ))
        return False

    fields, vals = [], []
    if title:    fields.append("title = %s");    vals.append(title)
    if start:    fields.append("start_ts = %s"); vals.append(start)
    if end:      fields.append("end_ts = %s");   vals.append(end)
    if location is not None: fields.append("location = %s"); vals.append(location)
    if notes is not None:    fields.append("notes = %s");    vals.append(notes)
    if not fields:
        return False
    vals.append(uid)
    db.execute(f"UPDATE calendar_events SET {', '.join(fields)} WHERE uid = %s", vals)

    # Google Calendar sync
    rows = db.query("SELECT gcal_id FROM calendar_events WHERE uid = %s", (uid,))
    if rows and rows[0].get("gcal_id") and gcal_writer.is_available():
        gcal_writer.update_event(rows[0]["gcal_id"], title=title, start=start,
                                 end=end, location=location, description=notes)
    invalidate_cache()
    return True


def delete_event(uid: str | None, gcal_id: str | None = None) -> bool:
    """Löscht einen Event aus DB und/oder Google Calendar."""
    if uid:
        rows = db.query("SELECT gcal_id FROM calendar_events WHERE uid = %s", (uid,))
        if rows and rows[0].get("gcal_id"):
            gcal_id = gcal_id or rows[0]["gcal_id"]
        db.execute("DELETE FROM calendar_events WHERE uid = %s", (uid,))
    if gcal_id and gcal_writer.is_available():
        gcal_writer.delete_event(gcal_id)
    invalidate_cache()
    return True


def create_event(title: str, start: datetime, end: datetime = None,
                 location: str = None, notes: str = None, all_day: bool = False) -> str:
    uid = f"alfred-{uuid.uuid4()}"
    if end is None and not all_day:
        end = start + timedelta(hours=1)

    # In Alfred-DB speichern (immer)
    db.execute(
        "INSERT INTO calendar_events (uid, title, start_ts, end_ts, all_day, location, notes) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (uid, title, start, end, all_day, location, notes),
    )

    # Zusätzlich nach Google Calendar pushen (wenn konfiguriert)
    if gcal_writer.is_available():
        gcal_id = gcal_writer.create_event(
            title=title, start=start, end=end,
            location=location, description=notes, all_day=all_day,
        )
        if gcal_id:
            # Google Event-ID im Datensatz speichern für spätere Updates/Löschungen
            try:
                db.execute(
                    "UPDATE calendar_events SET gcal_id = %s WHERE uid = %s",
                    (gcal_id, uid),
                )
            except Exception:
                pass  # Spalte existiert noch nicht – Migration läuft separat
        invalidate_cache()

    return uid
