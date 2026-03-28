from __future__ import annotations

from unittest.mock import patch

from dharma_swarm.cron_job_runtime import CronJobRunStatus
from dharma_swarm.cron_runner import execute_cron_job, run_cron_job
from dharma_swarm.models import LLMResponse, ProviderType
from dharma_swarm.runtime_provider import RuntimeProviderConfig


def test_run_cron_job_dispatches_headless_prompt():
    with patch("dharma_swarm.pulse.run_claude_headless", return_value="Mission pulse ok") as mock:
        success, output, error = run_cron_job(
            {
                "id": "job-1",
                "name": "pulse",
                "handler": "headless_prompt",
                "prompt": "say hi",
                "model": "haiku",
                "timeout_sec": 30,
            }
        )

    assert success is True
    assert "Cron Job: pulse" in output
    assert "Mission pulse ok" in output
    assert error is None
    mock.assert_called_once_with(prompt="say hi", timeout=30, model="haiku")


def test_run_cron_job_surfaces_headless_failures():
    with patch("dharma_swarm.pulse.run_claude_headless", return_value="ERROR: boom"):
        success, output, error = run_cron_job(
            {
                "name": "pulse",
                "handler": "headless_prompt",
                "prompt": "say hi",
            }
        )

    assert success is False
    assert "ERROR: boom" in output
    assert error == "ERROR: boom"


def test_run_cron_job_keeps_default_headless_jobs_claude_locked_without_explicit_portable_surface():
    with patch("dharma_swarm.pulse.run_claude_headless", return_value="Mission pulse ok") as mock_claude:
        with patch("dharma_swarm.cron_runner.complete_via_preferred_runtime_providers") as mock_runtime:
            success, output, error = run_cron_job(
                {
                    "id": "job-locked",
                    "name": "Locked pulse",
                    "handler": "headless_prompt",
                    "prompt": "say hi",
                    "available_provider_types": [ProviderType.OLLAMA.value, ProviderType.GROQ.value],
                }
            )

    assert success is True
    assert "Mission pulse ok" in output
    assert error is None
    mock_claude.assert_called_once()
    mock_runtime.assert_not_called()


def test_run_cron_job_portable_headless_uses_hosted_runtime_provider_chain():
    async def _fake_complete(**kwargs):
        assert kwargs["messages"] == [{"role": "user", "content": "say hi"}]
        assert kwargs["provider_order"] == (ProviderType.OLLAMA, ProviderType.GROQ)
        assert kwargs["openrouter_model"] is None
        return (
            LLMResponse(
                content="Portable ok",
                model="glm-5:cloud",
                provider=ProviderType.OLLAMA.value,
            ),
            RuntimeProviderConfig(
                provider=ProviderType.OLLAMA,
                default_model="glm-5:cloud",
                available=True,
            ),
        )

    with patch("dharma_swarm.cron_runner.complete_via_preferred_runtime_providers", _fake_complete):
        success, output, error = run_cron_job(
            {
                "id": "portable-job",
                "name": "Portable pulse",
                "handler": "headless_prompt",
                "prompt": "say hi",
                "execution_surface": "hosted_api",
                "available_provider_types": [ProviderType.OLLAMA.value, ProviderType.GROQ.value],
            }
        )

    assert success is True
    assert error is None
    assert "Portable ok" in output
    assert "surface=hosted_api" in output
    assert "provider=ollama" in output


def test_run_cron_job_portable_persists_artifact_when_job_requires_output_file():
    async def _fake_complete(**kwargs):
        return (
            LLMResponse(
                content="JK PULSE [DATE] [GREEN] — Stable.",
                model="glm-5:cloud",
                provider=ProviderType.OLLAMA.value,
            ),
            RuntimeProviderConfig(
                provider=ProviderType.OLLAMA,
                default_model="glm-5:cloud",
                available=True,
            ),
        )

    with patch("dharma_swarm.cron_runner.persist_portable_job_output", return_value="/tmp/jk_pulse.md"):
        with patch("dharma_swarm.cron_runner.complete_via_preferred_runtime_providers", _fake_complete):
            success, output, error = run_cron_job(
                {
                    "id": "jk_pulse",
                    "name": "Jagat Kalyan Pulse",
                    "handler": "headless_prompt",
                    "prompt": "raw prompt",
                    "execution_surface": "hosted_api",
                    "available_provider_types": [ProviderType.OLLAMA.value],
                }
            )

    assert success is True
    assert error is None
    assert "Artifact: wrote /tmp/jk_pulse.md" in output


def test_run_cron_job_portable_known_job_uses_materialized_local_snapshot():
    async def _fake_complete(**kwargs):
        assert kwargs["messages"] == [{"role": "user", "content": "LOCAL SNAPSHOT PROMPT"}]
        return (
            LLMResponse(
                content="Portable ok",
                model="glm-5:cloud",
                provider=ProviderType.OLLAMA.value,
            ),
            RuntimeProviderConfig(
                provider=ProviderType.OLLAMA,
                default_model="glm-5:cloud",
                available=True,
            ),
        )

    with patch(
        "dharma_swarm.cron_runner.build_portable_job_prompt",
        return_value="LOCAL SNAPSHOT PROMPT",
    ):
        with patch("dharma_swarm.cron_runner.complete_via_preferred_runtime_providers", _fake_complete):
            success, output, error = run_cron_job(
                {
                    "id": "pulse",
                    "name": "Portable pulse",
                    "handler": "headless_prompt",
                    "prompt": "raw prompt should not leak through",
                    "execution_surface": "hosted_api",
                    "available_provider_types": [ProviderType.OLLAMA.value],
                }
            )

    assert success is True
    assert error is None
    assert "Portable ok" in output


def test_run_cron_job_uses_hosted_fallback_when_claude_headless_auth_fails():
    async def _fake_complete(**kwargs):
        assert kwargs["provider_order"] == (ProviderType.OLLAMA, ProviderType.GROQ)
        assert kwargs["openrouter_model"] is None
        return (
            LLMResponse(
                content="Recovered on hosted path",
                model="glm-5:cloud",
                provider=ProviderType.OLLAMA.value,
            ),
            RuntimeProviderConfig(
                provider=ProviderType.OLLAMA,
                default_model="glm-5:cloud",
                available=True,
            ),
        )

    with patch(
        "dharma_swarm.pulse.run_claude_headless",
        return_value="ERROR: unattended Claude bare mode requires ANTHROPIC_API_KEY",
    ):
        with patch("dharma_swarm.cron_runner.complete_via_preferred_runtime_providers", _fake_complete):
            success, output, error = run_cron_job(
                {
                    "id": "portable-fallback",
                    "name": "Fallback pulse",
                    "handler": "headless_prompt",
                    "prompt": "say hi",
                    "execution_surface": "claude_bare_with_hosted_fallback",
                    "available_provider_types": [ProviderType.OLLAMA.value, ProviderType.GROQ.value],
                }
            )

    assert success is True
    assert error is None
    assert "Recovered on hosted path" in output
    assert "surface=hosted_api_fallback" in output
    assert "provider=ollama" in output


def test_run_cron_job_portable_headless_reports_honest_failure_when_no_compatible_provider():
    async def _fake_complete(**kwargs):
        raise RuntimeError("No preferred providers available")

    with patch("dharma_swarm.cron_runner.complete_via_preferred_runtime_providers", _fake_complete):
        success, output, error = run_cron_job(
            {
                "id": "portable-job",
                "name": "Portable pulse",
                "handler": "headless_prompt",
                "prompt": "say hi",
                "execution_surface": "hosted_api",
                "available_provider_types": [ProviderType.OLLAMA.value],
            }
        )

    assert success is False
    assert "No preferred providers available" in output
    assert error == "No preferred providers available"


def test_run_cron_job_uses_local_pulse_fallback_when_claude_credit_is_exhausted(
    monkeypatch,
):
    monkeypatch.setattr(
        "dharma_swarm.pulse.run_claude_headless",
        lambda **_: "Error (rc=1): Credit balance is too low",
    )
    monkeypatch.setattr(
        "dharma_swarm.cron_runner.read_agni_state",
        lambda: {"priorities_stale": True, "priorities_age_hours": 52.0},
    )
    monkeypatch.setattr(
        "dharma_swarm.cron_runner.read_trishula_inbox",
        lambda: "7 messages, most recent: note.md",
    )
    monkeypatch.setattr(
        "dharma_swarm.cron_runner.read_memory_context",
        lambda *args, **kwargs: "[L4] recent memory",
    )
    monkeypatch.setattr(
        "dharma_swarm.cron_runner.read_manifest",
        lambda: "Ecosystem: 77/79 paths exist.",
    )
    monkeypatch.setattr(
        "dharma_swarm.cron_runner._assurance_critical_summary",
        lambda: "Assurance: 1 CRITICAL finding across 3 latest scans.",
    )

    success, output, error = run_cron_job(
        {
            "id": "pulse",
            "name": "DGC Pulse",
            "handler": "headless_prompt",
            "prompt": "say hi",
            "model": "flash",
            "fallback_mode": "local_pulse",
        }
    )

    assert success is True
    assert error is None
    assert "Mode: local (fallback)" in output
    assert "Credit balance is too low" in output
    assert "AGNI: priorities stale (52.0h)" in output
    assert "Assurance: 1 CRITICAL finding across 3 latest scans." in output


def test_run_cron_job_keeps_credit_failure_without_local_fallback():
    with patch(
        "dharma_swarm.pulse.run_claude_headless",
        return_value="Error (rc=1): Credit balance is too low",
    ):
        success, output, error = run_cron_job(
            {
                "id": "pulse",
                "name": "DGC Pulse",
                "handler": "headless_prompt",
                "prompt": "say hi",
            }
        )

    assert success is False
    assert "Credit balance is too low" in output
    assert error == "Error (rc=1): Credit balance is too low"


def test_run_cron_job_uses_local_pulse_fallback_when_claude_cli_is_missing(
    monkeypatch,
):
    monkeypatch.setattr(
        "dharma_swarm.pulse.run_claude_headless",
        lambda **_: "ERROR: claude CLI not found in PATH",
    )
    monkeypatch.setattr(
        "dharma_swarm.cron_runner.read_agni_state",
        lambda: {"priorities_stale": False},
    )
    monkeypatch.setattr(
        "dharma_swarm.cron_runner.read_trishula_inbox",
        lambda: "3 messages, most recent: note.md",
    )
    monkeypatch.setattr(
        "dharma_swarm.cron_runner.read_memory_context",
        lambda *args, **kwargs: "[witness] local heartbeat",
    )
    monkeypatch.setattr(
        "dharma_swarm.cron_runner.read_manifest",
        lambda: "Ecosystem: 77/79 paths exist.",
    )
    monkeypatch.setattr(
        "dharma_swarm.cron_runner._assurance_critical_summary",
        lambda: "Assurance: 0 CRITICAL findings across 3 latest scans.",
    )

    success, output, error = run_cron_job(
        {
            "id": "pulse",
            "name": "DGC Pulse",
            "handler": "headless_prompt",
            "prompt": "say hi",
            "model": "flash",
            "fallback_mode": "local_pulse",
        }
    )

    assert success is True
    assert error is None
    assert "Mode: local (fallback)" in output
    assert "claude CLI not found in PATH" in output


def test_run_cron_job_dispatches_review_cycle():
    with patch(
        "dharma_swarm.review_cycle.review_run_fn",
        return_value=(True, "# Review", None),
    ) as mock:
        success, output, error = run_cron_job({"handler": "review_cycle"})

    assert success is True
    assert output == "# Review"
    assert error is None
    mock.assert_called_once()


def test_run_cron_job_dispatches_doctor_assurance():
    with patch(
        "dharma_swarm.doctor.doctor_run_fn",
        return_value=(True, "# Doctor", None),
    ) as mock:
        success, output, error = run_cron_job({"handler": "doctor_assurance"})

    assert success is True
    assert output == "# Doctor"
    assert error is None
    mock.assert_called_once()


def test_run_cron_job_rejects_unknown_handler():
    success, output, error = run_cron_job({"handler": "mystery"})

    assert success is False
    assert "Unsupported cron handler" in output
    assert error == output


def test_execute_cron_job_maps_overnight_waiting_summary_to_waiting_external():
    async def _fake_run_overnight(**kwargs):
        assert kwargs["external_wait_handoff"] is True
        return {
            "status": "waiting",
            "date": "2026-03-27",
            "wake_at": "2026-03-27T12:00:00+00:00",
            "next_action": "Collect benchmark outputs",
            "resume_task_id": "wait_benchmark__resume",
            "wait_id": "wait-123",
        }

    with patch("dharma_swarm.overnight_director.run_overnight", _fake_run_overnight):
        result = execute_cron_job(
            {
                "handler": "overnight_director",
                "name": "Overnight Director",
                "hours": 8,
                "external_wait_handoff": True,
            }
        )

    assert result.status is CronJobRunStatus.WAITING_EXTERNAL
    assert result.next_action == "Collect benchmark outputs"
    assert result.wake_at is not None
    assert result.metadata["overnight_run_date"] == "2026-03-27"
    assert result.metadata["wait_id"] == "wait-123"


def test_execute_cron_job_resumes_overnight_director_from_resume_state():
    seen: dict[str, object] = {}

    async def _fake_run_overnight(**kwargs):
        seen.update(kwargs)
        return {"status": "completed", "date": "2026-03-27"}

    with patch("dharma_swarm.overnight_director.run_overnight", _fake_run_overnight):
        result = execute_cron_job(
            {
                "handler": "overnight_director",
                "external_wait_handoff": True,
                "_resume_state": {
                    "status": "ready_to_resume",
                    "metadata": {
                        "overnight_run_date": "2026-03-27",
                    },
                },
            }
        )

    assert result.status is CronJobRunStatus.COMPLETED
    assert seen["run_date"] == "2026-03-27"
    assert seen["resume_temporal_run"] is True
