# Alfred Multi-Device + Generatives "Jarvis"-UI — Design / Spec

**Datum:** 2026-07-04
**Scope:** Zwei zusammenhängende Vorhaben: (1) Alfred von Mac-only auf ein Multi-Device-System
erweitern (Mac + Windows-PC als ein System), mit dem Ziel nativer Desktop-Apps für macOS und
Windows. (2) Diese Desktop-Apps bekommen kein klassisches Dashboard, sondern ein generatives,
kontextabhängiges UI im Jarvis-Stil, gesteuert primär per Stimme (gleichwertig per Text).

Dies ist eine **Architektur-Spec** — sie legt Systemgrenzen, Mechanismus und Baureihenfolge fest.
Konkrete Widget-Inhalte, Pixel-genaues Styling, Auto-Update/Signing/Installer-Details sind
bewusst nicht Teil dieser Spec und folgen in eigenen Runden.

---

## 1. Systemarchitektur: ein Backend, mehrere Clients

**Entscheidung:** Der bestehende Alfred-Prozess (FastAPI + Postgres + Ollama + Telegram-Bot +
Autopilot) bleibt die **einzige** Instanz, läuft weiter 24/7 auf dem Mac (launchd). Der
Windows-PC bekommt **kein eigenes Backend** und **kein eigenes Ollama** — er ist ein reiner
Client, genau wie die drei bestehenden iOS-Apps heute.

**Warum:** Verteilte Zustände (zwei Postgres-Instanzen, zwei Ollama-Modelle, "wer ist
gerade primary") sind ein eigenständiges, sehr fehleranfälliges Problem, das nichts mit dem
eigentlichen Ziel (ein smarter Concierge) zu tun hat. Der Mac läuft ohnehin durchgehend — es
gibt keinen Grund, diese Komplexität einzukaufen.

**Netzwerk:** Tailscale bleibt der Transportweg. Der Windows-PC tritt demselben Tailnet bei;
danach ist `macbook-air-von-timo.tail7e29ff.ts.net:7779` von dort erreichbar wie vom iPhone
heute. Kein zusätzliches App-Token nötig (Tailnet-Zugehörigkeit ist die Zugriffskontrolle,
wie im bestehenden Dashboard-Code dokumentiert).

## 2. App-Technologie: Tauri, eine Codebasis

**Entscheidung:** Ein Tauri-Projekt unter `apps/desktop/` erzeugt sowohl die macOS-`.app` als
auch die Windows-`.exe`/`.msi`. Tauri nutzt das Betriebssystem-eigene WebView statt Chromium
mitzuliefern (Electron-Alternative) — Apps sind ein Bruchteil der Größe, starten schneller,
verbrauchen weniger RAM. Passt zum Ziel "so gut wie möglich ohne Millionär zu sein": kein
Cloud-Hosting, keine teure Infrastruktur, ein schlanker nativer Client pro Plattform.

**Reihenfolge:** Windows-App zuerst (dort existiert aktuell kein Zugang zu Alfred), macOS-App
danach. Da beide aus derselben Codebasis kommen, ist die macOS-App danach überwiegend
Build-Konfiguration + Feinschliff, kein zweiter Entwicklungsdurchlauf.

**Frontend-Strategie:** Kein Wiederverwenden der bestehenden PWA-`index.html` — das neue UI
(Abschnitt 3-6) ist ein eigenständiges Frontend, das die vorhandenen REST-/SSE-Endpunkte des
Backends nutzt (dieselbe API wie PWA und iOS-Apps), aber komplett neu gebaut wird. Die
bestehende PWA bleibt parallel bestehen (funktioniert weiter im Browser/Homescreen), wird aber
nicht Ausgangspunkt der neuen App.

## 3. UI-Grundprinzip: ein adaptiver Screen statt Dashboard

Statt eines Dashboards mit vielen sichtbaren Buttons/Kacheln zeigt die App standardmäßig einen
**ruhigen, weitgehend leeren Screen** (Ruhezustand: HUD-Ring + minimaler Status). Der Bildschirm
**morpht** inhaltlich je nach Anfrage: "Plane mir eine Reise nach Lissabon" lässt eine Karte
erscheinen, "wie war mein Training diese Woche" lässt ein Balkendiagramm erscheinen. Es gibt
keine feste Navigationsleiste mit Icons für jeden Lebensbereich, die permanent sichtbar ist.

**Optik:** Holographic-HUD-Stil — glühendes Cyan auf sehr dunklem/schwarzem Hintergrund,
kreisförmige Ring-Elemente, dezente Scanline-/Grid-Texturen. Monospace-Akzentschrift für
Status-/Datenlabels.

## 4. Steuerungsmechanismus: generatives UI über die bestehende Tool-Architektur

Alfred hat bereits eine Tool-Registry (57 Tools, das LLM ruft sie im ReAct-Loop selbst auf,
z.B. `create_task`). Das UI wird über **dasselbe Prinzip** gesteuert — kein zweites System:

- **Deterministische Basis-Zuordnung:** jedem relevanten Daten-Tool wird ein Widget-Typ
  zugeordnet (`get_sleep_data` → Schlaf-Widget mit Graph + Qualitäts-Ring, `get_calendar_events`
  → Karte/Kalender-Widget). Ruft der Agent im normalen Gespräch dieses Tool auf, erscheint das
  Widget automatisch — ohne dass ein Extra-LLM-Call "über UI nachdenken" muss.
- **Explizite UI-Tools** für Fälle mit echtem Urteilsbedarf: `show_widget(widget_type, params,
  slot)`, `arrange_screen(layout_preset, widgets)`, `close_widget(slot)`. Ganz normale Tools in
  der bestehenden Registry, die der Agent wie jedes andere Tool aufruft.
- Die App abonniert den **UI-State** über einen neuen SSE-Kanal (analog zum bestehenden
  Status-/Chat-Feed) — Rendering ist reine Client-Logik.

**Text und Stimme sind gleichwertig**, weil beide durch denselben Agent-Loop laufen: Sprache
wird lokal transkribiert (Whisper, wie bei Telegram-Sprachnachrichten heute) und geht als
normaler Text-Turn in den Agenten — kein separater "Sprachmodus" mit eigener Logik.

## 5. Sprachsteuerung: always-on, kein Wake-Word

**Entscheidung:** Kein Push-to-Talk, kein Wake-Word ("Hey Alfred") — das Mikrofon läuft
dauerhaft, Alfred erkennt aus dem natürlichen Gesprächsfluss, wann er gemeint ist (z.B. "ruf
mir bitte die Nacht-Zusammenfassung auf" ohne Attention-Wort).

**Mechanismus (Vorschlag):**
1. Lokale Voice-Activity-Detection (VAD) markiert Sprachsegmente (billig, läuft dauerhaft).
2. Lokales Whisper-Streaming transkribiert erkannte Segmente (wiederverwendet die bestehende
   lokale Whisper-Infrastruktur).
3. Ein sehr schneller lokaler Zwischen-Check ("ist das ein an mich gerichteter Befehl,
   ja/nein") über die bestehende `core.fast`-Schnelllane entscheidet, BEVOR der teure
   Haupt-Agent-Loop überhaupt anläuft — kritisch für die geforderte niedrige Latenz.
4. Nur bei positivem Treffer läuft die Anfrage durch den vollen Agent-Loop (inkl. Tool-Calls,
   UI-Steuerung).

**Risiko-Hinweis (bewusst so entschieden, nicht übersehen):** Dies ist die technisch
anspruchsvollste und unsicherste Komponente des gesamten Plans — Fehlalarm-Rate (Nebensätze im
Raum lösen ungewollt etwas aus) und Dauerlast auf dem M4/16GB neben Postgres/Ollama/Backend sind
beides offene Fragen, die sich erst in der Implementierung zeigen. Es wurde entschieden, dies
direkt fest einzuplanen (kein isolierter Vorab-Prototyp) — im Bauplan sollte diese Komponente
dennoch früh angegangen werden, damit sich Probleme zeigen, solange noch wenig anderer Code
darauf aufbaut.

## 6. Layout: begrenztes Set adaptiver Vorlagen

Kein einzelnes festes Layout, aber auch kein echtes Freiform-Positionieren durch die KI (kaum
vorhersagbar zu bauen/testen). Stattdessen ein **kleines Set an Layout-Vorlagen** (z.B.
Einzel-Fokus, 2er-Grid, 3er-Grid, Karte-dominant), zwischen denen Alfred per `arrange_screen`
kontextabhängig wählt — inklusive Zuweisung, welches Widget in welchen Slot der gewählten
Vorlage kommt. Innerhalb einer Vorlage: Hover-to-Expand (Widget unter dem Mauszeiger vergrößert
sich leicht) als Mikro-Interaktion.

## 7. Versteckte manuelle Navigation

Eine Tastenkombination (plattformspezifisch: macOS/Windows-Konventionen unterscheiden sich,
Festlegung der genauen Tasten folgt in der Implementierung) öffnet eine **Vollbild-Übersicht**
mit ca. 9 vorkonfigurierten Unterscreens (Health, Brain, Tasks, Kalender, etc. — analog zu den
heutigen Dashboard-Views). Klick auf einen davon setzt ihn als neuen Hauptscreen. Dies ist ein
reiner Fallback/Escape-Hatch für manuelle Navigation ohne Sprache/Text — die KI ist dabei nicht
involviert.

## Nicht-Ziele dieser Spec
- Konkrete Widget-Bibliothek (welche Widgets es geben wird, Detail-Design pro Widget)
- Genaue Tastenkombination für die versteckte Navigation
- Auto-Update-Mechanismus, Code-Signing/Notarization, Windows-Installer
- Wiederverwendung/Migration der bestehenden PWA-Views in die neuen Widgets (separates Thema)
- Genaue VAD-/Whisper-Modellwahl und Performance-Zielwerte (Teil der Implementierungsplanung)

## Offene Punkte für die Implementierungsplanung
- Reihenfolge der Bausteine: Empfehlung wäre, den Voice-Pipeline-Kern (Abschnitt 5) früh zu
  bauen und isoliert zu messen (Latenz, Fehlalarm-Rate), auch wenn er nicht als separate Spec
  vorgezogen wird — die restliche App hängt stark von seiner Zuverlässigkeit ab.
- Genaues SSE-Protokoll für den UI-State-Kanal (Nachrichtenformat für `show_widget`/
  `arrange_screen`/`close_widget`)
- Erste Widget-Bibliothek: welche 5-10 Widgets deckt die häufigsten Anfragen ab (Schlaf,
  Training, Tasks, Kalender/Karte, Kalorien, Habits, Second Brain, Ziele)
