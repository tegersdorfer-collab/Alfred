"""
Sprach-Verarbeitung — gemeinsame Whisper-Transkription + schneller Adress-Check.

Whisper-Teil ist identisch zu dem, was communication/telegram.py bisher exklusiv
für Telegram-Sprachnachrichten nutzte — jetzt hier zentralisiert, damit Phase 5
(Desktop-Sprachsteuerung) dieselbe Logik wiederverwendet statt sie zu duplizieren.
"""
import asyncio
import logging

from core import fast

log = logging.getLogger(__name__)

_whisper_model = None
_whisper_lock = asyncio.Lock()


async def transcribe_audio(audio_path: str) -> str:
    """Transkribiert eine Audiodatei lokal mit Whisper. Gibt leeren String bei Fehler zurück."""
    global _whisper_model
    try:
        import whisper
    except ImportError:
        log.warning("openai-whisper nicht installiert – Audio kann nicht transkribiert werden")
        return ""

    async with _whisper_lock:
        if _whisper_model is None:
            log.info("🔊 Lade Whisper-Modell 'base' …")
            _whisper_model = await asyncio.to_thread(whisper.load_model, "base")

    try:
        result = await asyncio.to_thread(_whisper_model.transcribe, audio_path, language="de")
        return (result.get("text") or "").strip()
    except Exception as e:
        log.error(f"Whisper-Transkription fehlgeschlagen: {e}")
        return ""


async def is_addressed_to_alfred(text: str) -> bool:
    """Schneller Ja/Nein-Check: ist dieser transkribierte Text ein an Alfred
    gerichteter Befehl/Anfrage? Leerer Text spart den LLM-Call."""
    if not text.strip():
        return False
    return await fast.yes_no(
        f"Ist dieser Satz eine Anfrage oder ein Befehl an einen persönlichen KI-Assistenten "
        f"namens Alfred (nicht nur Small Talk mit jemand anderem im Raum)?\n\n\"{text}\""
    )
