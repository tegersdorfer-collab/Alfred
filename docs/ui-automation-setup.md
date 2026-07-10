# UI-Automatik & Spicetify-Bridge — Setup + Live-Smoke-Test

Beides ist gebaut und per Tests abgesichert. Zwei Schritte fehlen, die nur du am
Mac machen kannst. Danach je ein kurzer Smoke-Test.

## 1. Bedienungshilfen-Recht für Mantis (für `computer_task`)

Der Mantis-Prozess braucht das „Bedienungshilfen"-Recht, um Apps zu bedienen.

1. Systemeinstellungen → **Datenschutz & Sicherheit → Bedienungshilfen**.
2. Den Python-Interpreter hinzufügen/aktivieren:
   `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14`
   (Mit „+" hinzufügen, zum Pfad navigieren — ⇧⌘G und Pfad einfügen.)
3. Mantis neu starten: `cd ~/Mantis && ./start.sh`.

**Smoke-Test (read-only, ungefährlich):**
```bash
cd ~/Mantis && python3.14 -c "
from tools.uiauto import engine
print('trusted:', engine.is_trusted())
snap = engine.snapshot('Notizen')   # oder eine offene App
print(len(snap), 'Elemente'); [print(e['ref'], e['role'], e['title'][:30]) for e in snap[:8]]
"
```
Erwartung: `trusted: True` und eine Liste bedienbarer Elemente.

**Dann echt über Mantis** (bringt die App in den Vordergrund, klickt real):
```bash
curl -s -X POST http://127.0.0.1:7779/api/chat -H "Content-Type: application/json" \
  -d '{"text":"bediene die app notizen und erstelle eine neue notiz mit dem titel test"}'
```
Der qwen-Loop inspiziert, klickt, tippt. Destruktive Elemente (Löschen/Senden/
Kaufen/Passwortfelder) verweigert Mantis hart — das ist gewollt.

> Hinweis: Der Loop läuft auf qwen3.5:9b und ist beim ersten echten Einsatz evtl.
> tuning-bedürftig (Element-Wahl, Schrittzahl). Genau dafür ist dieser erste
> Live-Lauf da — beobachte das Dashboard-Log (`grep computer_task /tmp/mantis_out.log`).

## 2. Spicetify-Bridge (strukturierte Spotify-Suche ohne Developer-Key)

```bash
cp ~/Mantis/tools/spotify/spicetify_ext/mantis-bridge.js ~/.config/spicetify/Extensions/
spicetify config extensions mantis-bridge.js
spicetify apply     # startet Spotify neu
```

**Smoke-Test:** Nach `spicetify apply` Spotify offen lassen, dann:
```bash
grep "Spicetify-Bridge verbunden" /tmp/mantis_out.log   # Extension hat sich verbunden?
curl -s -X POST http://127.0.0.1:7779/api/chat -H "Content-Type: application/json" \
  -d '{"text":"spiel bohemian rhapsody"}'
```
Erwartung: strukturierte Suche über die Bridge (kein SPOTIFY_CLIENT_ID nötig),
dann Wiedergabe. Läuft die Bridge nicht, fällt der spotify-Skill automatisch auf
den bisherigen AppleScript/Web-API-Weg zurück — nichts geht kaputt.

## Was schon (autonom) verifiziert ist

- Engine-**Lese**-Pfad live gegen die echte Accessibility-API (182 Elemente aus
  einer realen App gelesen, Rollen/refs korrekt).
- Safety-Schicht (rote Linien), Ref-Zuordnung, Fallbacks, WS-Routen-Einbindung,
  Spotify-Bridge-Bevorzugung: 718 Tests grün, ruff sauber, Mantis bootet mit den
  neuen Tools (78 gesamt).

## Was auf dich wartet (nicht ohne dich verifizierbar)

- Recht vergeben (oben) → **Schreib**-Pfad (klicken/tippen) live.
- Spicetify-Extension installieren → Bridge-Handshake live.
