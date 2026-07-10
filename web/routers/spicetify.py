"""WebSocket-Route für die Spicetify-Bridge.

Die Spicetify-Extension (tools/spotify/spicetify_ext/mantis-bridge.js) verbindet
sich mit `/spicetify/ws`. Mantis schickt darüber Kommandos, die Extension
antwortet mit strukturierten Daten aus Spotifys internen APIs.

Die eigentliche Request/Response-Logik liegt in tools/spotify/bridge.BRIDGE; diese
Route ist nur der Transport-Adapter (accept → register → relay → unregister).
"""
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from tools.spotify.bridge import BRIDGE

log = logging.getLogger("mantis.api")


def build_router(orch=None) -> APIRouter:
    router = APIRouter()

    @router.websocket("/spicetify/ws")
    async def spicetify_ws(sock: WebSocket):
        await sock.accept()
        await BRIDGE.register(sock)
        log.info("🎧 Spicetify-Bridge verbunden")
        try:
            while True:
                raw = await sock.receive_text()
                await BRIDGE.on_message(raw)
        except WebSocketDisconnect:
            pass
        except Exception as e:
            log.warning("Spicetify-Bridge-Fehler: %s", e)
        finally:
            await BRIDGE.unregister(sock)
            log.info("🎧 Spicetify-Bridge getrennt")

    return router
