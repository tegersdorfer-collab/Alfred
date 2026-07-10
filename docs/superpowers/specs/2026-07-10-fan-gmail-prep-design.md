# Ventilator-IR + Gmail-Anbindung (Vorbereitung) — Design

**Datum:** 2026-07-10 · **Status:** vom User freigegeben. Beides ist **Scaffolding**:
der User liefert später die konkreten Daten (IR-Codes bzw. OAuth-Token). Alles muss
ohne diese Daten sauber degradieren (klare „noch nicht eingerichtet"-Meldungen).

Zwei unabhängige Features, ein gemeinsamer Branch:

---

## Feature 1 — Ventilator per Flipper-IR

Direkter Klon des bestehenden Lampen-Musters (`tools/flipper/`, `core/skills/flipper.py`).

**`tools/flipper/remotes.json`** — neuer Eintrag `ventilator` mit **Platzhalter-Signalen**:
```
"ventilator": {
  "label": "Ventilator",
  "note": "Codes noch NICHT angelernt — per Flipper 'ir rx' aufnehmen und command füllen.",
  "learned": false,
  "signals": {
    "an": {"protocol": "", "address": "", "command": ""},
    "aus": {"protocol": "", "address": "", "command": ""},
    "staerker": {"protocol": "", "address": "", "command": ""},
    "schwaecher": {"protocol": "", "address": "", "command": ""}
  }
}
```

**`core/skills/ventilator.py`** — Tool `ventilator`:
- `action`-Enum: `an`, `aus`, `staerker`, `schwaecher`; optional `schritte` (nur staerker/
  schwaecher, wie „heller/dunkler" bei der Lampe, 1–10).
- Alias-Normalisierung (an/ein/anmachen; aus/ausmachen; stärker/schneller/hoch; schwächer/
  langsamer/runter).
- Prüft `learned`-Flag bzw. leere `command` → freundliche Meldung „Ventilator-IR noch nicht
  angelernt — Codes in remotes.json eintragen." Sonst `MANAGER.send_named("ventilator", sig)`.

**`core/fast_commands.py`** — Fast-Paths (wie Lampe): „ventilator an/aus", „ventilator stärker/
schwächer". Greifen erst, wenn Codes hinterlegt sind (sonst kommt die „nicht angelernt"-Meldung).

**Tests:** tx gemockt (wie `test_flipper.py`). Geprüft: Alias→Signal, schritte-Wiederholung
(mit gepatchtem gelerntem Remote), „nicht angelernt"-Pfad, Fast-Path-Regeln (+ Negativfälle).

**User später:** IR-Codes per Flipper aufnehmen, in `remotes.json` eintragen, `learned: true`.

---

## Feature 2 — Gmail-Anbindung

Spiegelt die bestehende Google-Calendar-OAuth (`domains/gcal_writer.py`, `scripts/gcal_auth.py`).
Scope **gmail.modify + gmail.send** (lesen/verwalten/senden).

**`domains/gmail_client.py`** — OAuth + Gmail-API (google-api-python-client, bereits Dependency):
- `_get_service()` lazy, `build("gmail","v1",creds)`, Token `data/gmail_token.json`,
  Auto-Refresh (Muster wie gcal_writer). `is_available()`.
- Funktionen: `list_unread(max_n)`, `search(query, max_n)`, `get_message(id)`,
  `mark_read(id)`, `archive(id)`, `send(to, subject, body)`. Alle wrappen die Gmail-API.
- Test-Seam: `_get_service()` liefert in Tests einen Fake-Service.

**`scripts/gmail_auth.py`** — einmaliger OAuth-Flow (Muster gcal_auth), Gmail-Scopes, Port 8082,
schreibt `data/gmail_token.json`.

**`core/skills/email.py`** — Agent-Tools (Kategorie `email`):
- `email_unread()` — ungelesene zusammenfassen (Absender · Betreff · Datum).
- `email_search(query)` — Gmail-Suchsyntax.
- `email_read(id)` — Volltext einer Mail.
- `email_mark_read(id)`, `email_archive(id)` — Verwalten.
- `email_send(to, subject, body, confirm=false)` — **Sicherheit**: bei `confirm=false`
  liefert es NUR eine Entwurfs-Vorschau (an/Betreff/Text) und sendet NICHT; nur bei
  explizitem `confirm=true` wird gesendet. Nie automatisch aus fremdem Inhalt heraus.
- Ohne Token/Config → alle Tools geben die Setup-Meldung („`python scripts/gmail_auth.py`") zurück.

**Registrierung:** Import in `core/skills/__init__.py`, Kategorie-Keywords `email` in
`core/tools.py` (mail, email, posteingang, ungelesen, schreib eine mail, …).

**Tests:** `_get_service` gemockt (Fake mit users().messages()…-Kette); jede Tool-Formatierung,
der Entwurf-vs-Senden-Gate, und der „nicht eingerichtet"-Pfad (`is_available()` False).

**User später:** In der Google Cloud Console die **Gmail API aktivieren**, dann einmalig
`python scripts/gmail_auth.py` (neuer Scope → eigenes Token, unabhängig vom Calendar-Token).

---

## Globale Randbedingungen

- Python 3.14, Tests `pytest -q`, Lint `ruff (F,E9)`, Deutsch + Emoji-Stil.
- Keine neuen Dependencies (google-api-python-client bereits da; Flipper vorhanden).
- Beide Features degradieren ohne User-Daten sauber; Mantis-Start nie gefährdet.
- `data/gmail_token.json` ist Secret → gitignored (data/ ist es bereits).
- Senden strukturell gated (Entwurf → confirm). Deckt sich mit der Grundregel „keine
  irreversible Aktion (Senden) ohne ausdrückliche Freigabe".
- Commits `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## Nicht in dieser Scheibe
- Echte IR-Codes / echter OAuth-Flow (liefert der User).
- Anhänge, HTML-Mails, Threads-Ansicht (später bei Bedarf).
- Push/Benachrichtigung bei neuer Mail (später).
