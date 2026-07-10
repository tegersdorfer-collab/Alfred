"""Gmail-Client — spiegelt die Google-Calendar-OAuth (domains/gcal_writer.py).

OAuth2-Token in data/gmail_token.json (nie ins Repo). Scope: gmail.modify + gmail.send
(lesen/verwalten/senden). Initialer Flow: `python scripts/gmail_auth.py`.

Die API-Funktionen sind dünn; die einzige Live-Grenze ist _get_service() (in Tests
gemockt). Reine Parse-/Bau-Helfer (_summary/_extract_body/_build_raw) sind separat testbar.
"""
import base64
import json
import logging
from email.mime.text import MIMEText
from pathlib import Path

import config

log = logging.getLogger(__name__)

_TOKEN_PATH = Path(__file__).parent.parent / "data" / "gmail_token.json"
_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

_service = None


def is_available() -> bool:
    client_id = getattr(config, "GOOGLE_CLIENT_ID", "")
    client_secret = getattr(config, "GOOGLE_CLIENT_SECRET", "")
    return bool(client_id and client_secret and _TOKEN_PATH.exists())


def _get_service():  # pragma: no cover - live-only
    """Lazy Gmail-Service mit Auto-Refresh (Muster wie gcal_writer)."""
    global _service
    if _service is not None:
        return _service
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "Google-API-Pakete fehlen: pip install google-api-python-client "
            "google-auth-oauthlib google-auth-httplib2")

    client_id = getattr(config, "GOOGLE_CLIENT_ID", "")
    client_secret = getattr(config, "GOOGLE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise RuntimeError("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET fehlen in .env")
    if not _TOKEN_PATH.exists():
        raise RuntimeError(f"Gmail-Token fehlt ({_TOKEN_PATH}). Einmalig: "
                           "python scripts/gmail_auth.py")

    with open(_TOKEN_PATH) as f:
        td = json.load(f)
    creds = Credentials(
        token=td.get("token"), refresh_token=td.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",  # noqa: S106
        client_id=client_id, client_secret=client_secret, scopes=_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token(creds)
    _service = build("gmail", "v1", credentials=creds)
    return _service


def _save_token(creds) -> None:  # pragma: no cover - live-only
    _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_TOKEN_PATH, "w") as f:
        json.dump({"token": creds.token, "refresh_token": creds.refresh_token,
                   "expiry": creds.expiry.isoformat() if creds.expiry else None}, f, indent=2)


# ── Reine Helfer ──────────────────────────────────────────────────────────────

def _headers(msg: dict) -> dict:
    return {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}


def _summary(msg: dict) -> dict:
    h = _headers(msg)
    return {"id": msg.get("id", ""), "from": h.get("from", ""), "subject": h.get("subject", ""),
            "date": h.get("date", ""), "snippet": msg.get("snippet", "")}


def _decode(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data.encode()).decode("utf-8", "ignore")
    except Exception:
        return ""


def _find_mime(payload: dict, want: str) -> str:
    """Rekursiv das erste Body-Data-Feld finden, dessen mimeType mit `want`
    beginnt (want='' = beliebig)."""
    mt = payload.get("mimeType", "")
    data = payload.get("body", {}).get("data")
    if data and (not want or mt.startswith(want)):
        return _decode(data)
    for part in payload.get("parts", []) or []:
        found = _find_mime(part, want)
        if found:
            return found
    return ""


def _extract_body(payload: dict) -> str:
    # Erst text/plain bevorzugen, sonst irgendeinen Text-Body (Fallback NUR global,
    # nicht mitten in der Rekursion — sonst gewinnt versehentlich die HTML-Variante).
    return _find_mime(payload, "text/plain") or _find_mime(payload, "")


def _build_raw(to: str, subject: str, body: str) -> str:
    msg = MIMEText(body, _charset="utf-8")
    msg["To"] = to
    msg["Subject"] = subject
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


# ── API-Funktionen (dünn; _get_service in Tests gemockt) ──────────────────────

async def _list(query: str, max_n: int) -> list[dict]:
    svc = _get_service()
    resp = svc.users().messages().list(userId="me", q=query, maxResults=max_n).execute()
    out = []
    for m in resp.get("messages", []):
        full = svc.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]).execute()
        out.append(_summary(full))
    return out


async def list_unread(max_n: int = 10) -> list[dict]:
    return await _list("is:unread", max_n)


async def search(query: str, max_n: int = 10) -> list[dict]:
    return await _list(query, max_n)


async def get_message(msg_id: str) -> dict:
    svc = _get_service()
    full = svc.users().messages().get(userId="me", id=msg_id, format="full").execute()
    out = _summary(full)
    out["body"] = _extract_body(full.get("payload", {}))
    return out


async def mark_read(msg_id: str) -> None:
    svc = _get_service()
    svc.users().messages().modify(userId="me", id=msg_id,
                                  body={"removeLabelIds": ["UNREAD"]}).execute()


async def archive(msg_id: str) -> None:
    svc = _get_service()
    svc.users().messages().modify(userId="me", id=msg_id,
                                  body={"removeLabelIds": ["INBOX"]}).execute()


async def send(to: str, subject: str, body: str) -> dict:
    svc = _get_service()
    return svc.users().messages().send(
        userId="me", body={"raw": _build_raw(to, subject, body)}).execute()
