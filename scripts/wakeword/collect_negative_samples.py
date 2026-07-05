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
