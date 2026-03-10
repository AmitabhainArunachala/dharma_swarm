from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from dharma_swarm.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    CircuitBreakerRegistry,
    InMemoryCircuitStateStore,
    RedisCircuitStateStore,
    RetryPolicy,
    run_with_retry,
)


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_circuit_breaker_opens_on_failure_rate_threshold() -> None:
    clock = _Clock()
    breaker = CircuitBreaker(
        CircuitBreakerConfig(
            window_seconds=60.0,
            failure_rate_threshold=0.50,
            min_samples=4,
            open_duration_seconds=30.0,
        ),
        time_fn=clock.now,
    )
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    breaker.record_success()
    assert breaker.state == CircuitState.OPEN


def test_circuit_breaker_half_open_then_closes_on_success() -> None:
    clock = _Clock()
    breaker = CircuitBreaker(
        CircuitBreakerConfig(
            window_seconds=60.0,
            failure_rate_threshold=0.50,
            min_samples=2,
            open_duration_seconds=10.0,
            half_open_max_attempts=1,
        ),
        time_fn=clock.now,
    )
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert breaker.allow_request() is False

    clock.advance(11.0)
    assert breaker.allow_request() is True
    assert breaker.allow_request() is False

    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.allow_request() is True


def test_breaker_registry_reuses_breaker() -> None:
    registry = CircuitBreakerRegistry()
    first = registry.get("openrouter:gpt-5-mini")
    second = registry.get("openrouter:gpt-5-mini")
    assert first is second


def test_breaker_registry_persists_state_with_shared_store() -> None:
    store = InMemoryCircuitStateStore()
    config = CircuitBreakerConfig(
        failure_rate_threshold=0.5,
        min_samples=2,
        open_duration_seconds=30.0,
    )
    first_registry = CircuitBreakerRegistry(config=config, store=store)
    first_breaker = first_registry.get("provider:model")
    first_breaker.record_failure()
    first_breaker.record_failure()
    assert first_breaker.state == CircuitState.OPEN

    second_registry = CircuitBreakerRegistry(config=config, store=store)
    second_breaker = second_registry.get("provider:model")
    assert second_breaker.state == CircuitState.OPEN


def test_breaker_registry_falls_back_when_store_errors() -> None:
    class _FailingStore:
        def load(self, key: str):
            raise RuntimeError("redis unavailable")

        def save(self, key: str, payload: dict[str, object]):
            raise RuntimeError("redis unavailable")

    registry = CircuitBreakerRegistry(
        config=CircuitBreakerConfig(min_samples=2, failure_rate_threshold=0.5),
        store=_FailingStore(),  # type: ignore[arg-type]
    )
    breaker = registry.get("provider:model")
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    # Registry should continue serving the same lane without surfacing store failures.
    again = registry.get("provider:model")
    assert again is breaker


def test_redis_circuit_store_roundtrip(monkeypatch) -> None:
    payloads: dict[str, str] = {}

    class _FakeRedisClient:
        def get(self, key: str):
            return payloads.get(key)

        def setex(self, key: str, ttl: int, value: str):
            payloads[key] = value

    class _FakeRedis:
        @staticmethod
        def from_url(url: str, decode_responses: bool = True):
            return _FakeRedisClient()

    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(Redis=_FakeRedis))
    store = RedisCircuitStateStore("redis://localhost:6379/0")
    store.save("lane-a", {"state": "open", "count": 2})
    loaded = store.load("lane-a")
    assert loaded is not None
    assert loaded["state"] == "open"
    assert loaded["count"] == 2


@pytest.mark.asyncio
async def test_run_with_retry_retries_then_succeeds(monkeypatch) -> None:
    calls = {"n": 0}

    async def no_sleep(_: float) -> None:
        return None

    async def operation() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient failure")
        return "ok"

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    out = await run_with_retry(
        operation,
        policy=RetryPolicy(
            max_attempts=3,
            base_delay_seconds=0.0,
            jitter_seconds=0.0,
            max_delay_seconds=0.0,
        ),
    )
    assert out == "ok"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_run_with_retry_stops_on_non_retryable_error() -> None:
    calls = {"n": 0}

    async def operation() -> str:
        calls["n"] += 1
        raise RuntimeError("API key not set")

    with pytest.raises(RuntimeError, match="API key not set"):
        await run_with_retry(
            operation,
            policy=RetryPolicy(
                max_attempts=5,
                base_delay_seconds=0.0,
                jitter_seconds=0.0,
                max_delay_seconds=0.0,
            ),
        )
    assert calls["n"] == 1
