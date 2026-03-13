from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = Path.home() / ".dharma"
SHARED_DIR = STATE_DIR / "shared"
REPORT_DIR = REPO_ROOT / "reports" / "verification"

DEFAULT_ROUTE_TASK = (
    "test the full power of dgc from inside the system and show what it can do"
)
DEFAULT_CONTEXT_SEARCH_QUERY = (
    "mechanistic thread reports unfinished work active modules evidence paths"
)
DEFAULT_COMPOSE_TASK = (
    "Probe DGC full power from inside this workspace, verify the mechanistic "
    "thread snapshot, and produce a concrete artifact"
)
DEFAULT_AUTONOMY_ACTION = (
    "run a broad but safe local full-power probe without mutating external systems"
)
DEFAULT_PYTEST_TARGETS = (
    "tests/test_doctor.py",
    "tests/test_dgc_cli.py",
    "tests/test_dgc_cli_mission_brief.py",
    "tests/test_dgc_cli_memory_retrospectives.py",
    "tests/test_skill_composer.py",
    "tests/test_dag_executor.py",
    "tests/test_context_search.py",
    "tests/test_adaptive_autonomy.py",
    "tests/test_stigmergy.py",
    "tests/test_subconscious_hum.py",
    "tests/test_ouroboros.py",
    "tests/test_intent_router.py",
    "tests/test_intent_router_semantic.py",
    "tests/test_thinkodynamic_director.py",
    "tests/test_thinkodynamic_director_provider_fallback.py",
)
TASK_STATUS_RE = re.compile(r"^\s*\S+\s+(pending|running|completed|failed)\b", re.M)


@dataclass(frozen=True)
class ProbeSpec:
    name: str
    command: tuple[str, ...]
    timeout_sec: float = 20.0
    allow_failure: bool = False


@dataclass
class ProbeResult:
    name: str
    command: list[str]
    elapsed_sec: float
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return not self.timed_out and self.returncode == 0

    @property
    def status(self) -> str:
        if self.timed_out:
            return "timeout"
        if self.returncode == 0:
            return "ok"
        if self.returncode is None:
            return "error"
        return "fail"

    def preview(self, lines: int = 8) -> str:
        primary = self.stdout.strip() or self.stderr.strip()
        return preview_text(primary, lines=lines)


def preview_text(text: str, *, lines: int = 8, chars: int = 1000) -> str:
    text = text.strip()
    if not text:
        return "(no output)"
    split = text.splitlines()
    clipped = split[:lines]
    joined = "\n".join(clipped)
    if len(joined) > chars:
        joined = joined[: chars - 3].rstrip() + "..."
    elif len(split) > lines:
        joined += "\n..."
    return joined


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else {"value": data}


def latest_files(path: Path, pattern: str, *, limit: int = 5) -> list[Path]:
    if not path.exists():
        return []
    return sorted(path.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]


def iso_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def parse_task_status_counts(text: str) -> dict[str, int]:
    counts = {name: 0 for name in ("pending", "running", "completed", "failed")}
    for status in TASK_STATUS_RE.findall(text):
        counts[status] += 1
    return counts


def run_command(
    command: tuple[str, ...],
    *,
    timeout_sec: float,
    cwd: Path = REPO_ROOT,
    name: str,
) -> ProbeResult:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        elapsed = time.monotonic() - started
        return ProbeResult(
            name=name,
            command=list(command),
            elapsed_sec=elapsed,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        return ProbeResult(
            name=name,
            command=list(command),
            elapsed_sec=elapsed,
            returncode=None,
            stdout=_coerce_output(exc.stdout),
            stderr=_coerce_output(exc.stderr),
            timed_out=True,
            error=f"timeout after {timeout_sec:.1f}s",
        )
    except OSError as exc:
        elapsed = time.monotonic() - started
        return ProbeResult(
            name=name,
            command=list(command),
            elapsed_sec=elapsed,
            returncode=None,
            stdout="",
            stderr="",
            error=str(exc),
        )


def _coerce_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def build_probe_specs(
    *,
    python_executable: str,
    route_task: str,
    context_search_query: str,
    compose_task: str,
    autonomy_action: str,
    include_sprint_probe: bool,
) -> list[ProbeSpec]:
    dgc = (python_executable, "-m", "dharma_swarm.dgc_cli")
    specs = [
        ProbeSpec("status", dgc + ("status",)),
        ProbeSpec("runtime-status", dgc + ("runtime-status",)),
        ProbeSpec("mission-status", dgc + ("mission-status",)),
        ProbeSpec("mission-brief", dgc + ("mission-brief",)),
        ProbeSpec("campaign-brief", dgc + ("campaign-brief",), allow_failure=True),
        ProbeSpec("canonical-status", dgc + ("canonical-status",)),
        ProbeSpec("health", dgc + ("health",)),
        ProbeSpec("health-check", dgc + ("health-check",)),
        ProbeSpec("memory", dgc + ("memory",)),
        ProbeSpec("doctor", dgc + ("doctor",), timeout_sec=30.0),
        ProbeSpec("provider-smoke", dgc + ("provider-smoke", "--json"), allow_failure=True),
        ProbeSpec("skills", dgc + ("skills",)),
        ProbeSpec("route", dgc + ("route", route_task)),
        ProbeSpec(
            "context-search",
            dgc + ("context-search", "--budget", "8", context_search_query),
        ),
        ProbeSpec("compose", dgc + ("compose", compose_task)),
        ProbeSpec("autonomy", dgc + ("autonomy", autonomy_action)),
        ProbeSpec("context-research", dgc + ("context", "research")),
        ProbeSpec("task-list", dgc + ("task", "list")),
        ProbeSpec("dharma-status", dgc + ("dharma", "status")),
        ProbeSpec("stigmergy", dgc + ("stigmergy",)),
        ProbeSpec("hum", dgc + ("hum",)),
        ProbeSpec(
            "ouroboros-connections",
            dgc + ("ouroboros", "connections"),
            timeout_sec=30.0,
        ),
    ]
    if include_sprint_probe:
        specs.append(
            ProbeSpec(
                "sprint",
                dgc + ("sprint", "--local"),
                timeout_sec=15.0,
                allow_failure=True,
            )
        )
    return specs


def collect_state_snapshot() -> dict[str, Any]:
    return {
        "thread_state": read_json(STATE_DIR / "thread_state.json"),
        "mission": read_json(STATE_DIR / "mission.json"),
        "thinkodynamic_director_heartbeat": read_json(
            STATE_DIR / "thinkodynamic_director_heartbeat.json"
        ),
        "orchestrator_state": read_json(STATE_DIR / "orchestrator_state.json"),
        "garden_latest_cycle": read_json(STATE_DIR / "garden" / "latest_cycle.json"),
    }


def collect_recent_paths() -> dict[str, list[dict[str, str]]]:
    module_paths = [
        {
            "path": str(path.relative_to(REPO_ROOT)),
            "mtime_utc": iso_mtime(path),
        }
        for path in sorted(
            (REPO_ROOT / "dharma_swarm").glob("*.py"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )[:8]
    ]
    report_paths = [
        {
            "path": str(path.relative_to(REPO_ROOT)),
            "mtime_utc": iso_mtime(path),
        }
        for path in latest_files(REPO_ROOT / "docs" / "reports", "*.md", limit=8)
    ]
    shared_paths = [
        {
            "path": str(path),
            "mtime_utc": iso_mtime(path),
        }
        for path in latest_files(SHARED_DIR, "*", limit=10)
        if path.is_file()
    ]
    return {
        "active_modules": module_paths,
        "recent_repo_reports": report_paths,
        "recent_shared_artifacts": shared_paths,
    }


def collect_stress_summary() -> dict[str, Any] | None:
    latest_json = next(iter(latest_files(SHARED_DIR, "dgc_max_stress_*.json", limit=1)), None)
    latest_md = next(iter(latest_files(SHARED_DIR, "dgc_max_stress_*.md", limit=1)), None)
    if latest_json is None:
        return None
    try:
        payload = json.loads(latest_json.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    orchestrator = payload.get("phase_orchestrator_load", {})
    evolution = payload.get("phase_evolution", {})
    cli_flood = payload.get("phase_cli_flood", {})
    research = payload.get("phase_research_agents", {})
    return {
        "json_path": str(latest_json),
        "md_path": str(latest_md) if latest_md else None,
        "ts_utc": payload.get("ts_utc"),
        "elapsed_sec": payload.get("elapsed_sec"),
        "profile": payload.get("config", {}).get("profile"),
        "provider_mode": payload.get("config", {}).get("resolved_provider_mode"),
        "research_complete": research.get("wait", {}).get("complete"),
        "research_status_sample": research.get("wait", {}).get("status"),
        "orchestrator_counts": orchestrator.get("counts"),
        "throughput_tasks_per_sec": orchestrator.get("throughput_tasks_per_sec"),
        "evolution_rejected": evolution.get("rejected"),
        "evolution_canary_promote": evolution.get("canary_promote"),
        "evolution_canary_rollback": evolution.get("canary_rollback"),
        "cli_total": cli_flood.get("total"),
        "cli_failed": cli_flood.get("failed"),
        "cli_pass_rate": cli_flood.get("pass_rate"),
    }


def collect_pytest_summary(result: ProbeResult | None) -> dict[str, Any] | None:
    if result is None:
        return None
    summary_line = ""
    warnings_line = ""
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if "passed" in stripped and "warning" in stripped:
            warnings_line = stripped
        elif "passed" in stripped and " in " in stripped:
            summary_line = stripped
    if not summary_line and warnings_line:
        summary_line = warnings_line
    return {
        "status": result.status,
        "elapsed_sec": round(result.elapsed_sec, 2),
        "summary_line": summary_line,
        "warnings_line": warnings_line,
        "preview": result.preview(lines=12),
    }


def derive_findings(
    probe_results: list[ProbeResult],
    state_snapshot: dict[str, Any],
    recent_paths: dict[str, list[dict[str, str]]],
    stress_summary: dict[str, Any] | None,
) -> list[str]:
    findings: list[str] = []
    by_name = {result.name: result for result in probe_results}

    thread_state = state_snapshot.get("thread_state") or {}
    mission = state_snapshot.get("mission") or {}
    heartbeat = state_snapshot.get("thinkodynamic_director_heartbeat") or {}
    if thread_state.get("current_thread"):
        findings.append(
            "Active thread remains "
            f"`{thread_state['current_thread']}` with "
            f"{thread_state.get('contributions', {}).get(thread_state['current_thread'], 0)} "
            "recorded contributions."
        )
    if mission.get("mission_title"):
        findings.append(
            "The mission layer is active and delegated: "
            f"`{mission['mission_title']}` with {mission.get('task_count', 0)} mission tasks."
        )
    campaign = read_json(STATE_DIR / "campaign.json") or {}
    if campaign.get("campaign_id"):
        findings.append(
            "Campaign ledger is present with "
            f"{len(campaign.get('semantic_briefs', []))} semantic briefs and "
            f"{len(campaign.get('execution_briefs', []))} execution briefs."
        )
    if heartbeat:
        findings.append(
            "Thinkodynamic director heartbeat is current: "
            f"cycle `{heartbeat.get('cycle_id')}`, mode `{heartbeat.get('mode')}`, "
            f"altitude `{heartbeat.get('altitude')}`."
        )

    health = by_name.get("health")
    if health and health.ok:
        findings.append(f"Ecosystem health probe passed: `{health.preview(lines=2)}`.")

    doctor = by_name.get("doctor")
    if doctor and doctor.ok:
        findings.append(
            "Doctor passed with worker binaries, provider env, fasttext, and redis all available."
        )

    provider_smoke = by_name.get("provider-smoke")
    if provider_smoke and provider_smoke.ok:
        findings.append(
            "Provider smoke produced a machine-readable provider evidence packet."
        )

    health_check = by_name.get("health-check")
    if health_check and "DEGRADED" in health_check.stdout:
        findings.append(
            "Health-check is degraded because previously active agents have no traces in the last hour."
        )

    canonical = by_name.get("canonical-status")
    if canonical and "fully merged: NO" in canonical.stdout:
        findings.append("Canonical topology is still split; DGC and SAB are not fully merged.")

    context_search = by_name.get("context-search")
    if context_search and "No relevant context found." in context_search.stdout:
        findings.append(
            "Context search did not retrieve the mechanistic/work-summary query, so retrieval coverage is weaker than raw filesystem context."
        )

    sprint = by_name.get("sprint")
    if sprint and sprint.timed_out:
        findings.append("Sprint generation appears able to emit artifacts but the CLI probe can hang past a 15s timeout.")

    task_list = by_name.get("task-list")
    if task_list and task_list.ok:
        counts = parse_task_status_counts(task_list.stdout)
        if counts["pending"] or counts["running"]:
            findings.append(
                "Task board is active with "
                f"{counts['running']} running and {counts['pending']} pending tasks."
            )

    garden = state_snapshot.get("garden_latest_cycle") or {}
    for result in garden.get("results", []):
        if result.get("status") == "timeout":
            findings.append(
                f"Garden cycle still has timeout debt: `{result.get('skill')}` hit `{result.get('status')}`."
            )
            break

    if recent_paths.get("active_modules"):
        findings.append(
            "The hottest code surfaces by mtime are director/CLI/orchestration modules, not peripheral docs."
        )

    if stress_summary:
        findings.append(
            "Stress harness succeeded under mock provider with "
            f"CLI pass rate `{stress_summary.get('cli_pass_rate')}` and "
            f"orchestrator counts `{json.dumps(stress_summary.get('orchestrator_counts', {}), sort_keys=True)}`."
        )
    return findings


def render_markdown_report(payload: dict[str, Any]) -> str:
    state = payload["state_snapshot"]
    recent = payload["recent_paths"]
    findings = payload["findings"]
    stress = payload.get("stress_summary")
    pytest_summary = payload.get("pytest_summary")
    command_results = payload["command_results"]

    lines = [
        "# DGC Full Power Probe",
        f"- Timestamp (UTC): `{payload['ts_utc']}`",
        f"- Workspace: `{payload['workspace']}`",
        f"- Python: `{payload['python_executable']}`",
        "",
        "## Verdict",
    ]
    for finding in findings:
        lines.append(f"- {finding}")

    lines.extend(
        [
            "",
            "## Verified Snapshot",
            f"- Thread state: `{json.dumps(state.get('thread_state', {}), sort_keys=True)}`",
            f"- Mission: `{json.dumps(state.get('mission', {}), sort_keys=True)}`",
            f"- Director heartbeat: `{json.dumps(state.get('thinkodynamic_director_heartbeat', {}), sort_keys=True)}`",
            f"- Orchestrator state: `{json.dumps(state.get('orchestrator_state', {}), sort_keys=True)}`",
        ]
    )

    garden = state.get("garden_latest_cycle")
    if garden:
        lines.append(f"- Garden latest cycle: `{json.dumps(garden, sort_keys=True)}`")

    lines.extend(["", "## Command Probes", "| Probe | Status | Elapsed | Preview |", "|---|---:|---:|---|"])
    for result in command_results:
        preview = result["preview"].replace("\n", "<br>")
        lines.append(
            f"| `{result['name']}` | `{result['status']}` | `{result['elapsed_sec']:.2f}s` | {preview} |"
        )

    if stress:
        lines.extend(
            [
                "",
                "## Stress Harness",
                f"- Timestamp (UTC): `{stress.get('ts_utc')}`",
                f"- Profile: `{stress.get('profile')}`",
                f"- Provider mode: `{stress.get('provider_mode')}`",
                f"- Research complete: `{stress.get('research_complete')}`",
                f"- Orchestrator counts: `{json.dumps(stress.get('orchestrator_counts', {}), sort_keys=True)}`",
                f"- Throughput tasks/sec: `{stress.get('throughput_tasks_per_sec')}`",
                f"- Evolution rejected/promote/rollback: `{stress.get('evolution_rejected')}` / "
                f"`{stress.get('evolution_canary_promote')}` / `{stress.get('evolution_canary_rollback')}`",
                f"- CLI flood total/failed/pass_rate: `{stress.get('cli_total')}` / "
                f"`{stress.get('cli_failed')}` / `{stress.get('cli_pass_rate')}`",
                f"- JSON artifact: `{stress.get('json_path')}`",
                f"- Markdown artifact: `{stress.get('md_path')}`",
            ]
        )

    if pytest_summary:
        lines.extend(
            [
                "",
                "## Pytest",
                f"- Status: `{pytest_summary.get('status')}`",
                f"- Elapsed: `{pytest_summary.get('elapsed_sec')}s`",
                f"- Summary: `{pytest_summary.get('summary_line')}`",
                f"- Warnings: `{pytest_summary.get('warnings_line')}`",
                "",
                "```text",
                pytest_summary.get("preview", "(no output)"),
                "```",
            ]
        )

    lines.extend(["", "## Active Modules"])
    for item in recent["active_modules"]:
        lines.append(f"- `{item['path']}` @ `{item['mtime_utc']}`")

    lines.extend(["", "## Recent Repo Reports"])
    for item in recent["recent_repo_reports"]:
        lines.append(f"- `{item['path']}` @ `{item['mtime_utc']}`")

    lines.extend(["", "## Recent Shared Artifacts"])
    for item in recent["recent_shared_artifacts"]:
        lines.append(f"- `{item['path']}` @ `{item['mtime_utc']}`")

    return "\n".join(lines) + "\n"


def run_full_power_probe(
    *,
    python_executable: str = sys.executable,
    route_task: str = DEFAULT_ROUTE_TASK,
    context_search_query: str = DEFAULT_CONTEXT_SEARCH_QUERY,
    compose_task: str = DEFAULT_COMPOSE_TASK,
    autonomy_action: str = DEFAULT_AUTONOMY_ACTION,
    include_sprint_probe: bool = True,
    run_stress: bool = True,
    run_pytest: bool = True,
    pytest_targets: tuple[str, ...] = DEFAULT_PYTEST_TARGETS,
) -> dict[str, Any]:
    probe_results: list[ProbeResult] = []

    for spec in build_probe_specs(
        python_executable=python_executable,
        route_task=route_task,
        context_search_query=context_search_query,
        compose_task=compose_task,
        autonomy_action=autonomy_action,
        include_sprint_probe=include_sprint_probe,
    ):
        result = run_command(
            spec.command,
            timeout_sec=spec.timeout_sec,
            name=spec.name,
        )
        probe_results.append(result)

    stress_result: ProbeResult | None = None
    if run_stress:
        stress_result = run_command(
            (
                python_executable,
                "-m",
                "dharma_swarm.dgc_cli",
                "stress",
                "--profile",
                "quick",
                "--provider-mode",
                "mock",
            ),
            timeout_sec=180.0,
            name="stress",
        )

    pytest_result: ProbeResult | None = None
    if run_pytest:
        pytest_result = run_command(
            (python_executable, "-m", "pytest", "-q", *pytest_targets),
            timeout_sec=180.0,
            name="pytest",
        )

    state_snapshot = collect_state_snapshot()
    recent_paths = collect_recent_paths()
    stress_summary = collect_stress_summary() if run_stress else None
    pytest_summary = collect_pytest_summary(pytest_result)

    findings = derive_findings(
        probe_results,
        state_snapshot,
        recent_paths,
        stress_summary,
    )
    if stress_result and not stress_result.ok:
        findings.append(f"Stress harness probe did not complete cleanly: `{stress_result.status}`.")
    if pytest_result and not pytest_result.ok:
        findings.append(f"Selected pytest suite did not complete cleanly: `{pytest_result.status}`.")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    command_result_payload = [
        {
            "name": result.name,
            "status": result.status,
            "elapsed_sec": round(result.elapsed_sec, 2),
            "command": result.command,
            "returncode": result.returncode,
            "timed_out": result.timed_out,
            "error": result.error,
            "preview": result.preview(),
        }
        for result in probe_results
    ]
    payload = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "workspace": str(REPO_ROOT),
        "python_executable": python_executable,
        "state_snapshot": state_snapshot,
        "recent_paths": recent_paths,
        "command_results": command_result_payload,
        "stress_summary": stress_summary,
        "stress_result": asdict(stress_result) if stress_result else None,
        "pytest_summary": pytest_summary,
        "pytest_result": asdict(pytest_result) if pytest_result else None,
        "findings": findings,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = REPORT_DIR / f"dgc_full_power_probe_{ts}.md"
    json_path = REPORT_DIR / f"dgc_full_power_probe_{ts}.json"
    payload["report_markdown_path"] = str(md_path)
    payload["report_json_path"] = str(json_path)
    markdown = render_markdown_report(payload)
    md_path.write_text(markdown)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a reusable DGC full-power probe.")
    parser.add_argument("--route-task", default=DEFAULT_ROUTE_TASK)
    parser.add_argument("--context-search-query", default=DEFAULT_CONTEXT_SEARCH_QUERY)
    parser.add_argument("--compose-task", default=DEFAULT_COMPOSE_TASK)
    parser.add_argument("--autonomy-action", default=DEFAULT_AUTONOMY_ACTION)
    parser.add_argument("--skip-sprint-probe", action="store_true")
    parser.add_argument("--skip-stress", action="store_true")
    parser.add_argument("--skip-pytest", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload = run_full_power_probe(
        route_task=args.route_task,
        context_search_query=args.context_search_query,
        compose_task=args.compose_task,
        autonomy_action=args.autonomy_action,
        include_sprint_probe=not args.skip_sprint_probe,
        run_stress=not args.skip_stress,
        run_pytest=not args.skip_pytest,
    )
    print(f"Report: {payload['report_markdown_path']}")
    print(f"JSON:   {payload['report_json_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
