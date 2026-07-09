"""
Erzeugt Referenz-Audiodateien (via Piper TTS, bekannte Ground-Truth) für den
STT-Latenz-/Qualitäts-Benchmark. Deutsche Sätze unterschiedlicher Länge/
Komplexität, damit der Vergleich zwischen den Whisper-Implementierungen
realistisch ist (kurze Befehle vs. längere Sätze mit Fachbegriffen).
"""
import asyncio
import sys
sys.path.insert(0, ".")

from core import tts

SENTENCES = {
    "kurz_befehl": "Wie ist das Wetter heute?",
    "kurz_frage": "Mantis, wie spät ist es gerade?",
    "mittel_alltag": "Kannst du mir bitte einen Termin für morgen um vierzehn Uhr im Kalender eintragen?",
    "mittel_zahlen": "Ich habe heute Nacht sieben Komma fünf Stunden geschlafen und möchte das eintragen.",
    "lang_komplex": "Erinnere mich bitte daran, dass ich am Dienstag um neun Uhr dreißig einen Zahnarzttermin habe, und sag mir außerdem, ob es an dem Tag regnen soll.",
    "fachbegriffe": "Starte bitte den Skill Factory Workflow und prüfe, ob die Postgres Datenbank noch erreichbar ist.",
}

OUT_DIR = "data/stt_benchmark"


async def main():
    import os
    os.makedirs(OUT_DIR, exist_ok=True)
    for key, text in SENTENCES.items():
        ogg = await tts.synthesize(text, speed=1.0)
        if not ogg:
            print(f"FEHLER: TTS für '{key}' fehlgeschlagen")
            continue
        ogg_path = f"{OUT_DIR}/{key}.ogg"
        with open(ogg_path, "wb") as f:
            f.write(ogg)
        # In WAV konvertieren (manche STT-Engines brauchen WAV/PCM direkt)
        import subprocess
        wav_path = f"{OUT_DIR}/{key}.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-i", ogg_path, "-ar", "16000", "-ac", "1", wav_path],
            capture_output=True, check=True,
        )
        with open(f"{OUT_DIR}/{key}.txt", "w") as f:
            f.write(text)
        print(f"{key}: {wav_path} ({len(text)} Zeichen)")


if __name__ == "__main__":
    asyncio.run(main())
