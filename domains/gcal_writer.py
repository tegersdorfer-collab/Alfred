"""
Google Calendar Writer – schreibt Termine via Google Calendar API v3.
OAuth2-Token wird in data/gcal_token.json gespeichert (nie ins Repo!).
Initialer Auth-Flow: python scripts/gcal_auth.py einmalig ausführen.
"""
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import config

log = logging.getLogger(__name__)

_TOKEN_PATH = Path(__file__).parent.parent / "data" / "gcal_token.json"
_TZ = getattr(config, "OWNER_TIMEZONE", "Europe/Berlin")
_SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Lazy-loaded Google API client
_service = None


def _get_service():
    """Gibt Google Calendar Service zurück (lazy + auto-refresh)."""
    global _service
    if _service is not None:
        return _service

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "Google API Pakete fehlen. Bitte ausführen:\n"
            "  pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
        )

    client_id     = getattr(config, "GOOGLE_CLIENT_ID", "")
    client_secret = getattr(config, "GOOGLE_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET fehlen in .env"
        )

    if not _TOKEN_PATH.exists():
        raise RuntimeError(
            f"Google OAuth Token nicht gefunden: {_TOKEN_PATH}\n"
            "Bitte einmalig ausführen: python scripts/gcal_auth.py"
        )

    with open(_TOKEN_PATH) as f:
        token_data = json.load(f)

    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",  # noqa: S106
        client_id=client_id,
        client_secret=client_secret,
        scopes=_SCOPES,
    )

    # Auto-Refresh falls abgelaufen
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds)
            log.info("Google OAuth Token erneuert.")
        except Exception as e:
            log.error(f"Token-Refresh fehlgeschlagen: {e}")
            raise

    _service = build("calendar", "v3", credentials=creds)
    return _service


def _save_token(creds) -> None:
    """Speichert erneuerten Token zurück nach data/gcal_token.json."""
    _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_TOKEN_PATH, "w") as f:
        json.dump({
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
        }, f, indent=2)


def is_available() -> bool:
    """Gibt True zurück wenn Google Calendar konfiguriert und Token vorhanden."""
    client_id     = getattr(config, "GOOGLE_CLIENT_ID", "")
    client_secret = getattr(config, "GOOGLE_CLIENT_SECRET", "")
    return bool(client_id and client_secret and _TOKEN_PATH.exists())


def find_by_title(query: str, days_ahead: int = 60) -> list[dict]:
    """Sucht Google Calendar Events nach Titel (case-insensitive Substring)."""
    try:
        from datetime import datetime, timezone, timedelta
        svc = _get_service()
        now = datetime.now(timezone.utc)
        horizon = (now + timedelta(days=days_ahead)).isoformat()
        result = svc.events().list(
            calendarId=get_calendar_id(),
            timeMin=now.isoformat(),
            timeMax=horizon,
            maxResults=50,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        q = query.lower()
        return [e for e in result.get("items", [])
                if q in e.get("summary", "").lower()]
    except Exception as e:
        log.debug(f"gcal find_by_title: {e}")
        return []


def get_calendar_id() -> str:
    """Primärer Kalender-ID (aus config oder 'primary')."""
    return getattr(config, "GOOGLE_CALENDAR_ID", "primary")


def create_event(
    title: str,
    start: datetime,
    end: datetime = None,
    location: str = None,
    description: str = None,
    all_day: bool = False,
) -> str | None:
    """
    Erstellt einen Termin in Google Calendar.
    Gibt die Google Event-ID zurück oder None bei Fehler.
    """
    try:
        svc = _get_service()
    except Exception as e:
        log.warning(f"Google Calendar nicht verfügbar: {e}")
        return None

    if end is None and not all_day:
        end = start + timedelta(hours=1)

    tz = _TZ

    if all_day:
        body = {
            "summary": title,
            "start": {"date": start.strftime("%Y-%m-%d")},
            "end":   {"date": (end or start + timedelta(days=1)).strftime("%Y-%m-%d")},
        }
    else:
        body = {
            "summary": title,
            "start": {"dateTime": start.isoformat(), "timeZone": tz},
            "end":   {"dateTime": end.isoformat(),   "timeZone": tz},
        }

    if location:
        body["location"] = location
    if description:
        body["description"] = description

    try:
        result = svc.events().insert(
            calendarId=get_calendar_id(), body=body
        ).execute()
        gcal_id = result.get("id")
        log.info(f"Google Calendar Event erstellt: {title!r} → {gcal_id}")
        return gcal_id
    except Exception as e:
        log.error(f"Google Calendar create_event fehlgeschlagen: {e}")
        return None


def update_event(
    gcal_id: str,
    title: str = None,
    start: datetime = None,
    end: datetime = None,
    location: str = None,
    description: str = None,
) -> bool:
    """Aktualisiert einen bestehenden Google Kalender-Termin."""
    try:
        svc = _get_service()
        existing = svc.events().get(
            calendarId=get_calendar_id(), eventId=gcal_id
        ).execute()

        if title:
            existing["summary"] = title
        if location is not None:
            existing["location"] = location
        if description is not None:
            existing["description"] = description
        if start:
            existing["start"] = {"dateTime": start.isoformat(), "timeZone": _TZ}
        if end:
            existing["end"] = {"dateTime": end.isoformat(), "timeZone": _TZ}

        svc.events().update(
            calendarId=get_calendar_id(), eventId=gcal_id, body=existing
        ).execute()
        log.info(f"Google Calendar Event aktualisiert: {gcal_id}")
        return True
    except Exception as e:
        log.error(f"Google Calendar update_event fehlgeschlagen: {e}")
        return False


def delete_event(gcal_id: str) -> bool:
    """Löscht einen Google Kalender-Termin."""
    try:
        svc = _get_service()
        svc.events().delete(
            calendarId=get_calendar_id(), eventId=gcal_id
        ).execute()
        log.info(f"Google Calendar Event gelöscht: {gcal_id}")
        return True
    except Exception as e:
        log.error(f"Google Calendar delete_event fehlgeschlagen: {e}")
        return False
