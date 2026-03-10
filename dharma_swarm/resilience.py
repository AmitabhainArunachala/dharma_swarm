"""Routing resilience primitives (retry + fallback + circuit breaker)."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from enum import Enum
import json
import os
import random
import time
from typing import Any, Awaitable, Callable, TypeVar


T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.25
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 2.0
    jitter_seconds: float = 0.05


@dataclass(frozen=True)
class CircuitBreakerConfig:
    window_seconds: float = 60.0
    failure_rate_threshold: float = 0.10
    min_samples: int = 8
    open_duration_seconds: float = 30.0
    half_open_max_attempts: int = 1


class CircuitStateStore(ABC):
    """Persistence layer for breaker state sharing."""

    @abstractmethod
    def load(self, key: str) -> dict[str, Any] | None:
        """Load serialized breaker state for a key."""

    @abstractmethod
    def save(self, key: str, payload: dict[str, Any]) -> None:
        """Persist breaker state for a key."""


class InMemoryCircuitStateStore(CircuitStateStore):
    def __init__(self) -> None:
        self._payloads: dict[str, dict[str, Any]] = {}

    def load(self, key: str) -> dict[str, Any] | None:
        payload = self._payloads.get(key)
        if payload is None:
            return None
        return dict(payload)

    def save(self, key: str, payload: dict[str, Any]) -> None:
        self._payloads[key] = dict(payload)


class RedisCircuitStateStore(CircuitStateStore):
    """Redis-backed state store for cross-process breaker sharing."""

    def __init__(
        self,
        redis_url: str,
        *,
        key_prefix: str = "dgc:router:circuit:",
        ttl_seconds: int = 3600,
    ) -> None:
        try:
            import redis  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "redis package is required for RedisCircuitStateStore"
            ) from exc
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds

    def _full_key(self, key: str) -> str:
        return f"{self._key_prefix}{key}"

    def load(self, key: str) -> dict[str, Any] | None:
        raw = self._client.get(self._full_key(key))
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def save(self, key: str, payload: dict[str, Any]) -> None:
        self._client.setex(
            self._full_key(key),
            self._ttl_seconds,
            json.dumps(payload, ensure_ascii=True),
        )


class CircuitBreaker:
    """Sliding-window circuit breaker for one provider/model lane."""

    def __init__(
        self,
        config: CircuitBreakerConfig | None = None,
        *,
        time_fn: Callable[[], float] | None = None,
        persist_hook: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.config = config or CircuitBreakerConfig()
        self._time_fn = time_fn or time.monotonic
        self._events: deque[tuple[float, bool]] = deque()
        self._state = CircuitState.CLOSED
        self._opened_at: float | None = None
        self._half_open_attempts = 0
        self._persist_hook = persist_hook

    @property
    def state(self) -> CircuitState:
        self._refresh_time_state()
        return self._state

    def allow_request(self) -> bool:
        self._refresh_time_state()
        allowed = True
        if self._state == CircuitState.OPEN:
            allowed = False
        elif self._state == CircuitState.HALF_OPEN:
            if self._half_open_attempts >= self.config.half_open_max_attempts:
                allowed = False
            else:
                self._half_open_attempts += 1
        self._persist()
        return allowed

    def record_success(self) -> None:
        now = self._time_fn()
        self._append_event(now, success=True)
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._opened_at = None
            self._half_open_attempts = 0
            self._persist()
            return
        if self._state == CircuitState.CLOSED:
            self._maybe_trip_open(now)
        self._persist()

    def record_failure(self) -> None:
        now = self._time_fn()
        self._append_event(now, success=False)

        if self._state == CircuitState.HALF_OPEN:
            self._trip_open(now)
            self._persist()
            return

        if self._state == CircuitState.CLOSED:
            self._maybe_trip_open(now)
        self._persist()

    def snapshot(self) -> dict[str, float | int | str]:
        self._trim(self._time_fn())
        total = len(self._events)
        failures = sum(1 for _, success in self._events if not success)
        return {
            "state": self.state.value,
            "window_total": total,
            "window_failures": failures,
            "window_failure_rate": (failures / total) if total else 0.0,
            "open_since": self._opened_at or 0.0,
            "half_open_attempts": self._half_open_attempts,
        }

    def export_state(self) -> dict[str, Any]:
        self._trim(self._time_fn())
        return {
            "state": self.state.value,
            "opened_at": self._opened_at,
            "half_open_attempts": self._half_open_attempts,
            "events": [[ts, success] for ts, success in self._events],
        }

    def import_state(self, payload: dict[str, Any]) -> None:
        state_raw = str(payload.get("state", "closed")).lower()
        if state_raw not in {item.value for item in CircuitState}:
            state_raw = CircuitState.CLOSED.value
        self._state = CircuitState(state_raw)
        opened_raw = payload.get("opened_at")
        self._opened_at = float(opened_raw) if opened_raw is not None else None
        self._half_open_attempts = int(payload.get("half_open_attempts", 0) or 0)
        events_raw = payload.get("events") or []
        restored: deque[tuple[float, bool]] = deque()
        for item in events_raw:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            try:
                restored.append((float(item[0]), bool(item[1])))
            except (TypeError, ValueError):
                continue
        self._events = restored
        self._trim(self._time_fn())

    def _trip_open(self, now: float) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = now
        self._half_open_attempts = 0

    def _maybe_trip_open(self, now: float) -> None:
        total = len(self._events)
        if total < self.config.min_samples:
            return
        failures = sum(1 for _, success in self._events if not success)
        failure_rate = failures / max(total, 1)
        if failure_rate >= self.config.failure_rate_threshold:
            self._trip_open(now)

    def _refresh_time_state(self) -> None:
        if self._state != CircuitState.OPEN or self._opened_at is None:
            return
        elapsed = self._time_fn() - self._opened_at
        if elapsed >= self.config.open_duration_seconds:
            self._state = CircuitState.HALF_OPEN
            self._half_open_attempts = 0
            self._persist()

    def _append_event(self, now: float, *, success: bool) -> None:
        self._events.append((now, success))
        self._trim(now)

    def _trim(self, now: float) -> None:
        cutoff = now - self.config.window_seconds
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

    def _persist(self) -> None:
        if self._persist_hook is None:
            return
        try:
            self._persist_hook(self.export_state())
        except Exception:
            return


class CircuitBreakerRegistry:
    """Holds breaker state per provider/model lane."""

    def __init__(
        self,
        config: CircuitBreakerConfig | None = None,
        *,
        store: CircuitStateStore | None = None,
        redis_url: str | None = None,
    ) -> None:
        self._config = config or CircuitBreakerConfig()
        resolved_redis_url = redis_url or os.environ.get("DGC_ROUTER_REDIS_URL", "").strip()
        if store is not None:
            self._store = store
        elif resolved_redis_url:
            try:
                self._store = RedisCircuitStateStore(resolved_redis_url)
            except Exception:
                self._store = InMemoryCircuitStateStore()
        else:
            self._store = InMemoryCircuitStateStore()
        self._breakers: dict[str, CircuitBreaker] = {}

    def _fallback_to_memory(self) -> None:
        if not isinstance(self._store, InMemoryCircuitStateStore):
            self._store = InMemoryCircuitStateStore()

    def _safe_load(self, key: str) -> dict[str, Any] | None:
        try:
            return self._store.load(key)
        except Exception:
            self._fallback_to_memory()
            return None

    def _safe_save(self, key: str, payload: dict[str, Any]) -> None:
        try:
            self._store.save(key, payload)
        except Exception:
            self._fallback_to_memory()

    def get(self, key: str) -> CircuitBreaker:
        if key not in self._breakers:
            breaker = CircuitBreaker(
                self._config,
                persist_hook=lambda payload, k=key: self._safe_save(k, payload),
            )
            payload = self._safe_load(key)
            if payload:
                breaker.import_state(payload)
            self._breakers[key] = breaker
        return self._breakers[key]

    def snapshot_all(self) -> dict[str, dict[str, float | int | str]]:
        return {key: breaker.snapshot() for key, breaker in self._breakers.items()}


def is_retryable_exception(exc: Exception) -> bool:
    """Classify retryability conservatively to avoid pointless retries."""
    if isinstance(exc, (NotImplementedError, KeyError)):
        return False
    lowered = str(exc).lower()
    non_retry_terms = (
        "not set",
        "no provider",
        "api key",
        "apikey",
        "auth",
        "unauthorized",
        "forbidden",
        "not implemented",
    )
    return not any(term in lowered for term in non_retry_terms)


async def run_with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy,
    on_error: Callable[[Exception, int], None] | None = None,
) -> T:
    """Execute async operation with bounded exponential backoff retry."""
    attempt = 1
    delay = max(policy.base_delay_seconds, 0.0)
    while True:
        try:
            return await operation()
        except Exception as exc:
            if on_error is not None:
                on_error(exc, attempt)
            if attempt >= policy.max_attempts or not is_retryable_exception(exc):
                raise
            jitter = random.uniform(0.0, max(policy.jitter_seconds, 0.0))
            await asyncio.sleep(min(policy.max_delay_seconds, delay) + jitter)
            delay = min(policy.max_delay_seconds, delay * policy.backoff_multiplier)
            attempt += 1
