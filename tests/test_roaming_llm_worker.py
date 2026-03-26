from __future__ import annotations

import json

from dharma_swarm.roaming_llm_worker import (
    render_task_messages,
    resolve_provider_config,
    run_worker,
)


def test_resolve_provider_config_reads_openclaw_config_fallback() -> None:
    config = {
        "env": {"MOONSHOT_API_KEY": "moon-key"},
        "models": {
            "providers": {
                "moonshot": {
                    "baseUrl": "https://api.moonshot.ai/v1",
                    "apiKey": "${MOONSHOT_API_KEY}",
                    "models": [{"id": "kimi-k2.5"}],
                }
            }
        },
    }
    resolved = resolve_provider_config(provider="moonshot", env={}, config=config)
    assert resolved.provider == "moonshot"
    assert resolved.model == "kimi-k2.5"
    assert resolved.base_url == "https://api.moonshot.ai/v1"
    assert resolved.api_key == "moon-key"


def test_render_task_messages_embeds_summary_and_body() -> None:
    messages = render_task_messages(
        callsign="kimi-claw-phone",
        task_id="mbx_123",
        summary="Review this",
        body="Please summarize the risk profile.",
    )
    assert messages[0]["role"] == "system"
    assert "kimi-claw-phone" in messages[0]["content"]
    assert "mbx_123" in messages[1]["content"]
    assert "Review this" in messages[1]["content"]
    assert "risk profile" in messages[1]["content"]


def test_run_worker_wraps_provider_response(monkeypatch) -> None:
    env = {
        "ROAMING_TASK_ID": "mbx_abc",
        "ROAMING_TASK_SUMMARY": "Quick analysis",
        "ROAMING_TASK_BODY": "Give one sentence.",
        "OPENROUTER_API_KEY": "or-key",
    }

    def fake_request_chat_completion(**kwargs):
        assert kwargs["config"].provider == "openrouter"
        return "Markets are range-bound."

    monkeypatch.setattr(
        "dharma_swarm.roaming_llm_worker.request_chat_completion",
        fake_request_chat_completion,
    )

    result = run_worker(
        callsign="kimi-claw-phone",
        env=env,
        config={
            "models": {
                "providers": {
                    "openrouter": {
                        "baseUrl": "https://openrouter.ai/api/v1",
                        "models": [{"id": "moonshotai/kimi-k2.5"}],
                    }
                }
            }
        },
    )
    assert result["summary"] == "kimi-claw-phone handled mbx_abc"
    assert result["body"] == "Markets are range-bound."
    assert result["metadata"]["task_id"] == "mbx_abc"
    assert result["metadata"]["provider"] == "openrouter"
