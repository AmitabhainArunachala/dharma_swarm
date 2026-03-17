from __future__ import annotations

from unittest.mock import patch

from dharma_swarm.cron_runner import run_cron_job


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
