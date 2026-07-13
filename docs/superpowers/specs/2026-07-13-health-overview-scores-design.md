# SP4 — Health-Overview mit Domain-Scores

**Datum:** 2026-07-13
**Umbrella:** `2026-07-13-native-app-migration-scope.md` (Sub-Projekt 4, zuerst umgesetzt)
**Status:** Design genehmigt (Score-Modell, Architektur, Layout/Drilldown visuell bestätigt) → bereit für Implementierungsplan.

## Ziel

Ein sehr übersichtliches Health-Overlay in der Mac-App (`apps/desktop/`): vier
**Domain-Scores** als Blick-Anker, darunter Metrik-Graphen, jeweils **transparent
aufschlüsselbar**, plus ein Mantis-**Klartext-Read**. Geöffnet per Voice oder
Cmd/Ctrl+K. Nutzt bestehende HealthKit-/`/api/health`-Daten (COROS Pace 4 → COROS-App
→ Apple Health → BodyOS-Push).

## Bindende Randbedingung: Datenlage

Aktuell sind die Health-Daten dünn (nur `weight`/`steps`/`sleep` teils befüllt;
**HRV, Ruhepuls, Schlafphasen, Kalorien komplett leer**, nur 3/14 Tage). Der
BodyOS-Sync ist zurzeit aus (User: „kümmere ich mich später drum"). Daraus folgt das
**Kern-Designprinzip**: das Konstrukt wird für den **vollen** Metriksatz gebaut und
**degradiert elegant** bei fehlenden Werten — es wird *jetzt* gebaut, die Daten kommen
später. Der Sync-Fix ist ein separater Roadmap-Punkt (siehe unten), **kein** Blocker.

## Score-Modell

Vier Domains, je 0–100, als Ringe oben im Overlay:

| Domain | Sub-Metriken (Gewicht) | Quelle |
|---|---|---|
| **Recovery** | HRV (40 %), Ruhepuls (25 %), Schlafqualität (25 %), Load gestern (10 %) | COROS/HealthKit |
| **Sleep** | Dauer vs. Bedarf (40 %), Tief+REM-Anteil (30 %), Effizienz (15 %), Einschlaf-Konsistenz (15 %) | HealthKit sleep-stages |
| **Activity** | Schritte vs. Ziel (30 %), Aktiv-Kalorien (25 %), Trainingsminuten (25 %), Load-Balance (20 %) | HealthKit + COROS-Load |
| **Body** | Gewicht-Trend vs. Ziel, Körperfett (falls da) — langsamer Trend-Score | Manuell/COROS |

Gewichte sind **konfigurierbar** (eine Config-Konstante, kein Hardcode über den Code
verstreut). Kein einzelner „Gesamt-Gesundheits-Score" als Headline (verworfen: verdichtet
zu viel, irreführend bei Teil-Daten).

## Methodik

**Hybrid-Normalisierung pro Metrik:**
1. **Personalisierte Baseline** (bevorzugt): rollierender 60-Tage-Median + Streuung des
   Users. Jede Metrik wird relativ zum eigenen „Normal" auf 0–100 abgebildet
   (Oura/Whoop-Prinzip: „vs. dein Schnitt").
2. **Richtwert-Fallback** (Cold-Start): solange < N Tage Historie vorliegen (Vorschlag
   N = 14), allgemeine Gesundheits-Richtwerte (z.B. Schlaf 7–9 h = gut). Nahtloser
   Übergang zur Baseline, je mehr Daten da sind.

**Graceful Degradation (erste Klasse):**
- Fehlt eine Sub-Metrik, fliegt sie raus, die restlichen Gewichte werden **renormiert**.
- Fällt die Zahl verfügbarer Inputs unter einen Mindestanteil (Vorschlag: < 50 % des
  Domain-Gewichts vorhanden), zeigt die Domain **„zu wenig Daten"** statt einer
  erfundenen Zahl.
- Der Leer-Zustand ist ein bewusstes UI-Element (gestrichelter Ring, „—", erklärender
  Text), kein Fehler.

**Transparenz:** Jeder Domain-Score ist im Drilldown vollständig aufgeschlüsselt — jede
Sub-Metrik mit Rohwert, Baseline-Kontext, Sub-Score und Gewicht. Deterministisch &
reproduzierbar; kein Blackbox-Wert.

**Mantis-Klartext-Read (Differenzierer):** Über den Zahlen erzeugt Mantis einen kurzen
natürlichsprachigen Read („Recovery 62: HRV 12 % unter Baseline nach 5 h Schlaf — heute
ruhiger"). Deterministische Scores liefern die Fakten, das LLM formuliert. Auch per Voice
abrufbar.

## Architektur

**Backend = Single Source of Truth** (Desktop + iOS + Voice teilen es):

- **`domains/health_scores.py`** — reine Funktionen, kein I/O:
  - `compute_baselines(rows, window=60) -> Baselines`
  - `score_metric(value, baseline, guideline) -> float | None`
  - `compute_domain_scores(rows_today, baselines, config) -> ScoredDay`
    (liefert je Domain: Score-or-None, Sub-Beiträge, Degradations-Flags)
  Voll unit-testbar mit Fixtures — inkl. leerer/dünner Daten (Degradation & Cold-Start
  sind getestet, nicht gehofft).
- **`web/routers/health.py`** — neuer dünner Endpoint
  `GET /api/health/scores?days=N` → pro Tag Domain-Scores + Sub-Beiträge + Baseline-
  Kontext + Flags. Adapter über die bestehenden `get_recent_health`-Rows.
- **Narrative** — `health_narrative(scored_today) -> str` (in `core/skills/health.py`
  oder daneben), via LLM, on-demand + täglich gecacht. Zusätzlich als Voice-Intent
  verdrahtet („wie ist meine recovery heute").

**Frontend = nur rendern** (`apps/desktop/src/`):
- **Kompaktes `health`-Widget**: 4 Domain-Ringe als Glance im HUD. Neuer `case 'health'`
  in `renderWidget()`.
- **Vollbild `health-overlay.ts`** nach dem `nav-overlay`-Muster (erstes Content-Overlay,
  wird in SP1 generalisiert). Layout **Ring-Hero** (visuell bestätigt):
  - Oben: 4 Domain-Ringe (Recovery/Sleep/Activity/Body).
  - Darunter: Mantis-Klartext-Banner.
  - Darunter: Metrik-Raster (HRV, Ruhepuls, Tiefschlaf, Schritte, Load, Gewicht …).
  - **Drilldown** (Klick auf Ring): großer Ring + „vs. Baseline"; „Woraus sich X ergibt"
    (Sub-Metriken mit Balken/Sub-Score/Gewicht); Domain-Verlaufsgraph mit Baseline-Band;
    **Mini-Graph pro Sub-Metrik**; Zeitraum-Umschalter 14/30/90 T; Mantis-Read.
  - **Leer-Zustand**: gestrichelter Ring + „—" + erklärender Text statt Fake-Score.
- Charts mit Bordmitteln (SVG, wie `fx/`, sleep-bars, gauge-row) — **kein CDN** (lokal-first).

**Datenfluss:** COROS → COROS-App → Apple Health → BodyOS-Push → `/api/health/push` → DB
→ `health_scores` → `/api/health/scores` → Widget/Overlay/Voice.

## Isolation / Unit-Grenzen

1. `health_scores.py` — reine Score-Logik. Input: Rows + Config. Output: ScoredDay. Kein I/O. ← Herzstück, TDD.
2. Baseline-Statistik — reine Funktion, isoliert testbar.
3. `/api/health/scores` — dünner Adapter (DB-Rows → Score-Funktion → JSON).
4. `health_narrative` — separat, LLM-gestützt, aus ScoredDay.
5. Frontend `health-overlay` / `health`-Widget — render-only, konsumiert `/api/health/scores`.

Jede Einheit ist unabhängig verständlich und testbar.

## Testing

- **Backend (TDD, führend):** Unit-Tests für Score-Normalisierung, Domain-Aggregation,
  **Degradation** (fehlende Metriken → Renormierung / „zu wenig Daten"), **Cold-Start**
  (Richtwert-Fallback), Baseline-Berechnung. Fixtures mit vollen, dünnen und leeren Rows.
- **Router:** Test gegen bekannte Rows → erwartetes JSON.
- **Frontend:** vitest fürs Rendern (Ringe, Drilldown, Leer-Zustand), analog vorhandener
  `apps/desktop/src/*.test.ts`.

## Roadmap-Abhängigkeit (separat, kein Blocker)

- **BodyOS-Health-Sync reparieren** — HRV/Ruhepuls/Schlafphasen fließen aktuell nicht
  (nur 3/14 Tage, Kernmetriken leer). Ursache untersuchen: BodyOS-HealthKit-Background-
  Delivery, COROS→Apple-Health-Freigaben, `/api/health/push`-Pfad, DB. Wird als
  ROADMAP-Punkt geführt; SP4 wird ohne diesen Fix gebaut und getestet.

## Offene Detail-Punkte (im Implementierungsplan zu fixieren)

- Genaue Cold-Start-Schwelle N (Vorschlag 14 Tage) und Degradations-Schwelle (Vorschlag
  50 % Domain-Gewicht).
- Konkrete Normalisierungskurve (z.B. lineares Mapping über ±2σ vs. Sigmoid) — im Plan
  festzulegen, gut A/B-testbar über Fixtures.
- Body-Domain: als 0–100-Score vs. reiner Trend-Indikator (Tendenz: Trend + Ziel-Score).
