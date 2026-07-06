"""Erzeugt vielfältige synthetische Negativ-Trainingssamples (NICHT "Mantis") via
Piper TTS — behebt die zu hohe False-Accept-Rate des ersten Trainingslaufs, der
nur 6 kurze reale Negativ-Clips aus einem einzigen Benchmark-Korpus hatte (zu
wenig Vielfalt, um "alles andere" von "Mantis" zu unterscheiden).

Zwei Kategorien, bewusst getrennt gehalten:
  1. ADVERSARIAL_WORDS: Wörter/Phrasen, die "Mantis" phonetisch ähneln (Mantel,
     Mandant, Fantasie, "man das ist", ...) — die schwierigsten und wertvollsten
     Negativbeispiele, weil sie genau die Verwechslungen abdecken, die in der
     Praxis am ehesten zu Fehlauslösern führen.
  2. EVERYDAY_SENTENCES: normale Alltags-/Alfred-Kommandosätze ohne "Mantis" —
     deckt den generellen "das ist kein Wake-Word"-Fall breiter ab.
"""
from pathlib import Path

from generate_positive_samples import VOICES, SPEEDS, resolve_voice_paths

ADVERSARIAL_WORDS = [
    "Mantel",
    "Mandant",
    "Mandarine",
    "Fantasie",
    "Man das ist",
    "Man tippt das",
    "Manchmal ist das so",
    "Antibiotika",
    "Praktisch ist das",
    "Kantine",
    "Grantig",
    "Man dies und das",
    "Santis",
    "Chantis",
    "Vantis",
]

EVERYDAY_SENTENCES = [
    "Wie ist das Wetter heute?",
    "Wie spät ist es gerade?",
    "Kannst du mir einen Termin eintragen?",
    "Erinnere mich bitte daran, einzukaufen.",
    "Ich habe heute Nacht acht Stunden geschlafen.",
    "Starte bitte den Workflow.",
    "Was steht heute auf meiner Liste?",
    "Trag das bitte im Kalender ein.",
    "Ich möchte einen neuen Task anlegen.",
    "Wie fühlst du dich heute?",
    "Das Essen war wirklich lecker.",
    "Ich gehe jetzt schlafen.",
    "Guten Morgen, wie geht es dir?",
    "Kannst du das für mich nachschauen?",
    "Die Sonne scheint heute schön.",
    "Ich brauche noch Milch und Brot.",
    "Lass uns morgen früh telefonieren.",
    "Das Meeting beginnt um neun Uhr.",
    "Ich bin gerade unterwegs zur Arbeit.",
    "Kannst du das bitte wiederholen?",
]

ALL_PHRASES = ADVERSARIAL_WORDS + EVERYDAY_SENTENCES


def build_negative_variants() -> list[dict]:
    variants = []
    for voice in VOICES:
        for speed in (0.9, 1.15):  # kleinere Speed-Auswahl als bei Positiv-Samples, reicht für Diversität
            for phrase in ALL_PHRASES:
                variants.append({"text": phrase, "voice": voice, "speed": speed})
    return variants


def render_all(output_dir: Path) -> list[Path]:
    from piper import PiperVoice
    from piper.config import SynthesisConfig
    import wave

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    loaded: dict[str, PiperVoice] = {}
    for i, variant in enumerate(build_negative_variants()):
        voice_name = variant["voice"]
        if voice_name not in loaded:
            onnx, cfg = resolve_voice_paths(voice_name)
            loaded[voice_name] = PiperVoice.load(str(onnx), str(cfg))
        voice = loaded[voice_name]
        syn_config = SynthesisConfig(length_scale=1.0 / variant["speed"])
        out_path = output_dir / f"synth_negative_{i:04d}_{voice_name}_{variant['speed']}.wav"
        with wave.open(str(out_path), "wb") as wav_file:
            voice.synthesize_wav(variant["text"], wav_file, syn_config=syn_config)
        paths.append(out_path)
    return paths


if __name__ == "__main__":
    out = render_all(Path(__file__).parent.parent.parent / "data" / "wakeword" / "samples" / "negative")
    print(f"Rendered {len(out)} synthetic negative samples to {out[0].parent}")
