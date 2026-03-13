"""Abstract base for messaging platform adapters.

Each platform (Telegram, Discord, Slack, etc.) implements PlatformAdapter
with connect/disconnect/send and emits MessageEvent objects for incoming messages.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Awaitable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """Type of incoming message."""
    TEXT = "text"
    COMMAND = "command"
    MEDIA = "media"
    LOCATION = "location"


class MessageEvent(BaseModel):
    """Normalized incoming message from any platform."""
    platform: str
    chat_id: str
    user_id: str = ""
    user_name: str = ""
    text: str = ""
    message_type: MessageType = MessageType.TEXT
    thread_id: str | None = None
    media_url: str | None = None
    raw: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SendResult(BaseModel):
    """Result of sending a message."""
    success: bool
    message_id: str = ""
    error: str = ""


# Type alias for the message handler callback
MessageHandler = Callable[[MessageEvent], Awaitable[str | None]]


class PlatformAdapter(ABC):
    """Abstract base class for messaging platform adapters.

    Subclasses implement platform-specific connection, message handling,
    and sending logic. The gateway runner manages adapter lifecycle.
    """

    def __init__(self, platform_name: str, config: dict[str, Any] | None = None):
        self.platform_name = platform_name
        self.config = config or {}
        self._running = False
        self._message_handler: MessageHandler | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    def set_message_handler(self, handler: MessageHandler) -> None:
        """Set the callback for incoming messages."""
        self._message_handler = handler

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the platform. Returns True on success."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the platform."""
        ...

    @abstractmethod
    async def send(
        self,
        chat_id: str,
        text: str,
        thread_id: str | None = None,
    ) -> SendResult:
        """Send a message to a chat."""
        ...

    async def _dispatch_message(self, event: MessageEvent) -> None:
        """Dispatch an incoming message to the handler."""
        if self._message_handler is None:
            logger.warning("[%s] No message handler set, dropping message", self.platform_name)
            return
        try:
            response = await self._message_handler(event)
            if response:
                await self.send(event.chat_id, response, thread_id=event.thread_id)
        except Exception:
            logger.exception("[%s] Error handling message from %s", self.platform_name, event.user_name)
