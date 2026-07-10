# UI-Automatisierung für Mantis — Design

**Datum:** 2026-07-10 · **Status:** Richtung vom User freigegeben („lass uns beide Wege gehen"), User währenddessen nicht am PC → autonom bauen bis Tests grün; Live-Verifikation + Rechtevergabe wartet auf Rückkehr.

## Ziel

Mantis kann macOS-Apps bedienen, indem es — bevorzugt über **strukturierte Elemente** — deren Oberfläche inspiziert und darauf klickt/tippt. Zwei komplementäre Wege:

1. **Generelle UI-Automatik** über die Accessibility-API (OSS-Engine **atomacos**), inklusive „Aufwecken" des Accessibility-Baums bei Electron-Apps via `AXManualAccessibility`. Deckt native Apps + die meisten Electron-Apps strukturiert ab.
2. **Spicetify-Bridge** für Spotify (dessen AX-Baum bleibt zu): eine Spicetify-Extension exponiert Spotifys interne, *strukturierte* APIs (`GraphQL`-Suche, `Player`, `Platform`) über einen lokalen Kanal an Mantis.

Vision (Screenshot + qwen3-vl) bleibt bewusst **außerhalb dieses Specs** als späterer Notnagel — beide hier gebauten Wege liefern strukturierte Daten, was zuverlässiger und besser testbar ist.

## Entscheidungen (vom User)

- **Umfang:** freies Agent-Klicken (generisches „finde Element X, klick/tippe"), nicht nur feste Flüsse.
- **Modell:** die UI-Entscheidungen laufen über das stärkere **qwen3.5:9b** (`cfg.BG_REASONING_MODEL`), nicht gemma.
- **Sicherheit:** autonom, aber mit **harten roten Linien** — destruktive/riskante Elemente + Passwortfelder werden in der Primitivschicht **verweigert** (nicht dem Modell überlassen).

## Dekomposition — zwei Sub-Projekte

Die beiden Wege sind weitgehend unabhängig und bekommen je einen eigenen Plan:

- **Sub-Projekt A (zuerst):** Generelle UI-Automatik (atomacos-Engine + AXManualAccessibility-Wake + Safety + qwen-`computer_task`-Loop).
- **Sub-Projekt B:** Spicetify-Bridge für Spotify.

---

## Sub-Projekt A — Generelle UI-Automatik

### Architektur (Muster wie flipper/spotify: Engine in `tools/`, Skill in `core/skills/`)

**`tools/uiauto/engine.py`** — dünner Wrapper um **atomacos** (lazy import, damit fehlendes atomacos die Skill-Registrierung nicht crasht):
- `is_trusted() -> bool` — `AXIsProcessTrusted()` (Bedienungshilfen-Recht vorhanden?).
- `wake_electron(app_ref)` — setzt `AXManualAccessibility=True` auf das App-Element (weckt Chromium-a11y). Fehler tolerant (native Apps unterstützen das Attribut nicht → ignorieren).
- `snapshot(app: str | None) -> list[Element]` — Vordergrund- oder benannte App; nach `wake_electron` die bedienbaren Elemente rekursiv sammeln. `Element = {ref:int, role:str, title:str, value:str, enabled:bool}`. Nur aktionable Rollen (Whitelist: AXButton, AXMenuItem, AXMenuButton, AXCheckBox, AXRadioButton, AXTextField, AXTextArea, AXSecureTextField, AXPopUpButton, AXLink, AXRow, AXCell, AXTab). `ref` = Index in den Snapshot; der Snapshot wird prozessweit als „letzter Snapshot" gehalten, damit `act(ref)` das Element wiederfindet.
- `act(ref:int, action:str="AXPress") -> None` — Aktion auf dem Element aus dem letzten Snapshot.
- `type_text(text:str)`, `press_key(chord:str)`, `focus_app(name:str)`.

**`tools/uiauto/safety.py`** — reine Logik, die roten Linien:
- `REDLINE_KEYWORDS` — deutsch+englisch: löschen, entfernen, papierkorb, delete, remove, trash, senden, send, abschicken, kaufen, buy, purchase, bezahlen, pay, checkout, veröffentlichen, publish, posten, post, überweisen, transfer, bestätigen-in-Kombination … (Whole-word/Token-Matching, keine Teilwort-Fehltreffer wie „Absender").
- `is_redline(el: Element) -> tuple[bool, str]` — True wenn: Titel enthält ein Redline-Token (tokenisiert, nicht substring) ODER `role == "AXSecureTextField"` (Passwort-/Sicherheitsfeld). Rückgabe (bool, Grund).
- `check_type_target(el) ` — Tippen in `AXSecureTextField` immer verboten.

**`core/skills/uiauto.py`** — Tools:
- Für den **Sub-Loop** (qwen) registriert, Kategorie `uiauto`: `ui_inspect(app?)`, `ui_click(ref)`, `ui_type(text)`, `ui_key(keys)`. Jede handelnde Funktion ruft VOR der Aktion `safety.is_redline` → bei Redline: **kein** Aufruf der Engine, Rückgabe „⛔ Rote Linie: … — nicht ausgeführt".
- Für den **Hauptagenten** (gemma): ein einziges Tool `computer_task(goal, app?)` (Kategorie `uiauto_entry`). Es prüft `is_trusted()` (sonst Setup-Meldung + öffnet den Systemeinstellungs-Bereich per `open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"`), dann startet es einen isolierten `Agent(backend=OllamaBackend(model=cfg.BG_REASONING_MODEL))`-Loop mit exakt den vier `ui_*`-Tools, Schrittbudget (Default 12), Timeout (Default 90s). Gibt ein Kurz-Summary zurück.

### Datenfluss

gemma → `computer_task(goal, app)` → Rechte-Check → qwen-Loop: `ui_inspect` liefert Elementliste mit Labels → qwen benennt `ref`+Aktion → Safety-Gate → `ui_click/type/key` → erneut `ui_inspect` … bis Ziel / Budget / Timeout / Redline. Jede Aktion: `log` + `BUS.emit` (Dashboard-Sichtbarkeit).

### Fehler & Grenzen

- Kein Recht → klare Setup-Meldung, Bereich geöffnet, Abbruch. App nicht gefunden / leerer Snapshot → ehrliche ❌-Meldung. Electron ohne Wake-Erfolg (z.B. Spotify) → „nichts Strukturiertes gefunden" (→ Sub-Projekt B bzw. später Vision).

### Tests (TDD)

- **safety.py:** volle Batterie — Redline-Tokens de/en, Sicherheitsfeld-Block, Teilwort-Fallen („Absenderadresse", „Löschschutz" dürfen nicht … bzw. bewusste Regeln), Groß/Klein.
- **engine.py:** atomacos an der Funktionsgrenze gemockt (wie flipper); Ref-Zuordnung, Rollen-Whitelist, `is_trusted`-False-Pfad, `wake_electron` tolerant.
- **skills/uiauto.py:** gemockte Engine; `ui_click` auf Redline ruft Engine NICHT; `computer_task` ohne Recht → Setup-Meldung; Loop-Stop-Bedingungen mit Fake-„qwen".

---

## Sub-Projekt B — Spicetify-Bridge (Spotify strukturiert)

### Architektur

**`tools/spotify/spicetify_ext/mantis-bridge.js`** — Spicetify-Extension. Läuft in Spotify, öffnet einen **lokalen WebSocket/HTTP-Endpunkt** (localhost, fester Port, nur 127.0.0.1) und beantwortet Kommandos über Spicetifys API:
- `search(query)` → `Spicetify.GraphQL` Suchergebnisse (strukturiert: Tracks/Alben/Playlists/Artists mit URIs + Namen).
- `now_playing()` → `Spicetify.Player.data` (Titel/Artist/Album/Status).
- `play(uri)`, `next()`, `previous()`, `pause()`, `resume()`, `set_volume(v)` → `Spicetify.Player.*`.

**`tools/spotify/bridge.py`** (Mantis-Seite) — httpx/websocket-Client zum lokalen Endpunkt, mit Timeout + „Bridge nicht erreichbar"-Fehler (Extension nicht installiert/Spotify zu).

**Integration in `core/skills/spotify.py`:** Das bestehende `spotify`-Tool bekommt die Bridge als **bevorzugte** Quelle für `status`/`spiel` (strukturierte Suche statt Web-API-Credentials), mit Fallback auf den bestehenden AppleScript/Web-API-Weg, wenn die Bridge nicht läuft. Playback-Aktionen (play/pause/next) können weiter über AppleScript laufen (robust) oder über die Bridge — die Bridge ist v.a. für die **strukturierte Suche** der Gewinn (keine Spotify-Developer-App/Credentials mehr nötig).

### Setup (User, einmalig, bei Rückkehr)

Extension nach `~/.config/spicetify/Extensions/` legen, `spicetify config extensions mantis-bridge.js`, `spicetify apply`. (Automatisierbar per Skript, aber `spicetify apply` startet Spotify neu → besser mit User.)

### Tests (TDD)

- **bridge.py:** httpx/websocket gemockt; Suche-Parsing, Fehler wenn Bridge weg.
- **skills/spotify.py:** Bridge bevorzugt, Fallback wenn Bridge-Fehler → bestehender Weg.
- Extension-JS: nicht unit-getestet (kein JS-Harness in Mantis) — manuell verifiziert bei Rückkehr.

## Globale Randbedingungen

- Python 3.14, Tests `python3.14 -m pytest -q`, Lint `ruff (F,E9)`.
- Deutsch in Doku/Strings, Emoji-Stil.
- Neue Dependency: `atomacos` → `requirements.txt`; lazy import in der Engine.
- Alles degradiert sauber ohne Rechte/ohne Bridge — Mantis-Start darf nie an fehlendem atomacos/Recht scheitern.
- Commits enden mit `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## Was NICHT verifizierbar ist ohne User

- Bedienungshilfen-Recht (System-Grant) → Live-AX gegen echte Apps.
- Spicetify-Extension installieren/`apply` (startet Spotify neu).
- Echte Klicks in laufenden Apps (unbeaufsichtigt bewusst unterlassen).

→ Autonom bis „alle Unit-/Integrationstests grün, Code degradiert sauber"; Live-Smoke-Test dokumentiert für die Rückkehr.
