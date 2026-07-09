"""Tests für set_status-Härtung (domains/tasks.py): ungültige Status dürfen die
DB nicht mehr korrumpieren (Regression zum Telegram-'open'-Bug). db gemockt.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains import tasks


class _Recorder:
    def __init__(self):
        self.executes = []

    def execute(self, sql, params=()):
        self.executes.append((sql, params))
        return 1


def _patch(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(tasks.db, "execute", rec.execute)
    return rec


def test_valid_status_written(monkeypatch):
    rec = _patch(monkeypatch)
    tasks.set_status(5, "in_progress")
    assert rec.executes and rec.executes[-1][1] == ("in_progress", 5)


def test_open_alias_coerced_to_todo(monkeypatch):
    rec = _patch(monkeypatch)
    tasks.set_status(7, "open")  # Filter-Alias, kein echter Status
    assert rec.executes[-1][1] == ("todo", 7)  # NICHT "open" gespeichert


def test_done_routes_to_complete_task(monkeypatch):
    rec = _patch(monkeypatch)
    tasks.set_status(9, "done")
    sql = rec.executes[-1][0]
    assert "status='done'" in sql and "completed_at=NOW()" in sql


def test_garbage_status_ignored(monkeypatch):
    rec = _patch(monkeypatch)
    tasks.set_status(3, "voelliger_quatsch")
    assert rec.executes == []  # nichts geschrieben — lieber nichts als Korruption


def test_todo_written(monkeypatch):
    rec = _patch(monkeypatch)
    tasks.set_status(1, "todo")
    assert rec.executes[-1][1] == ("todo", 1)
