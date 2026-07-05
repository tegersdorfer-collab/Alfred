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
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, UploadFile, File

from core.voice import transcribe_audio, is_addressed_to_alfred, mark_conversation_active
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
            reply, _trace = await orch.dashboard_respond(text)
            mark_conversation_active()
            try:
                ogg = await synthesize(reply)
            except Exception as e:
                log.error(f"TTS für Voice-Antwort fehlgeschlagen: {e}")
                ogg = b""
            if ogg:
                audio_b64 = base64.b64encode(ogg).decode("ascii")

        return {"text": text, "addressed": addressed, "reply": reply, "audio_b64": audio_b64}

    return router
