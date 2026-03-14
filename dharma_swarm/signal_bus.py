"""Signal Bus — in-process event bus for inter-loop temporal coherence.

The shared downbeat. Loops emit typed signals; other loops drain and respond.
This is the ONLY mechanism for loops to feel each other's rhythms.

Not a message bus (that's agent-to-agent). This is loop-to-loop:
  - cascade emits CASCADE_EIGENFORM_DISTANCE
  - audit emits ANOMALY_DETECTED
  - recognition emits RECOGNITION_UPDATED
  - swarm drains ANOMALY_DETECTED to suppress director during crises

Events expire after a configurable TTL (default: 2 cycle intervals).
Thread-safe via asyncio primitives (designed for single event loop).
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any


class SignalBus:
    """Simple in-process event bus for inter-loop signaling.

    Not async — emit/drain are synchronous because they only touch
    an in-memory deque.  Designed for a single asyncio event loop
    where all loops share one bus instance.

    Attributes:
        ttl_seconds: Events older than this are dropped on drain.
    """

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._events: deque[tuple[float, dict[str, Any]]] = deque()

    def emit(self, event: dict[str, Any]) -> None:
        """Emit a signal event.

        Args:
            event: Dict with at minimum a ``"type"`` key (str).
                   Additional keys are payload.

        Example::

            bus.emit({"type": "ANOMALY_DETECTED", "severity": "high"})
        """
        self._events.append((time.monotonic(), event))

    def drain(
        self,
        event_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Consume matching events, removing expired ones.

        Args:
            event_types: If provided, only return events whose ``"type"``
                         is in this list.  If None, return all events.

        Returns:
            List of event dicts that matched (consumed — won't appear again).
        """
        now = time.monotonic()
        cutoff = now - self.ttl_seconds

        # Separate into: expired (drop), matched (return), kept (stay)
        matched: list[dict[str, Any]] = []
        kept: deque[tuple[float, dict[str, Any]]] = deque()

        while self._events:
            ts, event = self._events.popleft()
            if ts < cutoff:
                continue  # expired — drop
            event_type = event.get("type", "")
            if event_types is None or event_type in event_types:
                matched.append(event)
            else:
                kept.append((ts, event))

        self._events = kept
        return matched

    def peek(
        self,
        event_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Like drain, but non-destructive — events stay in the bus.

        Args:
            event_types: Filter by type, or None for all.

        Returns:
            List of matching event dicts (not consumed).
        """
        now = time.monotonic()
        cutoff = now - self.ttl_seconds

        return [
            event
            for ts, event in self._events
            if ts >= cutoff
            and (event_types is None or event.get("type", "") in event_types)
        ]

    @property
    def pending_count(self) -> int:
        """Number of non-expired events currently in the bus."""
        now = time.monotonic()
        cutoff = now - self.ttl_seconds
        return sum(1 for ts, _ in self._events if ts >= cutoff)

    def clear(self) -> None:
        """Drop all events."""
        self._events.clear()

    # Module-level singleton
    _instance: SignalBus | None = None

    @classmethod
    def get(cls) -> SignalBus:
        """Return the module-level singleton SignalBus instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
