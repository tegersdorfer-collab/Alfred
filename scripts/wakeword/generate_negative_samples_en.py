"""Erzeugt "Vantis"-Negativ-Samples mit ENGLISCHER Aussprache — sehr ähnlich zu
"Mantis" (nur M->V) und laut Timo ein Wort, das öfter in der Nähe des
Wake-Words fallen wird. Wichtigstes Adversarial-Negativ-Beispiel für diese
Trainingsrunde, siehe generate_negative_samples.py für die deutschen
Adversarial-Wörter (Mantel, Mandant, ...)."""
from pathlib import Path

from generate_positive_samples_en import EN_VOICES, SPEEDS, resolve_voice_paths_en

CARRIER_PHRASES = [
    "{word}",
    "Hey {word}",
    "Okay {word}",
    "{word} are you there",
    "I mean {word}",
    "{word} not Mantis",
]


def build_negative_variants_en(word: str = "Vantis") -> list[dict]:
    variants = []
    for voice in EN_VOICES:
        for speed in SPEEDS:
            for phrase in CARRIER_PHRASES:
                variants.append({"text": phrase.format(word=word), "voice": voice, "speed": speed})
    return variants


def render_all(output_dir: Path, word: str = "Vantis") -> list[Path]:
    from piper import PiperVoice
    from piper.config import SynthesisConfig
    import wave

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    loaded: dict[str, PiperVoice] = {}
    for i, variant in enumerate(build_negative_variants_en(word)):
        voice_name = variant["voice"]
        if voice_name not in loaded:
            onnx, cfg = resolve_voice_paths_en(voice_name)
            loaded[voice_name] = PiperVoice.load(str(onnx), str(cfg))
        voice = loaded[voice_name]
        syn_config = SynthesisConfig(length_scale=1.0 / variant["speed"])
        out_path = output_dir / f"synth_negative_en_{i:04d}_{voice_name}_{variant['speed']}.wav"
        with wave.open(str(out_path), "wb") as wav_file:
            voice.synthesize_wav(variant["text"], wav_file, syn_config=syn_config)
        paths.append(out_path)
    return paths


if __name__ == "__main__":
    out = render_all(Path(__file__).parent.parent.parent / "data" / "wakeword" / "samples" / "negative")
    print(f"Rendered {len(out)} English 'Vantis' negative samples to {out[0].parent}")
