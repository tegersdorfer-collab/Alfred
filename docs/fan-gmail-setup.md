# Ventilator-IR + Gmail — Setup (wenn du so weit bist)

Beides ist gebaut und getestet; es fehlen nur deine Daten. Bis dahin geben beide
Features eine freundliche „noch nicht eingerichtet"-Meldung.

## Ventilator (Flipper-IR)

1. Fernbedienung des Ventilators per Flipper aufnehmen (`ir rx`), je Taste den Code notieren.
2. In `tools/flipper/remotes.json` unter `"ventilator"` die vier Signale füllen
   (`protocol`, `address`, `command`) und `"learned": true` setzen. Beispiel wie bei
   `schreibtischlampe`.
3. Fertig — kein Code-Change. Es funktioniert sofort:
   - Sprache/Chat: „ventilator an/aus", „ventilator stärker/schwächer" (Fast-Path, ohne LLM).
   - Tool `ventilator` (action = an/aus/staerker/schwaecher, optional `schritte`).

## Gmail

1. **Google Cloud Console** (dasselbe Projekt wie beim Kalender): **Gmail API aktivieren**.
   `GOOGLE_CLIENT_ID`/`SECRET` aus deiner `.env` werden wiederverwendet.
2. Einmalig: `cd ~/Mantis && python3 scripts/gmail_auth.py` → Browser-Login, Gmail-Rechte
   (lesen/verwalten/senden) bestätigen. Schreibt `data/gmail_token.json` (gitignored).
3. Mantis neu starten (`./start.sh`). Dann live:
   - Lesen: „hab ich neue mails?" (Fast-Path → `email_unread`), `email_search`, `email_read`.
   - Verwalten: `email_mark_read`, `email_archive`.
   - **Senden — mit Freigabe**: `email_send` zeigt IMMER zuerst den Entwurf; gesendet wird
     nur, wenn du zustimmst (dann ruft der Agent es mit `confirm=true`). Nie automatisch.

## Was schon verifiziert ist

- Ventilator: Tool + Fast-Paths + „nicht angelernt"-Pfad, Tests grün, live degradiert sauber.
- Gmail: Client (list/search/read/manage/send) + Entwurf-Gate + Auth-Skript, Tests grün,
  live degradiert sauber (Setup-Meldung, keine Fehler). 760+ Tests grün, CI grün.
- Beide Lese-/Schalt-Intents routen deterministisch (Fast-Path), damit das kleine Modell
  nichts erfindet.

## Sicherheitshinweis (Senden)

Der Sende-Weg ist strukturell auf „Entwurf → deine Freigabe" ausgelegt. Der Agent ist
angewiesen, `email_send` nie unaufgefordert mit `confirm=true` zu rufen. Prüf im Zweifel
den Entwurf, bevor du zustimmst.
