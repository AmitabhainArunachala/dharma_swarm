"""Telegram platform adapter using python-telegram-bot.

Requires: pip install python-telegram-bot

Configuration (in ~/.dharma/gateway.yaml):
    telegram:
      enabled: true
      token: ${TELEGRAM_BOT_TOKEN}
      allowed_users: []   # empty = allow all
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from dharma_swarm.gateway.base import (
    MessageEvent,
    MessageType,
    PlatformAdapter,
    SendResult,
)

logger = logging.getLogger(__name__)

try:
    from telegram import Update, Bot
    from telegram.ext import (
        Application,
        MessageHandler as TelegramMessageHandler,
        ContextTypes,
        filters,
    )
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Update = Any  # type: ignore[assignment,misc]
    Bot = Any  # type: ignore[assignment,misc]
    Application = Any  # type: ignore[assignment,misc]
    TelegramMessageHandler = Any  # type: ignore[assignment,misc]
    filters = None  # type: ignore[assignment]

    class _MockContextTypes:
        DEFAULT_TYPE = Any
    ContextTypes = _MockContextTypes  # type: ignore[assignment,misc]

# Telegram message limit
MAX_MESSAGE_LENGTH = 4096


def check_telegram_requirements() -> bool:
    """Check if Telegram dependencies are available."""
    return TELEGRAM_AVAILABLE


class TelegramAdapter(PlatformAdapter):
    """Telegram bot adapter.

    Handles receiving messages, sending responses, and forum topic threads.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__("telegram", config)
        self._app: Optional[Application] = None  # type: ignore[type-arg]
        self._bot: Optional[Bot] = None  # type: ignore[type-arg]
        self._allowed_users: set[str] = set()
        if config:
            allowed = config.get("allowed_users", [])
            if allowed:
                self._allowed_users = {str(u) for u in allowed}

    async def connect(self) -> bool:
        """Connect to Telegram and start polling."""
        if not TELEGRAM_AVAILABLE:
            logger.error(
                "[telegram] python-telegram-bot not installed. "
                "Run: pip install python-telegram-bot"
            )
            return False

        token = self.config.get("token") or os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not token:
            logger.error("[telegram] No bot token configured")
            return False

        try:
            self._app = Application.builder().token(token).build()
            self._bot = self._app.bot

            # Register text message handler
            self._app.add_handler(TelegramMessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._handle_text,
            ))

            # Start polling
            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

            self._running = True
            logger.info("[telegram] Connected and polling")
            return True

        except Exception:
            logger.exception("[telegram] Failed to connect")
            return False

    async def disconnect(self) -> None:
        """Stop polling and disconnect."""
        if self._app:
            try:
                await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception:
                logger.exception("[telegram] Error during disconnect")
        self._running = False
        logger.info("[telegram] Disconnected")

    async def send(
        self,
        chat_id: str,
        text: str,
        thread_id: str | None = None,
    ) -> SendResult:
        """Send a message to a Telegram chat."""
        if not self._bot:
            return SendResult(success=False, error="Bot not connected")

        try:
            # Split long messages
            chunks = _split_message(text)
            last_msg = None
            kwargs: dict[str, Any] = {}
            if thread_id:
                kwargs["message_thread_id"] = int(thread_id)

            for chunk in chunks:
                last_msg = await self._bot.send_message(
                    chat_id=int(chat_id),
                    text=chunk,
                    **kwargs,
                )

            return SendResult(
                success=True,
                message_id=str(last_msg.message_id) if last_msg else "",
            )
        except Exception as e:
            logger.error("[telegram] Send error: %s", e)
            return SendResult(success=False, error=str(e))

    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # type: ignore[name-defined]
        """Handle incoming text messages."""
        if not update.message or not update.message.text:
            return

        user = update.message.from_user
        user_id = str(user.id) if user else ""

        # ACL check
        if self._allowed_users and user_id not in self._allowed_users:
            logger.debug("[telegram] Ignoring message from unauthorized user %s", user_id)
            return

        event = MessageEvent(
            platform="telegram",
            chat_id=str(update.message.chat_id),
            user_id=user_id,
            user_name=user.username or user.first_name if user else "",
            text=update.message.text,
            message_type=MessageType.TEXT,
            thread_id=str(update.message.message_thread_id) if update.message.message_thread_id else None,
        )

        await self._dispatch_message(event)


def _split_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split a long message into chunks that fit Telegram's limit."""
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        # Try to split at newline
        split_at = text.rfind("\n", 0, max_length)
        if split_at < max_length // 2:
            split_at = max_length
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")

    return chunks
