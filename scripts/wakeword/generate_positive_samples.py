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


VOICE_MODELS: dict[str, str] = {
    "thorsten-high": "de_DE-thorsten-high",
    "thorsten_emotional-medium": "de_DE-thorsten_emotional-medium",
    "karlsson-low": "de_DE-karlsson-low",
    "pavoque-low": "de_DE-pavoque-low",
}


def resolve_voice_paths(voice_name: str) -> tuple[Path, Path]:
    """Lokale Neuimplementierung von core.tts.resolve_voice_paths.

    core.tts importiert core.db, das wiederum psycopg2/pgvector lädt und eine
    echte Postgres-Verbindung voraussetzt (config.DATABASE_URL) — völlig fehl
    am Platz für ein Offline-Skript, das in der isolierten data/wakeword/venv
    läuft. Die Modell-Verzeichnis-Konvention und VOICE_MODELS-Zuordnung sind
    hier dupliziert, aber bewusst 1:1 aus core/tts.py übernommen.
    """
    model_dir = Path(__file__).parent.parent.parent / "data" / "tts" / "piper"
    filename = VOICE_MODELS[voice_name]
    onnx = model_dir / f"{filename}.onnx"
    cfg = model_dir / f"{filename}.onnx.json"
    return onnx, cfg


def render_all(output_dir: Path, word: str = "Mantis") -> list[Path]:
    """Rendert jede Variante als WAV via Piper direkt (nicht core.tts, da dieses
    Skript in der isolierten data/wakeword/venv läuft, nicht im Hauptbackend-Prozess)."""
    from piper import PiperVoice
    from piper.config import SynthesisConfig
    import wave

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
