# Volle Session-Kontrolle (Logging v2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BodyOS-Protokollierung auf ein editierbares Hevy/Strong-Listen-Paradigma umstellen (Session + Verlauf), mit RPE/Warmup/Failure pro Satz und „letztes Mal"-Anzeige.

**Architecture:** Backend bekommt drei neue `workout_sets`-Spalten + Funktionen für Replace/Delete/last-sets + vier Endpoints. Die App ersetzt den linearen Wizard durch eine editierbare Übungsliste (gemeinsames Satz-Modell für Session und Verlaufs-Detail).

**Tech Stack:** Python/FastAPI, Postgres, SwiftUI, pytest.

## Global Constraints

- Einheitliche Satz-Payload: `{exercise, set_index, reps, weight_kg, rpe?, is_warmup?, is_failure?}`.
- Warmup-Sätze werden gespeichert (`is_warmup=true`), nicht mehr rausgefiltert.
- Migration ans Ende der `MIGRATIONS`-Liste in `core/db.py`, idempotent (`IF NOT EXISTS`).
- DB nur über `core.db`. iOS-Build: `DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer`, `-allowProvisioningUpdates`, Device-ID `00008140-00161DEE11EB801C`.
- today-plan/Zyklus/Plan-v2 bleiben unangetastet.

---

### Task 1: Backend — Migration + Satz-Normalisierung + log_workout-Felder

**Files:**
- Modify: `core/db.py` (Migration ans Ende der `MIGRATIONS`-Liste)
- Modify: `domains/fitness.py` (`normalize_set` neu, `log_workout` Set-Insert)
- Test: `tests/test_fitness.py` (`TestNormalizeSet`)

**Interfaces:**
- Produces: `fitness.normalize_set(raw: dict) -> dict` — `{exercise, set_index, reps, weight_kg, rpe, is_warmup, is_failure}` mit Defaults/Clamps.

- [ ] **Step 1: Failing test**

Ans Ende von `tests/test_fitness.py`:
```python
class TestNormalizeSet:
    def test_full_set(self):
        from domains.fitness import normalize_set
        s = normalize_set({"exercise": "Squat", "set_index": 2, "reps": 5,
                           "weight_kg": 100, "rpe": 8, "is_warmup": True, "is_failure": False})
        assert s["exercise"] == "Squat" and s["reps"] == 5 and s["weight_kg"] == 100.0
        assert s["rpe"] == 8 and s["is_warmup"] is True and s["is_failure"] is False

    def test_defaults_and_clamps(self):
        from domains.fitness import normalize_set
        s = normalize_set({"exercise": "Bench", "reps": 999, "rpe": 50})
        assert s["reps"] == 30 and s["rpe"] == 10
        assert s["is_warmup"] is False and s["is_failure"] is False
        assert s["weight_kg"] is None

    def test_missing_exercise_returns_none(self):
        from domains.fitness import normalize_set
        assert normalize_set({"reps": 5}) is None
```

- [ ] **Step 2: FAIL bestätigen**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_fitness.py::TestNormalizeSet -q`
Expected: FAIL (ImportError `normalize_set`)

- [ ] **Step 3: Migration in `core/db.py`**

In der `MIGRATIONS`-Liste vor dem schließenden `]` (nach dem `training_cycle_events`-Index):
```python
    "ALTER TABLE workout_sets ADD COLUMN IF NOT EXISTS rpe INT;",
    "ALTER TABLE workout_sets ADD COLUMN IF NOT EXISTS is_warmup BOOLEAN DEFAULT FALSE;",
    "ALTER TABLE workout_sets ADD COLUMN IF NOT EXISTS is_failure BOOLEAN DEFAULT FALSE;",
```

- [ ] **Step 4: `normalize_set` + `log_workout` in `domains/fitness.py`**

`normalize_set` neu (vor `log_workout`):
```python
def normalize_set(raw: dict) -> dict | None:
    """Validiert/säubert eine Satz-Payload. None wenn keine Übung."""
    if not isinstance(raw, dict):
        return None
    name = (raw.get("exercise") or "").strip()
    if not name:
        return None
    def _i(v, lo, hi):
        try:
            return max(lo, min(hi, int(v)))
        except (TypeError, ValueError):
            return None
    w = raw.get("weight_kg")
    try:
        w = float(w) if w is not None else None
    except (TypeError, ValueError):
        w = None
    return {
        "exercise": name,
        "set_index": raw.get("set_index"),
        "reps": _i(raw.get("reps"), 0, 30),
        "weight_kg": w,
        "rpe": _i(raw.get("rpe"), 1, 10),
        "is_warmup": bool(raw.get("is_warmup", False)),
        "is_failure": bool(raw.get("is_failure", False)),
    }
```

`log_workout` Set-Insert (Zeile ~83) ersetzen durch (nutzt `normalize_set`):
```python
    for i, s in enumerate(sets or [], 1):
        ns = normalize_set(s)
        if not ns:
            continue
        ex_id = ensure_exercise(ns["exercise"]) if ns["exercise"] else None
        db.execute(
            """INSERT INTO workout_sets
               (workout_id, exercise_id, set_index, reps, weight_kg, rpe, is_warmup, is_failure)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (wid, ex_id, ns["set_index"] or i, ns["reps"], ns["weight_kg"],
             ns["rpe"], ns["is_warmup"], ns["is_failure"]),
        )
    return wid
```
(Die alte Schleife inkl. `distance_km`/`duration_s` ersetzen; diese Felder kamen aus dem
CSV-Import, der `log_workout` ohne diese Set-Keys aufruft — Import-Sätze haben dann
rpe/flags = None/False, was unkritisch ist.)

- [ ] **Step 5: PASS + Migration anwenden**

Run:
```bash
cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_fitness.py::TestNormalizeSet -q
python3 -c "from core import db; db.run_migrations(); print(db.query(\"SELECT column_name FROM information_schema.columns WHERE table_name='workout_sets' AND column_name IN ('rpe','is_warmup','is_failure')\"))"
```
Expected: Tests grün; drei Spalten gelistet.

- [ ] **Step 6: Integration-Smoke (log_workout schreibt neue Felder)**

Run:
```bash
cd /Users/timoegersdorfer/Alfred && python3 -c "
from domains import fitness
from core import db
wid = fitness.log_workout('Test', type_='lower', sets=[
    {'exercise':'Squat','reps':5,'weight_kg':100,'rpe':8,'is_warmup':False},
    {'exercise':'Squat','reps':12,'weight_kg':40,'is_warmup':True}])
rows = db.query('SELECT reps, weight_kg, rpe, is_warmup, is_failure FROM workout_sets WHERE workout_id=%s ORDER BY set_index',(wid,))
print(rows)
db.execute('DELETE FROM workout_sets WHERE workout_id=%s',(wid,)); db.execute('DELETE FROM workouts WHERE id=%s',(wid,))
print('cleaned')"
```
Expected: zwei Zeilen, eine mit rpe=8/is_warmup=False, eine mit is_warmup=True; `cleaned`.

- [ ] **Step 7: Commit**

```bash
git add core/db.py domains/fitness.py tests/test_fitness.py
git commit -m "feat(fitness): per-set rpe/warmup/failure columns + normalize_set"
```

---

### Task 2: Backend — update/delete/last_sets + Endpoints

**Files:**
- Modify: `domains/fitness.py` (`update_workout`, `delete_workout`, `last_sets_for`)
- Modify: `web/routers/fitness.py` (GET/PUT/DELETE `/api/workouts/{wid}`, GET `/api/fitness/last-sets`)

**Interfaces:**
- Consumes: `normalize_set` (Task 1), `ensure_exercise`.
- Produces:
  - `fitness.update_workout(workout_id, title, notes, rpe, sets) -> None`
  - `fitness.delete_workout(workout_id) -> None`
  - `fitness.last_sets_for(exercise_name) -> list[dict]` (je `{reps, weight_kg}`)
  - HTTP: `GET/PUT/DELETE /api/workouts/{wid}`, `GET /api/fitness/last-sets`

- [ ] **Step 1: Funktionen in `domains/fitness.py` (nach `log_workout`)**

```python
def update_workout(workout_id: int, title: str | None = None, notes: str | None = None,
                   rpe: int | None = None, sets: list[dict] | None = None) -> None:
    """Ersetzt Kopf + komplette Satzliste eines Workouts (für nachträgliches Editieren)."""
    if title is not None or notes is not None or rpe is not None:
        db.execute("UPDATE workouts SET title=COALESCE(%s,title), notes=COALESCE(%s,notes), "
                   "rpe=COALESCE(%s,rpe) WHERE id=%s", (title, notes, rpe, workout_id))
    if sets is not None:
        db.execute("DELETE FROM workout_sets WHERE workout_id=%s", (workout_id,))
        for i, s in enumerate(sets, 1):
            ns = normalize_set(s)
            if not ns:
                continue
            ex_id = ensure_exercise(ns["exercise"]) if ns["exercise"] else None
            db.execute(
                """INSERT INTO workout_sets
                   (workout_id, exercise_id, set_index, reps, weight_kg, rpe, is_warmup, is_failure)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (workout_id, ex_id, ns["set_index"] or i, ns["reps"], ns["weight_kg"],
                 ns["rpe"], ns["is_warmup"], ns["is_failure"]))


def delete_workout(workout_id: int) -> None:
    db.execute("DELETE FROM workout_sets WHERE workout_id=%s", (workout_id,))
    db.execute("DELETE FROM workouts WHERE id=%s", (workout_id,))


def last_sets_for(exercise_name: str) -> list[dict]:
    """Arbeitssätze (kein Warmup) der jüngsten Session mit dieser Übung."""
    row = db.query_one(
        """SELECT ws.workout_id FROM workout_sets ws
           JOIN exercises e ON e.id = ws.exercise_id
           JOIN workouts w ON w.id = ws.workout_id
           WHERE LOWER(e.name)=LOWER(%s) AND COALESCE(ws.is_warmup,FALSE)=FALSE
           ORDER BY w.date DESC, w.id DESC LIMIT 1""", (exercise_name,))
    if not row:
        return []
    return db.query(
        """SELECT ws.reps, ws.weight_kg FROM workout_sets ws
           JOIN exercises e ON e.id = ws.exercise_id
           WHERE ws.workout_id=%s AND LOWER(e.name)=LOWER(%s) AND COALESCE(ws.is_warmup,FALSE)=FALSE
           ORDER BY ws.set_index""", (row["workout_id"], exercise_name))
```

- [ ] **Step 2: Endpoints in `web/routers/fitness.py` (vor `return router`)**

```python
    @router.get("/api/workouts/{wid}")
    def workout_detail(wid: int):
        w = db.query_one("SELECT * FROM workouts WHERE id=%s", (wid,))
        if not w:
            return JSONResponse({"error": "not found"}, 404)
        w["sets"] = db.query(
            """SELECT ws.id, ws.set_index, ws.reps, ws.weight_kg, ws.rpe,
                      COALESCE(ws.is_warmup,FALSE) AS is_warmup,
                      COALESCE(ws.is_failure,FALSE) AS is_failure, e.name AS exercise
               FROM workout_sets ws LEFT JOIN exercises e ON e.id=ws.exercise_id
               WHERE ws.workout_id=%s ORDER BY ws.set_index""", (wid,))
        return _jsonable(w)

    @router.put("/api/workouts/{wid}")
    async def workout_update(wid: int, req: Request):
        d = await req.json()
        fitness.update_workout(wid, title=d.get("title"), notes=d.get("notes"),
                               rpe=d.get("rpe"), sets=d.get("sets"))
        return {"ok": True}

    @router.delete("/api/workouts/{wid}")
    def workout_delete(wid: int):
        fitness.delete_workout(wid)
        return {"ok": True}

    @router.get("/api/fitness/last-sets")
    def last_sets(exercise: str = ""):
        return _jsonable(fitness.last_sets_for(exercise)) if exercise else []
```

- [ ] **Step 3: Verifizieren (Import + Tests)**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/ -q && python3 -c "import web.routers.fitness; print('ok')"`
Expected: alle grün, `ok`

- [ ] **Step 4: Integration-Smoke (E2E gegen Server)**

Run:
```bash
cd /Users/timoegersdorfer/Alfred && ./start.sh >/dev/null 2>&1; sleep 5
WID=$(curl -s -X POST localhost:7779/api/workouts -H 'Content-Type: application/json' -d '{"title":"T","type":"lower","sets":[{"exercise":"Squat","reps":5,"weight_kg":100,"rpe":8}]}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "WID=$WID"
curl -s localhost:7779/api/workouts/$WID | python3 -c "import sys,json;d=json.load(sys.stdin);print('sets:',d['sets'])"
curl -s -X PUT localhost:7779/api/workouts/$WID -H 'Content-Type: application/json' -d '{"sets":[{"exercise":"Squat","reps":6,"weight_kg":102.5,"rpe":9}]}' >/dev/null
curl -s "localhost:7779/api/fitness/last-sets?exercise=Squat" | python3 -c "import sys,json;print('last-sets:',json.load(sys.stdin))"
curl -s -X DELETE localhost:7779/api/workouts/$WID >/dev/null
curl -s -o /dev/null -w "nach delete: HTTP %{http_code}\n" localhost:7779/api/workouts/$WID
```
Expected: PUT ersetzt (reps 6 / 102.5), last-sets zeigt den aktualisierten Satz, nach DELETE 404.

- [ ] **Step 5: Commit**

```bash
git add domains/fitness.py web/routers/fitness.py
git commit -m "feat(fitness): workout detail/update/delete + last-sets endpoints"
```

---

### Task 3: BodyOS — Modelle + API-Calls

**Files:**
- Modify: `apps/BodyOS/BodyOS/Models/BodyModels.swift` (Session-Modell neu, Detail-Modelle, Payload)
- Modify: `apps/BodyOS/BodyOS/API/FitnessAPI.swift` (4 Calls)

**Interfaces:**
- Consumes (HTTP): Endpoints aus Task 2.
- Produces (Swift): `SessionSet`, `SessionExercise`, `ActiveSession` (neu), `LogSetPayload` (erweitert), `WorkoutDetail`, `WorkoutDetailSet`; `FitnessAPI.fetchWorkout/updateWorkout/deleteWorkout/lastSets`.

- [ ] **Step 1: Session-Modell in `BodyModels.swift` ersetzen**

`LoggedSet` und `ActiveSession` (alte Wizard-Structs) ersetzen durch das Listen-Modell:
```swift
struct SessionSet: Identifiable, Codable {
    var id = UUID()
    var weight: Double = 0
    var reps: Int = 0
    var rpe: Int? = nil
    var isWarmup: Bool = false
    var isFailure: Bool = false
    var done: Bool = false
}

struct SessionExercise: Identifiable, Codable {
    var id = UUID()
    var name: String
    var sets: [SessionSet] = []
}

struct ActiveSession: Codable {
    var dayType: String
    var dayLabel: String
    var exercises: [SessionExercise] = []
    var startTime: Date = Date()
    var notes: String = ""
    var elapsedSeconds: Int { Int(Date().timeIntervalSince(startTime)) }
}
```

- [ ] **Step 2: Payload + Detail-Modelle ergänzen**

`LogSetPayload` ersetzen + neue Detail-Modelle:
```swift
struct LogSetPayload: Encodable {
    let exercise: String
    let setIndex: Int
    let reps: Int?
    let weightKg: Double?
    let rpe: Int?
    let isWarmup: Bool
    let isFailure: Bool
}

struct WorkoutDetail: Decodable {
    let id: Int
    let title: String
    let type: String
    let notes: String?
    let rpe: Int?
    let sets: [WorkoutDetailSet]
}

struct WorkoutDetailSet: Identifiable, Decodable {
    let id: Int
    let exercise: String?
    let reps: Int?
    let weightKg: Double?
    let rpe: Int?
    let isWarmup: Bool
    let isFailure: Bool
}

struct LastSet: Decodable { let reps: Int?; let weightKg: Double? }
```
(`LogWorkoutRequest` behält `title/type/durationMin/notes/rpe/sets` — `sets` ist jetzt
`[LogSetPayload]` mit den neuen Feldern.)

- [ ] **Step 3: API-Calls in `FitnessAPI.swift` (vor schließender `}`)**

```swift
    func fetchWorkout(_ id: Int) async throws -> WorkoutDetail {
        try await client.get("/api/workouts/\(id)")
    }
    func updateWorkout(_ id: Int, body: UpdateWorkoutRequest) async throws {
        let _: OkResponse = try await client.put("/api/workouts/\(id)", body: body)
    }
    func deleteWorkout(_ id: Int) async throws {
        try await client.delete("/api/workouts/\(id)")
    }
    func lastSets(exercise: String) async throws -> [LastSet] {
        let enc = exercise.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? exercise
        return try await client.get("/api/fitness/last-sets?exercise=\(enc)")
    }
```
Und `UpdateWorkoutRequest` in `BodyModels.swift`:
```swift
struct UpdateWorkoutRequest: Encodable {
    let title: String?
    let notes: String?
    let rpe: Int?
    let sets: [LogSetPayload]
}
```

- [ ] **Step 4: Build (Compile-Check)** — erwartet rote Stellen in den Views, die Task 4/5 fixen

Run:
```bash
cd /Users/timoegersdorfer/Alfred
DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer xcodebuild \
  -project apps/BodyOS/BodyOS.xcodeproj -scheme BodyOS \
  -destination 'platform=iOS,id=00008140-00161DEE11EB801C' -configuration Release \
  -allowProvisioningUpdates build 2>&1 | grep -E "error:" | head
```
Expected: Fehler nur in `ActiveSessionView.swift`/`WorkoutView.swift` (nutzen das alte Modell) — werden in Task 4/5 behoben. Keine Fehler in BodyModels/FitnessAPI.

- [ ] **Step 5: Commit**

```bash
git add apps/BodyOS/BodyOS/Models/BodyModels.swift apps/BodyOS/BodyOS/API/FitnessAPI.swift
git commit -m "feat(BodyOS): list-based session model + workout detail/last-sets API"
```

---

### Task 4: BodyOS — Session-UI als editierbare Liste

**Files:**
- Rewrite: `apps/BodyOS/BodyOS/Views/ActiveSessionView.swift`
- Modify: `apps/BodyOS/BodyOS/Views/WorkoutView.swift` (`startSession` baut neues Modell; Resume bleibt)

**Interfaces:**
- Consumes: `ActiveSession`/`SessionExercise`/`SessionSet`, `FitnessAPI.logWorkout/lastSets/fetchExercises`, `RestTimer`.

**Komponenten & Verhalten (vollständig umzusetzen):**

- `ActiveSessionViewModel` (ObservableObject): hält `@Published var session: ActiveSession`,
  `restTimer`, `cacheKey="active_session"`, `onComplete`. Methoden:
  - `persist()` → `OfflineCache.shared.save(session, key: cacheKey)` (nach jeder Mutation aufrufen).
  - `addSet(toExercise idx)` → kopiert Werte des letzten Satzes als Vorschlag, `append`, persist.
  - `deleteSet(ex, set)` / `addExercise(name)` / `removeExercise(idx)` / `swapExercise(idx, newName)` → mutieren + persist.
  - `toggleDone(ex, set)` → set.done umschalten; wenn jetzt done & nicht Warmup → `restTimer.start(seconds: restFor(ex))`; persist.
  - `finish()` → baut `[LogSetPayload]` aus allen `done`-Sätzen (setIndex = laufende Nr pro Übung,
    Reihenfolge der Übungen), `FitnessAPI.logWorkout(...)`, bei Erfolg `OfflineCache.clear(cacheKey)` + `onComplete()`.
  - `cancel()` → `restTimer.stop()`, `OfflineCache.clear(cacheKey)`, `onComplete()`.
  - `restFor(ex)` → fester Default 90 (rest_sec lebt im Plan, nicht in `SessionExercise`; optional
    später durchreichen — hier 90 als sinnvoller Default).
- `ActiveSessionView` (List/ScrollView):
  - Pro `SessionExercise` eine Section: Header = Name + `lastSetHint` (via `.task`
    `FitnessAPI.lastSets(exercise:)` laden, anzeigen „Letztes Mal: 100 kg × 5") + Menü-Button (•••)
    mit „Übung tauschen" (zeigt Exercise-Picker-Sheet) und „Übung entfernen" (confirmationDialog).
  - Satz-Zeilen: Index, `TextField`/Stepper für Gewicht + Wdh, kleines RPE-Feld (optional),
    Toggles W/F, ✓-Button (`toggleDone`). `.swipeActions` → Satz löschen.
  - „+ Satz" je Section; „+ Übung" am Ende (öffnet Exercise-Picker-Sheet).
  - `RestTimerView` als Overlay/Section wenn `restTimer.isRunning`.
  - Toolbar: links „Abbrechen" (confirmationDialog → `vm.cancel()`), Mitte Zeit (`elapsedDisplay`),
    rechts „Fertig" (→ `vm.finish()`).
  - Exercise-Picker-Sheet: lädt `FitnessAPI.fetchExercises()`, durchsuchbare Liste, Auswahl ruft
    `addExercise`/`swapExercise`.
  - `RPESliderView` und der alte `ExerciseSetLogView`/Wizard werden entfernt.
- `RestTimerView` aus der alten Datei bleibt erhalten (wiederverwendet).

- [ ] **Step 1: `ActiveSessionView.swift` neu schreiben** gemäß obiger Komponenten/Verhalten.
  `RestTimerView` beibehalten, `RPESliderView` + `ExerciseSetLogView` entfernen.

- [ ] **Step 2: `WorkoutView.startSession()` ans neue Modell anpassen**

In `apps/BodyOS/BodyOS/Views/WorkoutView.swift` `startSession()` ersetzen durch:
```swift
    func startSession() {
        guard let plan else { return }
        let exs = plan.exercises.map { ex in
            SessionExercise(name: ex.name, sets: ex.workingSets.map {
                SessionSet(weight: $0.weight ?? 0, reps: $0.reps ?? 0)
            })
        }
        activeSession = ActiveSession(dayType: plan.dayType, dayLabel: plan.dayLabel, exercises: exs)
    }
```
Die Resume-Logik im `.task` (lädt `ActiveSession` aus dem Cache) bleibt unverändert — sie
dekodiert jetzt das neue Modell.

- [ ] **Step 3: Build + Deploy**

Run:
```bash
cd /Users/timoegersdorfer/Alfred
DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer xcodebuild \
  -project apps/BodyOS/BodyOS.xcodeproj -scheme BodyOS \
  -destination 'platform=iOS,id=00008140-00161DEE11EB801C' -configuration Release \
  -allowProvisioningUpdates build 2>&1 | grep -E "BUILD SUCCEEDED|BUILD FAILED|error:" | head
APP_PATH=$(find ~/Library/Developer/Xcode/DerivedData/BodyOS-* -name "BodyOS.app" -path "*/Release-iphoneos/*" | head -1)
DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer xcrun devicectl device install app --device 00008140-00161DEE11EB801C "$APP_PATH" 2>&1 | grep -E "installed|error" | head -1
```
Expected: `BUILD SUCCEEDED` + `App installed`. (Compile-Fehler iterativ fixen.)

- [ ] **Step 4: Commit**

```bash
git add apps/BodyOS/BodyOS/Views/ActiveSessionView.swift apps/BodyOS/BodyOS/Views/WorkoutView.swift
git commit -m "feat(BodyOS): editable list-based workout session (add/remove/edit/swap sets)"
```

---

### Task 5: BodyOS — editierbarer Verlauf

**Files:**
- Create: `apps/BodyOS/BodyOS/Views/WorkoutDetailView.swift`
- Modify: `apps/BodyOS/BodyOS/Views/WorkoutView.swift` (History-Card → NavigationLink auf Detail)
- Modify: `apps/BodyOS/BodyOS.xcodeproj/project.pbxproj` (neue Datei registrieren)

**Interfaces:**
- Consumes: `FitnessAPI.fetchWorkout/updateWorkout/deleteWorkout`, `WorkoutDetail`/`WorkoutDetailSet`.

**Komponente `WorkoutDetailView`:**
- `init(workoutId: Int, onChange: () -> Void)`; `.task` lädt `fetchWorkout`.
- Zeigt editierbare Satzliste (gruppiert nach Übung): Gewicht/Wdh/RPE editierbar, W/F-Toggles,
  Swipe-to-delete pro Satz.
- Toolbar „Speichern" → `updateWorkout(id, UpdateWorkoutRequest(title:nil,notes:nil,rpe:nil,sets:…))`
  mit allen aktuellen Sätzen; danach `onChange()` + dismiss.
- „Training löschen" (confirmationDialog) → `deleteWorkout(id)` + `onChange()` + dismiss.

- [ ] **Step 1: `WorkoutDetailView.swift` anlegen** gemäß Komponente.

- [ ] **Step 2: In `WorkoutView` die History-Card verlinken**

Im `historyContent` die `WorkoutHistoryCard(item: item)` in einen `NavigationLink` wickeln:
```swift
                            NavigationLink {
                                WorkoutDetailView(workoutId: item.id) {
                                    Task { await vm.loadHistory() }
                                }
                            } label: {
                                WorkoutHistoryCard(item: item)
                            }
                            .buttonStyle(.plain)
```

- [ ] **Step 3: Datei in pbxproj registrieren**

In `apps/BodyOS/BodyOS.xcodeproj/project.pbxproj` analog zu den anderen View-Dateien
(`BF16` BodySettingsView) eine PBXBuildFile + PBXFileReference + Eintrag in der Views-`PBXGroup`
(`BGRPE`) + in der Sources-`PBXSourcesBuildPhase` (`BBP0`) für `WorkoutDetailView.swift` ergänzen
(neue IDs `BF18`/`BA18`).

- [ ] **Step 4: Build + Deploy**

Run:
```bash
cd /Users/timoegersdorfer/Alfred
DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer xcodebuild \
  -project apps/BodyOS/BodyOS.xcodeproj -scheme BodyOS \
  -destination 'platform=iOS,id=00008140-00161DEE11EB801C' -configuration Release \
  -allowProvisioningUpdates build 2>&1 | grep -E "BUILD SUCCEEDED|BUILD FAILED|error:" | head
APP_PATH=$(find ~/Library/Developer/Xcode/DerivedData/BodyOS-* -name "BodyOS.app" -path "*/Release-iphoneos/*" | head -1)
DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer xcrun devicectl device install app --device 00008140-00161DEE11EB801C "$APP_PATH" 2>&1 | grep -E "installed|error" | head -1
```
Expected: `BUILD SUCCEEDED` + `App installed`.

- [ ] **Step 5: Commit**

```bash
git add apps/BodyOS/BodyOS/Views/WorkoutDetailView.swift apps/BodyOS/BodyOS/Views/WorkoutView.swift apps/BodyOS/BodyOS.xcodeproj/project.pbxproj
git commit -m "feat(BodyOS): editable workout history detail (PUT/DELETE)"
```

---

### Task 6: End-to-End-Verifikation + Spec-Abgleich

**Files:** keine (nur Verifikation)

- [ ] **Step 1: Alle Tests grün**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/ -q`
Expected: alle grün.

- [ ] **Step 2: Backend-Roundtrip (Session-Save mit Flags → Verlauf → Edit → Delete)**

Run:
```bash
cd /Users/timoegersdorfer/Alfred
WID=$(curl -s -X POST localhost:7779/api/workouts -H 'Content-Type: application/json' -d '{"title":"Lower · A","type":"lower","sets":[{"exercise":"Kniebeugen Langhantel","reps":5,"weight_kg":100,"rpe":8,"is_warmup":false,"is_failure":true},{"exercise":"Kniebeugen Langhantel","reps":12,"weight_kg":40,"is_warmup":true}]}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s localhost:7779/api/workouts/$WID | python3 -c "import sys,json;d=json.load(sys.stdin);print([(s['reps'],s['weight_kg'],s['rpe'],s['is_warmup'],s['is_failure']) for s in d['sets']])"
curl -s -X DELETE localhost:7779/api/workouts/$WID >/dev/null
echo "Test-Workout entfernt"
```
Expected: Sätze inkl. rpe/is_warmup/is_failure korrekt; danach gelöscht.

- [ ] **Step 3: Manuelle Sichtung am iPhone**

BodyOS → Training starten: Übungsliste, Satz hinzufügen/löschen, Gewicht/Wdh ändern, W/F/RPE,
„Letztes Mal", Rest-Timer, Übung tauschen/entfernen, Fertig → erscheint im Verlauf.
Verlauf → Training antippen → Satz ändern → Speichern; Training löschen.

- [ ] **Step 4: Spec-Abgleich**

`docs/superpowers/specs/2026-06-27-full-session-logging-design.md` durchgehen: Datenmodell,
Endpoints, Session-UI (add/remove/edit/swap, W/F/RPE, letztes Mal, Rest, Skip entfällt),
Verlauf-Edit. Abweichungen notieren.
