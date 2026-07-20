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
