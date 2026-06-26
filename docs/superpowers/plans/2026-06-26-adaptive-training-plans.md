# Alfred adaptive Trainingspläne Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Alfred generiert vollautomatisch alle 6 Wochen individuelle Trainingspläne (Übungen pro LOWER/UPPER-Slot) basierend auf einem Nutzerprofil; `today-plan` konsumiert sie statt hardcodierter Listen.

**Architecture:** Ein Nutzerprofil (Settings-JSON) speist eine LLM-Generierung (Claude Haiku, qwen-Fallback), deren Output über eine pure `normalize_plan`-Funktion validiert und via `save_training_plan` persistiert wird. Ein pure `needs_regen` steuert den 6-Wochen-Auto-Trigger im Idle-Loop. `today-plan` liest den aktiven Plan, mit hardcodierten Defaults als Fallback.

**Tech Stack:** Python/FastAPI, Postgres (JSONB), LLM (`chat_llm`/`bg_llm`), SwiftUI, pytest.

## Global Constraints

- `.env` ist gitignored — nie committen.
- Zyklus LOWER → JOGGEN → UPPER bleibt unverändert; Plan füllt nur `lower`/`upper`.
- Generierung läuft über `orch.chat_llm` (Claude Haiku), Fallback `orch.bg_llm` (qwen), dann hardcodierte Defaults. `today-plan` bricht NIE.
- LLM-`chat`-Signatur: `await llm.chat(messages=[{"role":"user","content":...}], temperature=…, max_tokens=…, format="json") -> str`.
- DB nur über `core.db`; Settings über `db.get_setting`/`db.set_setting` (value ist JSONB → get liefert dict).
- iOS-Build/Deploy: `DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer`, Device-ID `00008140-00161DEE11EB801C`.
- Plan-Regeneration-Schwelle: 42 Tage (= 6 Wochen).

---

### Task 1: Pure Plan-Logik (normalize_plan, needs_regen, DEFAULT_PLAN) + Tests

**Files:**
- Create: `domains/plan_generator.py`
- Test: `tests/test_plan_generator.py`

**Interfaces:**
- Produces:
  - `DEFAULT_PLAN: dict` — `{"lower":[{name,weight,reps,sets,rpe}],"upper":[...]}`
  - `normalize_plan(raw: dict | None) -> dict | None` — validiert/säubert LLM-JSON; `None` wenn lower oder upper leer/fehlt.
  - `needs_regen(plan: dict | None, today: date) -> bool` — True wenn kein Plan oder ≥42 Tage alt.

- [ ] **Step 1: Failing test schreiben**

`tests/test_plan_generator.py`:
```python
"""Unit-Tests für die pure Plan-Logik (ohne DB/LLM)."""
import sys, os
from datetime import date, datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domains.plan_generator import normalize_plan, needs_regen, DEFAULT_PLAN

TODAY = date(2026, 6, 26)


class TestNormalizePlan:
    def test_valid_plan_passes(self):
        raw = {"lower": [{"name": "Squat", "weight": 100, "reps": 5, "sets": 4, "rpe": 8}],
               "upper": [{"name": "Bench", "weight": 80, "reps": 6, "sets": 4}]}
        out = normalize_plan(raw)
        assert out["lower"][0]["name"] == "Squat"
        assert out["upper"][0]["sets"] == 4
        assert out["upper"][0]["reps"] == 6

    def test_missing_upper_returns_none(self):
        assert normalize_plan({"lower": [{"name": "Squat", "reps": 5, "sets": 4}]}) is None

    def test_not_a_dict_returns_none(self):
        assert normalize_plan(None) is None
        assert normalize_plan("nope") is None

    def test_exercise_without_name_dropped(self):
        raw = {"lower": [{"name": "", "reps": 5, "sets": 4}, {"name": "Squat", "reps": 5, "sets": 4}],
               "upper": [{"name": "Bench", "reps": 6, "sets": 4}]}
        out = normalize_plan(raw)
        assert len(out["lower"]) == 1
        assert out["lower"][0]["name"] == "Squat"

    def test_all_exercises_invalid_returns_none(self):
        raw = {"lower": [{"name": "", "reps": 5}], "upper": [{"name": "Bench", "reps": 6, "sets": 4}]}
        assert normalize_plan(raw) is None

    def test_sets_reps_clamped(self):
        raw = {"lower": [{"name": "Squat", "reps": 999, "sets": 99}],
               "upper": [{"name": "Bench", "reps": 6, "sets": 4}]}
        out = normalize_plan(raw)
        assert out["lower"][0]["sets"] == 6     # 1..6
        assert out["lower"][0]["reps"] == 30    # 1..30

    def test_default_plan_is_valid(self):
        assert normalize_plan(DEFAULT_PLAN) is not None


class TestNeedsRegen:
    def test_no_plan_needs_regen(self):
        assert needs_regen(None, TODAY) is True

    def test_fresh_plan_no_regen(self):
        plan = {"created_at": datetime(2026, 6, 20, 10, 0)}
        assert needs_regen(plan, TODAY) is False

    def test_old_plan_needs_regen(self):
        plan = {"created_at": datetime(2026, 5, 1, 10, 0)}  # > 42 Tage
        assert needs_regen(plan, TODAY) is True

    def test_exactly_42_days_regen(self):
        plan = {"created_at": datetime.combine(TODAY - timedelta(days=42), datetime.min.time())}
        assert needs_regen(plan, TODAY) is True

    def test_missing_created_at_needs_regen(self):
        assert needs_regen({}, TODAY) is True
```

- [ ] **Step 2: Test ausführen, FAIL bestätigen**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_plan_generator.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'domains.plan_generator'`

- [ ] **Step 3: `domains/plan_generator.py` anlegen**

```python
"""Adaptive Trainingsplan-Generierung: pure Validierung + LLM-Orchestrierung."""
import logging
from datetime import date, datetime

log = logging.getLogger("alfred.plan")

DEFAULT_PLAN = {
    "lower": [
        {"name": "Squat", "weight": 100, "reps": 5, "sets": 4, "rpe": 8},
        {"name": "Romanian Deadlift", "weight": 80, "reps": 8, "sets": 3, "rpe": 7},
        {"name": "Leg Press", "weight": 140, "reps": 10, "sets": 3, "rpe": 8},
        {"name": "Leg Curl", "weight": 50, "reps": 12, "sets": 3, "rpe": 8},
        {"name": "Calf Raise", "weight": 60, "reps": 15, "sets": 4, "rpe": 9},
    ],
    "upper": [
        {"name": "Bench Press", "weight": 80, "reps": 6, "sets": 4, "rpe": 8},
        {"name": "Overhead Press", "weight": 50, "reps": 8, "sets": 3, "rpe": 7},
        {"name": "Barbell Row", "weight": 70, "reps": 8, "sets": 4, "rpe": 7},
        {"name": "Dumbbell Curl", "weight": 16, "reps": 10, "sets": 3, "rpe": 8},
        {"name": "Tricep Pushdown", "weight": 35, "reps": 12, "sets": 3, "rpe": 8},
        {"name": "Lateral Raise", "weight": 10, "reps": 15, "sets": 3, "rpe": 9},
    ],
}


def _clamp_int(v, lo: int, hi: int, default: int) -> int:
    try:
        v = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def normalize_plan(raw) -> dict | None:
    """Validiert/säubert LLM-JSON zu {lower:[...], upper:[...]}. None wenn ungültig."""
    if not isinstance(raw, dict):
        return None
    out = {}
    for slot in ("lower", "upper"):
        items = raw.get(slot)
        if not isinstance(items, list):
            return None
        cleaned = []
        for it in items:
            if not isinstance(it, dict):
                continue
            name = (it.get("name") or "").strip()
            if not name:
                continue
            ex = {"name": name,
                  "sets": _clamp_int(it.get("sets"), 1, 6, 3),
                  "reps": _clamp_int(it.get("reps"), 1, 30, 8)}
            w = it.get("weight")
            try:
                if w is not None:
                    ex["weight"] = float(w)
            except (TypeError, ValueError):
                pass
            rpe = it.get("rpe")
            if rpe is not None:
                ex["rpe"] = _clamp_int(rpe, 1, 10, 7)
            cleaned.append(ex)
        if not cleaned:
            return None
        out[slot] = cleaned
    return out


def needs_regen(plan: dict | None, today: date) -> bool:
    """True wenn kein Plan vorhanden oder der aktive Plan ≥42 Tage alt ist."""
    if not plan:
        return True
    created = plan.get("created_at")
    if isinstance(created, datetime):
        d = created.date()
    elif isinstance(created, date):
        d = created
    elif created:
        d = date.fromisoformat(str(created)[:10])
    else:
        return True
    return (today - d).days >= 42
```

- [ ] **Step 4: Test ausführen, PASS bestätigen**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_plan_generator.py -v`
Expected: PASS (alle 12 Tests grün)

- [ ] **Step 5: Commit**

```bash
git add domains/plan_generator.py tests/test_plan_generator.py
git commit -m "feat(plan): pure plan normalization + regen logic"
```

---

### Task 2: Trainingsprofil — Speicherung + Merge + Endpoints

**Files:**
- Modify: `domains/fitness.py` (Profil-Helfer am Dateiende)
- Modify: `web/routers/fitness.py` (zwei Endpoints)
- Test: `tests/test_fitness.py` (TestMergeProfile)

**Interfaces:**
- Produces:
  - `fitness.DEFAULT_PROFILE: dict`
  - `fitness.merge_profile(cur: dict, patch: dict) -> dict` (pure)
  - `fitness.get_training_profile() -> dict`
  - `fitness.save_training_profile(patch: dict) -> dict`
  - HTTP: `GET /api/fitness/profile`, `PUT /api/fitness/profile`

- [ ] **Step 1: Failing test schreiben**

Ans Ende von `tests/test_fitness.py` anhängen:
```python


class TestMergeProfile:
    def test_patch_overrides_only_allowed_keys(self):
        from domains.fitness import merge_profile, DEFAULT_PROFILE
        cur = dict(DEFAULT_PROFILE)
        out = merge_profile(cur, {"goal": "strength", "hacker": "x"})
        assert out["goal"] == "strength"
        assert "hacker" not in out

    def test_unset_keys_keep_current(self):
        from domains.fitness import merge_profile
        cur = {"goal": "muscle", "equipment": "gym", "experience": "advanced", "notes": "knie"}
        out = merge_profile(cur, {"equipment": "home"})
        assert out["equipment"] == "home"
        assert out["goal"] == "muscle"
        assert out["notes"] == "knie"

    def test_empty_patch_returns_current(self):
        from domains.fitness import merge_profile, DEFAULT_PROFILE
        assert merge_profile(dict(DEFAULT_PROFILE), {}) == DEFAULT_PROFILE
```

- [ ] **Step 2: Test ausführen, FAIL bestätigen**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_fitness.py::TestMergeProfile -v`
Expected: FAIL mit `ImportError: cannot import name 'merge_profile'`

- [ ] **Step 3: Profil-Helfer in `domains/fitness.py` (am Dateiende) einfügen**

```python


# ── Trainingsprofil (Basis für adaptive Pläne) ──────────────────────────────

DEFAULT_PROFILE = {"goal": "muscle", "equipment": "gym",
                   "experience": "intermediate", "notes": ""}
_PROFILE_KEYS = ("goal", "equipment", "experience", "notes")


def merge_profile(cur: dict, patch: dict) -> dict:
    """Mergt einen Profil-Patch (nur erlaubte Keys) auf das aktuelle Profil."""
    allowed = {k: patch[k] for k in _PROFILE_KEYS if k in patch}
    return {**cur, **allowed}


def get_training_profile() -> dict:
    p = db.get_setting("training_profile")
    if not isinstance(p, dict):
        return dict(DEFAULT_PROFILE)
    return {**DEFAULT_PROFILE, **p}


def save_training_profile(patch: dict) -> dict:
    merged = merge_profile(get_training_profile(), patch)
    db.set_setting("training_profile", merged)
    return merged
```

- [ ] **Step 4: Test ausführen, PASS bestätigen**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_fitness.py::TestMergeProfile -v`
Expected: PASS (3 Tests grün)

- [ ] **Step 5: Endpoints in `web/routers/fitness.py` einfügen**

Direkt vor `return router` (nach dem `rest_day`-Endpoint):
```python
    @router.get("/api/fitness/profile")
    def get_profile():
        return fitness.get_training_profile()

    @router.put("/api/fitness/profile")
    async def put_profile(req: Request):
        try:
            d = await req.json()
        except Exception:
            d = {}
        return fitness.save_training_profile(d if isinstance(d, dict) else {})
```

- [ ] **Step 6: Verifizieren + Commit**

Run:
```bash
cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/ -q && python3 -c "import web.routers.fitness; print('ok')"
```
Expected: alle grün, `ok`

```bash
git add domains/fitness.py web/routers/fitness.py tests/test_fitness.py
git commit -m "feat(fitness): training profile storage + endpoints"
```

---

### Task 3: LLM-Generierung (build_prompt + generate_and_save)

**Files:**
- Modify: `domains/plan_generator.py` (Prompt-Bau + async Orchestrierung)
- Test: `tests/test_plan_generator.py` (TestBuildPrompt)

**Interfaces:**
- Consumes: `fitness.get_training_profile`, `fitness.active_plan`, `fitness.muscle_volume`, `fitness.ensure_exercise`, `fitness.save_training_plan`; `core.jsonutil.extract_json`; `normalize_plan` (Task 1).
- Produces:
  - `build_prompt(profile: dict, last_exercises: list[str], muscle_volume: dict) -> str` (pure)
  - `async generate_and_save(chat_llm, bg_llm=None) -> dict | None`

- [ ] **Step 1: Failing test schreiben**

Ans Ende von `tests/test_plan_generator.py` anhängen:
```python


class TestBuildPrompt:
    def test_prompt_contains_profile_and_schema(self):
        from domains.plan_generator import build_prompt
        p = build_prompt(
            {"goal": "muscle", "equipment": "home", "experience": "advanced", "notes": "Knie schonen"},
            ["Squat", "Bench Press"], {"legs": 12, "chest": 8})
        assert "muscle" in p and "home" in p and "advanced" in p
        assert "Knie schonen" in p
        assert "Squat" in p          # Vermeidungs-Hinweis enthält letzte Übungen
        assert "lower" in p and "upper" in p   # Schema
```

- [ ] **Step 2: Test ausführen, FAIL bestätigen**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_plan_generator.py::TestBuildPrompt -v`
Expected: FAIL mit `ImportError: cannot import name 'build_prompt'`

- [ ] **Step 3: `build_prompt` + `generate_and_save` in `domains/plan_generator.py` einfügen**

Am Dateiende anhängen:
```python


def build_prompt(profile: dict, last_exercises: list[str], muscle_volume: dict) -> str:
    avoid = ", ".join(last_exercises) if last_exercises else "—"
    vol = ", ".join(f"{k}:{v}" for k, v in (muscle_volume or {}).items() if v)
    return (
        "Du bist ein Personal Trainer. Erstelle einen 6-Wochen-Trainingsplan für einen "
        "Push/Pull-freien Split mit genau zwei Krafttagen: LOWER (Beine/Rumpf) und UPPER "
        "(Oberkörper). Joggen ist separat und NICHT Teil des Plans.\n\n"
        f"Profil:\n- Ziel: {profile.get('goal')}\n- Equipment: {profile.get('equipment')}\n"
        f"- Erfahrung: {profile.get('experience')}\n- Hinweise: {profile.get('notes') or 'keine'}\n\n"
        f"Trainiertes Volumen (letzte 30 Tage, Sätze je Muskel): {vol or 'wenig Daten'}\n"
        f"Übungen des letzten Plans (bitte variieren, möglichst NICHT wiederholen): {avoid}\n\n"
        "Wähle pro Tag 5–6 Übungen passend zu Ziel, Equipment und Erfahrung. "
        "Realistische Startgewichte in kg. Antworte AUSSCHLIESSLICH mit JSON in genau diesem Schema:\n"
        '{"lower":[{"name":"...","weight":100,"reps":5,"sets":4,"rpe":8}],'
        '"upper":[{"name":"...","weight":80,"reps":6,"sets":4,"rpe":8}]}'
    )


async def generate_and_save(chat_llm, bg_llm=None) -> dict | None:
    """Generiert einen Plan via LLM (Claude→qwen Fallback), validiert, speichert.
    Gibt den gespeicherten Plan zurück oder None (dann bleibt der alte Plan aktiv)."""
    from domains import fitness
    from core.jsonutil import extract_json

    profile = fitness.get_training_profile()
    last = fitness.active_plan()
    last_ex: list[str] = []
    if last and isinstance(last.get("plan_json"), dict):
        for slot in ("lower", "upper"):
            last_ex += [e.get("name") for e in last["plan_json"].get(slot, []) if e.get("name")]
    muscle = fitness.muscle_volume(30)
    prompt = build_prompt(profile, last_ex, muscle)

    plan = None
    for llm in (chat_llm, bg_llm):
        if not llm:
            continue
        try:
            txt = await llm.chat(messages=[{"role": "user", "content": prompt}],
                                 temperature=0.4, max_tokens=1200, format="json")
            plan = normalize_plan(extract_json(txt, default=None))
            if plan:
                break
        except Exception:
            log.exception("Plan-LLM fehlgeschlagen, versuche Fallback")
            plan = None

    if not plan:
        log.warning("Plan-Generierung lieferte keinen gültigen Plan — alter Plan bleibt aktiv")
        return None

    for slot in ("lower", "upper"):
        for ex in plan[slot]:
            fitness.ensure_exercise(ex["name"])
    fitness.save_training_plan(name="Alfred-Block", goal=profile.get("goal", "muscle"),
                               weeks=6, plan=plan)
    log.info("Neuer Trainingsplan generiert und gespeichert")
    return plan
```

- [ ] **Step 4: Test ausführen, PASS bestätigen**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_plan_generator.py -v`
Expected: PASS (alle Tests inkl. TestBuildPrompt grün)

- [ ] **Step 5: Commit**

```bash
git add domains/plan_generator.py tests/test_plan_generator.py
git commit -m "feat(plan): LLM plan generation with Claude→qwen fallback"
```

---

### Task 4: today-plan konsumiert aktiven Plan + manueller Generate-Endpoint

**Files:**
- Modify: `web/routers/fitness.py` (`today_plan` Übungsaufbau, neuer Endpoint)

**Interfaces:**
- Consumes: `fitness.active_plan`, `plan_generator.DEFAULT_PLAN`, `plan_generator.generate_and_save`.
- Produces (HTTP): `today-plan` mit zusätzlichen Feldern `plan_week: int|None`, `plan_source: str`; `POST /api/fitness/plan/generate`.

- [ ] **Step 1: Import ergänzen**

In `web/routers/fitness.py` bei den Domain-Imports (Zeile ~21) `plan_generator` ergänzen:
```python
from domains import habits, fitness, nutrition, journal, goals, weather, tasks as tasks_d, calendar as cal_d
from domains import second_brain as _brain
from domains import plan_generator
```

- [ ] **Step 2: Übungsaufbau in `today_plan()` auf aktiven Plan umstellen**

In `web/routers/fitness.py` den Block, der `exercises_list` für lower/upper baut, ersetzen.
Suche den Abschnitt ab `if day_type == "lower":` bis vor `else:  # jog` und ersetze die
beiden Branches durch eine plan-getriebene Variante:
```python
        plan_row = fitness.active_plan()
        plan_json = plan_row.get("plan_json") if plan_row else None
        plan_source = "alfred" if isinstance(plan_json, dict) and plan_json.get(day_type) else "default"
        plan_week = None
        if plan_source == "alfred":
            created = plan_row.get("created_at")
            if created is not None:
                from datetime import datetime as _dt2, date as _date2
                cd = created.date() if isinstance(created, _dt2) else created
                if isinstance(cd, _date2):
                    plan_week = min(6, (_date.today() - cd).days // 7 + 1)

        def _block(slot: str) -> list[dict]:
            src = plan_json.get(slot) if isinstance(plan_json, dict) and plan_json.get(slot) \
                else plan_generator.DEFAULT_PLAN[slot]
            return [build_sets(ex["name"], float(ex.get("weight") or 20), int(ex.get("reps") or 8),
                               working_count=int(ex.get("sets") or 3),
                               rpe_target=int(ex.get("rpe") or 7)) for ex in src]

        if day_type == "lower":
            exercises_list = _block("lower")
        elif day_type == "upper":
            exercises_list = _block("upper")
        else:  # jog
            exercises_list = []
            alfred_note = "Heute: Joggen — läuft über Strava."
```
(Den alten `else:  # jog`-Block mit ersetzen — er ist im neuen Code enthalten.)

- [ ] **Step 3: Response um `plan_week`/`plan_source` erweitern**

Im `return {…}` von `today_plan()` zwei Felder ergänzen:
```python
            "done_today": done_today,
            "next_label": state["next_label"],
            "plan_week": plan_week,
            "plan_source": plan_source,
```
(Die ersten beiden Zeilen existieren bereits — `plan_week`/`plan_source` direkt darunter einfügen. Für den Jog-Tag sind die Werte unkritisch.)

- [ ] **Step 4: Generate-Endpoint einfügen**

Vor `return router` (nach den Profil-Endpoints aus Task 2):
```python
    @router.post("/api/fitness/plan/generate")
    async def generate_plan(req: Request):
        if not orch:
            return JSONResponse({"error": "kein Kern"}, 503)
        plan = await plan_generator.generate_and_save(orch.chat_llm, orch.bg_llm)
        if not plan:
            return JSONResponse({"ok": False, "error": "Generierung fehlgeschlagen"}, 502)
        return {"ok": True, "plan": plan}
```

- [ ] **Step 5: Verifizieren (Import + Fallback ohne Plan)**

Run:
```bash
cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/ -q && python3 -c "import web.routers.fitness; print('ok')"
```
Expected: alle grün, `ok`

Server neu starten + today-plan-Fallback prüfen (kein aktiver Plan → Default-Übungen):
```bash
cd /Users/timoegersdorfer/Alfred && ./start.sh >/dev/null 2>&1; sleep 5
curl -s localhost:7779/api/fitness/today-plan | python3 -c "import sys,json;d=json.load(sys.stdin);print('source',d['plan_source'],'week',d['plan_week'],'exercises',len(d['exercises']))"
```
Expected: `source default week None exercises 5` (lower-Tag, DB heute leer)

- [ ] **Step 6: Commit**

```bash
git add web/routers/fitness.py
git commit -m "feat(fitness): today-plan reads active plan + manual generate endpoint"
```

---

### Task 5: Idle-Loop Auto-Trigger (alle 6 Wochen)

**Files:**
- Modify: `core/idle_loop.py` (chat_llm-Param, `_last_plan_check`, `_tick_plan`)
- Modify: `orchestrator.py` (chat_llm in IdleLoop-Wiring)

**Interfaces:**
- Consumes: `plan_generator.needs_regen`, `plan_generator.generate_and_save`, `fitness.active_plan`.

- [ ] **Step 1: `chat_llm` in `IdleLoop.__init__` aufnehmen**

In `core/idle_loop.py`, in der `__init__`-Signatur `bg_llm` um `chat_llm` ergänzen und zuweisen.
Signatur (Zeile ~33) `bg_llm, suggest_one,` → `bg_llm, chat_llm, suggest_one,`.
Im Body nach `self.bg_llm = bg_llm` einfügen:
```python
        self.chat_llm            = chat_llm
```
Bei den `_last_*`-Feldern (nach `self._last_insight_run`) ergänzen:
```python
        self._last_plan_check: datetime | None = None
```

- [ ] **Step 2: `_tick_plan` hinzufügen + im Loop aufrufen**

In `core/idle_loop.py` eine neue Methode neben `_tick_maintenance` einfügen:
```python
    async def _tick_plan(self) -> None:
        """Alle 6h prüfen, ob ein neuer Trainingsplan fällig ist (≥42 Tage / keiner)."""
        now = datetime.now()
        if _elapsed_since(self._last_plan_check, now) < 21600:
            return
        self._last_plan_check = now
        try:
            from datetime import date as _date
            from domains import fitness, plan_generator
            if plan_generator.needs_regen(fitness.active_plan(), _date.today()):
                await plan_generator.generate_and_save(self.chat_llm, self.bg_llm)
        except Exception:
            log.exception("Plan-Auto-Generierung fehlgeschlagen")
```
An der Stelle, wo `await self._tick_maintenance()` aufgerufen wird (Zeile ~90), direkt danach:
```python
                await self._tick_plan()
```

- [ ] **Step 3: `orchestrator.py` — chat_llm durchreichen**

In `orchestrator.py` im `IdleLoop(...)`-Aufruf `bg_llm=bg_llm,` um `chat_llm` ergänzen:
```python
            bg_llm=bg_llm, chat_llm=chat_llm, suggest_one=suggest_one,
```

- [ ] **Step 4: Verifizieren (Start ohne Fehler)**

Run:
```bash
cd /Users/timoegersdorfer/Alfred && python3 -c "import core.idle_loop, orchestrator; print('import ok')"
./start.sh >/dev/null 2>&1; sleep 5
curl -s -m 5 localhost:7779/health >/dev/null && echo "Alfred läuft" || (echo "FEHLER"; tail -20 /tmp/alfred_out.log)
```
Expected: `import ok`, `Alfred läuft`

- [ ] **Step 5: Commit**

```bash
git add core/idle_loop.py orchestrator.py
git commit -m "feat(plan): idle-loop auto-regenerates plan every 6 weeks"
```

---

### Task 6: BodyOS — Profil-Screen, Generate-Button, Wochen-Badge

**Files:**
- Modify: `apps/BodyOS/BodyOS/Models/BodyModels.swift` (TrainingProfile, TodayPlan-Felder)
- Modify: `apps/BodyOS/BodyOS/API/FitnessAPI.swift` (3 Calls)
- Modify: `apps/BodyOS/BodyOS/Views/BodySettingsView.swift` (Profil-Section)
- Modify: `apps/BodyOS/BodyOS/Views/WorkoutView.swift` (Badge + Generate-Button)

**Interfaces:**
- Consumes (HTTP): Endpoints aus Task 2/4.
- Produces (Swift): `TrainingProfile`; `FitnessAPI.fetchProfile/saveProfile/generatePlan`; `TodayPlan.planWeek/planSource`.

- [ ] **Step 1: Models erweitern**

In `apps/BodyOS/BodyOS/Models/BodyModels.swift` `TodayPlan` um zwei Felder ergänzen:
```swift
    let doneToday: Bool?
    let nextLabel: String?
    let planWeek: Int?
    let planSource: String?
}
```
Und eine neue Struct (z.B. nach `TodayPlan`):
```swift
struct TrainingProfile: Codable {
    var goal: String
    var equipment: String
    var experience: String
    var notes: String
}
```

- [ ] **Step 2: API-Calls in `FitnessAPI.swift` ergänzen**

Vor der schließenden `}`:
```swift
    func fetchProfile() async throws -> TrainingProfile {
        try await client.get("/api/fitness/profile")
    }

    func saveProfile(_ p: TrainingProfile) async throws -> TrainingProfile {
        try await client.put("/api/fitness/profile", body: p)
    }

    @discardableResult
    func generatePlan() async throws -> OkResponse {
        try await client.post("/api/fitness/plan/generate", body: EmptyReqBody())
    }
}

private struct EmptyReqBody: Encodable {}
```
(Die schließende `}` der Klasse wird durch obigen Block ersetzt — `EmptyReqBody` steht danach auf Dateiebene.)

- [ ] **Step 3: `put` in AlfredClient ergänzen**

`AlfredClient.post` baut die Request inline (kein gemeinsamer `send`-Helper). `put` ist daher
eine 1:1-Kopie von `post` mit `httpMethod = "PUT"`. In `apps/BodyOS/BodyOS/API/AlfredClient.swift`
direkt nach der `post`-Methode (Zeile ~30) einfügen:
```swift
    func put<Body: Encodable, T: Decodable>(_ path: String, body: Body) async throws -> T {
        var req = URLRequest(url: try makeURL(path))
        req.httpMethod = "PUT"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(body)
        let data = try await withRetry { try await self.session.data(for: req) }
        return try decode(T.self, from: data)
    }
```

- [ ] **Step 4: Profil-Section in `BodySettingsView.swift`**

In `BodySettingsView` ein `@State private var profile: TrainingProfile?` ergänzen und eine
Section vor „Info" einfügen:
```swift
                Section("Trainingsprofil") {
                    if let p = Binding($profile) {
                        Picker("Ziel", selection: p.goal) {
                            Text("Muskelaufbau").tag("muscle")
                            Text("Kraft").tag("strength")
                            Text("Recomp").tag("recomp")
                        }
                        Picker("Equipment", selection: p.equipment) {
                            Text("Gym").tag("gym")
                            Text("Home").tag("home")
                            Text("Minimal").tag("minimal")
                        }
                        Picker("Erfahrung", selection: p.experience) {
                            Text("Anfänger").tag("beginner")
                            Text("Fortgeschritten").tag("intermediate")
                            Text("Erfahren").tag("advanced")
                        }
                        TextField("Hinweise (Verletzungen, Vorlieben)", text: p.notes, axis: .vertical)
                        Button("Profil speichern") {
                            Task { if let saved = try? await FitnessAPI.shared.saveProfile(p.wrappedValue) { profile = saved } }
                        }
                    } else {
                        ProgressView()
                    }
                }
```
Und in `body` ein `.task { profile = try? await FitnessAPI.shared.fetchProfile() }` an die `Form`
hängen (oder am `NavigationStack`).

- [ ] **Step 5: Badge + Generate-Button in `WorkoutView.swift`**

In `WorkoutView` eine Hilfs-View ergänzen und im `dayHeaderCard` bzw. direkt darunter einbinden.
Nach `dayHeaderCard(plan)` in `todayContent` (im nicht-erledigt-Zweig oder generell) einfügen:
```swift
                    if let week = plan.planWeek, plan.planSource == "alfred" {
                        Text("Plan: Woche \(week)/6 · von Alfred")
                            .font(.caption).foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal)
                    }
```
Und einen Generate-Button (z.B. ganz unten in `todayContent`, vor `.padding(.bottom, 32)` schließt):
```swift
                    Button { Task { try? await FitnessAPI.shared.generatePlan(); await vm.loadPlan() } } label: {
                        Label("Neuen Plan generieren", systemImage: "sparkles")
                            .font(.caption).frame(maxWidth: .infinity).padding(.vertical, 8)
                    }
                    .padding(.horizontal)
```

- [ ] **Step 6: Build + Deploy**

Run:
```bash
cd /Users/timoegersdorfer/Alfred
DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer xcodebuild \
  -project apps/BodyOS/BodyOS.xcodeproj -scheme BodyOS \
  -destination 'platform=iOS,id=00008140-00161DEE11EB801C' \
  -configuration Release build 2>&1 | grep -E "BUILD SUCCEEDED|BUILD FAILED|error:" | head
APP_PATH=$(find ~/Library/Developer/Xcode/DerivedData/BodyOS-* -name "BodyOS.app" -path "*/Release-iphoneos/*" | head -1)
DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer xcrun devicectl device install app \
  --device 00008140-00161DEE11EB801C "$APP_PATH" 2>&1 | grep -E "installed|error" | head -1
```
Expected: `BUILD SUCCEEDED` + `App installed`
(Bei Swift-Compile-Fehlern: Meldung lesen, betroffene View/Model fixen, neu bauen.)

- [ ] **Step 7: Commit**

```bash
git add apps/BodyOS/BodyOS/Models/BodyModels.swift apps/BodyOS/BodyOS/API/FitnessAPI.swift \
        apps/BodyOS/BodyOS/API/AlfredClient.swift apps/BodyOS/BodyOS/Views/BodySettingsView.swift \
        apps/BodyOS/BodyOS/Views/WorkoutView.swift
git commit -m "feat(BodyOS): training profile screen + plan week badge + generate button"
```

---

### Task 7: End-to-End-Verifikation + Spec-Abgleich

**Files:** keine (nur Verifikation)

- [ ] **Step 1: Profil setzen + Plan generieren (echter LLM-Call)**

Run (Alfred läuft):
```bash
cd /Users/timoegersdorfer/Alfred
curl -s -X PUT localhost:7779/api/fitness/profile -H 'Content-Type: application/json' \
  -d '{"goal":"muscle","equipment":"gym","experience":"advanced","notes":"keine"}' | python3 -m json.tool
echo "--- generieren (kann ein paar Sekunden dauern) ---"
curl -s -X POST localhost:7779/api/fitness/plan/generate | python3 -c "import sys,json;d=json.load(sys.stdin);print('ok',d.get('ok'),'| lower',len(d.get('plan',{}).get('lower',[])),'| upper',len(d.get('plan',{}).get('upper',[]))" 2>/dev/null || echo "Generierung-Response prüfen"
```
Expected: Profil gespeichert; `ok True` mit je ≥1 Übung in lower/upper.

- [ ] **Step 2: today-plan nutzt jetzt den generierten Plan**

Run:
```bash
curl -s localhost:7779/api/fitness/today-plan | python3 -c "import sys,json;d=json.load(sys.stdin);print('source',d['plan_source'],'week',d['plan_week'],'erste Übung',d['exercises'][0]['name'] if d['exercises'] else '—')"
```
Expected: `source alfred week 1` und eine Übung aus dem generierten Plan.

- [ ] **Step 3: Fallback-Sicherheit prüfen (kaputtes JSON simulieren)**

Run:
```bash
cd /Users/timoegersdorfer/Alfred && python3 -c "
from domains.plan_generator import normalize_plan
assert normalize_plan({'lower':[],'upper':[]}) is None
assert normalize_plan('müll') is None
print('normalize_plan robust')
"
```
Expected: `normalize_plan robust`

- [ ] **Step 4: Generierten Test-Plan wieder entfernen (sauberer Zustand)**

Run:
```bash
cd /Users/timoegersdorfer/Alfred && python3 -c "from core import db; db.execute(\"UPDATE training_plans SET active=FALSE WHERE name='Alfred-Block'\"); print('Plan deaktiviert → today-plan fällt auf Defaults zurück')"
```
Expected: Meldung; today-plan liefert danach wieder `plan_source default`.

- [ ] **Step 5: Alle Tests grün + Spec-Abgleich**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/ -q`
Expected: alle grün.

Spec `docs/superpowers/specs/2026-06-26-adaptive-training-plans-design.md` durchgehen:
Profil (Felder/Endpoints), Generierung (Trigger/LLM/Fallback), today-plan-Konsum + Fallback,
BodyOS-UI. Abweichungen notieren.

- [ ] **Step 6: Auf dem iPhone sichten**

BodyOS → Einstellungen → „Trainingsprofil" (Picker + Speichern), Training-Tab → Wochen-Badge
+ „Neuen Plan generieren"-Button.
