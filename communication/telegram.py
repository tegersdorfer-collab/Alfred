"""
Telegram Bot – primärer Kommunikationskanal.
Tauschbar gegen andere Kanäle via CommunicationChannel Interface.
Unterstützt: Text, Sprachnachrichten (→ Transkription via Whisper), Fotos (→ Claude Haiku Vision).
"""
import asyncio
import base64
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from io import BytesIO

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters,
)
from telegram.constants import ChatAction

from communication.base import CommunicationChannel, IncomingMessage, MessageHandler as MH
import config

log = logging.getLogger(__name__)


# ── Whisper (lazy-loaded, optional) ──────────────────────────────────────────

_whisper_model = None
_whisper_lock = asyncio.Lock()


async def _transcribe(audio_path: str) -> str:
    """Transkribiert eine Audiodatei lokal mit Whisper. Gibt leeren String bei Fehler zurück."""
    global _whisper_model
    try:
        import whisper
    except ImportError:
        log.warning("openai-whisper nicht installiert – Sprachnachricht kann nicht transkribiert werden")
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


# ── Ollama-Vision (für Fotos) ─────────────────────────────────────────────────

_VISION_MODEL = "llava:7b"
_VISION_PROMPT = (
    "Beschreibe dieses Bild kurz auf Deutsch. "
    "Falls es sich um Essen oder Getränke handelt, schätze die Kalorien "
    "und Makronährstoffe (Protein, Kohlenhydrate, Fett) so genau wie möglich "
    "und beginne deine Antwort mit '🍽️ MAHLZEIT:'. "
    "Sonst beginne mit '🖼️ BILD:'."
)


async def _describe_image(image_bytes: bytes) -> str:
    """Beschreibt ein Bild lokal mit llava:7b via Ollama. Erkennt Mahlzeiten für Tracking."""
    try:
        import ollama as _ollama
        b64 = base64.standard_b64encode(image_bytes).decode()
        client = _ollama.AsyncClient(host=config.OLLAMA_BASE_URL)
        resp = await client.chat(
            model=_VISION_MODEL,
            messages=[{
                "role": "user",
                "content": _VISION_PROMPT,
                "images": [b64],
            }],
            options={"num_predict": 512},
            keep_alive=0,
        )
        return (resp.message.content or "").strip()
    except Exception as e:
        log.error(f"Ollama-Vision fehlgeschlagen: {e}")
        return "Konnte Bild nicht analysieren."


class TelegramChannel(CommunicationChannel):
    supports_streaming = True

    def __init__(self, token: str | None = None):
        self._token = token or config.TELEGRAM_BOT_TOKEN
        self._app: Application | None = None
        self._chat_id: str | None = config.TELEGRAM_CHAT_ID or None
        self._allowed: set[str] = set(config.TELEGRAM_ALLOWED_IDS)
        self._handler: MH | None = None

    def on_message(self, handler: MH) -> None:
        self._handler = handler

    async def send(self, text: str) -> None:
        if not self._app or not self._chat_id:
            print(f"[Alfred → Telegram nicht verbunden]: {text}")
            return

        # Lange Nachrichten aufteilen (Telegram-Limit: 4096 Zeichen)
        chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
        for chunk in chunks:
            try:
                await self._app.bot.send_message(
                    chat_id=self._chat_id,
                    text=chunk,
                    parse_mode="Markdown",
                )
            except Exception:
                # Fallback: plain text wenn Markdown Fehler wirft
                await self._app.bot.send_message(
                    chat_id=self._chat_id,
                    text=chunk,
                )

    async def send_typing(self) -> None:
        if self._app and self._chat_id:
            await self._app.bot.send_chat_action(
                chat_id=self._chat_id,
                action=ChatAction.TYPING,
            )

    # ── Streaming (Live-Edit einer Nachricht) ─────────────────────────────────

    async def start_message(self, text: str = "…") -> int | None:
        if not (self._app and self._chat_id):
            return None
        try:
            msg = await self._app.bot.send_message(chat_id=self._chat_id, text=text)
            return msg.message_id
        except Exception:
            return None

    async def edit_message(self, message_id: int, text: str, markdown: bool = False) -> None:
        if not (self._app and self._chat_id and message_id):
            return
        try:
            await self._app.bot.edit_message_text(
                chat_id=self._chat_id, message_id=message_id, text=text[:4096],
                parse_mode="Markdown" if markdown else None,
            )
        except Exception:
            pass  # "message is not modified" o.ä. ignorieren

    def _authorized(self, update: Update) -> bool:
        """Darf dieser Absender mit Alfred reden?
        Mit konfigurierter Allowlist: strikt (User- oder Chat-ID muss passen).
        Ohne Allowlist: Trust-on-first-use – der erste Absender wird für die
        Laufzeit gesperrt, alle anderen abgewiesen (statt offen für jeden)."""
        if not update.message or not update.message.from_user:
            return False
        uid = str(update.message.from_user.id)
        cid = str(update.message.chat_id)
        if self._allowed:
            return uid in self._allowed or cid in self._allowed
        # Nichts konfiguriert → auf ersten Absender sperren und laut warnen
        log.warning(
            "⚠️  Keine TELEGRAM_ALLOWED_IDS/TELEGRAM_CHAT_ID gesetzt – sperre auf "
            "ersten Absender %s. Trag die ID in .env ein!", uid,
        )
        self._allowed = {uid}
        self._chat_id = cid
        return True

    async def _handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.message or not update.message.text:
            return
        if not self._authorized(update):
            who = update.message.from_user.id if update.message.from_user else "?"
            log.warning("Nachricht von nicht autorisierter ID %s verworfen", who)
            return

        # Chat-ID des autorisierten Absenders merken (für Antworten/Proaktives)
        self._chat_id = str(update.message.chat_id)

        msg = IncomingMessage(
            text=update.message.text,
            sender_id=str(update.message.from_user.id),
            timestamp=datetime.now(),
            raw=update,
        )

        if self._handler:
            await self._handler(msg)

    async def _handle_voice(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Sprachnachricht → Whisper-Transkription → Alfred-Handler."""
        if not update.message:
            return
        if not self._authorized(update):
            return
        self._chat_id = str(update.message.chat_id)

        voice = update.message.voice or update.message.audio
        if not voice:
            return

        await self._app.bot.send_chat_action(chat_id=self._chat_id, action=ChatAction.TYPING)

        try:
            tg_file = await context.bot.get_file(voice.file_id)
            suffix = ".ogg" if update.message.voice else ".mp3"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp_path = tmp.name
            await tg_file.download_to_drive(tmp_path)
        except Exception as e:
            log.error(f"Sprachnachricht-Download fehlgeschlagen: {e}")
            await self.send("⚠️ Konnte Sprachnachricht nicht herunterladen.")
            return

        try:
            text = await _transcribe(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        if not text:
            await self.send("🎤 Konnte die Sprachnachricht nicht verstehen. Bitte schreib es kurz.")
            return

        log.info(f"🎤 Transkription: {text[:100]}")
        await self.send(f"🎤 _{text}_")

        msg = IncomingMessage(
            text=text,
            sender_id=str(update.message.from_user.id),
            timestamp=datetime.now(),
            raw=update,
        )
        if self._handler:
            await self._handler(msg)

    async def _handle_photo(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Foto → Claude Haiku Vision → Mahlzeit-Logging oder Bildbeschreibung."""
        if not update.message or not update.message.photo:
            return
        if not self._authorized(update):
            return
        self._chat_id = str(update.message.chat_id)

        await self._app.bot.send_chat_action(chat_id=self._chat_id, action=ChatAction.TYPING)

        # Höchste Auflösung nehmen
        photo = sorted(update.message.photo, key=lambda p: p.file_size or 0)[-1]
        try:
            tg_file = await context.bot.get_file(photo.file_id)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp_path = tmp.name
            await tg_file.download_to_drive(tmp_path)
            image_bytes = Path(tmp_path).read_bytes()
        except Exception as e:
            log.error(f"Foto-Download fehlgeschlagen: {e}")
            await self.send("⚠️ Konnte das Foto nicht herunterladen.")
            return
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        caption = update.message.caption or ""
        description = await _describe_image(image_bytes)

        if description.startswith("🍽️ MAHLZEIT:"):
            # Mahlzeit erkannt → als Tracking-Befehl an Alfred weiterleiten
            meal_text = (
                f"{description}\n\n"
                f"Bitte diese Mahlzeit in meinem Journal tracken."
                + (f" Zusatz: {caption}" if caption else "")
            )
            await self.send(description)
            msg = IncomingMessage(
                text=meal_text,
                sender_id=str(update.message.from_user.id),
                timestamp=datetime.now(),
                raw=update,
            )
            if self._handler:
                await self._handler(msg)
        else:
            # Allgemeines Bild → beschreiben und ggf. auf Caption antworten
            response = description
            if caption:
                msg = IncomingMessage(
                    text=f"{description}\n\nFrage des Nutzers zum Bild: {caption}",
                    sender_id=str(update.message.from_user.id),
                    timestamp=datetime.now(),
                    raw=update,
                )
                await self.send(description)
                if self._handler:
                    await self._handler(msg)
            else:
                await self.send(response)

    async def _handle_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._authorized(update):
            log.warning("/start von nicht autorisierter ID verworfen")
            return
        self._chat_id = str(update.message.chat_id)
        await update.message.reply_text(
            "Alfred online. Was brauchst du?"
        )

    async def _handle_status(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._authorized(update):
            return
        await update.message.reply_text("✅ System läuft.")

    async def start(self) -> None:
        if not self._token:
            raise ValueError("TELEGRAM_BOT_TOKEN nicht gesetzt in .env")

        self._app = (
            Application.builder()
            .token(self._token)
            .build()
        )

        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(CommandHandler("status", self._handle_status))
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        )
        self._app.add_handler(
            MessageHandler(filters.VOICE | filters.AUDIO, self._handle_voice)
        )
        self._app.add_handler(
            MessageHandler(filters.PHOTO, self._handle_photo)
        )

        print("📱 Telegram Bot gestartet – warte auf Nachrichten...")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
