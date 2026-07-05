import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import struct
from unittest.mock import MagicMock, patch

import core.vad as vad


def silence_chunk(n_samples: int = 512) -> bytes:
    return struct.pack(f"<{n_samples}h", *([0] * n_samples))


class TestSileroVAD:
    def test_speech_probability_calls_onnx_session(self, tmp_path):
        model_path = tmp_path / "fake.onnx"
        model_path.write_bytes(b"fake")
        with patch.object(vad, "_load_session") as mock_load:
            mock_session = MagicMock()
            mock_session.run.return_value = [[[0.87]]]
            mock_load.return_value = mock_session

            model = vad.SileroVAD(model_path)
            prob = model.speech_probability(silence_chunk())

            assert prob == 0.87
            mock_session.run.assert_called_once()


class FakeVAD:
    """Test-Double: gibt vordefinierte Wahrscheinlichkeiten in Aufrufreihenfolge zurück."""
    def __init__(self, probs: list[float]):
        self._probs = iter(probs)

    def speech_probability(self, pcm_chunk: bytes) -> float:
        return next(self._probs)


class TestVadSegmenter:
    def test_no_segment_while_silent(self):
        fake = FakeVAD([0.1, 0.1, 0.1])
        seg = vad.VadSegmenter(fake, chunk_ms=100)
        for _ in range(3):
            assert seg.process_chunk(silence_chunk()) is None

    def test_emits_segment_after_speech_then_silence(self):
        # 100ms Chunks: 5x Sprache (500ms) dann 9x Stille (900ms, > SILENCE_MS_TO_STOP=800)
        probs = [0.9] * 5 + [0.1] * 9
        fake = FakeVAD(probs)
        seg = vad.VadSegmenter(fake, chunk_ms=100)
        events = [seg.process_chunk(silence_chunk()) for _ in range(len(probs))]
        emitted = [e for e in events if e is not None]
        assert len(emitted) == 1
        assert emitted[0].duration_ms >= 500

    def test_discards_segment_shorter_than_min_duration(self):
        # nur 200ms Sprache (< MIN_SEGMENT_MS=300) dann Stille
        probs = [0.9] * 2 + [0.1] * 9
        fake = FakeVAD(probs)
        seg = vad.VadSegmenter(fake, chunk_ms=100)
        events = [seg.process_chunk(silence_chunk()) for _ in range(len(probs))]
        assert all(e is None for e in events)
