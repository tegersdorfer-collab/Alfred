"""Tests für die Email-Skill-Tools (core/skills/email.py) — Gmail-Client gemockt.

Fokus: Formatierung, der Entwurf-vs-Senden-Gate (confirm), und dass ohne
Einrichtung (is_available False) sauber eine Setup-Meldung kommt statt eines Fehlers.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains import gmail_client
from core.skills import email as emailskill


def _available(yes=True):
    gmail_client.is_available = lambda: yes


def test_unavailable_gives_setup():
    _available(False)
    out = asyncio.run(emailskill._email_unread())
    assert "gmail_auth" in out.lower() or "eingerichtet" in out.lower()


def test_unread_lists():
    _available(True)
    async def fake(max_n=10):
        return [{"id": "1", "from": "Anna <a@x.de>", "subject": "Treffen", "date": "d", "snippet": "hi"}]
    gmail_client.list_unread = fake
    out = asyncio.run(emailskill._email_unread())
    assert "Treffen" in out and "Anna" in out


def test_read_shows_body():
    _available(True)
    async def fake(mid):
        return {"id": mid, "from": "a@x.de", "subject": "Betreff", "date": "d", "body": "Der Inhalt."}
    gmail_client.get_message = fake
    out = asyncio.run(emailskill._email_read("1"))
    assert "Betreff" in out and "Der Inhalt." in out


def test_send_draft_gate_blocks_without_confirm():
    _available(True)
    sent = []
    async def fake_send(to, subject, body):
        sent.append((to, subject, body))
    gmail_client.send = fake_send
    out = asyncio.run(emailskill._email_send("bob@x.de", "Hi", "Text"))   # kein confirm
    assert sent == []                       # NICHT gesendet
    assert "entwurf" in out.lower() and "confirm" in out.lower()


def test_send_with_confirm_sends():
    _available(True)
    sent = []
    async def fake_send(to, subject, body):
        sent.append((to, subject, body))
    gmail_client.send = fake_send
    out = asyncio.run(emailskill._email_send("bob@x.de", "Hi", "Text", confirm=True))
    assert sent == [("bob@x.de", "Hi", "Text")]
    assert "✅" in out or "gesendet" in out.lower()


def test_mark_read_and_archive():
    _available(True)
    calls = []
    async def fr(mid): calls.append(("read", mid))
    async def fa(mid): calls.append(("arch", mid))
    gmail_client.mark_read = fr
    gmail_client.archive = fa
    asyncio.run(emailskill._email_mark_read("7"))
    asyncio.run(emailskill._email_archive("7"))
    assert calls == [("read", "7"), ("arch", "7")]
