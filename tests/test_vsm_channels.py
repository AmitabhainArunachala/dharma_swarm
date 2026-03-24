"""Tests for VSM nervous system channels."""

import asyncio
import pytest
from pathlib import Path
from dharma_swarm.vsm_channels import (
    AlgedonicChannel,
    AlgedonicSignal,
    AgentViability,
    AgentViabilityMonitor,
    AuditResult,
    GatePattern,
    GatePatternAggregator,
    SporadicAuditor,
    VarietyExpansionProtocol,
    VSMCoordinator,
)
from dharma_swarm.models import GateResult


# ── S3↔S4: Gate Pattern Aggregator ───────────────────────────────

class TestGatePatternAggregator:

    def test_records_gate_check(self, tmp_path):
        agg = GatePatternAggregator(state_dir=tmp_path)
        result = agg.record_gate_check("AHIMSA", GateResult.PASS, "safe action")
        # Single pass shouldn't be anomalous
        assert result is None

    def test_detects_anomalous_pattern(self, tmp_path):
        agg = GatePatternAggregator(state_dir=tmp_path)
        # 5 failures out of 6 checks
        for i in range(5):
            agg.record_gate_check("SATYA", GateResult.FAIL, f"bad action {i}")
        pattern = agg.record_gate_check("SATYA", GateResult.PASS, "ok action")
        # After 6 checks with 5 failures (83% failure rate), should be anomalous
        patterns = agg.get_all_patterns()
        satya = [p for p in patterns if p.gate_name == "SATYA"][0]
        assert satya.is_anomalous
        assert satya.failure_rate > 0.8

    def test_zeitgeist_signal_boosts_sensitivity(self, tmp_path):
        agg = GatePatternAggregator(state_dir=tmp_path)
        assert agg.get_sensitivity_boost("SATYA") == 0.0
        agg.receive_zeitgeist_signal("threat", ["competing", "preprint"])
        assert agg.get_sensitivity_boost("SATYA") == 0.2

    def test_opportunity_relaxes_gate(self, tmp_path):
        agg = GatePatternAggregator(state_dir=tmp_path)
        agg.receive_zeitgeist_signal("opportunity", ["tool_release"])
        assert agg.get_sensitivity_boost("VYAVASTHIT") == -0.1


# ── S3*: Sporadic Auditor ────────────────────────────────────────

class TestSporadicAuditor:

    def test_audit_passes_clean_output(self, tmp_path):
        auditor = SporadicAuditor(state_dir=tmp_path)
        result = asyncio.run(
            auditor.audit_agent_output(
                agent_id="test_agent",
                task_description="analyze data",
                output="The results suggest a possible correlation, though uncertainty remains.",
            )
        )
        assert result.passed

    def test_audit_catches_overclaiming(self, tmp_path):
        auditor = SporadicAuditor(state_dir=tmp_path)
        result = asyncio.run(
            auditor.audit_agent_output(
                agent_id="test_agent",
                task_description="analyze data",
                output="I am certain " * 100 + " this is definitely correct without a doubt",
            )
        )
        assert not result.passed
        assert any("Overmind Humility" in f for f in result.findings)

    def test_audit_catches_gate_inconsistency(self, tmp_path):
        auditor = SporadicAuditor(state_dir=tmp_path)
        result = asyncio.run(
            auditor.audit_agent_output(
                agent_id="test_agent",
                task_description="deploy code",
                output="Deployed successfully.",
                gate_results={"AHIMSA": "FAIL"},
            )
        )
        assert not result.passed
        assert any("Gate consistency" in f for f in result.findings)

    def test_probability_control(self, tmp_path):
        # With probability 0, should never audit
        auditor = SporadicAuditor(audit_probability=0.0, state_dir=tmp_path)
        audits = sum(1 for _ in range(100) if auditor.should_audit())
        assert audits == 0

        # With probability 1, should always audit
        auditor = SporadicAuditor(audit_probability=1.0, state_dir=tmp_path)
        audits = sum(1 for _ in range(100) if auditor.should_audit())
        assert audits == 100


# ── Algedonic Channel ────────────────────────────────────────────

class TestAlgedonicChannel:

    def test_fire_signal(self, tmp_path):
        channel = AlgedonicChannel(state_dir=tmp_path)
        signal = AlgedonicSignal(
            severity="warning",
            source_system="S3",
            title="Test signal",
            description="Testing algedonic channel",
        )
        asyncio.run(channel.fire(signal))
        assert len(channel.active_signals) == 1
        assert channel.active_signals[0].title == "Test signal"

    def test_acknowledge_signal(self, tmp_path):
        channel = AlgedonicChannel(state_dir=tmp_path)
        signal = AlgedonicSignal(
            severity="critical",
            source_system="S1",
            title="Critical issue",
            description="Something broke",
        )
        asyncio.run(channel.fire(signal))
        assert len(channel.active_signals) == 1

        channel.acknowledge(signal.id)
        assert len(channel.active_signals) == 0
        assert len(channel.all_signals) == 1

    def test_gate_streak_triggers_signal(self, tmp_path):
        channel = AlgedonicChannel(state_dir=tmp_path)
        asyncio.run(
            channel.check_gate_streak("agent_01", 5, "AHIMSA")
        )
        assert len(channel.active_signals) == 1
        assert "agent_01" in channel.active_signals[0].title

    def test_health_triggers_signal(self, tmp_path):
        channel = AlgedonicChannel(state_dir=tmp_path)
        asyncio.run(
            channel.check_health("evolution", 0.05)
        )
        assert len(channel.active_signals) == 1
        assert channel.active_signals[0].severity == "critical"

    def test_callback_invoked(self, tmp_path):
        channel = AlgedonicChannel(state_dir=tmp_path)
        received = []
        channel.register_callback(lambda sig: received.append(sig))

        signal = AlgedonicSignal(
            severity="warning",
            source_system="S3",
            title="Test",
            description="Test",
        )
        asyncio.run(channel.fire(signal))
        assert len(received) == 1

    def test_active_summary_written(self, tmp_path):
        channel = AlgedonicChannel(state_dir=tmp_path)
        signal = AlgedonicSignal(
            severity="emergency",
            source_system="S1",
            title="Emergency",
            description="System down",
        )
        asyncio.run(channel.fire(signal))
        active_path = tmp_path / "meta" / "ALGEDONIC_ACTIVE.md"
        assert active_path.exists()
        content = active_path.read_text()
        assert "Emergency" in content
        assert "ACTIVE SIGNALS" in content


# ── Agent Viability ──────────────────────────────────────────────

class TestAgentViability:

    def test_compute_overall(self):
        v = AgentViability(
            agent_id="test",
            s1_operations=0.9,
            s2_coordination=0.8,
            s3_control=0.7,
            s4_intelligence=0.6,
            s5_identity=1.0,
        )
        overall = v.compute_overall()
        assert 0.7 < overall < 0.85

    def test_zero_floor(self):
        v = AgentViability(
            agent_id="test",
            s1_operations=0.0,
            s2_coordination=1.0,
            s3_control=1.0,
            s4_intelligence=1.0,
            s5_identity=1.0,
        )
        overall = v.compute_overall()
        # Should not be zero due to floor
        assert overall > 0

    def test_monitor_tracks_viabilities(self):
        monitor = AgentViabilityMonitor()
        monitor.update(AgentViability(agent_id="a1", s1_operations=0.9))
        monitor.update(AgentViability(agent_id="a2", s1_operations=0.8))
        assert monitor.fleet_health() > 0.5
        assert monitor.get("a1") is not None
        assert monitor.get("nonexistent") is None


# ── Variety Expansion Protocol ───────────────────────────────────

class TestVarietyExpansion:

    def test_propose_and_approve(self, tmp_path):
        vep = VarietyExpansionProtocol(state_dir=tmp_path)
        proposal = vep.propose(
            gate_name="DATA_INTEGRITY",
            tier="B",
            rationale="New data corruption threats detected by zeitgeist",
        )
        assert len(vep.pending) == 1
        assert len(vep.approved) == 0

        vep.approve(proposal.id)
        assert len(vep.pending) == 0
        assert len(vep.approved) == 1

    def test_reject(self, tmp_path):
        vep = VarietyExpansionProtocol(state_dir=tmp_path)
        proposal = vep.propose("UNNECESSARY", "C", "weak rationale")
        vep.reject(proposal.id)
        assert len(vep.pending) == 0
        assert len(vep.approved) == 0


# ── VSM Coordinator ──────────────────────────────────────────────

class TestVSMCoordinator:

    def test_status(self, tmp_path):
        vsm = VSMCoordinator(state_dir=tmp_path)
        status = vsm.status()
        assert "algedonic_active" in status
        assert "fleet_health" in status
        assert status["algedonic_active"] == 0

    def test_on_gate_check_tracks_streaks(self, tmp_path):
        vsm = VSMCoordinator(state_dir=tmp_path)
        vsm.on_gate_check("AHIMSA", GateResult.FAIL, "bad", "agent_01")
        vsm.on_gate_check("AHIMSA", GateResult.FAIL, "bad", "agent_01")
        assert vsm._agent_failure_streaks["agent_01"] == 2

        vsm.on_gate_check("AHIMSA", GateResult.PASS, "ok", "agent_01")
        assert vsm._agent_failure_streaks["agent_01"] == 0

    def test_on_agent_output_fires_algedonic_on_streak(self, tmp_path):
        vsm = VSMCoordinator(state_dir=tmp_path)
        # Build up a failure streak
        for _ in range(5):
            vsm.on_gate_check("AHIMSA", GateResult.FAIL, "bad", "agent_01")

        # This should trigger algedonic
        asyncio.run(
            vsm.on_agent_output("agent_01", "task", "output")
        )
        assert len(vsm.algedonic.active_signals) >= 1
