"""Tests for the Claude Code ↔ dharma_swarm bridge module."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from dharma_swarm.claude_hooks import (
    stop_verify,
    session_context,
    verify_baseline,
)


class TestStopVerify:
    """stop_verify delegates to telos_gates and returns structured results."""

    def test_returns_gate_report(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.claude_hooks.STATE_DIR", tmp_path)
        result = stop_verify()
        assert "gate_decision" in result
        assert "gate_reason" in result
        assert "gates_passed" in result
        assert "gates_total" in result
        assert isinstance(result["gates_passed"], int)
        assert isinstance(result["gates_total"], int)

    def test_writes_audit_trail(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.claude_hooks.STATE_DIR", tmp_path)
        stop_verify()
        audit_file = tmp_path / "audit" / "claude_sessions.jsonl"
        assert audit_file.exists()
        entry = json.loads(audit_file.read_text().strip())
        assert entry["event"] == "session_stop"
        assert "timestamp" in entry

    def test_gates_pass_count_reasonable(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.claude_hooks.STATE_DIR", tmp_path)
        result = stop_verify()
        # With a benign action string, most gates should pass
        assert result["gates_passed"] >= 8
        assert result["gates_total"] >= 11


class TestSessionContext:
    """session_context assembles a compact DGC snapshot."""

    def test_returns_nonempty_string(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.claude_hooks.STATE_DIR", tmp_path)
        ctx = session_context()
        assert isinstance(ctx, str)
        assert "DGC mission-control" in ctx

    def test_includes_active_thread(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.claude_hooks.STATE_DIR", tmp_path)
        (tmp_path / "active_thread.txt").write_text("mechanistic")
        ctx = session_context()
        assert "mechanistic" in ctx

    def test_handles_missing_state_gracefully(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.claude_hooks.STATE_DIR", tmp_path / "nonexistent")
        ctx = session_context()
        assert isinstance(ctx, str)
        assert "DGC mission-control" in ctx

    def test_includes_ecosystem_count(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.claude_hooks.STATE_DIR", tmp_path)
        ctx = session_context()
        assert "Ecosystem:" in ctx or "alive" in ctx


class TestVerifyBaseline:
    """verify_baseline combines gates + health into one report."""

    def test_returns_gates_and_health(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.claude_hooks.STATE_DIR", tmp_path)
        result = verify_baseline()
        assert "gates" in result
        assert "health" in result
        assert "decision" in result["gates"]
        assert "passed" in result["gates"]
        assert "total" in result["gates"]

    def test_health_section_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.claude_hooks.STATE_DIR", tmp_path)
        result = verify_baseline()
        health = result["health"]
        assert health is not None
        # Either has status or error
        assert "status" in health or "error" in health


class TestCLIEntryPoint:
    """The module can be invoked as a CLI tool."""

    def test_stop_verify_cli(self):
        result = subprocess.run(
            [sys.executable, "-m", "dharma_swarm.claude_hooks", "stop_verify"],
            capture_output=True, text=True, timeout=15,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "gate_decision" in data

    def test_session_context_cli(self):
        result = subprocess.run(
            [sys.executable, "-m", "dharma_swarm.claude_hooks", "session_context"],
            capture_output=True, text=True, timeout=15,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0
        assert "DGC mission-control" in result.stdout

    def test_verify_baseline_cli(self):
        result = subprocess.run(
            [sys.executable, "-m", "dharma_swarm.claude_hooks", "verify_baseline"],
            capture_output=True, text=True, timeout=15,
            cwd=str(Path(__file__).parent.parent),
        )
        # Exit 0 or 1 depending on gate result — both valid
        data = json.loads(result.stdout)
        assert "gates" in data
        assert "health" in data

    def test_unknown_command_exits_nonzero(self):
        result = subprocess.run(
            [sys.executable, "-m", "dharma_swarm.claude_hooks", "bogus"],
            capture_output=True, text=True, timeout=10,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode != 0
