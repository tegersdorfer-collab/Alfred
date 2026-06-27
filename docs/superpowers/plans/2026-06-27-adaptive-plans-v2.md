# Adaptiv-Plan v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Alfreds Trainingsplan aufwerten — durchdachter Prompt mit voller Muskelabdeckung und A/B-Varianten pro Slot, die im Zyklus automatisch alternieren.

**Architecture:** Backend-only. `plan_generator` erzeugt vier Listen (`lowerA/lowerB/upperA/upperB`); `today-plan` wählt die Variante serverseitig per `slot_workout_count`-Count. Die App ruft unverändert `today-plan` auf und erhält dieselbe flache `exercises`-Liste plus Varianten-Label.

**Tech Stack:** Python/FastAPI, Postgres, Claude Haiku (Generierung), pytest.

## Global Constraints

- Zyklus LOWER → JOGGEN → UPPER bleibt; nur der Lower/Upper-Inhalt ändert sich.
- Plan-JSON-Schema: `{"lowerA":[…],"lowerB":[…],"upperA":[…],"upperB":[…]}`, je Übung `{name, weight?, reps, sets, rpe?}`.
- Variantenwahl: `A` wenn `slot_workout_count(slot)` gerade, sonst `B`.
- Fallback: kein aktiver Plan / Variante fehlt → `DEFAULT_PLAN[slot]` (bleibt `{lower, upper}`). today-plan bricht NIE.
- Generierung über `orch.chat_llm` (Claude Haiku), Fallback `orch.bg_llm`. Müll-JSON → alter Plan bleibt.
- Muskelabdeckung über A+B zusammen inkl. Unterarme, Nacken, Bauch/Core, Waden, hintere Schulter.

---

### Task 1: normalize_plan auf A/B + pick_variant (pure) + Tests

**Files:**
- Modify: `domains/plan_generator.py` (`normalize_plan` ersetzen, `pick_variant` neu, `_clean_exercise_list` neu)
- Modify: `tests/test_plan_generator.py` (`TestNormalizePlan` ersetzen, `TestPickVariant` neu)

**Interfaces:**
- Produces:
  - `pick_variant(slot_count: int) -> str` — "A" wenn gerade, sonst "B".
  - `normalize_plan(raw) -> dict | None` — gibt `{lowerA,lowerB,upperA,upperB}` (Listen) oder `None`.
  - `_clean_exercise_list(items) -> list` — säubert eine Übungsliste.

- [ ] **Step 1: Tests ersetzen**

In `tests/test_plan_generator.py` die ganze Klasse `TestNormalizePlan` ersetzen durch:
```python
class TestNormalizePlan:
    def _valid_raw(self):
        return {
            "lowerA": [{"name": "Squat", "weight": 100, "reps": 5, "sets": 4, "rpe": 8}],
            "lowerB": [{"name": "Deadlift", "weight": 120, "reps": 5, "sets": 3}],
            "upperA": [{"name": "Bench", "weight": 80, "reps": 6, "sets": 4}],
            "upperB": [{"name": "Overhead Press", "weight": 50, "reps": 8, "sets": 3}],
        }

    def test_valid_ab_plan_passes(self):
        out = normalize_plan(self._valid_raw())
        assert out["lowerA"][0]["name"] == "Squat"
        assert out["upperB"][0]["name"] == "Overhead Press"
        assert set(out.keys()) == {"lowerA", "lowerB", "upperA", "upperB"}

    def test_missing_upperA_returns_none(self):
        raw = self._valid_raw(); del raw["upperA"]
        assert normalize_plan(raw) is None

    def test_missing_lowerB_falls_back_to_lowerA(self):
        raw = self._valid_raw(); del raw["lowerB"]
        out = normalize_plan(raw)
        assert out["lowerB"] == out["lowerA"]

    def test_not_a_dict_returns_none(self):
        assert normalize_plan(None) is None
        assert normalize_plan("nope") is None

    def test_exercise_without_name_dropped(self):
        raw = self._valid_raw()
        raw["lowerA"] = [{"name": "", "reps": 5, "sets": 4},
                         {"name": "Squat", "reps": 5, "sets": 4}]
        out = normalize_plan(raw)
        assert len(out["lowerA"]) == 1 and out["lowerA"][0]["name"] == "Squat"

    def test_empty_lowerA_returns_none(self):
        raw = self._valid_raw(); raw["lowerA"] = [{"name": "", "reps": 5}]
        assert normalize_plan(raw) is None

    def test_sets_reps_clamped(self):
        raw = self._valid_raw()
        raw["lowerA"] = [{"name": "Squat", "reps": 999, "sets": 99}]
        out = normalize_plan(raw)
        assert out["lowerA"][0]["sets"] == 6 and out["lowerA"][0]["reps"] == 30


class TestPickVariant:
    def test_even_is_a(self):
        assert pick_variant(0) == "A"
        assert pick_variant(2) == "A"

    def test_odd_is_b(self):
        assert pick_variant(1) == "B"
        assert pick_variant(3) == "B"
```
Und den Import oben in der Datei ergänzen:
```python
from domains.plan_generator import normalize_plan, needs_regen, DEFAULT_PLAN, pick_variant
```
(Die alte Zeile `from domains.plan_generator import normalize_plan, needs_regen, DEFAULT_PLAN` ersetzen. `DEFAULT_PLAN` bleibt im Import, auch wenn `test_default_plan_is_valid` entfällt — der Test wird mit der alten `TestNormalizePlan`-Klasse mitgelöscht.)

- [ ] **Step 2: Test ausführen, FAIL bestätigen**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_plan_generator.py -q`
Expected: FAIL (ImportError `pick_variant` bzw. neue Tests rot)

- [ ] **Step 3: `normalize_plan` ersetzen + `pick_variant`/`_clean_exercise_list` ergänzen**

In `domains/plan_generator.py` die bestehende `normalize_plan`-Funktion ersetzen durch:
```python
def _clean_exercise_list(items) -> list:
    """Säubert eine Übungsliste: nur Einträge mit Namen, sets/reps gekappt."""
    if not isinstance(items, list):
        return []
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
    return cleaned


def normalize_plan(raw) -> dict | None:
    """Validiert LLM-JSON zu {lowerA,lowerB,upperA,upperB}. None wenn ungültig.
    Pflicht: lowerA + upperA nicht-leer. Fehlt eine B-Variante → B = A."""
    if not isinstance(raw, dict):
        return None
    lower_a = _clean_exercise_list(raw.get("lowerA"))
    upper_a = _clean_exercise_list(raw.get("upperA"))
    if not lower_a or not upper_a:
        return None
    lower_b = _clean_exercise_list(raw.get("lowerB")) or lower_a
    upper_b = _clean_exercise_list(raw.get("upperB")) or upper_a
    return {"lowerA": lower_a, "lowerB": lower_b, "upperA": upper_a, "upperB": upper_b}


def pick_variant(slot_count: int) -> str:
    """A bei gerader Anzahl bisheriger Slot-Sessions, sonst B (wechselt jede Runde)."""
    return "A" if slot_count % 2 == 0 else "B"
```

- [ ] **Step 4: Test ausführen, PASS bestätigen**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_plan_generator.py -q`
Expected: PASS (alle grün)

- [ ] **Step 5: Commit**

```bash
git add domains/plan_generator.py tests/test_plan_generator.py
git commit -m "feat(plan): A/B variant normalize_plan + pick_variant"
```

---

### Task 2: build_prompt v2 + generate_and_save A/B + slot_workout_count

**Files:**
- Modify: `domains/plan_generator.py` (`build_prompt`, `generate_and_save`)
- Modify: `domains/fitness.py` (`slot_workout_count` neu)

**Interfaces:**
- Consumes: `normalize_plan` (Task 1), `fitness.ensure_exercise`, `fitness.save_training_plan`, `fitness.active_plan`, `fitness.muscle_volume`, `fitness.get_training_profile`.
- Produces: `fitness.slot_workout_count(slot: str) -> int`.

- [ ] **Step 1: `slot_workout_count` in `domains/fitness.py` ergänzen**

Direkt nach `jog_done_today_exists()` (am Dateiende im Zyklus-Block):
```python
def slot_workout_count(slot: str) -> int:
    """Wie oft slot (lower/upper) schon als Workout abgeschlossen wurde — für A/B-Wahl."""
    row = db.query_one(
        "SELECT COUNT(*) AS c FROM training_cycle_events WHERE slot=%s AND kind='workout'",
        (slot,))
    return row["c"] if row else 0
```

- [ ] **Step 2: `build_prompt` v2 ersetzen**

In `domains/plan_generator.py` die `build_prompt`-Funktion ersetzen durch:
```python
def build_prompt(profile: dict, last_exercises: list[str], muscle_volume: dict) -> str:
    avoid = ", ".join(last_exercises) if last_exercises else "—"
    vol = ", ".join(f"{k}:{v}" for k, v in (muscle_volume or {}).items() if v)
    return (
        "Du bist ein erfahrener Strength-Coach und Personal Trainer. Erstelle einen "
        "durchdachten, sicheren 6-Wochen-Trainingsplan für einen Split mit zwei Krafttagen: "
        "LOWER (Beine, Hüfte, unterer Rücken, Core) und UPPER (Brust, Rücken, Schultern, Arme). "
        "Joggen ist separat und NICHT Teil des Plans.\n\n"
        f"Profil:\n- Ziel: {profile.get('goal')}\n- Equipment: {profile.get('equipment')}\n"
        f"- Erfahrung: {profile.get('experience')}\n"
        f"- Hinweise/Verletzungen: {profile.get('notes') or 'keine'}\n\n"
        f"Bisheriges Volumen je Muskel (30 Tage): {vol or 'wenig Daten'}\n"
        f"Übungen des letzten Blocks (VARIIERE, möglichst nicht wiederholen): {avoid}\n\n"
        "Erstelle JE ZWEI Varianten pro Krafttag (A und B), die sich klar unterscheiden — "
        "Timo wechselt jede Runde zwischen A und B für Abwechslung.\n"
        "Regeln pro Tag:\n"
        "- Reihenfolge: schwerer Haupt-Compound → zweiter Compound → Akzessorisch/Isolation → "
        "bewusst vernachlässigte Muskeln.\n"
        "- 5–7 Übungen pro Tag.\n"
        "- Decke über UPPER-A und UPPER-B zusammen auch UNTERARME, NACKEN und HINTERE SCHULTER ab; "
        "über LOWER-A und LOWER-B zusammen auch WADEN und BAUCH/CORE.\n"
        "- Schemata passend zum Ziel (Hypertrophie: meist 3–4 Sätze × 6–12 Wdh, Hauptübung 4–6). "
        "Realistische Startgewichte in kg, passend zu Equipment und Erfahrung.\n\n"
        "Antworte AUSSCHLIESSLICH mit JSON in genau diesem Schema:\n"
        '{"lowerA":[{"name":"...","weight":100,"reps":5,"sets":4,"rpe":8}],'
        '"lowerB":[...],"upperA":[...],"upperB":[...]}'
    )
```

- [ ] **Step 3: `generate_and_save` auf A/B umstellen**

In `domains/plan_generator.py` die `generate_and_save`-Funktion ersetzen durch:
```python
async def generate_and_save(chat_llm, bg_llm=None) -> dict | None:
    """Generiert einen A/B-Plan via LLM (Claude→qwen Fallback), validiert, speichert.
    Gibt den gespeicherten Plan zurück oder None (dann bleibt der alte Plan aktiv)."""
    from domains import fitness
    from core.jsonutil import extract_json

    profile = fitness.get_training_profile()
    last = fitness.active_plan()
    last_ex: list[str] = []
    if last and isinstance(last.get("plan_json"), dict):
        for v in last["plan_json"].values():
            if isinstance(v, list):
                last_ex += [e.get("name") for e in v if isinstance(e, dict) and e.get("name")]
    muscle = fitness.muscle_volume(30)
    prompt = build_prompt(profile, last_ex, muscle)

    plan = None
    for llm in (chat_llm, bg_llm):
        if not llm:
            continue
        try:
            txt = await llm.chat(messages=[{"role": "user", "content": prompt}],
                                 temperature=0.4, max_tokens=2500, format="json")
            plan = normalize_plan(extract_json(txt, default=None))
            if plan:
                break
        except Exception:
            log.exception("Plan-LLM fehlgeschlagen, versuche Fallback")
            plan = None

    if not plan:
        log.warning("Plan-Generierung lieferte keinen gültigen Plan — alter Plan bleibt aktiv")
        return None

    seen = set()
    for key in ("lowerA", "lowerB", "upperA", "upperB"):
        for ex in plan[key]:
            if ex["name"] not in seen:
                seen.add(ex["name"])
                fitness.ensure_exercise(ex["name"])
    fitness.save_training_plan(name="Alfred-Block", goal=profile.get("goal", "muscle"),
                               weeks=6, plan=plan)
    log.info("Neuer A/B-Trainingsplan generiert und gespeichert")
    return plan
```

- [ ] **Step 4: Verifizieren (Import + Smoke)**

Run:
```bash
cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/ -q && python3 -c "
from domains.plan_generator import build_prompt
p = build_prompt({'goal':'muscle','equipment':'gym','experience':'advanced','notes':''}, [], {})
assert 'NACKEN' in p and 'UNTERARME' in p and 'WADEN' in p and 'lowerA' in p
print('prompt v2 ok')
import web.routers.fitness; print('router import ok')"
```
Expected: alle Tests grün, `prompt v2 ok`, `router import ok`

- [ ] **Step 5: Commit**

```bash
git add domains/plan_generator.py domains/fitness.py
git commit -m "feat(plan): v2 coach prompt with full muscle coverage + A/B generation"
```

---

### Task 3: today-plan wählt die A/B-Variante

**Files:**
- Modify: `web/routers/fitness.py` (`today_plan` — Plan-Block + day_label)

**Interfaces:**
- Consumes: `fitness.slot_workout_count`, `plan_generator.pick_variant`, `plan_generator.DEFAULT_PLAN`, `fitness.active_plan`.

- [ ] **Step 1: Plan-Block in `today_plan()` ersetzen**

In `web/routers/fitness.py` den Abschnitt von `plan_row = fitness.active_plan()` bis zum
`else:  # jog`-Block (die Variante aus dem vorherigen Feature) ersetzen durch:
```python
        plan_row = fitness.active_plan()
        plan_json = plan_row.get("plan_json") if plan_row else None

        def _variant(slot: str) -> str:
            return plan_generator.pick_variant(fitness.slot_workout_count(slot))

        variant = _variant(day_type) if day_type in ("lower", "upper") else "A"
        plan_key = f"{day_type}{variant}"
        plan_source = "alfred" if isinstance(plan_json, dict) and plan_json.get(plan_key) else "default"
        plan_week = None
        if plan_source == "alfred":
            created = plan_row.get("created_at")
            if created is not None:
                from datetime import datetime as _dt2, date as _date2
                cd = created.date() if isinstance(created, _dt2) else created
                if isinstance(cd, _date2):
                    plan_week = min(6, (_date.today() - cd).days // 7 + 1)

        def _block(slot: str) -> list[dict]:
            key = f"{slot}{_variant(slot)}"
            src = plan_json.get(key) if isinstance(plan_json, dict) and plan_json.get(key) \
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

        day_label = fitness.CYCLE_LABEL[day_type]
        if day_type in ("lower", "upper"):
            day_label = f"{day_label} · {variant}"
```

- [ ] **Step 2: `day_label` im Return verwenden**

Im `return {…}` von `today_plan()` die Zeile `"day_label": fitness.CYCLE_LABEL[day_type],`
ersetzen durch:
```python
            "day_label": day_label,
```

- [ ] **Step 3: Verifizieren (Import + Tests)**

Run:
```bash
cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/ -q && python3 -c "import web.routers.fitness; print('ok')"
```
Expected: alle grün, `ok`

- [ ] **Step 4: Fallback gegen laufenden Server (kein A/B-Plan aktiv → Defaults)**

Run:
```bash
cd /Users/timoegersdorfer/Alfred && ./start.sh >/dev/null 2>&1; sleep 5
curl -s localhost:7779/api/fitness/today-plan | python3 -c "import sys,json;d=json.load(sys.stdin);print('source',d['plan_source'],'label',d['day_label'],'übungen',len(d['exercises']))"
```
Expected: heute Lower → `source` evtl. `alfred` oder `default`, `label` enthält `· A`/`· B` (oder bei jog kein Suffix), Übungsliste nicht-leer bei Kraft-Tag.

- [ ] **Step 5: Commit**

```bash
git add web/routers/fitness.py
git commit -m "feat(plan): today-plan picks A/B variant + variant label"
```

---

### Task 4: Neuen v2-Plan generieren + End-to-End-Verifikation

**Files:** keine (nur Ausführung/Verifikation)

- [ ] **Step 1: v2-Plan generieren (echter Haiku-Call)**

Run (Alfred läuft):
```bash
cd /Users/timoegersdorfer/Alfred
curl -s -m 90 -X POST localhost:7779/api/fitness/plan/generate | python3 -c "
import sys,json
d=json.load(sys.stdin)
p=d.get('plan',{})
print('ok', d.get('ok'))
for k in ('lowerA','lowerB','upperA','upperB'):
    print(f'{k}: {[e[\"name\"] for e in p.get(k,[])]}')
"
```
Expected: `ok True`; vier nicht-leere Listen; A und B unterscheiden sich; sichtbar auch
Übungen für Unterarme/Nacken/Bauch/Waden über die Varianten verteilt.

- [ ] **Step 2: today-plan nutzt den v2-Plan**

Run:
```bash
curl -s localhost:7779/api/fitness/today-plan | python3 -c "import sys,json;d=json.load(sys.stdin);print('source',d['plan_source'],'label',d['day_label']);print('übungen:',[e['name'] for e in d['exercises']])"
```
Expected: `source alfred`, `label` mit `· A` oder `· B`, Übungen aus dem generierten Plan.

- [ ] **Step 3: Varianten-Wechsel prüfen (A → B nach einem Lower-Workout)**

Run:
```bash
cd /Users/timoegersdorfer/Alfred
python3 -c "from domains import fitness; print('lower-count vorher:', fitness.slot_workout_count('lower'))"
curl -s -X POST localhost:7779/api/workouts -H 'Content-Type: application/json' -d '{"title":"Lower","type":"lower"}' >/dev/null
python3 -c "
from domains import fitness, plan_generator
c = fitness.slot_workout_count('lower')
print('lower-count nachher:', c, '→ Variante', plan_generator.pick_variant(c))
"
```
Expected: Count +1, Variante wechselt (gerade→A bzw. ungerade→B).

- [ ] **Step 4: Test-Daten entfernen + alle Tests**

Run:
```bash
cd /Users/timoegersdorfer/Alfred
python3 -c "from core import db; db.execute(\"DELETE FROM training_cycle_events WHERE date=CURRENT_DATE\"); db.execute(\"DELETE FROM workouts WHERE date=CURRENT_DATE AND title='Lower'\"); print('cleaned')"
python3 -m pytest tests/ -q
```
Expected: `cleaned`, alle Tests grün.

- [ ] **Step 5: Spec-Abgleich**

Spec `docs/superpowers/specs/2026-06-27-adaptive-plans-v2-design.md` durchgehen: Prompt v2,
A/B-Schema + Validierung, Varianten-Auswahl, today-plan-Konsum, Fallback, neu generiert.
Abweichungen notieren.
