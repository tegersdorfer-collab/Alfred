# Umbrella-Scope: Weg vom Web-Dashboard → native Mac-App

**Datum:** 2026-07-13
**Status:** Scope-Rahmen (nicht die Umsetzung). Jedes Sub-Projekt bekommt eine eigene Spec → Plan → Umsetzung.

## Ziel

Das überladene Web-Dashboard (`web/index.html`, Browser-Tab auf `:7779`) als primäre
Oberfläche ablösen. Die **Tauri-Desktop-App** (`apps/desktop/`) wird die echte Mac-App
und bekommt alle relevanten Fähigkeiten der Web-App — aber **ohne Navigationsleiste**.
Bedienung ausschließlich über **Voice** (Always-on) und das **Hidden-Menu** (Cmd/Ctrl+K-
Palette, `nav-overlay.ts`) plus das generative HUD (Mantis wählt Widgets selbst).

Das ist ein **Ausbau**, kein Neubau: die Desktop-App verkörpert dieses Paradigma bereits
(HUD, 11 Widgets, Cmd+K-Palette, Voice via Whisper/Piper). Referenz-Architektur:
`docs/superpowers/specs/2026-07-04-multi-device-jarvis-ui-design.md`.

## Ausgangslage (Ist-Stand 2026-07-13)

- **`apps/desktop/`** — Tauri v2 (Rust-Shell + Vite/TS-Frontend). Widgets werden per
  `renderWidget()` in ein `widget-area`-Grid gerendert; Backend wählt sie generativ.
  Einziges Vollbild-Overlay bisher: `nav-overlay.ts` (die Cmd+K-Palette).
- **`web/routers/`** — ~18 Feature-Router: brain, knowledge, calendar, chat, fitness,
  globe, goals, habits, health, insights, journal, nutrition, spicetify, system, tasks,
  trigger, ui_state, voice, meta. Das ist der Feature-Ziel-Umfang.
- **3 native iOS-Apps** (BodyOS/BrainOS/FlowOS, SwiftUI) laufen parallel gegen dasselbe
  Backend. BrainOS hat bereits Second-Brain + `[[wiki-links]]` + force-directed Graph;
  BodyOS hat HealthKit + Health-View. **Offene strategische Frage:** bleiben die iOS-Apps
  parallel bestehen oder wird die Mac-App die eine Oberfläche? → pro Sub-Projekt klären,
  nicht global. Für SP4/SP3 gilt: Backend ist Single Source of Truth, alle Clients teilen es.

## Zerlegung in vier Sub-Projekte

### SP1 — App-Shell & Navigation (Fundament)
Navigationsleiste endgültig entfernen; Voice + Cmd/Ctrl+K-Palette als *einzigen*
Navigationsweg formalisieren; ein **Overlay-Framework** einführen (Vollbild-Content-
Ansichten für große Bereiche wie Graph & Health, abgegrenzt von kleinen HUD-Widgets).
De-riskt SP3 & SP4. **Hinweis:** SP4 pioniert das erste Content-Overlay (`health-overlay`);
SP1 verallgemeinert dieses Muster nachträglich zu einem generischen Framework.

### SP2 — Feature-Parität
Restliche Web-Bereiche als Widgets/Overlays nachziehen: goals, journal, insights,
fitness, news-globe, calendar-detail, nutrition-detail usw. Inkrementell, ein Bereich
nach dem anderen. Jeder Bereich: Backend-Router existiert schon → nur Frontend-Widget/
Overlay + Cmd+K-Kachel + ggf. Voice-Intent.

### SP3 — Memory-Overhaul + Wissensgraph
Backend-Gedächtnis auf ein **Obsidian/Zettelkasten-Modell** heben (Markdown-Dateien,
`[[Links]]`, Folgezettel/IDs) + ein **Graphify-artiges Vollbild-Graph-Overlay** in der
App. Offene Vorklärung: eigenes Obsidian-Vault einbetten vs. eigener schlanker Ersatz.
Tiefste, riskanteste Säule (fasst den Memory-Kern an, nicht nur UI). Verweist auf das
bestehende `productivity:memory-management` + `core`/`domains/second_brain.py` +
BrainOS-Graph als Vorlage.

### SP4 — Health-Overview mit Scores  ← **zuerst**
Übersichtliches Health-Overlay: 4 Domain-Scores (Recovery/Sleep/Activity/Body) +
Metrik-Graphen, jeweils transparent aufschlüsselbar, plus Mantis-Klartext-Read.
Detail-Spec: `2026-07-13-health-overview-scores-design.md`.

## Reihenfolge & Abhängigkeiten

```
SP4 (Health) ──▶ SP1 (Shell/Overlay-Framework) ──▶ SP3 (Memory/Graph)
                                                └──▶ SP2 (Feature-Parität, begleitend)
```

**Empfohlen: SP4 → SP1 → SP3, SP2 begleitend.** Begründung: SP4 ist gut abgegrenzt,
hat hohen Alltagsnutzen und liefert das erste Content-Overlay als konkretes Muster.
SP1 hebt dieses Muster danach ins Generische. SP3 ist die tiefste Säule und profitiert
vom fertigen Overlay-Framework. SP2 läuft inkrementell nebenher.

**Gewählt vom User (2026-07-13): Start mit SP4.**

## Nicht-Ziele (dieser Umbau)

- Kein Abschalten der 3 iOS-Apps in diesem Rahmen (separate Entscheidung).
- Kein sofortiges Löschen des Web-Dashboards — es bleibt, bis die Mac-App Parität hat.
- Kein Windows-spezifischer Ausbau hier (Tauri deckt es aus einer Codebasis mit ab).
```
