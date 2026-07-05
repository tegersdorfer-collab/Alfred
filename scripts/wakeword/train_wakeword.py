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
       exportieren, danach per onnxruntime-Selbsttest (ein Forward-Pass mit
       Dummy-Input) verifizieren, dass die exportierte Datei tatsächlich lädt
       und funktioniert.

  Train/Val-Split (WICHTIG, Review-Fix): Der Split in Trainings- und
  Validierungsanteil (80/20, stratifiziert nach Klasse) passiert AUF
  CLIP-EBENE, VOR der Fenster-Extraktion (siehe split_clips_train_val).
  Ursprünglich wurde zuerst über alle Clips hinweg gefenstert (Sliding
  Window, Schrittweite 1) und danach rein positionsbasiert über die
  gesamte, flache Fenster-Liste gesplittet. Das ist Data Leakage: bei
  Schrittweite 1 sind benachbarte Fenster aus demselben Clip fast
  identisch, und ein rein positionsbasierter Split verteilt sie trotzdem
  auf Train UND Val. Das Modell "erkennt" dann denselben Clip wieder,
  statt zu generalisieren - Ergebnis war eine künstlich perfekte
  val_acc=1.0, die nichts über echte Generalisierung aussagt. Nach der
  Korrektur (ganze WAV-Dateien werden VOR dem Fenstern Train oder Val
  zugeordnet) beobachten wir aktuell val_acc=1.000 / val_recall=1.000 mit
  Seed 42 (13 Val-Clips positiv -> 13 Fenster, 1 Val-Clip negativ -> 48
  Fenster). Das ist NICHT dieselbe Zahl wie vorher aus denselben Gründen wie
  vorher: hier ist es der ehrliche Wert eines winzigen, leicht trennbaren
  Val-Sets (Mantis-Rufe klingen sehr unterschiedlich von den 6
  Hintergrundgeräusch-Negativen), nicht das Resultat von Fenster-Leakage.
  Mit nur 6 Negativ-Clips insgesamt bedeutet ein 80/20-Split, dass nur 1
  Negativ-Clip in Val landet; das ist eine bekannte Limitation des kleinen
  Datensatzes (hohe Varianz: ein einziger unglücklich gewählter Val-Clip
  kann das Ergebnis kippen) und wird hier bewusst nicht künstlich umgangen
  (siehe Warnung zur Laufzeit sowie split_clips_train_val). Mit mehr
  Negativ-Clips wäre eine robustere Einschätzung möglich (z.B. K-Fold über
  Clips statt Einzelsplit).

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


def split_clips_train_val(files, val_fraction: float = 0.2, seed: int = 42):
    """Teilt eine Liste von Clip-Pfaden AUF CLIP-EBENE in Train- und Val-Anteil auf
    (~80/20), BEVOR irgendwelche Fenster extrahiert werden. Das ist entscheidend:
    würde man stattdessen erst alle Fenster aller Clips zusammenwerfen und danach
    zufällig auf Positionsebene splitten, landen bei Schrittweite-1-Sliding-Windows
    fast identische, überlappende Fenster desselben Clips sowohl in Train als auch
    in Val (Data Leakage) - das Modell "erinnert" sich dann an den Clip statt zu
    generalisieren, was künstlich hohe/perfekte Val-Metriken erzeugt.

    Rundung: mind. 1 Clip landet in Val, sofern mind. 2 Clips vorhanden sind (sonst
    bleibt alles in Train - ein einzelner Clip lässt sich nicht sinnvoll splitten).
    """
    files = list(files)
    rng = np.random.RandomState(seed)
    idx = np.arange(len(files))
    rng.shuffle(idx)

    if len(files) < 2:
        return [files[i] for i in idx], []

    n_val = max(1, round(len(files) * val_fraction))
    n_val = min(n_val, len(files) - 1)  # mind. 1 Clip muss in Train bleiben

    val_files = [files[i] for i in idx[:n_val]]
    train_files = [files[i] for i in idx[n_val:]]
    return train_files, val_files


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

    # Split AUF CLIP-EBENE (80/20, stratifiziert nach Klasse) - VOR der Fenster-Extraktion.
    # Damit landen alle Fenster eines Clips garantiert komplett in Train ODER Val, nie in
    # beiden (siehe split_clips_train_val-Docstring für die Begründung/Data-Leakage-Problem).
    pos_train_files, pos_val_files = split_clips_train_val(positive_files)
    neg_train_files, neg_val_files = split_clips_train_val(negative_files)
    log.info(f"Clip-Split: Positiv {len(pos_train_files)} train / {len(pos_val_files)} val Clips, "
             f"Negativ {len(neg_train_files)} train / {len(neg_val_files)} val Clips")
    if len(neg_val_files) <= 1:
        log.warning("Nur 1 Negativ-Clip in Val (von insgesamt 6 Negativ-Clips) - bekannte Limitation "
                    "des kleinen Datensatzes. Val-Metriken für die Negativ-Klasse sind entsprechend "
                    "hochvarianz/wenig aussagekräftig; wird hier absichtlich nicht künstlich umgangen.")

    log.info("Berechne Embeddings und Trainingsfenster für Positiv-Train-Clips...")
    X_pos_train, y_pos_train = build_feature_dataset(pos_train_files, audio_features, label=1)
    log.info("Berechne Embeddings und Trainingsfenster für Positiv-Val-Clips...")
    X_pos_val, y_pos_val = build_feature_dataset(pos_val_files, audio_features, label=1)
    log.info(f"  -> {X_pos_train.shape[0]} train / {X_pos_val.shape[0]} val positive Fenster "
             f"aus {len(positive_files)} Clips")

    log.info("Berechne Embeddings und Trainingsfenster für Negativ-Train-Clips...")
    X_neg_train, y_neg_train = build_feature_dataset(neg_train_files, audio_features, label=0)
    log.info("Berechne Embeddings und Trainingsfenster für Negativ-Val-Clips...")
    X_neg_val, y_neg_val = build_feature_dataset(neg_val_files, audio_features, label=0)
    log.info(f"  -> {X_neg_train.shape[0]} train / {X_neg_val.shape[0]} val negative Fenster "
             f"aus {len(negative_files)} Clips")

    if X_pos_train.shape[0] == 0 or X_neg_train.shape[0] == 0:
        raise RuntimeError("Keine gültigen Trainingsfenster für Positiv- oder Negativ-Klasse extrahiert - "
                           "Samples zu kurz oder Feature-Extraktion fehlgeschlagen")

    X_train_np = np.concatenate([X_pos_train, X_neg_train], axis=0)
    y_train_np = np.concatenate([y_pos_train, y_neg_train], axis=0)
    X_val_np = np.concatenate([X_pos_val, X_neg_val], axis=0)
    y_val_np = np.concatenate([y_pos_val, y_neg_val], axis=0)

    rng = np.random.RandomState(42)
    train_perm = rng.permutation(X_train_np.shape[0])
    val_perm = rng.permutation(X_val_np.shape[0]) if X_val_np.shape[0] > 0 else np.array([], dtype=int)

    X_train, y_train = torch.from_numpy(X_train_np[train_perm]), torch.from_numpy(y_train_np[train_perm])
    X_val, y_val = torch.from_numpy(X_val_np[val_perm]), torch.from_numpy(y_val_np[val_perm])

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

    log.info("Selbsttest: lade exportiertes ONNX-Modell erneut und prüfe Forward-Pass mit Dummy-Input...")
    import onnxruntime as ort
    ort_session = ort.InferenceSession(str(OUTPUT_PATH))
    dummy_input = np.random.randn(1, N_FRAMES, EMBEDDING_DIM).astype(np.float32)
    input_name = ort_session.get_inputs()[0].name
    ort_out = ort_session.run(None, {input_name: dummy_input})
    assert ort_out and ort_out[0].shape[0] == 1, f"Unerwartete ONNX-Ausgabe: {ort_out}"
    log.info(f"  -> ONNX-Selbsttest OK, Ausgabe-Shape {ort_out[0].shape}")

    elapsed = time.time() - start_time
    log.info(f"Training abgeschlossen in {elapsed:.1f}s. Modell gespeichert unter {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
