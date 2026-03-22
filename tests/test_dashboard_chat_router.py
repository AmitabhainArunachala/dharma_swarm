from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.routers import chat as chat_router


def _chat_client() -> TestClient:
    app = FastAPI()
    app.include_router(chat_router.router)
    return TestClient(app)


def test_chat_status_reports_runtime_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("DASHBOARD_CHAT_MODEL", "anthropic/claude-opus-4-6")
    monkeypatch.setenv("DASHBOARD_QWEN_MODEL", "qwen/qwen3-coder:free")
    monkeypatch.setenv("DASHBOARD_GLM_MODEL", "z-ai/glm-5")
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
    assert body["chat_contract_version"] == chat_router.CHAT_CONTRACT_VERSION
    assert body["model"] == "anthropic/claude-opus-4-6"
    assert body["provider"] == "openrouter"
    assert body["max_tool_rounds"] == 64
    assert body["max_tokens"] == 12288
    assert body["timeout_seconds"] == 420.0
    assert body["tool_result_max_chars"] == 36000
    assert body["history_message_limit"] == 150
    assert body["persistent_sessions"] is False
    assert body["default_profile_id"] == "claude_opus"
    assert len(body["profiles"]) == 4
    claude = next(profile for profile in body["profiles"] if profile["id"] == "claude_opus")
    assert claude["available"] is True
    assert claude["availability_kind"] == "api_key"
    assert "OpenRouter" in claude["status_note"]
    qwen = next(profile for profile in body["profiles"] if profile["id"] == "qwen35_surgeon")
    assert qwen["model"] == "qwen/qwen3-coder:free"
    assert qwen["available"] is True
    glm = next(profile for profile in body["profiles"] if profile["id"] == "glm5_researcher")
    assert glm["model"] == "z-ai/glm-5"
    assert glm["available"] is True


def test_chat_status_uses_configured_default_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("DASHBOARD_DEFAULT_PROFILE_ID", "codex_operator")

    client = _chat_client()
    resp = client.get("/api/chat/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["default_profile_id"] == "codex_operator"
    assert body["model"] == "openai/gpt-5-codex"


def test_qwen_profile_clamps_max_tool_rounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("DASHBOARD_CHAT_MAX_TOOL_ROUNDS", "64")

    settings = chat_router._get_chat_settings("qwen35_surgeon")

    assert settings.max_tool_rounds == chat_router.QWEN_MAX_TOOL_ROUNDS
    assert settings.model == "qwen/qwen3-coder"


@pytest.mark.asyncio
async def test_agentic_stream_reports_missing_visible_qwen_output() -> None:
    settings = chat_router._get_chat_settings("qwen35_surgeon")

    async def fake_call_openrouter(messages, runtime_settings):
        del messages
        assert runtime_settings.model == "qwen/qwen3-coder"
        return {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "reasoning": "I should answer directly, but I used my output budget on reasoning.",
                        "tool_calls": None,
                    },
                    "finish_reason": "stop",
                }
            ]
        }

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(chat_router, "_call_openrouter", fake_call_openrouter)
    try:
        chunks = [
            chunk
            async for chunk in chat_router._agentic_stream(
                [{"role": "user", "content": "say OK"}],
                settings,
            )
        ]
    finally:
        monkeypatch.undo()

    payload = "".join(chunks)
    assert "returned reasoning without visible output" in payload
    assert "qwen/qwen3-coder" in payload


@pytest.mark.asyncio
async def test_agentic_stream_stops_after_max_tool_rounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHBOARD_CHAT_MAX_TOOL_ROUNDS", "2")
    settings = chat_router._get_chat_settings()
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
