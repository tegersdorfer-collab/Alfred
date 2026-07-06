"""Interaktiver Rekorder für echte Sprachaufnahmen — schließt die Domain-Gap-Lücke
zwischen rein synthetischem Piper-TTS-Training und echter Mikrofon-/Stimmaufnahme
(siehe Live-Hörtest-Feedback: Modell reagierte auf TTS-Trainingsdaten gut, auf
echte Stimme kaum).

Nimmt für jede Phrase mehrere Wiederholungen auf (16kHz mono, wie vom Training
erwartet) und speichert sie in data/wakeword/samples/positive/ bzw. negative/,
mit "real_"-Präfix, damit sie sich klar von den synthetischen Samples
unterscheiden lassen.

Nutzung (interaktiv, im eigenen Terminal ausführen — braucht echtes Mikrofon):
    data/wakeword/venv/bin/python scripts/wakeword/record_real_samples.py
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
RECORD_SECONDS = 2.0
REPEATS_PER_PHRASE = 6

POSITIVE_DIR = Path(__file__).parent.parent.parent / "data" / "wakeword" / "samples" / "positive"
NEGATIVE_DIR = Path(__file__).parent.parent.parent / "data" / "wakeword" / "samples" / "negative"

# Positiv: das Wake-Word selbst, englisch ausgesprochen, in ein paar Trägersätzen
POSITIVE_PHRASES = [
    "Mantis",
    "Mantis",
    "Hey Mantis",
    "Okay Mantis",
]

# Negativ: das ähnlichste Verwechslungswort (Timos eigener Hinweis) plus
# ein paar normale Sätze mit echter Stimme (nicht nur synthetisch)
NEGATIVE_PHRASES = [
    "Vantis",
    "Vantis",
    "Wie ist das Wetter heute",
    "Kannst du mir helfen",
]


def record_one(seconds: float = RECORD_SECONDS) -> np.ndarray:
    audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    return audio[:, 0]


def save_wav(path: Path, audio: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(audio.tobytes())


def record_phrase_set(phrases: list[str], output_dir: Path, label: str) -> int:
    count = 0
    for phrase in phrases:
        for rep in range(REPEATS_PER_PHRASE):
            input(f"\n[{label}] Sag jetzt: \"{phrase}\"  (Wiederholung {rep + 1}/{REPEATS_PER_PHRASE}) — Enter zum Starten, {RECORD_SECONDS:.0f}s Aufnahme")
            print("🔴 Aufnahme läuft ...")
            audio = record_one()
            out_path = output_dir / f"real_{label}_{phrase.replace(' ', '_')}_{rep:02d}.wav"
            save_wav(out_path, audio)
            print(f"   gespeichert: {out_path.name}")
            count += 1
    return count


def main() -> None:
    print("Echte Sprachaufnahmen für das Mantis-Wake-Word-Training.")
    print(f"Insgesamt {len(POSITIVE_PHRASES) * REPEATS_PER_PHRASE} Positiv- und "
          f"{len(NEGATIVE_PHRASES) * REPEATS_PER_PHRASE} Negativ-Aufnahmen, je {RECORD_SECONDS:.0f}s.")
    print("Sprich normal, wie du es auch live sagen würdest (nicht überdeutlich).\n")

    input("Enter zum Start ...")

    n_pos = record_phrase_set(POSITIVE_PHRASES, POSITIVE_DIR, "positive")
    n_neg = record_phrase_set(NEGATIVE_PHRASES, NEGATIVE_DIR, "negative")

    print(f"\nFertig: {n_pos} Positiv- und {n_neg} Negativ-Aufnahmen gespeichert.")
    print("Als nächstes: data/wakeword/venv/bin/python scripts/wakeword/train_wakeword.py")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        sys.exit(1)
