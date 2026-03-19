from __future__ import annotations

import json
import sys
import types

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.routers import chat as chat_router
from dharma_swarm.resident_operator import OperatorEvent


def _chat_client() -> TestClient:
    app = FastAPI()
    app.include_router(chat_router.router)
    return TestClient(app)


def test_chat_status_reports_runtime_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_router, "_claude_max_available", lambda: True)
    monkeypatch.setenv("DASHBOARD_CHAT_MODEL", "claude-opus-4-6")
    monkeypatch.setenv("DASHBOARD_CHAT_MAX_TOOL_ROUNDS", "64")
    monkeypatch.setenv("DASHBOARD_CHAT_MAX_TOKENS", "12288")
    monkeypatch.setenv("DASHBOARD_CHAT_TIMEOUT_SECONDS", "420")
    monkeypatch.setenv("DASHBOARD_CHAT_TOOL_RESULT_MAX_CHARS", "36000")
    monkeypatch.setenv("DASHBOARD_CHAT_HISTORY_MESSAGE_LIMIT", "150")

    client = _chat_client()
    resp = client.get("/api/chat/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert body["model"] == "claude-opus-4-6"
    assert body["provider"] == "claude_max"
    assert body["max_tool_rounds"] == 64
    assert body["max_tokens"] == 12288
    assert body["timeout_seconds"] == 420.0
    assert body["tool_result_max_chars"] == 36000
    assert body["history_message_limit"] == 150
    assert body["persistent_sessions"] is True
    assert body["chat_ws_path_template"] == "/ws/chat/{session_id}"


def _openai_settings() -> chat_router.ChatRuntimeSettings:
    return chat_router.ChatRuntimeSettings(
        provider="openai",
        api_key_env="OPENAI_API_KEY",
        api_key="test-openai-key",
        model="gpt-5.4",
        max_tool_rounds=chat_router.DEFAULT_MAX_TOOL_ROUNDS,
        max_tokens=chat_router.DEFAULT_MAX_TOKENS,
        timeout_seconds=chat_router.DEFAULT_TIMEOUT_SECONDS,
        tool_result_max_chars=chat_router.DEFAULT_TOOL_RESULT_MAX_CHARS,
        history_message_limit=chat_router.DEFAULT_HISTORY_MESSAGE_LIMIT,
        temperature=chat_router.DEFAULT_TEMPERATURE,
    )


def test_chat_status_reports_codex_profile_as_resident_operator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_router, "_claude_max_available", lambda: True)
    monkeypatch.setattr(chat_router, "_codex_cli_available", lambda: True)
    monkeypatch.setenv("DASHBOARD_CODEX_MODEL", "gpt-5.4")

    client = _chat_client()
    resp = client.get("/api/chat/status")

    assert resp.status_code == 200
    body = resp.json()
    codex = next(profile for profile in body["profiles"] if profile["id"] == "codex_operator")

    assert codex["provider"] == "resident_codex"
    assert codex["model"] == "gpt-5.4"


def test_chat_settings_marks_resident_codex_ready_when_cli_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_router, "_codex_cli_available", lambda: True)

    settings = chat_router._get_chat_settings("codex_operator")

    assert settings.provider == "resident_codex"
    assert settings.api_key == "codex-cli"
    assert settings.api_key_env == "CODEX_CLI"


def test_resolve_api_key_falls_back_to_keychain_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("USER", "dhyana")

    def fake_lookup(service: str, *, account: str | None = None) -> str:
        assert service == "openai-api-key"
        assert account == "dhyana"
        return "sk-test-openai"

    monkeypatch.setattr(chat_router, "_lookup_keychain_secret", fake_lookup)

    assert chat_router._resolve_api_key("OPENAI_API_KEY") == "sk-test-openai"


def test_extract_openrouter_affordable_max_tokens() -> None:
    error_text = (
        "This request requires more credits. You requested up to 8192 tokens, "
        "but can only afford 71."
    )

    assert chat_router._extract_openrouter_affordable_max_tokens(error_text) == 71
    assert chat_router._extract_openrouter_affordable_max_tokens("no cap here") is None


def test_extract_openai_retry_after_seconds() -> None:
    error_text = (
        'OpenAI 429: {"error":{"message":"Rate limit reached. '
        'Please try again in 5.61s."}}'
    )

    assert chat_router._extract_openai_retry_after_seconds(error_text) == 5.61
    assert chat_router._extract_openai_retry_after_seconds("retry later") is None


@pytest.mark.asyncio
async def test_call_openai_uses_max_completion_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _openai_settings()
    captured_payload: dict[str, object] = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "ok"}}]}

    class FakeAsyncClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, *, headers=None, json=None):
            del url, headers
            assert json is not None
            captured_payload.update(json)
            return FakeResponse()

    fake_httpx = types.SimpleNamespace(
        AsyncClient=FakeAsyncClient,
        Timeout=lambda timeout: timeout,
        HTTPError=RuntimeError,
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    result = await chat_router._call_openai(
        [{"role": "user", "content": "hello"}],
        settings,
    )

    assert result["choices"][0]["message"]["content"] == "ok"
    assert captured_payload["max_completion_tokens"] == settings.max_tokens
    assert "max_tokens" not in captured_payload


@pytest.mark.asyncio
async def test_call_openai_retries_after_transient_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _openai_settings()
    payloads: list[dict[str, object]] = []
    sleeps: list[float] = []

    class FakeResponse:
        def __init__(self, status_code: int, text: str = "", data: dict | None = None):
            self.status_code = status_code
            self.text = text
            self._data = data or {}

        def json(self) -> dict:
            return self._data

    class FakeAsyncClient:
        def __init__(self, timeout=None):
            self.timeout = timeout
            self.calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, *, headers=None, json=None):
            del url, headers
            assert json is not None
            payloads.append(dict(json))
            self.calls += 1
            if self.calls == 1:
                return FakeResponse(
                    429,
                    'Rate limit reached. Please try again in 5.61s.',
                )
            return FakeResponse(
                200,
                data={"choices": [{"message": {"content": "retried ok"}}]},
            )

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    fake_httpx = types.SimpleNamespace(
        AsyncClient=FakeAsyncClient,
        Timeout=lambda timeout: timeout,
        HTTPError=RuntimeError,
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
    monkeypatch.setattr(chat_router.asyncio, "sleep", fake_sleep)

    result = await chat_router._call_openai(
        [{"role": "user", "content": "hello"}],
        settings,
    )

    assert result["choices"][0]["message"]["content"] == "retried ok"
    assert len(payloads) == 2
    assert sleeps == [5.61]


@pytest.mark.asyncio
async def test_call_openrouter_retries_with_affordable_token_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = chat_router.ChatRuntimeSettings(
        provider="openrouter",
        api_key_env="OPENROUTER_API_KEY",
        api_key="test-router-key",
        model="anthropic/claude-opus-4-6",
        max_tool_rounds=40,
        max_tokens=chat_router.DEFAULT_MAX_TOKENS,
        timeout_seconds=chat_router.DEFAULT_TIMEOUT_SECONDS,
        tool_result_max_chars=chat_router.DEFAULT_TOOL_RESULT_MAX_CHARS,
        history_message_limit=chat_router.DEFAULT_HISTORY_MESSAGE_LIMIT,
        temperature=chat_router.DEFAULT_TEMPERATURE,
    )
    payloads: list[dict[str, object]] = []

    class FakeResponse:
        def __init__(self, status_code: int, text: str = "", data: dict | None = None):
            self.status_code = status_code
            self.text = text
            self._data = data or {}

        def json(self) -> dict:
            return self._data

    class FakeAsyncClient:
        def __init__(self, timeout=None):
            self.timeout = timeout
            self.calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, *, headers=None, json=None):
            del url, headers
            assert json is not None
            payloads.append(dict(json))
            self.calls += 1
            if self.calls == 1:
                return FakeResponse(
                    402,
                    "You requested up to 8192 tokens, but can only afford 71.",
                )
            return FakeResponse(
                200,
                data={"choices": [{"message": {"content": "ok"}}]},
            )

    fake_httpx = types.SimpleNamespace(
        AsyncClient=FakeAsyncClient,
        Timeout=lambda timeout: timeout,
        HTTPError=RuntimeError,
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    result = await chat_router._call_openrouter(
        [{"role": "user", "content": "hello"}],
        settings,
    )

    assert result["choices"][0]["message"]["content"] == "ok"
    assert payloads[0]["max_tokens"] == settings.max_tokens
    assert payloads[1]["max_tokens"] == 71


@pytest.mark.asyncio
async def test_agentic_stream_uses_claude_max_for_claude_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_router, "_claude_max_available", lambda: True)
    settings = chat_router._get_chat_settings("claude_opus")

    async def fake_call_claude_max(messages, runtime_settings):
        del messages
        assert runtime_settings.provider == "claude_max"
        assert runtime_settings.model == "claude-opus-4-6"
        return {
            "choices": [
                {
                    "message": {
                        "content": "claude max online",
                    },
                    "finish_reason": "stop",
                }
            ]
        }

    monkeypatch.setattr(chat_router, "_call_claude_max", fake_call_claude_max)

    chunks = [
        chunk
        async for chunk in chat_router._agentic_stream(
            [{"role": "user", "content": "wire it up"}],
            settings,
        )
    ]
    payload = "".join(chunks)

    assert "claude max online" in payload


@pytest.mark.asyncio
async def test_agentic_stream_stops_after_max_tool_rounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = chat_router.ChatRuntimeSettings(
        provider="openrouter",
        api_key_env="OPENROUTER_API_KEY",
        api_key="test-router-key",
        model="anthropic/claude-opus-4-6",
        max_tool_rounds=2,
        max_tokens=chat_router.DEFAULT_MAX_TOKENS,
        timeout_seconds=chat_router.DEFAULT_TIMEOUT_SECONDS,
        tool_result_max_chars=chat_router.DEFAULT_TOOL_RESULT_MAX_CHARS,
        history_message_limit=chat_router.DEFAULT_HISTORY_MESSAGE_LIMIT,
        temperature=chat_router.DEFAULT_TEMPERATURE,
    )
    call_count = 0

    async def fake_call_openrouter(messages, runtime_settings):
        nonlocal call_count
        del messages
        assert runtime_settings.max_tool_rounds == 2
        call_count += 1
        return {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": f"tc-{call_count}",
                                "function": {
                                    "name": "read_file",
                                    "arguments": '{"path":"/tmp/demo.txt"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }

    async def fake_execute_tool(name, args):
        assert name == "read_file"
        assert args == {"path": "/tmp/demo.txt"}
        return "ok"

    monkeypatch.setattr(chat_router, "_call_openrouter", fake_call_openrouter)
    monkeypatch.setattr(chat_router, "execute_tool", fake_execute_tool)

    chunks = [
        chunk
        async for chunk in chat_router._agentic_stream(
            [{"role": "user", "content": "inspect the repo"}],
            settings,
        )
    ]
    payload = "".join(chunks)

    assert call_count == 2
    assert "[Reached maximum tool rounds. Stopping.]" in payload


@pytest.mark.asyncio
async def test_stream_resident_codex_routes_dashboard_codex_profile_to_operator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[str, str, str]] = []

    class FakeOperator:
        _running = True

        async def handle_message(self, session_id: str, content: str, client_id: str):
            captured.append((session_id, content, client_id))
            yield OperatorEvent(event_type="text_delta", content="resident codex online")
            yield OperatorEvent(
                event_type="tool_call",
                content=json.dumps({"name": "shell", "args": {"command": "pwd"}}),
                metadata={"tool": "shell"},
            )
            yield OperatorEvent(
                event_type="tool_result",
                content="/Users/dhyana/dharma_swarm",
                metadata={"tool": "shell"},
            )
            yield OperatorEvent(
                event_type="done",
                metadata={"provider": "codex_resident"},
            )

    async def fake_noop(*args, **kwargs):
        del args, kwargs
        return None

    monkeypatch.setattr(chat_router, "_get_resident_codex_operator", lambda: FakeOperator())
    monkeypatch.setattr(chat_router, "_publish_residual_turn", fake_noop)
    monkeypatch.setattr(chat_router, "_broadcast_chat_event", fake_noop)
    monkeypatch.setattr(chat_router, "_log_conversation", lambda *args, **kwargs: None)
    monkeypatch.setitem(
        sys.modules,
        "dharma_swarm.conversation_log",
        types.SimpleNamespace(log_exchange=lambda *args, **kwargs: None),
    )

    client = _chat_client()
    resp = client.post(
        "/api/chat",
        json={
            "profile_id": "codex_operator",
            "session_id": "sess-1",
            "messages": [{"role": "user", "content": "wire it up"}],
        },
    )

    assert resp.status_code == 200
    assert resp.headers["x-chat-session-id"] == "sess-1"
    assert "resident codex online" in resp.text
    assert '"tool_call"' in resp.text
    assert '"tool_result"' in resp.text
    assert captured == [("sess-1", "wire it up", "dashboard_codex")]


@pytest.mark.asyncio
async def test_agentic_stream_surfaces_openai_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _openai_settings()

    async def fake_call_openai(messages, runtime_settings):
        del messages, runtime_settings
        return {"_error": "OpenAI 400: bad request"}

    monkeypatch.setattr(chat_router, "_call_openai", fake_call_openai)

    chunks = [
        chunk
        async for chunk in chat_router._agentic_stream(
            [{"role": "user", "content": "wire it up"}],
            settings,
        )
    ]
    payload = "".join(chunks)

    assert "OpenAI 400: bad request" in payload


def test_delta_messages_for_session_prefers_newest_user_when_server_has_history() -> None:
    existing = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    incoming = [{"role": "user", "content": "what next?"}]

    assert chat_router._delta_messages_for_session(existing, incoming) == incoming


def test_chat_stream_uses_persisted_session_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_router, "_claude_max_available", lambda: True)

    class FakeConversationStore:
        def __init__(self) -> None:
            self.sessions = {
                "sess-1": [
                    {"role": "user", "content": "hello", "seq": 1},
                    {"role": "assistant", "content": "hi", "seq": 2},
                ]
            }

        async def create_session(self, session_id: str, client_id: str = "", metadata=None):
            del client_id, metadata
            self.sessions.setdefault(session_id, [])
            return session_id

        async def add_turn(
            self,
            session_id: str,
            role: str,
            content: str = "",
            tool_calls=None,
            tool_results=None,
            token_count: int = 0,
            cost_usd: float = 0.0,
            quality_score: float = 0.0,
        ):
            del tool_calls, tool_results, token_count, cost_usd, quality_score
            turns = self.sessions.setdefault(session_id, [])
            seq = len(turns) + 1
            turns.append({"role": role, "content": content, "seq": seq})
            return f"turn-{seq}", seq

        async def get_history(self, session_id: str, limit: int = 100, after_seq: int = 0):
            turns = self.sessions.get(session_id, [])
            return [turn for turn in turns if turn["seq"] > after_seq][:limit]

    store = FakeConversationStore()
    captured_messages: list[dict[str, str]] = []

    async def fake_get_store():
        return store

    async def fake_call_claude_max(messages, runtime_settings):
        del runtime_settings
        captured_messages.extend(messages)
        return {
            "choices": [
                {
                    "message": {
                        "content": "server remembered context",
                    },
                    "finish_reason": "stop",
                }
            ]
        }

    async def fake_context():
        return "ctx"

    async def fake_noop(*args, **kwargs):
        del args, kwargs
        return None

    monkeypatch.setattr(chat_router, "_get_chat_conversation_store", fake_get_store)
    monkeypatch.setattr(chat_router, "_call_claude_max", fake_call_claude_max)
    monkeypatch.setattr(chat_router, "_gather_brief_context", fake_context)
    monkeypatch.setattr(chat_router, "_broadcast_chat_event", fake_noop)
    monkeypatch.setattr(chat_router, "_publish_residual_turn", fake_noop)
    monkeypatch.setattr(chat_router, "_log_conversation", lambda *args, **kwargs: None)
    monkeypatch.setitem(
        sys.modules,
        "dharma_swarm.conversation_log",
        types.SimpleNamespace(log_exchange=lambda *args, **kwargs: None),
    )

    client = _chat_client()
    resp = client.post(
        "/api/chat",
        json={
            "profile_id": "claude_opus",
            "session_id": "sess-1",
            "messages": [{"role": "user", "content": "what next?"}],
        },
    )

    assert resp.status_code == 200
    assert resp.headers["x-chat-session-id"] == "sess-1"
    assert '"session"' in resp.text
    assert '"sess-1"' in resp.text
    assert any(msg["role"] == "user" and msg["content"] == "hello" for msg in captured_messages)
    assert any(msg["role"] == "assistant" and msg["content"] == "hi" for msg in captured_messages)
    assert any(msg["role"] == "user" and msg["content"] == "what next?" for msg in captured_messages)
