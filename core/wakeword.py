"""openWakeWord-Wrapper — erkennt das Wake-Word 'Mantis' im laufenden Audiostrom,
ersetzt für die Erstaktivierung den LLM-basierten is_addressed_to_alfred()-Check
aus core/voice.py (siehe docs/superpowers/specs/2026-07-05-vad-wakeword-streaming-design.md)."""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

MODEL_KEY = "mantis"


def _load_model(model_path: Path):
    from openwakeword.model import Model
    return Model(wakeword_models=[str(model_path)])


class WakeWordDetector:
    def __init__(self, model_path: Path, threshold: float = 0.5):
        self._model = _load_model(model_path)
        self._threshold = threshold

    def check(self, pcm_chunk: bytes) -> bool:
        n_samples = len(pcm_chunk) // 2
        samples = np.array(struct.unpack(f"<{n_samples}h", pcm_chunk), dtype=np.int16)
        prediction = self._model.predict(samples)
        score = max(prediction.values()) if prediction else 0.0
        return score >= self._threshold
