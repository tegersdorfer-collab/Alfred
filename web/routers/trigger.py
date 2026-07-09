"""Externe Trigger-API — Not-Stopp und Automationen ohne Mantis-Neustart.

Alle Endpoints sind mit einem Shared-Secret (config.TRIGGER_TOKEN, aus .env)
geschützt und per constant-time-Vergleich geprüft. Ist kein Token gesetzt, ist
die ganze API deaktiviert (503) — sicherer Default.

Motivation: Bisher gab es keinen sauberen Weg, von außen etwas auszulösen —
ein Roboter-Not-Stopp ging nur über einen kompletten Mantis-Neustart (der die
BLE-Verbindung droppt). Jetzt: `POST /api/trigger/estop`.

Aufruf-Beispiel:
    curl -X POST -H "X-Mantis-Token: <token>" http://<host>:7779/api/trigger/estop
"""
import hmac
import logging

from fastapi import APIRouter, Request, Header
from fastapi.responses import JSONResponse

import config
from core import tools as T

log = logging.getLogger("mantis.api")


def _token_ok(provided: str | None) -> bool:
    """Constant-time-Vergleich; False wenn kein Server-Token konfiguriert ist."""
    expected = config.TRIGGER_TOKEN or ""
    if not expected:
        return False
    return hmac.compare_digest(provided or "", expected)


def build_router(orch=None) -> APIRouter:
    router = APIRouter()

    def _guard(token: str | None):
        """Gibt eine JSONResponse zurück, wenn abgelehnt — sonst None."""
        if not (config.TRIGGER_TOKEN or ""):
            return JSONResponse({"error": "Trigger-API deaktiviert (TRIGGER_TOKEN nicht gesetzt)."}, 503)
        if not _token_ok(token):
            log.warning("Trigger abgelehnt: ungültiger/fehlender Token")
            return JSONResponse({"error": "Nicht autorisiert."}, 401)
        return None

    @router.get("/api/trigger/ping")
    def trigger_ping(x_mantis_token: str | None = Header(default=None)):
        denied = _guard(x_mantis_token)
        return denied or {"ok": True, "message": "Trigger-API erreichbar, Token gültig."}

    @router.post("/api/trigger/estop")
    async def trigger_estop(x_mantis_token: str | None = Header(default=None)):
        """Not-Stopp: autonomen Fahrmodus beenden UND Motoren bremsen."""
        denied = _guard(x_mantis_token)
        if denied:
            return denied
        # Wichtig: NUR stoppen was aktiv/verbunden ist. Ein Not-Stopp darf niemals
        # erst einen BLE-Scan/Connect starten (dauert ~20s) — das Gegenteil von "sofort".
        results = {}
        try:
            from tools.robot.autonomy import AUTO
            results["autonomy"] = await AUTO.stop() if AUTO.running else "war nicht aktiv"
        except Exception as e:
            results["autonomy"] = f"Fehler: {e}"
        try:
            from tools.robot.manager import MANAGER
            results["motors"] = await MANAGER.stop() if MANAGER.connected else "kein Roboter verbunden"
        except Exception as e:
            results["motors"] = f"Fehler: {e}"
        log.warning("🛑 NOT-STOPP via Trigger-API ausgelöst: %s", results)
        return {"ok": True, "message": "Not-Stopp ausgelöst.", "details": results}

    @router.post("/api/trigger/tool")
    async def trigger_tool(req: Request, x_mantis_token: str | None = Header(default=None)):
        """Führt ein registriertes Tool von außen aus: Body {tool, args}."""
        denied = _guard(x_mantis_token)
        if denied:
            return denied
        try:
            body = await req.json()
        except Exception:
            body = {}
        name = (body or {}).get("tool", "")
        args = (body or {}).get("args", {}) or {}
        if not name:
            return JSONResponse({"error": "Feld 'tool' fehlt."}, 400)
        if name not in T.REGISTRY:
            return JSONResponse({"error": f"Tool '{name}' existiert nicht."}, 404)
        result = await T.execute(name, args)
        log.info("Trigger-Tool ausgeführt: %s(%s)", name, args)
        return {"ok": True, "tool": name, "result": result}

    return router
