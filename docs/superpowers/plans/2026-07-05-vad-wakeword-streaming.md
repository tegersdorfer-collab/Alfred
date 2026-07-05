# Server-Side VAD + Wake-Word Streaming Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace client-side RMS-energy voice-activity detection with server-side Silero VAD, and replace the LLM-based "addressed to Alfred" text check with a custom openWakeWord "Mantis" model, both running on a continuous WebSocket audio stream from the Tauri desktop client.

**Architecture:** New backend modules `core/vad.py` (Silero VAD wrapper) and `core/wakeword.py` (openWakeWord wrapper) run per-connection inside a new `core/voice_stream.py` session manager, fed by a new `/ws/voice/stream` WebSocket route. The existing HTTP `/api/voice/segment` route stays untouched. A `voice_stream_mode` DB setting (default `"http"`) gates which path the frontend uses; `apps/desktop/src/voice-capture-stream.ts` is the new WebSocket-based client capture module, wired in alongside (not replacing) the existing `voice-capture.ts`.

**Tech Stack:** Python `onnxruntime` (already installed, confirmed working on this backend's Python 3.14), Silero VAD ONNX model (public, MIT-licensed, downloaded once), openWakeWord's trained `data/wakeword/mantis.onnx` (from the companion plan `docs/superpowers/plans/2026-07-05-wakeword-training.md` — **must be validated by Timo before Task 6 of this plan**), FastAPI WebSocket, TypeScript `AudioWorkletNode` + native `WebSocket`.

## Global Constraints

- The existing HTTP path (`web/routers/voice.py`'s `/api/voice/segment`, `core/voice.py`'s `is_addressed_to_alfred`) must remain fully functional and untouched throughout this plan — no big-bang cutover (see design spec's "Error handling" section).
- Default `voice_stream_mode` setting is `"http"` — the new streaming path is opt-in until Timo flips it after manual testing.
- Audio format for VAD/wake-word: 16kHz mono 16-bit PCM (what both Silero VAD and openWakeWord expect).
- This plan does **not** rename Alfred to Mantis anywhere — only the wake word the model listens for is "Mantis".
- Task 6 (wiring the trained wake-word model into the live pipeline) must not start until Timo has confirmed via the companion wake-word-training plan that `data/wakeword/mantis.onnx` is validated.

---

### Task 1: Silero VAD wrapper (`core/vad.py`)

**Files:**
- Create: `core/vad.py`
- Create: `data/vad/` (directory for the downloaded ONNX model, gitignored)
- Modify: `.gitignore` (add `data/vad/*.onnx`)
- Modify: `requirements.txt` (add `onnxruntime>=1.17`, `numpy` if not already present)
- Test: `tests/test_vad.py`

**Interfaces:**
- Produces: `class SileroVAD` with `__init__(self, model_path: Path)` and `def speech_probability(self, pcm_chunk: bytes) -> float` (returns 0.0–1.0, the model's raw speech-probability output for one chunk) and `class VadSegmenter` with `def process_chunk(self, pcm_chunk: bytes) -> "SegmentEvent | None"` implementing the speech/silence state machine (start/stop detection, min-duration filtering, preroll buffering) — the same constants as the old JS logic in `apps/desktop/src/voice-capture.ts:8-15` (`SILENCE_MS_TO_STOP=800`, `MIN_SEGMENT_MS=300`, `PREROLL_MS=400`), ported to Python. `SegmentEvent` is a small dataclass: `audio: bytes` (the complete segment's raw PCM, preroll included), `duration_ms: float`.
- Consumed by: Task 3 (`core/voice_stream.py`).

- [ ] **Step 1: Download the Silero VAD ONNX model**

Run:
```bash
mkdir -p data/vad
curl -sL -o data/vad/silero_vad.onnx https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx
```
Expected: `data/vad/silero_vad.onnx` exists and is a few MB. If this URL has moved, check the current path in the `silero-vad` PyPI package's data files instead (`python3 -c "import silero_vad, os; print(os.path.dirname(silero_vad.__file__))"` after `pip install silero-vad`) and use that file directly — do not fabricate a URL, verify it resolves with `curl -sI` first.

- [ ] **Step 2: Add dependency and gitignore entry**

Add to `requirements.txt` (near the other utility deps):
```
onnxruntime>=1.17
```
Add to `.gitignore`:
```
data/vad/*.onnx
```

- [ ] **Step 3: Write the failing test for `speech_probability`**

Create `tests/test_vad.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_vad.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.vad'`

- [ ] **Step 5: Implement `SileroVAD`**

Create `core/vad.py`:
```python
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
    def __init__(self, model_path: Path):
        self._session = _load_session(model_path)
        self._h = np.zeros((2, 1, 64), dtype=np.float32)
        self._c = np.zeros((2, 1, 64), dtype=np.float32)

    def speech_probability(self, pcm_chunk: bytes) -> float:
        n_samples = len(pcm_chunk) // 2
        samples = struct.unpack(f"<{n_samples}h", pcm_chunk)
        audio = np.array(samples, dtype=np.float32) / 32768.0
        inputs = {
            "input": audio[np.newaxis, :],
            "sr": np.array(SAMPLE_RATE, dtype=np.int64),
            "h": self._h,
            "c": self._c,
        }
        outputs = self._session.run(None, inputs)
        return float(np.array(outputs[0]).flatten()[0])


@dataclass
class SegmentEvent:
    audio: bytes
    duration_ms: float
```

Note: the exact ONNX input/output names (`input`/`sr`/`h`/`c`) depend on the specific Silero VAD export version downloaded in Step 1 — inspect the actual model with `python3 -c "import onnxruntime as ort; s = ort.InferenceSession('data/vad/silero_vad.onnx'); print([i.name for i in s.get_inputs()], [o.name for o in s.get_outputs()])"` and adjust the `inputs` dict keys in `speech_probability` to match before running Step 6.

- [ ] **Step 6: Run test to verify it passes**

Run: `python3 -m pytest tests/test_vad.py -v`
Expected: PASS

- [ ] **Step 7: Write the failing test for `VadSegmenter`'s state machine**

Append to `tests/test_vad.py`:
```python
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
```

- [ ] **Step 8: Run test to verify it fails**

Run: `python3 -m pytest tests/test_vad.py -v -k VadSegmenter`
Expected: FAIL with `AttributeError: module 'core.vad' has no attribute 'VadSegmenter'`

- [ ] **Step 9: Implement `VadSegmenter`**

Append to `core/vad.py`:
```python
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
```

- [ ] **Step 10: Run test to verify it passes**

Run: `python3 -m pytest tests/test_vad.py -v`
Expected: PASS (all tests)

- [ ] **Step 11: Commit**

```bash
git add core/vad.py tests/test_vad.py requirements.txt .gitignore
git commit -m "feat(vad): add server-side Silero VAD segmenter"
```

---

### Task 2: openWakeWord wrapper (`core/wakeword.py`)

**Files:**
- Create: `core/wakeword.py`
- Modify: `requirements.txt` (add `openwakeword>=0.6.0`)
- Test: `tests/test_wakeword.py`

**Interfaces:**
- Produces: `class WakeWordDetector` with `__init__(self, model_path: Path, threshold: float = 0.5)` and `def check(self, pcm_chunk: bytes) -> bool` (True if "Mantis" score crosses threshold on this chunk).
- Consumed by: Task 3 (`core/voice_stream.py`).
- Depends on: `data/wakeword/mantis.onnx` existing and validated (companion plan) — but this task's *tests* mock the model entirely, so this task can be implemented and tested independently of that plan's completion. Only real-world use requires the trained model to exist.

- [ ] **Step 1: Add dependency**

Add to `requirements.txt`:
```
openwakeword>=0.6.0
```
Run: `pip3 install openwakeword>=0.6.0` (or the repo's actual install command — check for a `Makefile`/`setup.sh` target first with `grep -rn "pip install -r requirements" . --include="*.sh" --include="Makefile" | grep -v venv`) and confirm import: `python3 -c "import openwakeword; print('ok')"`

- [ ] **Step 2: Write the failing test**

Create `tests/test_wakeword.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

import core.wakeword as wakeword


class TestWakeWordDetector:
    def test_check_true_when_score_above_threshold(self, tmp_path):
        model_path = tmp_path / "mantis.onnx"
        model_path.write_bytes(b"fake")
        with patch.object(wakeword, "_load_model") as mock_load:
            mock_model = MagicMock()
            mock_model.predict.return_value = {"mantis": 0.8}
            mock_load.return_value = mock_model

            detector = wakeword.WakeWordDetector(model_path, threshold=0.5)
            assert detector.check(b"\x00\x00" * 512) is True

    def test_check_false_when_score_below_threshold(self, tmp_path):
        model_path = tmp_path / "mantis.onnx"
        model_path.write_bytes(b"fake")
        with patch.object(wakeword, "_load_model") as mock_load:
            mock_model = MagicMock()
            mock_model.predict.return_value = {"mantis": 0.2}
            mock_load.return_value = mock_model

            detector = wakeword.WakeWordDetector(model_path, threshold=0.5)
            assert detector.check(b"\x00\x00" * 512) is False
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_wakeword.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.wakeword'`

- [ ] **Step 4: Implement**

Create `core/wakeword.py`:
```python
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
```

Note: `prediction` dict keys depend on the actual filename/label baked into the trained model from the companion plan — inspect a real `data/wakeword/mantis.onnx` once available (`_load_model(...).predict(...)` printed keys) and adjust `MODEL_KEY`/lookup if it's not simply `"mantis"`.

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_wakeword.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add core/wakeword.py tests/test_wakeword.py requirements.txt
git commit -m "feat(wakeword): add openWakeWord detector wrapper"
```

---

### Task 3: Voice-stream session manager (`core/voice_stream.py`)

**Files:**
- Create: `core/voice_stream.py`
- Test: `tests/test_voice_stream.py`

**Interfaces:**
- Consumes: `core.vad.VadSegmenter`/`SileroVAD` (Task 1), `core.wakeword.WakeWordDetector` (Task 2), `core.voice.transcribe_audio`/`mark_conversation_active` (existing, `core/voice.py`).
- Produces: `class VoiceStreamSession` with `def __init__(self, vad_segmenter, wakeword_detector, conversation_active_fn: Callable[[], bool])` and `async def handle_chunk(self, pcm_chunk: bytes, muted: bool) -> dict | None` — returns a dict shaped like the existing HTTP response (`{"text", "addressed", "audio_bytes"}` — note: raw bytes here, not yet base64; that encoding happens in Task 4's WebSocket route) when a complete segment resolves to a transcribed, addressed utterance; `None` otherwise. Also tracks whether the wake word fired within the current in-progress segment.
- Consumed by: Task 4 (`/ws/voice/stream` route).

- [ ] **Step 1: Write the failing test**

Create `tests/test_voice_stream.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from unittest.mock import AsyncMock, MagicMock

from core.voice_stream import VoiceStreamSession
from core.vad import SegmentEvent


def make_session(segment_events, wake_hits, conversation_active=False):
    fake_segmenter = MagicMock()
    fake_segmenter.process_chunk.side_effect = segment_events
    fake_wakeword = MagicMock()
    fake_wakeword.check.side_effect = wake_hits
    return VoiceStreamSession(
        vad_segmenter=fake_segmenter,
        wakeword_detector=fake_wakeword,
        conversation_active_fn=lambda: conversation_active,
    )


class TestVoiceStreamSession:
    def test_ignores_muted_chunks(self):
        session = make_session(segment_events=[], wake_hits=[])
        result = asyncio.run(session.handle_chunk(b"\x00\x00", muted=True))
        assert result is None

    def test_no_result_while_segment_incomplete(self):
        session = make_session(segment_events=[None], wake_hits=[False])
        result = asyncio.run(session.handle_chunk(b"\x00\x00", muted=False))
        assert result is None

    def test_segment_without_wakeword_or_active_conversation_is_dropped(self):
        segment = SegmentEvent(audio=b"AUDIO", duration_ms=500)
        session = make_session(segment_events=[segment], wake_hits=[False], conversation_active=False)
        result = asyncio.run(session.handle_chunk(b"\x00\x00", muted=False))
        assert result is None

    def test_segment_with_wakeword_triggers_transcription(self, monkeypatch):
        import core.voice_stream as vs
        segment = SegmentEvent(audio=b"AUDIO", duration_ms=500)
        session = make_session(segment_events=[segment], wake_hits=[True], conversation_active=False)
        monkeypatch.setattr(vs, "transcribe_pcm", AsyncMock(return_value="hallo mantis"))

        result = asyncio.run(session.handle_chunk(b"\x00\x00", muted=False))

        assert result == {"text": "hallo mantis", "addressed": True}

    def test_segment_during_active_conversation_triggers_even_without_wakeword(self, monkeypatch):
        import core.voice_stream as vs
        segment = SegmentEvent(audio=b"AUDIO", duration_ms=500)
        session = make_session(segment_events=[segment], wake_hits=[False], conversation_active=True)
        monkeypatch.setattr(vs, "transcribe_pcm", AsyncMock(return_value="und morgen?"))

        result = asyncio.run(session.handle_chunk(b"\x00\x00", muted=False))

        assert result == {"text": "und morgen?", "addressed": True}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_voice_stream.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.voice_stream'`

- [ ] **Step 3: Implement**

Create `core/voice_stream.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_voice_stream.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add core/voice_stream.py tests/test_voice_stream.py
git commit -m "feat(voice-stream): add VAD+wakeword session manager for streaming pipeline"
```

---

### Task 4: `voice_stream_mode` setting + WebSocket route (model-independent scaffolding)

**Files:**
- Modify: `web/routers/voice.py`
- Test: `tests/test_voice_router_stream.py`

**Interfaces:**
- Consumes: `core.db.get_setting`/`set_setting` (existing, `core/db.py:530-543`), `core.voice_stream.VoiceStreamSession` (Task 3).
- Produces: `GET /api/voice/stream-mode` (returns `{"mode": "http" | "websocket"}`) and `WS /ws/voice/stream` in the same router's `build_router`.

This task wires the route using a **stub** wake-word detector (always returns `False`) since the real trained model isn't required to test the route's plumbing — Task 6 swaps in the real model once validated.

- [ ] **Step 1: Write the failing test for the mode endpoint**

Create `tests/test_voice_router_stream.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from unittest.mock import patch

from web.routers.voice import build_router
from fastapi import FastAPI


def make_client():
    app = FastAPI()
    app.include_router(build_router(orch=None))
    return TestClient(app)


class TestStreamModeEndpoint:
    def test_defaults_to_http(self):
        client = make_client()
        with patch("web.routers.voice.db.get_setting", return_value=None):
            resp = client.get("/api/voice/stream-mode")
        assert resp.json() == {"mode": "http"}

    def test_returns_websocket_when_set(self):
        client = make_client()
        with patch("web.routers.voice.db.get_setting", return_value="websocket"):
            resp = client.get("/api/voice/stream-mode")
        assert resp.json() == {"mode": "websocket"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_voice_router_stream.py -v`
Expected: FAIL (404, route doesn't exist yet, or `AttributeError` for missing `db` import in the module)

- [ ] **Step 3: Add the mode endpoint and WebSocket route**

Modify `web/routers/voice.py` — add these imports at the top (alongside the existing ones):
```python
from fastapi import APIRouter, UploadFile, File, WebSocket, WebSocketDisconnect

from core import db
from core.voice_stream import VoiceStreamSession
from core.voice import _conversation_active  # neue kleine Hilfsfunktion, siehe Schritt 4
```

Add inside `build_router`, after the existing `/api/voice/segment` route:
```python
    @router.get("/api/voice/stream-mode")
    async def voice_stream_mode():
        mode = db.get_setting("voice_stream_mode", "http")
        return {"mode": mode}

    @router.websocket("/ws/voice/stream")
    async def voice_stream(websocket: WebSocket):
        await websocket.accept()

        from core.vad import SileroVAD, VadSegmenter
        from pathlib import Path

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
                    import json
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
                    from core.voice import mark_conversation_active
                    mark_conversation_active()
                    try:
                        ogg = await synthesize(reply)
                    except Exception as e:
                        log.error(f"TTS für Voice-Antwort fehlgeschlagen: {e}")
                        ogg = b""
                    if ogg:
                        audio_b64 = base64.b64encode(ogg).decode("ascii")

                await websocket.send_json({
                    "text": text, "addressed": True, "reply": reply, "audio_b64": audio_b64,
                })
        except WebSocketDisconnect:
            log.info("Voice-WebSocket-Verbindung geschlossen")


class _StubWakeWordDetector:
    """Platzhalter bis Task 6 den echten, validierten Mantis-Detector einsetzt."""
    def check(self, pcm_chunk: bytes) -> bool:
        return False
```

- [ ] **Step 4: Add `_conversation_active` helper to `core/voice.py`**

The existing module only exposes `mark_conversation_active()` (sets the deadline) — add a matching getter. In `core/voice.py`, after the existing `mark_conversation_active` function (around line 30), add:
```python
def _conversation_active() -> bool:
    return time.monotonic() < _conversation_active_until
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_voice_router_stream.py -v`
Expected: PASS

- [ ] **Step 6: Manual smoke test of the WebSocket route**

Restart the backend (`kill -9 $(pgrep -f "python.*main.py"); launchctl kickstart -k gui/501/com.alfred.assistant; sleep 5; curl -s http://localhost:7779/health`), then:
```bash
python3 -c "
import asyncio, websockets

async def main():
    async with websockets.connect('ws://localhost:7779/ws/voice/stream') as ws:
        await ws.send(b'\x00\x00' * 1600)  # 100ms Stille bei 16kHz
        print('sent silence chunk, connection alive')

asyncio.run(main())
"
```
Expected: no exception, connection stays open (stub wakeword always returns False, so nothing is transcribed yet — this just confirms the route doesn't crash on real traffic).

- [ ] **Step 7: Commit**

```bash
git add web/routers/voice.py core/voice.py tests/test_voice_router_stream.py
git commit -m "feat(voice-stream): add /ws/voice/stream route with stub wakeword detector"
```

---

### Task 5: Frontend streaming capture (`voice-capture-stream.ts`)

**Files:**
- Create: `apps/desktop/src/voice-capture-stream.ts`
- Create: `apps/desktop/public/pcm-worklet.js` (AudioWorkletProcessor — plain JS, runs in the audio rendering thread, can't be TypeScript-compiled inline)
- Test: `apps/desktop/src/voice-capture-stream.test.ts`
- Modify: `apps/desktop/src/main.ts` (call the new module instead of/alongside `startVoiceCapture`, gated by the `/api/voice/stream-mode` endpoint from Task 4)

**Interfaces:**
- Produces: `startVoiceCaptureStream(baseUrl: string, onSegment: (result: VoiceSegmentResult) => void, wsFactory?: (url: string) => WebSocket) -> () => void` — same shape as the existing `startVoiceCapture` in `voice-capture.ts:25-28`, reusing its exported `VoiceSegmentResult` type.
- Consumes: nothing from other new-plan files directly (frontend and backend are decoupled by the WebSocket wire protocol: binary PCM frames sent, JSON `segment_result` messages received).

- [ ] **Step 1: Write the AudioWorklet processor (plain JS, no test — runs in a separate thread jsdom can't execute)**

Create `apps/desktop/public/pcm-worklet.js`:
```javascript
class PCMWorkletProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (input.length > 0) {
      const channelData = input[0];
      const pcm16 = new Int16Array(channelData.length);
      for (let i = 0; i < channelData.length; i++) {
        const s = Math.max(-1, Math.min(1, channelData[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
    }
    return true;
  }
}
registerProcessor('pcm-worklet', PCMWorkletProcessor);
```

- [ ] **Step 2: Write the failing test for `startVoiceCaptureStream`**

Create `apps/desktop/src/voice-capture-stream.test.ts`:
```typescript
import { describe, it, expect, vi } from 'vitest';
import { startVoiceCaptureStream } from './voice-capture-stream';

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  sent: unknown[] = [];
  onmessage: ((ev: { data: string }) => void) | null = null;
  onopen: (() => void) | null = null;
  readyState = 1; // OPEN
  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
  send(data: unknown) {
    this.sent.push(data);
  }
  close() {}
}

describe('startVoiceCaptureStream', () => {
  it('opens a WebSocket to the stream endpoint', () => {
    FakeWebSocket.instances = [];
    const onSegment = vi.fn();
    const stop = startVoiceCaptureStream(
      'http://localhost:7779',
      onSegment,
      (url) => new FakeWebSocket(url) as unknown as WebSocket,
    );
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.instances[0].url).toBe('ws://localhost:7779/ws/voice/stream');
    stop();
  });

  it('forwards segment_result messages to onSegment', () => {
    FakeWebSocket.instances = [];
    const onSegment = vi.fn();
    startVoiceCaptureStream(
      'http://localhost:7779',
      onSegment,
      (url) => new FakeWebSocket(url) as unknown as WebSocket,
    );
    const ws = FakeWebSocket.instances[0];
    const payload = { text: 'hallo', addressed: true, reply: 'hi', audio_b64: null };
    ws.onmessage?.({ data: JSON.stringify(payload) });
    expect(onSegment).toHaveBeenCalledWith(payload);
  });

  it('sends a mute=true control message while a reply plays', () => {
    FakeWebSocket.instances = [];
    const originalAudio = globalThis.Audio;
    // @ts-expect-error - Test-Double, kein vollständiges HTMLAudioElement nötig
    globalThis.Audio = class {
      onended: (() => void) | null = null;
      onerror: (() => void) | null = null;
      play() {
        return Promise.resolve();
      }
      pause() {}
    };
    try {
      const onSegment = vi.fn();
      startVoiceCaptureStream(
        'http://localhost:7779',
        onSegment,
        (url) => new FakeWebSocket(url) as unknown as WebSocket,
      );
      const ws = FakeWebSocket.instances[0];
      const payload = { text: 'hallo', addressed: true, reply: 'hi', audio_b64: 'BASE64AUDIO' };
      ws.onmessage?.({ data: JSON.stringify(payload) });
      expect(ws.sent).toEqual([JSON.stringify({ type: 'mute', value: true })]);
    } finally {
      globalThis.Audio = originalAudio;
    }
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/voice-capture-stream.test.ts`
Expected: FAIL with `Cannot find module './voice-capture-stream'`

- [ ] **Step 4: Implement `voice-capture-stream.ts`**

Create `apps/desktop/src/voice-capture-stream.ts`:
```typescript
import type { VoiceSegmentResult } from './voice-capture';

function wsUrlFor(baseUrl: string): string {
  return baseUrl.replace(/^http/, 'ws') + '/ws/voice/stream';
}

export function startVoiceCaptureStream(
  baseUrl: string,
  onSegment: (result: VoiceSegmentResult) => void,
  wsFactory: (url: string) => WebSocket = (url) => new WebSocket(url),
): () => void {
  let stopped = false;
  let stream: MediaStream | null = null;
  let audioCtx: AudioContext | null = null;
  let workletNode: AudioWorkletNode | null = null;
  const ws = wsFactory(wsUrlFor(baseUrl));
  let currentReplyAudio: HTMLAudioElement | null = null;

  function sendMute(value: boolean): void {
    if (ws.readyState === 1) {
      ws.send(JSON.stringify({ type: 'mute', value }));
    }
  }

  function playReplyAudio(audioB64: string): void {
    try {
      if (currentReplyAudio) {
        currentReplyAudio.pause();
        currentReplyAudio.onended = null;
      }
      const audio = new Audio(`data:audio/ogg;base64,${audioB64}`);
      currentReplyAudio = audio;
      sendMute(true);
      // Solange Alfred spricht: Server-seitige VAD/Wake-Word-Auswertung pausieren
      // (per Mute-Flag), sonst hört das Mikrofon Alfreds eigene Stimme und löst
      // ein neues Segment aus (Echo-Vermeidung, siehe alte voice-capture.ts).
      const stopPlayingFlag = () => sendMute(false);
      audio.onended = stopPlayingFlag;
      audio.onerror = stopPlayingFlag;
      audio.play().catch(stopPlayingFlag);
    } catch {
      sendMute(false);
    }
  }

  ws.onmessage = (ev: { data: string }) => {
    try {
      const result = JSON.parse(ev.data) as VoiceSegmentResult;
      if (result.audio_b64) playReplyAudio(result.audio_b64);
      onSegment(result);
    } catch {
      // ungültige Nachricht ignorieren, kein Absturz
    }
  };

  navigator.mediaDevices
    .getUserMedia({ audio: true })
    .then(async (mediaStream) => {
      if (stopped) {
        mediaStream.getTracks().forEach((t) => t.stop());
        return;
      }
      stream = mediaStream;
      audioCtx = new AudioContext({ sampleRate: 16000 });
      await audioCtx.audioWorklet.addModule('/pcm-worklet.js');
      const source = audioCtx.createMediaStreamSource(stream);
      workletNode = new AudioWorkletNode(audioCtx, 'pcm-worklet');
      workletNode.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
        if (!stopped && ws.readyState === 1) {
          ws.send(event.data);
        }
      };
      source.connect(workletNode);
    })
    .catch(() => {
      // Mikrofon-Zugriff verweigert/nicht verfügbar — Voice-Capture bleibt inaktiv
    });

  return () => {
    stopped = true;
    if (workletNode) workletNode.port.onmessage = null;
    if (stream) stream.getTracks().forEach((t) => t.stop());
    if (audioCtx) audioCtx.close();
    ws.close();
  };
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/voice-capture-stream.test.ts`
Expected: PASS (both tests)

- [ ] **Step 6: Wire mode selection into `main.ts`**

Read the current call site: `grep -n "startVoiceCapture" apps/desktop/src/main.ts`. Replace the direct call with a mode check, following this shape (adapt to the exact surrounding code found by the grep):
```typescript
import { startVoiceCaptureStream } from './voice-capture-stream';

async function initVoiceCapture(baseUrl: string, onSegment: (r: VoiceSegmentResult) => void) {
  const res = await fetch(`${baseUrl}/api/voice/stream-mode`);
  const { mode } = await res.json();
  return mode === 'websocket'
    ? startVoiceCaptureStream(baseUrl, onSegment)
    : startVoiceCapture(baseUrl, onSegment);
}
```
Call `initVoiceCapture` wherever `startVoiceCapture` was previously called directly.

- [ ] **Step 7: Run the full frontend test suite to check nothing else broke**

Run: `cd apps/desktop && npx vitest run`
Expected: all tests PASS, including the pre-existing `voice-capture-calibration.test.ts` (unaffected — old module untouched) and `main.test.ts` (may need a small mock update for the new `fetch` call in `initVoiceCapture`; if it fails, add a `fetch` mock returning `{mode: "http"}` to keep existing test behavior).

- [ ] **Step 8: Commit**

```bash
git add apps/desktop/src/voice-capture-stream.ts apps/desktop/src/voice-capture-stream.test.ts apps/desktop/public/pcm-worklet.js apps/desktop/src/main.ts
git commit -m "feat(voice-stream): add WebSocket-based capture client, mode-gated in main.ts"
```

---

### Task 6: Wire in the validated wake-word model (blocked on companion plan)

**Precondition:** Timo has confirmed (per `docs/superpowers/plans/2026-07-05-wakeword-training.md`, Task 5) that `data/wakeword/mantis.onnx` performs acceptably. Do not start this task before that confirmation.

**Files:**
- Modify: `web/routers/voice.py` (replace `_StubWakeWordDetector` with the real one)
- Test: extend `tests/test_voice_router_stream.py`

**Interfaces:**
- Consumes: `core.wakeword.WakeWordDetector` (Task 2), `data/wakeword/mantis.onnx` (companion plan's output).

- [ ] **Step 1: Replace the stub in the WebSocket route**

In `web/routers/voice.py`, inside the `voice_stream` handler from Task 4, replace:
```python
        wakeword_detector = _StubWakeWordDetector()  # Task 6 ersetzt dies durch den echten Detector
```
with:
```python
        from core.wakeword import WakeWordDetector
        wakeword_path = Path(__file__).parent.parent.parent / "data" / "wakeword" / "mantis.onnx"
        wakeword_detector = WakeWordDetector(wakeword_path)
```
Remove the now-unused `_StubWakeWordDetector` class.

- [ ] **Step 2: Manual end-to-end test**

Run: `data/wakeword/venv/bin/python scripts/e2e_voice_latency_test.py --mode websocket` (extend this existing script with a `--mode` flag if it doesn't already support one — check its current CLI args first with `python3 scripts/e2e_voice_latency_test.py --help`). Say "Mantis" followed by a question via the desktop app with `voice_stream_mode` set to `"websocket"` (`core.db.set_setting("voice_stream_mode", "websocket")` from a Python shell against the running backend). Confirm a spoken reply comes back and latency is comparable to or better than the existing HTTP path's numbers from the prior handoff (~5.5–12s warm).

- [ ] **Step 3: Commit**

```bash
git add web/routers/voice.py
git commit -m "feat(wakeword): wire validated Mantis model into streaming voice pipeline"
```

- [ ] **Step 4: Flip the setting once Timo confirms it works well in real use**

Run (only after Timo's go-ahead): `python3 -c "from core import db; db.set_setting('voice_stream_mode', 'websocket')"`
