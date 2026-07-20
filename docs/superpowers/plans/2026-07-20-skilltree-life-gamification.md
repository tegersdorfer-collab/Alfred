# Skilltree — Life-Gamification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein Skilltree, der Timos Fortschritt in 5 Lebens-Achsen ehrlich aus vorhandenen Mantis-Daten misst (Level + Decay + permanente Meilenstein-Nodes) und adaptive Quests vergibt — sichtbar als Mac-App-Overlay und per Voice.

**Architecture:** Reine Logik-Schicht (Scoring/Decay/Nodes/Quests, TDD, kein I/O) + dünner Signal-Collector über bestehende Stores + Service-Facade + Router/Voice/Widget/Overlay exakt nach der SP4-Health-Vorlage. **Stateless abgeleitet wie `health_scores`** — keine neue DB-Tabelle in der Kern-Phase; der Zustand ergibt sich aus der Signal-History.

**Tech Stack:** Python 3.14 (pytest, ruff), FastAPI-Router (`build_router(orch)`-Muster), TypeScript-Overlay auf dem `overlay.ts`-Framework (vitest, tsc).

## Global Constraints

- **Kanonische Shapes** (überall identisch verwenden):
  - `SignalEvent` = `{"axis": str, "kind": str, "value": float, "ts": str, "source": str, "count": int}` — `ts` ist ISO-Datum `YYYY-MM-DD`, `count` default 1.
  - `axis_cfg` = `{"key": str, "label": str, "components": {kind: {"weight": float, "retention": "fast"|"slow"|"permanent"}}}`
  - `node_def` = `{"key": str, "label": str, "axis": str, "signal_kind": str, "threshold": float}`
  - `quest` = `{"key": str, "axis": str, "label": str, "target_kind": str, "target_count": int, "since": str}`
  - `axis_state` = `{"axis": str, "label": str, "xp": float, "level": int, "trend": float}`
- **Reine Logik = kein I/O.** Alle Funktionen in `domains/skilltree/{scoring,nodes,quests,config}.py` arbeiten über injizierte `list[dict]`, nie DB/Netz (Vorbild: `domains/health_scores.py`).
- **Ehrlich bei fehlenden Daten** — nie Werte erfinden; leere Achse = Level 0 / trend 0, nicht geraten.
- **Backend-Tests:** `python3.14 -m pytest -q` + `python3.14 -m ruff check <pfade>`. **Frontend:** `cd apps/desktop && npx vitest run` + `npx tsc --noEmit`.
- **Deutsche Docstrings/Labels**, Modulstil wie `health_scores.py` (`from __future__ import annotations`).
- **Commit-Footer:** `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Nur committen, wenn der Nutzer den Flow bestätigt.

---

### Task 1: Retention-Decay + XP-Akkumulation (reine Logik)

**Files:**
- Create: `domains/skilltree/__init__.py` (leer)
- Create: `domains/skilltree/scoring.py`
- Test: `tests/test_skilltree_scoring.py`

**Interfaces:**
- Produces: `RETENTION_HALFLIFE: dict`, `retention_decay(retention: str, elapsed_days: float) -> float`, `axis_xp(signals: list[dict], axis_cfg: dict, now: date) -> float`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_skilltree_scoring.py
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.skilltree.scoring import axis_xp, retention_decay

# ── retention_decay: exponentieller Zerfall je Halbwertszeit ──────────────────

def test_permanent_never_decays():
    assert retention_decay("permanent", 3650) == 1.0

def test_fresh_signal_full_weight():
    assert retention_decay("fast", 0) == 1.0

def test_one_halflife_halves():
    # fast = 14 Tage Halbwertszeit → nach 14 Tagen Faktor 0.5
    assert retention_decay("fast", 14) == 0.5

def test_slow_decays_slower_than_fast():
    assert retention_decay("slow", 14) > retention_decay("fast", 14)

# ── axis_xp: gewichtete, zeit-gedämpfte Summe der Signale ──────────────────────

AXIS = {"key": "koerper", "label": "Körper", "components": {
    "training": {"weight": 10.0, "retention": "fast"},
    "pr": {"weight": 50.0, "retention": "permanent"},
}}

def test_axis_xp_sums_weighted_signals_fresh():
    now = date(2026, 7, 20)
    sigs = [
        {"axis": "koerper", "kind": "training", "value": 1.0, "ts": "2026-07-20", "source": "health", "count": 1},
        {"axis": "koerper", "kind": "pr", "value": 1.0, "ts": "2026-07-20", "source": "health", "count": 1},
    ]
    # training 1.0*10*1.0 + pr 1.0*50*1.0 = 60.0
    assert axis_xp(sigs, AXIS, now) == 60.0

def test_axis_xp_applies_decay_to_old_fast_signal():
    now = date(2026, 7, 20)
    sigs = [{"axis": "koerper", "kind": "training", "value": 1.0, "ts": "2026-07-06", "source": "health", "count": 1}]
    # 14 Tage alt, fast → 10 * 0.5 = 5.0
    assert axis_xp(sigs, AXIS, now) == 5.0

def test_axis_xp_ignores_unknown_kind():
    now = date(2026, 7, 20)
    sigs = [{"axis": "koerper", "kind": "unknown", "value": 1.0, "ts": "2026-07-20", "source": "x", "count": 1}]
    assert axis_xp(sigs, AXIS, now) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_skilltree_scoring.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'domains.skilltree'`

- [ ] **Step 3: Write minimal implementation**

```python
# domains/skilltree/scoring.py
"""Skilltree-Scoring — reine Funktionen, kein I/O.

Rechnet aus einer Signal-History (list[SignalEvent]) pro Achse XP + Level. Ältere
Signale zerfallen je nach Retention-Klasse ihrer Komponente (fast/slow/permanent),
sodass das Level den *aktuellen* Zustand spiegelt, nicht die Lebenssumme. Fehlt eine
Achse an Daten, ist sie ehrlich Level 0 — nie geraten.
"""
from __future__ import annotations

from datetime import date

# Halbwertszeit in Tagen je Retention-Klasse. permanent → kein Zerfall.
RETENTION_HALFLIFE: dict[str, float | None] = {
    "fast": 14.0,       # Kondition, Fokus-Streak, Momentum
    "slow": 90.0,       # Kraft-Basis, gefestigtes Wissen
    "permanent": None,  # tief verankert (verhält sich fast wie ein Node)
}


def retention_decay(retention: str, elapsed_days: float) -> float:
    """Multiplikativer Faktor 0..1 für ein Signal, das `elapsed_days` alt ist.

    permanent → 1.0. Sonst exponentiell: 0.5 ** (elapsed / halflife).
    """
    halflife = RETENTION_HALFLIFE.get(retention)
    if halflife is None:
        return 1.0
    if elapsed_days <= 0:
        return 1.0
    return round(0.5 ** (elapsed_days / halflife), 6)


def axis_xp(signals: list[dict], axis_cfg: dict, now: date) -> float:
    """Gewichtete, zeit-gedämpfte XP-Summe der Signale dieser Achse.

    Signale mit unbekanntem `kind` (nicht in der Achsen-Config) fallen raus.
    """
    comps = axis_cfg.get("components", {})
    total = 0.0
    for s in signals:
        comp = comps.get(s["kind"])
        if not comp:
            continue
        elapsed = (now - date.fromisoformat(s["ts"])).days
        factor = retention_decay(comp["retention"], elapsed)
        total += s["value"] * s.get("count", 1) * comp["weight"] * factor
    return round(total, 1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3.14 -m pytest tests/test_skilltree_scoring.py -q && python3.14 -m ruff check domains/skilltree/scoring.py`
Expected: PASS (7 passed), ruff clean

- [ ] **Step 5: Commit**

```bash
git add domains/skilltree/__init__.py domains/skilltree/scoring.py tests/test_skilltree_scoring.py
git commit -m "feat(skilltree): retention decay + weighted XP accumulation"
```

---

### Task 2: XP→Level + Achsen-Zustand mit Trend (reine Logik)

**Files:**
- Modify: `domains/skilltree/scoring.py`
- Test: `tests/test_skilltree_scoring.py` (ergänzen)

**Interfaces:**
- Consumes: `axis_xp(signals, axis_cfg, now)` (Task 1)
- Produces: `xp_to_level(xp: float, curve_k: float = 100.0) -> int`, `axis_level(signals: list[dict], axis_cfg: dict, now: date, curve_k: float = 100.0) -> dict` → `axis_state`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_skilltree_scoring.py — anhängen
from datetime import timedelta
from domains.skilltree.scoring import axis_level, xp_to_level

# ── xp_to_level: abflachende Kurve (höhere Level kosten mehr XP) ───────────────

def test_zero_xp_is_level_zero():
    assert xp_to_level(0.0) == 0

def test_level_grows_with_sqrt_of_xp():
    # curve_k=100 → Level = floor(sqrt(xp/100)); 400 XP → Level 2
    assert xp_to_level(400.0) == 2
    assert xp_to_level(900.0) == 3

def test_level_is_monotonic():
    assert xp_to_level(100.0) <= xp_to_level(101.0)

# ── axis_level: XP + Level + 7-Tage-Trend in einem axis_state ──────────────────

AXIS2 = {"key": "koerper", "label": "Körper", "components": {
    "training": {"weight": 100.0, "retention": "slow"},
}}

def test_axis_level_reports_state_shape():
    now = date(2026, 7, 20)
    sigs = [{"axis": "koerper", "kind": "training", "value": 4.0, "ts": "2026-07-20", "source": "h", "count": 1}]
    st = axis_level(sigs, AXIS2, now)
    assert st["axis"] == "koerper"
    assert st["label"] == "Körper"
    assert st["xp"] == 400.0
    assert st["level"] == 2
    assert "trend" in st

def test_axis_level_trend_positive_when_recent_activity():
    now = date(2026, 7, 20)
    # frisches Signal → XP jetzt > XP vor 7 Tagen → trend > 0
    sigs = [{"axis": "koerper", "kind": "training", "value": 4.0, "ts": "2026-07-18", "source": "h", "count": 1}]
    assert axis_level(sigs, AXIS2, now)["trend"] > 0

def test_empty_axis_is_level_zero_trend_zero():
    st = axis_level([], AXIS2, date(2026, 7, 20))
    assert st["level"] == 0 and st["xp"] == 0.0 and st["trend"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_skilltree_scoring.py -q`
Expected: FAIL — `ImportError: cannot import name 'axis_level'`

- [ ] **Step 3: Write minimal implementation**

```python
# domains/skilltree/scoring.py — anhängen
from datetime import timedelta


def xp_to_level(xp: float, curve_k: float = 100.0) -> int:
    """Monoton, abflachend: Level = floor(sqrt(xp / curve_k)). 0 XP → Level 0."""
    if xp <= 0:
        return 0
    return int((xp / curve_k) ** 0.5)


def axis_level(signals: list[dict], axis_cfg: dict, now: date, curve_k: float = 100.0) -> dict:
    """XP + Level + 7-Tage-Trend für eine Achse (→ axis_state).

    Trend = XP(jetzt) − XP(vor 7 Tagen), auf denselben Signalen mit verschobenem
    `now` gerechnet (ältere Signale zählen dann stärker gedämpft / gar nicht).
    """
    xp_now = axis_xp(signals, axis_cfg, now)
    xp_prev = axis_xp([s for s in signals if s["ts"] <= (now - timedelta(days=7)).isoformat()],
                      axis_cfg, now - timedelta(days=7))
    return {
        "axis": axis_cfg["key"],
        "label": axis_cfg["label"],
        "xp": xp_now,
        "level": xp_to_level(xp_now, curve_k),
        "trend": round(xp_now - xp_prev, 1),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3.14 -m pytest tests/test_skilltree_scoring.py -q && python3.14 -m ruff check domains/skilltree/scoring.py`
Expected: PASS (13 passed), ruff clean

- [ ] **Step 5: Commit**

```bash
git add domains/skilltree/scoring.py tests/test_skilltree_scoring.py
git commit -m "feat(skilltree): xp-to-level curve + axis state with trend"
```

---

### Task 3: Permanente Meilenstein-Nodes (reine Logik)

**Files:**
- Create: `domains/skilltree/nodes.py`
- Test: `tests/test_skilltree_nodes.py`

**Interfaces:**
- Produces: `unlocked_nodes(signals: list[dict], node_defs: list[dict]) -> list[dict]` → Liste `{"key","label","axis"}`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_skilltree_nodes.py
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.skilltree.nodes import unlocked_nodes

NODES = [
    {"key": "dl_100", "label": "100 kg Kreuzheben", "axis": "koerper", "signal_kind": "deadlift", "threshold": 100.0},
    {"key": "dl_140", "label": "140 kg Kreuzheben", "axis": "koerper", "signal_kind": "deadlift", "threshold": 140.0},
]

def test_node_unlocks_when_threshold_ever_reached():
    sigs = [{"axis": "koerper", "kind": "deadlift", "value": 110.0, "ts": "2026-05-01", "source": "fitness", "count": 1}]
    keys = [n["key"] for n in unlocked_nodes(sigs, NODES)]
    assert keys == ["dl_100"]  # 110 ≥ 100, aber < 140

def test_node_stays_unlocked_even_if_later_value_lower():
    # permanent: einmal erreicht bleibt freigeschaltet, auch wenn die Form später sinkt
    sigs = [
        {"axis": "koerper", "kind": "deadlift", "value": 145.0, "ts": "2026-03-01", "source": "f", "count": 1},
        {"axis": "koerper", "kind": "deadlift", "value": 90.0, "ts": "2026-07-01", "source": "f", "count": 1},
    ]
    assert {n["key"] for n in unlocked_nodes(sigs, NODES)} == {"dl_100", "dl_140"}

def test_no_signal_no_unlock():
    assert unlocked_nodes([], NODES) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_skilltree_nodes.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'domains.skilltree.nodes'`

- [ ] **Step 3: Write minimal implementation**

```python
# domains/skilltree/nodes.py
"""Meilenstein-Nodes — permanent, reine Logik.

Ein Node schaltet frei, sobald seine Bedingung *je* erfüllt war (max value eines
signal_kind ≥ threshold). Anders als das Achsen-Level zerfällt ein Node nie — das
"hab ich mal geschafft" bleibt stehen. Ableitung aus der Signal-History, kein State.
"""
from __future__ import annotations


def unlocked_nodes(signals: list[dict], node_defs: list[dict]) -> list[dict]:
    """Alle Nodes, deren Schwelle in der History je erreicht wurde."""
    out: list[dict] = []
    for nd in node_defs:
        vals = [s["value"] for s in signals if s["kind"] == nd["signal_kind"]]
        if vals and max(vals) >= nd["threshold"]:
            out.append({"key": nd["key"], "label": nd["label"], "axis": nd["axis"]})
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3.14 -m pytest tests/test_skilltree_nodes.py -q && python3.14 -m ruff check domains/skilltree/nodes.py`
Expected: PASS (3 passed), ruff clean

- [ ] **Step 5: Commit**

```bash
git add domains/skilltree/nodes.py tests/test_skilltree_nodes.py
git commit -m "feat(skilltree): permanent milestone nodes"
```

---

### Task 4: Achsen-Config (Daten + Struktur-Test)

**Files:**
- Create: `domains/skilltree/config.py`
- Test: `tests/test_skilltree_config.py`

**Interfaces:**
- Produces: `AXES: list[dict]` (5 `axis_cfg`), `NODE_DEFS: list[dict]`, `QUEST_POOL: list[dict]`, `axis_by_key(key: str) -> dict | None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_skilltree_config.py
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.skilltree.config import AXES, NODE_DEFS, QUEST_POOL, axis_by_key

def test_five_start_axes_present():
    keys = {a["key"] for a in AXES}
    assert keys == {"koerper", "wissen", "schaffen", "geist", "disziplin"}

def test_every_axis_has_components_with_valid_retention():
    valid = {"fast", "slow", "permanent"}
    for a in AXES:
        assert a["components"], f"{a['key']} ohne Komponenten"
        for kind, comp in a["components"].items():
            assert comp["retention"] in valid
            assert comp["weight"] > 0

def test_axis_by_key_roundtrip():
    assert axis_by_key("koerper")["label"] == "Körper"
    assert axis_by_key("nope") is None

def test_node_defs_reference_existing_axes():
    axis_keys = {a["key"] for a in AXES}
    for nd in NODE_DEFS:
        assert nd["axis"] in axis_keys

def test_quests_reference_existing_axes():
    axis_keys = {a["key"] for a in AXES}
    for q in QUEST_POOL:
        assert q["axis"] in axis_keys
        assert q["target_count"] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_skilltree_config.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# domains/skilltree/config.py
"""Skilltree-Konfiguration — Daten, kein Code.

Fünf Start-Achsen (erweiterbar: neue Achse = ein Eintrag hier, kein Umbau). Jede
Achse mappt Signal-`kind`s auf Gewicht + Retention-Klasse. NODE_DEFS = permanente
Meilensteine, QUEST_POOL = Vorlagen für die Quest-Engine.
"""
from __future__ import annotations

AXES: list[dict] = [
    {"key": "koerper", "label": "Körper", "components": {
        "training": {"weight": 12.0, "retention": "fast"},
        "kondition": {"weight": 8.0, "retention": "fast"},
        "kraft": {"weight": 15.0, "retention": "slow"},
    }},
    {"key": "wissen", "label": "Wissen", "components": {
        "zettel": {"weight": 8.0, "retention": "slow"},
        "lernpfad": {"weight": 12.0, "retention": "slow"},
        "studium": {"weight": 15.0, "retention": "permanent"},
    }},
    {"key": "schaffen", "label": "Schaffen", "components": {
        "commit": {"weight": 6.0, "retention": "fast"},
        "projekt": {"weight": 20.0, "retention": "permanent"},
    }},
    {"key": "geist", "label": "Geist", "components": {
        "reflexion": {"weight": 8.0, "retention": "fast"},
        "insight": {"weight": 10.0, "retention": "slow"},
    }},
    {"key": "disziplin", "label": "Disziplin", "components": {
        "streak": {"weight": 10.0, "retention": "fast"},
        "habit": {"weight": 8.0, "retention": "fast"},
    }},
]

NODE_DEFS: list[dict] = [
    {"key": "dl_100", "label": "100 kg Kreuzheben", "axis": "koerper", "signal_kind": "kraft", "threshold": 100.0},
    {"key": "notes_100", "label": "100 Zettel angelegt", "axis": "wissen", "signal_kind": "zettel_total", "threshold": 100.0},
    {"key": "ship_first", "label": "Erstes Projekt released", "axis": "schaffen", "signal_kind": "projekt", "threshold": 1.0},
]

QUEST_POOL: list[dict] = [
    {"key": "train_3x", "axis": "koerper", "label": "3× trainieren diese Woche", "target_kind": "training", "target_count": 3},
    {"key": "zettel_5", "axis": "wissen", "label": "5 neue Zettel schreiben", "target_kind": "zettel", "target_count": 5},
    {"key": "commit_5", "axis": "schaffen", "label": "An 5 Tagen committen", "target_kind": "commit", "target_count": 5},
    {"key": "reflect_3", "axis": "geist", "label": "3× reflektieren/journaln", "target_kind": "reflexion", "target_count": 3},
    {"key": "streak_5", "axis": "disziplin", "label": "5-Tage-Habit-Streak halten", "target_kind": "streak", "target_count": 5},
]


def axis_by_key(key: str) -> dict | None:
    return next((a for a in AXES if a["key"] == key), None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3.14 -m pytest tests/test_skilltree_config.py -q && python3.14 -m ruff check domains/skilltree/config.py`
Expected: PASS (5 passed), ruff clean

- [ ] **Step 5: Commit**

```bash
git add domains/skilltree/config.py tests/test_skilltree_config.py
git commit -m "feat(skilltree): 5 start axes + node/quest config data"
```

---

### Task 5: Quest-Engine — adaptive Auswahl + Auto-Completion (reine Logik)

**Files:**
- Create: `domains/skilltree/quests.py`
- Test: `tests/test_skilltree_quests.py`

**Interfaces:**
- Consumes: `axis_state` (Task 2), `QUEST_POOL` (Task 4)
- Produces: `classify_axes(axis_states: list[dict], rust_threshold: float = -5.0, momentum_threshold: float = 5.0) -> dict`, `pick_quests(axis_states: list[dict], quest_pool: list[dict], n: int = 3) -> list[dict]`, `quest_progress(quest: dict, signals: list[dict], now: date) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_skilltree_quests.py
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.skilltree.quests import classify_axes, pick_quests, quest_progress

def _state(axis, level=1, trend=0.0):
    return {"axis": axis, "label": axis.title(), "xp": 100.0, "level": level, "trend": trend}

POOL = [
    {"key": "train_3x", "axis": "koerper", "label": "3× trainieren", "target_kind": "training", "target_count": 3},
    {"key": "zettel_5", "axis": "wissen", "label": "5 Zettel", "target_kind": "zettel", "target_count": 5},
]

# ── classify_axes: rostend (negativer Trend) vs. Momentum (positiver Trend) ─────

def test_classify_splits_rusting_and_momentum():
    states = [_state("koerper", trend=-8.0), _state("wissen", trend=9.0), _state("geist", trend=0.0)]
    c = classify_axes(states)
    assert c["rusting"] == ["koerper"]
    assert c["momentum"] == ["wissen"]

# ── pick_quests: Rost hat Priorität, dann Momentum ─────────────────────────────

def test_pick_prioritizes_rusting_axis():
    states = [_state("koerper", trend=-8.0), _state("wissen", trend=9.0)]
    picked = pick_quests(states, POOL, n=1)
    assert picked[0]["axis"] == "koerper"  # Rost vor Momentum

def test_pick_uses_momentum_when_no_rust():
    states = [_state("koerper", trend=2.0), _state("wissen", trend=9.0)]
    picked = pick_quests(states, POOL, n=1)
    assert picked[0]["axis"] == "wissen"

def test_pick_respects_count_limit():
    states = [_state("koerper", trend=-8.0), _state("wissen", trend=-9.0)]
    assert len(pick_quests(states, POOL, n=1)) == 1

# ── quest_progress: Auto-Completion aus harten Signalen ────────────────────────

def test_quest_progress_counts_matching_signals_since_start():
    q = {"key": "train_3x", "axis": "koerper", "label": "3×", "target_kind": "training",
         "target_count": 3, "since": "2026-07-14"}
    sigs = [
        {"axis": "koerper", "kind": "training", "value": 1.0, "ts": "2026-07-15", "source": "h", "count": 1},
        {"axis": "koerper", "kind": "training", "value": 1.0, "ts": "2026-07-17", "source": "h", "count": 1},
        {"axis": "koerper", "kind": "training", "value": 1.0, "ts": "2026-07-10", "source": "h", "count": 1},  # vor since → zählt nicht
    ]
    p = quest_progress(q, sigs, date(2026, 7, 20))
    assert p["count"] == 2
    assert p["pct"] == round(2 / 3, 2)
    assert p["done"] is False

def test_quest_progress_done_when_target_reached():
    q = {"key": "train_3x", "axis": "koerper", "label": "3×", "target_kind": "training",
         "target_count": 2, "since": "2026-07-14"}
    sigs = [
        {"axis": "koerper", "kind": "training", "value": 1.0, "ts": "2026-07-15", "source": "h", "count": 1},
        {"axis": "koerper", "kind": "training", "value": 1.0, "ts": "2026-07-17", "source": "h", "count": 1},
    ]
    assert quest_progress(q, sigs, date(2026, 7, 20))["done"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_skilltree_quests.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'domains.skilltree.quests'`

- [ ] **Step 3: Write minimal implementation**

```python
# domains/skilltree/quests.py
"""Quest-Engine — adaptive Auswahl + Auto-Completion, reine Logik.

Adaptiv: rostende Achsen (negativer Trend) werden zuerst gepusht (rundes Wachstum),
dann wird Momentum (positiver Trend) verstärkt. Completion wird aus harten Signalen
abgeleitet — keine manuelle Abhaken nötig, wo Daten fließen.
"""
from __future__ import annotations

from datetime import date


def classify_axes(axis_states: list[dict], rust_threshold: float = -5.0,
                  momentum_threshold: float = 5.0) -> dict:
    """Achsen nach Trend einteilen. rustend = trend ≤ rust_threshold,
    Momentum = trend ≥ momentum_threshold. Rest bleibt neutral."""
    rusting = [s["axis"] for s in axis_states if s["trend"] <= rust_threshold]
    momentum = [s["axis"] for s in axis_states if s["trend"] >= momentum_threshold]
    return {"rusting": rusting, "momentum": momentum}


def pick_quests(axis_states: list[dict], quest_pool: list[dict], n: int = 3) -> list[dict]:
    """Bis zu n Quests: erst für rostende Achsen (Priorität), dann Momentum, dann Rest.

    Reihenfolge der Achsen innerhalb einer Gruppe = schwächster Trend zuerst
    (rostend) bzw. stärkster zuerst (Momentum).
    """
    c = classify_axes(axis_states)
    trend = {s["axis"]: s["trend"] for s in axis_states}
    rusting = sorted(c["rusting"], key=lambda a: trend[a])            # negativster zuerst
    momentum = sorted(c["momentum"], key=lambda a: -trend[a])         # stärkster zuerst
    rest = [s["axis"] for s in axis_states if s["axis"] not in rusting and s["axis"] not in momentum]
    order = rusting + momentum + rest
    picked: list[dict] = []
    for axis in order:
        q = next((q for q in quest_pool if q["axis"] == axis), None)
        if q:
            picked.append(q)
        if len(picked) >= n:
            break
    return picked


def quest_progress(quest: dict, signals: list[dict], now: date) -> dict:
    """Fortschritt aus harten Signalen seit quest['since'] (inklusive)."""
    matched = [s for s in signals
               if s["kind"] == quest["target_kind"] and s["ts"] >= quest["since"]]
    count = sum(s.get("count", 1) for s in matched)
    pct = min(1.0, count / quest["target_count"]) if quest["target_count"] else 0.0
    return {"count": count, "pct": round(pct, 2), "done": count >= quest["target_count"]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3.14 -m pytest tests/test_skilltree_quests.py -q && python3.14 -m ruff check domains/skilltree/quests.py`
Expected: PASS (7 passed), ruff clean

- [ ] **Step 5: Commit**

```bash
git add domains/skilltree/quests.py tests/test_skilltree_quests.py
git commit -m "feat(skilltree): adaptive quest engine + auto-completion"
```

---

### Task 6: Signal-Collector über bestehende Stores (I/O)

**Files:**
- Create: `domains/skilltree/signals.py`
- Test: `tests/test_skilltree_signals.py`

**Interfaces:**
- Consumes: nichts aus früheren Tasks (produziert die `SignalEvent`-Liste, die alle Reinen konsumieren)
- Produces: `collect_from_health(health_rows: list) -> list[dict]`, `collect_signals(dashboard, now: date) -> list[dict]`

**Note:** M1 schließt die **Health**-Quelle an (via `dashboard.get_recent_health()`, verifiziert vorhanden — liefert Objekte mit `.date/.exercise_minutes/.steps`). Weitere Quellen (Second Brain → `zettel`, Habits → `streak`, Git → `commit`) sind **additive Folge-Collectors** nach identischem Muster; `collect_signals` ist der eine Erweiterungspunkt. Testbar über ein Fake-Dashboard (Dependency Injection), keine echte DB im Test.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_skilltree_signals.py
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.skilltree.signals import collect_from_health, collect_signals


class _H:
    def __init__(self, d, exercise_minutes=None, steps=None):
        self.date = d
        self.exercise_minutes = exercise_minutes
        self.steps = steps


class _FakeDash:
    def __init__(self, rows):
        self._rows = rows
    def get_recent_health(self, days=90):
        return self._rows


def test_health_exercise_becomes_training_signal():
    rows = [_H("2026-07-18", exercise_minutes=45, steps=9000)]
    sigs = collect_from_health(rows)
    kinds = {s["kind"] for s in sigs}
    assert "training" in kinds
    train = next(s for s in sigs if s["kind"] == "training")
    assert train["axis"] == "koerper"
    assert train["ts"] == "2026-07-18"
    assert train["source"] == "health"
    assert train["value"] > 0

def test_health_zero_exercise_no_training_signal():
    rows = [_H("2026-07-18", exercise_minutes=0, steps=0)]
    assert all(s["kind"] != "training" for s in collect_from_health(rows))

def test_collect_signals_pulls_from_dashboard():
    dash = _FakeDash([_H("2026-07-18", exercise_minutes=30, steps=8000)])
    sigs = collect_signals(dash, date(2026, 7, 20))
    assert any(s["kind"] == "training" for s in sigs)
    assert all({"axis", "kind", "value", "ts", "source"} <= set(s) for s in sigs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_skilltree_signals.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# domains/skilltree/signals.py
"""Signal-Collector — der einzige I/O-Punkt des Skilltree.

Zieht harte Signale aus bestehenden Mantis-Stores und normalisiert sie auf
SignalEvent. Kennt die Stores, aber keine Scoring-Logik. Erweiterung = eine neue
collect_from_*-Funktion + ein Aufruf in collect_signals (der Erweiterungspunkt).
"""
from __future__ import annotations

from datetime import date


def collect_from_health(health_rows: list) -> list[dict]:
    """Health-Rows → Körper-Signale.

    - Trainingsminuten > 0 → ein `training`-Signal (value = Minuten/30, gedeckelt bei 2).
    """
    out: list[dict] = []
    for h in health_rows:
        mins = getattr(h, "exercise_minutes", None) or 0
        if mins > 0:
            out.append({
                "axis": "koerper", "kind": "training",
                "value": round(min(mins / 30.0, 2.0), 2),
                "ts": str(h.date), "source": "health", "count": 1,
            })
    return out


def collect_signals(dashboard, now: date) -> list[dict]:
    """Alle harten Signale der letzten 90 Tage aus den vorhandenen Stores.

    M1: Health. Weitere Quellen (Second Brain, Habits, Git) docken hier an —
    je eine collect_from_*-Funktion, hier aufgerufen und in die Liste gemischt.
    """
    signals: list[dict] = []
    if dashboard is not None:
        signals += collect_from_health(dashboard.get_recent_health(days=90))
    return signals
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3.14 -m pytest tests/test_skilltree_signals.py -q && python3.14 -m ruff check domains/skilltree/signals.py`
Expected: PASS (3 passed), ruff clean

- [ ] **Step 5: Commit**

```bash
git add domains/skilltree/signals.py tests/test_skilltree_signals.py
git commit -m "feat(skilltree): signal collector (health source, extensible)"
```

---

### Task 7: Service-Facade — kompletter Skilltree-State

**Files:**
- Create: `domains/skilltree/service.py`
- Test: `tests/test_skilltree_service.py`

**Interfaces:**
- Consumes: `collect_signals` (T6), `axis_level` (T2), `unlocked_nodes` (T3), `pick_quests`+`quest_progress` (T5), `AXES`+`NODE_DEFS`+`QUEST_POOL` (T4)
- Produces: `build_skilltree_state(dashboard, now: date, quest_since: str) -> dict` → `{"axes": [axis_state], "nodes": [...], "quests": [{...quest, "progress": {...}}]}`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_skilltree_service.py
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.skilltree.service import build_skilltree_state


class _H:
    def __init__(self, d, exercise_minutes=None):
        self.date = d
        self.exercise_minutes = exercise_minutes
        self.steps = None


class _FakeDash:
    def __init__(self, rows):
        self._rows = rows
    def get_recent_health(self, days=90):
        return self._rows


def test_state_has_all_axes_even_when_empty():
    state = build_skilltree_state(_FakeDash([]), date(2026, 7, 20), quest_since="2026-07-14")
    axes = {a["axis"] for a in state["axes"]}
    assert axes == {"koerper", "wissen", "schaffen", "geist", "disziplin"}
    assert all(a["level"] == 0 for a in state["axes"])  # keine Daten → ehrlich Level 0

def test_state_reflects_training_in_body_axis():
    rows = [_H(f"2026-07-{d:02d}", exercise_minutes=60) for d in range(10, 20)]
    state = build_skilltree_state(_FakeDash(rows), date(2026, 7, 20), quest_since="2026-07-14")
    body = next(a for a in state["axes"] if a["axis"] == "koerper")
    assert body["xp"] > 0 and body["level"] >= 0

def test_state_includes_quests_with_progress():
    rows = [_H(f"2026-07-{d:02d}", exercise_minutes=60) for d in range(15, 19)]
    state = build_skilltree_state(_FakeDash(rows), date(2026, 7, 20), quest_since="2026-07-14")
    assert isinstance(state["quests"], list)
    for q in state["quests"]:
        assert "progress" in q and "pct" in q["progress"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_skilltree_service.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# domains/skilltree/service.py
"""Skilltree-Service-Facade — verbindet Collector + reine Logik zum Gesamt-State.

Der eine Einstieg für Router/Voice/Widget. Stateless: alles aus der Signal-History
abgeleitet (wie health_scores). `quest_since` grenzt das Quest-Fenster ab (z.B.
Wochenstart) — kommt vom Aufrufer, damit die Facade zeitfrei/testbar bleibt.
"""
from __future__ import annotations

from datetime import date

from domains.skilltree.config import AXES, NODE_DEFS, QUEST_POOL
from domains.skilltree.nodes import unlocked_nodes
from domains.skilltree.quests import pick_quests, quest_progress
from domains.skilltree.scoring import axis_level
from domains.skilltree.signals import collect_signals


def build_skilltree_state(dashboard, now: date, quest_since: str) -> dict:
    signals = collect_signals(dashboard, now)
    axes = [axis_level(signals, cfg, now) for cfg in AXES]
    nodes = unlocked_nodes(signals, NODE_DEFS)
    quests = []
    for q in pick_quests(axes, QUEST_POOL):
        active = {**q, "since": quest_since}
        quests.append({**active, "progress": quest_progress(active, signals, now)})
    return {"axes": axes, "nodes": nodes, "quests": quests}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3.14 -m pytest tests/test_skilltree_service.py -q && python3.14 -m ruff check domains/skilltree/service.py`
Expected: PASS (3 passed), ruff clean

- [ ] **Step 5: Commit**

```bash
git add domains/skilltree/service.py tests/test_skilltree_service.py
git commit -m "feat(skilltree): service facade assembling full state"
```

---

### Task 8: API-Router `GET /api/skilltree`

**Files:**
- Create: `web/routers/skilltree.py`
- Modify: `web/api.py` (Router registrieren — Muster prüfen: wie `health`-Router eingehängt wird)
- Test: `tests/test_skilltree_router.py`

**Interfaces:**
- Consumes: `build_skilltree_state` (T7)
- Produces: HTTP `GET /api/skilltree` → `{"axes","nodes","quests"}` (leerer/`orch=None`-Fall → leere Achsen). `build_router(orch) -> APIRouter` (Muster wie `web/routers/health.py`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_skilltree_router.py
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from fastapi import FastAPI
from web.routers.skilltree import build_router


class _H:
    def __init__(self, d, exercise_minutes=None):
        self.date = d
        self.exercise_minutes = exercise_minutes
        self.steps = None


class _Dash:
    def get_recent_health(self, days=90):
        return [_H(f"2026-07-{d:02d}", exercise_minutes=60) for d in range(10, 20)]


class _Orch:
    _dashboard = _Dash()


def _client(orch):
    app = FastAPI()
    app.include_router(build_router(orch))
    return TestClient(app)


def test_endpoint_returns_all_axes():
    r = _client(_Orch()).get("/api/skilltree")
    assert r.status_code == 200
    body = r.json()
    assert {a["axis"] for a in body["axes"]} == {"koerper", "wissen", "schaffen", "geist", "disziplin"}
    assert "quests" in body and "nodes" in body

def test_endpoint_without_orch_is_empty_axes():
    body = _client(None).get("/api/skilltree").json()
    assert all(a["level"] == 0 for a in body["axes"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_skilltree_router.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'web.routers.skilltree'`

- [ ] **Step 3: Write minimal implementation**

```python
# web/routers/skilltree.py
"""Skilltree — API-Router (Muster wie web/routers/health.py).

Reiner Adapter über domains.skilltree.service. quest_since = Montag der laufenden
Woche (Wochen-Quests). orch=None → leere Achsen (kein Crash, ehrlich leer).
"""
import logging
from datetime import date, timedelta

from fastapi import APIRouter

from domains.skilltree.config import AXES
from domains.skilltree.service import build_skilltree_state

log = logging.getLogger("mantis.api")


def _empty_state() -> dict:
    return {"axes": [{"axis": a["key"], "label": a["label"], "xp": 0.0, "level": 0, "trend": 0.0}
                     for a in AXES], "nodes": [], "quests": []}


def _week_start(today: date) -> str:
    return (today - timedelta(days=today.weekday())).isoformat()


def build_router(orch=None) -> APIRouter:
    router = APIRouter()

    @router.get("/api/skilltree")
    def skilltree():
        """Achsen-Level + freigeschaltete Nodes + adaptive Wochen-Quests."""
        if not orch or not getattr(orch, "_dashboard", None):
            return _empty_state()
        today = date.today()
        return build_skilltree_state(orch._dashboard, today, quest_since=_week_start(today))

    return router
```

- [ ] **Step 4: Register the router**

Öffne `web/api.py`, finde, wo die anderen Router eingehängt werden (suche `from web.routers.health import` bzw. `include_router(health`). Ergänze analog:

```python
from web.routers.skilltree import build_router as build_skilltree_router
# ... bei den anderen include_router-Aufrufen:
app.include_router(build_skilltree_router(orch))
```

- [ ] **Step 5: Run tests + smoke, then commit**

Run: `python3.14 -m pytest tests/test_skilltree_router.py -q && python3.14 -m ruff check web/routers/skilltree.py`
Expected: PASS (2 passed), ruff clean
Live (Mantis läuft): `curl -s localhost:7779/api/skilltree | head -c 300` → JSON mit `axes`.

```bash
git add web/routers/skilltree.py web/api.py tests/test_skilltree_router.py
git commit -m "feat(skilltree): GET /api/skilltree endpoint"
```

---

### Task 9: Voice-Intent + Fast-Path + Widget-Payload

**Files:**
- Create: `core/skills/skilltree.py`
- Modify: `core/skills/__init__.py` (Import, damit `@T.register` greift — prüfen, wie `health` importiert wird)
- Modify: `core/ui_state.py` (`WIDGET_MAP` + `_DASHBOARD_BUILDERS` + neuer Builder)
- Modify: `core/fast_commands.py` (Fast-Path für „skilltree/level/fortschritt")
- Test: `tests/test_skilltree_widget.py`

**Interfaces:**
- Consumes: `build_skilltree_state` (T7)
- Produces: Tool `get_skilltree` (Voice), `skilltree_widget_payload(dashboard) -> dict` (Typ `"skilltree"`), Fast-Command `get_skilltree`

- [ ] **Step 1: Write the failing test (widget payload)**

```python
# tests/test_skilltree_widget.py
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ui_state import skilltree_widget_payload


class _H:
    def __init__(self, d, exercise_minutes=None):
        self.date = d
        self.exercise_minutes = exercise_minutes
        self.steps = None


class _Dash:
    def get_recent_health(self, days=90):
        return [_H(f"2026-07-{d:02d}", exercise_minutes=60) for d in range(10, 20)]


def test_widget_payload_shape():
    p = skilltree_widget_payload(_Dash())
    assert p["widget"] == "skilltree"
    assert {a["axis"] for a in p["axes"]} == {"koerper", "wissen", "schaffen", "geist", "disziplin"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_skilltree_widget.py -q`
Expected: FAIL — `ImportError: cannot import name 'skilltree_widget_payload'`

- [ ] **Step 3: Add the widget payload builder**

In `core/ui_state.py` — Builder ergänzen (neben `health_widget_payload`):

```python
def skilltree_widget_payload(dashboard: Any, days: int = 90) -> dict:
    """HUD-Glance: Achsen-Level + Top-Quest. Aus dem Skilltree-Service abgeleitet."""
    from datetime import date, timedelta
    from domains.skilltree.service import build_skilltree_state
    today = date.today()
    since = (today - timedelta(days=today.weekday())).isoformat()
    state = build_skilltree_state(dashboard, today, quest_since=since)
    return {"widget": "skilltree", "axes": state["axes"],
            "nodes": state["nodes"], "quests": state["quests"]}
```

In `WIDGET_MAP` ergänzen: `"get_skilltree": "skilltree",`
In `_DASHBOARD_BUILDERS` ergänzen: `"skilltree": skilltree_widget_payload,`

- [ ] **Step 4: Add Voice tool + fast-path**

`core/skills/skilltree.py`:

```python
"""Skilltree-Tools — Voice-Zugriff auf Level & nächste Quest."""
import logging
from datetime import date, timedelta

from core import tools as T
from core.skill_context import CTX

log = logging.getLogger("core.skills")


@T.register("get_skilltree",
    "Timos Skilltree-Status: Level je Lebens-Achse + nächste Quest. Für 'wie ist "
    "mein level / was soll ich als nächstes tun / skilltree'.", {}, [], "skilltree")
async def _get_skilltree():
    if not CTX.dashboard:
        return "Skilltree nicht verfügbar."
    from domains.skilltree.service import build_skilltree_state
    today = date.today()
    since = (today - timedelta(days=today.weekday())).isoformat()
    st = build_skilltree_state(CTX.dashboard, today, quest_since=since)
    levels = ", ".join(f"{a['label']} Lv{a['level']}" for a in st["axes"])
    quest = st["quests"][0]["label"] if st["quests"] else "keine offene Quest"
    return f"{levels}. Nächste Quest: {quest}."
```

In `core/skills/__init__.py`: den neuen Modul-Import analog zu den anderen (`from core.skills import skilltree` bzw. wie `health` gelistet ist) ergänzen.

In `core/fast_commands.py`: dem Muster von `get_health_scores` folgen — ein Wort-Set (`{"skilltree", "level", "fortschritt", "quest"}`) und in `match()` `return FastCommand("get_skilltree", {}, "skilltree")`.

- [ ] **Step 5: Run tests + commit**

Run: `python3.14 -m pytest tests/test_skilltree_widget.py -q && python3.14 -m ruff check core/ui_state.py core/skills/skilltree.py core/fast_commands.py`
Expected: PASS, ruff clean

```bash
git add core/ui_state.py core/skills/skilltree.py core/skills/__init__.py core/fast_commands.py tests/test_skilltree_widget.py
git commit -m "feat(skilltree): voice intent, fast-path, widget payload"
```

---

### Task 10: Skilltree-Overlay (Frontend, vitest) + Integration

**Files:**
- Create: `apps/desktop/src/skilltree-overlay.ts`
- Create: `apps/desktop/src/skilltree-overlay.test.ts`
- Modify: `apps/desktop/src/main.ts` (Import, `initSkilltreeOverlay` vor `initNavOverlay`, `case 'skilltree'` im Widget-Switch)

**Interfaces:**
- Consumes: `GET /api/skilltree` (T8), Widget-Payload `skilltree` (T9), `createOverlay`/`registerOverlay` (`overlay.ts`)
- Produces: `overviewHtml(data)`, `axisDetailHtml(axis, quests)`, `widgetHtml(p)`, `initSkilltreeOverlay(baseUrl, fetchImpl?)`

- [ ] **Step 1: Write the failing test**

```typescript
// apps/desktop/src/skilltree-overlay.test.ts
import { describe, it, expect } from 'vitest';
import { overviewHtml, widgetHtml } from './skilltree-overlay';

const DATA = {
  axes: [
    { axis: 'koerper', label: 'Körper', xp: 400, level: 2, trend: 12 },
    { axis: 'wissen', label: 'Wissen', xp: 100, level: 1, trend: -8 },
  ],
  nodes: [{ key: 'dl_100', label: '100 kg Kreuzheben', axis: 'koerper' }],
  quests: [{ key: 'zettel_5', axis: 'wissen', label: '5 neue Zettel schreiben',
             progress: { count: 2, pct: 0.4, done: false } }],
};

describe('overviewHtml', () => {
  it('zeigt Achsen mit Level', () => {
    const html = overviewHtml(DATA);
    expect(html).toContain('Körper');
    expect(html).toContain('Lv2');
    expect(html).toContain('Wissen');
  });
  it('markiert eine rostende Achse (negativer Trend)', () => {
    expect(overviewHtml(DATA)).toContain('↓'); // Wissen trend -8
  });
  it('listet die nächste Quest mit Fortschritt', () => {
    const html = overviewHtml(DATA);
    expect(html).toContain('5 neue Zettel');
    expect(html).toContain('40'); // pct 0.4 → 40%
  });
  it('zeigt freigeschaltete Nodes', () => {
    expect(overviewHtml(DATA)).toContain('100 kg Kreuzheben');
  });
});

describe('widgetHtml', () => {
  it('kompakte Achsen-Glance', () => {
    const html = widgetHtml(DATA);
    expect(html).toContain('Skilltree');
    expect(html).toContain('Körper');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/skilltree-overlay.test.ts`
Expected: FAIL — cannot find module './skilltree-overlay'

- [ ] **Step 3: Write minimal implementation**

```typescript
// apps/desktop/src/skilltree-overlay.ts
// Skilltree-Overlay — Achsen-Level + Nodes + adaptive Quests. Holt /api/skilltree
// selbst. Reine Render-Funktionen (overviewHtml/axisDetailHtml/widgetHtml) sind
// vom Fetch getrennt und per vitest getestet. Ehrlich: Level 0 statt Fake.

import { createOverlay, registerOverlay } from './overlay';

type Axis = { axis: string; label: string; xp: number; level: number; trend: number };
type Node = { key: string; label: string; axis: string };
type Quest = { key: string; axis: string; label: string;
               progress: { count: number; pct: number; done: boolean } };
type SkilltreeData = { axes: Axis[]; nodes: Node[]; quests: Quest[] };

const AXIS_COLOR: Record<string, string> = {
  koerper: '#3ee0c8', wissen: '#8b9cff', schaffen: '#f5c451',
  geist: '#c78bff', disziplin: '#7fe081',
};

function esc(s: string): string {
  return s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c] as string);
}

function trendArrow(trend: number): string {
  return trend <= -5 ? '↓' : trend >= 5 ? '↑' : '→';
}

function axisRow(a: Axis): string {
  const color = AXIS_COLOR[a.axis] ?? '#8fb';
  return `<div class="st-axis" data-axis="${a.axis}">
    <span class="st-alabel" style="color:${color}">${esc(a.label)}</span>
    <span class="st-alevel">Lv${a.level}</span>
    <span class="st-atrend">${trendArrow(a.trend)}</span></div>`;
}

function questRow(q: Quest): string {
  const pct = Math.round(q.progress.pct * 100);
  return `<div class="st-quest"><span class="st-qlabel">${esc(q.label)}</span>
    <span class="st-qtrack"><span class="st-qfill" style="width:${pct}%"></span></span>
    <span class="st-qpct">${pct}%</span></div>`;
}

export function overviewHtml(data: SkilltreeData): string {
  const axes = (data?.axes ?? []).map(axisRow).join('');
  const quests = (data?.quests ?? []).map(questRow).join('') || '<div class="st-empty">Keine offene Quest.</div>';
  const nodes = (data?.nodes ?? [])
    .map((n) => `<span class="st-node">✦ ${esc(n.label)}</span>`).join('') || '';
  return `<div class="st-head"><h2>Skilltree</h2><button class="ho-close" data-action="close">✕</button></div>
    <div class="st-axes">${axes}</div>
    <div class="st-section">Quests</div><div class="st-quests">${quests}</div>
    ${nodes ? `<div class="st-section">Freigeschaltet</div><div class="st-nodes">${nodes}</div>` : ''}`;
}

export function axisDetailHtml(axis: Axis, quests: Quest[]): string {
  const mine = quests.filter((q) => q.axis === axis.axis).map(questRow).join('')
    || '<div class="st-empty">Keine Quest für diese Achse.</div>';
  return `<div class="st-drill"><button class="ho-back" data-action="overview">‹ Übersicht</button>
    <h2>${esc(axis.label)} — Lv${axis.level}</h2>
    <div class="st-why">XP ${Math.round(axis.xp)} · Trend ${trendArrow(axis.trend)}</div>
    <div class="st-quests">${mine}</div></div>`;
}

export function widgetHtml(p: SkilltreeData): string {
  const axes = (p?.axes ?? [])
    .map((a) => `<span class="st-chip" style="border-color:${AXIS_COLOR[a.axis] ?? '#8fb'}">${esc(a.label)} ${a.level}</span>`)
    .join('');
  return `<div class="widget-title">🌳 Skilltree</div><div class="st-chips">${axes}</div>`;
}

export function initSkilltreeOverlay(baseUrl: string, fetchImpl: typeof fetch = fetch): { open: () => void } {
  let data: SkilltreeData | null = null;
  const { el, open } = createOverlay({
    id: 'skilltree-overlay',
    openEvent: 'open-skilltree',
    background: 'rgba(8,14,18,0.96)',
    render: async (container, { close }) => {
      const showOverview = (): void => {
        container.innerHTML = data ? overviewHtml(data) : '<div class="st-empty">Lade …</div>';
        container.querySelectorAll<HTMLElement>('.st-axis[data-axis]').forEach((row) => {
          row.addEventListener('click', () => {
            const axis = data!.axes.find((a) => a.axis === row.dataset.axis)!;
            container.innerHTML = axisDetailHtml(axis, data!.quests);
            container.querySelector('[data-action="overview"]')?.addEventListener('click', showOverview);
          });
        });
        container.querySelector('[data-action="close"]')?.addEventListener('click', close);
      };
      showOverview();
      try {
        data = await (await fetchImpl(`${baseUrl}/api/skilltree`)).json();
        showOverview();
      } catch {
        container.innerHTML = '<div class="st-empty">Skilltree nicht erreichbar.</div>';
      }
    },
  });
  el.style.padding = '32px 40px';
  registerOverlay({ key: 'skilltree', label: 'Skilltree', openEvent: 'open-skilltree' });
  return { open };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/skilltree-overlay.test.ts && npx tsc --noEmit`
Expected: PASS (5 passed), tsc clean

- [ ] **Step 5: Wire into main.ts**

In `apps/desktop/src/main.ts`:
1. Import (bei den anderen Overlay-Imports, ~Zeile 10):
```typescript
import { initSkilltreeOverlay, widgetHtml as skilltreeWidgetHtml } from './skilltree-overlay';
```
2. Init **vor** `initNavOverlay(getBaseUrl())` (~Zeile 421-423):
```typescript
initSkilltreeOverlay(getBaseUrl());
```
3. Im Widget-`switch` (neben `case 'health':`, ~Zeile 343) ein `case 'skilltree':` ergänzen, das `skilltreeWidgetHtml(payload)` rendert — dem `case 'health'`-Block nachbilden (gleiche Struktur, andere Render-Funktion).

- [ ] **Step 6: Full suite + live check, then commit**

Run: `cd apps/desktop && npx vitest run && npx tsc --noEmit`
Expected: alle grün
Live (Mantis + Dev-App laufen): `preview_start {url:"http://localhost:1420"}` → `javascript_tool: document.dispatchEvent(new CustomEvent('open-skilltree'))` → `computer screenshot` — Achsen + Quests sichtbar. Nav-Kachel „Skilltree" erscheint automatisch (Registry).

```bash
git add apps/desktop/src/skilltree-overlay.ts apps/desktop/src/skilltree-overlay.test.ts apps/desktop/src/main.ts
git commit -m "feat(skilltree): overlay + nav tile + widget, wired into app"
```

---

## Future Tasks (nach dem Kern-System, eigene Milestones)

Bewusst **nicht** im Kern-Plan (brauchen Persistenz oder Hardware — erst bauen, wenn nötig):

- **Weitere Signalquellen** (additive Collectors in `signals.py`): Second Brain → `zettel`/`lernpfad`, Habits → `streak`/`habit`, Git → `commit`, Goals/Journal → `reflexion`/`insight`, Fitness → `kraft`/`kondition` + `deadlift` fürs `dl_100`-Node. Je Quelle: `collect_from_*` + Aufruf in `collect_signals` + Test mit Fake-Store. **Vor Implementierung die jeweilige Store-Signatur verifizieren** (z.B. `domains/second_brain.py`, `domains/habits.py`).
- **Self-Report + Kalibrierungs-Spiegel** (Ebene ③): erste Persistenz (`skill_reports`-Tabelle), `POST /api/skilltree/report`, `calibration_check(self_level, measured_level, tolerance)` als reine Funktion, Overlay-UI zum Reporten, Nudge wenn Selbstbild ↔ Daten divergieren.
- **Cam-Verifikation** (Ebene ②): sobald die Cam da ist, als zusätzliche Signalquelle/Gate im Collector.
- **Retention-Tuning + Gewichte** an echten Daten (M4 des Specs): Halbwertszeiten/Gewichte pro Achse justieren, sobald reale Signal-History vorliegt.

## Self-Review (gegen den Spec)

**Spec-Coverage:** Fundament-Stats (T1/T2), Achsen erweiterbar (T4), Messen ① (T6), XP/Level (T2), Nodes permanent (T3), Decay smart mit Retention-Klassen (T1), Motor adaptiv Rost+Momentum (T5), kein Doppel-Tracking (T6/T7 leiten aus vorhandenen Stores ab), Router/Voice/Widget/Overlay (T8-T10). Messen ②/③ (Cam, Self-Report/Kalibrierung) → bewusst Future Tasks (brauchen Hardware/Persistenz). ✔
**Placeholder-Scan:** kein TBD/TODO in Kern-Tasks; jeder Code-Step zeigt echten Code. Erweiterungspunkte (weitere Collectors, main.ts `case`) sind konkret referenziert (Datei/Zeile/Vorbildblock), keine vagen „handle X". ✔
**Typ-Konsistenz:** `SignalEvent`/`axis_state`/`quest`-Shapes identisch über T1-T10; `build_skilltree_state`-Rückgabe (`axes/nodes/quests`) konsistent in Router (T8), Widget (T9), Overlay (T10). ✔
