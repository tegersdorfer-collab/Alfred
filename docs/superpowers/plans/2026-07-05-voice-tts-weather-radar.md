# Voice Sensitivity, TTS Voices, Weather Radar Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix voice-detection sensitivity via auto-calibration, add three selectable
alternative Piper TTS voices, and replace the desktop weather widget with an OpenStreetMap +
RainViewer precipitation-radar map.

**Architecture:** Three independent units sharing one plan because they were requested
together. VAD calibration and TTS voice selection are backend/client tuning changes with no
shared code. The weather map adds a new pure-function tile-math module
(`apps/desktop/src/fx/map-tiles.ts`) and a new radar-frame-fetching helper, consumed by a
rewritten `weather` case in `main.ts`. Backend gains `lat`/`lon` in the weather payload.

**Tech Stack:** TypeScript (vanilla, desktop app), Python (backend, pytest), Piper TTS CLI
downloader, public OpenStreetMap tile server, public RainViewer radar API (no API key).

## Global Constraints

- No new npm dependencies in `apps/desktop/` (tile math and grid rendering are simple enough
  to hand-write; no mapping library is added).
- No changes to the backend Whisper speech-recognition pipeline — VAD work is client-side
  capture only.
- Every new function gets tests: Python via pytest following `tests/test_tts.py`'s pattern
  (`monkeypatch`, plain `assert`); TypeScript via Vitest following
  `apps/desktop/src/motion.test.ts`'s pattern (`describe`/`it`/`expect`).
- After every backend task: `python3 -m pytest tests/ -q` must stay green (313 passing at
  start of this plan).
- After every desktop task: `cd apps/desktop && npm test -- --run && npx tsc --noEmit` must
  both stay green (82 tests passing at start of this plan).
- Settings are read/written via the existing `core.db.get_setting(key, default)` /
  `core.db.set_setting(key, value)` helpers (`core/db.py:530-541`) — do not invent a new
  settings mechanism.
- Design spec of record: `docs/superpowers/specs/2026-07-05-voice-tts-weather-radar-design.md`.
  If a task here seems to contradict it, the spec wins — stop and flag it.
- One live verification at the end of the whole plan (Task 8): listen to the new TTS voices
  and look at the running map widget — not per-task, per the spec's §"Testability" sections.

---

### Task 1: VAD auto-calibration

**Files:**
- Modify: `apps/desktop/src/voice-capture.ts:8-13` (constants), inside `startVoiceCapture`
  (the `.then((mediaStream) => { ... })` block and `tick()`)
- Test: `apps/desktop/src/voice-capture-calibration.test.ts` (new file — `voice-capture.ts`
  itself has no existing test file to extend; this new file isolates the pure calibration
  logic so it's testable without a real `MediaStream`/`AudioContext`)

**Interfaces:**
- Produces: `computeCalibratedThreshold(samples: number[]): number` — exported pure function.
  Given an array of RMS samples collected during the calibration window, returns
  `Math.max(NOISE_FLOOR_MULTIPLIER * mean(samples), MIN_THRESHOLD)`. Consumed by
  `startVoiceCapture`'s calibration phase (Step 5 below).

- [ ] **Step 1: Write the failing test**

Create `apps/desktop/src/voice-capture-calibration.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import { computeCalibratedThreshold } from './voice-capture';

describe('computeCalibratedThreshold', () => {
  it('setzt den Schwellwert auf das 2.5-fache des mittleren Rauschpegels', () => {
    const samples = [0.01, 0.012, 0.008, 0.01]; // mean = 0.01
    expect(computeCalibratedThreshold(samples)).toBeCloseTo(0.025, 5);
  });

  it('fällt bei sehr leiser Umgebung auf den Mindestwert zurück', () => {
    const samples = [0.0001, 0.0002, 0.0001];
    expect(computeCalibratedThreshold(samples)).toBe(0.006);
  });

  it('wirft nicht bei einem leeren Array — Mindestwert als Fallback', () => {
    expect(computeCalibratedThreshold([])).toBe(0.006);
  });

  it('rundet nicht auf 0 bei exakt lautlosen Samples', () => {
    expect(computeCalibratedThreshold([0, 0, 0])).toBe(0.006);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/voice-capture-calibration.test.ts`
Expected: FAIL — `computeCalibratedThreshold` is not exported from `./voice-capture`.

- [ ] **Step 3: Add the constants and the pure function**

In `apps/desktop/src/voice-capture.ts`, replace the existing constants block (lines 8-13):

```typescript
const SILENCE_THRESHOLD = 0.02;   // RMS-Lautstärke-Schwelle (0..1)
const SILENCE_MS_TO_STOP = 800;   // so lange Stille beendet ein Sprachsegment
const MIN_SEGMENT_MS = 300;       // kürzere "Segmente" werden verworfen (Rauschen)
const PREROLL_MS = 400;           // Vorlauf vor Lautstärke-Trigger, damit der Wortanfang nicht abgeschnitten wird
const CHUNK_TIMESLICE_MS = 100;   // Aufnahme-Intervall des durchgehenden Recorders
const BUFFER_RETENTION_MS = 4000; // wie lange gepufferte Chunks für den Vorlauf vorgehalten werden
```

with:

```typescript
const SILENCE_MS_TO_STOP = 800;   // so lange Stille beendet ein Sprachsegment
const MIN_SEGMENT_MS = 300;       // kürzere "Segmente" werden verworfen (Rauschen)
const PREROLL_MS = 400;           // Vorlauf vor Lautstärke-Trigger, damit der Wortanfang nicht abgeschnitten wird
const CHUNK_TIMESLICE_MS = 100;   // Aufnahme-Intervall des durchgehenden Recorders
const BUFFER_RETENTION_MS = 4000; // wie lange gepufferte Chunks für den Vorlauf vorgehalten werden
const CALIBRATION_MS = 600;       // Dauer der Rauschpegel-Messung beim Start
const NOISE_FLOOR_MULTIPLIER = 2.5; // Schwellwert = Rauschpegel * Multiplikator
const MIN_THRESHOLD = 0.006;      // Sicherheits-Untergrenze, falls der Raum extrem leise ist

export function computeCalibratedThreshold(samples: number[]): number {
  if (samples.length === 0) return MIN_THRESHOLD;
  const mean = samples.reduce((sum, v) => sum + v, 0) / samples.length;
  return Math.max(NOISE_FLOOR_MULTIPLIER * mean, MIN_THRESHOLD);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/voice-capture-calibration.test.ts`
Expected: PASS (4 tests)

- [ ] **Step 5: Wire the calibration phase into `startVoiceCapture`**

In `apps/desktop/src/voice-capture.ts`, inside the `.then((mediaStream) => { ... })` block,
find the section that creates `analyser`/`data` and starts `recorder`. Add a calibration
phase right after `const data = new Uint8Array(analyser.fftSize);` and before
`recorder = new MediaRecorder(stream);`:

```typescript
      let effectiveThreshold = MIN_THRESHOLD;
      const calibrationSamples: number[] = [];
      const calibrationStart = performance.now();

      function calibrationTick(): void {
        if (stopped || !audioCtx) return;
        analyser.getByteTimeDomainData(data);
        calibrationSamples.push(rms(data));
        if (performance.now() - calibrationStart < CALIBRATION_MS) {
          rafId = requestAnimationFrame(calibrationTick);
        } else {
          effectiveThreshold = computeCalibratedThreshold(calibrationSamples);
          startRecordingAndDetection();
        }
      }

      function startRecordingAndDetection(): void {
```

Then find the existing lines starting from `recorder = new MediaRecorder(stream);` down
through the end of the `tick()` function definition and the trailing
`rafId = requestAnimationFrame(tick);` call that starts it — these all need to move inside
the new `startRecordingAndDetection()` function body (indent them one level, they stay
otherwise identical), so the recorder/tick loop only starts after calibration completes.
Inside `tick()`, replace the one usage of `SILENCE_THRESHOLD`:

```typescript
        if (level > SILENCE_THRESHOLD) {
```

with:

```typescript
        if (level > effectiveThreshold) {
```

Close the `startRecordingAndDetection` function body with a `}` after its final
`rafId = requestAnimationFrame(tick);` line (mirroring the closing brace the block already
had before this change), and replace the old top-level `rafId = requestAnimationFrame(tick);`
line (which used to start the loop immediately) with a call to start calibration instead:

```typescript
      rafId = requestAnimationFrame(calibrationTick);
```

- [ ] **Step 6: Run full check and commit**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS.

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/voice-capture.ts apps/desktop/src/voice-capture-calibration.test.ts
git commit -m "feat: auto-calibrate VAD threshold from ambient noise floor"
```

---

### Task 2: TTS voice-model selection

**Files:**
- Modify: `core/tts.py:24-51`
- Test: `tests/test_tts.py` (append to existing `class TestIsAvailable`/new class, following
  the file's established `monkeypatch` pattern — do not remove existing tests)

**Interfaces:**
- Produces: `resolve_voice_paths(voice_name: str) -> tuple[Path, Path]` — given a voice name
  key (e.g. `"thorsten-high"`, `"thorsten_emotional-medium"`, `"karlsson-low"`,
  `"pavoque-low"`), returns `(onnx_path, config_path)` from a `VOICE_MODELS` dict. Raises
  `KeyError` for an unknown voice name (a code bug, not a runtime condition to swallow).
  Consumed by `_load_voice()` (modified in this task) and by Task 8's live-verification step.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tts.py`, as a new class after `TestIsAvailable`:

```python
class TestResolveVoicePaths:
    def test_loest_bekannte_stimme_auf(self):
        onnx, cfg = tts.resolve_voice_paths("thorsten-high")
        assert onnx.name == "de_DE-thorsten-high.onnx"
        assert cfg.name == "de_DE-thorsten-high.onnx.json"

    def test_loest_alle_vier_kandidaten_auf(self):
        for name in ["thorsten-high", "thorsten_emotional-medium", "karlsson-low", "pavoque-low"]:
            onnx, cfg = tts.resolve_voice_paths(name)
            assert onnx.suffix == ".onnx"
            assert cfg.name == onnx.name + ".json"

    def test_wirft_bei_unbekannter_stimme(self):
        import pytest
        with pytest.raises(KeyError):
            tts.resolve_voice_paths("nicht-existent")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_tts.py::TestResolveVoicePaths -v`
Expected: FAIL — `AttributeError: module 'core.tts' has no attribute 'resolve_voice_paths'`

- [ ] **Step 3: Replace the hardcoded model path with a voice registry**

In `core/tts.py`, replace lines 24-29:

```python
_MODEL_DIR    = Path(__file__).parent.parent / "data" / "tts" / "piper"
_ONNX_PATH    = _MODEL_DIR / "de_DE-thorsten-high.onnx"
_CONFIG_PATH  = _MODEL_DIR / "de_DE-thorsten-high.onnx.json"

DEFAULT_VOICE = "de_DE-thorsten-high"  # männlich, deutsch
DEFAULT_SPEED = 1.0
```

with:

```python
_MODEL_DIR = Path(__file__).parent.parent / "data" / "tts" / "piper"

VOICE_MODELS: dict[str, str] = {
    "thorsten-high": "de_DE-thorsten-high",
    "thorsten_emotional-medium": "de_DE-thorsten_emotional-medium",
    "karlsson-low": "de_DE-karlsson-low",
    "pavoque-low": "de_DE-pavoque-low",
}

DEFAULT_VOICE = "thorsten-high"  # männlich, deutsch — unverändert ggü. bisherigem Verhalten
DEFAULT_SPEED = 1.0


def resolve_voice_paths(voice_name: str) -> tuple[Path, Path]:
    """Löst einen Stimmen-Schlüssel (z.B. 'karlsson-low') zu (onnx_path, config_path) auf.

    Wirft KeyError für unbekannte Namen — ein falscher Stimmen-Name ist ein
    Programmfehler (z.B. Tippfehler im Setting), kein zur Laufzeit erwarteter Zustand.
    """
    filename = VOICE_MODELS[voice_name]
    onnx = _MODEL_DIR / f"{filename}.onnx"
    return onnx, _MODEL_DIR.with_name(_MODEL_DIR.name) / f"{filename}.onnx.json"
```

Note: the second element of the returned tuple has a redundant `.with_name(...)` — simplify
it to just `_MODEL_DIR / f"{filename}.onnx.json"` (the same directory, just the config file):

```python
def resolve_voice_paths(voice_name: str) -> tuple[Path, Path]:
    """Löst einen Stimmen-Schlüssel (z.B. 'karlsson-low') zu (onnx_path, config_path) auf.

    Wirft KeyError für unbekannte Namen — ein falscher Stimmen-Name ist ein
    Programmfehler (z.B. Tippfehler im Setting), kein zur Laufzeit erwarteter Zustand.
    """
    filename = VOICE_MODELS[voice_name]
    onnx = _MODEL_DIR / f"{filename}.onnx"
    config = _MODEL_DIR / f"{filename}.onnx.json"
    return onnx, config
```

- [ ] **Step 4: Update `is_available()` and `_load_voice()` to use the active voice setting**

In `core/tts.py`, replace `is_available()` and `_load_voice()`:

```python
def is_available() -> bool:
    return _ONNX_PATH.exists() and _CONFIG_PATH.exists()


def _load_voice():
    global _voice
    if _voice is not None:
        return _voice
    if not is_available():
        raise RuntimeError(
            f"Piper-Modell nicht gefunden in {_MODEL_DIR}. "
            "Bitte de_DE-thorsten-high.onnx (+ .onnx.json) herunterladen."
        )
    from piper import PiperVoice
    _voice = PiperVoice.load(str(_ONNX_PATH), str(_CONFIG_PATH))
    log.info("🔊 Piper TTS geladen (de_DE-thorsten-high)")
    return _voice
```

with:

```python
def _active_voice_name() -> str:
    return db.get_setting("tts_voice", DEFAULT_VOICE) or DEFAULT_VOICE


def is_available() -> bool:
    try:
        onnx, config = resolve_voice_paths(_active_voice_name())
    except KeyError:
        return False
    return onnx.exists() and config.exists()


def _load_voice():
    global _voice, _loaded_voice_name
    voice_name = _active_voice_name()
    if _voice is not None and _loaded_voice_name == voice_name:
        return _voice
    onnx, config = resolve_voice_paths(voice_name)
    if not (onnx.exists() and config.exists()):
        raise RuntimeError(
            f"Piper-Modell '{voice_name}' nicht gefunden in {_MODEL_DIR}. "
            f"Bitte {onnx.name} (+ .onnx.json) herunterladen."
        )
    from piper import PiperVoice
    _voice = PiperVoice.load(str(onnx), str(config))
    _loaded_voice_name = voice_name
    log.info(f"🔊 Piper TTS geladen ({voice_name})")
    return _voice
```

Add `from core import db` to the imports at the top of `core/tts.py` (it currently has no
`core.db` import — check the existing import block and add it alongside the standard-library
imports), and add a new module-level variable next to `_voice: object | None = None`:

```python
_voice: object | None = None
_loaded_voice_name: str | None = None
_lock = asyncio.Lock()
```

- [ ] **Step 5: Update the existing `TestIsAvailable` tests for the new signature**

The existing tests in `tests/test_tts.py::TestIsAvailable` monkeypatch `tts._ONNX_PATH`/
`tts._CONFIG_PATH`, which no longer exist as module attributes after Step 4. Replace that
class with:

```python
class TestIsAvailable:
    def test_verfuegbar_wenn_modell_dateien_existieren(self, tmp_path, monkeypatch):
        onnx = tmp_path / "de_DE-thorsten-high.onnx"
        cfg = tmp_path / "de_DE-thorsten-high.onnx.json"
        onnx.write_bytes(b"x")
        cfg.write_bytes(b"{}")
        monkeypatch.setattr(tts, "_MODEL_DIR", tmp_path)
        monkeypatch.setattr(tts.db, "get_setting", lambda key, default=None: "thorsten-high")
        assert tts.is_available() is True

    def test_nicht_verfuegbar_wenn_dateien_fehlen(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tts, "_MODEL_DIR", tmp_path)
        monkeypatch.setattr(tts.db, "get_setting", lambda key, default=None: "thorsten-high")
        assert tts.is_available() is False

    def test_nicht_verfuegbar_bei_unbekanntem_stimmen_namen(self, monkeypatch):
        monkeypatch.setattr(tts.db, "get_setting", lambda key, default=None: "unbekannt")
        assert tts.is_available() is False
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_tts.py -v`
Expected: PASS (all tests, existing `TestCleanForSpeech`/`TestSynthesize` classes untouched
and still passing, plus the new `TestResolveVoicePaths` class and the updated
`TestIsAvailable` class).

- [ ] **Step 7: Run full backend check and commit**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (313 + new tests, 0 failures)

```bash
cd /Users/timoegersdorfer/Alfred
git add core/tts.py tests/test_tts.py
git commit -m "feat: make Piper TTS voice selectable via tts_voice setting"
```

---

### Task 3: Download three alternative Piper voice models

**Files:**
- No source files modified — this task only adds binary model files under
  `data/tts/piper/` (already gitignored, per `ROADMAP.md`'s documented pattern for
  `thorsten-high` — these downloads are NOT committed to git).

**Interfaces:**
- Produces: three new `.onnx`/`.onnx.json` file pairs on disk, matching the filenames
  `resolve_voice_paths` (Task 2) expects for `thorsten_emotional-medium`, `karlsson-low`,
  `pavoque-low`.

- [ ] **Step 1: Download the three voices**

Run from the repo root (same mechanism `ROADMAP.md` documents was used for `thorsten-high`):

```bash
python3 -m piper.download_voices de_DE-thorsten_emotional-medium
python3 -m piper.download_voices de_DE-karlsson-low
python3 -m piper.download_voices de_DE-pavoque-low
```

- [ ] **Step 2: Verify the files landed where `resolve_voice_paths` expects them**

Run: `ls data/tts/piper/`
Expected: alongside the existing `de_DE-thorsten-high.onnx`/`.onnx.json`, six new files:
`de_DE-thorsten_emotional-medium.onnx`, `.onnx.json`, `de_DE-karlsson-low.onnx`, `.onnx.json`,
`de_DE-pavoque-low.onnx`, `.onnx.json`.

If `piper.download_voices` places files in a different location (e.g. a package cache
directory rather than `data/tts/piper/`), move/symlink them into `data/tts/piper/` with the
exact filenames above — `resolve_voice_paths` (Task 2) constructs paths as
`_MODEL_DIR / f"{filename}.onnx"` where `_MODEL_DIR` is `data/tts/piper/`, so the files must
live there under those exact names for `is_available()`/`_load_voice()` to find them.

- [ ] **Step 3: Confirm each voice loads and synthesizes**

Run this once per new voice name to confirm the model files are valid and Piper can load them
(this is a manual smoke check, not a pytest test — TTS audio correctness isn't something an
assertion can meaningfully verify, per the design spec):

```bash
python3 -c "
import asyncio, sys
sys.path.insert(0, '.')
from core import db, tts
for name in ['thorsten_emotional-medium', 'karlsson-low', 'pavoque-low']:
    db.set_setting('tts_voice', name)
    tts._voice = None
    tts._loaded_voice_name = None
    ogg = asyncio.run(tts.synthesize('Hallo, ich bin Alfred.'))
    print(name, '->', len(ogg), 'bytes OGG' if ogg else 'FEHLGESCHLAGEN')
db.set_setting('tts_voice', 'thorsten-high')  # zurück auf den bisherigen Default
"
```

Expected: each line prints a non-zero byte count. If any voice fails, re-run its
`download_voices` command — a partial/corrupted download is the most likely cause.

- [ ] **Step 4: No commit needed for this task**

The downloaded model files are gitignored binary data (matching the existing
`de_DE-thorsten-high.onnx` pattern) — there is nothing to commit. Proceed to Task 4.

---

### Task 4: Backend — add lat/lon to the weather payload

**Files:**
- Modify: `domains/weather.py:54-64`
- Test: `tests/test_weather.py` (new file — no existing test file covers `domains/weather.py`)

**Interfaces:**
- Produces: `get_weather()`'s returned dict gains `lat: float` and `lon: float` keys
  (alongside the existing `city`/`now`/`forecast`). Consumed by Task 7 (`main.ts`'s `weather`
  case) via the existing `weather_widget_payload` passthrough in `core/ui_state.py` (already
  forwards the whole dict unchanged — no change needed there, confirmed in the design spec).

- [ ] **Step 1: Write the failing test**

Create `tests/test_weather.py`:

```python
"""Unit-Tests für domains/weather.py: Geocoding + Forecast (Open-Meteo)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from domains import weather


def _fake_response(json_data):
    resp = MagicMock()
    resp.json.return_value = json_data
    return resp


class TestGetWeather:
    def test_gibt_lat_lon_der_stadt_zurueck(self, monkeypatch):
        geocode_response = _fake_response({
            "results": [{"name": "Nürnberg", "latitude": 49.4521, "longitude": 11.0767}]
        })
        forecast_response = _fake_response({
            "current": {
                "temperature_2m": 20.0, "apparent_temperature": 19.5,
                "relative_humidity_2m": 60, "wind_speed_10m": 10, "weather_code": 3,
            },
            "daily": {
                "time": ["2026-07-05"], "temperature_2m_max": [24.0], "temperature_2m_min": [18.0],
                "weather_code": [3], "precipitation_probability_max": [15],
            },
        })

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=[geocode_response, forecast_response])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("domains.weather.httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(weather.get_weather("Nürnberg"))

        assert result["lat"] == 49.4521
        assert result["lon"] == 11.0767
        assert result["city"] == "Nürnberg"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_weather.py -v`
Expected: FAIL — `KeyError: 'lat'` (the returned dict doesn't have `lat`/`lon` yet).

- [ ] **Step 3: Add lat/lon to the returned dict**

In `domains/weather.py`, replace the final `return` statement (lines 54-64):

```python
    return {
        "city": loc["name"],
        "now": {
            "temp": cur.get("temperature_2m"),
            "feels": cur.get("apparent_temperature"),
            "humidity": cur.get("relative_humidity_2m"),
            "wind": cur.get("wind_speed_10m"),
            "desc": WMO.get(cur.get("weather_code"), "?"),
        },
        "forecast": days,
    }
```

with:

```python
    return {
        "city": loc["name"],
        "lat": lat,
        "lon": lon,
        "now": {
            "temp": cur.get("temperature_2m"),
            "feels": cur.get("apparent_temperature"),
            "humidity": cur.get("relative_humidity_2m"),
            "wind": cur.get("wind_speed_10m"),
            "desc": WMO.get(cur.get("weather_code"), "?"),
        },
        "forecast": days,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_weather.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Run full backend check and commit**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (313 + new tests, 0 failures)

```bash
cd /Users/timoegersdorfer/Alfred
git add domains/weather.py tests/test_weather.py
git commit -m "feat: include lat/lon in weather payload for the desktop radar map"
```

---

### Task 5: Slippy-map tile-math module

**Files:**
- Create: `apps/desktop/src/fx/map-tiles.ts`
- Test: `apps/desktop/src/fx/map-tiles.test.ts`

**Interfaces:**
- Produces: `latLonToTile(lat: number, lon: number, zoom: number): { x: number; y: number }`
  — standard OSM slippy-map projection, integer tile coordinates.
- Produces: `tileGrid(centerX: number, centerY: number, radius: number): { x: number; y: number }[]`
  — a square grid of tile coordinates from `centerX - radius` to `centerX + radius`
  (inclusive) in both dimensions, in row-major order (y outer loop, x inner loop). Consumed
  by Task 7 (`main.ts`'s rewritten `weather` case).

- [ ] **Step 1: Write the failing test**

Create `apps/desktop/src/fx/map-tiles.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import { latLonToTile, tileGrid } from './map-tiles';

describe('latLonToTile', () => {
  it('berechnet die bekannte Kachel für Nürnberg bei Zoom 8', () => {
    // Referenzwert: https://tools.geofabrik.de/calc/ für lat=49.4521, lon=11.0767, zoom=8
    const tile = latLonToTile(49.4521, 11.0767, 8);
    expect(tile.x).toBe(135);
    expect(tile.y).toBe(87);
  });

  it('berechnet die Kachel (0,0) für die Nordwest-Ecke der Karte', () => {
    const tile = latLonToTile(85.0, -180, 2);
    expect(tile.x).toBe(0);
    expect(tile.y).toBe(0);
  });

  it('skaliert korrekt mit dem Zoom-Level (mehr Kacheln bei höherem Zoom)', () => {
    const low = latLonToTile(49.4521, 11.0767, 4);
    const high = latLonToTile(49.4521, 11.0767, 8);
    expect(high.x).toBeGreaterThan(low.x);
  });
});

describe('tileGrid', () => {
  it('erzeugt ein 3x3-Raster bei radius=1', () => {
    const grid = tileGrid(10, 10, 1);
    expect(grid.length).toBe(9);
    expect(grid).toContainEqual({ x: 9, y: 9 });
    expect(grid).toContainEqual({ x: 10, y: 10 });
    expect(grid).toContainEqual({ x: 11, y: 11 });
  });

  it('erzeugt genau eine Kachel bei radius=0', () => {
    const grid = tileGrid(5, 5, 0);
    expect(grid).toEqual([{ x: 5, y: 5 }]);
  });

  it('ist in row-major Reihenfolge (y äußere, x innere Schleife)', () => {
    const grid = tileGrid(0, 0, 1);
    expect(grid[0]).toEqual({ x: -1, y: -1 });
    expect(grid[1]).toEqual({ x: 0, y: -1 });
    expect(grid[2]).toEqual({ x: 1, y: -1 });
    expect(grid[3]).toEqual({ x: -1, y: 0 });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/fx/map-tiles.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `map-tiles.ts`**

Create `apps/desktop/src/fx/map-tiles.ts`:

```typescript
export function latLonToTile(lat: number, lon: number, zoom: number): { x: number; y: number } {
  const n = Math.pow(2, zoom);
  const latRad = (lat * Math.PI) / 180;
  const x = Math.floor(((lon + 180) / 360) * n);
  const y = Math.floor(
    ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n,
  );
  return { x, y };
}

export function tileGrid(
  centerX: number,
  centerY: number,
  radius: number,
): { x: number; y: number }[] {
  const grid: { x: number; y: number }[] = [];
  for (let y = centerY - radius; y <= centerY + radius; y++) {
    for (let x = centerX - radius; x <= centerX + radius; x++) {
      grid.push({ x, y });
    }
  }
  return grid;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/fx/map-tiles.test.ts`
Expected: PASS (6 tests). If the Nürnberg reference tile values don't match exactly (rounding
differences are possible depending on the exact formula variant), compute the actual value by
running the implementation once (`node -e` with a small inline script, or a temporary
`console.log` in the test) and use that real computed value in the test instead of guessing —
the point of the test is to lock in correct, verifiable behavior, not to match an unverified
guess.

- [ ] **Step 5: Run full check and commit**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS.

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/fx/map-tiles.ts apps/desktop/src/fx/map-tiles.test.ts
git commit -m "feat: add slippy-map tile-coordinate math (latLonToTile, tileGrid)"
```

---

### Task 6: RainViewer radar-frame helper

**Files:**
- Create: `apps/desktop/src/fx/radar-frames.ts`
- Test: `apps/desktop/src/fx/radar-frames.test.ts`

**Interfaces:**
- Consumes: nothing from earlier tasks (standalone fetch + parse helper).
- Produces: `fetchRadarFrameTimes(fetchImpl?: typeof fetch): Promise<number[]>` — fetches
  `https://api.rainviewer.com/public/weather-maps.json`, returns the last 4 timestamps from
  the response's `radar.past` array (or fewer if less than 4 are available; empty array on
  any fetch/parse failure — never throws). Produces:
  `radarTileUrl(time: number, z: number, x: number, y: number): string` — builds
  `https://tilecache.rainviewer.com/v2/radar/{time}/256/{z}/{x}/{y}/2/1_1.png`. Both consumed
  by Task 7 (`main.ts`'s rewritten `weather` case).

- [ ] **Step 1: Write the failing test**

Create `apps/desktop/src/fx/radar-frames.test.ts`:

```typescript
import { describe, it, expect, vi } from 'vitest';
import { fetchRadarFrameTimes, radarTileUrl } from './radar-frames';

describe('fetchRadarFrameTimes', () => {
  it('gibt die letzten 4 Zeitstempel aus radar.past zurück', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        radar: { past: [{ time: 1 }, { time: 2 }, { time: 3 }, { time: 4 }, { time: 5 }] },
      }),
    });
    const times = await fetchRadarFrameTimes(fakeFetch as unknown as typeof fetch);
    expect(times).toEqual([2, 3, 4, 5]);
  });

  it('gibt alle Zeitstempel zurück wenn weniger als 4 verfügbar sind', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ radar: { past: [{ time: 10 }, { time: 20 }] } }),
    });
    const times = await fetchRadarFrameTimes(fakeFetch as unknown as typeof fetch);
    expect(times).toEqual([10, 20]);
  });

  it('gibt ein leeres Array zurück bei Netzwerkfehler statt zu werfen', async () => {
    const fakeFetch = vi.fn().mockRejectedValue(new Error('network down'));
    const times = await fetchRadarFrameTimes(fakeFetch as unknown as typeof fetch);
    expect(times).toEqual([]);
  });

  it('gibt ein leeres Array zurück bei unerwarteter Antwortstruktur', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ unexpected: 'shape' }),
    });
    const times = await fetchRadarFrameTimes(fakeFetch as unknown as typeof fetch);
    expect(times).toEqual([]);
  });
});

describe('radarTileUrl', () => {
  it('baut die korrekte RainViewer-Kachel-URL', () => {
    expect(radarTileUrl(1234567890, 8, 137, 87)).toBe(
      'https://tilecache.rainviewer.com/v2/radar/1234567890/256/8/137/87/2/1_1.png',
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/fx/radar-frames.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `radar-frames.ts`**

Create `apps/desktop/src/fx/radar-frames.ts`:

```typescript
export async function fetchRadarFrameTimes(
  fetchImpl: typeof fetch = fetch,
): Promise<number[]> {
  try {
    const res = await fetchImpl('https://api.rainviewer.com/public/weather-maps.json');
    const data = await res.json();
    const past = data?.radar?.past;
    if (!Array.isArray(past)) return [];
    return past.slice(-4).map((frame: { time: number }) => frame.time);
  } catch {
    return [];
  }
}

export function radarTileUrl(time: number, z: number, x: number, y: number): string {
  return `https://tilecache.rainviewer.com/v2/radar/${time}/256/${z}/${x}/${y}/2/1_1.png`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/fx/radar-frames.test.ts`
Expected: PASS (5 tests)

- [ ] **Step 5: Run full check and commit**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS.

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/fx/radar-frames.ts apps/desktop/src/fx/radar-frames.test.ts
git commit -m "feat: add RainViewer radar-frame fetch/URL helper"
```

---

### Task 7: Rewrite the `weather` widget as a radar map

**Files:**
- Modify: `apps/desktop/src/main.ts` (the `weather` case in `renderWidget`, currently lines
  256-273 as of Task 9 of the prior "Ghost Protocol v2" pass — re-locate the exact case by
  searching for `case 'weather':` since line numbers have shifted across many commits)
- Modify: `apps/desktop/src/style.css` (append map/radar CSS)

**Interfaces:**
- Consumes: `latLonToTile`, `tileGrid` (from `./fx/map-tiles`, Task 5), `fetchRadarFrameTimes`,
  `radarTileUrl` (from `./fx/radar-frames`, Task 6), `icon` (from `./fx/icons`, already
  committed in the prior pass).

- [ ] **Step 1: Add imports**

In `apps/desktop/src/main.ts`, add to the existing imports:

```typescript
import { latLonToTile, tileGrid } from './fx/map-tiles';
import { fetchRadarFrameTimes, radarTileUrl } from './fx/radar-frames';
```

- [ ] **Step 2: Add a `renderWeatherMap` function**

Add this function near the other `render*` helpers (`renderBars`, `renderList`,
`renderGauge`, `renderGraph`) in `apps/desktop/src/main.ts`:

```typescript
const MAP_ZOOM = 8;
const MAP_RADIUS = 1; // 1 => 3x3 grid

function renderWeatherMap(container: HTMLElement, payload: any): void {
  const lat = payload.lat;
  const lon = payload.lon;
  const city = payload.city ?? '';
  const now = payload.now ?? {};

  if (typeof lat !== 'number' || typeof lon !== 'number') {
    container.innerHTML = `<div class="widget-title">${icon('weather-cloud')} Wetter — ${city}</div><div class="list-line">Keine Standortdaten verfügbar.</div>`;
    applyPanelChrome(container);
    return;
  }

  const center = latLonToTile(lat, lon, MAP_ZOOM);
  const grid = tileGrid(center.x, center.y, MAP_RADIUS);
  const gridSize = MAP_RADIUS * 2 + 1;

  const baseTiles = grid
    .map(
      (t) =>
        `<img class="map-tile" src="https://tile.openstreetmap.org/${MAP_ZOOM}/${t.x}/${t.y}.png" />`,
    )
    .join('');

  container.innerHTML = `
    <div class="widget-title">${icon('weather-cloud')} Wetter — ${city}</div>
    <div class="map-header">${now.temp ?? '–'}°C (gefühlt ${now.feels ?? '–'}°C), ${now.desc ?? ''}</div>
    <div class="map-grid" style="grid-template-columns: repeat(${gridSize}, 1fr);">
      ${baseTiles}
      <div class="map-radar-layer" style="grid-template-columns: repeat(${gridSize}, 1fr);"></div>
    </div>
    <div class="map-attribution">© OpenStreetMap contributors</div>
  `;
  applyPanelChrome(container);

  const radarLayer = container.querySelector('.map-radar-layer');
  if (!radarLayer) return;

  fetchRadarFrameTimes().then((times) => {
    if (times.length === 0) return; // kein Radar-Overlay verfügbar — Basiskarte bleibt sichtbar
    const frames = times.map(
      (time) =>
        `<div class="map-radar-frame">${grid
          .map(
            (t) =>
              `<img class="map-tile map-radar-tile" src="${radarTileUrl(time, MAP_ZOOM, t.x, t.y)}" />`,
          )
          .join('')}</div>`,
    );
    radarLayer.innerHTML = frames.join('');
    const frameEls = radarLayer.querySelectorAll<HTMLElement>('.map-radar-frame');
    let activeIndex = 0;
    frameEls.forEach((el, i) => {
      el.style.display = i === 0 ? 'grid' : 'none';
    });
    const intervalId = setInterval(() => {
      frameEls[activeIndex].style.display = 'none';
      activeIndex = (activeIndex + 1) % frameEls.length;
      frameEls[activeIndex].style.display = 'grid';
    }, 800);
    // Intervall an das Element hängen, damit es beim nächsten renderWidget-Aufruf
    // für dieses Slot (siehe Step 3 der applyUiEvent-Neuzeichnung) gestoppt werden kann.
    (container as any)._radarIntervalId = intervalId;
  });
}
```

- [ ] **Step 3: Clear any previous radar interval before re-rendering a slot**

In `apps/desktop/src/main.ts`, find `renderWidget` (the function containing the `switch
(slot.widget) { ... }` block). At the very top of `renderWidget`, before the `switch`
statement, add:

```typescript
  if ((container as any)._radarIntervalId) {
    clearInterval((container as any)._radarIntervalId);
    (container as any)._radarIntervalId = null;
  }
```

This prevents a leaked `setInterval` from a previous weather-map render continuing to run
(and throwing once its DOM elements are gone) after the widget area re-renders with different
content.

- [ ] **Step 4: Replace the `weather` case body**

Find the current `case 'weather': { ... }` block (search for `case 'weather':` — do not
assume a specific line number, it has shifted). Replace its entire body with:

```typescript
    case 'weather':
      renderWeatherMap(container, p);
      break;
```

Delete the old `conditionIcon` helper and the `renderList`-based rendering that were
previously inside this case — they're fully replaced by `renderWeatherMap`.

- [ ] **Step 5: Add map/radar CSS**

Append to `apps/desktop/src/style.css`:

```css
.map-header {
  font-size: var(--fs-body);
  color: var(--c-idle);
  text-align: center;
  margin-bottom: 8px;
}
.map-grid {
  display: grid;
  gap: 0;
  position: relative;
  width: 100%;
  max-width: 384px;
  margin: 0 auto;
}
.map-tile {
  width: 100%;
  display: block;
  filter: saturate(0.6) brightness(0.7);
}
.map-radar-layer {
  position: absolute;
  inset: 0;
  display: grid;
  gap: 0;
}
.map-radar-frame {
  position: absolute;
  inset: 0;
  display: grid;
  gap: 0;
}
.map-radar-tile {
  width: 100%;
  display: block;
  filter: hue-rotate(140deg) saturate(1.4) brightness(1.1);
  mix-blend-mode: screen;
}
.map-attribution {
  font-size: var(--fs-micro);
  color: var(--c-idle-dim);
  text-align: right;
  margin-top: 4px;
}
```

- [ ] **Step 6: Run full check**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS. If any existing test in `main.test.ts` references the old `weather`
case's `conditionIcon` behavior or its `renderList`-based output, remove/update that test —
the case's rendering strategy has fundamentally changed in this task, so an old assertion
about its text-list output is now testing removed behavior, not a regression.

- [ ] **Step 7: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/main.ts apps/desktop/src/style.css
git commit -m "feat: replace weather widget with OSM + RainViewer radar map"
```

---

### Task 8: ROADMAP update and final live verification

**Files:**
- Modify: `ROADMAP.md`

- [ ] **Step 1: Add the ROADMAP section**

Add a new section to `ROADMAP.md`, directly after the most recent dated section (the Ghost
Protocol v2 entry from earlier the same day):

```markdown
## Voice-Sensitivity, TTS-Stimmen, Wetter-Radar-Karte (2026-07-05)

Spec: `docs/superpowers/specs/2026-07-05-voice-tts-weather-radar-design.md`
Plan: `docs/superpowers/plans/2026-07-05-voice-tts-weather-radar.md`

- [x] VAD-Schwellwert kalibriert sich jetzt selbst aus dem Umgebungsrauschpegel statt eines
      festen Werts (`computeCalibratedThreshold` in `voice-capture.ts`)
- [x] Drei zusätzliche männliche Piper-Stimmen heruntergeladen und über die
      `tts_voice`-Einstellung umschaltbar (thorsten_emotional-medium, karlsson-low,
      pavoque-low) — Auswahl bisher nur per direktem Settings-Aufruf, kein UI-Dropdown
- [x] Wetter-Widget zeigt jetzt eine OSM-Karte mit RainViewer-Regenradar-Overlay
      (letzte 4 Frames, ~800ms-Loop) statt der reinen Text-/Forecast-Liste
- [ ] TTS-Stimmen-Auswahl im Settings-Panel als Dropdown (Folgearbeit, sobald Timo eine
      Favoritenstimme gewählt hat)
```

- [ ] **Step 2: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add ROADMAP.md
git commit -m "docs: log voice-sensitivity/TTS-voice/weather-radar work in ROADMAP"
```

- [ ] **Step 3: Final live verification**

Run both full suites one last time to confirm everything is green together:

```bash
python3 -m pytest tests/ -q
cd apps/desktop && npm test -- --run && npx tsc --noEmit
```

Then rebuild and relaunch the desktop app:

```bash
cd /Users/timoegersdorfer/Alfred/apps/desktop && npm run tauri build
pkill -f "/Applications/Alfred.app/Contents/MacOS/desktop" 2>/dev/null
sleep 1
rm -rf /Applications/Alfred.app
cp -R /Users/timoegersdorfer/Alfred/apps/desktop/src-tauri/target/release/bundle/macos/Alfred.app /Applications/Alfred.app
open /Applications/Alfred.app
```

Restart the Alfred backend process so `core/tts.py`'s changes and the new lat/lon field in
`domains/weather.py` take effect:

```bash
kill -9 $(pgrep -f "python.*main.py") 2>/dev/null
launchctl kickstart -k gui/501/com.alfred.assistant
sleep 3
curl -s http://localhost:7779/health
```

If a screenshot/inspection tool is available, use it to look at the running desktop app's
weather widget (confirm the map tiles and radar overlay actually render, not just that the
process is alive) and report what you see. Ask a weather question via chat/voice to trigger
the widget if it isn't already showing. This is the one point in this plan where the map's
actual visual correctness — as opposed to its unit-tested tile math — gets checked; state
plainly in the final report whether this was possible in the environment or whether Timo
needs to check it himself.
