from __future__ import annotations

from dharma_swarm import api_key_audit as audit


def test_configured_key_names_only_returns_nonempty_entries() -> None:
    env = {
        "OPENAI_API_KEY": "set",
        "OPENROUTER_API_KEY": "",
        "GROQ_API_KEY": " also-set ",
    }

    assert audit.configured_key_names(env) == [
        "OPENAI_API_KEY",
        "GROQ_API_KEY",
    ]


def test_summarize_audit_records_uses_completion_when_auth_probe_is_skipped() -> None:
    records = [
        {
            "configured": True,
            "provider": "ollama",
            "auth": {"status": "skipped"},
            "default_completion": {"status": "ok"},
            "default_agentic": {"status": "error"},
        },
        {
            "configured": True,
            "provider": "openrouter",
            "auth": {"status": "ok"},
            "default_completion": {"status": "ok"},
            "default_agentic": {"status": "ok"},
        },
        {
            "configured": True,
            "provider": "",
            "auth": {"status": "error"},
            "default_completion": {"status": "unwired"},
            "default_agentic": {"status": "unwired"},
        },
    ]

    summary = audit.summarize_audit_records(records)

    assert summary == {
        "configured": 3,
        "configured_auth_ok": 2,
        "default_completion_ok": 2,
        "default_agentic_ok": 1,
        "wired": 2,
        "unwired": 1,
    }


def test_text_report_renders_configured_records_only() -> None:
    payload = {
        "canonical_runtime_owner": "dharma_swarm/runtime_provider.py",
        "documented_env_path": ".env.template",
        "summary": {
            "configured": 1,
            "configured_auth_ok": 1,
            "default_completion_ok": 1,
            "default_agentic_ok": 1,
            "wired": 1,
            "unwired": 0,
        },
        "records": [
            {
                "key_name": "OPENAI_API_KEY",
                "configured": True,
                "provider": "openai",
                "notes": "Direct OpenAI lane.",
                "auth": {"status": "ok"},
                "default_completion": {
                    "status": "ok",
                    "model": "gpt-5",
                    "base_url": "https://api.openai.com/v1",
                },
                "default_agentic": {"status": "error", "error": "bad default"},
            },
            {
                "key_name": "OPENROUTER_API_KEY",
                "configured": False,
                "provider": "openrouter",
                "notes": "",
                "auth": {"status": "missing_config"},
                "default_completion": {"status": "missing_config"},
                "default_agentic": {"status": "missing_config"},
            },
        ],
    }

    report = audit._render_text_report(payload)

    assert "OPENAI_API_KEY:" in report
    assert "OPENROUTER_API_KEY:" not in report
    assert "default_agentic: error" in report
