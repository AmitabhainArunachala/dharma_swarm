"""Tests for the Messaging Gateway."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.gateway.base import (
    MessageEvent,
    MessageType,
    PlatformAdapter,
    SendResult,
)
from dharma_swarm.gateway.runner import GatewayRunner, _resolve_env_vars


# -- Concrete adapter for testing --

class MockAdapter(PlatformAdapter):
    """Concrete adapter for testing the abstract base."""

    def __init__(self):
        super().__init__("mock", {"enabled": True})
        self.sent_messages: list[tuple[str, str]] = []

    async def connect(self) -> bool:
        self._running = True
        return True

    async def disconnect(self) -> None:
        self._running = False

    async def send(self, chat_id: str, text: str, thread_id: str | None = None) -> SendResult:
        self.sent_messages.append((chat_id, text))
        return SendResult(success=True, message_id="msg_1")


class TestMessageEvent:
    """Tests for MessageEvent model."""

    def test_create_text_event(self):
        event = MessageEvent(
            platform="telegram",
            chat_id="12345",
            user_id="user1",
            text="Hello",
        )
        assert event.platform == "telegram"
        assert event.message_type == MessageType.TEXT
        assert event.text == "Hello"

    def test_create_command_event(self):
        event = MessageEvent(
            platform="discord",
            chat_id="chan1",
            text="/help",
            message_type=MessageType.COMMAND,
        )
        assert event.message_type == MessageType.COMMAND


class TestSendResult:
    """Tests for SendResult model."""

    def test_success(self):
        r = SendResult(success=True, message_id="123")
        assert r.success is True

    def test_failure(self):
        r = SendResult(success=False, error="timeout")
        assert r.success is False
        assert r.error == "timeout"


class TestPlatformAdapter:
    """Tests for the abstract PlatformAdapter via MockAdapter."""

    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        adapter = MockAdapter()
        assert adapter.is_running is False
        assert await adapter.connect() is True
        assert adapter.is_running is True
        await adapter.disconnect()
        assert adapter.is_running is False

    @pytest.mark.asyncio
    async def test_send(self):
        adapter = MockAdapter()
        await adapter.connect()
        result = await adapter.send("chat1", "Hello world")
        assert result.success is True
        assert adapter.sent_messages == [("chat1", "Hello world")]

    @pytest.mark.asyncio
    async def test_set_message_handler(self):
        adapter = MockAdapter()
        responses: list[str] = []

        async def handler(event: MessageEvent) -> str | None:
            responses.append(event.text)
            return f"Echo: {event.text}"

        adapter.set_message_handler(handler)
        await adapter.connect()

        event = MessageEvent(
            platform="mock", chat_id="c1", text="test"
        )
        await adapter._dispatch_message(event)
        assert responses == ["test"]
        assert ("c1", "Echo: test") in adapter.sent_messages

    @pytest.mark.asyncio
    async def test_dispatch_without_handler(self):
        adapter = MockAdapter()
        await adapter.connect()
        event = MessageEvent(platform="mock", chat_id="c1", text="orphan")
        # Should not raise
        await adapter._dispatch_message(event)
        assert adapter.sent_messages == []


class TestResolveEnvVars:
    """Tests for config env var resolution."""

    def test_resolve_simple(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "secret123")
        assert _resolve_env_vars("${MY_TOKEN}") == "secret123"

    def test_resolve_missing(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        assert _resolve_env_vars("${MISSING_VAR}") == ""

    def test_resolve_dict(self, monkeypatch):
        monkeypatch.setenv("A", "val_a")
        result = _resolve_env_vars({"key": "${A}", "plain": "text"})
        assert result == {"key": "val_a", "plain": "text"}

    def test_resolve_list(self, monkeypatch):
        monkeypatch.setenv("X", "42")
        result = _resolve_env_vars(["${X}", "static"])
        assert result == ["42", "static"]

    def test_non_env_string_unchanged(self):
        assert _resolve_env_vars("plain text") == "plain text"


class TestGatewayRunner:
    """Tests for GatewayRunner lifecycle."""

    @pytest.mark.asyncio
    async def test_start_stop_empty_config(self):
        runner = GatewayRunner(config={})
        await runner.start()
        assert runner.is_running is True
        assert len(runner.adapters) == 0
        await runner.stop()
        assert runner.is_running is False

    @pytest.mark.asyncio
    async def test_send_to_unknown_platform(self):
        runner = GatewayRunner(config={})
        await runner.start()
        result = await runner.send_to_platform("telegram", "123", "hello")
        assert result is False
        await runner.stop()
