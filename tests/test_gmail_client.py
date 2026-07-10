"""Tests für den Gmail-Client (domains/gmail_client.py) — ohne echtes Google.

Reine Parse-/Bau-Helfer werden direkt getestet; die API-Funktionen gegen einen
Fake-Service, der die users().messages()...-Kette nachbildet.
"""

import asyncio
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains import gmail_client as gc


# ── Reine Helfer ──────────────────────────────────────────────────────────────

def test_summary_extracts_headers():
    msg = {"id": "m1", "snippet": "Hallo Welt",
           "payload": {"headers": [
               {"name": "From", "value": "Anna <anna@x.de>"},
               {"name": "Subject", "value": "Treffen"},
               {"name": "Date", "value": "Wed, 10 Jul 2026 08:00:00 +0000"}]}}
    s = gc._summary(msg)
    assert s == {"id": "m1", "from": "Anna <anna@x.de>", "subject": "Treffen",
                 "date": "Wed, 10 Jul 2026 08:00:00 +0000", "snippet": "Hallo Welt"}


def test_extract_body_from_parts():
    data = base64.urlsafe_b64encode("Der Text.".encode()).decode()
    payload = {"mimeType": "multipart/alternative", "parts": [
        {"mimeType": "text/html", "body": {"data": base64.urlsafe_b64encode(b"<p>x</p>").decode()}},
        {"mimeType": "text/plain", "body": {"data": data}}]}
    assert gc._extract_body(payload) == "Der Text."


def test_build_raw_roundtrip():
    raw = gc._build_raw("bob@x.de", "Hallo", "Wie geht's?")
    decoded = base64.urlsafe_b64decode(raw.encode()).decode()
    # Header sind Klartext; der Body ist (utf-8) base64-kodiert im MIME.
    assert "To: bob@x.de" in decoded and "Subject: Hallo" in decoded
    import email as _email
    parsed = _email.message_from_string(decoded)
    assert parsed.get_payload(decode=True).decode() == "Wie geht's?"


# ── API-Funktionen gegen Fake-Service ─────────────────────────────────────────

class _Exec:
    def __init__(self, result): self._r = result
    def execute(self): return self._r


class _Messages:
    def __init__(self, store): self.store = store; self.modified = []; self.sent = []
    def list(self, userId, q=None, maxResults=10):
        self.store["last_q"] = q
        return _Exec({"messages": [{"id": i} for i in self.store["ids"]]})
    def get(self, userId, id, format=None, metadataHeaders=None):
        return _Exec(self.store["msgs"][id])
    def modify(self, userId, id, body):
        self.modified.append((id, body)); return _Exec({"id": id})
    def send(self, userId, body):
        self.sent.append(body); return _Exec({"id": "sent1"})


class _Users:
    def __init__(self, msgs): self._m = msgs
    def messages(self): return self._m


class _Service:
    def __init__(self, msgs): self._u = _Users(msgs)
    def users(self): return self._u


# Echte API-Funktionen beim Import sichern — test_email_skill patcht sie global;
# hier stellen wir sie vor jedem Test wieder her (Test-Isolation).
_REAL = {n: getattr(gc, n) for n in ("list_unread", "search", "get_message",
                                     "mark_read", "archive", "send")}


def _fake(ids, msgs):
    for n, f in _REAL.items():
        setattr(gc, n, f)
    store = {"ids": ids, "msgs": msgs}
    m = _Messages(store)
    gc._get_service = lambda: _Service(m)
    return m


def _hdr(frm, subj):
    return {"payload": {"headers": [{"name": "From", "value": frm}, {"name": "Subject", "value": subj},
                                     {"name": "Date", "value": "d"}]}, "snippet": "…"}


def test_list_unread():
    m = _fake(["a", "b"], {"a": {"id": "a", **_hdr("x@x.de", "Eins")},
                            "b": {"id": "b", **_hdr("y@y.de", "Zwei")}})
    out = asyncio.run(gc.list_unread(5))
    assert [o["subject"] for o in out] == ["Eins", "Zwei"]
    assert m.store["last_q"] == "is:unread"


def test_mark_read_and_archive():
    m = _fake(["a"], {"a": {"id": "a", **_hdr("x", "y")}})
    asyncio.run(gc.mark_read("a"))
    asyncio.run(gc.archive("a"))
    assert m.modified[0] == ("a", {"removeLabelIds": ["UNREAD"]})
    assert m.modified[1] == ("a", {"removeLabelIds": ["INBOX"]})


def test_send_builds_and_sends():
    m = _fake([], {})
    asyncio.run(gc.send("bob@x.de", "Hi", "Text"))
    assert "raw" in m.sent[0]
    decoded = base64.urlsafe_b64decode(m.sent[0]["raw"].encode()).decode()
    assert "To: bob@x.de" in decoded
