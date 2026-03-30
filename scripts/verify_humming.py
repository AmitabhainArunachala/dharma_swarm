#!/usr/bin/env python3
"""Canonical humming verification driver for the operator/runtime stack."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

REPO_BOUNDARY_RUNTIME_STATE_PREFIXES = (
    ".dharma",
    ".swarm",
    ".hive-mind",
)
REPO_BOUNDARY_RUNTIME_ARTIFACTS = frozenset(
    {
        "daemon.pid",
        "operator.pid",
        "pulse.log",
        "runtime.db",
        "marks.jsonl",
        "dgc_health.json",
    }
)
REPO_BOUNDARY_SOURCE_DIRS = (
    "api",
    "dharma_swarm",
    "scripts",
    "tools",
)
REPO_BOUNDARY_OVERSIZED_STATE_BYTES = 512 * 1024


@dataclass(frozen=True)
class Phase:
    name: str
    command: tuple[str, ...]
    timeout_seconds: float | None = None


@dataclass(frozen=True)
class PhaseResult:
    name: str
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def run_command(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout_seconds: float | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _assurance_gate_code() -> str:
    return textwrap.dedent(
        """
        import json
        import sys
        from pathlib import Path

        from dharma_swarm.assurance.runner import run_assurance

        report = run_assurance(repo_root=Path(".").resolve())
        print(json.dumps({"status": report["status"], "summary": report["summary"]}))
        sys.exit(0 if report["status"] == "PASS" else 1)
        """
    ).strip()


def _runtime_supervision_smoke_code() -> str:
    return textwrap.dedent(
        """
        import json
        import sys
        import tempfile
        from pathlib import Path

        from dharma_swarm.runtime_artifacts import (
            dgc_health_snapshot_summary,
            write_dgc_health_snapshot,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / ".dharma"
            (state_dir / "daemon.pid").parent.mkdir(parents=True, exist_ok=True)
            (state_dir / "daemon.pid").write_text("4242\\n", encoding="utf-8")
            write_dgc_health_snapshot(
                state_dir,
                daemon_pid=4242,
                agent_count=1,
                task_count=2,
                anomaly_count=0,
                source="verify_humming",
            )
            summary = dgc_health_snapshot_summary(state_dir)
            payload = {
                "status": summary["status"],
                "daemon_pid": summary["daemon_pid"],
                "live_pid": summary["live_pid"],
                "daemon_pid_mismatch": summary["daemon_pid_mismatch"],
            }
            print(json.dumps(payload))
            sys.exit(
                0
                if summary["status"] == "fresh" and not summary["daemon_pid_mismatch"]
                else 1
            )
        """
    ).strip()


def _build_phases(repo_root: Path) -> list[Phase]:
    python = sys.executable
    return [
        Phase(
            name="python compile",
            command=(
                python,
                "-m",
                "compileall",
                "dharma_swarm",
                "api",
                "tests",
            ),
        ),
        Phase(
            name="targeted operator/API tests",
            command=(
                python,
                "-m",
                "pytest",
                "-q",
                "tests/test_api_main_bootstrap.py",
                "tests/test_agents_router.py",
                "tests/test_runtime_artifacts.py",
                "--tb=short",
            ),
        ),
        Phase(
            name="dashboard lint",
            command=("npm", "--prefix", "dashboard", "run", "lint", "--", "--quiet"),
            timeout_seconds=120.0,
        ),
        Phase(
            name="dashboard build",
            command=("npm", "--prefix", "dashboard", "run", "build"),
            timeout_seconds=300.0,
        ),
        Phase(
            name="assurance gate",
            command=(
                python,
                "-c",
                _assurance_gate_code(),
            ),
        ),
        Phase(
            name="dgc status",
            command=(python, "-m", "dharma_swarm.dgc", "status"),
        ),
        Phase(
            name="runtime supervision smoke",
            command=(
                python,
                "-c",
                _runtime_supervision_smoke_code(),
            ),
        ),
    ]


def _tracked_repo_paths(repo_root: Path) -> tuple[Path, ...]:
    completed = run_command(("git", "ls-files"), cwd=repo_root)
    if completed.returncode != 0:
        return ()
    return tuple(
        Path(line.strip())
        for line in completed.stdout.splitlines()
        if line.strip()
    )


def _format_bytes(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MiB"
    return f"{size_bytes / 1024:.0f} KiB"


def collect_repo_boundary_drift(repo_root: Path) -> list[str]:
    findings: list[str] = []
    tracked_paths = _tracked_repo_paths(repo_root)

    runtime_state_roots = sorted(
        {
            path.parts[0]
            for path in tracked_paths
            if path.parts
            and any(path.parts[0].startswith(prefix) for prefix in REPO_BOUNDARY_RUNTIME_STATE_PREFIXES)
        }
        | {
            path.name
            for path in repo_root.iterdir()
            if any(path.name.startswith(prefix) for prefix in REPO_BOUNDARY_RUNTIME_STATE_PREFIXES)
        }
    )
    if runtime_state_roots:
        findings.append(
            "machine-local runtime state: " + ", ".join(runtime_state_roots[:4])
        )

    specs_state_root = repo_root / "specs" / "states"
    if specs_state_root.exists():
        state_files = [path for path in specs_state_root.rglob("*") if path.is_file()]
        total_bytes = sum(path.stat().st_size for path in state_files)
        if total_bytes >= REPO_BOUNDARY_OVERSIZED_STATE_BYTES:
            largest = max(state_files, key=lambda path: path.stat().st_size, default=None)
            detail = f"{len(state_files)} files, {_format_bytes(total_bytes)} total"
            if largest is not None:
                detail = f"{detail}, largest {largest.relative_to(repo_root)}"
            findings.append(f"oversized generated state under specs/states/: {detail}")

    runtime_artifacts: set[Path] = {
        path
        for path in tracked_paths
        if path.name in REPO_BOUNDARY_RUNTIME_ARTIFACTS
        and (len(path.parts) == 1 or path.parts[0] in REPO_BOUNDARY_SOURCE_DIRS)
    }
    for dirname in REPO_BOUNDARY_SOURCE_DIRS:
        source_root = repo_root / dirname
        if not source_root.exists():
            continue
        runtime_artifacts.update(
            path.relative_to(repo_root)
            for path in source_root.rglob("*")
            if path.is_file() and path.name in REPO_BOUNDARY_RUNTIME_ARTIFACTS
        )
    for name in REPO_BOUNDARY_RUNTIME_ARTIFACTS:
        top_level = repo_root / name
        if top_level.exists():
            runtime_artifacts.add(Path(name))
    if runtime_artifacts:
        findings.append(
            "runtime artifacts in source tree: "
            + ", ".join(str(path) for path in sorted(runtime_artifacts)[:4])
        )

    return findings


def _run_phase(phase: Phase, *, repo_root: Path) -> PhaseResult:
    try:
        completed = run_command(
            phase.command,
            cwd=repo_root,
            timeout_seconds=phase.timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return PhaseResult(
            name=phase.name,
            command=phase.command,
            returncode=124,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            timed_out=True,
        )
    return PhaseResult(
        name=phase.name,
        command=phase.command,
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def _render_summary(results: list[PhaseResult], *, repo_boundary_findings: list[str]) -> str:
    lines = [
        "HUMMING VERIFICATION",
        "====================",
        f"{'Phase':32} {'Result':8} Command",
    ]

    for result in results:
        status = "PASS" if result.passed else "TIMEOUT" if result.timed_out else "FAIL"
        lines.append(
            f"{result.name:32} {status:8} {shlex.join(result.command)}"
        )

    failed = [result for result in results if not result.passed]
    lines.append("")
    lines.append(
        f"Overall: {'PASS' if not failed else 'FAIL'} "
        f"({len(results) - len(failed)}/{len(results)} required phases passed)"
    )
    if repo_boundary_findings:
        lines.append(f"Repo boundary: WARN ({len(repo_boundary_findings)} findings)")
        for finding in repo_boundary_findings:
            lines.append(f"- {finding}")
    else:
        lines.append("Repo boundary: clean")
    if failed:
        lines.append("Failed phases:")
        for result in failed:
            reason = "timed out" if result.timed_out else f"exit {result.returncode}"
            lines.append(f"- {result.name}: {reason}")
        lines.append("")
        lines.append("Diagnostics:")
        for result in failed:
            lines.extend(_render_failure_output(result))
    return "\n".join(lines)


def _render_failure_output(result: PhaseResult) -> list[str]:
    lines = [f"--- {result.name} ({shlex.join(result.command)}) ---"]
    if result.stdout.strip():
        lines.append("stdout:")
        lines.append(textwrap.indent(result.stdout.rstrip(), prefix="  "))
    else:
        lines.append("stdout: <empty>")
    if result.stderr.strip():
        lines.append("stderr:")
        lines.append(textwrap.indent(result.stderr.rstrip(), prefix="  "))
    else:
        lines.append("stderr: <empty>")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the canonical humming verification lane")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=_repo_root(),
        help="Repository root to use for relative commands",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    results = [_run_phase(phase, repo_root=repo_root) for phase in _build_phases(repo_root)]
    repo_boundary_findings = collect_repo_boundary_drift(repo_root)
    print(_render_summary(results, repo_boundary_findings=repo_boundary_findings))
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
