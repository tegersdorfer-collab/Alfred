"""
Alfred Dashboard API – läuft IM Alfred-Prozess (geteilter State mit dem Agent).
Voll interaktiv: REST für alle Domänen + 2-Wege-Chat (SSE-Streaming) + Live-Feeds.

App-Factory: `/health` bleibt hier, alle übrigen Endpoints liegen in
`web/routers/<domain>.py`. Jedes Router-Modul exportiert `build_router(orch)`
und wird unten via `app.include_router(...)` eingebunden.
"""
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

import config
from core import db, tools as T
from datetime import datetime

log = logging.getLogger("alfred.api")


def create_app(orch=None) -> FastAPI:
    app = FastAPI(title="Alfred Dashboard", docs_url=None, redoc_url=None)

    # Kein App-Token: main.py bindet den Server nur ins Tailnet, das Netzwerk
    # selbst ist die Zugriffskontrolle. Macht PWA-Homescreen-start_url "/" möglich.

    # ── System Health-Check ──────────────────────────────────────────────────
    @app.get("/health")
    async def system_health():
        """Schnell-Check: DB, Ollama, Telegram — für Monitoring und Aufwach-Diagnose."""
        import httpx as _httpx
        checks = {}

        # DB
        try:
            db.query_one("SELECT 1")
            checks["db"] = "ok"
        except Exception as e:
            checks["db"] = f"error: {e}"

        # Ollama
        try:
            async with _httpx.AsyncClient(timeout=3) as c:
                r = await c.get(f"{config.OLLAMA_BASE_URL}/api/tags")
            checks["ollama"] = "ok" if r.status_code == 200 else f"http {r.status_code}"
        except Exception as e:
            checks["ollama"] = f"error: {e}"

        # Telegram (nur prüfen ob Token gesetzt)
        checks["telegram"] = "ok" if config.TELEGRAM_BOT_TOKEN else "no token"

        # Orchestrator
        checks["orchestrator"] = "ok" if orch is not None else "not attached"

        ok = all(v == "ok" for v in checks.values())
        return JSONResponse({"ok": ok, "checks": checks}, status_code=200 if ok else 503)

    # ── Domänen-Router einbinden ──────────────────────────────────────────────
    from web import routers
    for module in routers.ROUTER_MODULES:
        app.include_router(module.build_router(orch))

    return app
