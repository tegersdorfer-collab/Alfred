# Voice-Pipeline: Server-Side VAD + Custom Wake-Word ("Mantis") — Design

**Date:** 2026-07-05
**Status:** Approved by Timo, ready for planning

## Context

Follow-up to the voice-pipeline overhaul (see `ROADMAP.md`'s "Voice-Pipeline-Latenz-Untersuchung"
section and the 2026-07-05 handoff). The current client-side voice capture
(`apps/desktop/src/voice-capture.ts`) uses a hand-rolled RMS-energy threshold to detect
speech segments, and there is no wake-word — "addressed to Alfred" is decided purely by
an LLM text check (`core/voice.py::is_addressed_to_alfred`) after transcription. Both are
on the roadmap to be replaced with Silero VAD and openWakeWord respectively.

Note: renaming the assistant from "Alfred" to "Mantis" is explicitly **out of scope** for
this project. Only the wake-word model is trained to respond to the word "Mantis" — no
code, persona, or documentation renaming happens here. That is a separate future project.

## Goals

1. Replace the client-side RMS-energy VAD with Silero VAD, running server-side on a
   continuous raw-audio stream.
2. Add wake-word detection via a custom-trained openWakeWord model for "Mantis",
   replacing the LLM-based `is_addressed_to_alfred` text check as the primary
   activation trigger.
3. Keep the existing HTTP segment-upload path (`/api/voice/segment`) untouched and
   active until the new path is validated — no big-bang cutover.

## Non-goals

- Renaming Alfred to Mantis anywhere in code, persona, or docs.
- Full incremental audio streaming of the *reply* (TTS still returns as one blob per
  the existing `audio_b64` contract) — that's the separate "streaming LLM→TTS chain"
  item from the roadmap.
- Changing the existing multi-turn "conversation active" follow-up window logic
  (`mark_conversation_active`) beyond wiring the new wake-word trigger into it.

## Architecture

### Overview

The Tauri desktop client streams continuous raw PCM audio (16kHz mono — the sample
rate both Silero VAD and openWakeWord expect) to the backend over a new WebSocket route,
`/ws/voice/stream`, instead of client-side-segmented HTTP uploads. The backend runs two
models on the same incoming audio stream:

- **Silero VAD** (ONNX via `onnxruntime`) determines segment boundaries (speech start/stop),
  replacing the RMS-threshold state machine currently in `voice-capture.ts` — logic moves
  server-side essentially unchanged (same debounce/min-duration/preroll concepts).
- **openWakeWord**, running a custom-trained "Mantis" model, scans the same stream for the
  wake word independently of VAD segment boundaries.

A completed VAD segment is only sent through transcription → agent response if either:
(a) the wake word was detected within that segment, or (b) the conversation is still
"active" per the existing follow-up-window logic (`mark_conversation_active`), so
multi-turn conversations don't require repeating "Mantis" every turn.

The existing HTTP route `/api/voice/segment` and its LLM-based `is_addressed_to_alfred`
check remain fully functional and unchanged, gated behind a `voice_stream_mode` setting
(`core.db.set_setting`) that defaults to the old path. The new WebSocket path only becomes
the active mode once Timo has manually validated the trained wake-word model's accuracy.

### Frontend (`apps/desktop/src/voice-capture.ts`)

Replace the `MediaRecorder` + RMS-threshold + calibration block with an `AudioWorkletNode`
that captures raw PCM chunks and streams them over the WebSocket as they arrive — no
client-side segmentation logic remains. The existing echo-avoidance behavior
(`isPlayingReply` pausing mic evaluation while Alfred's TTS reply plays) is preserved, but
instead of pausing analysis locally, a "muted" flag is sent alongside the stream so the
backend's VAD/wake-word models ignore audio during playback (prevents the mic hearing
Alfred's own voice and re-triggering).

The WebSocket receives `segment_result` events with the same payload shape the HTTP path
already returns (`text`, `addressed`, `reply`, `audio_b64`), so `onSegment` callback
consumers don't need to change.

### Backend

New module `core/voice_stream.py`: manages per-connection state (ring buffer of recent
audio for preroll, VAD speech/silence state machine, wake-word sliding-window scorer).
On segment completion, reuses the existing `transcribe_audio` and agent-response flow from
`web/routers/voice.py` — only the "addressed" determination changes (wake-word flag instead
of LLM text check).

New WebSocket route in `web/routers/voice.py` (or a new `web/routers/voice_stream.py`):
`/ws/voice/stream`, accepts raw PCM frames + mute-flag control messages, emits
`segment_result` JSON events.

### Wake-word training (sub-project, precedes integration)

New script `scripts/train_wakeword.py`, using openWakeWord's training pipeline:

- Generates synthetic positive samples: the word "Mantis" synthesized via Piper TTS across
  the available voice models/speeds for variety.
- Uses negative samples: general speech/background audio, reusing existing STT-benchmark
  audio (`scripts/stt_benchmark_prepare.py` output) as negative examples plus openWakeWord's
  standard background-noise augmentation.
- Trains a small ONNX wake-word model, run locally (CPU/GPU as available — expect this can
  take hours, runs unattended in the background).
- Output: a `.onnx` model file that Timo validates manually (by ear/testing) before it's
  wired into `core/voice_stream.py`. No automatic cutover — Timo confirms quality first.

## Error handling

- WebSocket disconnect/reconnect (mic hiccup, network blip): client reconnects
  automatically; any in-flight segment is simply dropped rather than buffered for retry —
  segments are short, so losing one occasionally is an acceptable trade-off for simplicity.
- Silero VAD misfires on non-speech transients (coughs, taps): filtered by the existing
  minimum-segment-duration guard (equivalent of today's `MIN_SEGMENT_MS`), now applied
  server-side.
- Old HTTP path stays fully functional throughout — if the new path misbehaves, flipping
  the `voice_stream_mode` setting back is a one-line rollback.

## Testing

- Extend the existing `scripts/e2e_voice_latency_test.py` with a WebSocket-mode benchmark
  to measure end-to-end latency of the new streaming path against the old HTTP path.
- Validate the trained wake-word model offline against a held-out mix of positive ("Mantis"
  in different voices/tones) and negative (normal conversation, similar-sounding words)
  samples before integration — target a low false-accept rate at acceptable recall, final
  threshold tuned by Timo's own listening tests.

## Open items for the implementation plan

- Exact WebSocket message framing (binary PCM frames + JSON control messages, or a single
  framed protocol).
- Which existing STT-benchmark audio qualifies as usable negative training data, and
  whether additional negative samples are needed.
- Where the openWakeWord training venv lives (likely a new dedicated venv similar to
  `data/xtts/venv`, since openWakeWord's dependencies may not match the main backend's
  Python 3.14 runtime — needs a compatibility check during planning).
