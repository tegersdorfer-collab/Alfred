# Alfred Desktop-HUD — UI-Polish "Ghost Protocol" — Design / Spec

**Datum:** 2026-07-05
**Scope:** Rein visuelle Überarbeitung des bestehenden Desktop-HUD (`apps/desktop/`). Keine neuen
Widgets, keine neue Funktionalität, kein neuer Backend-Code. Ziel: aus dem funktional
vollständigen, aber visuell rohen HUD (Stand Nachtsession 2026-07-05, `ROADMAP.md`) ein Interface
machen, das wie das UI einer fiktiven Superintelligenz wirkt — ruhig im Leerlauf, sichtbar
"lebendig" bei Aktivität.

Nicht Teil dieser Spec (bewusst ausgeklammert): Screen-Recording-Permission, Windows-Build,
neue Widget-Typen, Backend-/Datenänderungen.

---

## 1. Ist-Zustand (Bestandsaufnahme)

- Ein einziges `apps/desktop/src/style.css` (310 Zeilen), durchgehend hardcodierte Hex-Werte,
  kein Variablen-/Token-System.
- Farbsprache: nahezu monochrom Cyan (`#00e5ff`) auf Dunkelblau-Schwarz (`#04070d`), einzige
  Ausnahme ist ein Amber-Ton (`#ffb84d`) für Warn-Toasts. Kein Error-, kein Success-Zustand.
- Ambient-Layer (Grid-Textur, wandernde Scanline, Vignette per `box-shadow: inset`) sind bereits
  vorhanden und gut — bleiben unverändert.
- 11 Widget-Typen in `main.ts::renderWidget`, aber nur 3 unterschiedliche Rendering-Pfade:
  - `renderBars` (echtes Visual, SVG-frei, reine Balken) — genutzt von `sleep`, `training`
  - `renderList` (reine Textzeilen) — genutzt von `tasks`, `calendar`, `habits`, `brain`,
    `skills`, `weather`
  - `renderGraph` (echtes SVG, Node/Edge-Kreisdiagramm) — genutzt von `brain_graph`
  - Sonderfälle **ohne** Helper, nur roher Text-String: `nutrition`, `system` — diese sind die
    am wenigsten polierten und zugleich am besten für Gauges geeignet (beides reine
    Prozent-/Zahlenwerte).
- Keine Zahlen-Animation (Werte springen hart), kein Hover-/Klick-Feedback außer
  `.nav-tile:hover`, keine einheitliche Transition beim State-Wechsel (nur generisches
  Opacity-Fade auf Container-Ebene).

## 2. Designrichtung: "Ghost Protocol"

Leitidee: Farbe und Bewegung sind **Bedeutungsträger, nicht Dekoration**. Im Ruhezustand ist das
HUD gedimmt und fast unauffällig; sobald das System etwas tut (denkt, antwortet, warnt), zieht
sichtbar Licht/Farbe/Bewegung durch das Interface. Das erzeugt den Eindruck einer wartenden,
denkenden Präsenz statt eines Dashboards mit Live-Zahlen.

### 2.1 Farbpalette (Statushierarchie)

Alles über CSS-Variablen in einem `:root`-Token-Block, keine Hex-Werte mehr direkt in Regeln:

| Token | Wert | Bedeutung |
|---|---|---|
| `--c-idle` | `#00e5ff` @ ~40% Opacity | Ruhezustand, Standard-Textfarbe |
| `--c-active` | `#00e5ff` @ 100%, mit Pulse | Denken/Verarbeiten |
| `--c-speaking` | wärmerer Cyan-Ton (leicht Richtung Weiß) | Antwort läuft |
| `--c-warn` | `#ffb84d` (bestehend) | Warnung |
| `--c-error` | `#ff3860`-Ton | Fehler/kritisch (neu, existiert noch nicht) |
| `--c-ok` | `#4dffb8`-Ton | Erfolg/Bestätigung (neu, existiert noch nicht) |
| `--bg-base` | `#04070d` (bestehend) | Grundhintergrund |

Jede Farbe bekommt zusätzlich eine `--glow-*`-Variante (fertiger `box-shadow`-String) für
konsistente Leucht-Effekte statt Ad-hoc-Shadows pro Widget.

### 2.2 Typografie-Skala

SF Mono bleibt (System-Readout-Charakter, sci-fi-typisch durch Letter-Spacing). Neue feste Skala
statt der aktuell zwei Ad-hoc-Größen:

- `--fs-micro: 10px` (Metadaten, Timestamps)
- `--fs-label: 11px` (Widget-Titel, bestehend)
- `--fs-body: 13px` (Listenzeilen, bestehend)
- `--fs-value: 20px` (neu — große Kennzahlen: CPU %, RAM %, Temperatur)
- `--fs-hero: 32px` (neu — HUD-Zentralstatus)

Uppercase + Letter-Spacing für Labels bleibt Signature-Stil, wird aber konsequent auf alle
Widget-Titel angewendet (aktuell inkonsistent).

### 2.3 Motion-Sprache

- **State-Transition ("Charge"-Effekt):** Jeder Wechsel (idle→active, Widget erscheint/verschwindet,
  Alert kommt rein) triggert einen kurzen Rand-/Ring-Aufhell-Puls (~200ms) statt hartem Fade.
  Realisiert als wiederverwendbare CSS-Animation-Klasse (`.charge-pulse`), nicht pro Widget neu.
- **Zahlen-Tweening:** Numerische Werte (CPU %, RAM %, kcal, Makros) animieren beim Update von
  Alt- zu Neuwert (kleiner JS-Helper, kein neues Framework/keine neue Dependency — reines
  `requestAnimationFrame`-Interpolieren von Text-Content).
- **Hover-/Klick-Feedback:** Jedes interaktive Element (nicht nur `.nav-tile`) bekommt einen
  kurzen Glow-Ripple bei Hover/Active.
- Bestehende Ambient-Layer (Scanline, Grid, Vignette, `#hud-ring`-Breathe-Animation) bleiben
  unangetastet — die sind schon Teil der Zielästhetik.

### 2.4 Von Text zu Visual (größter Hebel für den "Superintelligenz"-Eindruck)

Reihenfolge nach Aufwand/Wirkung, gleichzeitig die Abarbeitungsreihenfolge für die
Implementierung:

1. **`system`-Widget** (aktuell roher String) → radiale SVG-Gauges für CPU % und RAM %
   (`stroke-dasharray`-Technik, wie schon in `renderGraph` für SVG vorgemacht), Ollama-Status
   als farbiger Punkt (`--c-ok`/`--c-error`) statt Emoji. Dient als **Referenz-Widget**: hier
   wird das Token-System, die Gauge-Komponente und die Zahlen-Tweening-Logik zuerst gebaut und
   verifiziert, bevor der Rest folgt.
2. **`nutrition`-Widget** (aktuell roher String) → gleiche Gauge-Komponente wiederverwendet für
   kcal-Ziel-Fortschritt + drei kleine Balken für Protein/Carbs/Fat.
3. **`sleep` / `training`** (schon `renderBars`) → nur Token-Umstellung + Charge-Pulse bei
   Werteänderung, keine strukturelle Änderung nötig.
4. **`brain_graph`** (schon SVG) → nur Token-Umstellung (Farben aus `--c-*` statt Hex) +
   Hover-Feedback auf Nodes.
5. **`tasks` / `calendar` / `habits` / `brain` / `skills` / `weather`** (alle `renderList`) →
   bleiben Listen (das ist für diese Inhalte die richtige Darstellung), bekommen aber: farbige
   Statuspunkte statt Emoji wo sinnvoll (`habits`-Streak, `tasks`-Progress als kleiner Inline-Bar
   statt nur Prozentzahl-Text), konsistente Tokens, Charge-Pulse bei Zeilen-Update.
6. **Nicht-Widget-UI** (Alert-Overlay, Settings-Panel, Chat-Input, Conversation-Log,
   Nav-Overlay): Token-Umstellung + Motion-Konsistenz, keine strukturelle Änderung — diese sind
   bereits funktional/visuell in Ordnung, brauchen nur Angleichung an das neue System.

### 2.5 Technisches Vorgehen

- `style.css` bekommt einen `:root`-Token-Block ganz oben; der Rest der Datei wird schrittweise
  auf Variablen umgestellt (kein Big-Bang-Rewrite — pro Widget-PR/Commit).
- Neue, wiederverwendbare Bausteine (nicht pro Widget dupliziert):
  - CSS-Klasse `.charge-pulse` (State-Transition-Animation)
  - JS-Helper `tweenNumber(el, from, to, durationMs)` in einer neuen kleinen Datei
    `apps/desktop/src/motion.ts` (mit Unit-Tests wie die übrigen `*.ts`-Module)
  - SVG-Gauge-Helper `renderGauge(container, pct, color)` in `main.ts` neben den bestehenden
    `renderBars`/`renderList`/`renderGraph`-Helpern, gleiches Muster
- Kein neues Frontend-Framework, keine neue Dependency — bleibt vanilla TS/CSS wie bisher.
- Verifikation pro Widget: bestehende Vitest-Suite grün + `npm run tauri build` +
  Live-Screenshot-Check (mehrere Fenstergrößen, da HUD responsive über `grid-template-columns`
  läuft) — kein Widget gilt als fertig ohne visuellen Check, nur `npm test` reicht nicht.
- Fortschritt wird laufend in `ROADMAP.md` unter einem neuen Abschnitt `## UI-Polish-Pass
  (2026-07-05)` pro Widget abgehakt.

## 3. Out of Scope / bewusst nicht Teil dieser Runde

- Neue Widget-Typen oder Backend-/Payload-Änderungen (`core/ui_state.py` bleibt unangetastet).
- Screen-Recording-Permission, Windows-Build (siehe Handoff-Doc vom 2026-07-05 — beide
  User-Action-blockiert, nicht UI-relevant).
- Grundsätzlicher Wechsel von Vanilla-TS auf ein UI-Framework (React o.ä.) — die aktuelle
  Struktur ist klein genug, dass das keinen Mehrwert brächte und nur Risiko für die laufende
  Voice-Pipeline-Integration einführen würde.
- Sound-Design-Änderungen (`sound-feedback.ts` bleibt wie es ist, ist kein visuelles Thema).

## 4. Akzeptanzkriterien

- Keine Hex-Farbwerte mehr direkt in `style.css`-Regeln außerhalb des `:root`-Token-Blocks.
- Alle 11 Widgets nutzen konsistent dieselbe Typografie-Skala und Statusfarben.
- `system` und `nutrition` zeigen echte Visuals (Gauges/Balken) statt reinem Text.
- Jeder Widget-/State-Wechsel läuft über die gemeinsame Charge-Pulse-Animation statt Ad-hoc-Fades.
- Numerische Live-Werte (CPU/RAM/kcal/Makros) tweenen statt hart zu springen.
- Bestehende Test-Suite (`npm test -- --run`, `npx tsc --noEmit`) bleibt grün; neue Helper
  (`motion.ts`, `renderGauge`) bekommen eigene Tests nach demselben Muster wie bestehende Module.
