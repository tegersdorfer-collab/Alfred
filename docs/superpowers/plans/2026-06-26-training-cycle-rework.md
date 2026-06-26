# Trainingsplan-Umbau Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BodyOS auf festen abschluss-basierten 3-Tage-Zyklus (LOWER → JOGGEN → UPPER) umstellen, mit Restday-Pause und HealthKit-Auto-Erkennung für Läufe.

**Architecture:** Eine Postgres-Tabelle `training_cycle_events` ist die einzige Quelle für die Zyklus-Position. Die Position wird als *pure function* aus der Event-Liste abgeleitet (unit-testbar ohne DB). Das Backend liefert den Tagesplan über `/api/fitness/today-plan`; die BodyOS-App rendert ihn server-getrieben und hakt den Jog-Tag via HealthKit automatisch ab.

**Tech Stack:** Python/FastAPI, Postgres (psycopg), SwiftUI, HealthKit, pytest.

## Global Constraints

- `.env` ist gitignored und wird NIE committet — nur `.env.example` geht zu GitHub.
- Zyklus-Reihenfolge exakt: `CYCLE = ["lower", "jog", "upper"]`.
- Jog-Events landen NICHT in `workouts` — nur in `training_cycle_events`. Kraft-Statistik bleibt rein.
- DB-Zugriff nur über `core.db` (`db.query`, `db.query_one`, `db.execute`, `db.insert_returning`).
- Migrationen: neues Statement ans Ende der `MIGRATIONS`-Liste in `core/db.py` (idempotent, `IF NOT EXISTS`).
- iOS-Build/Deploy: `DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer`, Device-ID `00008140-00161DEE11EB801C`.

---

### Task 1: Pure Zyklus-Logik + Unit-Tests

**Files:**
- Modify: `domains/fitness.py` (oben, nach den Imports `CYCLE`, `CYCLE_LABEL` + zwei pure Funktionen)
- Test: `tests/test_cycle.py` (neu)

**Interfaces:**
- Produces:
  - `CYCLE: list[str] = ["lower", "jog", "upper"]`
  - `CYCLE_LABEL: dict[str,str]`
  - `next_slot_from_events(events: list[dict]) -> str` — `events` newest-first, je `{slot, kind}`; gibt nächsten Slot, Rest-Events übersprungen; leer → `"lower"`.
  - `cycle_state(events: list[dict], today: date) -> dict` — gibt `{"slot": str, "done_today": bool, "next_label": str}`.

- [ ] **Step 1: Failing test schreiben**

`tests/test_cycle.py`:
```python
"""Unit-Tests für die pure Zyklus-Logik (ohne DB)."""
import sys, os
from datetime import date, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domains.fitness import next_slot_from_events, cycle_state, CYCLE_LABEL

TODAY = date(2026, 6, 26)
YDAY = TODAY - timedelta(days=1)


class TestNextSlot:
    def test_empty_starts_lower(self):
        assert next_slot_from_events([]) == "lower"

    def test_after_lower_is_jog(self):
        assert next_slot_from_events([{"slot": "lower", "kind": "workout"}]) == "jog"

    def test_after_jog_is_upper(self):
        assert next_slot_from_events([{"slot": "jog", "kind": "jog"}]) == "upper"

    def test_after_upper_wraps_to_lower(self):
        assert next_slot_from_events([{"slot": "upper", "kind": "workout"}]) == "lower"

    def test_rest_is_skipped(self):
        events = [{"slot": "lower", "kind": "rest"},
                  {"slot": "lower", "kind": "workout"}]
        # letzter Nicht-Rest ist lower → next ist jog
        assert next_slot_from_events(events) == "jog"

    def test_only_rest_starts_lower(self):
        assert next_slot_from_events([{"slot": "upper", "kind": "rest"}]) == "lower"


class TestCycleState:
    def test_done_today_when_last_event_today(self):
        events = [{"slot": "lower", "kind": "workout", "date": TODAY}]
        s = cycle_state(events, TODAY)
        assert s["done_today"] is True
        assert s["slot"] == "lower"
        assert s["next_label"] == CYCLE_LABEL["jog"]

    def test_pending_when_last_event_yesterday(self):
        events = [{"slot": "lower", "kind": "workout", "date": YDAY}]
        s = cycle_state(events, TODAY)
        assert s["done_today"] is False
        assert s["slot"] == "jog"

    def test_empty_is_pending_lower(self):
        s = cycle_state([], TODAY)
        assert s == {"slot": "lower", "done_today": False, "next_label": CYCLE_LABEL["jog"]}

    def test_rest_today_keeps_pending(self):
        events = [{"slot": "jog", "kind": "rest", "date": TODAY},
                  {"slot": "lower", "kind": "workout", "date": YDAY}]
        s = cycle_state(events, TODAY)
        # Rest heute zählt nicht als erledigt → jog bleibt pending
        assert s["done_today"] is False
        assert s["slot"] == "jog"
```

- [ ] **Step 2: Test ausführen, FAIL bestätigen**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_cycle.py -v`
Expected: FAIL mit `ImportError: cannot import name 'next_slot_from_events'`

- [ ] **Step 3: Implementierung in `domains/fitness.py`**

Direkt nach den bestehenden Imports (oben, vor `def ensure_exercise`) einfügen:
```python
CYCLE = ["lower", "jog", "upper"]
CYCLE_LABEL = {"lower": "Lower Body", "jog": "Joggen", "upper": "Upper Body"}


def _event_date(ev: dict):
    """Normalisiert das date-Feld eines Events auf ein date-Objekt."""
    d = ev.get("date")
    if isinstance(d, date):
        return d
    if isinstance(d, str) and d:
        return date.fromisoformat(d[:10])
    return None


def next_slot_from_events(events: list[dict]) -> str:
    """events newest-first, je {slot, kind}. Nächster Slot; Rest übersprungen."""
    for e in events:
        if e.get("kind") == "rest":
            continue
        slot = e.get("slot")
        if slot in CYCLE:
            return CYCLE[(CYCLE.index(slot) + 1) % len(CYCLE)]
        return CYCLE[0]
    return CYCLE[0]


def cycle_state(events: list[dict], today: date) -> dict:
    """Liefert {slot, done_today, next_label}. events newest-first, je {slot, kind, date}."""
    last = next((e for e in events if e.get("kind") != "rest"), None)
    if last and _event_date(last) == today and last.get("slot") in CYCLE:
        slot = last["slot"]
        done_today = True
    else:
        slot = next_slot_from_events(events)
        done_today = False
    after = CYCLE[(CYCLE.index(slot) + 1) % len(CYCLE)]
    return {"slot": slot, "done_today": done_today, "next_label": CYCLE_LABEL[after]}
```

`date` ist in `domains/fitness.py` bereits importiert (`from datetime import date` — verifizieren; falls nur `date` fehlt, ergänzen).

- [ ] **Step 4: Test ausführen, PASS bestätigen**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_cycle.py -v`
Expected: PASS (alle 10 Tests grün)

- [ ] **Step 5: Commit**

```bash
git add domains/fitness.py tests/test_cycle.py
git commit -m "feat(fitness): pure training cycle logic + tests"
```

---

### Task 2: DB-Migration + DB-gestützte Cycle-Helfer

**Files:**
- Modify: `core/db.py` (Migration ans Ende der `MIGRATIONS`-Liste, vor `]` bei Zeile ~485)
- Modify: `domains/fitness.py` (drei DB-Helfer am Dateiende)

**Interfaces:**
- Consumes: `CYCLE`, `cycle_state` aus Task 1.
- Produces:
  - `record_cycle_event(slot: str, kind: str, on_date: date | None = None) -> None`
  - `recent_cycle_events(limit: int = 12) -> list[dict]` — Rows `{date, slot, kind}`, newest-first.
  - `jog_done_today_exists() -> bool`

- [ ] **Step 1: Migration einfügen**

In `core/db.py`, in der `MIGRATIONS`-Liste direkt vor dem schließenden `]` (nach dem `body_measurements_date_idx`-Eintrag, Zeile ~484):
```python
    """CREATE TABLE IF NOT EXISTS training_cycle_events (
        id          SERIAL PRIMARY KEY,
        date        DATE NOT NULL DEFAULT CURRENT_DATE,
        slot        TEXT NOT NULL,
        kind        TEXT NOT NULL,
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );""",
    "CREATE INDEX IF NOT EXISTS training_cycle_events_date_idx ON training_cycle_events (date DESC, id DESC);",
```

- [ ] **Step 2: DB-Helfer in `domains/fitness.py` (am Dateiende) einfügen**

```python
# ── Trainingszyklus (LOWER → JOGGEN → UPPER) ────────────────────────────────

def record_cycle_event(slot: str, kind: str, on_date: date | None = None) -> None:
    """Schreibt ein Zyklus-Event. kind ∈ {workout, jog, rest}."""
    db.execute(
        "INSERT INTO training_cycle_events (date, slot, kind) VALUES (%s,%s,%s)",
        (on_date or date.today(), slot, kind),
    )


def recent_cycle_events(limit: int = 12) -> list[dict]:
    return db.query(
        "SELECT date, slot, kind FROM training_cycle_events ORDER BY date DESC, id DESC LIMIT %s",
        (limit,),
    )


def jog_done_today_exists() -> bool:
    row = db.query_one(
        "SELECT 1 AS x FROM training_cycle_events WHERE kind='jog' AND date=CURRENT_DATE LIMIT 1"
    )
    return row is not None
```

- [ ] **Step 3: Migration anwenden + verifizieren**

Run:
```bash
cd /Users/timoegersdorfer/Alfred && python3 -c "from core import db; db.run_migrations(); print(db.query('SELECT count(*) c FROM training_cycle_events'))"
```
Expected: läuft ohne Fehler, gibt `[{'c': 0}]`

- [ ] **Step 4: Smoke-Test der Helfer**

Run:
```bash
cd /Users/timoegersdorfer/Alfred && python3 -c "
from domains import fitness as f
f.record_cycle_event('lower','workout')
print('jog_done_today:', f.jog_done_today_exists())
print('events:', f.recent_cycle_events(3))
from datetime import date
print('state:', f.cycle_state(f.recent_cycle_events(12), date.today()))
"
```
Expected: `jog_done_today: False`, ein `lower/workout`-Event, `state` mit `done_today: True`, `slot: 'lower'`.

- [ ] **Step 5: Testzeile wieder entfernen (DB sauber halten)**

Run:
```bash
cd /Users/timoegersdorfer/Alfred && python3 -c "from core import db; db.execute(\"DELETE FROM training_cycle_events WHERE kind='workout' AND date=CURRENT_DATE\"); print('cleaned')"
```
Expected: `cleaned`

- [ ] **Step 6: Commit**

```bash
git add core/db.py domains/fitness.py
git commit -m "feat(fitness): training_cycle_events table + db helpers"
```

---

### Task 3: `today-plan` umbauen + neue Endpoints

**Files:**
- Modify: `web/routers/fitness.py` — `today_plan()` (Zeile 68–193) ersetzen, `add_workout` (Zeile 39–46) erweitern, zwei neue Endpoints.

**Interfaces:**
- Consumes: `fitness.recent_cycle_events`, `fitness.cycle_state`, `fitness.record_cycle_event`, `fitness.jog_done_today_exists`, `fitness.CYCLE_LABEL`.
- Produces (HTTP): `GET /api/fitness/today-plan` mit Feldern `day_type, day_label, intensity_factor, done_today, next_label, alfred_message, health, exercises`; `POST /api/fitness/jog-done`; `POST /api/fitness/rest-day`.

- [ ] **Step 1: `add_workout` erweitern — Cycle-Event bei LOWER/UPPER**

In `web/routers/fitness.py` die `add_workout`-Funktion (Zeile 39–46) ersetzen durch:
```python
    @router.post("/api/workouts")
    async def add_workout(req: Request):
        d = await req.json()
        wid = fitness.log_workout(
            title=d["title"], type_=d.get("type", "strength"),
            duration_min=d.get("duration_min"), distance_km=d.get("distance_km"),
            notes=d.get("notes"), rpe=d.get("rpe"), sets=d.get("sets"))
        t = (d.get("type") or "").lower()
        if t in ("lower", "upper"):
            fitness.record_cycle_event(t, "workout")
        return {"id": wid}
```

- [ ] **Step 2: `today_plan()` ersetzen**

Die komplette `today_plan()`-Funktion (Zeile 68–193) ersetzen durch:
```python
    @router.get("/api/fitness/today-plan")
    def today_plan():
        """Heutiger Trainingsplan: abschluss-basierter Zyklus LOWER → JOGGEN → UPPER,
        moduliert über HRV+Schlaf (Intensität) und Progressive Overload."""
        from datetime import date as _date
        import math as _math

        events = fitness.recent_cycle_events(limit=12)
        state = fitness.cycle_state(events, _date.today())
        day_type = state["slot"]
        done_today = state["done_today"]

        health = db.query_one("SELECT * FROM health_data ORDER BY date DESC LIMIT 1") or {}
        hrv = float(health.get("hrv_avg") or 0)
        sleep_h = float(health.get("sleep_hours") or 0)
        hrv_score = min(hrv / 70.0, 1.2) if hrv > 0 else 1.0
        sleep_score = min(sleep_h / 8.0, 1.1) if sleep_h > 0 else 1.0
        intensity = round(max(0.85, min(1.05, (hrv_score + sleep_score) / 2.0)), 2)

        alfred_note = ""
        if hrv > 0 and sleep_h > 0 and day_type != "jog":
            if intensity >= 1.0:
                alfred_note = f"HRV {hrv:.0f}, Schlaf {sleep_h:.1f}h — top Werte, Gewichte leicht erhöhen."
            elif intensity <= 0.88:
                alfred_note = f"HRV {hrv:.0f}, Schlaf {sleep_h:.1f}h — Erholung niedrig, Gewichte reduzieren."
            else:
                alfred_note = f"HRV {hrv:.0f}, Schlaf {sleep_h:.1f}h — normale Session."

        def last_set(exercise_name: str) -> dict | None:
            return db.query_one(
                """SELECT ws.weight_kg, ws.reps FROM workout_sets ws
                   JOIN exercises e ON e.id = ws.exercise_id
                   WHERE LOWER(e.name) = LOWER(%s)
                   ORDER BY ws.id DESC LIMIT 1""",
                (exercise_name,),
            )

        def build_sets(exercise_name: str, default_weight: float, default_reps: int,
                       working_count: int = 3, rpe_target: int = 7) -> dict:
            prev = last_set(exercise_name)
            if prev and prev.get("weight_kg"):
                base_w = float(prev["weight_kg"]) * intensity
                base_r = prev.get("reps") or default_reps
            else:
                base_w = default_weight * intensity
                base_r = default_reps
            w = _math.floor(base_w / 2.5) * 2.5
            warmup = [
                {"weight": round(w * 0.4, 1), "reps": 12},
                {"weight": round(w * 0.6, 1), "reps": 8},
                {"weight": round(w * 0.8, 1), "reps": 5},
            ]
            working = [{"weight": w, "reps": base_r, "rpe_target": rpe_target}] * working_count
            return {"name": exercise_name, "warmup_sets": warmup, "working_sets": working}

        if day_type == "lower":
            exercises_list = [
                build_sets("Squat", 100, 5, working_count=4, rpe_target=8),
                build_sets("Romanian Deadlift", 80, 8, working_count=3, rpe_target=7),
                build_sets("Leg Press", 140, 10, working_count=3, rpe_target=8),
                build_sets("Leg Curl", 50, 12, working_count=3, rpe_target=8),
                build_sets("Calf Raise", 60, 15, working_count=4, rpe_target=9),
            ]
        elif day_type == "upper":
            exercises_list = [
                build_sets("Bench Press", 80, 6, working_count=4, rpe_target=8),
                build_sets("Overhead Press", 50, 8, working_count=3, rpe_target=7),
                build_sets("Barbell Row", 70, 8, working_count=4, rpe_target=7),
                build_sets("Dumbbell Curl", 16, 10, working_count=3, rpe_target=8),
                build_sets("Tricep Pushdown", 35, 12, working_count=3, rpe_target=8),
                build_sets("Lateral Raise", 10, 15, working_count=3, rpe_target=9),
            ]
        else:  # jog
            exercises_list = []
            alfred_note = "Heute: Joggen — läuft über Strava."

        return {
            "day_type": day_type,
            "day_label": fitness.CYCLE_LABEL[day_type],
            "intensity_factor": intensity,
            "done_today": done_today,
            "next_label": state["next_label"],
            "alfred_message": alfred_note or f"Heute: {fitness.CYCLE_LABEL[day_type]}.",
            "health": {
                "hrv": hrv or None,
                "sleep_hours": sleep_h or None,
                "date": str(health.get("date", "")),
            },
            "exercises": exercises_list,
        }
```

- [ ] **Step 3: Neue Endpoints `jog-done` + `rest-day` einfügen**

In `web/routers/fitness.py` direkt vor `return router` (Zeile ~253) einfügen:
```python
    @router.post("/api/fitness/jog-done")
    async def jog_done(req: Request):
        """Markiert den heutigen Jog-Tag als erledigt (idempotent pro Tag)."""
        try:
            d = await req.json()
        except Exception:
            d = {}
        if fitness.jog_done_today_exists():
            return {"ok": True, "already": True}
        fitness.record_cycle_event("jog", "jog")
        return {"ok": True, "source": (d or {}).get("source", "manual")}

    @router.post("/api/fitness/rest-day")
    async def rest_day(req: Request):
        """Schiebt einen Ruhetag ein — Zeiger bleibt auf dem aktuellen Slot."""
        from datetime import date as _date
        events = fitness.recent_cycle_events(limit=12)
        state = fitness.cycle_state(events, _date.today())
        fitness.record_cycle_event(state["slot"], "rest")
        return {"ok": True, "slot": state["slot"]}
```

- [ ] **Step 4: Bestehende Tests + Import-Smoke prüfen**

Run:
```bash
cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/ -q && python3 -c "import web.routers.fitness as f; print('router import ok')"
```
Expected: alle Tests grün, `router import ok`

- [ ] **Step 5: End-to-End gegen laufenden Server**

Run (Alfred läuft auf :7779):
```bash
curl -s localhost:7779/api/fitness/today-plan | python3 -m json.tool | head -20
curl -s -X POST localhost:7779/api/fitness/rest-day | python3 -m json.tool
curl -s localhost:7779/api/fitness/today-plan | python3 -c "import sys,json; d=json.load(sys.stdin); print('day_type', d['day_type'], 'done_today', d['done_today'], 'next', d['next_label'])"
```
Expected: today-plan liefert `day_type/done_today/next_label`; rest-day gibt `{"ok": true, "slot": ...}`; Slot bleibt nach rest-day gleich.

- [ ] **Step 6: Rest-Test-Event entfernen + Commit**

```bash
cd /Users/timoegersdorfer/Alfred && python3 -c "from core import db; db.execute(\"DELETE FROM training_cycle_events WHERE kind='rest' AND date=CURRENT_DATE\"); print('cleaned')"
git add web/routers/fitness.py
git commit -m "feat(fitness): completion-based cycle in today-plan + jog-done/rest-day endpoints"
```

---

### Task 4: BodyOS — Models + API-Calls

**Files:**
- Modify: `apps/BodyOS/BodyOS/Models/BodyModels.swift` (`TodayPlan` um zwei Felder erweitern)
- Modify: `apps/BodyOS/BodyOS/API/FitnessAPI.swift` (zwei neue Calls)

**Interfaces:**
- Consumes (HTTP): Endpoints aus Task 3.
- Produces (Swift): `TodayPlan.doneToday: Bool`, `TodayPlan.nextLabel: String`; `FitnessAPI.markJogDone(distanceKm:durationMin:source:)`, `FitnessAPI.markRestDay()`.

- [ ] **Step 1: `TodayPlan` erweitern**

In `apps/BodyOS/BodyOS/Models/BodyModels.swift` die `TodayPlan`-Struct (Zeile 6–13) ersetzen durch:
```swift
struct TodayPlan: Codable {
    let dayType: String
    let dayLabel: String
    let intensityFactor: Double
    let alfredMessage: String
    let health: HealthSnapshot?
    let exercises: [PlannedExercise]
    let doneToday: Bool?
    let nextLabel: String?
}
```
(`AlfredClient` nutzt `convertFromSnakeCase`, daher mappen `done_today`→`doneToday`, `next_label`→`nextLabel` automatisch — verifizieren in `AlfredClient.swift`, Decoder-Setup. Falls kein snake-case-Decoder: explizite `CodingKeys` ergänzen.)

- [ ] **Step 2: API-Calls ergänzen**

In `apps/BodyOS/BodyOS/API/FitnessAPI.swift` vor der schließenden `}` einfügen:
```swift
    func markJogDone(distanceKm: Double? = nil, durationMin: Int? = nil,
                     source: String = "manual") async throws {
        struct Body: Encodable { let distanceKm: Double?; let durationMin: Int?; let source: String }
        let _: OkResponse = try await client.post(
            "/api/fitness/jog-done",
            body: Body(distanceKm: distanceKm, durationMin: durationMin, source: source))
    }

    func markRestDay() async throws {
        struct Empty: Encodable {}
        let _: OkResponse = try await client.post("/api/fitness/rest-day", body: Empty())
    }
```

- [ ] **Step 3: Build (Compile-Check)**

Run:
```bash
DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer xcodebuild \
  -project apps/BodyOS/BodyOS.xcodeproj -scheme BodyOS \
  -destination 'platform=iOS,id=00008140-00161DEE11EB801C' \
  -configuration Release build 2>&1 | grep -E "BUILD SUCCEEDED|BUILD FAILED|error:"
```
Expected: `** BUILD SUCCEEDED **`

- [ ] **Step 4: Commit**

```bash
git add apps/BodyOS/BodyOS/Models/BodyModels.swift apps/BodyOS/BodyOS/API/FitnessAPI.swift
git commit -m "feat(BodyOS): TodayPlan done/next fields + jog-done/rest-day API"
```

---

### Task 5: BodyOS — HealthKit Lauf-Erkennung

**Files:**
- Modify: `apps/BodyOS/BodyOS/Utilities/HealthKitManager.swift` (`HKWorkoutType` zu readTypes, neue `fetchTodayRun()`)
- Modify: `apps/BodyOS/BodyOS/Info.plist` (Usage-String um „Läufe" ergänzen)

**Interfaces:**
- Produces (Swift): `HealthKitManager.fetchTodayRun() async -> (distanceKm: Double, durationMin: Int)?`

- [ ] **Step 1: readTypes erweitern**

In `HealthKitManager.swift` das `readTypes`-Set (Zeile 13–19) um den Workout-Typ ergänzen:
```swift
    private let readTypes: Set<HKObjectType> = [
        HKQuantityType(.stepCount),
        HKQuantityType(.heartRateVariabilitySDNN),
        HKQuantityType(.restingHeartRate),
        HKQuantityType(.bodyMass),
        HKCategoryType(.sleepAnalysis),
        HKObjectType.workoutType(),
    ]
```

- [ ] **Step 2: `fetchTodayRun()` einfügen**

In `HealthKitManager.swift` vor der schließenden `}` der Klasse (nach `fetchSleepHours`, Zeile ~141) einfügen:
```swift
    /// Jüngster heutiger Lauf aus HealthKit (z.B. von Coros via Apple Health).
    func fetchTodayRun() async -> (distanceKm: Double, durationMin: Int)? {
        guard isAvailable else { return nil }
        let today = Calendar.current.startOfDay(for: Date())
        let tomorrow = Calendar.current.date(byAdding: .day, value: 1, to: today)!
        let timePred = HKQuery.predicateForSamples(withStart: today, end: tomorrow)
        let runPred = HKQuery.predicateForWorkouts(with: .running)
        let pred = NSCompoundPredicate(andPredicateWithSubpredicates: [timePred, runPred])

        return await withCheckedContinuation { cont in
            let sort = NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: false)
            let query = HKSampleQuery(sampleType: .workoutType(), predicate: pred,
                                      limit: 1, sortDescriptors: [sort]) { _, samples, _ in
                guard let w = samples?.first as? HKWorkout else { cont.resume(returning: nil); return }
                let km = w.totalDistance?.doubleValue(for: .meter()) ?? 0
                let minutes = Int(w.duration / 60.0)
                cont.resume(returning: (distanceKm: km / 1000.0, durationMin: minutes))
            }
            store.execute(query)
        }
    }
```

- [ ] **Step 3: Info.plist Usage-String ergänzen**

In `apps/BodyOS/BodyOS/Info.plist` den `NSHealthShareUsageDescription`-String ersetzen durch:
```xml
	<string>BodyOS liest deine Gesundheitsdaten (Schritte, HRV, Schlaf, Gewicht, Läufe) um sie mit Alfred zu synchronisieren</string>
```

- [ ] **Step 4: Build (Compile-Check)**

Run:
```bash
DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer xcodebuild \
  -project apps/BodyOS/BodyOS.xcodeproj -scheme BodyOS \
  -destination 'platform=iOS,id=00008140-00161DEE11EB801C' \
  -configuration Release build 2>&1 | grep -E "BUILD SUCCEEDED|BUILD FAILED|error:"
```
Expected: `** BUILD SUCCEEDED **`

- [ ] **Step 5: Commit**

```bash
git add apps/BodyOS/BodyOS/Utilities/HealthKitManager.swift apps/BodyOS/BodyOS/Info.plist
git commit -m "feat(BodyOS): read today's run from HealthKit"
```

---

### Task 6: BodyOS — WorkoutView drei Zustände (Kraft / Jog / Erledigt)

**Files:**
- Modify: `apps/BodyOS/BodyOS/Views/WorkoutView.swift` (ViewModel + `todayContent`)
- Modify: `apps/BodyOS/BodyOS/Views/ActiveSessionView.swift` (Zeile 54: `type: plan.dayType`)

**Interfaces:**
- Consumes: `TodayPlan.doneToday/nextLabel`, `FitnessAPI.markJogDone/markRestDay`, `HealthKitManager.fetchTodayRun`.

- [ ] **Step 1: ActiveSessionView — korrekten Typ senden**

In `apps/BodyOS/BodyOS/Views/ActiveSessionView.swift` Zeile 54:
```swift
            type: plan.dayType,
```
(ersetzt `type: plan.dayType == "jog" ? "run" : "strength"` — Jog läuft nicht mehr über die Session, LOWER/UPPER müssen ihren echten Typ senden, damit das Backend das Cycle-Event schreibt.)

- [ ] **Step 2: ViewModel um Aktionen erweitern**

In `WorkoutView.swift` in `WorkoutViewModel` (nach `startSession()`, Zeile 37) einfügen:
```swift
    func markJogDone(auto: Bool, km: Double? = nil, min: Int? = nil) async {
        try? await FitnessAPI.shared.markJogDone(
            distanceKm: km, durationMin: min, source: auto ? "healthkit" : "manual")
        await loadPlan()
    }

    func markRestDay() async {
        try? await FitnessAPI.shared.markRestDay()
        await loadPlan()
    }

    /// Beim Öffnen des Jog-Tags HealthKit nach einem Lauf fragen und ggf. auto-abhaken.
    func autoDetectRun() async {
        guard let plan, plan.dayType == "jog", plan.doneToday != true else { return }
        if let run = await HealthKitManager.shared.fetchTodayRun(), run.distanceKm > 0.3 {
            await markJogDone(auto: true, km: run.distanceKm, min: run.durationMin)
        }
    }
```

- [ ] **Step 3: `todayContent` auf drei Zustände umbauen**

In `WorkoutView.swift` die `todayContent`-Computed-Property (Zeile 86–108) ersetzen durch:
```swift
    @ViewBuilder
    private var todayContent: some View {
        if vm.isLoading {
            Spacer(); ProgressView("Alfred denkt nach…"); Spacer()
        } else if let plan = vm.plan {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    dayHeaderCard(plan)
                    if plan.doneToday == true {
                        doneCard(plan)
                    } else if plan.dayType == "jog" {
                        jogCard(plan)
                    } else {
                        if !plan.alfredMessage.isEmpty { alfredCard(plan.alfredMessage) }
                        if let health = plan.health { healthCard(health) }
                        exerciseList(plan)
                        startButton
                        restButton
                    }
                }
                .padding(.bottom, 32)
            }
            .task { await vm.autoDetectRun() }
        } else {
            Spacer(); errorView; Spacer()
        }
    }

    private func doneCard(_ plan: TodayPlan) -> some View {
        VStack(spacing: 8) {
            Image(systemName: "checkmark.seal.fill").font(.largeTitle).foregroundStyle(.green)
            Text("\(plan.dayLabel) erledigt").font(.headline)
            if let next = plan.nextLabel { Text("Morgen: \(next)").font(.subheadline).foregroundStyle(.secondary) }
        }
        .frame(maxWidth: .infinity).padding(.vertical, 32)
        .background(Color.green.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 16)).padding(.horizontal)
    }

    private func jogCard(_ plan: TodayPlan) -> some View {
        VStack(spacing: 16) {
            VStack(spacing: 8) {
                Image(systemName: "figure.run").font(.largeTitle).foregroundStyle(.orange)
                Text("Heute: Joggen").font(.headline)
                Text("Läuft über Strava / Coros — wird automatisch erkannt.")
                    .font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center)
            }
            Button { Task { await vm.markJogDone(auto: false) } } label: {
                Label("Joggen erledigt", systemImage: "checkmark")
                    .frame(maxWidth: .infinity).padding()
                    .background(Color.orange).foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 14))
            }
            restButton
        }
        .padding().background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16)).padding(.horizontal)
    }

    private var restButton: some View {
        Button { Task { await vm.markRestDay() } } label: {
            Label("Restday einlegen", systemImage: "moon.zzz")
                .frame(maxWidth: .infinity).padding()
                .foregroundStyle(.secondary)
                .background(Color(.tertiarySystemBackground))
                .clipShape(RoundedRectangle(cornerRadius: 14))
        }
        .padding(.horizontal)
    }
```

- [ ] **Step 4: Build + Deploy aufs iPhone**

Run:
```bash
DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer xcodebuild \
  -project apps/BodyOS/BodyOS.xcodeproj -scheme BodyOS \
  -destination 'platform=iOS,id=00008140-00161DEE11EB801C' \
  -configuration Release build 2>&1 | grep -E "BUILD SUCCEEDED|BUILD FAILED|error:"
APP_PATH=$(find ~/Library/Developer/Xcode/DerivedData/BodyOS-* -name "BodyOS.app" -path "*/Release-iphoneos/*" | head -1)
DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer xcrun devicectl device install app \
  --device 00008140-00161DEE11EB801C "$APP_PATH" 2>&1 | grep -E "installed|error"
```
Expected: `BUILD SUCCEEDED` + `App installed`

- [ ] **Step 5: Commit**

```bash
git add apps/BodyOS/BodyOS/Views/WorkoutView.swift apps/BodyOS/BodyOS/Views/ActiveSessionView.swift
git commit -m "feat(BodyOS): three workout states (strength/jog/done) + restday"
```

---

### Task 7: End-to-End-Verifikation + Spec-Abgleich

**Files:** keine (nur Verifikation)

- [ ] **Step 1: Vollständiger Zyklus-Durchlauf gegen Server**

Run:
```bash
cd /Users/timoegersdorfer/Alfred
echo "--- Start (erwartet lower, da DB leer für heute) ---"
curl -s localhost:7779/api/fitness/today-plan | python3 -c "import sys,json;d=json.load(sys.stdin);print('slot',d['day_type'],'exercises',len(d['exercises']),'done',d['done_today'])"
echo "--- LOWER loggen ---"
curl -s -X POST localhost:7779/api/workouts -H 'Content-Type: application/json' -d '{"title":"Lower","type":"lower"}' >/dev/null
curl -s localhost:7779/api/fitness/today-plan | python3 -c "import sys,json;d=json.load(sys.stdin);print('nach lower: slot',d['day_type'],'done',d['done_today'],'next',d['next_label'])"
echo "--- (morgen simulieren ist nicht nötig; Jog ist erst nach Tageswechsel pending) ---"
```
Expected: Start `slot lower, exercises 5`; nach Lower-Log `done True` (heute erledigt) und `next Joggen`. Jog-Block hat `exercises 0`.

- [ ] **Step 2: Test-Events wieder entfernen**

Run:
```bash
cd /Users/timoegersdorfer/Alfred && python3 -c "from core import db; db.execute(\"DELETE FROM training_cycle_events WHERE date=CURRENT_DATE\"); db.execute(\"DELETE FROM workouts WHERE date=CURRENT_DATE AND title='Lower'\"); print('cleaned')"
```
Expected: `cleaned`

- [ ] **Step 3: Spec-Abgleich**

Spec `docs/superpowers/specs/2026-06-26-training-cycle-rework-design.md` durchgehen, jeden Punkt gegen die Implementierung prüfen: Zyklus-Reihenfolge, Restday=Pause, Jog ohne distance/pace, Jog nicht in `workouts`, done_today/next_label, HealthKit-Auto, Dashboard zieht denselben Endpoint. Abweichungen notieren.

- [ ] **Step 4: Alle Python-Tests grün**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/ -q`
Expected: alle grün.

- [ ] **Step 5: Auf dem iPhone manuell sichten**

BodyOS öffnen → „Training"-Tab: an einem LOWER/UPPER-Tag Übungsliste + „Training starten" + „Restday einlegen"; nach dem Loggen die „erledigt"-Karte mit „Morgen: …". (Jog-Tag erscheint erst, wenn der Zyklus dort steht.)
