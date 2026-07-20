# Skilltree — Life-Gamification mit ehrlicher Messung

**Datum:** 2026-07-20
**Status:** Design (per Brainstorm entschieden) → Implementierungsplan folgt.
**Motivation:** Timos Leben gamifizieren & „upleveln". Mantis misst Fortschritt **ehrlich** (aus echten Daten, nicht self-reported XP) und **pusht aktiv**. Kein hübsches Dashboard, das nichts ändert — der Wert entsteht aus echter Messung + adaptivem Antrieb.

## Entscheidungen (fix)
1. **Aufbau (Rückgrat):** **Stats/Level (B)** als Fundament + **Quest-Motor (C)** als Antrieb + **Skilltree-Optik (A)** als Framing. Nicht drei Systeme — ein System mit diesen drei Schichten.
2. **Achsen (Start, erweiterbar als Config):** Körper, Wissen, Schaffen/Handwerk, Geist/Mindset, Disziplin/Fokus. Neue Achse = ein Config-Eintrag, kein Umbau. „Sozial" bewusst erst mal draußen.
3. **Messen — 3 Signal-Ebenen:**
   - **① Harte Signale (automatisch, unfälschbar):** Health-Scores, Git-Commits/Projekt-Aktivität, angelegte Zettel, Lernpfad-/Studien-Fortschritt. Rückgrat.
   - **② Cam-verifiziert (später):** Anti-Cheat-Upgrade (sieht: wirklich am Schreibtisch/fokussiert). **System läuft heute komplett ohne Cam** — kein Cam-Zwang im Fundament.
   - **③ Self-Report mit Kalibrierung:** Für nicht-direkt-messbares (Mindset, Reflexion). XP fließt (kein Gate), aber Mantis ist **Kalibrierungs-Spiegel**: gleicht gegen harte Signale ab, deckt **blinde Flecken/Fehleinschätzung** auf, korrigiert rückwirkend. Ziel: ehrliche Selbstsicht, nicht Lügen-Fang.
4. **XP/Level:** kontinuierlich, pro Achse, aus gewichteten Signalen (hart = voll, self-report = Vertrauensfaktor). Mantis rechnet im Hintergrund, kein Punkte-Feilschen.
5. **Nodes (permanent):** Meilensteine rasten ein und **verfallen nie** („100 kg gehoben", „Modul bestanden", „Konzept verstanden"). Das ist die Baum-Optik.
6. **Decay (smart):** nur das *aktuelle Level* rostet — mit **Retention-Klasse pro Komponente**: *schnell* (Kondition, Fokus-Streak, Momentum), *langsam* (Kraft-Basis, gefestigtes Wissen), *quasi-permanent* (tief verankert). Rost erst nach echter Vernachlässigung, langsam, **mit Vorwarnung**. Node bleibt, Level sinkt.
7. **Motor (adaptiv):** Quests, die **Rost pushen** (Priorität: rundes Wachstum) **+ Momentum nutzen** (Eisen schmieden solang heiß). Im Ruhezustand **Berater**, keine Nervensäge.
8. **Kein Doppel-Tracking:** Skilltree ist ein **Leselayer** über vorhandene Mantis-Daten (Health, Second Brain, Wissensgraph, Git). Er trackt nicht neu, was Mantis schon weiß.

## Architektur (Komponenten, isoliert)

### A. Signal-Collector (`domains/skilltree/signals.py`)
Dünner Sammler: zieht Roh-Signale aus den bestehenden Stores (Health-Scores, `brain_notes`, kg, Git-Aktivität, Lernpfade) → normalisiertes `SignalEvent{axis, kind, value, source, ts, confidence}`. Kennt die Stores, aber keine Scoring-Logik.

### B. Scoring & Decay (`domains/skilltree/scoring.py`) — **reine Logik, TDD**
- `axis_level(signal_history, axis_config, now) -> {level, xp, trend}` — gewichtete XP-Akkumulation + zeitbasierter Decay je Retention-Klasse. Injizierbar → pytest.
- `retention_decay(component, elapsed) -> factor` — reine Kurve pro Klasse (schnell/langsam/quasi-permanent).
- `calibration_check(self_report, hard_signals) -> {aligned, gap, note}` — deckt blinde Flecken auf (③).
- `unlocked_nodes(signal_history, node_defs) -> [node]` — Meilenstein-Erkennung (permanent, idempotent).

### C. Quest-Engine (`domains/skilltree/quests.py`) — **reine Logik, TDD**
- `pick_quests(axis_states, momentum, history, quest_pool) -> [quest]` — adaptive Auswahl: rostende Achse (Push) vs. Momentum-Achse (Verstärken), Anti-Wiederholung, Ambitions-Dosierung. Rein → pytest.
- `quest_progress(quest, signals) -> {done, pct}` — **Auto-Completion** aus harten Signalen (Commit/Training/Zettel erkannt → Quest hakt sich selbst ab); Self-Report nur für den Rest.

### D. Config (`domains/skilltree/config.py` + DB)
Achsen-Definitionen, Signal-Gewichte, Retention-Klassen, Node-Defs, Quest-Pool — **Daten, kein Code**. Erweiterbar ohne Umbau (Entscheidung #2).

### E. Persistenz
Postgres: `skill_axes` (Zustand/History), `skill_nodes` (freigeschaltete Meilensteine), `skill_quests` (aktiv/erledigt), `skill_signals` (optional Cache). Migration nach Mantis-Muster (`core/db.py`).

### F. Schnittstellen (Mantis-Integration, exakt nach SP4-Health-Vorlage)
- **Endpoint:** `GET /api/skilltree` (Achsen-Level, Nodes, aktive Quests), `POST /api/skilltree/quest/{id}` (report/complete), `POST /api/skilltree/report` (self-report) — `web/routers/skilltree.py`.
- **Voice-Intent:** `get_skilltree_status` / `get_next_quest` (`core/skills/skilltree.py`) + Fast-Path (`core/fast_commands.py`). Mantis spricht Status, Quests, Rost-Warnungen; Report per Sprache.
- **Widget:** Payload in `core/ui_state.py` (WIDGET_MAP + `_DASHBOARD_BUILDERS`, Typ `skilltree`).
- **Frontend:** `apps/desktop/src/skilltree-overlay.ts` auf SP1-Framework (`createOverlay`/`registerOverlay`): Baum-Viz mit Achsen-Ringen + Nodes, Drilldown pro Achse, Quest-Liste, Self-Report-UI. Reine Render-/Layout-Helfer exportiert → **vitest**. Widget `case 'skilltree'` in `main.ts`; `initSkilltreeOverlay(getBaseUrl())` **vor** `initNavOverlay(...)`.

## Datenfluss
Bestehende Stores → Signal-Collector → `SignalEvent` → Scoring/Decay → Achsen-Level + Node-Unlocks (DB) → Quest-Engine wählt adaptive Quests → Voice/Overlay zeigt Status+Quests → harte Signale haken Quests auto ab, Rest per Self-Report → Kalibrierungs-Check flaggt blinde Flecken.

## Milestones
- **M1 — Scoring-Kern (TDD):** `scoring.py` + `signals.py`, 5 Achsen aus vorhandenen Daten berechnet, Decay + Nodes. Verifikation: echte Level aus Timos DB (curl `/api/skilltree`).
- **M2 — Quest-Engine (TDD):** `quests.py`, adaptive Auswahl + Auto-Completion. Verifikation: Quests reagieren auf Rost/Momentum.
- **M3 — Overlay + Voice:** Baum-Viz, Drilldown, Self-Report-UI (vitest), Voice-Intents + Fast-Path. Live-Check (Screenshot, wie Session-Standard).
- **M4 — Kalibrierung + Feinschliff:** blinde-Flecken-Nudges, Retention-Tuning an echten Daten.
- **später — Cam-Ebene ②:** wenn die Cam da ist, als zusätzliche Verifikationsquelle in den Collector.

## Risiken / offen
- **Signal-Qualität:** Level ist nur so ehrlich wie die harten Signale. Achsen ohne guten Datenanschluss (Geist/Mindset) hängen stärker an ③ → Kalibrierung wichtig.
- **Retention-Kurven** brauchen Tuning an echten Daten (M4), Startwerte sind Schätzung.
- **Motivation vs. Ehrlichkeit:** Decay muss sich fair anfühlen, sonst demotiviert es. Vorwarnung + permanente Nodes federn das ab — an echten Daten prüfen.
- **Gewichtung** der Signale pro Achse: erst grob, dann iterativ.

## Nicht in Scope (YAGNI)
Keine sozialen Features/Vergleiche/Leaderboards. Keine externen Belohnungen. Keine neue Datenerfassung, die Mantis nicht eh schon hat (außer später Cam). Kein Achsen-Zwang — Start mit 5, wächst bei Bedarf.
