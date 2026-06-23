"""Unit-Tests für Habits-Domäne (streak-Logik, kein DB nötig)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from domains.habits import _streak_from_dates, streak, find_habit


def _dates(*offsets: int) -> set:
    """Erzeugt ein Set aus date-Objekten relativ zu heute (0=heute, -1=gestern, …)."""
    today = date.today()
    return {today + timedelta(days=o) for o in offsets}


class TestStreakFromDates:
    def test_empty_returns_zero(self):
        assert _streak_from_dates(set()) == 0

    def test_only_today(self):
        assert _streak_from_dates(_dates(0)) == 1

    def test_only_yesterday(self):
        # gestern als Startpunkt erlaubt
        assert _streak_from_dates(_dates(-1)) == 1

    def test_today_and_yesterday(self):
        assert _streak_from_dates(_dates(0, -1)) == 2

    def test_continuous_streak(self):
        assert _streak_from_dates(_dates(0, -1, -2, -3, -4)) == 5

    def test_gap_breaks_streak(self):
        # heute + vor 2 Tagen, aber gestern fehlt
        assert _streak_from_dates(_dates(0, -2)) == 1

    def test_old_dates_dont_count(self):
        # nur alte Einträge, kein aktueller
        assert _streak_from_dates(_dates(-5, -6, -7)) == 0

    def test_future_date_ignored(self):
        # Zukünftige Einträge sollen Streak nicht starten
        assert _streak_from_dates(_dates(1)) == 0

    def test_streak_counts_backwards_correctly(self):
        # 7 Tage am Stück bis gestern
        assert _streak_from_dates(_dates(-1, -2, -3, -4, -5, -6, -7)) == 7


class TestStreakWithDb:
    def test_no_logs_returns_zero(self):
        with patch("domains.habits.db") as mock_db:
            mock_db.query.return_value = []
            assert streak(habit_id=1) == 0

    def test_streak_with_consecutive_days(self):
        today = date.today()
        rows = [{"date": today - timedelta(days=i)} for i in range(3)]
        with patch("domains.habits.db") as mock_db:
            mock_db.query.return_value = rows
            assert streak(habit_id=1) == 3

    def test_streak_broken_by_gap(self):
        today = date.today()
        rows = [{"date": today}, {"date": today - timedelta(days=2)}]
        with patch("domains.habits.db") as mock_db:
            mock_db.query.return_value = rows
            assert streak(habit_id=1) == 1


class TestFindHabit:
    def test_exact_match(self):
        rows = [{"id": 1, "name": "Sport", "emoji": "💪", "active": True}]
        with patch("domains.habits.db") as mock_db:
            mock_db.query.return_value = rows
            result = find_habit("Sport")
            assert result is not None
            assert result["id"] == 1

    def test_no_match_returns_none(self):
        with patch("domains.habits.db") as mock_db:
            mock_db.query.return_value = []
            assert find_habit("Nichtexistent") is None
