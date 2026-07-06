"""Erzeugt synthetische "Mantis"-Positiv-Samples mit ENGLISCHER Aussprache
(wie das englische Wort "mantis" / Gottesanbeterin, nicht die deutsche
Lautung) — Timo spricht das Wake-Word englisch aus, das reine deutsche
Piper-Training (generate_positive_samples.py) hat das nicht erkannt.

Nutzt englische Piper-Stimmen (data/wakeword/piper_en/, separat von den
deutschen Produktions-Stimmen in data/tts/piper/ gehalten, damit dieses
Trainings-Nebenprodukt nicht mit der echten TTS-Stimmenauswahl kollidiert)."""
from pathlib import Path

EN_VOICES = ["lessac-medium", "amy-medium"]
SPEEDS = [0.85, 1.0, 1.15, 1.3]
CARRIER_PHRASES = [
    "{word}",
    "Hey {word}",
    "Okay {word}",
    "{word} are you there",
]

_MODEL_DIR = Path(__file__).parent.parent.parent / "data" / "wakeword" / "piper_en"


def build_positive_variants_en(word: str = "Mantis") -> list[dict]:
    variants = []
    for voice in EN_VOICES:
        for speed in SPEEDS:
            for phrase in CARRIER_PHRASES:
                variants.append({"text": phrase.format(word=word), "voice": voice, "speed": speed})
    return variants


def resolve_voice_paths_en(voice_name: str) -> tuple[Path, Path]:
    filename = f"en_US-{voice_name}"
    return _MODEL_DIR / f"{filename}.onnx", _MODEL_DIR / f"{filename}.onnx.json"


def render_all(output_dir: Path, word: str = "Mantis") -> list[Path]:
    from piper import PiperVoice
    from piper.config import SynthesisConfig
    import wave

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    loaded: dict[str, PiperVoice] = {}
    for i, variant in enumerate(build_positive_variants_en(word)):
        voice_name = variant["voice"]
        if voice_name not in loaded:
            onnx, cfg = resolve_voice_paths_en(voice_name)
            loaded[voice_name] = PiperVoice.load(str(onnx), str(cfg))
        voice = loaded[voice_name]
        syn_config = SynthesisConfig(length_scale=1.0 / variant["speed"])
        out_path = output_dir / f"positive_en_{i:04d}_{voice_name}_{variant['speed']}.wav"
        with wave.open(str(out_path), "wb") as wav_file:
            voice.synthesize_wav(variant["text"], wav_file, syn_config=syn_config)
        paths.append(out_path)
    return paths


if __name__ == "__main__":
    out = render_all(Path(__file__).parent.parent.parent / "data" / "wakeword" / "samples" / "positive")
    print(f"Rendered {len(out)} English-pronunciation positive samples to {out[0].parent}")
