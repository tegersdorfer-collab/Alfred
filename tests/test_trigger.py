"""Tests für die externe Trigger-API (web/routers/trigger.py): Token-Schutz,
deaktiviert-Default, Not-Stopp, generischer Tool-Trigger. Kein Roboter/BLE nötig.
"""

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from core import tools as T
from web.routers.trigger import build_router


def _client():
    app = FastAPI()
    app.include_router(build_router(orch=None))
    return TestClient(app)


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setattr(config, "TRIGGER_TOKEN", "geheim123")
    return "geheim123"


# ── Token-Schutz ──────────────────────────────────────────────────────────────

def test_disabled_when_no_token(monkeypatch):
    monkeypatch.setattr(config, "TRIGGER_TOKEN", "")
    r = _client().get("/api/trigger/ping")
    assert r.status_code == 503  # sicherer Default: aus


def test_wrong_token_rejected(token):
    r = _client().get("/api/trigger/ping", headers={"X-Mantis-Token": "falsch"})
    assert r.status_code == 401


def test_missing_token_rejected(token):
    assert _client().get("/api/trigger/ping").status_code == 401


def test_ping_ok_with_token(token):
    r = _client().get("/api/trigger/ping", headers={"X-Mantis-Token": token})
    assert r.status_code == 200 and r.json()["ok"] is True


# ── Not-Stopp ─────────────────────────────────────────────────────────────────

def test_estop_calls_both_stops(token, monkeypatch):
    calls = []

    async def fake_auto_stop():
        calls.append("autonomy"); return "🛑 Autonomie gestoppt."

    async def fake_motor_stop():
        calls.append("motors"); return "🛑 gestoppt"

    import tools.robot.autonomy as autonomy_mod
    import tools.robot.manager as manager_mod
    # running/connected sind Klassen-Properties → auf der Klasse überschreiben,
    # damit der estop-Guard die (gefakten) Stops tatsächlich aufruft.
    monkeypatch.setattr(type(autonomy_mod.AUTO), "running", property(lambda self: True))
    monkeypatch.setattr(type(manager_mod.MANAGER), "connected", property(lambda self: True))
    monkeypatch.setattr(autonomy_mod.AUTO, "stop", fake_auto_stop)
    monkeypatch.setattr(manager_mod.MANAGER, "stop", fake_motor_stop)

    r = _client().post("/api/trigger/estop", headers={"X-Mantis-Token": token})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert set(calls) == {"autonomy", "motors"}


def test_estop_requires_token(token):
    assert _client().post("/api/trigger/estop").status_code == 401


# ── Generischer Tool-Trigger ──────────────────────────────────────────────────

@pytest.fixture
def echo_tool():
    async def _echo(text: str = ""):
        return f"ECHO:{text}"
    saved = dict(T.REGISTRY)
    T.REGISTRY["echo"] = T.Tool("echo", "Echo", {"text": {"type": "string"}}, _echo)
    yield
    T.REGISTRY.clear()
    T.REGISTRY.update(saved)


def test_tool_trigger_runs_registered_tool(token, echo_tool):
    r = _client().post("/api/trigger/tool", headers={"X-Mantis-Token": token},
                       json={"tool": "echo", "args": {"text": "hi"}})
    assert r.status_code == 200
    assert r.json()["result"] == "ECHO:hi"


def test_tool_trigger_unknown_tool_404(token):
    r = _client().post("/api/trigger/tool", headers={"X-Mantis-Token": token},
                       json={"tool": "gibtsnicht"})
    assert r.status_code == 404


def test_tool_trigger_missing_field_400(token):
    r = _client().post("/api/trigger/tool", headers={"X-Mantis-Token": token}, json={})
    assert r.status_code == 400


def test_tool_trigger_requires_token(token, echo_tool):
    r = _client().post("/api/trigger/tool", json={"tool": "echo"})
    assert r.status_code == 401
