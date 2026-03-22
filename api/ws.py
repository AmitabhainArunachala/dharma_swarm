"""WebSocket connection manager + event broadcaster."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections grouped by channel."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, channel: str = "default") -> None:
        await websocket.accept()
        async with self._lock:
            if channel not in self._connections:
                self._connections[channel] = []
            self._connections[channel].append(websocket)
        logger.info("WS connected: channel=%s, total=%d", channel, self.count(channel))

    async def disconnect(self, websocket: WebSocket, channel: str = "default") -> None:
        async with self._lock:
            if channel in self._connections:
                try:
                    self._connections[channel].remove(websocket)
                except ValueError:
                    pass
                if not self._connections[channel]:
                    del self._connections[channel]
        logger.info("WS disconnected: channel=%s", channel)

    def count(self, channel: str = "default") -> int:
        return len(self._connections.get(channel, []))

    async def broadcast(self, channel: str, data: dict[str, Any]) -> None:
        """Send data to all connections on a channel."""
        connections = self._connections.get(channel, [])
        if not connections:
            return

        message = json.dumps(data, default=str)
        dead: list[WebSocket] = []

        for ws in connections:
            try:
                await ws.send_text(message)
            except Exception:
                logger.debug("Failed to send broadcast to WebSocket on channel %s", channel, exc_info=True)
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    try:
                        self._connections[channel].remove(ws)
                    except (ValueError, KeyError):
                        pass

    async def send_personal(self, websocket: WebSocket, data: dict[str, Any]) -> None:
        try:
            await websocket.send_text(json.dumps(data, default=str))
        except Exception:
            logger.debug("Failed to send personal WebSocket message", exc_info=True)


# Singleton
manager = ConnectionManager()
