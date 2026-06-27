# Asynchrone Foto-Kalorien-Analyse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Foto-Kalorien-Scan asynchron machen — Upload kehrt sofort zurück, Mahlzeit erscheint als „wird analysiert…" und füllt sich selbst, plus Beschreibungsfeld und Tap-to-Edit.

**Architecture:** `analyze-photo` legt sofort eine Pending-Mahlzeit (`status=analyzing`) an und startet einen asyncio-Background-Task fürs Vision-Modell, der die Mahlzeit füllt. Die App pollt, solange etwas analysiert wird. Kein HTTP-Timeout mehr.

**Tech Stack:** Python/FastAPI, Postgres, Ollama (qwen3-vl:8b), SwiftUI.

## Global Constraints

- `meals.status ∈ {analyzing, done, failed}`, Default `'done'`.
- Vision-Call: `options={"num_predict":600,"temperature":0.2,"num_ctx":8192}`, `keep_alive=0`, `format="json"`.
- Beschreibung (`text`) → Vision-Hinweis UND Mahlzeit-Name (falls gesetzt), sonst `food_name`.
- Background-Task-Refs in modulweitem Set halten (GC). Startup: verwaiste `analyzing` → `failed`.
- DB nur über `core.db`. iOS-Build: `DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer`, `-allowProvisioningUpdates`, Device-ID `00008140-00161DEE11EB801C`.

---

### Task 1: Backend — meals.status + Domain-Funktionen

**Files:**
- Modify: `core/db.py` (Migration ans Ende der `MIGRATIONS`-Liste)
- Modify: `domains/nutrition.py` (`create_pending_meal`, `complete_meal`, `fail_meal`, `update_meal`)

**Interfaces:**
- Produces:
  - `nutrition.create_pending_meal(description: str, on_date=None) -> int`
  - `nutrition.complete_meal(meal_id, name, calories, protein, carbs, fat) -> None`
  - `nutrition.fail_meal(meal_id) -> None`
  - `nutrition.update_meal(meal_id, name, calories, protein, carbs, fat) -> None`

- [ ] **Step 1: Migration in `core/db.py`**

In der `MIGRATIONS`-Liste vor dem schließenden `]` (nach den `workout_sets`-ALTERs):
```python
    "ALTER TABLE meals ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'done';",
```

- [ ] **Step 2: Funktionen in `domains/nutrition.py` (nach `log_meal`)**

```python
def create_pending_meal(description: str, on_date: date | None = None) -> int:
    d = on_date or date.today()
    return db.insert_returning(
        "INSERT INTO meals (date, meal_type, description, status) "
        "VALUES (%s,'snack',%s,'analyzing') RETURNING id",
        (d, description or "Wird analysiert…"))


def complete_meal(meal_id: int, name: str, calories, protein, carbs, fat) -> None:
    db.execute(
        "UPDATE meals SET description=%s, calories=%s, protein_g=%s, carbs_g=%s, fat_g=%s, "
        "status='done' WHERE id=%s",
        (name, calories, protein, carbs, fat, meal_id))


def fail_meal(meal_id: int) -> None:
    db.execute("UPDATE meals SET status='failed' WHERE id=%s", (meal_id,))


def update_meal(meal_id: int, name: str | None, calories, protein, carbs, fat) -> None:
    db.execute(
        "UPDATE meals SET description=COALESCE(%s,description), calories=%s, protein_g=%s, "
        "carbs_g=%s, fat_g=%s WHERE id=%s",
        (name, calories, protein, carbs, fat, meal_id))
```
(`date` ist in `domains/nutrition.py` bereits importiert — verifizieren; sonst `from datetime import date` ergänzen.)

- [ ] **Step 3: Migration + Smoke**

Run:
```bash
cd /Users/timoegersdorfer/Alfred && python3 -c "
from core import db
db.run_migrations()
from domains import nutrition
mid = nutrition.create_pending_meal('Test-Nudeln')
print('pending:', db.query_one('SELECT description,status,calories FROM meals WHERE id=%s',(mid,)))
nutrition.complete_meal(mid, 'Nudeln', 520, 25, 60, 18)
print('done:', db.query_one('SELECT description,status,calories,protein_g FROM meals WHERE id=%s',(mid,)))
nutrition.update_meal(mid, 'Nudeln korrigiert', 600, 30, 65, 20)
print('updated:', db.query_one('SELECT description,calories FROM meals WHERE id=%s',(mid,)))
nutrition.fail_meal(mid); print('failed:', db.query_one('SELECT status FROM meals WHERE id=%s',(mid,)))
db.execute('DELETE FROM meals WHERE id=%s',(mid,)); print('cleaned')"
```
Expected: pending status=analyzing/calories None; done status=done/calories 520; updated calories 600; failed status=failed; cleaned.

- [ ] **Step 4: Commit**

```bash
git add core/db.py domains/nutrition.py
git commit -m "feat(nutrition): meal status + pending/complete/fail/update helpers"
```

---

### Task 2: Backend — async analyze-photo + background task + PUT + startup cleanup

**Files:**
- Modify: `web/routers/nutrition.py` (`analyze_food_photo` umbauen, `_run_analysis` + `_BG_TASKS`, PUT-Endpoint)
- Modify: `orchestrator.py` (Startup-Cleanup für verwaiste `analyzing`-Mahlzeiten)

**Interfaces:**
- Consumes: `nutrition.create_pending_meal/complete_meal/fail_meal/update_meal`, `_sum_food_items`, `extract_json`.
- Produces (HTTP): `POST /api/nutrition/analyze-photo` → `{ok, meal_id, status}`; `PUT /api/nutrition/{mid}`.

- [ ] **Step 1: `_run_analysis` + `_BG_TASKS` (Modulebene in `web/routers/nutrition.py`)**

Nach `_sum_food_items` (vor `build_router`) einfügen:
```python
_BG_TASKS: set = set()


async def _run_analysis(meal_id: int, image_bytes: bytes, annotation: str) -> None:
    """Hintergrund: Vision-Modell laufen lassen und die Pending-Mahlzeit füllen."""
    import base64 as _b64
    try:
        import ollama as _ollama
        b64 = _b64.standard_b64encode(image_bytes).decode()
        _client = _ollama.AsyncClient(host=config.OLLAMA_BASE_URL)
        vision_model = getattr(config, "VISION_MODEL", "qwen3-vl:8b")
        prompt = (
            "Du bist ein Ernährungsexperte. Schätze die Nährwerte dieses Essens/Getränks "
            "so genau wie möglich.\n"
            + (f"Zusatzinfo vom Nutzer: {annotation}.\n" if annotation else "")
            + "Gehe so vor:\n"
            "1. Zerlege das Gericht in seine einzelnen Komponenten (z.B. Reis, Hähnchen, Soße).\n"
            "2. Schätze für JEDE Komponente das Gewicht in Gramm — nutze Teller, Besteck oder "
            "Hand als Größenreferenz. Lieber realistisch großzügig als zu klein.\n"
            "3. Berechne pro Komponente kcal/Protein/Kohlenhydrate/Fett anhand üblicher Nährwerte.\n"
            "Antworte NUR mit JSON (kein Text davor/danach), Einheiten kcal und Gramm:\n"
            '{"items":[{"name":"...","grams":0,"calories":0,"protein":0,"carbs":0,"fat":0}],'
            '"food_name":"Gesamtgericht","portion":"z.B. 1 großer Teller","confidence":0.0}'
        )
        resp = await _client.chat(
            model=vision_model,
            messages=[{"role": "user", "content": prompt, "images": [b64]}],
            options={"num_predict": 600, "temperature": 0.2, "num_ctx": 8192},
            keep_alive=0, format="json")
        data = _sum_food_items(extract_json((resp.message.content or "").strip(), default={}))
        if not data or not data.get("calories"):
            nutrition.fail_meal(meal_id)
            return
        name = annotation or data.get("food_name") or "Mahlzeit"
        nutrition.complete_meal(meal_id, name, data.get("calories"), data.get("protein"),
                                data.get("carbs"), data.get("fat"))
        log.info(f"Async-Foto-Analyse fertig (meal {meal_id})")
    except Exception:
        log.exception("Async-Foto-Analyse fehlgeschlagen")
        nutrition.fail_meal(meal_id)
```

- [ ] **Step 2: `analyze_food_photo` async umbauen**

Die bestehende `analyze_food_photo`-Funktion (der ganze Body mit dem synchronen Vision-Call)
ersetzen durch:
```python
    @router.post("/api/nutrition/analyze-photo")
    async def analyze_food_photo(req: Request):
        """Legt sofort eine Pending-Mahlzeit an und analysiert im Hintergrund."""
        try:
            form = await req.form()
            image_file = form.get("image")
            annotation = (form.get("text") or "").strip()
            if not image_file:
                return JSONResponse({"error": "kein Bild"}, 400)
            image_bytes = await image_file.read()
        except Exception as e:
            return JSONResponse({"error": f"Upload-Fehler: {e}"}, 400)
        mid = nutrition.create_pending_meal(annotation)
        task = asyncio.create_task(_run_analysis(mid, image_bytes, annotation))
        _BG_TASKS.add(task)
        task.add_done_callback(_BG_TASKS.discard)
        return {"ok": True, "meal_id": mid, "status": "analyzing"}
```

- [ ] **Step 3: PUT-Endpoint (neben den anderen nutrition-Routes, z.B. nach `log-meal`)**

```python
    @router.put("/api/nutrition/{mid}")
    async def nutrition_update(mid: int, req: Request):
        d = await req.json()
        nutrition.update_meal(mid, d.get("name"), d.get("calories"), d.get("protein"),
                              d.get("carbs"), d.get("fat"))
        return {"ok": True}
```

- [ ] **Step 4: Startup-Cleanup in `orchestrator.py`**

In `_init_db` (nach `db.run_migrations()`, im try-Block) ergänzen:
```python
            db.execute("UPDATE meals SET status='failed' WHERE status='analyzing'")
```

- [ ] **Step 5: Verifizieren (Import + Tests + E2E)**

Run:
```bash
cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/ -q && python3 -c "import web.routers.nutrition, orchestrator; print('ok')"
./start.sh >/dev/null 2>&1; sleep 5
RESP=$(curl -s -X POST localhost:7779/api/nutrition/analyze-photo -F "text=Testgericht" -F "image=@/dev/null")
echo "analyze (ohne echtes Bild) → $RESP"
```
Expected: Tests grün, `ok`. analyze-photo gibt `{"ok":true,"meal_id":N,"status":"analyzing"}` sofort zurück (die Analyse failt im Hintergrund, weil /dev/null kein Bild ist — das ist erwartet).

- [ ] **Step 6: Pending-Mahlzeit + PUT + Cleanup prüfen**

Run:
```bash
cd /Users/timoegersdorfer/Alfred
curl -s localhost:7779/api/nutrition | python3 -c "import sys,json;d=json.load(sys.stdin);print([(m['id'],m.get('status'),m.get('description')) for m in (d.get('meals') or [])][-3:])"
python3 -c "from core import db; db.execute(\"DELETE FROM meals WHERE description IN ('Testgericht','Wird analysiert…') AND date=CURRENT_DATE\"); print('cleaned test meals')"
```
Expected: heutige Mahlzeiten enthalten einen `analyzing`/`failed`-Eintrag mit `status`-Feld.

- [ ] **Step 7: Commit**

```bash
git add web/routers/nutrition.py orchestrator.py
git commit -m "feat(nutrition): async photo analysis (pending meal + bg task) + meal update + startup cleanup"
```

---

### Task 3: BodyOS — Modelle + API

**Files:**
- Modify: `apps/BodyOS/BodyOS/Models/BodyModels.swift` (`MealItem.status`, `UpdateMealRequest`)
- Modify: `apps/BodyOS/BodyOS/API/NutritionAPI.swift` (`analyzePhoto` Rückgabe, `updateMeal`)

**Interfaces:**
- Produces (Swift): `MealItem.status: String?`, `UpdateMealRequest`; `NutritionAPI.analyzePhoto(...)->Void`, `NutritionAPI.updateMeal(_:_:)`.

- [ ] **Step 1: `MealItem` um `status` + `UpdateMealRequest`**

In `BodyModels.swift` der `MealItem`-Struct das Feld ergänzen:
```swift
    let status: String?
```
(direkt nach `createdAt` einfügen; `convertFromSnakeCase` mappt `status` automatisch.)
Und neue Struct:
```swift
struct UpdateMealRequest: Encodable {
    let name: String
    let calories: Double?
    let protein: Double?
    let carbs: Double?
    let fat: Double?
}
```

- [ ] **Step 2: `NutritionAPI` anpassen**

`analyzePhoto` Rückgabe auf void ändern (App lädt danach neu) + `updateMeal` ergänzen:
```swift
    func analyzePhoto(imageData: Data, annotation: String?) async throws {
        _ = try await client.postMultipart("/api/nutrition/analyze-photo", imageData: imageData, text: annotation)
    }

    func updateMeal(_ id: Int, _ req: UpdateMealRequest) async throws {
        let _: OkResponse = try await client.put("/api/nutrition/\(id)", body: req)
    }
```
(Die alte `analyzePhoto`-Implementierung, die `MacroEstimate` dekodiert, vollständig ersetzen.)

- [ ] **Step 3: Build (Compile-Check)** — Fehler nur dort, wo `analyzePhoto`'s Rückgabe genutzt wird (AnalysisView/NutritionView), behebt Task 4.

Run:
```bash
cd /Users/timoegersdorfer/Alfred
DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer xcodebuild \
  -project apps/BodyOS/BodyOS.xcodeproj -scheme BodyOS \
  -destination 'platform=iOS,id=00008140-00161DEE11EB801C' -configuration Release \
  -allowProvisioningUpdates build 2>&1 | grep -E "error:" | sed 's|.*BodyOS/BodyOS/||' | head
```
Expected: Fehler nur in `NutritionView.swift`/`AnalysisView.swift` (nutzen die alte `analyzePhoto`-Rückgabe). Keine Fehler in BodyModels/NutritionAPI.

- [ ] **Step 4: Commit**

```bash
git add apps/BodyOS/BodyOS/Models/BodyModels.swift apps/BodyOS/BodyOS/API/NutritionAPI.swift
git commit -m "feat(BodyOS): meal status field + async analyzePhoto + updateMeal API"
```

---

### Task 4: BodyOS — Beschreibung, Pending-Anzeige, Polling, Tap-to-Edit

**Files:**
- Modify: `apps/BodyOS/BodyOS/Views/NutritionView.swift`

**Komponenten & Verhalten (vollständig umzusetzen):**

- **`NutritionViewModel`:** neuer `@Published var description = ""`, `@Published var showDescription = false`.
  - `func analyzeCaptured()`: guard `capturedImage`; `jpegData(0.8)`; `try? await NutritionAPI.shared.analyzePhoto(imageData:annotation: description)`; `description=""`, `capturedImage=nil`; `await load()`; danach `startPolling()`.
  - `func startPolling()`: in einer `Task` solange `nutrition?.meals?.contains{ $0.status=="analyzing" } == true`: `try? await Task.sleep(3s)`, `await load()`. (Nur einen Poll-Task gleichzeitig laufen lassen — Flag `isPolling`.)
  - `func saveEdit(_ meal, name, kcal, p, c, f)`: `NutritionAPI.shared.updateMeal(meal.id, UpdateMealRequest(...))`; `await load()`.
- **Foto-Flow umbauen:** Der `.sheet($vm.showCamera)`-onDismiss navigiert NICHT mehr zu `AnalysisView`,
  sondern: wenn `capturedImage != nil` → `vm.showDescription = true`.
  - Neues `.sheet($vm.showDescription)`: kleines Formular mit `Image(capturedImage)` Vorschau,
    `TextField("Beschreibung (optional)", text: $vm.description)`, Button „Analysieren" →
    `Task { await vm.analyzeCaptured() }` + dismiss. „Abbrechen" verwirft.
  - `showAnalysis`/`.navigationDestination` auf `AnalysisView` aus dem Foto-Pfad entfernen.
- **`MealRowView` erweitern** (status):
  - `status == "analyzing"` → `ProgressView()` + „wird analysiert…" statt der Makros.
  - `status == "failed"` → „Analyse fehlgeschlagen" (rot) + Swipe-Löschen bleibt.
  - sonst → Makros wie bisher.
  - Tap (onTapGesture / Button) → öffnet ein Edit-Sheet `MealEditView(meal:)` (Name + Makros
    vorausgefüllt) → `vm.saveEdit(...)`.
- **`MealEditView`** (neue kleine View in derselben Datei): Form mit Name + kcal/P/C/F
  (vorausgefüllt aus `MealItem`), „Sichern" → `onSave(...)`, „Abbrechen".
- **Polling-Start:** `.task`/`onAppear` ruft `vm.load()` und danach `vm.startPolling()`.

- [ ] **Step 1: `NutritionView.swift` gemäß obiger Komponenten umsetzen** (Beschreibung-Sheet,
  Pending/Failed-Anzeige, Polling, MealEditView, Tap-to-Edit). `AnalysisView` nicht mehr aus
  dem Foto-Pfad aufrufen.

- [ ] **Step 2: Build + Deploy**

Run:
```bash
cd /Users/timoegersdorfer/Alfred
DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer xcodebuild \
  -project apps/BodyOS/BodyOS.xcodeproj -scheme BodyOS \
  -destination 'platform=iOS,id=00008140-00161DEE11EB801C' -configuration Release \
  -allowProvisioningUpdates build 2>&1 | grep -E "BUILD SUCCEEDED|BUILD FAILED|error:" | sed 's|.*BodyOS/BodyOS/||' | head
APP_PATH=$(find ~/Library/Developer/Xcode/DerivedData/BodyOS-* -name "BodyOS.app" -path "*/Release-iphoneos/*" | head -1)
DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer xcrun devicectl device install app --device 00008140-00161DEE11EB801C "$APP_PATH" 2>&1 | grep -E "installed|error" | head -1
```
Expected: `BUILD SUCCEEDED` + `App installed`. (Compile-Fehler iterativ fixen.)

- [ ] **Step 3: Commit**

```bash
git add apps/BodyOS/BodyOS/Views/NutritionView.swift
git commit -m "feat(BodyOS): async photo flow — description, pending+poll, tap-to-edit meals"
```

---

### Task 5: End-to-End-Verifikation + Spec-Abgleich

**Files:** keine (nur Verifikation)

- [ ] **Step 1: Alle Tests grün**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/ -q`
Expected: alle grün.

- [ ] **Step 2: Async-Flow gegen Server (echtes Bild)**

Run (ein vorhandenes JPEG nutzen, z.B. aus Downloads):
```bash
cd /Users/timoegersdorfer/Alfred
IMG=$(ls ~/Downloads/*.jpg ~/Downloads/*.jpeg 2>/dev/null | head -1)
echo "Bild: $IMG"
R=$(curl -s -X POST localhost:7779/api/nutrition/analyze-photo -F "text=Testmahlzeit" -F "image=@$IMG")
echo "sofortige Antwort: $R"
MID=$(echo "$R" | python3 -c "import sys,json;print(json.load(sys.stdin)['meal_id'])")
echo "warte auf Hintergrund-Analyse…"; sleep 25
curl -s localhost:7779/api/nutrition | python3 -c "import sys,json;d=json.load(sys.stdin);m=[x for x in d['meals'] if x['id']==$MID];print('Ergebnis:', {k:m[0].get(k) for k in ('status','description','calories','protein_g')} if m else 'fehlt')"
curl -s -X DELETE localhost:7779/api/nutrition/$MID >/dev/null; echo "Test-Mahlzeit entfernt"
```
Expected: sofortige Antwort `status:analyzing` in <1 s; nach ~25 s `status:done` mit Kalorien
(oder `failed`, falls das Modell nichts erkennt) — entscheidend: der Request blockierte nicht.

- [ ] **Step 3: Manuelle Sichtung am iPhone**

BodyOS → Ernährung → Foto → Beschreibung eingeben → „Analysieren": Mahlzeit erscheint sofort
als „wird analysiert…", App bleibt bedienbar (anderer Tab), füllt sich nach kurzer Zeit selbst.
Mahlzeit antippen → Werte korrigieren → Sichern.

- [ ] **Step 4: Spec-Abgleich**

`docs/superpowers/specs/2026-06-27-async-photo-analysis-design.md` durchgehen: Status-Spalte,
async Endpoint + Background-Task, Beschreibung als Hinweis+Name, Tap-to-Edit, Pending-Anzeige +
Polling, Startup-Cleanup. Abweichungen notieren.
