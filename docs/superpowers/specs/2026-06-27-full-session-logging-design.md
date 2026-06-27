# Volle Session-Kontrolle (Logging v2) — Design / Spec

**Datum:** 2026-06-27
**Scope:** BodyOS-Trainingsprotokollierung von einem linearen Wizard auf ein editierbares
Hevy/Strong-Listen-Paradigma umstellen — während der Session UND nachträglich im Verlauf.
Inkl. RPE/Warmup/Failure pro Satz und „letztes Mal"-Anzeige.

Baut auf dem Trainingszyklus + Adaptiv-Plan v2 auf. Ändert nur, **wie** ein Training
protokolliert wird, nicht den Plan/Zyklus.

---

## Ziel

Aus der starren „ein Satz nach dem anderen"-Führung wird eine vollwertige Gym-App-Protokollierung:
Sätze frei hinzufügen/löschen/ändern, Übungen tauschen/entfernen/hinzufügen, jeden Satz mit
RPE/Warmup/Failure markieren, und sehen „was hatte ich letztes Mal". Abgeschlossene Trainings
sind im Verlauf editierbar.

## 1. Backend-Datenmodell

`workout_sets` erhält drei Spalten (Migration ans Ende der `MIGRATIONS`-Liste, idempotent):
```sql
ALTER TABLE workout_sets ADD COLUMN IF NOT EXISTS rpe INT;
ALTER TABLE workout_sets ADD COLUMN IF NOT EXISTS is_warmup BOOLEAN DEFAULT FALSE;
ALTER TABLE workout_sets ADD COLUMN IF NOT EXISTS is_failure BOOLEAN DEFAULT FALSE;
```

**Einheitliche Satz-Payload** (POST create + PUT replace):
`{exercise, set_index, reps, weight_kg, rpe?, is_warmup?, is_failure?}`.

`domains/fitness.py` → `log_workout`: Set-Insert um `rpe, is_warmup, is_failure` erweitern
(aus dem Set-Dict, Defaults: rpe None, Flags False). Warmup-Sätze werden jetzt **mitgespeichert**
(nicht mehr vor dem Senden rausgefiltert), markiert über `is_warmup=true`.

Neue Funktion `domains/fitness.py`:
- `update_workout(workout_id, title, notes, rpe, sets) -> None` — ersetzt Titel/Notiz/RPE und
  löscht+schreibt die Sätze neu (atomar). Für nachträgliches Editieren.
- `delete_workout(workout_id) -> None` — löscht Workout + zugehörige Sätze.
- `last_sets_for(exercise_name) -> list[dict]` — Arbeitssätze (`is_warmup=false`) der jüngsten
  Session mit dieser Übung, je `{reps, weight_kg}`.

## 2. Neue Endpoints (`web/routers/fitness.py`)

- `GET /api/workouts/{wid}` — ein Training mit allen Sätzen (inkl. neue Felder).
- `PUT /api/workouts/{wid}` — Body `{title?, notes?, rpe?, sets:[…]}` → `update_workout`.
- `DELETE /api/workouts/{wid}` — `delete_workout`.
- `GET /api/fitness/last-sets?exercise=NAME` — `last_sets_for`.

`POST /api/workouts` (bestehend) akzeptiert zusätzlich die neuen Satz-Felder (über das
erweiterte `log_workout`). Cycle-Event-Hook bleibt unverändert.

## 3. Session-UI (ActiveSessionView neu)

Der Wizard (`ExerciseSetLogView` + `RPESliderView` Schritt-für-Schritt) wird durch eine
scrollbare **Übungsliste** ersetzt:

- **Übungskarte:** Name, „Letztes Mal: 80 kg × 6" (aus `last-sets`), Liste von Satz-Zeilen.
- **Satz-Zeile:** Satz-Nr · Gewicht-Feld · Wdh-Feld · optional RPE · **✓ erledigt** ·
  **W** (Warmup-Toggle) · **F** (Failure-Toggle). Swipe-to-delete pro Satz.
- **„+ Satz"** je Übung (kopiert Werte der letzten Zeile als Vorschlag).
- **Übungsmenü** (•••): „Übung tauschen" (Picker aus `/api/fitness/exercises`),
  „Übung entfernen" (Bestätigung).
- **„+ Übung"** am Listenende (Picker aus Bibliothek).
- **Rest-Timer:** startet beim Abhaken eines Arbeitssatzes (per-Übung `rest_sec`), wegtippbar.
- **Toolbar:** Zeit · „Abbrechen" (Bestätigung, bereits vorhanden) · „Fertig".
- **„Fertig"** → `POST /api/workouts` mit allen als erledigt markierten Sätzen
  (reps/weight_kg/rpe/is_warmup/is_failure), Titel = Tageslabel, Notiz optional.
- **RPE pro Satz** ersetzt den separaten RPE-Slider-Screen. Der **Skip-Button entfällt** — die
  Wizard-Schritte gibt es nicht mehr; „Übung entfernen" deckt das Überspringen ab.

### Session-Modell + Persist/Resume
`ActiveSession` wird auf das Listen-Modell umgestellt: eine Liste von Übungen, je mit einer
Liste editierbarer Sätze (`SessionSet { weight, reps, rpe?, isWarmup, isFailure, done }`).
Bleibt `Codable`; die bestehende Persist/Resume-Logik (Cache-Key `active_session`) speichert
das neue Modell und stellt es beim App-Start wieder her.

## 4. Verlauf editierbar

`WorkoutHistoryCard` → Tap → neue `WorkoutDetailView`:
- Lädt das Training via `GET /api/workouts/{wid}`.
- Zeigt dieselbe editierbare Satzliste (Übungen + Sätze, inkl. RPE/Warmup/Failure).
- **Speichern** → `PUT /api/workouts/{wid}` (Sätze ändern/löschen, Titel/Notiz/RPE).
- **Training löschen** → `DELETE /api/workouts/{wid}` (mit Bestätigung), zurück zum Verlauf.

## 5. Testing

- **Backend pure/integration:**
  - Migration idempotent (zweimal `run_migrations` ohne Fehler, Spalten existieren).
  - `log_workout` mit neuen Feldern → `workout_sets` enthält rpe/is_warmup/is_failure.
  - `update_workout` ersetzt Sätze korrekt (alte weg, neue da).
  - `delete_workout` entfernt Workout + Sätze.
  - `last_sets_for` liefert nur Arbeitssätze der jüngsten Session.
  - Bestehende Tests bleiben grün.
- **App:** Build + Deploy + manuelle Sichtung: Session (add/remove/edit/swap, W/F/RPE, letztes
  Mal, Rest), Verlauf-Edit (öffnen, ändern, speichern, löschen).

## Nicht in diesem Scope (YAGNI)

- Supersätze/Dropsätze als eigene Konstrukte.
- Übungs-Detailstatistik/Charts pro Übung (separates Feature).
- Plan-Änderungen (gehört zu Plan-v2, bereits erledigt).
