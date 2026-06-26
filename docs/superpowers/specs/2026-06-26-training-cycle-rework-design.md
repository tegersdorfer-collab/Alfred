# Trainingsplan-Umbau — Design / Spec

**Datum:** 2026-06-26
**Scope:** BodyOS Trainingsplan auf festen 3-Tage-Zyklus umstellen, abschluss-basiert,
mit Restday-Funktion. Joggen raus aus dem loggbaren Training (läuft über Strava).

---

## Ziel

Timo trainiert nach einem festen, sich wiederholenden Split: **LOWER → JOGGEN → UPPER**.
Joggen wird über die Coros Pace 4 + Strava aufgezeichnet, **nicht** in BodyOS geloggt —
in BodyOS erscheint der Jog-Tag nur als Übersicht. Krafttraining (LOWER/UPPER) wird in
BodyOS geloggt. Bei Bedarf kann ein Restday eingeschoben werden, der den Plan pausiert.

## Kern-Mechanik (abschluss-basiert)

Fester Zyklus: `CYCLE = ["lower", "jog", "upper"]`, wiederholend.

Der Zeiger („was ist als Nächstes dran") rückt **nur vor, wenn der aktuelle Slot
erledigt ist** — nicht kalendergetrieben. Lässt Timo einen Tag aus ohne ihn zu erledigen,
bleibt derselbe Slot dran.

| Slot   | Erledigt durch                                          | Wirkung            |
|--------|---------------------------------------------------------|--------------------|
| LOWER  | Krafttraining in BodyOS geloggt                         | Zeiger → JOGGEN    |
| JOGGEN | Auto via HealthKit (Coros-Lauf) — Button als Fallback   | Zeiger → UPPER     |
| UPPER  | Krafttraining in BodyOS geloggt                         | Zeiger → LOWER     |
| —      | Button „Restday"                                        | Zeiger **bleibt**  |

**Joggen-Auto-Erkennung (HealthKit):** Die Coros Pace 4 schreibt Läufe via Coros-App in
Apple Health. BodyOS liest am Jog-Tag die heutigen Lauf-Workouts (`HKWorkout`,
Activity `.running`) und ruft bei einem gefundenen Lauf automatisch `jog-done` auf
(mit Distanz/Dauer). Findet sich kein Lauf, bleibt der manuelle Button „✓ Joggen erledigt"
als Fallback.

**Restday = reine Pause.** Wird als bewusster Ruhetag geloggt (damit Alfred nicht nachfragt),
der Zeiger rückt **nicht** vor — am nächsten Tag ist derselbe Slot dran. Timo verschiebt
sein Training nur nach hinten, überspringt es nicht.

**„Heute schon erledigt"-Zustand:** Wenn der letzte zyklus-vorrückende Event von *heute*
ist, zeigt BodyOS „✓ LOWER erledigt — morgen: Joggen" statt erneut zum Training aufzufordern.

## Datenmodell — eine Quelle der Wahrheit

Neue Tabelle:

```sql
CREATE TABLE training_cycle_events (
    id    SERIAL PRIMARY KEY,
    date  DATE NOT NULL DEFAULT CURRENT_DATE,
    slot  TEXT NOT NULL,              -- 'lower' | 'jog' | 'upper'
    kind  TEXT NOT NULL,              -- 'workout' | 'jog' | 'rest'
    created_at TIMESTAMPTZ DEFAULT now()
);
```

- LOWER/UPPER-Workout geloggt → zusätzlich ein `kind='workout'`-Event.
- „Joggen erledigt" → `kind='jog'`-Event.
- Restday → `kind='rest'`-Event.

**Zeiger-Ableitung:** Letztes Event mit `kind != 'rest'` holen, Zeiger = `CYCLE[(index+1) % 3]`.
Kein Event → Start bei `lower`. Stateless abgeleitet, übersteht Neustarts, liefert Verlauf
gratis.

**Wichtig:** Jog-Marker landen **nicht** in der `workouts`-Tabelle. Kraft-Statistik,
Volumen und Heatmap bleiben dadurch frei von Lauf-Daten.

## Backend-Änderungen (`web/routers/fitness.py`, `domains/fitness.py`)

### `/api/fitness/today-plan` (umgebaut)
- Zyklus-Reihenfolge: `["lower", "jog", "upper"]` (vorher `["upper","jog","lower"]`).
- Zeiger aus `training_cycle_events` ableiten statt aus letztem `workouts`-Eintrag.
- **Jog-Tag** liefert: keine `exercises`, dafür `day_type="jog"`, Hinweistext
  „Heute: Joggen — läuft über Strava". Kein `distance_km`/`pace_target` mehr.
- **LOWER/UPPER**: unverändert HRV+Schlaf → Intensitäts-Faktor und Progressive Overload
  aus dem letzten Satz (bestehende `build_sets`-Logik bleibt).
- Neue Felder im Response: `done_today: bool`, `next_label: str`.

### Neue Endpoints
- `POST /api/fitness/jog-done` → schreibt `jog`-Event, rückt Zeiger vor. Optionaler Body
  `{distance_km, duration_min, source}` (`source ∈ {healthkit, manual}`). Idempotent pro Tag:
  existiert heute schon ein `jog`-Event, kein zweites schreiben.
- `POST /api/fitness/rest-day` → schreibt `rest`-Event (Zeiger bleibt).

### `POST /api/workouts` (erweitert)
- Wenn das geloggte Workout ein Zyklus-Tag ist (`type ∈ {lower, upper}`), zusätzlich ein
  `workout`-`training_cycle_events`-Event schreiben.

### Hardcodierte Übungslisten (Default, später von Alfred überschreibbar)
- **LOWER**: Squat, Romanian Deadlift, Leg Press, Leg Curl, Calf Raise
- **UPPER**: Bench Press, Overhead Press, Barbell Row, Dumbbell Curl, Tricep Pushdown, Lateral Raise

## App-Änderungen (BodyOS)

### `WorkoutView` — drei Zustände statt einem
1. **Kraft-Tag** (LOWER/UPPER): wie bisher (Header, Alfred-Karte, Health, Übungsliste,
   „Training starten") + **Restday-Button**.
2. **Jog-Tag**: Info-Karte „Heute: Joggen — läuft über Strava". Beim Öffnen fragt BodyOS
   HealthKit nach einem heutigen Lauf; gefunden → automatisch `jog-done` (Distanz/Dauer)
   und Wechsel in Zustand 3 mit „✓ Lauf erkannt (X km)". Kein Lauf → manueller Button
   **„✓ Joggen erledigt"**. Plus **Restday-Button**. Keine Set-Logging-UI.
3. **Erledigt heute**: kompakte Karte „✓ <Slot> erledigt — morgen: <next_label>".

### Model `TodayPlan`
- Neue Felder: `doneToday: Bool`, `nextLabel: String`.
- `PlannedSet`: `distanceKm`/`paceTarget` können bleiben (werden für Jog nicht mehr befüllt),
  optional später entfernen.

### Neue API-Calls (`FitnessAPI.swift`)
- `markJogDone(distanceKm:durationMin:source:)` → `POST /api/fitness/jog-done`
- `markRestDay()` → `POST /api/fitness/rest-day`

### HealthKit (`HealthKitManager.swift`)
- `HKWorkoutType.workoutType()` zu `readTypes` hinzufügen.
- Neue Methode `fetchTodayRun() async -> (distanceKm: Double, durationMin: Int)?` —
  `HKSampleQuery` auf `HKWorkout` mit `HKQuery.predicateForWorkouts(with: .running)` +
  heutigem Zeitfenster, jüngsten Lauf zurückgeben.
- Info.plist: `NSHealthShareUsageDescription` muss vorhanden sein (für bestehende
  Health-Reads ohnehin nötig — verifizieren).

### Dashboard (`web/index.html`)
- Zieht denselben `today-plan` → bleibt automatisch synchron. Keine Doppel-Logik.

## Testing

- `training_cycle_events`-Ableitung: leere Tabelle → `lower`; nach `workout/lower` → `jog`;
  nach `jog` → `upper`; nach `rest` → Slot unverändert.
- „done_today": Event von heute → `done_today=True` + korrektes `next_label`.
- Jog-Tag liefert leere `exercises` + Hinweistext.
- Kraft-Workout-Log schreibt genau ein Cycle-Event.
- Bestehende Tests (Volumen, Progression) dürfen nicht brechen (Jog raus aus `workouts`).

---

## Future / Phase 2+ (NICHT in diesem Scope — nur Architektur offen halten)

Diese Punkte werden jetzt **nicht** gebaut, das Datenmodell soll sie aber nicht verbauen:

1. **Sport-Habit auto-abhaken** — Wenn die heutige Trainingseinheit (LOWER/UPPER geloggt
   oder Joggen erledigt) erledigt ist, automatisch den „Sport"-Habit via
   `habits.log_habit()` abhaken. Kleiner Fast-Follow, hängt am selben
   „Slot erledigt"-Event.

2. **Alfred-generierte, adaptive Pläne** — Alfred erstellt individuelle Pläne (z.B. 6 Wochen
   fester Block, danach neue Übungen). Da die App Übungen rein server-seitig aus `today-plan`
   rendert (kein Xcode-Rebuild nötig) und `ensure_exercise()` Übungen in die Bibliothek
   schreiben kann, ist das reine Backend-Arbeit. Aufsetzbar auf bestehendem
   `save_training_plan()` / `active_plan()`.

3. **Lauf-Import handy-unabhängig machen** — Die HealthKit-Bridge (in diesem Scope) synct
   nur, wenn BodyOS mal offen ist. Wenn das nicht reicht, später auf server-seitiges
   **Strava API Polling** upgraden: Idle-Loop pollt `GET /athlete/activities`, läuft auch
   wenn das Handy schläft. Braucht einmal OAuth + Refresh-Token in `.env`. Docked an
   denselben `jog-done`-Endpoint. (Strava-Webhooks wären Push, brauchen aber eine
   öffentliche URL / Cloudflare Tunnel — Overkill für den lokalen/Tailscale-Setup.)
