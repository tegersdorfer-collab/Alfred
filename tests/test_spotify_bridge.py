"""Tests für die Spicetify-Bridge (tools/spotify/bridge.py) — ohne echten Socket.

Der Transport (_send) wird gemockt und simuliert die Extension-Antwort, sodass
die Request/Response-Korrelation, Fehler und Timeouts geprüft werden.
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.spotify.bridge import SpotifyBridge, BridgeError


def _connected(reply_for):
    """Bridge, die 'verbunden' ist und deren _send die Extension-Antwort
    simuliert. reply_for(method, params) -> dict (result oder error)."""
    b = SpotifyBridge()
    b._ws = object()  # als verbunden markieren

    async def fake_send(text):
        msg = json.loads(text)
        reply = reply_for(msg["method"], msg["params"])
        await b.on_message(json.dumps({"id": msg["id"], **reply}))
    b._send = fake_send
    return b


def test_not_connected_raises():
    b = SpotifyBridge()
    assert b.is_connected() is False
    try:
        asyncio.run(b.search("kids"))
        assert False, "sollte werfen"
    except BridgeError as e:
        assert "verbunden" in str(e).lower()


def test_search_roundtrip():
    b = _connected(lambda m, p: {"result": {"uri": "spotify:track:x", "name": "Kids — MGMT"}})
    res = asyncio.run(b.search("kids"))
    assert res == {"uri": "spotify:track:x", "name": "Kids — MGMT"}


def test_params_are_forwarded():
    seen = {}

    def reply(method, params):
        seen["method"] = method
        seen["params"] = params
        return {"result": None}
    b = _connected(reply)
    asyncio.run(b.search("focus", typ="playlist"))
    assert seen["method"] == "search"
    assert seen["params"] == {"query": "focus", "typ": "playlist"}


def test_error_reply_raises():
    b = _connected(lambda m, p: {"error": "Spotify-API-Fehler"})
    try:
        asyncio.run(b.now_playing())
        assert False, "sollte werfen"
    except BridgeError as e:
        assert "spotify-api-fehler" in str(e).lower()


def test_timeout_raises():
    b = SpotifyBridge()
    b._ws = object()

    async def silent_send(text):
        pass  # keine Antwort → Timeout
    b._send = silent_send

    async def run():
        return await b._rpc("now_playing", timeout=0.05)
    try:
        asyncio.run(run())
        assert False, "sollte timeouten"
    except BridgeError as e:
        assert "timeout" in str(e).lower()


def test_unregister_fails_pending():
    b = SpotifyBridge()
    b._ws = ws = object()

    async def run():
        # Anfrage starten, die nie beantwortet wird, dann Verbindung trennen
        task = asyncio.ensure_future(b._rpc("play", {"uri": "x"}, timeout=2))
        await asyncio.sleep(0.01)
        await b.unregister(ws)
        return await task

    async def silent_send(text):
        pass
    b._send = silent_send
    try:
        asyncio.run(run())
        assert False, "sollte werfen"
    except BridgeError as e:
        assert "getrennt" in str(e).lower()
