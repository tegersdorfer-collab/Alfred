"""openWakeWord-Wrapper — erkennt das Wake-Word 'Mantis' im laufenden Audiostrom,
ersetzt für die Erstaktivierung den LLM-basierten is_addressed_to_alfred()-Check
aus core/voice.py (siehe docs/superpowers/specs/2026-07-05-vad-wakeword-streaming-design.md)."""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

MODEL_KEY = "mantis"

# openWakeWord's documented standard chunk size is 1280 samples (80ms @
# 16kHz) — see openwakeword.model.Model.predict docstring ("Ideally should be
# multiples of 80 ms (1280 samples)"). Smaller/larger inputs are technically
# accepted upstream but add internal buffering/latency, so callers in this
# codebase are required to pre-buffer to this exact size (see
# core/voice_stream.py::VoiceStreamSession) for predictable, testable timing.
WAKEWORD_REQUIRED_SAMPLES = 1280


def _load_model(model_path: Path):
    from openwakeword.model import Model
    return Model(wakeword_models=[str(model_path)])


class WakeWordDetector:
    def __init__(self, model_path: Path, threshold: float = 0.5):
        self._model = _load_model(model_path)
        self._threshold = threshold

    def check(self, pcm_chunk: bytes) -> bool:
        n_samples = len(pcm_chunk) // 2
        if n_samples != WAKEWORD_REQUIRED_SAMPLES:
            raise ValueError(
                f"WakeWordDetector.check requires exactly "
                f"{WAKEWORD_REQUIRED_SAMPLES} samples ({WAKEWORD_REQUIRED_SAMPLES * 2} bytes), "
                f"got {n_samples} samples ({len(pcm_chunk)} bytes). Callers must "
                f"buffer raw audio to this frame size before calling (see "
                f"core/voice_stream.py::VoiceStreamSession)."
            )
        samples = np.array(struct.unpack(f"<{n_samples}h", pcm_chunk), dtype=np.int16)
        prediction = self._model.predict(samples)
        score = max(prediction.values()) if prediction else 0.0
        return score >= self._threshold
