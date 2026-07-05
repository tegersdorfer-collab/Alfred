# Voice Sensitivity, TTS Voice Selection, Weather Radar Map — Design / Spec

**Datum:** 2026-07-05
**Scope:** Three independent fixes/features, bundled in one spec because they're small and
were requested together, but implemented and tested as separate units:

1. Auto-calibrating voice-activity-detection (VAD) threshold in the desktop voice capture,
   replacing a fixed magic-number threshold that doesn't adapt to mic/room noise.
2. Downloadable/selectable alternative male Piper TTS voices, so Timo can audition and pick one.
3. A weather widget rewrite: replaces the current text-only weather widget with an
   OpenStreetMap + RainViewer precipitation-radar map view, centered on the configured city.

Not in scope: VAD/TTS changes to the backend's own speech recognition (Whisper) pipeline —
this is client-side capture only. No new UI framework. No changes to other widgets.

## 1. VAD auto-calibration

**Current state:** `apps/desktop/src/voice-capture.ts:8` — `SILENCE_THRESHOLD = 0.02`, a fixed
RMS-energy magic number compared every `CHUNK_TIMESLICE_MS` (100ms) against the mic's live RMS
level to decide speech-vs-silence. Timo reports Alfred often doesn't register that he's
talking — a fixed threshold that happens to sit above his mic's typical speech RMS (quieter
mic, different room noise floor than whatever the original constant was tuned for) is the
most likely cause, and is inherently fragile across different hardware/environments.

**Design:** replace the fixed constant with a short calibration phase run once when voice
capture starts: sample RMS energy for `CALIBRATION_MS = 600`ms before any speech-detection
logic runs, take the mean of those samples as the ambient noise floor, and set the effective
threshold to `max(NOISE_FLOOR_MULTIPLIER * noiseFloor, MIN_THRESHOLD)` — a floor so a
perfectly silent room doesn't produce a threshold of ~0 (which would trigger on any noise
at all). `NOISE_FLOOR_MULTIPLIER = 2.5` and `MIN_THRESHOLD = 0.006` are reasonable starting
constants (roughly a third of the current fixed value, as a safety floor only — the
calibrated value will typically land above this for any real room). During the calibration
window, no speech segments are captured (this is a one-time ~0.6s startup cost, not a
per-utterance delay).

**Testability:** the calibration logic (given a sequence of RMS samples, compute the
threshold) is a pure function, fully unit-testable without a real microphone.

## 2. TTS voice candidates

**Current state:** `core/tts.py:25-28` hardcodes `MODEL_ONNX_PATH` to
`data/tts/piper/de_DE-thorsten-high.onnx`. No other voice is downloaded or selectable.

**Design:** download three additional male German Piper voices via the existing
`python3 -m piper.download_voices <name>` mechanism (per `ROADMAP.md`'s documented pattern
for `thorsten-high`): `de_DE-thorsten_emotional-medium`, `de_DE-karlsson-low`,
`de_DE-pavoque-low`. Add a `TTS_VOICE` setting (reusing the existing `db.get_setting`/
`db.set_setting` pattern already used elsewhere, e.g. `weather_city`) defaulting to
`thorsten-high` (no behavior change until Timo explicitly switches it), with `core/tts.py`
resolving the active model path from a small `VOICE_MODELS` dict keyed by voice name instead
of the single hardcoded path. This makes trying a new voice a one-line setting change
(`db.set_setting("tts_voice", "karlsson-low")`) rather than a code edit — Timo can audition
voices via Alfred's existing chat/Telegram interface by asking Alfred to switch, once wired
up, or the plan can leave switching to a direct DB-setting call for this first pass (no new
UI is being added for this — out of scope per "each is a separate small unit").

**Testability:** the voice-name → model-path resolution is a pure function, unit-testable.
Actual audio synthesis with each downloaded model is verified by a live listen, not a test
(TTS audio quality isn't something an automated assertion can meaningfully check).

## 3. Weather radar map widget

**Current state:** `main.ts`'s `weather` case renders `renderList` with a text summary + daily
forecast lines. `domains/weather.py::get_weather()` geocodes the city (extracting `lat`/`lon`
locally at line 34) but never returns those coordinates — only city name, current conditions,
and forecast.

**Design:**

- **Backend (`domains/weather.py`):** add `lat` and `lon` (rounded to the geocoding API's
  natural precision) to the dict `get_weather()` returns. `core/ui_state.py::weather_widget_payload`
  already forwards the whole dict unchanged, so no change needed there.
- **Tile math (`apps/desktop/src/fx/map-tiles.ts`, new module):** a pure function
  `latLonToTile(lat, lon, zoom) => { x, y }` implementing the standard OSM slippy-map
  projection, and `tileGrid(centerX, centerY, radius) => {x,y}[]` producing a square grid of
  tile coordinates (e.g. 3×3, radius 1) around the center tile. Both are pure, fully
  unit-testable without network access.
- **Rendering (`main.ts`'s `weather` case, rewritten):** for the resolved city's lat/lon at a
  fixed zoom level (`MAP_ZOOM = 8`, a regional view — wide enough to show nearby precipitation
  systems, not just the immediate street grid), render a 3×3 grid of `<img>` elements:
  - Base layer: `https://tile.openstreetmap.org/{z}/{x}/{y}.png`
  - Radar overlay: RainViewer's public API. First fetch
    `https://api.rainviewer.com/public/weather-maps.json` (no key required) to get the list of
    available radar frame timestamps, then for the last 4 frames build overlay tile URLs
    `https://tilecache.rainviewer.com/v2/radar/{time}/256/{z}/{x}/{y}/2/1_1.png` per grid tile,
    absolutely positioned over the base tiles with `opacity` and `mix-blend-mode` suited to a
    dark HUD (semi-transparent, tinted toward the existing `--c-active`/`--c-warn` palette isn't
    feasible for externally-rendered PNG tiles — instead a subtle CSS filter, e.g. `hue-rotate`
    + `brightness`, nudges the radar colors toward the HUD's cyan/amber identity without
    altering the underlying precipitation-intensity color coding, which must stay legible).
  - Client-side animation: cycle the 4 fetched radar-frame overlays every 800ms
    (`setInterval`, cleared on widget teardown/re-render) for a simple radar-loop effect.
  - A small header strip keeps city name + current temp/desc (reusing the existing text line),
    so the "at a glance" numeric info isn't lost, only the forecast list is replaced by the map.
  - An OSM attribution caption (`© OpenStreetMap contributors`) is required by OSM's tile usage
    policy and rendered as a small caption in the corner of the map.
- **Failure handling:** if the RainViewer frames fetch fails (network error, unexpected
  response shape), render the base map with no radar overlay rather than a broken widget —
  precipitation data is an enhancement, not a hard requirement for the map to be useful.

**Testability:** `latLonToTile`/`tileGrid` are pure functions with exact-value unit tests
(known lat/lon → known tile coordinates, verifiable against public slippy-map examples).
The RainViewer frame-list parsing (given a mocked JSON response, extract the last 4 timestamps
and build the expected tile URLs) is unit-testable. The actual visual composited map (tiles
loading, radar cycling, filter tint) is verified by one live look at the running app, same as
prior UI passes in this project — image-loading/network-dependent rendering isn't something
an automated DOM test can meaningfully assert beyond "the right `<img src>` was set."

## Out of scope

- No pan/zoom interactivity on the map (fixed view centered on the configured city — matches
  "wie im Wetter nach 8 zeigt" as a glance-and-done HUD widget, not an explorable map).
- No new UI for switching the TTS voice from within the app in this pass — switching is a
  direct settings-DB call for this first "audition" round; a proper settings-panel dropdown is
  a natural follow-up once Timo has picked a favorite.
- No changes to the backend Whisper speech-recognition pipeline — this is client-side
  capture/VAD only.

## Acceptance Criteria

- VAD threshold is computed from a live noise-floor sample, not a fixed constant; the
  computation is a pure, unit-tested function.
- Three new Piper voice models are downloaded and resolvable via a `tts_voice` setting;
  switching the setting changes which model `core/tts.py` synthesizes with, without a code
  change.
- The `weather` widget renders a 3×3 OSM tile grid centered on the configured city at zoom 8,
  with a RainViewer radar overlay that cycles through the last 4 available frames, degrading
  gracefully (base map only) if the radar-frame fetch fails.
- `latLonToTile`/`tileGrid` have exact-value unit tests; VAD calibration and voice-name
  resolution have unit tests; existing test suites stay green; `tsc --noEmit` stays clean.
- One final live look at the running app (map rendering, radar cycling, and — separately —
  listening to the new TTS voice candidates) before considering the pass done, consistent with
  how prior visual passes in this project were verified.
