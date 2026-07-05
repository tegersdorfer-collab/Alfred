"""Pro-Verbindung Session-Manager für /ws/voice/stream: kombiniert Silero-VAD-
Segmentierung mit openWakeWord-Erkennung. Ersetzt für den WebSocket-Pfad sowohl
die client-seitige RMS-Erkennung als auch den LLM-basierten
is_addressed_to_alfred()-Text-Check aus core/voice.py (siehe
docs/superpowers/specs/2026-07-05-vad-wakeword-streaming-design.md)."""
from __future__ import annotations

import tempfile
import wave
from pathlib import Path
from typing import Callable

from core.vad import VadSegmenter

SAMPLE_RATE = 16000


async def transcribe_pcm(pcm_audio: bytes) -> str:
    """Schreibt rohes PCM als WAV und transkribiert über die bestehende
    Whisper-Pipeline (core.voice.transcribe_audio erwartet einen Dateipfad)."""
    from core.voice import transcribe_audio

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
        with wave.open(tmp.name, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(pcm_audio)
        return await transcribe_audio(tmp.name)


class VoiceStreamSession:
    def __init__(
        self,
        vad_segmenter: VadSegmenter,
        wakeword_detector,
        conversation_active_fn: Callable[[], bool],
    ):
        self._segmenter = vad_segmenter
        self._wakeword = wakeword_detector
        self._conversation_active_fn = conversation_active_fn
        self._wake_fired_in_segment = False

    async def handle_chunk(self, pcm_chunk: bytes, muted: bool) -> dict | None:
        if muted:
            return None

        if self._wakeword.check(pcm_chunk):
            self._wake_fired_in_segment = True

        segment = self._segmenter.process_chunk(pcm_chunk)
        if segment is None:
            return None

        wake_fired = self._wake_fired_in_segment
        self._wake_fired_in_segment = False

        if not wake_fired and not self._conversation_active_fn():
            return None

        text = await transcribe_pcm(segment.audio)
        return {"text": text, "addressed": True}
