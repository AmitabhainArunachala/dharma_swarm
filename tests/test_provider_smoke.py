from __future__ import annotations

import asyncio

from api.routers import chat as chat_router
from dharma_swarm.models import ProviderType
from dharma_swarm.provider_smoke import (
    _probe_qwen_dashboard,
    run_provider_smoke,
    strongest_ollama_model,
)
from dharma_swarm.telemetry_plane import TelemetryPlaneStore


def test_strongest_ollama_model_prefers_largest_model_size() -> None:
    models = ["llama3.2:3b", "qwen2.5:14b", "gpt-oss:120b", "nemotron-mini:4b"]
    assert strongest_ollama_model(models) == "gpt-oss:120b"


def test_run_provider_smoke_reports_success_with_monkeypatched_probes(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "test-ollama-key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr(
        "dharma_swarm.provider_smoke.list_ollama_manifest_models",
        lambda base_dir=None: ["llama3.2:3b", "gpt-oss:120b"],
    )

    async def _fake_ollama(model: str):
        return {"status": "ok", "model": model, "response_preview": "OK", "usage": {}}

    async def _fake_nim(model: str):
        return {
            "status": "ok",
            "model": model,
            "response_preview": "OK",
            "usage": {},
            "base_url": "https://nim.local/v1",
        }

    async def _fake_openrouter(model: str):
        return {
            "status": "ok",
            "model": model,
            "response_preview": "OK",
            "usage": {},
        }

    monkeypatch.setattr("dharma_swarm.provider_smoke._probe_ollama", _fake_ollama)
    monkeypatch.setattr("dharma_swarm.provider_smoke._probe_nim", _fake_nim)
    monkeypatch.setattr("dharma_swarm.provider_smoke._probe_openrouter", _fake_openrouter)

    payload = run_provider_smoke()

    assert payload["ollama"]["configured_base_url"] == "https://ollama.com"
    assert payload["ollama"]["transport_mode"] == "cloud_api"
    assert payload["ollama"]["strongest_installed"] is None
    assert payload["ollama"]["status"] == "ok"
    assert "kimi-k2.5:cloud" in payload["ollama"]["catalog_models"]
    assert "minimax-m2.7:cloud" in payload["ollama"]["catalog_models"]
    assert payload["nvidia_nim"]["status"] == "ok"
    assert payload["nvidia_nim"]["deployment_mode"] == "hosted_api"
    assert "moonshotai/kimi-k2.5" in payload["nvidia_nim"]["catalog_models"]["self_hosted"]
    assert payload["nvidia_nim"]["strongest_verified"]
    assert payload["openrouter"]["status"] == "ok"
    assert payload["openrouter"]["strongest_verified"]


def test_run_provider_smoke_skips_empty_openrouter_outputs(monkeypatch) -> None:
    async def _fake_ollama(model: str):
        return {"status": "ok", "model": model, "response_preview": "OK", "usage": {}}

    async def _fake_nim(model: str):
        return {"status": "ok", "model": model, "response_preview": "OK", "usage": {}}

    async def _fake_openrouter(model: str):
        if model == "moonshotai/kimi-k2.5":
            return {
                "status": "empty_response",
                "model": model,
                "response_preview": "",
                "usage": {},
            }
        return {
            "status": "ok",
            "model": model,
            "response_preview": "OK",
            "usage": {},
        }

    monkeypatch.setattr("dharma_swarm.provider_smoke._probe_ollama", _fake_ollama)
    monkeypatch.setattr("dharma_swarm.provider_smoke._probe_nim", _fake_nim)
    monkeypatch.setattr("dharma_swarm.provider_smoke._probe_openrouter", _fake_openrouter)

    payload = run_provider_smoke()

    assert payload["openrouter"]["status"] == "ok"
    assert payload["openrouter"]["strongest_verified"] != "moonshotai/kimi-k2.5"


def test_run_provider_smoke_includes_qwen_dashboard_when_requested(monkeypatch) -> None:
    async def _fake_ollama(model: str):
        return {"status": "ok", "model": model, "response_preview": "OK", "usage": {}}

    async def _fake_nim(model: str):
        return {"status": "ok", "model": model, "response_preview": "OK", "usage": {}}

    async def _fake_openrouter(model: str):
        return {"status": "ok", "model": model, "response_preview": "OK", "usage": {}}

    async def _fake_qwen(provider_name: str, task: str):
        return {
            "status": "ok",
            "requested_provider": provider_name,
            "resolved_provider": provider_name,
            "task": task,
            "tool_names": ["read_file", "grep_search"],
        }

    monkeypatch.setattr("dharma_swarm.provider_smoke._probe_ollama", _fake_ollama)
    monkeypatch.setattr("dharma_swarm.provider_smoke._probe_nim", _fake_nim)
    monkeypatch.setattr("dharma_swarm.provider_smoke._probe_openrouter", _fake_openrouter)
    monkeypatch.setattr("dharma_swarm.provider_smoke._probe_qwen_dashboard", _fake_qwen)

    payload = run_provider_smoke(qwen_provider="together")

    assert payload["qwen_dashboard"]["status"] == "ok"
    assert payload["qwen_dashboard"]["requested_provider"] == "together"
    assert payload["qwen_dashboard"]["tool_names"] == ["read_file", "grep_search"]


def test_run_provider_smoke_persists_probe_outcomes_when_telemetry_db_requested(
    monkeypatch,
    tmp_path,
) -> None:
    telemetry_db = tmp_path / "runtime.db"

    async def _fake_ollama(model: str):
        return {"status": "ok", "model": model, "response_preview": "OK", "usage": {}}

    async def _fake_nim(model: str):
        return {"status": "timeout", "model": model, "response_preview": "", "usage": {}}

    async def _fake_openrouter(model: str):
        return {"status": "ok", "model": model, "response_preview": "OK", "usage": {}}

    async def _fake_qwen(provider_name: str, task: str):
        return {
            "status": "ok",
            "requested_provider": provider_name,
            "resolved_provider": provider_name,
            "task": task,
            "tool_names": ["read_file", "grep_search"],
        }

    monkeypatch.setattr("dharma_swarm.provider_smoke._probe_ollama", _fake_ollama)
    monkeypatch.setattr("dharma_swarm.provider_smoke._probe_nim", _fake_nim)
    monkeypatch.setattr("dharma_swarm.provider_smoke._probe_openrouter", _fake_openrouter)
    monkeypatch.setattr("dharma_swarm.provider_smoke._probe_qwen_dashboard", _fake_qwen)

    payload = run_provider_smoke(
        qwen_provider="together",
        telemetry_db_path=telemetry_db,
    )

    telemetry = payload["_telemetry"]
    assert telemetry["status"] == "persisted"
    assert telemetry["db_path"] == str(telemetry_db)
    assert telemetry["outcome_count"] == 4

    store = TelemetryPlaneStore(telemetry_db)
    outcomes = asyncio.run(
        store.list_external_outcomes(
            session_id=telemetry["session_id"],
            limit=10,
        )
    )

    assert len(outcomes) == 4
    assert {item.outcome_kind for item in outcomes} == {"provider_smoke_probe"}
    probe_names = {item.metadata["probe_name"] for item in outcomes}
    assert probe_names == {"ollama", "nvidia_nim", "openrouter", "qwen_dashboard"}
    qwen_outcome = next(item for item in outcomes if item.metadata["probe_name"] == "qwen_dashboard")
    assert qwen_outcome.subject_id == "together"
    assert qwen_outcome.status == "ok"


def test_probe_qwen_dashboard_reports_missing_config(monkeypatch) -> None:
    monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
    monkeypatch.setenv("DASHBOARD_QWEN_PROVIDER_ORDER", "together")

    result = asyncio.run(_probe_qwen_dashboard("together", "inspect wiring"))

    assert result["status"] == "missing_config"
    assert result["requested_provider"] == "together"
    assert result["required_env_key"] == "TOGETHER_API_KEY"


def test_probe_qwen_dashboard_collects_tool_calls_and_content(
    monkeypatch,
) -> None:
    settings = chat_router.ChatRuntimeSettings(
        provider=ProviderType.TOGETHER,
        api_key="together-key",
        base_url="https://api.together.xyz/v1",
        model="Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8",
        available=True,
        max_tool_rounds=4,
        max_tokens=1024,
        timeout_seconds=30.0,
        tool_result_max_chars=2000,
        history_message_limit=20,
        temperature=0.0,
    )

    monkeypatch.setenv("TOGETHER_API_KEY", "together-key")
    monkeypatch.setattr(chat_router, "_get_chat_settings", lambda profile_id=None: settings)

    async def _fake_agentic_stream(messages, runtime_settings, *, session_id="", profile_id=""):
        del messages
        del runtime_settings
        del session_id
        del profile_id
        yield 'data: {"tool_call":{"name":"read_file","args":{"path":"dharma_swarm/runtime_provider.py"}}}\n\n'
        yield 'data: {"tool_result":{"name":"read_file","summary":"runtime provider loaded"}}\n\n'
        yield 'data: {"content":"Resolved provider and tool path confirmed."}\n\n'
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(chat_router, "_agentic_stream", _fake_agentic_stream)

    result = asyncio.run(_probe_qwen_dashboard("together", "inspect wiring"))

    assert result["status"] == "ok"
    assert result["resolved_provider"] == "together"
    assert result["tool_call_count"] == 1
    assert result["tool_result_count"] == 1
    assert result["tool_names"] == ["read_file"]
    assert "Resolved provider" in result["response_preview"]
