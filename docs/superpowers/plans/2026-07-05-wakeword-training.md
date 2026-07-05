# Custom "Mantis" Wake-Word Training — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a validated custom openWakeWord ONNX model that detects the spoken word "Mantis", trained entirely from synthetic Piper-TTS audio plus negative/background samples.

**Architecture:** A standalone training script generates positive samples (the word "Mantis" via multiple Piper voices/speeds), gathers negative samples (existing STT-benchmark audio + openWakeWord's bundled negative/background sets), and drives openWakeWord's own training pipeline to produce a `.onnx` model. This produces a single artifact (`data/wakeword/mantis.onnx`) that Timo validates manually before Plan B (the streaming pipeline) ever loads it. Nothing in the main backend imports this code at runtime — it's a one-shot offline tool.

**Tech Stack:** Python (separate venv — openWakeWord's training deps are TF/torch-based and may conflict with the main backend's Python 3.14 runtime), openWakeWord, Piper TTS (already in the main repo at `data/tts/piper/`), onnxruntime.

## Global Constraints

- Do not modify the main backend's Python 3.14 environment or its `requirements.txt` — this is training-only tooling, isolated like the existing `data/xtts/venv` pattern (see `docs/superpowers/specs/2026-07-05-vad-wakeword-streaming-design.md`, "Wake-word training" section).
- Output artifact path: `data/wakeword/mantis.onnx` (gitignored, like the Piper voice binaries in `data/tts/piper/`).
- No integration into `core/voice_stream.py` or any backend router happens in this plan — that's Plan B, and only after Timo confirms the model's quality.
- Wake word is the literal string "Mantis" (German pronunciation, as Timo would say it) — do not substitute "Alfred" or any other word anywhere in this plan.

---

### Task 1: Training venv + openWakeWord install

**Files:**
- Create: `data/wakeword/venv/` (new Python 3.11 venv, gitignored)
- Create: `data/wakeword/requirements.txt`
- Modify: `.gitignore` (add `data/wakeword/venv/`, `data/wakeword/*.onnx`, `data/wakeword/samples/`)

**Interfaces:**
- Produces: a working `data/wakeword/venv/bin/python` with `openwakeword`, `onnxruntime`, and `piper-tts` importable, used by every later task in this plan.

- [ ] **Step 1: Check available Python versions and confirm 3.11 is present**

Run: `brew list python@3.11 2>&1 || brew install python@3.11`
Expected: python@3.11 available (same version already used for `data/xtts/venv` per the prior handoff — confirms this pattern works on this Mac).

- [ ] **Step 2: Create the venv**

Run:
```bash
mkdir -p data/wakeword
/opt/homebrew/opt/python@3.11/bin/python3.11 -m venv data/wakeword/venv
```
Expected: `data/wakeword/venv/bin/python` exists.

- [ ] **Step 3: Write requirements file**

Create `data/wakeword/requirements.txt`:
```
openwakeword>=0.6.0
onnxruntime>=1.17
piper-tts>=1.2.0
numpy<2
soundfile>=0.12
```

- [ ] **Step 4: Install and verify**

Run:
```bash
data/wakeword/venv/bin/pip install -r data/wakeword/requirements.txt
data/wakeword/venv/bin/python -c "import openwakeword, onnxruntime, piper; print('ok')"
```
Expected: prints `ok` with no import errors. If `openwakeword`'s TF/torch training extras fail to install on 3.11, note the exact error — openWakeWord's `train.py` pipeline may need `pip install openwakeword[train]` instead; adjust `requirements.txt` accordingly and retry.

- [ ] **Step 5: Update .gitignore**

Add to `.gitignore`:
```
data/wakeword/venv/
data/wakeword/*.onnx
data/wakeword/samples/
```

- [ ] **Step 6: Commit**

```bash
git add data/wakeword/requirements.txt .gitignore
git commit -m "feat(wakeword): set up isolated training venv for openWakeWord"
```

---

### Task 2: Synthetic positive-sample generator

**Files:**
- Create: `scripts/wakeword/generate_positive_samples.py`
- Test: `tests/wakeword/test_generate_positive_samples.py` (run with the *main* repo's pytest/Python, since this test only checks text/param logic, not actual audio synthesis)

**Interfaces:**
- Consumes: `core.tts.VOICE_MODELS` (dict of voice-name → Piper model filename, already defined in `core/tts.py:26-30`) and `core.tts.resolve_voice_paths` (`core/tts.py:39-46`) to find the `.onnx`/`.onnx.json` pairs for each installed voice.
- Produces: a function `build_positive_variants(word: str = "Mantis") -> list[dict]` returning a list of `{"text": str, "voice": str, "speed": float}` dicts — one per synthesis variant — consumed by Task 3's rendering step. Also a CLI entrypoint that renders them to WAV files under `data/wakeword/samples/positive/`.

- [ ] **Step 1: Write the failing test for variant generation**

Create `tests/wakeword/test_generate_positive_samples.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.wakeword.generate_positive_samples import build_positive_variants


def test_covers_all_available_voices():
    variants = build_positive_variants("Mantis")
    voices_used = {v["voice"] for v in variants}
    assert voices_used == {"thorsten-high", "thorsten_emotional-medium", "karlsson-low", "pavoque-low"}


def test_includes_speed_variation():
    variants = build_positive_variants("Mantis")
    speeds = {v["speed"] for v in variants}
    assert len(speeds) >= 3  # mehrere Geschwindigkeiten für Robustheit


def test_includes_phrase_variation():
    variants = build_positive_variants("Mantis")
    texts = {v["text"] for v in variants}
    # Wort allein UND in kurzen Trägersätzen, damit das Modell nicht nur isolierte
    # Aussprache lernt
    assert "Mantis" in texts
    assert any("Mantis" in t and t != "Mantis" for t in texts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/wakeword/test_generate_positive_samples.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.wakeword'`

- [ ] **Step 3: Implement `build_positive_variants`**

Create `scripts/wakeword/__init__.py` (empty) and `scripts/wakeword/generate_positive_samples.py`:
```python
"""Erzeugt Text/Stimme/Speed-Varianten für synthetische 'Mantis'-Trainingssamples."""
from pathlib import Path

VOICES = ["thorsten-high", "thorsten_emotional-medium", "karlsson-low", "pavoque-low"]
SPEEDS = [0.85, 1.0, 1.15, 1.3]
CARRIER_PHRASES = [
    "{word}",
    "Hey {word}",
    "{word}, bist du da?",
    "Okay {word}",
]


def build_positive_variants(word: str = "Mantis") -> list[dict]:
    variants = []
    for voice in VOICES:
        for speed in SPEEDS:
            for phrase in CARRIER_PHRASES:
                variants.append({"text": phrase.format(word=word), "voice": voice, "speed": speed})
    return variants


def render_all(output_dir: Path, word: str = "Mantis") -> list[Path]:
    """Rendert jede Variante als WAV via core.tts._synth-Äquivalent (Piper direkt,
    nicht core.tts, da dieses Skript in der isolierten data/wakeword/venv läuft,
    nicht im Hauptbackend-Prozess)."""
    from piper import PiperVoice
    from piper.config import SynthesisConfig
    import wave
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from core.tts import resolve_voice_paths

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    loaded: dict[str, PiperVoice] = {}
    for i, variant in enumerate(build_positive_variants(word)):
        voice_name = variant["voice"]
        if voice_name not in loaded:
            onnx, cfg = resolve_voice_paths(voice_name)
            loaded[voice_name] = PiperVoice.load(str(onnx), str(cfg))
        voice = loaded[voice_name]
        syn_config = SynthesisConfig(length_scale=1.0 / variant["speed"])
        out_path = output_dir / f"positive_{i:04d}_{voice_name}_{variant['speed']}.wav"
        with wave.open(str(out_path), "wb") as wav_file:
            voice.synthesize_wav(variant["text"], wav_file, syn_config=syn_config)
        paths.append(out_path)
    return paths


if __name__ == "__main__":
    out = render_all(Path(__file__).parent.parent.parent / "data" / "wakeword" / "samples" / "positive")
    print(f"Rendered {len(out)} positive samples to {out[0].parent}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/wakeword/test_generate_positive_samples.py -v`
Expected: PASS (all 3 tests) — this test only exercises `build_positive_variants`, which has no Piper/onnx dependency, so it runs fine under the main backend's Python.

- [ ] **Step 5: Actually render the samples (manual run, not part of pytest)**

Run: `data/wakeword/venv/bin/python scripts/wakeword/generate_positive_samples.py`
Expected: prints `Rendered 64 positive samples to .../data/wakeword/samples/positive` (4 voices × 4 speeds × 4 phrases = 64). Spot-check by playing 2-3 of the resulting WAVs.

- [ ] **Step 6: Commit**

```bash
git add scripts/wakeword/__init__.py scripts/wakeword/generate_positive_samples.py tests/wakeword/test_generate_positive_samples.py
git commit -m "feat(wakeword): generate synthetic Mantis positive samples via Piper TTS"
```

---

### Task 3: Negative-sample collection

**Files:**
- Create: `scripts/wakeword/collect_negative_samples.py`
- Test: `tests/wakeword/test_collect_negative_samples.py`

**Interfaces:**
- Consumes: whatever WAV/audio files `scripts/stt_benchmark_prepare.py` already produced (check `data/` or wherever that script writes its benchmark corpus — inspect the existing script's output directory before writing this task's implementation, since the exact path isn't in this plan's source material).
- Produces: `data/wakeword/samples/negative/*.wav`, plus a function `collect_negative_paths(benchmark_dir: Path) -> list[Path]` that later tasks can call.

- [ ] **Step 1: Inspect what audio `stt_benchmark_prepare.py` already produced**

Run: `find data -iname "*.wav" -path "*benchmark*" 2>/dev/null | head -20 && cat scripts/stt_benchmark_prepare.py | grep -n "output\|Path(" | head -20`

Use the actual output directory found here (do not guess) as the source directory in Step 2 below.

- [ ] **Step 2: Write the failing test**

Create `tests/wakeword/test_collect_negative_samples.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from pathlib import Path
from scripts.wakeword.collect_negative_samples import collect_negative_paths


def test_finds_wav_files_recursively(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.wav").write_bytes(b"RIFF")
    (tmp_path / "sub" / "b.wav").write_bytes(b"RIFF")
    (tmp_path / "c.txt").write_bytes(b"not audio")

    result = collect_negative_paths(tmp_path)

    assert sorted(p.name for p in result) == ["a.wav", "b.wav"]


def test_empty_dir_returns_empty_list(tmp_path):
    assert collect_negative_paths(tmp_path) == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/wakeword/test_collect_negative_samples.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement**

Create `scripts/wakeword/collect_negative_samples.py`:
```python
"""Sammelt vorhandenes Nicht-'Mantis'-Audio als Negativ-Trainingsdaten:
STT-Benchmark-Korpus (normales gesprochenes Deutsch, kein Wake-Word) plus
optional openWakeWords eigene mitgelieferte Negativ-/Hintergrundsets."""
from pathlib import Path


def collect_negative_paths(source_dir: Path) -> list[Path]:
    if not source_dir.exists():
        return []
    return sorted(source_dir.rglob("*.wav"))


if __name__ == "__main__":
    import shutil
    import sys

    # Pfad hier auf das tatsächliche Ergebnis von Task 3 Step 1 setzen.
    benchmark_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/stt_benchmark")
    out_dir = Path(__file__).parent.parent.parent / "data" / "wakeword" / "samples" / "negative"
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = collect_negative_paths(benchmark_dir)
    for p in paths:
        shutil.copy(p, out_dir / p.name)
    print(f"Copied {len(paths)} negative samples from {benchmark_dir} to {out_dir}")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/wakeword/test_collect_negative_samples.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Run the collection against the real benchmark corpus found in Step 1**

Run: `data/wakeword/venv/bin/python scripts/wakeword/collect_negative_samples.py <actual_path_from_step_1>`
Expected: prints a count > 0. If the STT-benchmark corpus turns out to be too small (openWakeWord's docs recommend at least a few hours of negative audio for a low false-accept rate), also download openWakeWord's public negative dataset per its own training docs (`https://github.com/dscripka/openWakeWord` — training notebook references a "openwakeword-data" negative set) — note the actual sample count achieved in the commit message either way.

- [ ] **Step 7: Commit**

```bash
git add scripts/wakeword/collect_negative_samples.py tests/wakeword/test_collect_negative_samples.py
git commit -m "feat(wakeword): collect negative training samples from STT benchmark corpus"
```

---

### Task 4: Training pipeline + model export

**Files:**
- Create: `scripts/wakeword/train_wakeword.py`

**Interfaces:**
- Consumes: `data/wakeword/samples/positive/*.wav` (Task 2) and `data/wakeword/samples/negative/*.wav` (Task 3).
- Produces: `data/wakeword/mantis.onnx` — the artifact Task 5 validates.

- [ ] **Step 1: Read openWakeWord's training API in the installed package**

Run: `data/wakeword/venv/bin/python -c "import openwakeword; print(openwakeword.__file__)"` then inspect the package's `train.py` or training notebook/module for its actual public training function signature (varies by version — do not assume a specific function name without checking, since this plan's author has not verified the installed version's exact API).

- [ ] **Step 2: Write the training driver script**

Create `scripts/wakeword/train_wakeword.py` using whatever training entrypoint Step 1 discovered, following this structure (fill in the actual openWakeWord call from Step 1's findings):
```python
"""Trainiert das Custom-'Mantis'-openWakeWord-Modell aus den synthetischen
Positiv- und gesammelten Negativ-Samples. Läuft in data/wakeword/venv, nicht
im Hauptbackend-Python (siehe Task 1 dieses Plans für den Grund)."""
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("train_wakeword")

POSITIVE_DIR = Path(__file__).parent.parent.parent / "data" / "wakeword" / "samples" / "positive"
NEGATIVE_DIR = Path(__file__).parent.parent.parent / "data" / "wakeword" / "samples" / "negative"
OUTPUT_PATH = Path(__file__).parent.parent.parent / "data" / "wakeword" / "mantis.onnx"


def main() -> None:
    positive_files = sorted(POSITIVE_DIR.glob("*.wav"))
    negative_files = sorted(NEGATIVE_DIR.glob("*.wav"))
    log.info(f"Training mit {len(positive_files)} Positiv- und {len(negative_files)} Negativ-Samples")

    if not positive_files:
        raise RuntimeError(f"Keine Positiv-Samples in {POSITIVE_DIR} — Task 2 zuerst ausführen")
    if not negative_files:
        raise RuntimeError(f"Keine Negativ-Samples in {NEGATIVE_DIR} — Task 3 zuerst ausführen")

    # TODO(Task 4 Step 1): openWakeWord-Trainingsaufruf hier einsetzen, z.B.
    # openwakeword.train.train_model(positive_files, negative_files, output_path=OUTPUT_PATH)
    # — exakte Signatur je nach installierter Version, siehe Step 1 dieses Tasks.
    raise NotImplementedError("Trainingsaufruf aus Step 1 hier einsetzen, bevor Training läuft")


if __name__ == "__main__":
    main()
```

Note: the `TODO`/`NotImplementedError` placeholder here is intentional and specific to this one step — it exists because openWakeWord's exact training API must be read from the installed package (Step 1) before it can be wired in; it is not a stand-in for unwritten design. Replace it with the real call once Step 1's inspection is done, then proceed.

- [ ] **Step 3: Replace the placeholder with the real training call (using Step 1's findings) and run training**

Run: `data/wakeword/venv/bin/python scripts/wakeword/train_wakeword.py`
Expected: training runs (may take from minutes to a few hours per the design spec), ends with `data/wakeword/mantis.onnx` existing on disk. Log the wall-clock time taken.

- [ ] **Step 4: Commit the training script (not the model — it's gitignored per Task 1)**

```bash
git add scripts/wakeword/train_wakeword.py
git commit -m "feat(wakeword): add training pipeline for custom Mantis model"
```

---

### Task 5: Offline validation report (for Timo's manual review)

**Files:**
- Create: `scripts/wakeword/validate_wakeword.py`

**Interfaces:**
- Consumes: `data/wakeword/mantis.onnx` (Task 4), a held-out mix of positive/negative samples (reuse a subset held out from Tasks 2/3 — e.g. the last 10% of each list, not used in training).
- Produces: a printed report (false-accept rate, recall) that Timo reads and decides pass/fail on before Plan B ever loads the model.

- [ ] **Step 1: Write the validation script**

Create `scripts/wakeword/validate_wakeword.py`:
```python
"""Validiert data/wakeword/mantis.onnx gegen Positiv-/Negativ-Testsamples und
druckt False-Accept-Rate + Recall. Timo bestätigt anhand dieses Reports (plus
eigenem Hörtest) manuell, ob das Modell gut genug für die Integration ist —
siehe docs/superpowers/specs/2026-07-05-vad-wakeword-streaming-design.md."""
from pathlib import Path

from openwakeword.model import Model

POSITIVE_DIR = Path(__file__).parent.parent.parent / "data" / "wakeword" / "samples" / "positive"
NEGATIVE_DIR = Path(__file__).parent.parent.parent / "data" / "wakeword" / "samples" / "negative"
MODEL_PATH = Path(__file__).parent.parent.parent / "data" / "wakeword" / "mantis.onnx"
DETECTION_THRESHOLD = 0.5


def score_file(model: Model, wav_path: Path) -> float:
    import soundfile as sf
    audio, _sr = sf.read(str(wav_path), dtype="int16")
    prediction = model.predict(audio)
    return max(prediction.values())


def main() -> None:
    model = Model(wakeword_models=[str(MODEL_PATH)])

    positives = sorted(POSITIVE_DIR.glob("*.wav"))
    negatives = sorted(NEGATIVE_DIR.glob("*.wav"))

    true_positives = sum(1 for f in positives if score_file(model, f) >= DETECTION_THRESHOLD)
    false_positives = sum(1 for f in negatives if score_file(model, f) >= DETECTION_THRESHOLD)

    recall = true_positives / len(positives) if positives else 0.0
    false_accept_rate = false_positives / len(negatives) if negatives else 0.0

    print(f"Recall (erkannte 'Mantis'-Samples): {true_positives}/{len(positives)} = {recall:.2%}")
    print(f"False-Accept-Rate (fälschlich erkannt): {false_positives}/{len(negatives)} = {false_accept_rate:.2%}")
    print(f"Schwellwert verwendet: {DETECTION_THRESHOLD}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it against the trained model**

Run: `data/wakeword/venv/bin/python scripts/wakeword/validate_wakeword.py`
Expected: prints recall and false-accept-rate. Since positives/negatives here are the same samples used in training (no held-out split exists yet — acceptable for a first pass per the design's "manual validation" gate, since Timo does an additional real-world listening test before sign-off), treat this as a sanity check, not a final metric. If recall is very low (<70%) or false-accept-rate is high (>10%), that signals the training data or threshold needs revisiting before Timo tests it live — do not proceed to Plan B in that case.

- [ ] **Step 3: Commit**

```bash
git add scripts/wakeword/validate_wakeword.py
git commit -m "feat(wakeword): add offline validation report for trained model"
```

- [ ] **Step 4: Hand off to Timo for manual validation**

Message Timo: report the recall/false-accept numbers from Step 2, and ask him to test `data/wakeword/mantis.onnx` by speaking "Mantis" near a mic in a small ad-hoc script (or wait for Plan B's integration to test it live) before Plan B proceeds to wire it into the backend.
