"""
Telegram Bot – primärer Kommunikationskanal.
Tauschbar gegen andere Kanäle via CommunicationChannel Interface.
"""
import asyncio
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters,
)
from telegram.constants import ChatAction

from communication.base import CommunicationChannel, IncomingMessage, MessageHandler as MH
import config


class TelegramChannel(CommunicationChannel):
    supports_streaming = True

    def __init__(self, token: str | None = None):
        self._token = token or config.TELEGRAM_BOT_TOKEN
        self._app: Application | None = None
        self._chat_id: str | None = config.TELEGRAM_CHAT_ID or None
        self._handler: MH | None = None

    def on_message(self, handler: MH) -> None:
        self._handler = handler

    async def send(self, text: str) -> None:
        if not self._app or not self._chat_id:
            print(f"[Jarvis → Telegram nicht verbunden]: {text}")
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

    async def _handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.message or not update.message.text:
            return

        # Chat-ID beim ersten Kontakt speichern
        self._chat_id = str(update.message.chat_id)

        msg = IncomingMessage(
            text=update.message.text,
            sender_id=str(update.message.from_user.id),
            timestamp=datetime.now(),
            raw=update,
        )

        if self._handler:
            await self._handler(msg)

    async def _handle_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        self._chat_id = str(update.message.chat_id)
        await update.message.reply_text(
            "Jarvis online. Was brauchst du?"
        )

    async def _handle_status(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
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

        print("📱 Telegram Bot gestartet – warte auf Nachrichten...")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
