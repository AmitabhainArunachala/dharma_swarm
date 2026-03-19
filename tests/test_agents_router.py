from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import api.main as api_main
from api.routers import agents as agents_router
from api.routers import chat as chat_router
import dharma_swarm.agent_registry as agent_registry
from dharma_swarm.resident_operator import OperatorEvent


def _agents_client() -> TestClient:
    app = FastAPI()
    app.include_router(agents_router.router)
    return TestClient(app)


def _resident_claude_settings() -> chat_router.ChatRuntimeSettings:
    return chat_router.ChatRuntimeSettings(
        provider="resident_claude",
        api_key_env="CLAUDE_MAX_LOGIN",
        api_key="claude-cli",
        model="claude-opus-4-6",
        max_tool_rounds=chat_router.DEFAULT_MAX_TOOL_ROUNDS,
        max_tokens=chat_router.DEFAULT_MAX_TOKENS,
        timeout_seconds=chat_router.DEFAULT_TIMEOUT_SECONDS,
        tool_result_max_chars=chat_router.DEFAULT_TOOL_RESULT_MAX_CHARS,
        history_message_limit=chat_router.DEFAULT_HISTORY_MESSAGE_LIMIT,
        temperature=chat_router.DEFAULT_TEMPERATURE,
    )


def test_dispatch_routes_opus_primus_to_resident_claude(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_profile_ids: list[str] = []
    captured_dispatches: list[tuple[str, str, str]] = []

    class FakeOperator:
        _running = True

        async def handle_message(self, session_id: str, content: str, client_id: str):
            captured_dispatches.append((session_id, content, client_id))
            yield OperatorEvent(event_type="text_delta", content="resident opus online")
            yield OperatorEvent(event_type="done", metadata={"provider": "claude_resident"})

    def fake_get_chat_settings(profile_id: str | None = None):
        captured_profile_ids.append(str(profile_id))
        return _resident_claude_settings()

    async def fake_brief_context() -> str:
        return "ctx"

    monkeypatch.setattr(chat_router, "_get_chat_settings", fake_get_chat_settings)
    monkeypatch.setattr(
        chat_router,
        "_resident_operator_binding",
        lambda provider: (FakeOperator(), "dashboard_claude", "missing", "not running")
        if provider == "resident_claude"
        else None,
    )
    monkeypatch.setattr(chat_router, "_gather_brief_context", fake_brief_context)

    client = _agents_client()
    resp = client.post(
        "/api/agents/opus-primus/dispatch",
        json={"title": "Review architecture"},
    )

    assert resp.status_code == 200
    assert "resident opus online" in resp.text
    assert '"completed"' in resp.text
    assert captured_profile_ids == ["claude_opus"]
    assert len(captured_dispatches) == 1
    assert captured_dispatches[0][1] == "Review architecture"
    assert captured_dispatches[0][2] == "dashboard_claude"


def test_get_agent_detail_falls_back_to_ginko_identity(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agents_dir = tmp_path / "ginko" / "agents" / "qwen35-surgeon"
    agents_dir.mkdir(parents=True)
    (agents_dir / "identity.json").write_text(
        json.dumps(
            {
                "name": "qwen35-surgeon",
                "role": "coder",
                "model": "qwen3-coder:480b-cloud",
                "status": "idle",
                "created_at": "2026-03-19T03:18:15.193259+00:00",
                "last_active": "2026-03-19T03:18:15.193259+00:00",
                "tasks_completed": 0,
                "total_calls": 0,
            }
        ),
        encoding="utf-8",
    )

    class FakeSwarm:
        async def list_agents(self):
            return []

        async def list_tasks(self):
            return []

    monkeypatch.setattr(agents_router, "GINKO_AGENTS_DIR", tmp_path / "ginko" / "agents")
    monkeypatch.setattr(agents_router, "_get_swarm", lambda: FakeSwarm())

    client = _agents_client()
    resp = client.get("/api/agents/qwen35-surgeon/detail")

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["agent"]["name"] == "qwen35-surgeon"
    assert body["agent"]["provider"] == "ollama"
    assert body["agent"]["model"] == "qwen3-coder:480b-cloud"
    assert body["config"]["provider"] == "ollama"
    assert body["config"]["role"] == "coder"


def test_observatory_route_is_not_shadowed_by_agent_lookup(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnexpectedSwarm:
        async def list_agents(self):
            raise AssertionError("dynamic /agents/{agent_id} route was selected")

    class FakeRegistry:
        def list_agents(self):
            return [
                {
                    "name": "sentinel",
                    "model": "anthropic/claude-opus-4",
                    "role": "observer",
                    "status": "idle",
                    "last_active": "2026-03-19T03:18:15.193259+00:00",
                }
            ]

        def get_agent_fitness(self, name: str):
            assert name == "sentinel"
            return {
                "composite_fitness": 0.92,
                "success_rate": 0.88,
                "avg_latency": 1.2,
                "total_calls": 4,
                "total_tokens": 1024,
                "total_cost_usd": 0.123456,
                "speed_score": 0.75,
            }

        def check_budget(self, name: str):
            assert name == "sentinel"
            return {
                "daily_spent": 0.02,
                "weekly_spent": 0.11,
                "status": "OK",
            }

    class FakeMonitor:
        async def check_health(self):
            return type("Health", (), {"anomalies": []})()

    monkeypatch.setattr(agents_router, "_get_swarm", lambda: UnexpectedSwarm())
    monkeypatch.setattr(agents_router, "GINKO_AGENTS_DIR", tmp_path / "ginko" / "agents")
    monkeypatch.setattr(agent_registry, "get_registry", lambda: FakeRegistry())
    monkeypatch.setattr(api_main, "get_monitor", lambda: FakeMonitor())

    client = _agents_client()
    resp = client.get("/api/agents/observatory")

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["agent_count"] == 1
    assert body["top_performer"] == "sentinel"
    assert body["agents"][0]["name"] == "sentinel"
    assert body["agents"][0]["composite_fitness"] == 0.92


def test_dispatch_routes_qwen35_surgeon_to_qwen_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_profile_ids: list[str] = []

    def fake_get_chat_settings(profile_id: str | None = None):
        captured_profile_ids.append(str(profile_id))
        return chat_router.ChatRuntimeSettings(
            provider="ollama_cloud",
            api_key_env="",
            api_key="ollama-cloud",
            model="qwen3-coder:480b-cloud",
            max_tool_rounds=chat_router.DEFAULT_MAX_TOOL_ROUNDS,
            max_tokens=chat_router.DEFAULT_MAX_TOKENS,
            timeout_seconds=chat_router.DEFAULT_TIMEOUT_SECONDS,
            tool_result_max_chars=chat_router.DEFAULT_TOOL_RESULT_MAX_CHARS,
            history_message_limit=chat_router.DEFAULT_HISTORY_MESSAGE_LIMIT,
            temperature=chat_router.DEFAULT_TEMPERATURE,
        )

    async def fake_brief_context() -> str:
        return "ctx"

    async def fake_call_chat_provider(messages, runtime_settings):
        del messages, runtime_settings
        return {
            "choices": [
                {
                    "message": {
                        "content": "qwen debugger online",
                    },
                }
            ]
        }

    monkeypatch.setattr(chat_router, "_get_chat_settings", fake_get_chat_settings)
    monkeypatch.setattr(chat_router, "_resident_operator_binding", lambda provider: None)
    monkeypatch.setattr(chat_router, "_gather_brief_context", fake_brief_context)
    monkeypatch.setattr(chat_router, "_call_chat_provider", fake_call_chat_provider)

    client = _agents_client()
    resp = client.post(
        "/api/agents/qwen35-surgeon/dispatch",
        json={"title": "Fix the failing debugger panel"},
    )

    assert resp.status_code == 200
    assert "qwen debugger online" in resp.text
    assert captured_profile_ids == ["qwen35_surgeon"]
