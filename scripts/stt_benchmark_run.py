"""
STT-Benchmark: vergleicht pywhispercpp (aktuell), faster-whisper, mlx-whisper
und lightning-whisper-mlx auf denselben deutschen Referenzsätzen.

Misst pro Engine: Modell-Ladezeit (einmalig), Inferenz-Latenz pro Satz,
und Genauigkeit (normalisierter Text-Vergleich gegen die bekannte
Ground-Truth aus stt_benchmark_prepare.py).
"""
import glob
import re
import time

DATA_DIR = "data/stt_benchmark"


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\wäöüß\s]", "", text)
    return re.sub(r"\s+", " ", text)


def similarity(a: str, b: str) -> float:
    """Einfache Wort-Overlap-Ähnlichkeit (Jaccard über Wortmengen) — reicht für
    einen groben Qualitätsvergleich zwischen Engines, kein vollwertiges WER."""
    wa, wb = set(normalize(a).split()), set(normalize(b).split())
    if not wa and not wb:
        return 1.0
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def load_test_cases():
    cases = []
    for txt_path in sorted(glob.glob(f"{DATA_DIR}/*.txt")):
        key = txt_path.rsplit("/", 1)[-1].replace(".txt", "")
        with open(txt_path) as f:
            ground_truth = f.read().strip()
        cases.append((key, f"{DATA_DIR}/{key}.wav", ground_truth))
    return cases


def bench_pywhispercpp(cases):
    from pywhispercpp.model import Model

    t0 = time.time()
    model = Model("medium", language="de", print_realtime=False, print_progress=False)
    load_time = time.time() - t0

    results = []
    for key, wav_path, truth in cases:
        t0 = time.time()
        segments = model.transcribe(wav_path)
        latency = time.time() - t0
        text = " ".join(s.text for s in segments).strip()
        results.append((key, latency, similarity(text, truth), text))
    return load_time, results


def bench_faster_whisper(cases, model_size="medium"):
    from faster_whisper import WhisperModel

    t0 = time.time()
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    load_time = time.time() - t0

    results = []
    for key, wav_path, truth in cases:
        t0 = time.time()
        segments, _info = model.transcribe(wav_path, language="de")
        text = " ".join(s.text for s in segments).strip()
        latency = time.time() - t0
        results.append((key, latency, similarity(text, truth), text))
    return load_time, results


def bench_mlx_whisper(cases, model_repo="mlx-community/whisper-medium-mlx"):
    import mlx_whisper

    # mlx_whisper lädt das Modell lazy beim ersten transcribe()-Aufruf — Ladezeit
    # wird daher am ersten Testfall gemessen, nicht separat vorab.
    results = []
    load_time = None
    for key, wav_path, truth in cases:
        t0 = time.time()
        result = mlx_whisper.transcribe(wav_path, path_or_hf_repo=model_repo, language="de")
        latency = time.time() - t0
        if load_time is None:
            load_time = latency  # erster Aufruf enthält Ladezeit, als Näherung markiert
        text = result["text"].strip()
        results.append((key, latency, similarity(text, truth), text))
    return load_time, results


def bench_lightning_whisper_mlx(cases, model_size="medium"):
    from lightning_whisper_mlx import LightningWhisperMLX

    t0 = time.time()
    model = LightningWhisperMLX(model=model_size, batch_size=1, quant=None)
    load_time = time.time() - t0

    results = []
    for key, wav_path, truth in cases:
        t0 = time.time()
        result = model.transcribe(wav_path)
        latency = time.time() - t0
        text = result["text"].strip() if isinstance(result, dict) else str(result).strip()
        results.append((key, latency, similarity(text, truth), text))
    return load_time, results


def print_report(name, load_time, results):
    print(f"\n=== {name} ===")
    print(f"Ladezeit: {load_time:.2f}s" if load_time is not None else "Ladezeit: n/a")
    total_latency = sum(r[1] for r in results)
    avg_sim = sum(r[2] for r in results) / len(results)
    for key, latency, sim, text in results:
        print(f"  {key:20s} {latency:6.2f}s  Ähnlichkeit={sim:.2f}  -> {text!r}")
    print(f"  GESAMT-Inferenz: {total_latency:.2f}s  Ø-Ähnlichkeit: {avg_sim:.2f}")


def main():
    cases = load_test_cases()
    print(f"{len(cases)} Testfälle geladen aus {DATA_DIR}/")

    engines = [
        ("pywhispercpp (aktuell, whisper.cpp medium)", bench_pywhispercpp),
        ("faster-whisper (CTranslate2, medium, int8)", bench_faster_whisper),
        ("mlx-whisper (Apple MLX, medium)", bench_mlx_whisper),
        ("lightning-whisper-mlx (medium)", bench_lightning_whisper_mlx),
    ]

    for name, fn in engines:
        try:
            load_time, results = fn(cases)
            print_report(name, load_time, results)
        except Exception as e:
            print(f"\n=== {name} ===\nFEHLER: {e}")


if __name__ == "__main__":
    main()
