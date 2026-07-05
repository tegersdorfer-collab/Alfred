"""Silero VAD — Sprachaktivitätserkennung server-seitig, ersetzt die frühere
RMS-Schwelle in apps/desktop/src/voice-capture.ts (siehe
docs/superpowers/specs/2026-07-05-vad-wakeword-streaming-design.md)."""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
SILENCE_MS_TO_STOP = 800
MIN_SEGMENT_MS = 300
PREROLL_MS = 400


def _load_session(model_path: Path):
    import onnxruntime as ort
    return ort.InferenceSession(str(model_path))


class SileroVAD:
    """Wraps the Silero VAD ONNX model. The public (recent) export exposes a
    single recurrent `state` tensor of shape (2, batch, 128) rather than the
    separate LSTM `h`/`c` tensors used by older exports — verified empirically
    via `s.get_inputs()` / `s.get_outputs()` on the downloaded model:
      inputs:  input [None, None] float32, state [2, None, 128] float32, sr [] int64
      outputs: output [None, 1] float32, stateN [None, None, None] float32
    """

    def __init__(self, model_path: Path):
        self._session = _load_session(model_path)
        self._state = np.zeros((2, 1, 128), dtype=np.float32)

    def speech_probability(self, pcm_chunk: bytes) -> float:
        n_samples = len(pcm_chunk) // 2
        samples = struct.unpack(f"<{n_samples}h", pcm_chunk)
        audio = np.array(samples, dtype=np.float32) / 32768.0
        inputs = {
            "input": audio[np.newaxis, :],
            "sr": np.array(SAMPLE_RATE, dtype=np.int64),
            "state": self._state,
        }
        outputs = self._session.run(None, inputs)
        if len(outputs) > 1:
            self._state = np.array(outputs[1], dtype=np.float32)
        return float(np.array(outputs[0]).flatten()[0])


@dataclass
class SegmentEvent:
    audio: bytes
    duration_ms: float


class VadSegmenter:
    """Zustandsautomat: sammelt PCM-Chunks, erkennt Sprechbeginn/-ende per VAD-
    Wahrscheinlichkeit, liefert fertige Segmente (inkl. Preroll) zurück. Portierte
    Logik von apps/desktop/src/voice-capture.ts's alter tick()-Funktion."""

    SPEECH_THRESHOLD = 0.5

    def __init__(self, vad_model: SileroVAD, chunk_ms: float):
        self._vad = vad_model
        self._chunk_ms = chunk_ms
        self._speaking = False
        self._silence_ms = 0.0
        self._speech_ms = 0.0
        self._buffer: list[bytes] = []
        self._preroll: list[bytes] = []

    def process_chunk(self, pcm_chunk: bytes) -> SegmentEvent | None:
        prob = self._vad.speech_probability(pcm_chunk)
        is_speech = prob >= self.SPEECH_THRESHOLD

        if is_speech:
            self._silence_ms = 0.0
            if not self._speaking:
                self._speaking = True
                self._speech_ms = 0.0
                self._buffer = list(self._preroll)
            self._speech_ms += self._chunk_ms
            self._buffer.append(pcm_chunk)
        elif self._speaking:
            self._buffer.append(pcm_chunk)
            self._silence_ms += self._chunk_ms
            if self._silence_ms >= SILENCE_MS_TO_STOP:
                self._speaking = False
                total_ms = self._speech_ms + self._silence_ms
                segment = b"".join(self._buffer)
                self._buffer = []
                if self._speech_ms >= MIN_SEGMENT_MS:
                    return SegmentEvent(audio=segment, duration_ms=total_ms)
                return None

        preroll_chunks = max(1, int(PREROLL_MS / self._chunk_ms))
        self._preroll.append(pcm_chunk)
        self._preroll = self._preroll[-preroll_chunks:]
        return None
