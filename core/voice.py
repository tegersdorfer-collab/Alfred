"""
Sprach-Verarbeitung — gemeinsame Whisper-Transkription + schneller Adress-Check.

Nutzt whisper.cpp (via pywhispercpp) statt des reinen PyTorch-openai-whisper —
auf Apple Silicon läuft das über Metal statt nur CPU und ist damit deutlich
schneller bei gleicher Modellqualität (siehe docs/superpowers/plans, Phase 5a-
Nachbesserung). Whisper-Teil ist identisch zu dem, was communication/telegram.py
bisher exklusiv für Telegram-Sprachnachrichten nutzte — jetzt hier zentralisiert,
damit Phase 5 (Desktop-Sprachsteuerung) dieselbe Logik wiederverwendet statt sie
zu duplizieren.
"""
import asyncio
import logging

import config
from core import fast

log = logging.getLogger(__name__)

_whisper_model = None
_whisper_lock = asyncio.Lock()


async def transcribe_audio(audio_path: str) -> str:
    """Transkribiert eine Audiodatei lokal mit whisper.cpp. Gibt leeren String bei Fehler zurück."""
    global _whisper_model
    try:
        from pywhispercpp.model import Model
    except ImportError:
        log.warning("pywhispercpp nicht installiert – Audio kann nicht transkribiert werden")
        return ""

    async with _whisper_lock:
        if _whisper_model is None:
            log.info("🔊 Lade whisper.cpp-Modell 'medium' …")
            _whisper_model = await asyncio.to_thread(
                Model, "medium", language="de", print_realtime=False, print_progress=False
            )

    try:
        segments = await asyncio.to_thread(_whisper_model.transcribe, audio_path)
        return " ".join(s.text for s in segments).strip()
    except Exception as e:
        log.error(f"Whisper-Transkription fehlgeschlagen: {e}")
        return ""


async def is_addressed_to_alfred(text: str) -> bool:
    """Schneller Ja/Nein-Check: ist dieser transkribierte Text ein an Alfred
    gerichteter Befehl/Anfrage? Leerer Text spart den LLM-Call.

    Zwei Layer: (1) Keyword-Vorfilter — wird "Alfred" explizit genannt, sofort JA
    ohne LLM-Call (Latenz ~0). (2) Nur wenn der Name fehlt, entscheidet ein sehr
    kleines dediziertes Modell (core.fast mit ADDRESS_CHECK_MODEL statt dem großen
    AGENT_MODEL_FAST), ob es sich auch ohne Namensnennung um eine an Alfred
    gerichtete Anfrage handelt (Spec: "nicht nur Wake-Word")."""
    stripped = text.strip()
    if not stripped:
        return False
    if "alfred" in stripped.lower():
        return True
    return await fast.yes_no(
        f"Ist dieser Satz eine Anfrage oder ein Befehl an einen persönlichen KI-Assistenten "
        f"namens Alfred (nicht nur Small Talk mit jemand anderem im Raum), auch wenn der Name "
        f"'Alfred' nicht genannt wird?\n\n\"{stripped}\"",
        model=config.ADDRESS_CHECK_MODEL,
    )
