"""Execution dispatch for scheduled cron jobs."""

from __future__ import annotations

from typing import Any


def _as_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _run_headless_prompt(job: dict[str, Any]) -> tuple[bool, str, str | None]:
    from dharma_swarm.pulse import run_claude_headless

    prompt = str(job.get("prompt", "")).strip()
    if not prompt:
        error = "Cron job prompt is empty"
        return False, error, error

    result = run_claude_headless(
        prompt=prompt,
        timeout=_as_int(job.get("timeout_sec"), 600),
        model=str(job.get("model", "")).strip() or None,
    )
    success = not result.startswith(("ERROR:", "TIMEOUT:", "Error (rc="))
    header = f"# Cron Job: {job.get('name', job.get('id', 'unnamed'))}\n\n"
    return success, header + result, None if success else result[:500]


def run_cron_job(job: dict[str, Any]) -> tuple[bool, str, str | None]:
    """Dispatch a cron job to the configured runner.

    Supported handlers:
        headless_prompt  — default, runs prompt via Claude headless
        doctor_assurance — recurring DGC Doctor sweep with persisted reports
        review_cycle     — 6-hour review cycle
        foreman          — foreman quality forge cycle
        custodians       — custodian maintenance fleet (no quality re-scan)
        custodians_forge — custodian fleet + foreman quality re-scan
    """
    handler = str(job.get("handler", "headless_prompt")).strip() or "headless_prompt"

    if handler == "headless_prompt":
        return _run_headless_prompt(job)
    if handler == "doctor_assurance":
        from dharma_swarm.doctor import doctor_run_fn
        return doctor_run_fn(job)
    if handler == "review_cycle":
        from dharma_swarm.review_cycle import review_run_fn
        return review_run_fn(job)
    if handler == "foreman":
        from dharma_swarm.foreman import foreman_run_fn
        return foreman_run_fn(job)
    if handler == "custodians":
        from dharma_swarm.custodians import custodians_run_fn
        return custodians_run_fn(job)
    if handler == "custodians_forge":
        from dharma_swarm.foreman import custodians_forge_fn
        return custodians_forge_fn(job)

    error = f"Unsupported cron handler: {handler}"
    return False, error, error
