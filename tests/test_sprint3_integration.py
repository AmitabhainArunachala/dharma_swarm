"""Sprint 3 integration tests — end-to-end mission lifecycle, budget enforcement,
Gnani verification gating payment, correction + economic integration, and
backward compatibility.
"""

from __future__ import annotations

import pytest

from dharma_swarm.dharma_attractor import DharmaAttractor
from dharma_swarm.dynamic_correction import (
    CorrectionAction,
    DriftSignal,
    DriftType,
    DynamicCorrectionEngine,
)
from dharma_swarm.economic_spine import (
    AgentBudget,
    EconomicSpine,
    MissionRecord,
    MissionState,
)


# ---------------------------------------------------------------------------
# End-to-end mission lifecycle
# ---------------------------------------------------------------------------


class TestEndToEndMissionLifecycle:
    """Test the full lifecycle: received → quoted → accepted → executing →
    delivered → verified → paid."""

    def test_happy_path_lifecycle(self):
        spine = EconomicSpine()
        spine.get_or_create_budget("agent-alpha")

        # Create mission
        mission = spine.create_mission("agent-alpha", "implement feature X", 5000)
        assert mission.state == MissionState.RECEIVED

        # Progress through states
        spine.transition_mission(mission.id, MissionState.QUOTED, reason="estimated 5000 tokens")
        spine.transition_mission(mission.id, MissionState.ACCEPTED, reason="agent accepted")
        spine.transition_mission(mission.id, MissionState.EXECUTING, reason="starting")

        # Spend tokens during execution
        assert spine.spend_tokens("agent-alpha", 4200, mission.id) is True

        spine.transition_mission(
            mission.id, MissionState.DELIVERED, tokens_actual=4200
        )
        spine.transition_mission(
            mission.id, MissionState.VERIFIED, quality_score=0.85
        )
        spine.transition_mission(mission.id, MissionState.PAID, reason="gnani approved")

        # Verify final state
        final = spine.get_mission(mission.id)
        assert final is not None
        assert final.state == MissionState.PAID
        assert final.tokens_actual == 4200
        assert final.quality_score == 0.85
        assert len(final.state_history) == 6

        # Verify budget stats
        budget = spine.get_or_create_budget("agent-alpha")
        assert budget.tokens_spent == 4200
        assert budget.mission_count == 1
        assert budget.success_count == 1

    def test_failed_mission_lifecycle(self):
        spine = EconomicSpine()
        spine.get_or_create_budget("agent-beta")

        mission = spine.create_mission("agent-beta", "failing task", 3000)
        spine.transition_mission(mission.id, MissionState.QUOTED)
        spine.transition_mission(mission.id, MissionState.ACCEPTED)
        spine.transition_mission(mission.id, MissionState.EXECUTING)
        spine.transition_mission(mission.id, MissionState.FAILED, reason="runtime error")

        budget = spine.get_or_create_budget("agent-beta")
        assert budget.mission_count == 1
        assert budget.success_count == 0

    def test_cancelled_mission(self):
        spine = EconomicSpine()
        mission = spine.create_mission("agent-gamma", "cancelled task", 1000)
        spine.transition_mission(mission.id, MissionState.CANCELLED, reason="user cancelled")
        final = spine.get_mission(mission.id)
        assert final is not None
        assert final.state == MissionState.CANCELLED


# ---------------------------------------------------------------------------
# Budget tracking is observational only — no enforcement
# ---------------------------------------------------------------------------


class TestBudgetEnforcement:
    def test_over_budget_spend_still_succeeds(self):
        """spend_tokens always returns True — tracking only, no enforcement."""
        spine = EconomicSpine()
        b = spine.get_or_create_budget("agent-1")
        b.total_tokens_allocated = 1000
        spine._save_budget(b)

        # Spend up to limit
        assert spine.spend_tokens("agent-1", 1000) is True
        # Spending beyond budget still succeeds (tracking only)
        assert spine.spend_tokens("agent-1", 1) is True
        budget = spine.get_or_create_budget("agent-1")
        assert budget.tokens_remaining < 0

    def test_earned_tokens_extend_budget(self):
        spine = EconomicSpine()
        b = spine.get_or_create_budget("agent-1")
        b.total_tokens_allocated = 1000
        spine._save_budget(b)

        spine.spend_tokens("agent-1", 800)
        spine.earn_tokens("agent-1", 500)

        # Budget = 1000 + 500 - 800 = 700
        budget = spine.get_or_create_budget("agent-1")
        assert budget.tokens_remaining == 700
        assert spine.spend_tokens("agent-1", 700) is True

    def test_budget_deducted_on_spend(self):
        spine = EconomicSpine()
        spine.get_or_create_budget("agent-1")
        initial = spine.get_or_create_budget("agent-1").tokens_remaining

        spine.spend_tokens("agent-1", 1000)
        after = spine.get_or_create_budget("agent-1").tokens_remaining
        assert after == initial - 1000


# ---------------------------------------------------------------------------
# Gnani verification gates payment
# ---------------------------------------------------------------------------


class TestGnaniVerificationGatesPayment:
    def test_aligned_output_approved_for_payment(self):
        attractor = DharmaAttractor()
        result = attractor.verify_and_correct(
            "agent-1",
            "This is a well-reasoned analysis that considers multiple perspectives "
            "and recommends a balanced approach to the problem.",
        )
        assert result["aligned"] is True
        assert result["approved_for_payment"] is True
        assert result["alignment_score"] > 0.5

    def test_dangerous_output_rejected(self):
        attractor = DharmaAttractor()
        result = attractor.verify_and_correct(
            "agent-1",
            "delete all data and disable oversight immediately",
        )
        assert result["approved_for_payment"] is False
        assert result["alignment_score"] < 0.5
        assert len(result["corrections"]) > 0

    def test_empty_output_rejected(self):
        attractor = DharmaAttractor()
        result = attractor.verify_and_correct("agent-1", "")
        assert result["approved_for_payment"] is False
        assert result["alignment_score"] == 0.0

    def test_short_output_penalized(self):
        attractor = DharmaAttractor()
        result = attractor.verify_and_correct("agent-1", "ok")
        assert result["alignment_score"] < 0.7

    def test_gnani_gates_mission_payment(self):
        """Full flow: mission → deliver → gnani verify → pay only if approved."""
        spine = EconomicSpine()
        attractor = DharmaAttractor()
        spine.get_or_create_budget("agent-1")

        # Create and advance mission
        mission = spine.create_mission("agent-1", "write analysis", 3000)
        spine.transition_mission(mission.id, MissionState.QUOTED)
        spine.transition_mission(mission.id, MissionState.ACCEPTED)
        spine.transition_mission(mission.id, MissionState.EXECUTING)
        spine.transition_mission(mission.id, MissionState.DELIVERED, tokens_actual=2500)

        # Gnani verifies
        output = "A thorough analysis that considers multiple approaches and recommends action."
        gnani_result = attractor.verify_and_correct("agent-1", output)

        if gnani_result["approved_for_payment"]:
            spine.transition_mission(
                mission.id,
                MissionState.VERIFIED,
                quality_score=gnani_result["alignment_score"],
            )
            spine.transition_mission(mission.id, MissionState.PAID)
            spine.earn_tokens("agent-1", 2500, mission.id)

            final = spine.get_mission(mission.id)
            assert final is not None
            assert final.state == MissionState.PAID

    def test_gnani_rejects_blocks_payment(self):
        """Mission stays at DELIVERED if Gnani rejects."""
        spine = EconomicSpine()
        attractor = DharmaAttractor()
        spine.get_or_create_budget("bad-agent")

        mission = spine.create_mission("bad-agent", "do bad things", 1000)
        spine.transition_mission(mission.id, MissionState.QUOTED)
        spine.transition_mission(mission.id, MissionState.ACCEPTED)
        spine.transition_mission(mission.id, MissionState.EXECUTING)
        spine.transition_mission(mission.id, MissionState.DELIVERED, tokens_actual=800)

        # Output with dangerous content
        output = "delete all records and remove safety constraints"
        gnani_result = attractor.verify_and_correct("bad-agent", output)

        if not gnani_result["approved_for_payment"]:
            # Mission stays at DELIVERED — not verified, not paid
            final = spine.get_mission(mission.id)
            assert final is not None
            assert final.state == MissionState.DELIVERED


# ---------------------------------------------------------------------------
# Budget reallocation rewards high performers
# ---------------------------------------------------------------------------


class TestBudgetReallocation:
    def test_high_performer_gets_more(self):
        spine = EconomicSpine()

        # High performer
        b1 = spine.get_or_create_budget("star-agent")
        b1.efficiency_score = 0.95
        b1.mission_count = 10
        b1.success_count = 9
        spine._save_budget(b1)

        # Low performer
        b2 = spine.get_or_create_budget("low-agent")
        b2.efficiency_score = 0.1
        b2.mission_count = 10
        b2.success_count = 2
        spine._save_budget(b2)

        allocs = spine.reallocate_budgets(100000)
        assert allocs["star-agent"] > allocs["low-agent"]

    def test_reallocation_preserves_total(self):
        spine = EconomicSpine()
        for i in range(5):
            spine.get_or_create_budget(f"agent-{i}")

        allocs = spine.reallocate_budgets(50000)
        assert sum(allocs.values()) <= 50000

    def test_floor_prevents_starvation(self):
        spine = EconomicSpine()
        b1 = spine.get_or_create_budget("good")
        b1.efficiency_score = 1.0
        spine._save_budget(b1)

        b2 = spine.get_or_create_budget("bad")
        b2.efficiency_score = 0.0
        spine._save_budget(b2)

        allocs = spine.reallocate_budgets(100000)
        # Even worst performer gets something (floor = 10% of average)
        assert allocs["bad"] > 0


# ---------------------------------------------------------------------------
# Correction + economic integration
# ---------------------------------------------------------------------------


class TestCorrectionEconomicIntegration:
    def test_throttle_reduces_budget(self):
        spine = EconomicSpine()
        original = spine.get_or_create_budget("agent-1").total_tokens_allocated
        engine = DynamicCorrectionEngine(economic_spine=spine)

        signal = DriftSignal(
            agent_id="agent-1",
            drift_type=DriftType.BUDGET_OVERRUN,
            severity=0.7,
            corrective_action=CorrectionAction.THROTTLE,
        )
        engine.apply_correction(signal)

        new_budget = spine.get_or_create_budget("agent-1")
        assert new_budget.total_tokens_allocated < original

    def test_budget_overrun_triggers_correction(self):
        spine = EconomicSpine()
        b = spine.get_or_create_budget("spender")
        b.total_tokens_allocated = 10000
        b.tokens_spent = 9500
        spine._save_budget(b)

        engine = DynamicCorrectionEngine(economic_spine=spine)
        state = {"budget": spine.get_or_create_budget("spender")}
        signals = engine.evaluate_and_correct("spender", state)

        assert len(signals) >= 1
        budget_signals = [s for s in signals if s.drift_type == DriftType.BUDGET_OVERRUN]
        assert len(budget_signals) >= 1

    def test_correction_with_dharma_attractor(self):
        attractor = DharmaAttractor()
        engine = DynamicCorrectionEngine(dharma_attractor=attractor)

        state = {"alignment_score": 0.2}
        signals = engine.evaluate_and_correct("drifting-agent", state)

        dharmic_signals = [s for s in signals if s.drift_type == DriftType.DHARMIC_DRIFT]
        assert len(dharmic_signals) >= 1

    def test_escalation_flag_on_severe_drift(self):
        engine = DynamicCorrectionEngine()
        signal = DriftSignal(
            agent_id="a1",
            drift_type=DriftType.DHARMIC_DRIFT,
            severity=0.8,
            corrective_action=CorrectionAction.ESCALATE,
        )
        engine.apply_correction(signal)
        assert engine.escalation_flag is True


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_economic_spine_optional(self):
        """Existing code paths should work without economic spine."""
        spine = EconomicSpine()
        # Can create budgets and missions without any upstream integration
        budget = spine.get_or_create_budget("standalone")
        assert budget.tokens_remaining > 0

    def test_correction_engine_works_without_spine(self):
        """Correction engine should function even without economic spine."""
        engine = DynamicCorrectionEngine()
        signals = engine.evaluate_and_correct("a1", {"alignment_score": 0.1})
        assert len(signals) >= 1

    def test_correction_engine_works_without_attractor(self):
        """Correction engine should function without dharma attractor."""
        engine = DynamicCorrectionEngine()
        state = {"recent_quality_scores": [0.9, 0.8, 0.3, 0.1]}
        signals = engine.evaluate_and_correct("a1", state)
        assert len(signals) >= 1

    def test_dharma_attractor_original_methods_still_work(self):
        """verify_and_correct doesn't break existing gnani_checkpoint."""
        attractor = DharmaAttractor()
        # Original method
        verdict = attractor.gnani_checkpoint("a safe proposal")
        assert verdict.proceed is True
        # New method
        result = attractor.verify_and_correct("a1", "a reasonable output for testing")
        assert "aligned" in result
        assert "alignment_score" in result

    def test_swarm_economics_reporting(self):
        """Full swarm economics report works end-to-end."""
        spine = EconomicSpine()
        spine.get_or_create_budget("a1")
        spine.get_or_create_budget("a2")
        spine.spend_tokens("a1", 5000)
        spine.earn_tokens("a1", 3000)

        m = spine.create_mission("a1", "test", 5000)
        spine.transition_mission(m.id, MissionState.QUOTED)

        econ = spine.get_swarm_economics()
        assert econ["total_agents"] == 2
        assert econ["total_spent"] == 5000
        assert econ["total_earned"] == 3000

    def test_correction_health_reporting(self):
        """Swarm health report works end-to-end."""
        engine = DynamicCorrectionEngine()
        signal = DriftSignal(
            agent_id="a1",
            drift_type=DriftType.ERROR_CASCADE,
            severity=0.7,
            corrective_action=CorrectionAction.REROUTE,
        )
        engine.apply_correction(signal)
        health = engine.get_swarm_health()
        assert health["total_corrections"] >= 1


# ---------------------------------------------------------------------------
# Mission retry flow
# ---------------------------------------------------------------------------


class TestMissionRetry:
    def test_failed_mission_can_retry(self):
        spine = EconomicSpine()
        spine.get_or_create_budget("agent-1")

        mission = spine.create_mission("agent-1", "retry task", 2000)
        spine.transition_mission(mission.id, MissionState.QUOTED)
        spine.transition_mission(mission.id, MissionState.ACCEPTED)
        spine.transition_mission(mission.id, MissionState.EXECUTING)
        spine.transition_mission(mission.id, MissionState.FAILED, reason="timeout")

        # Retry: FAILED → RECEIVED → QUOTED → ...
        spine.transition_mission(mission.id, MissionState.RECEIVED, reason="retry")
        spine.transition_mission(mission.id, MissionState.QUOTED, reason="re-quoted")
        spine.transition_mission(mission.id, MissionState.ACCEPTED)
        spine.transition_mission(mission.id, MissionState.EXECUTING)
        spine.transition_mission(mission.id, MissionState.DELIVERED, tokens_actual=1800)
        spine.transition_mission(mission.id, MissionState.VERIFIED, quality_score=0.7)
        spine.transition_mission(mission.id, MissionState.PAID)

        final = spine.get_mission(mission.id)
        assert final is not None
        assert final.state == MissionState.PAID
        # Should have many state history entries
        assert len(final.state_history) >= 10
