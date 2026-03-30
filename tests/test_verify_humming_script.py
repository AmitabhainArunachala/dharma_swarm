from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
from types import ModuleType, SimpleNamespace
import sys

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_humming.py"


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_humming", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_verify_humming_runs_phases_in_order(monkeypatch, capsys) -> None:
    mod = load_module()
    calls: list[tuple[tuple[str, ...], Path | None]] = []
    python = mod.sys.executable

    def fake_run_command(command, *, cwd=None, timeout_seconds=None):  # type: ignore[no-untyped-def]
        calls.append((tuple(command), cwd, timeout_seconds))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(mod, "run_command", fake_run_command)
    monkeypatch.setattr(mod, "collect_repo_boundary_drift", lambda repo_root: [])

    exit_code = mod.main([])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert [command[0] for command, _, _ in calls] == [
        python,
        python,
        "npm",
        "npm",
        python,
        python,
        python,
    ]
    assert calls[0][0][:4] == (python, "-m", "compileall", "dharma_swarm")
    assert calls[1][0][:3] == (python, "-m", "pytest")
    assert calls[2][0] == ("npm", "--prefix", "dashboard", "run", "lint", "--", "--quiet")
    assert calls[2][2] == 120.0
    assert calls[3][0] == ("npm", "--prefix", "dashboard", "run", "build")
    assert calls[3][2] == 300.0
    assert calls[4][0][:2] == (python, "-c")
    assert "run_assurance(" in calls[4][0][2]
    assert "json.dumps" in calls[4][0][2]
    assert "sys.exit(" in calls[4][0][2]
    assert calls[5][0][:4] == (python, "-m", "dharma_swarm.dgc", "status")
    assert calls[6][0][:2] == (python, "-c")
    assert "write_dgc_health_snapshot" in calls[6][0][2]
    assert "dgc_health_snapshot_summary" in calls[6][0][2]
    assert "HUMMING VERIFICATION" in captured.out
    assert "PASS" in captured.out


def test_verify_humming_exits_nonzero_when_a_required_phase_fails(monkeypatch, capsys) -> None:
    mod = load_module()
    python = mod.sys.executable

    def fake_run_command(command, *, cwd=None, timeout_seconds=None):  # type: ignore[no-untyped-def]
        if command[:2] == (python, "-c") and "run_assurance(" in command[2]:
            return SimpleNamespace(returncode=1, stdout="gate failed", stderr="trace")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(mod, "run_command", fake_run_command)

    exit_code = mod.main([])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "FAIL" in captured.out
    assert "assurance gate" in captured.out.lower()
    assert "gate failed" in captured.out
    assert "trace" in captured.out


def test_verify_humming_marks_timeouts_in_summary(monkeypatch, capsys) -> None:
    mod = load_module()

    def fake_run_command(command, *, cwd=None, timeout_seconds=None):  # type: ignore[no-untyped-def]
        if command[0] == "npm" and "build" in command:
            raise subprocess.TimeoutExpired(command, timeout=timeout_seconds, output="partial", stderr="slow")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(mod, "run_command", fake_run_command)

    exit_code = mod.main([])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "TIMEOUT" in captured.out
    assert "dashboard build: timed out" in captured.out
    assert "partial" in captured.out
    assert "slow" in captured.out


def test_verify_humming_python_phases_execute_without_tracebacks() -> None:
    mod = load_module()
    repo_root = SCRIPT_PATH.parents[1]
    python = mod.sys.executable
    phases = {
        phase.name: phase.command
        for phase in mod._build_phases(repo_root)
        if phase.command[:2] == (python, "-c")
    }

    assurance = subprocess.run(
        list(phases["assurance gate"]),
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert assurance.stderr == ""
    assurance_payload = json.loads(assurance.stdout.strip())
    assert assurance_payload["status"] in {"PASS", "WARN", "FAIL"}

    runtime_smoke = subprocess.run(
        list(phases["runtime supervision smoke"]),
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert runtime_smoke.returncode == 0
    assert runtime_smoke.stderr == ""
    runtime_payload = json.loads(runtime_smoke.stdout.strip())
    assert runtime_payload["status"] == "fresh"
    assert runtime_payload["daemon_pid"] == 4242
    assert runtime_payload["live_pid"] == 4242
    assert runtime_payload["daemon_pid_mismatch"] is False


def test_repo_boundary_scan_flags_runtime_drift_categories(tmp_path: Path) -> None:
    mod = load_module()

    (tmp_path / ".dharma" / "daemon.pid").parent.mkdir(parents=True)
    (tmp_path / ".dharma" / "daemon.pid").write_text("123\n", encoding="utf-8")
    (tmp_path / "specs" / "states").mkdir(parents=True)
    (tmp_path / "specs" / "states" / "oversized.json").write_bytes(b"x" * (600 * 1024))
    (tmp_path / "dharma_swarm").mkdir(parents=True)
    (tmp_path / "dharma_swarm" / "runtime.db").write_bytes(b"sqlite")

    findings = mod.collect_repo_boundary_drift(tmp_path)
    joined = "\n".join(findings)

    assert "machine-local runtime state" in joined
    assert "specs/states" in joined
    assert "runtime artifacts in source tree" in joined


def test_verify_humming_reports_repo_boundary_without_failing(
    monkeypatch,
    capsys,
) -> None:
    mod = load_module()

    def fake_run_command(command, *, cwd=None, timeout_seconds=None):  # type: ignore[no-untyped-def]
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(mod, "run_command", fake_run_command)
    monkeypatch.setattr(
        mod,
        "collect_repo_boundary_drift",
        lambda repo_root: [
            "machine-local runtime state: .dharma/",
            "runtime artifacts in source tree: dharma_swarm/runtime.db",
        ],
    )

    exit_code = mod.main([])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Repo boundary: WARN (2 findings)" in captured.out
    assert "machine-local runtime state: .dharma/" in captured.out
    assert "runtime artifacts in source tree: dharma_swarm/runtime.db" in captured.out
