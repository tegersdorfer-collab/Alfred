"""Unit-Tests für Tasks-Domäne (_computed_progress, set_progress-Klammerung)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch
from domains.tasks import _computed_progress


class TestComputedProgress:
    def test_no_subtasks_uses_progress_pct(self):
        task = {"subtasks": [], "progress_pct": 40, "status": "open"}
        assert _computed_progress(task) == 40

    def test_done_task_without_subtasks_returns_100(self):
        task = {"subtasks": None, "progress_pct": None, "status": "done"}
        assert _computed_progress(task) == 100

    def test_open_task_no_pct_returns_zero(self):
        task = {"subtasks": None, "progress_pct": None, "status": "open"}
        assert _computed_progress(task) == 0

    def test_subtasks_all_done(self):
        task = {
            "subtasks": [
                {"status": "done"},
                {"status": "done"},
                {"status": "done"},
            ],
            "progress_pct": 0,
            "status": "open",
        }
        assert _computed_progress(task) == 100

    def test_subtasks_none_done(self):
        task = {
            "subtasks": [{"status": "open"}, {"status": "open"}],
            "progress_pct": 50,
            "status": "open",
        }
        assert _computed_progress(task) == 0

    def test_subtasks_partial(self):
        task = {
            "subtasks": [
                {"status": "done"},
                {"status": "open"},
                {"status": "done"},
                {"status": "open"},
            ],
            "progress_pct": 0,
            "status": "open",
        }
        assert _computed_progress(task) == 50

    def test_subtasks_override_progress_pct(self):
        # Subtasks haben Vorrang vor progress_pct
        task = {
            "subtasks": [{"status": "done"}],
            "progress_pct": 0,
            "status": "open",
        }
        assert _computed_progress(task) == 100


class TestSetProgressClamping:
    def test_clamping_above_100(self):
        with patch("domains.tasks.db") as mock_db:
            from domains.tasks import set_progress
            set_progress(1, 150)
            call_args = mock_db.execute.call_args[0]
            assert call_args[1][0] == 100  # pct geclampt

    def test_clamping_below_zero(self):
        with patch("domains.tasks.db") as mock_db:
            from domains.tasks import set_progress
            set_progress(1, -10)
            call_args = mock_db.execute.call_args[0]
            assert call_args[1][0] == 0

    def test_100_sets_done_status(self):
        with patch("domains.tasks.db") as mock_db:
            from domains.tasks import set_progress
            set_progress(1, 100)
            call_args = mock_db.execute.call_args[0]
            assert call_args[1][1] == "done"

    def test_partial_sets_in_progress(self):
        with patch("domains.tasks.db") as mock_db:
            from domains.tasks import set_progress
            set_progress(1, 50)
            call_args = mock_db.execute.call_args[0]
            assert call_args[1][1] == "in_progress"
