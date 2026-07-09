"""Tests für die adaptive Bulk-Ziel-Rechenlogik (domains/nutrition.py) —
BMR, Gewichtstrend-Regression, kcal-Anpassung, Makro-Verteilung. Kein DB.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.nutrition import (
    bmr_mifflin, linear_slope_per_week, bulk_adjustment, macros_for,
)


# ── BMR ───────────────────────────────────────────────────────────────────────

def test_bmr_mifflin_male():
    # 10*84 + 6.25*192 - 5*19 + 5 = 840 + 1200 - 95 + 5 = 1950
    assert bmr_mifflin(84, 192, 19) == 1950


def test_bmr_mifflin_female_offset():
    assert bmr_mifflin(84, 192, 19, male=False) == 1950 - 5 - 161


# ── Lineare Regression (kg/Woche) ─────────────────────────────────────────────

def test_slope_needs_two_points():
    assert linear_slope_per_week([0], [84.0]) is None


def test_slope_no_variance_returns_none():
    # alle am selben Tag → keine x-Varianz
    assert linear_slope_per_week([5, 5, 5], [84.0, 85.0, 86.0]) is None


def test_slope_perfect_gain():
    # +0.1 kg/Tag über 30 Tage → 0.7 kg/Woche
    xs = list(range(0, 30))
    weights = [84.0 + 0.1 * d for d in xs]
    assert linear_slope_per_week(xs, weights) == 0.7


def test_slope_weight_loss_negative():
    xs = [0, 7, 14]
    weights = [90.0, 89.0, 88.0]  # -1 kg/Woche
    assert linear_slope_per_week(xs, weights) == -1.0


# ── Bulk-Anpassung ────────────────────────────────────────────────────────────

def test_adjustment_too_slow_adds():
    status, adj = bulk_adjustment(0.1, 0.25, current_adj=0, step=150, max_adj=600)
    assert status == "too_slow" and adj == 150


def test_adjustment_too_fast_subtracts():
    status, adj = bulk_adjustment(0.5, 0.25, current_adj=0, step=150, max_adj=600)
    assert status == "too_fast" and adj == -150


def test_adjustment_on_track_keeps():
    status, adj = bulk_adjustment(0.26, 0.25, current_adj=300, step=150, max_adj=600)
    assert status == "on_track" and adj == 300


def test_adjustment_capped_at_max():
    status, adj = bulk_adjustment(0.0, 0.25, current_adj=550, step=150, max_adj=600)
    assert adj == 600  # nicht 700


def test_adjustment_capped_at_min():
    status, adj = bulk_adjustment(1.0, 0.25, current_adj=-550, step=150, max_adj=600)
    assert adj == -600


# ── Makros ────────────────────────────────────────────────────────────────────

def test_macros_distribution():
    m = macros_for(3000, 84)
    assert m["protein"] == round(84 * 2.2)  # 185
    assert m["fat"] == 84
    # carbs = (3000 - 185*4 - 84*9) / 4 = (3000 - 740 - 756)/4 = 376
    assert m["carbs"] == 376


def test_macros_carbs_floor():
    # sehr niedriges kcal → carbs würde negativ, min 50
    m = macros_for(1000, 84)
    assert m["carbs"] == 50
