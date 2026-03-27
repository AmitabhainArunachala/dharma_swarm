"""Tests for the Dynamic Correction Engine — drift detectors, policy matching,
correction execution, cooldown enforcement, audit trail, and edge cases.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from dharma_swarm.dynamic_correction import (
    CorrectionAction,
    CorrectionPolicy,
    DEFAULT_POLICIES,
    DriftSignal,
    DriftType,
    DynamicCorrectionEngine,
)
from dharma_swarm.economic_spine import AgentBudget, EconomicSpine


# ---------------------------------------------------------------------------
# DriftSignal dataclass
# ---------------------------------------------------------------------------


class TestDriftSignal:
    def test_default_creation(self):
        s = DriftSignal(agent_id="a1", drift_type=DriftType.STUCK_AGENT)
        assert s.id  # auto-generated
        assert s.detected_at  # auto-generated
        assert s.resolved is False
        assert s.corrective_action is None

    def test_custom_fields(self):
        s = DriftSignal(
            id="custom-id",
            agent_id="a1",
            drift_type=DriftType.QUALITY_DEGRADATION,
            severity=0.8,
            details="test",
            corrective_action=CorrectionAction.WARN,
        )
        assert s.id == "custom-id"
        assert s.severity == 0.8
        assert s.corrective_action == CorrectionAction.WARN


# ---------------------------------------------------------------------------
# CorrectionPolicy
# ---------------------------------------------------------------------------


class TestCorrectionPolicy:
    def test_default_policies_cover_all_drift_types(self):
        policy_types = {p.drift_type for p in DEFAULT_POLICIES}
        for dt in DriftType:
            assert dt in policy_types

    def test_policy_creation(self):
        p = CorrectionPolicy(
            drift_type=DriftType.STUCK_AGENT,
            severity_thresholds={0.5: CorrectionAction.WARN, 0.9: CorrectionAction.RESTART},
        )
        assert p.drift_type == DriftType.STUCK_AGENT
        assert len(p.severity_thresholds) == 2


# ---------------------------------------------------------------------------
# Drift detectors
# ---------------------------------------------------------------------------


class TestQualityDegradation:
    def test_no_degradation(self):
        engine = DynamicCorrectionEngine()
        sig = engine.detect_quality_degradation("a1", [0.5, 0.6, 0.7, 0.8])
        assert sig is None  # Improving, not degrading

    def test_degradation_detected(self):
        engine = DynamicCorrectionEngine()
        sig = engine.detect_quality_degradation("a1", [0.9, 0.8, 0.5, 0.3])
        assert sig is not None
        assert sig.drift_type == DriftType.QUALITY_DEGRADATION
        assert sig.severity > 0.0

    def test_too_few_scores(self):
        engine = DynamicCorrectionEngine()
        sig = engine.detect_quality_degradation("a1", [0.9, 0.1])
        assert sig is None  # Need at least 3

    def test_flat_scores(self):
        engine = DynamicCorrectionEngine()
        sig = engine.detect_quality_degradation("a1", [0.5, 0.5, 0.5, 0.5])
        assert sig is None

    def test_severe_degradation(self):
        engine = DynamicCorrectionEngine()
        sig = engine.detect_quality_degradation("a1", [0.9, 0.9, 0.1, 0.1])
        assert sig is not None
        assert sig.severity > 0.5


class TestBudgetOverrun:
    def test_no_overrun(self):
        engine = DynamicCorrectionEngine()
        budget = AgentBudget(
            agent_id="a1", total_tokens_allocated=10000, tokens_spent=3000
        )
        sig = engine.detect_budget_overrun("a1", budget)
        assert sig is None  # 30% used, no overrun

    def test_overrun_detected(self):
        engine = DynamicCorrectionEngine()
        budget = AgentBudget(
            agent_id="a1", total_tokens_allocated=10000, tokens_spent=8000
        )
        sig = engine.detect_budget_overrun("a1", budget)
        assert sig is not None
        assert sig.drift_type == DriftType.BUDGET_OVERRUN

    def test_full_budget_used(self):
        engine = DynamicCorrectionEngine()
        budget = AgentBudget(
            agent_id="a1", total_tokens_allocated=10000, tokens_spent=10000
        )
        sig = engine.detect_budget_overrun("a1", budget)
        assert sig is not None
        assert sig.severity > 0.8

    def test_none_budget(self):
        engine = DynamicCorrectionEngine()
        sig = engine.detect_budget_overrun("a1", None)
        assert sig is None


class TestStuckAgent:
    def test_not_stuck(self):
        engine = DynamicCorrectionEngine()
        recent = datetime.now(timezone.utc) - timedelta(seconds=30)
        sig = engine.detect_stuck_agent("a1", recent, timedelta(minutes=1))
        assert sig is None

    def test_stuck_detected(self):
        engine = DynamicCorrectionEngine()
        long_ago = datetime.now(timezone.utc) - timedelta(minutes=10)
        sig = engine.detect_stuck_agent("a1", long_ago, timedelta(minutes=1))
        assert sig is not None
        assert sig.drift_type == DriftType.STUCK_AGENT

    def test_none_last_action(self):
        engine = DynamicCorrectionEngine()
        sig = engine.detect_stuck_agent("a1", None)
        assert sig is None


class TestDharmicDrift:
    def test_good_alignment(self):
        engine = DynamicCorrectionEngine()
        sig = engine.detect_dharmic_drift("a1", 0.85)
        assert sig is None

    def test_low_alignment(self):
        engine = DynamicCorrectionEngine()
        sig = engine.detect_dharmic_drift("a1", 0.3)
        assert sig is not None
        assert sig.drift_type == DriftType.DHARMIC_DRIFT
        assert sig.severity > 0.5

    def test_zero_alignment(self):
        engine = DynamicCorrectionEngine()
        sig = engine.detect_dharmic_drift("a1", 0.0)
        assert sig is not None
        assert sig.severity == pytest.approx(1.0)


class TestLoopDetection:
    def test_no_loop(self):
        engine = DynamicCorrectionEngine()
        sig = engine.detect_loop("a1", ["a", "b", "c", "d", "e"])
        assert sig is None

    def test_loop_detected(self):
        engine = DynamicCorrectionEngine()
        sig = engine.detect_loop("a1", ["a", "a", "a", "a", "a", "b"])
        assert sig is not None
        assert sig.drift_type == DriftType.LOOP_DETECTED

    def test_too_few_actions(self):
        engine = DynamicCorrectionEngine()
        sig = engine.detect_loop("a1", ["a", "a"])
        assert sig is None


class TestErrorCascade:
    def test_no_cascade(self):
        engine = DynamicCorrectionEngine()
        sig = engine.detect_error_cascade("a1", [])
        assert sig is None

    def test_cascade_detected(self):
        engine = DynamicCorrectionEngine()
        errors = [{"error": f"err{i}"} for i in range(5)]
        sig = engine.detect_error_cascade("a1", errors)
        assert sig is not None
        assert sig.drift_type == DriftType.ERROR_CASCADE

    def test_few_errors_below_threshold(self):
        engine = DynamicCorrectionEngine()
        sig = engine.detect_error_cascade("a1", [{"error": "e1"}, {"error": "e2"}])
        assert sig is None  # Need at least 3


# ---------------------------------------------------------------------------
# Policy matching
# ---------------------------------------------------------------------------


class TestPolicyMatching:
    def test_match_low_severity(self):
        engine = DynamicCorrectionEngine()
        signal = DriftSignal(
            agent_id="a1",
            drift_type=DriftType.QUALITY_DEGRADATION,
            severity=0.35,
        )
        action = engine.match_policy(signal)
        assert action == CorrectionAction.WARN

    def test_match_medium_severity(self):
        engine = DynamicCorrectionEngine()
        signal = DriftSignal(
            agent_id="a1",
            drift_type=DriftType.QUALITY_DEGRADATION,
            severity=0.65,
        )
        action = engine.match_policy(signal)
        assert action == CorrectionAction.THROTTLE

    def test_match_high_severity(self):
        engine = DynamicCorrectionEngine()
        signal = DriftSignal(
            agent_id="a1",
            drift_type=DriftType.QUALITY_DEGRADATION,
            severity=0.95,
        )
        action = engine.match_policy(signal)
        assert action == CorrectionAction.REROUTE

    def test_below_all_thresholds(self):
        engine = DynamicCorrectionEngine()
        signal = DriftSignal(
            agent_id="a1",
            drift_type=DriftType.QUALITY_DEGRADATION,
            severity=0.1,
        )
        action = engine.match_policy(signal)
        assert action is None

    def test_unknown_drift_type_no_policy(self):
        engine = DynamicCorrectionEngine(policies=[])
        signal = DriftSignal(
            agent_id="a1",
            drift_type=DriftType.STUCK_AGENT,
            severity=0.9,
        )
        action = engine.match_policy(signal)
        assert action is None


# ---------------------------------------------------------------------------
# Correction execution
# ---------------------------------------------------------------------------


class TestCorrectionExecution:
    def test_warn_action(self):
        engine = DynamicCorrectionEngine()
        signal = DriftSignal(
            agent_id="a1",
            drift_type=DriftType.QUALITY_DEGRADATION,
            severity=0.5,
            corrective_action=CorrectionAction.WARN,
        )
        assert engine.apply_correction(signal) is True

    def test_throttle_reduces_budget(self):
        spine = EconomicSpine()
        spine.get_or_create_budget("a1")
        engine = DynamicCorrectionEngine(economic_spine=spine)
        signal = DriftSignal(
            agent_id="a1",
            drift_type=DriftType.BUDGET_OVERRUN,
            severity=0.7,
            corrective_action=CorrectionAction.THROTTLE,
        )
        engine.apply_correction(signal)
        budget = spine.get_or_create_budget("a1")
        # Budget should be reduced by 20%
        assert budget.total_tokens_allocated < 100000

    def test_escalate_sets_flag(self):
        engine = DynamicCorrectionEngine()
        signal = DriftSignal(
            agent_id="a1",
            drift_type=DriftType.DHARMIC_DRIFT,
            severity=0.8,
            corrective_action=CorrectionAction.ESCALATE,
        )
        engine.apply_correction(signal)
        assert engine.escalation_flag is True

    def test_no_action_returns_false(self):
        engine = DynamicCorrectionEngine()
        signal = DriftSignal(
            agent_id="a1",
            drift_type=DriftType.STUCK_AGENT,
            severity=0.5,
        )
        assert engine.apply_correction(signal) is False


# ---------------------------------------------------------------------------
# Cooldown enforcement
# ---------------------------------------------------------------------------


class TestCooldown:
    def test_cooldown_blocks_rapid_correction(self):
        engine = DynamicCorrectionEngine()
        signal = DriftSignal(
            agent_id="a1",
            drift_type=DriftType.QUALITY_DEGRADATION,
            severity=0.5,
            corrective_action=CorrectionAction.WARN,
        )
        # First correction should succeed
        assert engine.apply_correction(signal) is True
        # Second should be blocked by cooldown
        signal2 = DriftSignal(
            agent_id="a1",
            drift_type=DriftType.QUALITY_DEGRADATION,
            severity=0.5,
            corrective_action=CorrectionAction.WARN,
        )
        assert engine.apply_correction(signal2) is False

    def test_different_agents_no_cooldown_interference(self):
        engine = DynamicCorrectionEngine()
        s1 = DriftSignal(
            agent_id="a1",
            drift_type=DriftType.STUCK_AGENT,
            severity=0.5,
            corrective_action=CorrectionAction.WARN,
        )
        s2 = DriftSignal(
            agent_id="a2",
            drift_type=DriftType.STUCK_AGENT,
            severity=0.5,
            corrective_action=CorrectionAction.WARN,
        )
        assert engine.apply_correction(s1) is True
        assert engine.apply_correction(s2) is True

    def test_different_drift_types_no_cooldown_interference(self):
        engine = DynamicCorrectionEngine()
        s1 = DriftSignal(
            agent_id="a1",
            drift_type=DriftType.QUALITY_DEGRADATION,
            severity=0.5,
            corrective_action=CorrectionAction.WARN,
        )
        s2 = DriftSignal(
            agent_id="a1",
            drift_type=DriftType.STUCK_AGENT,
            severity=0.5,
            corrective_action=CorrectionAction.WARN,
        )
        assert engine.apply_correction(s1) is True
        assert engine.apply_correction(s2) is True


# ---------------------------------------------------------------------------
# End-to-end correction flow
# ---------------------------------------------------------------------------


class TestEndToEndCorrection:
    def test_evaluate_and_correct_no_drift(self):
        engine = DynamicCorrectionEngine()
        signals = engine.evaluate_and_correct("a1", {})
        assert signals == []

    def test_evaluate_and_correct_with_quality_drift(self):
        engine = DynamicCorrectionEngine()
        state = {"recent_quality_scores": [0.9, 0.8, 0.4, 0.2]}
        signals = engine.evaluate_and_correct("a1", state)
        assert len(signals) >= 1
        assert any(s.drift_type == DriftType.QUALITY_DEGRADATION for s in signals)

    def test_evaluate_and_correct_with_budget_overrun(self):
        spine = EconomicSpine()
        b = spine.get_or_create_budget("a1")
        b.tokens_spent = 9000
        b.total_tokens_allocated = 10000
        spine._save_budget(b)

        engine = DynamicCorrectionEngine(economic_spine=spine)
        state = {"budget": b}
        signals = engine.evaluate_and_correct("a1", state)
        assert len(signals) >= 1
        assert any(s.drift_type == DriftType.BUDGET_OVERRUN for s in signals)

    def test_multiple_simultaneous_drifts(self):
        engine = DynamicCorrectionEngine()
        budget = AgentBudget(
            agent_id="a1", total_tokens_allocated=10000, tokens_spent=9500
        )
        state = {
            "recent_quality_scores": [0.9, 0.8, 0.3, 0.1],
            "budget": budget,
            "alignment_score": 0.2,
        }
        signals = engine.evaluate_and_correct("a1", state)
        drift_types = {s.drift_type for s in signals}
        # Should detect multiple types of drift
        assert len(drift_types) >= 2


# ---------------------------------------------------------------------------
# Audit trail & reporting
# ---------------------------------------------------------------------------


class TestAuditTrail:
    def test_correction_persisted(self):
        engine = DynamicCorrectionEngine()
        signal = DriftSignal(
            agent_id="a1",
            drift_type=DriftType.STUCK_AGENT,
            severity=0.7,
            corrective_action=CorrectionAction.RESTART,
        )
        engine.apply_correction(signal)
        history = engine.get_correction_history(agent_id="a1")
        assert len(history) == 1
        assert history[0].drift_type == DriftType.STUCK_AGENT

    def test_correction_history_all_agents(self):
        engine = DynamicCorrectionEngine()
        for agent in ("a1", "a2", "a3"):
            sig = DriftSignal(
                agent_id=agent,
                drift_type=DriftType.QUALITY_DEGRADATION,
                severity=0.5,
                corrective_action=CorrectionAction.WARN,
            )
            engine.apply_correction(sig)
        history = engine.get_correction_history()
        assert len(history) == 3

    def test_swarm_health(self):
        engine = DynamicCorrectionEngine()
        signal = DriftSignal(
            agent_id="a1",
            drift_type=DriftType.ERROR_CASCADE,
            severity=0.7,
            corrective_action=CorrectionAction.REROUTE,
        )
        engine.apply_correction(signal)
        health = engine.get_swarm_health()
        assert health["total_corrections"] == 1
        assert "corrections_by_type" in health
        assert "corrections_by_action" in health

    def test_resolve_signal(self):
        engine = DynamicCorrectionEngine()
        signal = DriftSignal(
            agent_id="a1",
            drift_type=DriftType.STUCK_AGENT,
            severity=0.5,
            corrective_action=CorrectionAction.WARN,
        )
        engine.apply_correction(signal)
        engine._active_signals.append(signal)
        engine.resolve_signal(signal.id)
        # Should be resolved in DB
        history = engine.get_correction_history(agent_id="a1")
        assert len(history) == 1
        assert history[0].resolved is True


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_agent_state(self):
        engine = DynamicCorrectionEngine()
        signals = engine.evaluate_and_correct("a1", {})
        assert signals == []

    def test_close(self):
        engine = DynamicCorrectionEngine()
        engine.close()
        # After close, operations should raise
        with pytest.raises(Exception):
            engine.get_correction_history()

    def test_custom_policies(self):
        custom = [
            CorrectionPolicy(
                drift_type=DriftType.STUCK_AGENT,
                severity_thresholds={0.1: CorrectionAction.EVOLVE},
            ),
        ]
        engine = DynamicCorrectionEngine(policies=custom)
        signal = DriftSignal(
            agent_id="a1",
            drift_type=DriftType.STUCK_AGENT,
            severity=0.2,
        )
        action = engine.match_policy(signal)
        assert action == CorrectionAction.EVOLVE
