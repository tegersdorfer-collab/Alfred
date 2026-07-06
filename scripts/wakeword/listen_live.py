"""
Live-Hörtest für das trainierte "Mantis"-Wake-Word-Modell.

Nimmt kontinuierlich Mikrofon-Audio auf (16kHz mono), berechnet denselben
openWakeWord-Embedding-Pfad wie train_wakeword.py/validate_wakeword.py und
druckt den aktuellen Score in Echtzeit. Sag "Mantis" und beobachte, ob/wie
sicher der Score über die Schwelle springt — das ist der Hörtest, den Timo
manuell bestätigt, bevor das Modell in die Streaming-Pipeline eingebunden wird
(siehe docs/superpowers/plans/2026-07-05-vad-wakeword-streaming.md, Task 6).

Läuft in der isolierten data/wakeword/venv (Python 3.11), nicht im
Hauptbackend-Python — Nutzung:
    data/wakeword/venv/bin/python scripts/wakeword/listen_live.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import sounddevice as sd

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("listen_live")

sys.path.insert(0, str(Path(__file__).parent))
from train_wakeword import EMBEDDING_DIM, N_FRAMES, TARGET_SR, embed_clip, extract_windows  # noqa: E402

MODEL_PATH = Path(__file__).parent.parent.parent / "data" / "wakeword" / "mantis.onnx"
DETECTION_THRESHOLD = 0.5
CHUNK_SECONDS = 0.5   # wie oft neu bewertet wird
BUFFER_SECONDS = 2.0  # Rolling-Window-Länge (genug für ein 16-Frame-Embedding-Fenster)


def main() -> None:
    if not MODEL_PATH.exists():
        raise SystemExit(f"Modell nicht gefunden: {MODEL_PATH} — erst scripts/wakeword/train_wakeword.py laufen lassen")

    from openwakeword.utils import AudioFeatures

    log.info("Lade openWakeWord-Feature-Extraktor und Mantis-Klassifikator ...")
    audio_features = AudioFeatures(inference_framework="onnx", device="cpu")
    ort_session = ort.InferenceSession(str(MODEL_PATH))
    input_name = ort_session.get_inputs()[0].name

    buffer = np.zeros(0, dtype=np.int16)
    buffer_samples = int(BUFFER_SECONDS * TARGET_SR)
    chunk_samples = int(CHUNK_SECONDS * TARGET_SR)

    log.info(f"Mikrofon läuft (16kHz mono). Sag \"Mantis\" — Schwelle = {DETECTION_THRESHOLD}. Strg+C zum Beenden.\n")

    def callback(indata, frames, time_info, status):
        nonlocal buffer
        if status:
            log.warning(f"Audio-Status: {status}")
        chunk = indata[:, 0]
        buffer = np.concatenate([buffer, chunk])[-buffer_samples:]

        if buffer.shape[0] < buffer_samples:
            return  # noch nicht genug Audio für ein volles Fenster

        embeddings = embed_clip(audio_features, buffer)
        windows = extract_windows(embeddings, n_frames=N_FRAMES)
        if windows.shape[0] == 0:
            return

        scores = []
        for window in windows:
            inp = window[np.newaxis, :, :].astype(np.float32)
            out = ort_session.run(None, {input_name: inp})
            scores.append(float(np.array(out[0]).flatten()[0]))
        score = max(scores)

        marker = "🟢 MANTIS ERKANNT" if score >= DETECTION_THRESHOLD else "  "
        bar = "█" * int(score * 40)
        print(f"\r{marker}  {score:.3f}  {bar:<40}", end="", flush=True)

    with sd.InputStream(
        samplerate=TARGET_SR,
        channels=1,
        dtype="int16",
        blocksize=chunk_samples,
        callback=callback,
    ):
        try:
            while True:
                sd.sleep(200)
        except KeyboardInterrupt:
            print("\nBeendet.")


if __name__ == "__main__":
    main()
