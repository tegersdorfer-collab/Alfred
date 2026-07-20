import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from fastapi import FastAPI
from web.routers.skilltree import build_router


class _H:
    def __init__(self, d, exercise_minutes=None):
        self.date = d
        self.exercise_minutes = exercise_minutes
        self.steps = None


class _Dash:
    def get_recent_health(self, days=90):
        return [_H(f"2026-07-{d:02d}", exercise_minutes=60) for d in range(10, 20)]


class _Orch:
    _dashboard = _Dash()


def _client(orch):
    app = FastAPI()
    app.include_router(build_router(orch))
    return TestClient(app)


def test_endpoint_returns_all_axes():
    r = _client(_Orch()).get("/api/skilltree")
    assert r.status_code == 200
    body = r.json()
    assert {a["axis"] for a in body["axes"]} == {"koerper", "wissen", "schaffen", "geist", "disziplin"}
    assert "quests" in body and "nodes" in body

def test_endpoint_without_orch_is_empty_axes():
    body = _client(None).get("/api/skilltree").json()
    assert all(a["level"] == 0 for a in body["axes"])
