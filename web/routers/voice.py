"""
Voice — API-Router für die Desktop-Sprachsteuerung (Phase 5a Erfassung + Phase 5b
Agent-Anbindung + TTS-Antwort).
Nimmt vom Tauri-Client hochgeladene Audio-Segmente entgegen, transkribiert sie
lokal, prüft ob sie an Alfred gerichtet sind, und lässt bei Adressierung den
echten Agenten (orch.dashboard_respond) antworten — Antwort kommt als Text UND
als synthetisierte Sprache (Piper-TTS, base64) zurück, damit der Desktop-Client
sie direkt abspielen kann.
"""
import base64
import json
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, WebSocket, WebSocketDisconnect

from core import db
from core.voice import transcribe_audio, is_addressed_to_alfred, mark_conversation_active, _conversation_active
from core.voice_stream import VoiceStreamSession
from core.tts import synthesize

log = logging.getLogger("alfred.api")


def build_router(orch=None) -> APIRouter:
    router = APIRouter()

    @router.post("/api/voice/segment")
    async def voice_segment(audio: UploadFile = File(...)):
        suffix = Path(audio.filename or "segment.wav").suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(await audio.read())
            tmp.flush()
            text = await transcribe_audio(tmp.name)

        addressed = await is_addressed_to_alfred(text) if text else False

        reply = None
        audio_b64 = None
        if addressed and orch is not None:
            reply, _trace = await orch.voice_respond(text)
            mark_conversation_active()
            try:
                ogg = await synthesize(reply)
            except Exception as e:
                log.error(f"TTS für Voice-Antwort fehlgeschlagen: {e}")
                ogg = b""
            if ogg:
                audio_b64 = base64.b64encode(ogg).decode("ascii")

        return {"text": text, "addressed": addressed, "reply": reply, "audio_b64": audio_b64}

    @router.get("/api/voice/stream-mode")
    async def voice_stream_mode():
        mode = db.get_setting("voice_stream_mode", "http") or "http"
        return {"mode": mode}

    @router.websocket("/ws/voice/stream")
    async def voice_stream(websocket: WebSocket):
        await websocket.accept()

        from core.vad import SileroVAD, VadSegmenter

        vad_model = SileroVAD(Path(__file__).parent.parent.parent / "data" / "vad" / "silero_vad.onnx")
        segmenter = VadSegmenter(vad_model, chunk_ms=100)
        wakeword_detector = _StubWakeWordDetector()  # Task 6 ersetzt dies durch den echten Detector
        session = VoiceStreamSession(
            vad_segmenter=segmenter,
            wakeword_detector=wakeword_detector,
            conversation_active_fn=_conversation_active,
        )

        muted = False
        try:
            while True:
                message = await websocket.receive()
                if "bytes" in message and message["bytes"] is not None:
                    result = await session.handle_chunk(message["bytes"], muted=muted)
                elif "text" in message and message["text"] is not None:
                    control = json.loads(message["text"])
                    if control.get("type") == "mute":
                        muted = bool(control.get("value", True))
                    continue
                else:
                    continue

                if result is None:
                    continue

                text = result["text"]
                reply = None
                audio_b64 = None
                if orch is not None:
                    reply, _trace = await orch.voice_respond(text)
                    mark_conversation_active()
                    try:
                        ogg = await synthesize(reply)
                    except Exception as e:
                        log.error(f"TTS für Voice-Antwort fehlgeschlagen: {e}")
                        ogg = b""
                    if ogg:
                        audio_b64 = base64.b64encode(ogg).decode("ascii")

                try:
                    await websocket.send_json({
                        "text": text, "addressed": True, "reply": reply, "audio_b64": audio_b64,
                    })
                except (WebSocketDisconnect, RuntimeError) as e:
                    # Client kann zwischen Antwortberechnung und send_json getrennt haben —
                    # Starlette meldet das je nach ASGI-Server als WebSocketDisconnect oder
                    # RuntimeError statt es beim nächsten receive() zu werfen.
                    log.info(f"Voice-WebSocket beim Antwortversand getrennt: {e}")
                    break
        except WebSocketDisconnect:
            log.info("Voice-WebSocket-Verbindung geschlossen")
        except Exception as e:
            log.error(f"Voice-WebSocket-Handler abgebrochen: {e}")

    return router


class _StubWakeWordDetector:
    """Platzhalter bis Task 6 den echten, validierten Mantis-Detector einsetzt."""
    def check(self, pcm_chunk: bytes) -> bool:
        return False
