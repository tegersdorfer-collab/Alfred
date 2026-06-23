"""
TTS — Text-to-Speech via Kokoro ONNX (lokal, Apache-2.0, ~80MB).

Gibt OGG/Opus-Bytes zurück die direkt als Telegram-Sprachnachricht verschickt werden können.
Lazy-loaded beim ersten Aufruf, dann im RAM gecacht.
"""
from __future__ import annotations
import asyncio
import io
import logging
import re
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

_MODEL_DIR  = Path(__file__).parent.parent / "data" / "tts"
_ONNX_PATH  = _MODEL_DIR / "kokoro-v1.0.onnx"
_VOICES_PATH = _MODEL_DIR / "voices-v1.0.bin"

# Beste verfügbare deutsche/neutrale Stimme in Kokoro
# af_heart = american female (warm, natürlich) — beste Qualität für kurze Texte
# bf_emma  = british female (klar, professionell)
DEFAULT_VOICE = "af_heart"
DEFAULT_SPEED = 1.0

_kokoro: object | None = None
_lock = asyncio.Lock()


def is_available() -> bool:
    return _ONNX_PATH.exists() and _VOICES_PATH.exists()


def _load_kokoro():
    global _kokoro
    if _kokoro is not None:
        return _kokoro
    if not is_available():
        raise RuntimeError(
            f"Kokoro-Modelle nicht gefunden in {_MODEL_DIR}. "
            "Bitte kokoro-v1.0.onnx und voices-v1.0.bin herunterladen."
        )
    from kokoro_onnx import Kokoro
    _kokoro = Kokoro(str(_ONNX_PATH), str(_VOICES_PATH))
    log.info(f"🔊 Kokoro TTS geladen — Stimmen: {_kokoro.get_voices()[:5]}")
    return _kokoro


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


def _synth(text: str, voice: str, speed: float) -> bytes:
    """Synthesisiert Text → WAV-Bytes (läuft in Thread, blockiert nicht Event-Loop)."""
    kokoro = _load_kokoro()
    import soundfile as sf
    samples, sample_rate = kokoro.create(text, voice=voice, speed=speed, lang="en-us")
    buf = io.BytesIO()
    sf.write(buf, samples, sample_rate, format="WAV")
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

    Kürzt automatisch auf max_chars um Timeouts zu vermeiden.
    Gibt leere Bytes zurück wenn TTS nicht verfügbar.
    """
    if not is_available():
        log.warning("TTS nicht verfügbar — Modelle fehlen in data/tts/")
        return b""

    text = _clean_for_speech(text)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(".", 1)[0] + "."

    if not text.strip():
        return b""

    async with _lock:
        try:
            wav = await asyncio.to_thread(_synth, text, voice, speed)
            ogg = await asyncio.to_thread(_wav_to_ogg, wav)
            log.info(f"🔊 TTS: {len(text)} Zeichen → {len(ogg)//1024}KB OGG")
            return ogg
        except Exception as e:
            log.error(f"TTS fehlgeschlagen: {e}")
            return b""


async def list_voices() -> list[str]:
    """Gibt alle verfügbaren Kokoro-Stimmen zurück."""
    if not is_available():
        return []
    try:
        kokoro = await asyncio.to_thread(_load_kokoro)
        return kokoro.get_voices()
    except Exception:
        return []
