"""Tests für die Thermal-Throttling-Strategie (thermal.py::ProportionalStrategy) —
reiner P-Controller, kein Sensor/OS nötig.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from thermal import ProportionalStrategy


def test_no_sleep_below_target():
    s = ProportionalStrategy(min_sleep=0.0, max_sleep=30.0)
    assert s.compute_sleep(60, target=75, max_temp=95) == 0.0


def test_no_sleep_at_target():
    s = ProportionalStrategy(0.0, 30.0)
    assert s.compute_sleep(75, target=75, max_temp=95) == 0.0


def test_half_overshoot_half_sleep():
    s = ProportionalStrategy(0.0, 30.0)
    # 85 liegt bei (85-75)/(95-75) = 0.5 → 0.5 * 30 = 15
    assert s.compute_sleep(85, target=75, max_temp=95) == 15.0


def test_capped_at_max_sleep():
    s = ProportionalStrategy(0.0, 30.0)
    # weit über max → ratio auf 1.0 gedeckelt
    assert s.compute_sleep(120, target=75, max_temp=95) == 30.0


def test_min_sleep_offset_applied():
    s = ProportionalStrategy(min_sleep=2.0, max_sleep=12.0)
    # ratio 0.5 → 2 + 0.5*(12-2) = 7
    assert s.compute_sleep(85, target=75, max_temp=95) == 7.0


def test_no_division_by_zero_when_max_equals_target():
    s = ProportionalStrategy(0.0, 30.0)
    # Fehlkonfiguration max==target: über Ziel → sofort max_sleep, kein Crash
    assert s.compute_sleep(80, target=75, max_temp=75) == 30.0


def test_should_pause_at_or_above_max():
    s = ProportionalStrategy()
    assert s.should_pause(95, max_temp=95) is True
    assert s.should_pause(96, max_temp=95) is True
    assert s.should_pause(94, max_temp=95) is False
