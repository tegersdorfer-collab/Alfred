"""Spicetify-Bridge (Mantis-Seite) — strukturierter Draht zu Spotify.

Spotify/Spicetify läuft im Browser-Sandbox und kann nur AUSGEHEND verbinden.
Deshalb ist Mantis der Server: die Spicetify-Extension (mantis-bridge.js) öffnet
einen WebSocket zu `/spicetify/ws`, registriert sich hier, und Mantis schickt
Kommandos (search/now_playing/play/…), die die Extension über Spotifys interne
APIs (GraphQL/Player/Platform) beantwortet.

Diese Klasse macht die Request/Response-Korrelation (id → Future). Der Transport
(`_send`) ist die einzige Grenze zum echten Socket und wird in Tests gemockt.
"""
from __future__ import annotations

import asyncio
import itertools
import json


class BridgeError(RuntimeError):
    """Bridge nicht verbunden / Timeout / Fehler von der Extension."""


class SpotifyBridge:
    def __init__(self):
        self._ws = None
        self._pending: dict[int, asyncio.Future] = {}
        self._ids = itertools.count(1)

    # ── Verbindungs-Lebenszyklus (von der WS-Route aufgerufen) ────────────────

    def is_connected(self) -> bool:
        return self._ws is not None

    async def register(self, ws) -> None:
        self._ws = ws

    async def unregister(self, ws) -> None:
        if self._ws is ws:
            self._ws = None
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(BridgeError("Bridge-Verbindung getrennt."))
        self._pending.clear()

    async def on_message(self, raw: str) -> None:
        """Antwort der Extension einer wartenden Anfrage zuordnen."""
        try:
            msg = json.loads(raw)
        except Exception:
            return
        fut = self._pending.pop(msg.get("id"), None)
        if fut and not fut.done():
            fut.set_result(msg)

    # ── Transport-Grenze (in Tests gemockt) ───────────────────────────────────

    async def _send(self, text: str) -> None:  # pragma: no cover - live-only
        await self._ws.send_text(text)

    # ── RPC + öffentliche API ─────────────────────────────────────────────────

    async def _rpc(self, method: str, params: dict | None = None, timeout: float = 8.0):
        if not self.is_connected():
            raise BridgeError("Spicetify-Bridge nicht verbunden (Extension aktiv?).")
        rid = next(self._ids)
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        await self._send(json.dumps({"id": rid, "method": method, "params": params or {}}))
        try:
            msg = await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self._pending.pop(rid, None)
            raise BridgeError("Spicetify-Bridge antwortet nicht (Timeout).")
        if msg.get("error"):
            raise BridgeError(str(msg["error"]))
        return msg.get("result")

    async def search(self, query: str, typ: str | None = None):
        """→ {'uri':…, 'name':…} bester Treffer, oder None."""
        return await self._rpc("search", {"query": query, "typ": typ})

    async def now_playing(self):
        """→ {'title','artist','album','playing'} oder None."""
        return await self._rpc("now_playing")

    async def play(self, uri: str):
        return await self._rpc("play", {"uri": uri})

    async def pause(self):
        return await self._rpc("pause")

    async def resume(self):
        return await self._rpc("resume")

    async def next(self):
        return await self._rpc("next")

    async def previous(self):
        return await self._rpc("previous")


# Modul-Singleton — WS-Route und spotify-Skill teilen sich diese Instanz.
BRIDGE = SpotifyBridge()
