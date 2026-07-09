"""Tests für die DB-Schicht (core/db.py): tote Connections dürfen den Pool nicht
vergiften, und Aufrufe werden bei Verbindungsverlust genau einmal wiederholt.

Läuft ohne echte PostgreSQL — der Pool wird durch einen Fake ersetzt.
"""

import os
import sys

import psycopg2
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import db


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        if self.conn.dead:
            raise psycopg2.OperationalError("server closed the connection unexpectedly")

    def fetchall(self):
        return [{"n": 1}]

    def fetchone(self):
        return {"n": 1}

    @property
    def rowcount(self):
        return 1

    def close(self):
        pass


class FakeConn:
    def __init__(self, dead=False):
        self.dead = dead
        self.executed: list = []
        self.committed = self.rolled_back = False

    def cursor(self, cursor_factory=None):
        return FakeCursor(self)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class FakePool:
    """Gibt Connections in Reihenfolge aus; merkt sich, ob putconn(close=True) kam."""

    def __init__(self, conns):
        self.conns = list(conns)
        self.returned: list = []  # (conn, closed)

    def getconn(self):
        return self.conns.pop(0)

    def putconn(self, conn, close=False):
        self.returned.append((conn, close))


@pytest.fixture
def fake_pool(monkeypatch):
    def install(conns):
        pool = FakePool(conns)
        monkeypatch.setattr(db, "_pool", pool)
        return pool
    yield install
    db._pool = None


def test_query_happy_path(fake_pool):
    pool = fake_pool([FakeConn()])
    assert db.query("SELECT 1") == [{"n": 1}]
    conn, closed = pool.returned[0]
    assert conn.committed and not closed  # gesunde Connection zurück in den Pool


def test_dead_connection_is_discarded_not_pooled(fake_pool):
    dead, fresh = FakeConn(dead=True), FakeConn()
    pool = fake_pool([dead, fresh])
    assert db.query("SELECT 1") == [{"n": 1}]  # Retry mit frischer Connection
    assert pool.returned[0] == (dead, True)    # tote Connection verworfen ...
    assert pool.returned[1] == (fresh, False)  # ... frische zurück in den Pool


def test_retry_happens_exactly_once(fake_pool):
    fake_pool([FakeConn(dead=True), FakeConn(dead=True), FakeConn()])
    with pytest.raises(psycopg2.OperationalError):
        db.query("SELECT 1")  # zwei tote hintereinander → Fehler, kein Endlos-Retry


def test_normal_errors_still_rollback_and_pool(fake_pool):
    class BadCursorConn(FakeConn):
        def cursor(self, cursor_factory=None):
            c = FakeCursor(self)
            def boom(sql, params=None):
                raise ValueError("kaputtes SQL")
            c.execute = boom
            return c

    conn = BadCursorConn()
    pool = fake_pool([conn])
    with pytest.raises(ValueError):
        db.query("SELECT kaputt")
    assert conn.rolled_back
    assert pool.returned[0] == (conn, False)  # NICHT verworfen — Connection ist ok


def test_execute_returns_rowcount(fake_pool):
    fake_pool([FakeConn()])
    assert db.execute("UPDATE x SET y=1") == 1


def test_insert_returning_first_value(fake_pool):
    fake_pool([FakeConn()])
    assert db.insert_returning("INSERT ... RETURNING id") == 1
