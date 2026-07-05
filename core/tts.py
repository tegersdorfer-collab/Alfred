"""
TTS — Text-to-Speech via Piper (lokal, MIT, deutsche Stimme).

Gibt OGG/Opus-Bytes zurück die direkt als Telegram-Sprachnachricht verschickt
werden können. Lazy-loaded beim ersten Aufruf, dann im RAM gecacht.

Ersetzt Kokoro-ONNX (kein Deutsch-Support — nur en/ja/zh/es/fr/hi/it/pt) und
Chatterbox-Multilingual (unterstützt Deutsch, aber 8-12s Latenz pro Satz auf
Apple Silicon — zu langsam für Sprachantworten). Piper: ~0.7s Modell-Ladezeit,
~1-2s Synthese für einen normalen Antwortsatz, native deutsche Stimme.
"""
from __future__ import annotations
import asyncio
import io
import logging
import re
import subprocess
import tempfile
import wave
from pathlib import Path

log = logging.getLogger(__name__)

_MODEL_DIR    = Path(__file__).parent.parent / "data" / "tts" / "piper"
_ONNX_PATH    = _MODEL_DIR / "de_DE-thorsten-high.onnx"
_CONFIG_PATH  = _MODEL_DIR / "de_DE-thorsten-high.onnx.json"

DEFAULT_VOICE = "de_DE-thorsten-high"  # männlich, deutsch
DEFAULT_SPEED = 1.0

_voice: object | None = None
_lock = asyncio.Lock()


def is_available() -> bool:
    return _ONNX_PATH.exists() and _CONFIG_PATH.exists()


def _load_voice():
    global _voice
    if _voice is not None:
        return _voice
    if not is_available():
        raise RuntimeError(
            f"Piper-Modell nicht gefunden in {_MODEL_DIR}. "
            "Bitte de_DE-thorsten-high.onnx (+ .onnx.json) herunterladen."
        )
    from piper import PiperVoice
    _voice = PiperVoice.load(str(_ONNX_PATH), str(_CONFIG_PATH))
    log.info("🔊 Piper TTS geladen (de_DE-thorsten-high)")
    return _voice


def _clean_for_speech(text: str) -> str:
    """Markdown und Sonderzeichen entfernen die beim Vorlesen störend klingen."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)       # **bold**
    text = re.sub(r'\*(.+?)\*', r'\1', text)             # *italic*
    text = re.sub(r'`+(.+?)`+', r'\1', text)             # `code`
    text = re.sub(r'#+\s*', '', text)                    # ## Header
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # [link](url)
    text = re.sub(r'https?://\S+', 'Link', text)         # nackte URLs
    text = re.sub(r'•\s*', '', text)                     # Bullet points
    text = re.sub(r'-{2,}', '', text)                    # --- Trennlinien
    text = re.sub(r'\n{3,}', '\n\n', text)               # Mehrfach-Leerzeilen
    return text.strip()


def _synth(text: str, speed: float) -> bytes:
    """Synthesisiert Text → WAV-Bytes (läuft in Thread, blockiert nicht Event-Loop)."""
    from piper.config import SynthesisConfig
    voice = _load_voice()
    syn_config = SynthesisConfig(length_scale=1.0 / speed if speed else None)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file, syn_config=syn_config)
    return buf.getvalue()


def _wav_to_ogg(wav_bytes: bytes) -> bytes:
    """WAV → OGG/Opus via ffmpeg (Telegram-kompatibles Format)."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
        tmp_wav.write(wav_bytes)
        wav_path = tmp_wav.name

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_ogg:
        ogg_path = tmp_ogg.name

    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", wav_path,
                "-c:a", "libopus",
                "-b:a", "64k",
                "-ar", "48000",
                ogg_path,
            ],
            capture_output=True,
            check=True,
        )
        return Path(ogg_path).read_bytes()
    finally:
        Path(wav_path).unlink(missing_ok=True)
        Path(ogg_path).unlink(missing_ok=True)


async def synthesize(
    text: str,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
    max_chars: int = 2000,
) -> bytes:
    """Text → OGG/Opus-Bytes (Telegram voice message format).

    `voice` bleibt aus API-Kompatibilitätsgründen erhalten, wird aktuell aber
    ignoriert — es ist nur eine deutsche Piper-Stimme geladen.
    Kürzt automatisch auf max_chars um Timeouts zu vermeiden.
    Gibt leere Bytes zurück wenn TTS nicht verfügbar.
    """
    if not is_available():
        log.warning("TTS nicht verfügbar — Modelle fehlen in data/tts/piper/")
        return b""

    text = _clean_for_speech(text)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(".", 1)[0] + "."

    if not text.strip():
        return b""

    async with _lock:
        try:
            wav = await asyncio.to_thread(_synth, text, speed)
            ogg = await asyncio.to_thread(_wav_to_ogg, wav)
            log.info(f"🔊 TTS: {len(text)} Zeichen → {len(ogg)//1024}KB OGG")
            return ogg
        except Exception as e:
            log.error(f"TTS fehlgeschlagen: {e}")
            return b""


async def list_voices() -> list[str]:
    """Gibt alle verfügbaren Stimmen zurück (aktuell nur eine deutsche Piper-Stimme)."""
    return [DEFAULT_VOICE] if is_available() else []
