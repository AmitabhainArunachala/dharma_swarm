"""Tests for Witness (Viveka) -- S3* sporadic auditor."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dharma_swarm.witness import (
    AuditFinding,
    WitnessAuditor,
)


# ---------------------------------------------------------------------------
# AuditFinding unit tests
# ---------------------------------------------------------------------------


class TestAuditFinding:
    def test_finding_defaults(self):
        f = AuditFinding("t-1", "agent-a", "task_completed")
        assert f.telos_aligned is True
        assert f.mimicry_detected is False
        assert f.gate_sufficient is True
        assert f.severity == "info"
        assert f.is_actionable is False

    def test_finding_actionable_when_not_aligned(self):
        f = AuditFinding("t-1", "agent-a", "task_completed", telos_aligned=False)
        assert f.is_actionable is True

    def test_finding_actionable_when_mimicry(self):
        f = AuditFinding("t-1", "agent-a", "task_completed", mimicry_detected=True)
        assert f.is_actionable is True

    def test_finding_actionable_when_gate_insufficient(self):
        f = AuditFinding("t-1", "agent-a", "task_completed", gate_sufficient=False)
        assert f.is_actionable is True

    def test_finding_actionable_when_warning(self):
        f = AuditFinding("t-1", "agent-a", "task_completed", severity="warning")
        assert f.is_actionable is True

    def test_finding_actionable_when_critical(self):
        f = AuditFinding("t-1", "agent-a", "task_completed", severity="critical")
        assert f.is_actionable is True

    def test_to_dict(self):
        f = AuditFinding("t-1", "agent-a", "scan", observation="looks good")
        d = f.to_dict()
        assert d["trace_id"] == "t-1"
        assert d["agent"] == "agent-a"
        assert d["action"] == "scan"
        assert d["observation"] == "looks good"
        assert d["telos_aligned"] is True
        assert "timestamp" in d
        assert "id" in d


# ---------------------------------------------------------------------------
# WitnessAuditor unit tests
# ---------------------------------------------------------------------------


class TestWitnessAuditor:
    def test_init_defaults(self):
        w = WitnessAuditor()
        assert w._cycle_seconds == 3600.0
        assert w._running is False
        assert w._cycles_completed == 0

    def test_get_stats(self):
        w = WitnessAuditor(cycle_seconds=120.0)
        stats = w.get_stats()
        assert stats["cycles_completed"] == 0
        assert stats["total_findings"] == 0
        assert stats["running"] is False
        assert stats["cycle_seconds"] == 120.0
        assert stats["actionable_rate"] == 0.0

    def test_stop(self):
        w = WitnessAuditor()
        w._running = True
        w.stop()
        assert w._running is False


# ---------------------------------------------------------------------------
# Evaluation logic
# ---------------------------------------------------------------------------


class TestEvaluation:
    @pytest.mark.asyncio
    async def test_evaluate_missing_gate_results(self):
        w = WitnessAuditor()
        trace = {
            "id": "t-1",
            "agent": "agent-a",
            "action": "task_completed",
            "metadata": {},  # no gate_results
        }
        finding = await w._evaluate_trace(trace)
        assert finding.gate_sufficient is False
        assert finding.severity == "warning"
        assert "no gate results" in finding.observation

    @pytest.mark.asyncio
    async def test_evaluate_fast_completion_mimicry(self):
        w = WitnessAuditor()
        trace = {
            "id": "t-2",
            "agent": "agent-b",
            "action": "task_completed",
            "metadata": {
                "gate_results": {"truth": "PASS"},
                "duration_seconds": 0.1,
            },
        }
        finding = await w._evaluate_trace(trace)
        assert finding.mimicry_detected is True
        assert "fast" in finding.observation.lower()

    @pytest.mark.asyncio
    async def test_evaluate_clean_trace(self):
        w = WitnessAuditor()
        trace = {
            "id": "t-3",
            "agent": "agent-c",
            "action": "task_completed",
            "metadata": {
                "gate_results": {"truth": "PASS"},
                "duration_seconds": 30.0,
            },
        }
        finding = await w._evaluate_trace(trace)
        assert finding.telos_aligned is True
        assert finding.mimicry_detected is False
        assert finding.gate_sufficient is True
        assert finding.severity == "info"

    @pytest.mark.asyncio
    async def test_evaluate_non_task_action(self):
        """Non-task actions shouldn't trigger gate or mimicry checks."""
        w = WitnessAuditor()
        trace = {
            "id": "t-4",
            "agent": "agent-d",
            "action": "heartbeat",
            "metadata": {},
        }
        finding = await w._evaluate_trace(trace)
        assert finding.gate_sufficient is True
        assert finding.mimicry_detected is False
        assert finding.severity == "info"


# ---------------------------------------------------------------------------
# Run cycle
# ---------------------------------------------------------------------------


class TestRunCycle:
    @pytest.mark.asyncio
    async def test_run_cycle_no_traces(self):
        w = WitnessAuditor()
        with patch.object(w, "_sample_traces", new_callable=AsyncMock, return_value=[]):
            findings = await w.run_cycle()
        assert findings == []
        assert w._cycles_completed == 0  # no traces = no completed cycle

    @pytest.mark.asyncio
    async def test_run_cycle_with_traces(self):
        w = WitnessAuditor()
        traces = [
            {"id": "t-1", "agent": "a", "action": "heartbeat", "metadata": {}},
            {"id": "t-2", "agent": "b", "action": "scan", "metadata": {}},
        ]
        with patch.object(w, "_sample_traces", new_callable=AsyncMock, return_value=traces):
            with patch.object(w, "_publish_findings", new_callable=AsyncMock):
                findings = await w.run_cycle()

        assert len(findings) == 2
        assert w._cycles_completed == 1
        assert w._total_findings == 2

    @pytest.mark.asyncio
    async def test_stats_update_after_cycle(self):
        w = WitnessAuditor()
        # One trace that's actionable (missing gate results on task_completed)
        traces = [
            {"id": "t-1", "agent": "a", "action": "task_completed", "metadata": {}},
        ]
        with patch.object(w, "_sample_traces", new_callable=AsyncMock, return_value=traces):
            with patch.object(w, "_publish_findings", new_callable=AsyncMock):
                await w.run_cycle()

        stats = w.get_stats()
        assert stats["cycles_completed"] == 1
        assert stats["total_findings"] == 1
        assert stats["actionable_findings"] == 1
        assert stats["actionable_rate"] == 1.0
