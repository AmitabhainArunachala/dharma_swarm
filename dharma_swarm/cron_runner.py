"""Execution dispatch for scheduled cron jobs."""

from __future__ import annotations

import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from dharma_swarm.cron_job_runtime import CronJobExecutionResult, CronJobRunStatus
from dharma_swarm.context import (
    read_agni_state,
    read_manifest,
    read_memory_context,
    read_trishula_inbox,
)
from dharma_swarm.job_capabilities import (
    JobCapabilityProfile,
    JobExecutionSurface,
    resolve_job_capability_profile,
)
from dharma_swarm.cron_portable_context import (
    build_portable_job_prompt,
    persist_portable_job_output,
)
from dharma_swarm.models import ProviderType
from dharma_swarm.runtime_provider import complete_via_preferred_runtime_providers


_LOCAL_FALLBACK_ERROR_MARKERS = (
    "credit balance is too low",
    "not logged in",
    "please run /login",
    "claude cli not found",
    "unattended claude bare mode requires anthropic_api_key",
)


def _as_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _as_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _run_overnight_director(job: dict[str, Any]) -> CronJobExecutionResult:
    """Launch the overnight director as a long-running process."""
    import asyncio
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        from dharma_swarm.overnight_director import run_overnight

        hours = float(job.get("hours", 8.0))
        autonomy = int(job.get("autonomy", 1))
        max_tokens = int(job.get("max_tokens", 500_000))
        external_wait_handoff = bool(job.get("external_wait_handoff", False))
        raw_resume_state = job.get("_resume_state")
        resume_state = raw_resume_state if isinstance(raw_resume_state, dict) else {}
        resume_metadata = resume_state.get("metadata", {}) if isinstance(resume_state.get("metadata", {}), dict) else {}
        run_date = str(resume_metadata.get("overnight_run_date", "")).strip() or None
        result = asyncio.run(run_overnight(
            hours=hours,
            autonomy_level=autonomy,
            max_tokens=max_tokens,
            external_wait_handoff=external_wait_handoff,
            run_date=run_date,
            resume_temporal_run=run_date is not None,
        ))
        summary = json.dumps(result, indent=2, default=str)[:5000]
        header = f"# Cron Job: {job.get('name', 'Overnight Director')}\n\n"
        if result.get("status") == "waiting":
            wake_at = None
            raw_wake_at = result.get("wake_at")
            if raw_wake_at:
                try:
                    wake_at = datetime.fromisoformat(str(raw_wake_at))
                except ValueError:
                    wake_at = None
            return CronJobExecutionResult(
                status=CronJobRunStatus.WAITING_EXTERNAL,
                output=header + summary,
                next_action=str(result.get("next_action", "")),
                wake_at=wake_at,
                metadata={
                    "overnight_run_date": str(result.get("date", run_date or "")),
                    "resume_task_id": str(result.get("resume_task_id", "")),
                    "wait_id": str(result.get("wait_id", "")),
                },
            )
        return CronJobExecutionResult(
            status=CronJobRunStatus.COMPLETED,
            output=header + summary,
        )
    except Exception as exc:
        error = f"Overnight director failed: {exc}"
        return CronJobExecutionResult(
            status=CronJobRunStatus.FAILED,
            output=error,
            error=error[:500],
        )


def _headless_failure_supports_local_fallback(result: str) -> bool:
    lowered = result.lower()
    return any(marker in lowered for marker in _LOCAL_FALLBACK_ERROR_MARKERS)


def _one_line(text: str, *, limit: int = 180) -> str:
    collapsed = " ".join(part.strip() for part in text.splitlines() if part.strip())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 3] + "..."


def _assurance_critical_summary() -> str:
    scans_dir = Path.home() / ".dharma" / "assurance" / "scans"
    if not scans_dir.exists():
        return "Assurance: no scan summaries found."

    critical_total = 0
    scanned = 0
    for path in sorted(scans_dir.glob("*latest.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        scanned += 1
        summary = payload.get("summary")
        if isinstance(summary, dict):
            try:
                critical_total += int(summary.get("critical", 0) or 0)
            except (TypeError, ValueError):
                pass
            continue
        findings = payload.get("findings")
        if isinstance(findings, list):
            critical_total += sum(
                1
                for finding in findings
                if isinstance(finding, dict)
                and str(finding.get("severity", "")).lower() == "critical"
            )

    if scanned == 0:
        return "Assurance: no readable latest scan summaries."

    noun = "finding" if critical_total == 1 else "findings"
    scan_noun = "scan" if scanned == 1 else "scans"
    return f"Assurance: {critical_total} CRITICAL {noun} across {scanned} latest {scan_noun}."


def _local_pulse_fallback(remote_error: str) -> str:
    agni_state = read_agni_state()
    if agni_state.get("priorities_stale"):
        age = agni_state.get("priorities_age_hours", "?")
        agni_summary = f"priorities stale ({age}h)"
    elif agni_state:
        agni_summary = "state files present"
    else:
        agni_summary = "state unavailable"

    return "\n".join(
        [
            "Mode: local (fallback)",
            f"Claude unavailable: {remote_error}",
            f"AGNI: {agni_summary}",
            f"Trishula: {_one_line(read_trishula_inbox())}",
            _assurance_critical_summary(),
            f"Memory: {_one_line(read_memory_context(limit=3))}",
            f"Ecosystem: {_one_line(read_manifest())}",
            "Witness: heartbeat preserved locally while the Claude lane is unavailable.",
        ]
    )


def _build_local_fallback(job: dict[str, Any], remote_error: str) -> str | None:
    mode = str(job.get("fallback_mode", "")).strip().lower()
    if mode == "local_pulse":
        return _local_pulse_fallback(remote_error)
    return None


def _result_from_legacy(
    success: bool,
    output: str,
    error: str | None,
) -> CronJobExecutionResult:
    return CronJobExecutionResult(
        status=CronJobRunStatus.COMPLETED if success else CronJobRunStatus.FAILED,
        output=output,
        error=error or "",
    )


def _portable_model_overrides(
    provider_order: tuple[ProviderType, ...],
    requested_model: str | None,
) -> tuple[str | None, str | None]:
    if not requested_model:
        return None, None
    lowered = requested_model.strip().lower()
    if lowered in {"flash", "haiku", "sonnet", "opus"}:
        return None, None

    openrouter_model = (
        requested_model
        if any(
            provider in provider_order
            for provider in (ProviderType.OPENROUTER, ProviderType.OPENROUTER_FREE)
        )
        else None
    )
    anthropic_model = (
        requested_model if ProviderType.ANTHROPIC in provider_order else None
    )
    return openrouter_model, anthropic_model


def _format_hosted_completion_output(
    job: dict[str, Any],
    *,
    surface: str,
    provider: str,
    model: str,
    content: str,
) -> str:
    header = f"# Cron Job: {job.get('name', job.get('id', 'unnamed'))}\n\n"
    route = f"Route: surface={surface} provider={provider} model={model}"
    return header + route + "\n\n" + content


def _run_hosted_portable_prompt(
    job: dict[str, Any],
    profile: JobCapabilityProfile,
    *,
    surface_label: str,
) -> tuple[bool, str, str | None]:
    prompt = build_portable_job_prompt(job)
    if not prompt:
        error = "Cron job prompt is empty"
        return False, error, error

    requested_model = str(job.get("model", "")).strip() or None
    openrouter_model, anthropic_model = _portable_model_overrides(
        profile.provider_order,
        requested_model,
    )
    timeout_seconds = _as_float(job.get("timeout_sec"), 600.0)

    try:
        response, config = asyncio.run(
            complete_via_preferred_runtime_providers(
                messages=[{"role": "user", "content": prompt}],
                system=str(job.get("system", "")).strip(),
                openrouter_model=openrouter_model,
                anthropic_model=anthropic_model,
                max_tokens=_as_int(job.get("max_tokens"), 4096),
                temperature=_as_float(job.get("temperature"), 0.7),
                provider_order=profile.provider_order,
                working_dir=str(job.get("working_dir", "")).strip() or None,
                timeout_seconds=timeout_seconds,
            )
        )
    except Exception as exc:
        error = str(exc) or "Portable hosted execution failed"
        header = f"# Cron Job: {job.get('name', job.get('id', 'unnamed'))}\n\n"
        return False, header + error, error[:500]

    provider = response.provider or config.provider.value
    model = response.model or config.default_model or requested_model or "unknown"
    try:
        artifact_path = persist_portable_job_output(job, response.content)
    except Exception as exc:
        error = f"Portable artifact persistence failed: {exc}"
        header = f"# Cron Job: {job.get('name', job.get('id', 'unnamed'))}\n\n"
        return False, header + error, error[:500]
    output = _format_hosted_completion_output(
        job,
        surface=surface_label,
        provider=provider,
        model=model,
        content=response.content,
    )
    if artifact_path is not None:
        output = output + f"\n\nArtifact: wrote {artifact_path}"
    return True, output, None


def _run_headless_prompt(job: dict[str, Any]) -> tuple[bool, str, str | None]:
    from dharma_swarm.pulse import run_claude_headless

    profile = resolve_job_capability_profile(job)
    prompt = str(job.get("prompt", "")).strip()
    if not prompt:
        error = "Cron job prompt is empty"
        return False, error, error

    # Legacy headless prompts often assume local file reads or shell actions,
    # so hosted portability stays explicit rather than automatic.
    if profile.prefers_hosted_api:
        return _run_hosted_portable_prompt(
            job,
            profile,
            surface_label=JobExecutionSurface.HOSTED_API.value,
        )

    result = run_claude_headless(
        prompt=prompt,
        timeout=_as_int(job.get("timeout_sec"), 600),
        model=str(job.get("model", "")).strip() or None,
    )
    success = not result.startswith(("ERROR:", "TIMEOUT:", "Error (rc="))
    header = f"# Cron Job: {job.get('name', job.get('id', 'unnamed'))}\n\n"
    if (
        not success
        and profile.allows_hosted_fallback
        and _headless_failure_supports_local_fallback(result)
    ):
        hosted_success, hosted_output, hosted_error = _run_hosted_portable_prompt(
            job,
            profile,
            surface_label="hosted_api_fallback",
        )
        if hosted_success:
            return True, hosted_output, None
        if hosted_error:
            result = f"{result}\nHosted fallback failed: {hosted_error}"
    if not success and _headless_failure_supports_local_fallback(result):
        fallback_output = _build_local_fallback(job, result)
        if fallback_output is not None:
            return True, header + fallback_output, None
    return success, header + result, None if success else result[:500]

def _run_scout_sweep(job: dict[str, Any]) -> CronJobExecutionResult:
    """Run all domain scouts sequentially."""
    import asyncio

    try:
        from dharma_swarm.scout_framework import run_all_scouts
        model = str(job.get("scout_model", "")).strip() or None
        reports = asyncio.run(run_all_scouts(model_override=model))
        from dharma_swarm.scout_report import report_summary
        lines = [report_summary(r) for r in reports]
        output = f"Scout sweep: {len(reports)} domains\n" + "\n".join(lines)
        return CronJobExecutionResult(
            status=CronJobRunStatus.COMPLETED,
            output=output,
        )
    except Exception as e:
        return CronJobExecutionResult(
            status=CronJobRunStatus.FAILED,
            output=str(e),
            error=str(e),
        )


def _run_scout_synthesis(job: dict[str, Any]) -> CronJobExecutionResult:
    """Run synthesis agent on latest scout reports."""
    import asyncio

    try:
        from dharma_swarm.synthesis_agent import run_synthesis
        path = asyncio.run(run_synthesis())
        if path:
            output = f"Synthesis written: {path}"
            return CronJobExecutionResult(
                status=CronJobRunStatus.COMPLETED,
                output=output,
            )
        return CronJobExecutionResult(
            status=CronJobRunStatus.FAILED,
            output="No scout reports found",
            error="No scout reports found",
        )
    except Exception as e:
        return CronJobExecutionResult(
            status=CronJobRunStatus.FAILED,
            output=str(e),
            error=str(e),
        )


def execute_cron_job(job: dict[str, Any]) -> CronJobExecutionResult:
    """Dispatch a cron job to the configured runner with structured status.

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
        return _result_from_legacy(*_run_headless_prompt(job))
    if handler == "overnight_director":
        return _run_overnight_director(job)
    if handler == "doctor_assurance":
        from dharma_swarm.doctor import doctor_run_fn
        return _result_from_legacy(*doctor_run_fn(job))
    if handler == "review_cycle":
        from dharma_swarm.review_cycle import review_run_fn
        return _result_from_legacy(*review_run_fn(job))
    if handler == "foreman":
        from dharma_swarm.foreman import foreman_run_fn
        return _result_from_legacy(*foreman_run_fn(job))
    if handler == "custodians":
        from dharma_swarm.custodians import custodians_run_fn
        return _result_from_legacy(*custodians_run_fn(job))
    if handler == "custodians_forge":
        from dharma_swarm.foreman import custodians_forge_fn
        return _result_from_legacy(*custodians_forge_fn(job))

    if handler == "scout_sweep":
        return _run_scout_sweep(job)
    if handler == "scout_synthesis":
        return _run_scout_synthesis(job)

    error = f"Unsupported cron handler: {handler}"
    return CronJobExecutionResult(
        status=CronJobRunStatus.FAILED,
        output=error,
        error=error,
    )


def run_cron_job(job: dict[str, Any]) -> tuple[bool, str, str | None]:
    """Dispatch a cron job to the configured runner."""

    result = execute_cron_job(job)
    success = result.status in {
        CronJobRunStatus.COMPLETED,
        CronJobRunStatus.WAITING_EXTERNAL,
        CronJobRunStatus.READY_TO_RESUME,
    }
    error = None if success else (result.error or result.output[:500] or "Cron job failed")

    # Report to KaizenOps
    try:
        from dharma_swarm.kaizen_ops_local import KaizenOpsLocal
        ops = KaizenOpsLocal()
        ops.ingest_cron_result(
            job_id=str(job.get("id", "unknown")),
            status=result.status.value,
            job_name=str(job.get("name", "")),
            error=result.error or "",
        )
        ops.close()
    except Exception:
        pass  # KaizenOps is non-blocking

    return success, result.output, error
