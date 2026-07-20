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


def test_axis_xp_only_counts_own_axis():
    now = date(2026, 7, 20)
    axis_k = {"key": "koerper", "label": "Körper", "components": {
        "training": {"weight": 10.0, "retention": "fast"}}}
    sigs = [
        {"axis": "koerper", "kind": "training", "value": 1.0, "ts": "2026-07-20", "source": "h", "count": 1},
        {"axis": "wissen", "kind": "training", "value": 1.0, "ts": "2026-07-20", "source": "x", "count": 1},
    ]
    assert axis_xp(sigs, axis_k, now) == 10.0  # fremde Achse mit gleichem kind zählt nicht


def test_retention_unknown_class_raises():
    import pytest
    with pytest.raises(ValueError):
        retention_decay("fastt", 5)


# ── xp_to_level: abflachende Kurve (höhere Level kosten mehr XP) ───────────────

from domains.skilltree.scoring import axis_level, xp_to_level


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
