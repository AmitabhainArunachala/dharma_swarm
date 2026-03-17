"""Tests for error_strategy.py — silent catch triage (Phase 5).

Verifies the @resilient decorator retries, escalates, and swallows
correctly based on configuration.
"""

from __future__ import annotations

import logging

import pytest

from dharma_swarm.error_strategy import (
    CRITICAL,
    EXPECTED,
    TRANSIENT,
    escalate,
    resilient,
)


class TestResilientSync:
    def test_succeeds_first_try(self) -> None:
        call_count = 0

        @resilient(retries=2, level=CRITICAL, swallow=False)
        def good() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        assert good() == "ok"
        assert call_count == 1

    def test_retries_then_succeeds(self) -> None:
        attempts = 0

        @resilient(retries=3, backoff=0.01, level=CRITICAL, swallow=False)
        def flaky() -> str:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ConnectionError("transient")
            return "recovered"

        assert flaky() == "recovered"
        assert attempts == 3

    def test_exhausted_raises(self) -> None:
        @resilient(retries=1, backoff=0.01, level=CRITICAL, swallow=False)
        def always_fail() -> str:
            raise ValueError("permanent")

        with pytest.raises(ValueError, match="permanent"):
            always_fail()

    def test_swallow_returns_none(self) -> None:
        @resilient(retries=0, level=EXPECTED, swallow=True)
        def fail() -> str:
            raise RuntimeError("gone")

        assert fail() is None


class TestResilientAsync:
    @pytest.mark.asyncio
    async def test_async_succeeds(self) -> None:
        @resilient(retries=1, level=CRITICAL, swallow=False)
        async def async_ok() -> str:
            return "async_ok"

        assert await async_ok() == "async_ok"

    @pytest.mark.asyncio
    async def test_async_retries(self) -> None:
        attempts = 0

        @resilient(retries=2, backoff=0.01, level=CRITICAL, swallow=False)
        async def async_flaky() -> str:
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                raise IOError("transient")
            return "recovered"

        assert await async_flaky() == "recovered"
        assert attempts == 2

    @pytest.mark.asyncio
    async def test_async_exhausted_raises(self) -> None:
        @resilient(retries=1, backoff=0.01, level=CRITICAL, swallow=False)
        async def async_fail() -> str:
            raise ValueError("async_permanent")

        with pytest.raises(ValueError, match="async_permanent"):
            await async_fail()

    @pytest.mark.asyncio
    async def test_async_swallow(self) -> None:
        @resilient(retries=0, level=EXPECTED, swallow=True)
        async def async_gone() -> str:
            raise RuntimeError("gone")

        assert await async_gone() is None


class TestEscalate:
    def test_escalate_logs_at_level(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            escalate("subsystem failed", subsystem="stigmergy", level=CRITICAL)
        assert "subsystem failed" in caplog.text
        assert "stigmergy" in caplog.text

    def test_escalate_with_exception(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            escalate(
                "init error",
                exc=RuntimeError("boom"),
                subsystem="engine",
                level=CRITICAL,
            )
        assert "init error" in caplog.text
        assert "boom" in caplog.text


class TestConstants:
    def test_severity_ordering(self) -> None:
        assert EXPECTED < TRANSIENT < CRITICAL
