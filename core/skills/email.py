"""Email-Tools (Gmail) für den Agenten — lesen, verwalten, senden.

Nutzt domains/gmail_client (OAuth-Spiegel von gcal). Ohne Einrichtung
(is_available False) geben alle Tools eine Setup-Meldung zurück.

SICHERHEIT beim Senden: email_send zeigt zuerst NUR den Entwurf und sendet erst,
wenn Timo ausdrücklich mit confirm=true bestätigt — nie automatisch.
"""
import logging

from core import tools as T
from domains import gmail_client

log = logging.getLogger("core.skills")

_SETUP = ("📭 Gmail ist noch nicht eingerichtet. In der Google Cloud Console die Gmail-API "
          "aktivieren, dann einmalig `python scripts/gmail_auth.py` ausführen "
          "(GOOGLE_CLIENT_ID/SECRET aus der .env werden wiederverwendet).")


def _fmt_list(items: list[dict]) -> str:
    if not items:
        return "📭 Keine passenden Mails."
    lines = [f"• [{it['id']}] {it['from']} — {it['subject']}"
             + (f" · {it['snippet'][:60]}" if it.get("snippet") else "")
             for it in items]
    return "\n".join(lines)


@T.register(
    "email_unread", "Zeigt ungelesene Gmail-Mails (Absender, Betreff, Vorschau).",
    {}, [], "email",
)
async def _email_unread():
    if not gmail_client.is_available():
        return _SETUP
    try:
        return "📬 Ungelesen:\n" + _fmt_list(await gmail_client.list_unread(10))
    except Exception as e:
        log.warning("email_unread: %s", e)
        return f"❌ Gmail-Fehler: {e}"


@T.register(
    "email_search", "Durchsucht Gmail (Gmail-Suchsyntax, z.B. 'from:chef betreff').",
    {"query": {"type": "string", "description": "Gmail-Suchanfrage"}}, ["query"], "email",
)
async def _email_search(query: str):
    if not gmail_client.is_available():
        return _SETUP
    try:
        return f"🔎 Treffer zu ‚{query}':\n" + _fmt_list(await gmail_client.search(query, 10))
    except Exception as e:
        return f"❌ Gmail-Fehler: {e}"


@T.register(
    "email_read", "Liest eine Mail im Volltext (per id aus email_unread/email_search).",
    {"id": {"type": "string", "description": "Message-ID"}}, ["id"], "email",
)
async def _email_read(id: str):
    if not gmail_client.is_available():
        return _SETUP
    try:
        m = await gmail_client.get_message(id)
    except Exception as e:
        return f"❌ Gmail-Fehler: {e}"
    return (f"✉️ Von: {m['from']}\nBetreff: {m['subject']}\nDatum: {m['date']}\n\n"
            f"{m.get('body', '')[:2000]}")


@T.register(
    "email_mark_read", "Markiert eine Mail als gelesen.",
    {"id": {"type": "string", "description": "Message-ID"}}, ["id"], "email",
)
async def _email_mark_read(id: str):
    if not gmail_client.is_available():
        return _SETUP
    try:
        await gmail_client.mark_read(id)
        return "✓ Als gelesen markiert."
    except Exception as e:
        return f"❌ Gmail-Fehler: {e}"


@T.register(
    "email_archive", "Archiviert eine Mail (aus dem Posteingang entfernen).",
    {"id": {"type": "string", "description": "Message-ID"}}, ["id"], "email",
)
async def _email_archive(id: str):
    if not gmail_client.is_available():
        return _SETUP
    try:
        await gmail_client.archive(id)
        return "🗄️ Archiviert."
    except Exception as e:
        return f"❌ Gmail-Fehler: {e}"


@T.register(
    "email_send",
    "Sendet eine E-Mail — ABER: rufe dies IMMER zuerst OHNE confirm auf, zeig Timo den "
    "Entwurf, und sende erst mit confirm=true, NACHDEM Timo ausdrücklich zugestimmt hat. "
    "Niemals unaufgefordert mit confirm=true senden.",
    {
        "to": {"type": "string", "description": "Empfänger-Adresse"},
        "subject": {"type": "string", "description": "Betreff"},
        "body": {"type": "string", "description": "Nachrichtentext"},
        "confirm": {"type": "boolean", "description": "true = wirklich senden (erst nach Timos OK)"},
    },
    ["to", "subject", "body"], "email",
)
async def _email_send(to: str, subject: str, body: str, confirm: bool = False):
    if not gmail_client.is_available():
        return _SETUP
    if not (to or "").strip() or not (subject or "").strip():
        return "❌ Empfänger und Betreff sind nötig."
    if not confirm:
        return (f"📝 Entwurf (noch NICHT gesendet):\nAn: {to}\nBetreff: {subject}\n\n{body}\n\n"
                f"→ Soll ich das so senden? Dann bestätige, ich sende dann mit confirm=true.")
    try:
        await gmail_client.send(to, subject, body)
    except Exception as e:
        log.warning("email_send: %s", e)
        return f"❌ Senden fehlgeschlagen: {e}"
    return f"✅ Gesendet an {to}."
