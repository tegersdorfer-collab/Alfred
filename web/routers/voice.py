"""
Voice — API-Router für den Sprach-Erfassungs-Messaufbau (Phase 5a).
Nimmt vom Tauri-Client hochgeladene Audio-Segmente entgegen, transkribiert sie
lokal und prüft ob sie an Alfred gerichtet sind. KEINE Agent-Anbindung —
reine Mess-/Beobachtungs-Infrastruktur, siehe Plan-Constraints.
"""
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, UploadFile, File

from core.voice import transcribe_audio, is_addressed_to_alfred

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
        return {"text": text, "addressed": addressed}

    return router
