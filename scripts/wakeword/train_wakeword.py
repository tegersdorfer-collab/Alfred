"""Trainiert das Custom-'Mantis'-openWakeWord-Modell aus den synthetischen
Positiv- und gesammelten Negativ-Samples. Läuft in data/wakeword/venv, nicht
im Hauptbackend-Python (siehe Task 1 dieses Plans für den Grund).

Hintergrund (Step 1 dieses Tasks): Die installierte openwakeword==0.6.0
bietet KEINE einzeilige "train_model(positive, negative, output)"-Funktion.
Stattdessen exportiert das Paket:

  - openwakeword.utils.AudioFeatures: berechnet aus 16kHz-PCM-Audio zunächst
    ein Melspektrogramm (ONNX-Modell "melspectrogram.onnx") und daraus mit
    Googles "speech_embedding"-Modell (ONNX "embedding_model.onnx") eine
    Sequenz von 96-dim Embedding-Frames. Diese beiden Feature-Modelle sind
    fest im Paket enthalten (resources/models/) und werden NICHT neu
    trainiert - nur der Klassifikations-Head oben drauf ist "custom".
  - openwakeword.train.Model: ein torch.nn.Module-Wrapper, der aus den
    Embedding-Fenstern (Shape (batch, n_frames, 96), Default n_frames=16)
    eine Wake-Word-Wahrscheinlichkeit (Sigmoid, ein Skalar) vorhersagt.
    model_type="dnn" ergibt ein kleines Fully-Connected-Netz.
    Model.export_to_onnx(...) exportiert per torch.onnx.export GENAU dieses
    Netz mit Eingabeform (1, n_frames, 96) und einem Output-Tensor - das ist
    exakt der Vertrag, den openwakeword.Model (die Inferenz-Wrapper-Klasse in
    model.py) beim Laden eines Custom-ONNX-Modells erwartet: dort wird
    `get_inputs()[0].shape[1]` als Fenstergröße (n_frames) und
    `get_outputs()[0].shape[1]` als Klassenzahl gelesen.
  - Das volle "auto_train"-Sequenzprogramm in openwakeword.train.Model ist auf
    große synthetische Trainingsläufe (zehntausende Steps, stundenlange
    Negativ-Validierungsdaten, mmap-Feature-Dateien) ausgelegt und für unsere
    70 Samples (64 positiv / 6 negativ) nicht praktikabel bzw. nicht sinnvoll
    anwendbar. Stattdessen bauen wir hier eine STARK VEREINFACHTE, aber
    ECHTE End-to-End-Pipeline auf denselben Bausteinen:

    1. Alle WAV-Dateien einlesen und auf 16 kHz mono int16 PCM resamplen.
    2. Aus jeder Datei per AudioFeatures.embed_clips(...) die 96-dim
       Embedding-Frame-Sequenz berechnen (Feature-Extraktion mit den
       mitgelieferten, eingefrorenen ONNX-Feature-Modellen).
    3. Aus jeder Sequenz alle Fenster der festen Länge n_frames=16
       herausschneiden (Sliding Window, Schrittweite 1) - das erzeugt aus den
       wenigen Clips deutlich mehr Trainingsbeispiele und entspricht exakt der
       Fenstergröße, die openwakeword.Model bei der Inferenz an das Modell
       übergibt.
    4. Einen kleinen openwakeword.train.Model(model_type="dnn") auf den
       gelabelten Fenstern (1=Mantis, 0=kein Mantis) trainieren - einfache
       Trainingsschleife mit Adam, ohne die aufwändige auto_train-Sequenz.
    5. Mit Model.export_to_onnx(...) nach data/wakeword/mantis.onnx
       exportieren.

  Dies ist EXPLIZIT eine vereinfachte Pipeline (siehe Task-Brief): ohne
  Augmentierung, ohne Negative-Mining, ohne große Negativ-Validierungsmenge,
  ohne Hyperparameter-Tuning. Für eine produktionsreife Version wären u.a.
  deutlich mehr/vielfältigere Negativ-Daten, Audio-Augmentierung (Rauschen,
  Raumimpulsantworten, Hintergrundgeräusche), "false positive per hour"-
  Validierung auf realistischen Langzeitaufnahmen und systematisches
  Hyperparameter-Tuning nötig.
"""
import logging
import time
from pathlib import Path

import numpy as np
import scipy.io.wavfile as wavfile
from scipy.signal import resample_poly

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("train_wakeword")

POSITIVE_DIR = Path(__file__).parent.parent.parent / "data" / "wakeword" / "samples" / "positive"
NEGATIVE_DIR = Path(__file__).parent.parent.parent / "data" / "wakeword" / "samples" / "negative"
OUTPUT_PATH = Path(__file__).parent.parent.parent / "data" / "wakeword" / "mantis.onnx"

TARGET_SR = 16000
N_FRAMES = 16  # Fenstergröße, die openwakeword.Model bei der Inferenz verwendet (Standard aller offiziellen Modelle)
EMBEDDING_DIM = 96


def load_and_resample(path: Path, target_sr: int = TARGET_SR) -> np.ndarray:
    """Lädt eine WAV-Datei und resampled sie bei Bedarf auf target_sr (16 kHz, int16 PCM mono)."""
    sr, data = wavfile.read(str(path))

    if data.ndim > 1:
        data = data.mean(axis=1).astype(data.dtype)

    if sr != target_sr:
        # Rationales Resampling per scipy (kein librosa/resampy in diesem venv installiert)
        gcd = np.gcd(sr, target_sr)
        up, down = target_sr // gcd, sr // gcd
        data = resample_poly(data.astype(np.float32), up, down)
        data = np.clip(data, -32768, 32767).astype(np.int16)
    elif data.dtype != np.int16:
        data = data.astype(np.int16)

    return data


MIN_CLIP_SAMPLES = 32000  # 2s @ 16kHz: liefert exakt genug Embedding-Frames für ein 16-Frame-Fenster (die
                          # Positiv-Samples sind kurz, ~0.4-1.8s; stärkeres Padding würde sie mit Stille verwässern)


def pad_to_min_length(data: np.ndarray, min_samples: int = MIN_CLIP_SAMPLES) -> np.ndarray:
    """Polstert zu kurze Clips mit Stille auf, damit die Feature-Extraktion (min. 76 Melspektrogramm-
    Frames für ein Embedding-Fenster) nicht mit einer leeren Fenster-Liste fehlschlägt."""
    if data.shape[0] >= min_samples:
        return data
    pad = min_samples - data.shape[0]
    return np.concatenate([data, np.zeros(pad, dtype=data.dtype)])


def extract_windows(features: np.ndarray, n_frames: int = N_FRAMES) -> np.ndarray:
    """Schneidet aus einer Embedding-Sequenz (n_total_frames, EMBEDDING_DIM) alle
    überlappenden Fenster der Länge n_frames heraus (Sliding Window, Schrittweite 1)."""
    if features.shape[0] < n_frames:
        return np.empty((0, n_frames, features.shape[1]), dtype=np.float32)
    windows = [features[i:i + n_frames] for i in range(0, features.shape[0] - n_frames + 1)]
    return np.array(windows, dtype=np.float32)


def build_feature_dataset(files, audio_features, label: int):
    """Lädt alle WAV-Dateien, berechnet openWakeWord-Embeddings und schneidet
    daraus gelabelte Trainingsfenster heraus."""
    all_windows = []
    for f in files:
        clip = pad_to_min_length(load_and_resample(f))
        # Einzelne Clips über die interne _get_embeddings-Methode verarbeiten (statt embed_clips,
        # dessen Batch-Pfad bei batch_size=1 einen Shape-Bug hat) - liefert direkt die
        # (n_frames, EMBEDDING_DIM)-Sequenz für genau diesen einen Clip.
        embeddings = audio_features._get_embeddings(clip)
        windows = extract_windows(embeddings)
        if windows.shape[0] > 0:
            all_windows.append(windows)
        else:
            log.warning(f"Clip zu kurz für ein Fenster (>= {N_FRAMES} Embedding-Frames nötig), übersprungen: {f}")

    if not all_windows:
        return np.empty((0, N_FRAMES, EMBEDDING_DIM), dtype=np.float32), np.empty((0,), dtype=np.float32)

    X = np.concatenate(all_windows, axis=0)
    y = np.full((X.shape[0],), label, dtype=np.float32)
    return X, y


def main() -> None:
    positive_files = sorted(POSITIVE_DIR.glob("*.wav"))
    negative_files = sorted(NEGATIVE_DIR.glob("*.wav"))
    log.info(f"Training mit {len(positive_files)} Positiv- und {len(negative_files)} Negativ-Samples")

    if not positive_files:
        raise RuntimeError(f"Keine Positiv-Samples in {POSITIVE_DIR} — Task 2 zuerst ausführen")
    if not negative_files:
        raise RuntimeError(f"Keine Negativ-Samples in {NEGATIVE_DIR} — Task 3 zuerst ausführen")

    start_time = time.time()

    # Lazy-Import, damit `--help`/Fehlerfälle ohne Torch/openwakeword schneller sind
    import torch
    from openwakeword.utils import AudioFeatures
    from openwakeword.train import Model as OWWModel

    log.info("Lade openWakeWord-Feature-Extraktor (Melspektrogramm + Google speech_embedding, ONNX)...")
    audio_features = AudioFeatures(inference_framework="onnx", device="cpu")

    log.info("Berechne Embeddings und Trainingsfenster für Positiv-Samples...")
    X_pos, y_pos = build_feature_dataset(positive_files, audio_features, label=1)
    log.info(f"  -> {X_pos.shape[0]} positive Fenster aus {len(positive_files)} Clips")

    log.info("Berechne Embeddings und Trainingsfenster für Negativ-Samples...")
    X_neg, y_neg = build_feature_dataset(negative_files, audio_features, label=0)
    log.info(f"  -> {X_neg.shape[0]} negative Fenster aus {len(negative_files)} Clips")

    if X_pos.shape[0] == 0 or X_neg.shape[0] == 0:
        raise RuntimeError("Keine gültigen Trainingsfenster für Positiv- oder Negativ-Klasse extrahiert - "
                           "Samples zu kurz oder Feature-Extraktion fehlgeschlagen")

    X = np.concatenate([X_pos, X_neg], axis=0)
    y = np.concatenate([y_pos, y_neg], axis=0)

    # Einfacher Train/Val-Split (80/20), stratifiziert nach Klasse
    rng = np.random.RandomState(42)
    pos_idx = np.where(y == 1)[0]
    neg_idx = np.where(y == 0)[0]
    rng.shuffle(pos_idx)
    rng.shuffle(neg_idx)

    def split(idx):
        n_val = max(1, int(len(idx) * 0.2))
        return idx[n_val:], idx[:n_val]

    pos_train, pos_val = split(pos_idx)
    neg_train, neg_val = split(neg_idx)
    train_idx = np.concatenate([pos_train, neg_train])
    val_idx = np.concatenate([pos_val, neg_val])
    rng.shuffle(train_idx)
    rng.shuffle(val_idx)

    X_train, y_train = torch.from_numpy(X[train_idx]), torch.from_numpy(y[train_idx])
    X_val, y_val = torch.from_numpy(X[val_idx]), torch.from_numpy(y[val_idx])

    log.info(f"Trainingsfenster: {X_train.shape[0]} (davon {int(y_train.sum())} positiv), "
             f"Validierungsfenster: {X_val.shape[0]} (davon {int(y_val.sum())} positiv)")

    input_shape = (N_FRAMES, EMBEDDING_DIM)
    model = OWWModel(n_classes=1, input_shape=input_shape, model_type="dnn", layer_dim=64, n_blocks=1)
    model.to(model.device)

    n_epochs = 100
    batch_size = 32
    n_train = X_train.shape[0]

    log.info(f"Starte Training: {n_epochs} Epochen, Batch-Size {batch_size}, Modell-Input-Shape {input_shape}")

    for epoch in range(n_epochs):
        perm = torch.randperm(n_train)
        epoch_loss = 0.0
        n_batches = 0
        for i in range(0, n_train, batch_size):
            batch_idx = perm[i:i + batch_size]
            xb = X_train[batch_idx].to(model.device)
            yb = y_train[batch_idx].to(model.device)[..., None]

            model.optimizer.zero_grad()
            preds = model.model(xb)
            loss = model.loss(preds, yb)
            loss.backward()
            model.optimizer.step()

            epoch_loss += loss.item()
            n_batches += 1

        if (epoch + 1) % 10 == 0 or epoch == 0:
            with torch.no_grad():
                val_preds = model.model(X_val.to(model.device))
                val_loss = model.loss(val_preds, y_val.to(model.device)[..., None]).item()
                val_acc = ((val_preds.squeeze() >= 0.5).float().cpu() == y_val).float().mean().item()
            log.info(f"Epoche {epoch + 1}/{n_epochs}: train_loss={epoch_loss / n_batches:.4f} "
                     f"val_loss={val_loss:.4f} val_acc={val_acc:.3f}")

    # Finale Validierungsmetriken
    with torch.no_grad():
        val_preds = model.model(X_val.to(model.device))
        val_acc = ((val_preds.squeeze() >= 0.5).float().cpu() == y_val).float().mean().item()
        val_recall_mask = y_val == 1
        if val_recall_mask.sum() > 0:
            val_recall = ((val_preds.squeeze().cpu() >= 0.5).float()[val_recall_mask] == 1).float().mean().item()
        else:
            val_recall = float("nan")
    log.info(f"Finale Validierung: accuracy={val_acc:.3f} recall={val_recall:.3f}")

    log.info(f"Exportiere Modell nach {OUTPUT_PATH}...")
    model.export_to_onnx(str(OUTPUT_PATH), class_mapping="mantis")

    elapsed = time.time() - start_time
    log.info(f"Training abgeschlossen in {elapsed:.1f}s. Modell gespeichert unter {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
