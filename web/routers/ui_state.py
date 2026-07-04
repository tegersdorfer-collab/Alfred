"""
UI-State — API-Router. SSE-Kanal für das generative UI.
Verhaltensgleiches Muster zu web/routers/chat.py::status_stream.
"""
import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from core.ui_state import UI_BUS, WIDGET_TYPES, build_widget_payload

log = logging.getLogger("alfred.api")


def build_router(orch=None) -> APIRouter:
    router = APIRouter()

    @router.get("/api/ui/current")
    def ui_current():
        return UI_BUS.current

    @router.post("/api/ui/select")
    async def ui_select(body: dict):
        widget_type = body.get("widget_type")
        if widget_type not in WIDGET_TYPES:
            raise HTTPException(status_code=400, detail=f"Unbekannter widget_type: {widget_type}")
        payload = build_widget_payload(widget_type)
        if payload is None:
            raise HTTPException(status_code=400, detail=f"Datenquelle für '{widget_type}' nicht verfügbar")
        UI_BUS.show_widget(widget_type, payload, slot="main")
        return UI_BUS.current

    @router.post("/api/ui/clear")
    async def ui_clear():
        UI_BUS.clear()
        return UI_BUS.current

    @router.get("/api/ui/stream")
    async def ui_stream():
        q = UI_BUS.subscribe()

        async def gen():
            try:
                yield f"data: {json.dumps(UI_BUS.current)}\n\n"
                while True:
                    try:
                        evt = await asyncio.wait_for(q.get(), timeout=25)
                        yield f"data: {json.dumps(evt)}\n\n"
                    except asyncio.TimeoutError:
                        yield "data: {\"keepalive\":true}\n\n"
            finally:
                UI_BUS.unsubscribe(q)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    return router
