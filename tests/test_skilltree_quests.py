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

# ── quest_progress axis filter: fremde Achsen zählen nicht ───────────────────────

def test_quest_progress_ignores_other_axis_same_kind():
    q = {"key": "train_3x", "axis": "koerper", "label": "3×", "target_kind": "training",
         "target_count": 2, "since": "2026-07-14"}
    sigs = [
        {"axis": "koerper", "kind": "training", "value": 1.0, "ts": "2026-07-15", "source": "h", "count": 1},
        {"axis": "wissen", "kind": "training", "value": 1.0, "ts": "2026-07-16", "source": "x", "count": 1},
    ]
    assert quest_progress(q, sigs, date(2026, 7, 20))["count"] == 1  # fremde Achse zählt nicht
