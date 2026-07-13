"""Tests für die Health-Scoring-Engine (domains/health_scores.py) — reine
Normalisierungs-/Aggregations-Logik über list[dict], keine DB.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.health_scores import (
    DEFAULT_CONFIG,
    compute_baselines,
    compute_body_trend,
    compute_domain_scores,
    health_narrative,
    score_history,
    score_metric,
)


def _row(date, **metrics):
    row = {"date": date}
    row.update(metrics)
    return row

# ── score_metric: Baseline-Normierung (0–100 über ±2σ um den Median) ──────────


def test_value_at_baseline_median_scores_50():
    # Wert genau auf dem persönlichen Median → neutraler Score 50.
    assert score_metric(60.0, baseline={"median": 60.0, "spread": 10.0}) == 50.0


def test_value_two_spread_above_scores_100():
    # +2σ über dem Median → Bestwert (higher-is-better).
    assert score_metric(80.0, baseline={"median": 60.0, "spread": 10.0}) == 100.0


def test_value_one_spread_above_scores_75():
    # +1σ → linear die Hälfte zwischen 50 und 100.
    assert score_metric(70.0, baseline={"median": 60.0, "spread": 10.0}) == 75.0


def test_value_far_above_clamps_to_100():
    # +5σ → geklemmt auf 100, nicht darüber.
    assert score_metric(110.0, baseline={"median": 60.0, "spread": 10.0}) == 100.0


def test_value_two_spread_below_scores_0():
    # -2σ (higher-is-better) → schlechtester Wert.
    assert score_metric(40.0, baseline={"median": 60.0, "spread": 10.0}) == 0.0


def test_lower_is_better_inverts():
    # Ruhepuls: unter dem Median ist BESSER → -2σ ergibt 100.
    assert score_metric(
        40.0, baseline={"median": 60.0, "spread": 10.0}, higher_is_better=False
    ) == 100.0


def test_missing_value_returns_none():
    # Fehlender Messwert → kein Score (Graceful Degradation, kein erfundener Wert).
    assert score_metric(None, baseline={"median": 60.0, "spread": 10.0}) is None


# ── score_metric: Richtwert-Fallback (Cold-Start, Trapez lo→ideal→hi) ──────────

# Schlaf: 7–9 h ideal, unter 4 h oder über 11 h wertlos.
SLEEP_GUIDE = {"lo": 4.0, "ideal_lo": 7.0, "ideal_hi": 9.0, "hi": 11.0}
# Schritte: höher ist besser, ab 8000 ideal, keine Obergrenze.
STEPS_GUIDE = {"lo": 0.0, "ideal_lo": 8000.0, "ideal_hi": float("inf"), "hi": float("inf")}


def test_guideline_ideal_plateau_scores_100():
    assert score_metric(8.0, guideline=SLEEP_GUIDE) == 100.0


def test_guideline_at_lower_bound_scores_0():
    assert score_metric(4.0, guideline=SLEEP_GUIDE) == 0.0


def test_guideline_ramp_up_is_linear():
    # Mitte zwischen lo (4) und ideal_lo (7) → 50.
    assert score_metric(5.5, guideline=SLEEP_GUIDE) == 50.0


def test_guideline_over_range_ramps_down():
    # Zwischen ideal_hi (9) und hi (11): 10 → 50.
    assert score_metric(10.0, guideline=SLEEP_GUIDE) == 50.0


def test_guideline_open_top_higher_is_better():
    assert score_metric(8000.0, guideline=STEPS_GUIDE) == 100.0
    assert score_metric(4000.0, guideline=STEPS_GUIDE) == 50.0


def test_baseline_takes_precedence_over_guideline():
    # Beides da → Baseline gewinnt (persönlicher > allgemeiner Maßstab).
    assert score_metric(
        60.0, baseline={"median": 60.0, "spread": 10.0}, guideline=SLEEP_GUIDE
    ) == 50.0


def test_baseline_without_spread_falls_back_to_guideline():
    # Cold-Start: noch keine belastbare Streuung → Richtwert greift.
    assert score_metric(
        8.0, baseline={"median": 8.0, "spread": None}, guideline=SLEEP_GUIDE
    ) == 100.0


def test_no_baseline_no_guideline_returns_none():
    assert score_metric(8.0) is None


# ── compute_baselines: rollierender Median + MAD-Streuung ──────────────────────


def test_baseline_median_and_mad_from_values():
    vals = [40.0, 50.0, 55.0, 60.0, 60.0, 65.0, 70.0]  # Median 60, MAD 5
    rows = [_row(f"2026-06-{i + 1:02d}", hrv=v) for i, v in enumerate(vals)]
    assert compute_baselines(rows, min_n=7)["hrv"] == {"median": 60.0, "spread": 5.0}


def test_baseline_ignores_none_values():
    rows = [_row("2026-06-01", hrv=None), _row("2026-06-02", hrv=60.0),
            _row("2026-06-03", hrv=None)]
    assert compute_baselines(rows, min_n=1)["hrv"] == {"median": 60.0, "spread": 0.0}


def test_baseline_too_few_values_yields_none_spread():
    # Unter min_n → Median ja, aber keine belastbare Streuung → Cold-Start.
    rows = [_row("2026-06-01", hrv=50.0), _row("2026-06-02", hrv=60.0),
            _row("2026-06-03", hrv=70.0)]
    b = compute_baselines(rows, min_n=7)["hrv"]
    assert b["median"] == 60.0
    assert b["spread"] is None


def test_baseline_uses_only_most_recent_window():
    rows = [_row("2026-06-01", hrv=10.0), _row("2026-06-02", hrv=20.0),
            _row("2026-06-03", hrv=30.0)]
    assert compute_baselines(rows, window=2, min_n=1)["hrv"]["median"] == 25.0


def test_baseline_metric_with_no_data_is_none():
    rows = [_row("2026-06-01", steps=100.0)]
    assert compute_baselines(rows, min_n=1)["hrv"] == {"median": None, "spread": None}


# ── compute_domain_scores: Aggregation, Renormierung, Degradation ─────────────

# Kontrollierte Config (stabil, unabhängig von den finalen Default-Gewichten).
TWO = {"demo": [
    {"metric": "hrv", "weight": 0.5, "higher_is_better": True},
    {"metric": "resting_hr", "weight": 0.5, "higher_is_better": False},
]}
BASE = {"hrv": {"median": 60.0, "spread": 10.0},
        "resting_hr": {"median": 50.0, "spread": 5.0}}


def test_domain_weighted_average_of_subscores():
    # hrv 70 → +1σ → 75; resting_hr 50 → Median → 50. 75*0.5 + 50*0.5 = 62.5.
    row = _row("2026-07-13", hrv=70.0, resting_hr=50.0)
    dom = compute_domain_scores(row, BASE, config=TWO)["demo"]
    assert dom["score"] == 62.5
    assert dom["status"] == "ok"
    assert dom["coverage"] == 1.0


def test_domain_renormalizes_weights_when_metric_missing():
    # resting_hr fehlt → nur hrv (75) zählt, Gewicht renormiert → Score 75.
    row = _row("2026-07-13", hrv=70.0)
    dom = compute_domain_scores(row, BASE, config=TWO)["demo"]
    assert dom["score"] == 75.0
    assert dom["coverage"] == 0.5
    used = {c["metric"]: c["used"] for c in dom["components"]}
    assert used == {"hrv": True, "resting_hr": False}


def test_domain_insufficient_data_below_coverage_threshold():
    cfg = {"demo3": [
        {"metric": "hrv", "weight": 0.6, "higher_is_better": True},
        {"metric": "resting_hr", "weight": 0.4, "higher_is_better": False},
    ]}
    row = _row("2026-07-13", resting_hr=50.0)  # nur 0.4 der Gewichte vorhanden
    dom = compute_domain_scores(row, BASE, config=cfg)["demo3"]
    assert dom["score"] is None
    assert dom["status"] == "insufficient_data"
    assert dom["coverage"] == 0.4


def test_domain_components_expose_raw_value_and_subscore():
    row = _row("2026-07-13", hrv=80.0, resting_hr=50.0)
    dom = compute_domain_scores(row, BASE, config=TWO)["demo"]
    hrv = next(c for c in dom["components"] if c["metric"] == "hrv")
    assert hrv["value"] == 80.0
    assert hrv["score"] == 100.0  # +2σ
    assert hrv["weight"] == 0.5


def test_default_config_has_core_domains():
    assert {"recovery", "sleep", "activity"} <= set(DEFAULT_CONFIG)


# ── score_history: pro Tag Domain-Scores gegen die gemeinsame Baseline ─────────


def test_score_history_returns_sorted_per_day_domains():
    rows = [_row("2026-07-13", steps=9000.0), _row("2026-07-11", steps=3000.0)]
    hist = score_history(rows)
    assert [h["date"] for h in hist] == ["2026-07-11", "2026-07-13"]  # chronologisch
    assert set(DEFAULT_CONFIG) <= set(hist[-1]["domains"])
    assert "status" in hist[-1]["domains"]["activity"]


def test_score_history_empty_rows_is_empty_list():
    assert score_history([]) == []


# ── compute_body_trend: Gewicht als Trend (kein erzwungener 0–100-Score) ───────


def test_body_trend_computes_deltas_and_direction():
    rows = [
        _row("2026-06-13", weight=85.0),   # -30 T
        _row("2026-07-06", weight=83.6),   # -7 T
        _row("2026-07-13", weight=83.0),   # heute
    ]
    t = compute_body_trend(rows)
    assert t["latest"] == 83.0
    assert t["delta_7d"] == -0.6
    assert t["delta_30d"] == -2.0
    assert t["direction"] == "down"


def test_body_trend_stable_within_threshold():
    rows = [_row("2026-06-13", weight=83.2), _row("2026-07-13", weight=83.0)]
    assert compute_body_trend(rows)["direction"] == "stable"


def test_body_trend_none_without_weight():
    assert compute_body_trend([_row("2026-07-13", steps=100.0)]) is None


# ── health_narrative: deterministischer Klartext-Read ─────────────────────────

_TODAY_MIXED = {
    "date": "2026-07-13",
    "domains": {
        "recovery": {"score": None, "status": "insufficient_data", "coverage": 0.25,
                     "components": []},
        "sleep": {"score": 56.0, "status": "ok", "coverage": 1.0, "components": [
            {"metric": "sleep_duration", "score": 54.0, "used": True},
            {"metric": "sleep_deep", "score": 60.0, "used": True}]},
        "activity": {"score": 36.0, "status": "ok", "coverage": 0.7, "components": [
            {"metric": "steps", "score": 20.0, "used": True},
            {"metric": "active_calories", "score": 55.0, "used": True}]},
    },
}


def test_narrative_names_weakest_domain_and_driver():
    text = health_narrative(_TODAY_MIXED)
    assert "Activity" in text        # schwächster ok-Bereich (36)
    assert "Schritte" in text        # dessen schwächster Treiber (steps 20)


def test_narrative_flags_missing_domain():
    # Recovery ohne Daten wird als offen benannt, nicht verschwiegen.
    assert "Recovery" in health_narrative(_TODAY_MIXED)


def test_narrative_no_scores_points_to_sync():
    empty = {"date": "2026-07-13", "domains": {
        "sleep": {"score": None, "status": "insufficient_data", "coverage": 0.0,
                  "components": []}}}
    assert "COROS" in health_narrative(empty)
