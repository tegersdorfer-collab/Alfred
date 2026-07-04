"""Testet den /api/ui/current-Endpunkt über einen echten FastAPI-TestClient
(SSE-Streaming selbst wird per manueller curl-Verifikation geprüft, nicht
hier — blockierende Generatoren sind mit TestClient unhandlich)."""
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
    def test_liefert_ruhezustand_wenn_kein_widget_aktiv(self):
        UI_BUS.clear()
        client = _make_client()
        resp = client.get("/api/ui/current")
        assert resp.status_code == 200
        body = resp.json()
        assert body["layout"] is None
        assert body["slots"] == {}

    def test_liefert_aktuellen_layout_zustand(self):
        UI_BUS.show_widget("sleep", {"nights": []})
        client = _make_client()
        resp = client.get("/api/ui/current")
        assert resp.status_code == 200
        body = resp.json()
        assert body["layout"] == "single"
        assert body["slots"]["main"] == {"widget": "sleep", "payload": {"nights": []}}
        UI_BUS.clear()  # Zustand für andere Tests zurücksetzen
