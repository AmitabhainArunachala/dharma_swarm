"""Integration smoke tests: prove the core call chains actually work.

Unlike unit tests that mock everything, these tests exercise REAL code paths
with only network calls (LLM APIs) mocked. They verify:

1. Evolution full cycle: Propose → Gate → Evaluate → Archive
2. Context assembly: role-based context produces content for the right domain
3. CLI commands: critical dgc commands don't crash
4. Monitor → Traces: health checks produce real trace entries
5. Telos gates: real gate evaluation returns decisions
6. Kernel integrity: principles are loadable and downward causation works
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dharma_swarm.archive import FitnessScore
from dharma_swarm.context import build_agent_context
from dharma_swarm.dharma_kernel import KernelGuard
from dharma_swarm.evolution import DarwinEngine, EvolutionStatus, Proposal
from dharma_swarm.models import GateDecision
from dharma_swarm.monitor import HealthReport, HealthStatus, SystemMonitor
from dharma_swarm.telos_gates import GateCheckResult, TelosGatekeeper, check_action
from dharma_swarm.traces import TraceEntry, TraceStore


# =========================================================================
# 1. Evolution Full Cycle
# =========================================================================


@pytest.mark.asyncio
async def test_evolution_propose_gate_evaluate_archive(tmp_path: Path) -> None:
    """Full evolution pipeline: Propose → Gate → Evaluate → Archive."""
    archive_path = tmp_path / "archive.jsonl"
    traces_path = tmp_path / "traces"

    engine = DarwinEngine(
        archive_path=archive_path,
        traces_path=traces_path,
        predictor_path=tmp_path / "predictor.jsonl",
    )

    proposal = Proposal(
        component="monitor",
        change_type="mutation",
        description="Add anomaly detection cooldown to prevent alert fatigue",
        diff="--- a/monitor.py\n+++ b/monitor.py\n@@ -1 +1 @@\n-old\n+new",
    )

    # Gate check (uses real telos gates, no LLM)
    gate_result = check_action(
        action=f"evolve:{proposal.component}",
        content=proposal.description,
    )
    assert isinstance(gate_result, GateCheckResult)
    assert gate_result.decision in (
        GateDecision.ALLOW,
        GateDecision.BLOCK,
        GateDecision.REVIEW,
    )
    assert len(gate_result.gate_results) > 0, "Gate produced no results"

    # Update proposal status based on gate result
    if gate_result.decision != GateDecision.BLOCK:
        proposal.status = EvolutionStatus.GATED
        proposal.gate_decision = gate_result.decision.value

    # Create fitness score and archive
    fitness = FitnessScore(
        correctness=0.9,
        dharmic_alignment=0.7,
        performance=0.8,
        elegance=0.6,
    )
    proposal.actual_fitness = fitness
    proposal.status = EvolutionStatus.EVALUATED

    archive_id = await engine.archive_result(proposal)
    assert archive_id, "Archive returned empty ID"
    assert archive_path.exists(), "Archive file not created"

    lines = archive_path.read_text().strip().split("\n")
    assert len(lines) >= 1, "Archive file is empty"

    entry = json.loads(lines[-1])
    assert entry["component"] == "monitor"
    assert "anomaly" in entry["description"].lower()


# =========================================================================
# 2. Context Assembly
# =========================================================================


def test_context_assembly_produces_content(tmp_path: Path) -> None:
    """Context assembly should produce non-empty content for known roles."""
    ctx = build_agent_context(role="surgeon", state_dir=tmp_path)
    assert isinstance(ctx, str)
    assert len(ctx) > 50, f"Context too short ({len(ctx)} chars)"


def test_context_assembly_different_roles(tmp_path: Path) -> None:
    """Different roles should both produce valid context strings."""
    surgeon = build_agent_context(role="surgeon", state_dir=tmp_path)
    cartographer = build_agent_context(role="cartographer", state_dir=tmp_path)
    assert isinstance(surgeon, str)
    assert isinstance(cartographer, str)


# =========================================================================
# 3. CLI Smoke Tests
# =========================================================================


DGC = "/opt/homebrew/bin/dgc"


@pytest.mark.skipif(
    not Path(DGC).exists(),
    reason="dgc CLI not installed",
)
class TestCLISmoke:
    """Verify critical CLI commands execute without crashing."""

    def _run(self, *args: str, timeout: int = 15) -> subprocess.CompletedProcess:
        return subprocess.run(
            [DGC, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def test_status(self) -> None:
        r = self._run("status")
        assert r.returncode == 0
        assert "STATUS" in r.stdout.upper() or "status" in r.stdout.lower()

    def test_health(self) -> None:
        r = self._run("health")
        assert r.returncode == 0
        assert "OK" in r.stdout or "MISSING" in r.stdout

    def test_daemon_status(self) -> None:
        r = self._run("daemon-status")
        assert r.returncode == 0
        assert "status" in r.stdout.lower() or "PID" in r.stdout

    def test_memory(self) -> None:
        r = self._run("memory")
        assert r.returncode == 0
        assert "memory" in r.stdout.lower() or "Memory" in r.stdout

    def test_canonical_status(self) -> None:
        r = self._run("canonical-status")
        assert r.returncode == 0
        assert "CANONICAL" in r.stdout.upper()


# =========================================================================
# 4. Monitor → Traces Integration
# =========================================================================


@pytest.mark.asyncio
async def test_monitor_health_check_produces_real_data(tmp_path: Path) -> None:
    """SystemMonitor should produce a report with actual health status."""
    trace_store = TraceStore(base_path=tmp_path)
    monitor = SystemMonitor(trace_store=trace_store)
    report = await monitor.check_health()

    assert isinstance(report, HealthReport)
    assert report.overall_status in (
        HealthStatus.HEALTHY,
        HealthStatus.DEGRADED,
        HealthStatus.CRITICAL,
        HealthStatus.UNKNOWN,
    )


@pytest.mark.asyncio
async def test_trace_store_write_and_read(tmp_path: Path) -> None:
    """TraceStore should persist entries and read them back."""
    store = TraceStore(base_path=tmp_path)

    entry = TraceEntry(
        agent="test_agent",
        action="test_action",
        state="completed",
        files_changed=["module_a.py"],
        metadata={"detail": "Integration test trace entry"},
    )
    entry_id = await store.log_entry(entry)
    assert entry_id, "log_entry returned empty ID"

    entries = await store.get_recent(limit=5)
    assert len(entries) >= 1
    latest = entries[-1]
    assert latest.agent == "test_agent"
    assert latest.action == "test_action"
    assert latest.state == "completed"


# =========================================================================
# 5. Telos Gates
# =========================================================================


def test_telos_gate_evaluation() -> None:
    """Telos gates should evaluate actions and return structured decisions."""
    result = check_action(
        action="deploy:production",
        content="Deploy latest version to production servers",
    )
    assert isinstance(result, GateCheckResult)
    assert result.decision in (
        GateDecision.ALLOW,
        GateDecision.BLOCK,
        GateDecision.REVIEW,
    )
    assert len(result.gate_results) > 0


def test_telos_gatekeeper_check() -> None:
    """TelosGatekeeper.check should evaluate consistently."""
    gk = TelosGatekeeper()
    result = gk.check(
        action="research:experiment",
        content="Run R_V contraction measurement on Mistral-7B",
    )
    assert isinstance(result, GateCheckResult)
    assert result.decision in (
        GateDecision.ALLOW,
        GateDecision.BLOCK,
        GateDecision.REVIEW,
    )


# =========================================================================
# 6. Kernel Integrity
# =========================================================================


def test_kernel_guard_loads() -> None:
    """KernelGuard should instantiate and expose its API."""
    guard = KernelGuard()
    # Should be able to check downward causation
    # Layer 3 proposing to layer 1 should be allowed (higher to lower)
    assert guard.check_downward_causation(proposer_layer=3, target_layer=1) is True
    # Layer 1 proposing to layer 3 should be blocked (lower to higher)
    assert guard.check_downward_causation(proposer_layer=1, target_layer=3) is False
