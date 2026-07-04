"""Testet den /api/ui/current-Endpunkt über einen echten FastAPI-TestClient
(SSE-Streaming selbst wird per manueller curl-Verifikation in Task 4 geprüft,
nicht hier — blockierende Generatoren sind mit TestClient unhandlich)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.ui_state import UI_BUS
from web.routers.ui_state import build_router


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(build_router())
    return TestClient(app)


class TestUiCurrentEndpoint:
    def test_liefert_none_widget_wenn_kein_zustand(self):
        UI_BUS._current = None
        client = _make_client()
        resp = client.get("/api/ui/current")
        assert resp.status_code == 200
        assert resp.json() == {"widget": None}

    def test_liefert_aktuellen_widget_zustand(self):
        UI_BUS.show_widget("sleep", {"nights": []})
        client = _make_client()
        resp = client.get("/api/ui/current")
        assert resp.status_code == 200
        body = resp.json()
        assert body["widget"] == "sleep"
        assert body["payload"] == {"nights": []}
        UI_BUS.clear()  # Zustand für andere Tests zurücksetzen
