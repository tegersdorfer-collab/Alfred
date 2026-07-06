"""Validiert data/wakeword/mantis.onnx gegen Positiv-/Negativ-Testsamples und
druckt False-Accept-Rate + Recall. Timo bestätigt anhand dieses Reports (plus
eigenem Hörtest) manuell, ob das Modell gut genug für die Integration ist —
siehe docs/superpowers/specs/2026-07-05-vad-wakeword-streaming-design.md.

Scoring-Ansatz (wichtig, siehe Task-5-Report für Details): Der naheliegende Weg
über `openwakeword.model.Model(...).predict(audio)` bzw. `.predict_clip(audio)`
wurde zuerst ausprobiert, liefert aber für dieses Custom-Modell KEINE brauchbaren
Scores (entweder durchgehend 0.0 bei einem einzelnen One-Shot-Predict-Aufruf, oder
bei simuliertem Streaming/`predict_clip` durchgehend hohe Scores >0.5 auch für
Negativ-Samples). Grund: `Model.predict()`/`predict_clip()` verwenden ihren eigenen
internen Preprocessor-Puffer- und Frame-Timing-Mechanismus für Live-Audio-Streams,
der nicht exakt der Fenster-Extraktion entspricht, mit der `train_wakeword.py`
dieses Modell trainiert hat (fester 16-Embedding-Frame-Ausschnitt aus einer
vollständig berechneten Embedding-Sequenz, kein Chunk-Streaming).

Stattdessen repliziert dieses Skript exakt die Feature-Extraktions- und Fenster-
Logik aus `train_wakeword.py`: Audio auf 16 kHz mono int16 PCM resamplen, per
`openwakeword.utils.AudioFeatures._get_embeddings(...)` (denselben eingefrorenen
Melspektrogramm+Embedding-ONNX-Modellen wie beim Training) eine (n_frames, 96)-
Embedding-Sequenz berechnen, alle überlappenden 16-Frame-Fenster (Schrittweite 1)
herausschneiden, jedes Fenster einzeln durch den Klassifikations-Head
(data/wakeword/mantis.onnx, Eingabeform (1, 16, 96)) laufen lassen und den
Maximal-Score über alle Fenster als Score der Datei nehmen. Das reproduziert
exakt den Trainings-/Inferenz-Vertrag und liefert klar getrennte Scores
(Positiv-Samples ~0.97, Negativ-Samples ~0.02 in einem manuellen Testlauf).
"""
import logging
import sys
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("validate_wakeword")

sys.path.insert(0, str(Path(__file__).parent))
from train_wakeword import (  # noqa: E402
    EMBEDDING_DIM,
    N_FRAMES,
    extract_windows,
    load_and_resample,
    pad_to_min_length,
)

POSITIVE_DIR = Path(__file__).parent.parent.parent / "data" / "wakeword" / "samples" / "positive"
NEGATIVE_DIR = Path(__file__).parent.parent.parent / "data" / "wakeword" / "samples" / "negative"
MODEL_PATH = Path(__file__).parent.parent.parent / "data" / "wakeword" / "mantis.onnx"
DETECTION_THRESHOLD = 0.5


def score_file(audio_features, ort_session, input_name: str, wav_path: Path) -> float:
    """Lädt eine WAV-Datei, berechnet Embedding-Fenster (identisch zu train_wakeword.py)
    und gibt den Maximal-Score des Klassifikations-Kopfs über alle Fenster zurück."""
    clip = pad_to_min_length(load_and_resample(wav_path))
    embeddings = audio_features._get_embeddings(clip)
    windows = extract_windows(embeddings)
    if windows.shape[0] == 0:
        log.warning(f"  Übersprungen (zu kurz für ein Fenster, >= {N_FRAMES} Embedding-Frames nötig): {wav_path.name}")
        return 0.0

    scores = []
    for window in windows:
        batch = window[None, ...].astype(np.float32)  # Modell erwartet Batch-Größe 1: (1, N_FRAMES, EMBEDDING_DIM)
        output = ort_session.run(None, {input_name: batch})[0]
        scores.append(float(output.max()))
    return max(scores)


def main() -> None:
    if not MODEL_PATH.exists():
        raise RuntimeError(f"Modell nicht gefunden: {MODEL_PATH} — zuerst train_wakeword.py ausführen")

    import onnxruntime as ort
    from openwakeword.utils import AudioFeatures

    log.info("Lade openWakeWord-Feature-Extraktor (Melspektrogramm + Google speech_embedding, ONNX)...")
    audio_features = AudioFeatures(inference_framework="onnx", device="cpu")

    log.info(f"Lade Klassifikations-Modell: {MODEL_PATH}")
    ort_session = ort.InferenceSession(str(MODEL_PATH))
    input_name = ort_session.get_inputs()[0].name
    expected_shape = ort_session.get_inputs()[0].shape
    log.info(f"  -> Erwartete Eingabeform: {expected_shape}")

    positives = sorted(POSITIVE_DIR.glob("*.wav"))
    negatives = sorted(NEGATIVE_DIR.glob("*.wav"))
    log.info(f"Positiv-Samples: {len(positives)}, Negativ-Samples: {len(negatives)}")

    log.info("Werte Positiv-Samples aus...")
    positive_scores = [(f, score_file(audio_features, ort_session, input_name, f)) for f in positives]

    log.info("Werte Negativ-Samples aus...")
    negative_scores = [(f, score_file(audio_features, ort_session, input_name, f)) for f in negatives]

    true_positives = sum(1 for _f, s in positive_scores if s >= DETECTION_THRESHOLD)
    false_positives = sum(1 for _f, s in negative_scores if s >= DETECTION_THRESHOLD)

    recall = true_positives / len(positives) if positives else 0.0
    false_accept_rate = false_positives / len(negatives) if negatives else 0.0

    print()
    print("=== Detail: Positiv-Samples ===")
    for f, s in positive_scores:
        marker = "OK" if s >= DETECTION_THRESHOLD else "MISS"
        print(f"  [{marker:4}] {s:.4f}  {f.name}")

    print()
    print("=== Detail: Negativ-Samples ===")
    for f, s in negative_scores:
        marker = "FALSE-ACCEPT" if s >= DETECTION_THRESHOLD else "ok"
        print(f"  [{marker:12}] {s:.4f}  {f.name}")

    print()
    print("=== Zusammenfassung ===")
    print(f"Recall (erkannte 'Mantis'-Samples): {true_positives}/{len(positives)} = {recall:.2%}")
    print(f"False-Accept-Rate (fälschlich erkannt): {false_positives}/{len(negatives)} = {false_accept_rate:.2%}")
    print(f"Schwellwert verwendet: {DETECTION_THRESHOLD}")
    print()
    print("Hinweis: Positiv-/Negativ-Samples sind dieselben, die auch für das Training verwendet")
    print("wurden (kein separater Held-out-Split) — dies ist ein Sanity-Check, keine finale Metrik.")
    print("Timo bestätigt das Modell zusätzlich per eigenem Hörtest, bevor Plan B es live einbindet.")

    if recall < 0.70 or false_accept_rate > 0.10:
        print()
        print("ACHTUNG: Recall < 70% oder False-Accept-Rate > 10% — Trainingsdaten/Schwellwert")
        print("vor einem Live-Test mit Timo überprüfen, nicht direkt zu Plan B übergehen.")


if __name__ == "__main__":
    main()
