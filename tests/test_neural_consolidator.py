"""Tests for the Neural Consolidation Engine.

Validates the backpropagation loop for agent behavior:
- Forward scan reads system state
- Loss computation identifies errors
- Contrarian discussion produces corrections
- Backpropagation writes correction files
- Cell division detects scope overload
- Correction injection into agent prompts
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from dharma_swarm.neural_consolidator import (
    BehavioralCorrection,
    CellDivisionProposal,
    ConsolidationReport,
    LossSignal,
    NeuralConsolidator,
    SystemSnapshot,
    load_behavioral_corrections,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_dharma(tmp_path: Path) -> Path:
    """Create a temporary .dharma directory structure."""
    base = tmp_path / ".dharma"
    base.mkdir()
    (base / "agents").mkdir()
    (base / "traces").mkdir()
    (base / "stigmergy").mkdir()
    (base / "agent_memory").mkdir()
    (base / "ginko" / "agents" / "operator").mkdir(parents=True)
    (base / "ginko" / "agents" / "archivist").mkdir(parents=True)
    (base / "logs" / "router").mkdir(parents=True)
    return base


@pytest.fixture
def consolidator(tmp_dharma: Path) -> NeuralConsolidator:
    """Create a NeuralConsolidator with temp directories."""
    return NeuralConsolidator(
        provider=None,
        base_path=tmp_dharma,
        corrections_dir=tmp_dharma / "consolidation" / "corrections",
        reports_dir=tmp_dharma / "consolidation" / "reports",
    )


def _write_jsonl(path: Path, records: list[dict]) -> None:
    """Write records to a JSONL file."""
    path.write_text("\n".join(json.dumps(r) for r in records))


# ---------------------------------------------------------------------------
# SystemSnapshot
# ---------------------------------------------------------------------------


class TestSystemSnapshot:
    def test_agent_names(self):
        snap = SystemSnapshot(agent_states={"a": {}, "b": {}})
        assert snap.agent_names == ["a", "b"]

    def test_total_tasks(self):
        snap = SystemSnapshot(task_outcomes=[{"title": "t1"}, {"title": "t2"}])
        assert snap.total_tasks == 2

    def test_failure_rate_zero(self):
        snap = SystemSnapshot(task_outcomes=[{"success": True}])
        assert snap.failure_rate == 0.0

    def test_failure_rate_half(self):
        snap = SystemSnapshot(task_outcomes=[
            {"success": True},
            {"success": False},
        ])
        assert snap.failure_rate == 0.5

    def test_failure_rate_empty(self):
        snap = SystemSnapshot()
        assert snap.failure_rate == 0.0


# ---------------------------------------------------------------------------
# Forward Scan
# ---------------------------------------------------------------------------


class TestForwardScan:
    @pytest.mark.asyncio
    async def test_scan_empty_state(self, consolidator: NeuralConsolidator):
        snap = await consolidator.forward_scan()
        assert isinstance(snap, SystemSnapshot)
        assert snap.timestamp != ""
        assert snap.total_tasks == 0

    @pytest.mark.asyncio
    async def test_scan_reads_traces(self, consolidator: NeuralConsolidator, tmp_dharma: Path):
        traces = [{"agent": "op", "action": "task_completed", "result": "done"}]
        _write_jsonl(tmp_dharma / "traces" / "2026-03-22.jsonl", traces)
        snap = await consolidator.forward_scan()
        assert len(snap.traces) == 1
        assert snap.traces[0]["agent"] == "op"

    @pytest.mark.asyncio
    async def test_scan_reads_stigmergy(self, consolidator: NeuralConsolidator, tmp_dharma: Path):
        marks = [
            {"agent": "op", "observation": "test mark", "salience": 0.8, "access_count": 0}
        ]
        _write_jsonl(tmp_dharma / "stigmergy" / "marks.jsonl", marks)
        snap = await consolidator.forward_scan()
        assert len(snap.stigmergy_marks) == 1

    @pytest.mark.asyncio
    async def test_scan_reads_agent_states(self, consolidator: NeuralConsolidator, tmp_dharma: Path):
        identity = {"tasks_completed": 10, "tasks_failed": 2, "avg_quality": 0.72}
        (tmp_dharma / "ginko" / "agents" / "operator" / "identity.json").write_text(
            json.dumps(identity)
        )
        snap = await consolidator.forward_scan()
        assert "operator" in snap.agent_states
        assert snap.agent_states["operator"]["tasks_completed"] == 10

    @pytest.mark.asyncio
    async def test_scan_reads_agent_states_from_agents_dir(
        self,
        consolidator: NeuralConsolidator,
        tmp_dharma: Path,
    ):
        identity = {"tasks_completed": 4, "tasks_failed": 1, "avg_quality": 0.91}
        agent_dir = tmp_dharma / "agents" / "glm"
        agent_dir.mkdir(parents=True)
        (agent_dir / "identity.json").write_text(json.dumps(identity))

        snap = await consolidator.forward_scan()

        assert "glm" in snap.agent_states
        assert snap.agent_states["glm"]["avg_quality"] == 0.91

    @pytest.mark.asyncio
    async def test_scan_reads_task_outcomes_from_agents_task_logs(
        self,
        consolidator: NeuralConsolidator,
        tmp_dharma: Path,
    ):
        agent_dir = tmp_dharma / "agents" / "glm"
        agent_dir.mkdir(parents=True)
        _write_jsonl(
            agent_dir / "task_log.jsonl",
            [
                {
                    "agent_name": "glm",
                    "task_description": "debug provider timeout",
                    "success": False,
                    "error": "HTTP 429",
                },
                {
                    "agent_name": "glm",
                    "task_description": "ship patch",
                    "success": True,
                    "error": "",
                },
            ],
        )

        snap = await consolidator.forward_scan()

        assert len(snap.task_outcomes) == 2
        assert snap.task_outcomes[0]["agent"] == "glm"
        assert snap.task_outcomes[0]["title"] == "debug provider timeout"
        assert snap.task_outcomes[0]["success"] is False

    def test_normalize_task_outcome_labels_unspecified_failure(
        self,
        consolidator: NeuralConsolidator,
    ):
        outcome = consolidator._normalize_task_outcome(  # noqa: SLF001
            {
                "task": "BTC at $74K. One sentence: buy, sell, or wait?",
                "success": False,
            },
            agent_name="vajra",
        )

        assert outcome["error"] == "unspecified_failure"

    @pytest.mark.asyncio
    async def test_scan_reads_task_outcomes_from_ginko_task_logs(
        self, consolidator: NeuralConsolidator, tmp_dharma: Path,
    ):
        outcomes = [
            {
                "task": "fix timeout bug",
                "success": False,
                "timestamp": "2026-03-22T00:00:00Z",
                "response_preview": "timeout exceeded",
            },
            {
                "task": "design architecture review",
                "success": True,
                "timestamp": "2026-03-22T00:05:00Z",
            },
        ]
        _write_jsonl(tmp_dharma / "ginko" / "agents" / "operator" / "task_log.jsonl", outcomes)

        snap = await consolidator.forward_scan()

        assert len(snap.task_outcomes) == 2
        assert snap.task_outcomes[0]["agent"] == "operator"
        assert snap.task_outcomes[0]["title"] == "fix timeout bug"
        assert snap.task_outcomes[0]["success"] is False

    @pytest.mark.asyncio
    async def test_scan_synthesizes_task_outcomes_from_traces_when_logs_absent(
        self, consolidator: NeuralConsolidator, tmp_dharma: Path,
    ):
        traces = [
            {
                "agent": "operator",
                "action": "audit governance gates",
                "success": False,
                "error": "missing gate evaluation",
            },
            {
                "agent": "operator",
                "action": "design architecture spec",
                "success": True,
            },
        ]
        _write_jsonl(tmp_dharma / "traces" / "2026-03-22.jsonl", traces)

        snap = await consolidator.forward_scan()

        assert len(snap.task_outcomes) == 2
        assert snap.task_outcomes[0]["title"] == "audit governance gates"
        assert snap.task_outcomes[0]["success"] is False


# ---------------------------------------------------------------------------
# Loss Computation
# ---------------------------------------------------------------------------


class TestLossComputation:
    def test_no_losses_on_empty_snapshot(self, consolidator: NeuralConsolidator):
        snap = SystemSnapshot()
        losses = consolidator.compute_loss(snap)
        assert losses == []

    def test_detect_repeated_failures(self, consolidator: NeuralConsolidator):
        snap = SystemSnapshot(task_outcomes=[
            {"success": False, "error": "timeout: exceeded limit", "agent": "op"},
            {"success": False, "error": "timeout: exceeded limit", "agent": "op"},
            {"success": True, "agent": "op"},
        ])
        losses = consolidator.compute_loss(snap)
        repeated = [l for l in losses if l.category == "repeated_failure"]
        assert len(repeated) >= 1
        assert repeated[0].severity >= 0.5

    def test_detect_mimicry(self, consolidator: NeuralConsolidator):
        snap = SystemSnapshot(traces=[
            {
                "agent": "op",
                "result": "I understand your concern. Great question! "
                          "That's a really important point. Let me help you with that.",
            },
        ])
        losses = consolidator.compute_loss(snap)
        mimicry = [l for l in losses if l.category == "mimicry"]
        assert len(mimicry) >= 1

    def test_no_mimicry_on_genuine_output(self, consolidator: NeuralConsolidator):
        snap = SystemSnapshot(traces=[
            {
                "agent": "op",
                "result": "The gate check failed because the telos score was 0.3, "
                          "below the threshold of 0.5. Root cause is missing context "
                          "injection in the prompt builder pipeline.",
            },
        ])
        losses = consolidator.compute_loss(snap)
        mimicry = [l for l in losses if l.category == "mimicry"]
        assert len(mimicry) == 0

    def test_detect_coordination_gap(self, consolidator: NeuralConsolidator):
        snap = SystemSnapshot(stigmergy_marks=[
            {"agent": "op", "salience": 0.8, "access_count": 0, "observation": "mark1"},
            {"agent": "op", "salience": 0.7, "access_count": 0, "observation": "mark2"},
            {"agent": "op", "salience": 0.6, "access_count": 0, "observation": "mark3"},
        ])
        losses = consolidator.compute_loss(snap)
        gaps = [l for l in losses if l.category == "coordination_gap"]
        assert len(gaps) >= 1

    def test_detect_scope_overload(self, consolidator: NeuralConsolidator):
        snap = SystemSnapshot(task_outcomes=[
            {"agent": "op", "title": "fix test bug"},
            {"agent": "op", "title": "research paper analysis"},
            {"agent": "op", "title": "code review module"},
            {"agent": "op", "title": "evolve fitness function"},
            {"agent": "op", "title": "audit governance gates"},
            {"agent": "op", "title": "design architecture spec"},
        ])
        losses = consolidator.compute_loss(snap)
        overload = [l for l in losses if l.category == "scope_overload"]
        assert len(overload) >= 1

    def test_detect_telos_drift(self, consolidator: NeuralConsolidator):
        snap = SystemSnapshot(task_outcomes=[
            {"agent": "op", "title": "task1"},
            {"agent": "op", "title": "task2"},
            {"agent": "op", "title": "task3"},
            {"agent": "op", "title": "task4"},
        ])
        losses = consolidator.compute_loss(snap)
        drift = [l for l in losses if l.category == "telos_drift"]
        assert len(drift) >= 1

    def test_losses_sorted_by_severity(self, consolidator: NeuralConsolidator):
        snap = SystemSnapshot(
            task_outcomes=[
                {"success": False, "error": "timeout", "agent": "a"},
                {"success": False, "error": "timeout", "agent": "a"},
                {"agent": "b", "title": "t1"},
                {"agent": "b", "title": "t2"},
                {"agent": "b", "title": "t3"},
            ],
        )
        losses = consolidator.compute_loss(snap)
        if len(losses) >= 2:
            for i in range(len(losses) - 1):
                assert losses[i].severity >= losses[i + 1].severity


# ---------------------------------------------------------------------------
# Contrarian Discussion (algorithmic fallback)
# ---------------------------------------------------------------------------


class TestContrarianDiscussion:
    @pytest.mark.asyncio
    async def test_algorithmic_fallback_no_provider(self, consolidator: NeuralConsolidator):
        """Without a provider, contrarian_discuss uses algorithmic corrections."""
        snap = SystemSnapshot()
        losses = [
            LossSignal(
                category="repeated_failure",
                agent="op",
                severity=0.8,
                evidence="Timeout occurred 4 times",
                correction_hint="Increase timeout or reduce task complexity",
            ),
        ]
        corrections = await consolidator.contrarian_discuss(snap, losses)
        assert len(corrections) >= 1
        assert corrections[0].target_agent == "op"
        assert corrections[0].source == "algorithmic"

    @pytest.mark.asyncio
    async def test_algorithmic_skips_low_severity(self, consolidator: NeuralConsolidator):
        snap = SystemSnapshot()
        losses = [
            LossSignal(
                category="telos_drift",
                agent="*",
                severity=0.1,  # Too low
                evidence="minor drift",
                correction_hint="minor fix",
            ),
        ]
        corrections = await consolidator.contrarian_discuss(snap, losses)
        assert len(corrections) == 0

    @pytest.mark.asyncio
    async def test_llm_discussion_with_mock_provider(self, tmp_dharma: Path):
        """With a provider, uses advocate/critic/synthesis pattern."""
        provider = AsyncMock()
        # Simulate LLM responses
        mock_response = AsyncMock()
        mock_response.content = json.dumps([{
            "target_agent": "operator",
            "correction": "Reduce task scope to engineering only",
            "evidence": "Scope overload detected across 7 domains",
            "confidence": 0.85,
        }])
        provider.complete = AsyncMock(return_value=mock_response)

        consolidator = NeuralConsolidator(
            provider=provider,
            base_path=tmp_dharma,
            corrections_dir=tmp_dharma / "consolidation" / "corrections",
        )

        snap = SystemSnapshot()
        losses = [
            LossSignal("scope_overload", "operator", 0.9, "7 domains", "split agent"),
        ]
        corrections = await consolidator.contrarian_discuss(snap, losses)

        # Provider was called 3 times (advocate, critic, synthesis)
        assert provider.complete.call_count == 3
        assert len(corrections) >= 1
        assert corrections[0].target_agent == "operator"

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_algorithmic(self, tmp_dharma: Path):
        """If LLM calls fail, falls back to algorithmic corrections."""
        provider = AsyncMock()
        provider.complete = AsyncMock(side_effect=RuntimeError("API error"))

        consolidator = NeuralConsolidator(
            provider=provider,
            base_path=tmp_dharma,
            corrections_dir=tmp_dharma / "consolidation" / "corrections",
        )

        snap = SystemSnapshot()
        losses = [
            LossSignal("repeated_failure", "op", 0.7, "error X 3 times", "fix X"),
        ]
        corrections = await consolidator.contrarian_discuss(snap, losses)
        assert len(corrections) >= 1
        assert corrections[0].source == "algorithmic"


# ---------------------------------------------------------------------------
# Backpropagation (Weight Update)
# ---------------------------------------------------------------------------


class TestBackpropagation:
    @pytest.mark.asyncio
    async def test_write_correction_file(self, consolidator: NeuralConsolidator, tmp_dharma: Path):
        corrections = [
            BehavioralCorrection(
                target_agent="operator",
                correction="Focus on engineering tasks only",
                evidence="Scope overload across 7 domains",
                confidence=0.85,
                source="synthesis",
                timestamp="2026-03-22T00:00:00Z",
            ),
        ]
        result = await consolidator.backpropagate(corrections)
        assert result["corrections_applied"] >= 1
        assert "operator" in result["agents_updated"]

        # Check file was written
        correction_path = tmp_dharma / "consolidation" / "corrections" / "operator.md"
        assert correction_path.exists()
        content = correction_path.read_text()
        assert "Focus on engineering tasks only" in content
        assert "Scope overload" in content

    @pytest.mark.asyncio
    async def test_wildcard_correction(self, consolidator: NeuralConsolidator, tmp_dharma: Path):
        corrections = [
            BehavioralCorrection(
                target_agent="*",
                correction="Check telos gates before all actions",
                evidence="4 ungated tasks detected",
                confidence=0.9,
                source="algorithmic",
                timestamp="2026-03-22T00:00:00Z",
            ),
        ]
        result = await consolidator.backpropagate(corrections)
        assert "_global" in result["agents_updated"]

        global_path = tmp_dharma / "consolidation" / "corrections" / "_global.md"
        assert global_path.exists()

    @pytest.mark.asyncio
    async def test_skip_low_confidence(self, consolidator: NeuralConsolidator, tmp_dharma: Path):
        corrections = [
            BehavioralCorrection(
                target_agent="op",
                correction="maybe try this",
                evidence="weak signal",
                confidence=0.1,  # Too low
                source="algorithmic",
            ),
        ]
        result = await consolidator.backpropagate(corrections)
        assert result["corrections_applied"] == 0


# ---------------------------------------------------------------------------
# Cell Division
# ---------------------------------------------------------------------------


class TestCellDivision:
    def test_no_division_on_focused_agent(self, consolidator: NeuralConsolidator):
        snap = SystemSnapshot(task_outcomes=[
            {"agent": "op", "title": "fix test bug"},
            {"agent": "op", "title": "fix code issue"},
            {"agent": "op", "title": "fix lint error"},
        ])
        proposals = consolidator.check_cell_division(snap)
        assert len(proposals) == 0

    def test_division_on_scope_overload(self, consolidator: NeuralConsolidator):
        snap = SystemSnapshot(task_outcomes=[
            {"agent": "op", "title": "fix test bug"},
            {"agent": "op", "title": "research consciousness paper"},
            {"agent": "op", "title": "code new module"},
            {"agent": "op", "title": "evolve fitness scoring"},
            {"agent": "op", "title": "audit governance gates"},
            {"agent": "op", "title": "design system architecture"},
        ])
        proposals = consolidator.check_cell_division(snap)
        assert len(proposals) >= 1
        assert proposals[0].parent_agent == "op"
        assert proposals[0].variety_score >= 6
        assert len(proposals[0].proposed_children) >= 2

    def test_division_on_high_failure_rate(self, consolidator: NeuralConsolidator):
        snap = SystemSnapshot(task_outcomes=[
            {"agent": "op", "title": "task1", "success": False},
            {"agent": "op", "title": "task2", "success": False},
            {"agent": "op", "title": "task3", "success": True},
            {"agent": "op", "title": "task4", "success": False},
            {"agent": "op", "title": "task5", "success": False},
        ])
        proposals = consolidator.check_cell_division(snap)
        # 80% failure rate should trigger division
        assert len(proposals) >= 1
        assert proposals[0].failure_rate >= 0.35

    def test_division_handles_null_domain(self, consolidator: NeuralConsolidator):
        snap = SystemSnapshot(task_outcomes=[
            {"agent": "op", "title": "task1", "success": False, "domain": None},
            {"agent": "op", "title": "task2", "success": False, "domain": None},
            {"agent": "op", "title": "task3", "success": False, "domain": None},
            {"agent": "op", "title": "task4", "success": False, "domain": None},
        ])

        proposals = consolidator.check_cell_division(snap)

        assert len(proposals) >= 1
        assert proposals[0].proposed_children[0]["specialization"] == "general"


# ---------------------------------------------------------------------------
# Correction Injection
# ---------------------------------------------------------------------------


class TestCorrectionInjection:
    def test_load_no_corrections(self, tmp_dharma: Path):
        cdir = tmp_dharma / "consolidation" / "corrections"
        result = load_behavioral_corrections("operator", corrections_dir=cdir)
        assert result == ""

    def test_load_agent_specific(self, tmp_dharma: Path):
        cdir = tmp_dharma / "consolidation" / "corrections"
        cdir.mkdir(parents=True)
        (cdir / "operator.md").write_text("# Corrections\nFocus on engineering only.")
        result = load_behavioral_corrections("operator", corrections_dir=cdir)
        assert "Focus on engineering only" in result
        assert "Neural Consolidation Corrections" in result

    def test_load_global_corrections(self, tmp_dharma: Path):
        cdir = tmp_dharma / "consolidation" / "corrections"
        cdir.mkdir(parents=True)
        (cdir / "_global.md").write_text("# Global\nCheck telos gates.")
        result = load_behavioral_corrections("anyagent", corrections_dir=cdir)
        assert "Check telos gates" in result

    def test_load_both_global_and_specific(self, tmp_dharma: Path):
        cdir = tmp_dharma / "consolidation" / "corrections"
        cdir.mkdir(parents=True)
        (cdir / "_global.md").write_text("# Global\nCheck telos.")
        (cdir / "operator.md").write_text("# Operator\nFocus on code.")
        result = load_behavioral_corrections("operator", corrections_dir=cdir)
        assert "Check telos" in result
        assert "Focus on code" in result


# ---------------------------------------------------------------------------
# Full Consolidation Cycle
# ---------------------------------------------------------------------------


class TestConsolidationCycle:
    @pytest.mark.asyncio
    async def test_full_cycle_empty_state(self, consolidator: NeuralConsolidator):
        report = await consolidator.consolidation_cycle()
        assert isinstance(report, ConsolidationReport)
        assert report.started_at != ""
        assert report.duration_seconds >= 0
        assert report.losses_found == 0
        assert report.corrections_applied == 0

    @pytest.mark.asyncio
    async def test_full_cycle_with_losses(self, consolidator: NeuralConsolidator, tmp_dharma: Path):
        # Seed some failing task outcomes
        cycles_path = tmp_dharma / "cycles.jsonl"
        outcomes = [
            {"agent": "op", "title": "task1", "success": False, "error": "timeout"},
            {"agent": "op", "title": "task2", "success": False, "error": "timeout"},
            {"agent": "op", "title": "task3", "success": True},
        ]
        _write_jsonl(cycles_path, outcomes)

        report = await consolidator.consolidation_cycle()
        assert report.losses_found >= 1
        # Algorithmic corrections should be applied
        assert report.corrections_applied >= 1

    @pytest.mark.asyncio
    async def test_full_cycle_persists_report(self, consolidator: NeuralConsolidator, tmp_dharma: Path):
        await consolidator.consolidation_cycle()
        reports_dir = tmp_dharma / "consolidation" / "reports"
        reports = list(reports_dir.glob("consolidation_*.json"))
        assert len(reports) >= 1
        data = json.loads(reports[0].read_text())
        assert "started_at" in data
        assert "losses_found" in data

    @pytest.mark.asyncio
    async def test_full_cycle_with_division_proposals(
        self, consolidator: NeuralConsolidator, tmp_dharma: Path,
    ):
        # Seed task outcomes spanning many domains
        cycles_path = tmp_dharma / "cycles.jsonl"
        outcomes = [
            {"agent": "op", "title": "fix test bug"},
            {"agent": "op", "title": "research paper"},
            {"agent": "op", "title": "code new module"},
            {"agent": "op", "title": "evolve fitness"},
            {"agent": "op", "title": "audit governance"},
            {"agent": "op", "title": "design architecture"},
        ]
        _write_jsonl(cycles_path, outcomes)

        report = await consolidator.consolidation_cycle()
        assert report.division_proposals >= 1

        # Check proposals were persisted
        proposals_dir = tmp_dharma / "consolidation" / "division_proposals"
        proposals = list(proposals_dir.glob("proposals_*.json"))
        assert len(proposals) >= 1


# ---------------------------------------------------------------------------
# Sleep Cycle Integration
# ---------------------------------------------------------------------------


class TestSleepCycleIntegration:
    @pytest.mark.asyncio
    async def test_neural_phase_exists_in_enum(self):
        from dharma_swarm.sleep_cycle import SleepPhase
        assert hasattr(SleepPhase, "NEURAL")
        assert SleepPhase.NEURAL.value == "neural"

    @pytest.mark.asyncio
    async def test_neural_phase_runs_in_cycle(self, tmp_dharma: Path):
        from dharma_swarm.sleep_cycle import SleepCycle, SleepPhase

        cycle = SleepCycle(
            agent_memory_dir=tmp_dharma / "agent_memory",
            reports_dir=tmp_dharma / "sleep_reports",
        )
        result = await cycle.run_phase(SleepPhase.NEURAL)
        assert "losses_found" in result
        assert "corrections_applied" in result

    @pytest.mark.asyncio
    async def test_neural_phase_in_full_cycle(self, tmp_dharma: Path):
        from dharma_swarm.sleep_cycle import SleepCycle

        cycle = SleepCycle(
            agent_memory_dir=tmp_dharma / "agent_memory",
            reports_dir=tmp_dharma / "sleep_reports",
        )
        report = await cycle.run_full_cycle()
        assert "neural" in report.phases_completed


# ---------------------------------------------------------------------------
# Agent Runner Correction Injection
# ---------------------------------------------------------------------------


class TestAgentRunnerInjection:
    def test_correction_appears_in_system_prompt(self, tmp_dharma: Path):
        """Verify that load_behavioral_corrections returns content
        that would be injected into agent system prompts."""
        cdir = tmp_dharma / "consolidation" / "corrections"
        cdir.mkdir(parents=True)
        (cdir / "operator.md").write_text(
            "# Corrections\n\nReduce scope to engineering tasks only."
        )

        result = load_behavioral_corrections("operator", corrections_dir=cdir)
        assert "Reduce scope to engineering tasks only" in result
        assert "Neural Consolidation Corrections" in result
        assert "behavioral adjustments" in result.lower()
