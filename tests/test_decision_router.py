from __future__ import annotations

from dharma_swarm.decision_router import (
    CollaborationMode,
    DecisionInput,
    DecisionRouter,
    RoutePath,
)


def test_reflex_path_for_low_risk_low_uncertainty() -> None:
    router = DecisionRouter()
    decision = router.route(
        DecisionInput(
            action_name="append_memory",
            risk_score=0.08,
            uncertainty=0.12,
            novelty=0.10,
            urgency=0.6,
            expected_impact=0.15,
            estimated_latency_ms=120,
            estimated_tokens=220,
        )
    )
    assert decision.path == RoutePath.REFLEX
    assert decision.requires_human is False


def test_deliberative_path_for_medium_risk() -> None:
    router = DecisionRouter()
    decision = router.route(
        DecisionInput(
            action_name="synthesize_plan",
            risk_score=0.40,
            uncertainty=0.35,
            novelty=0.55,
            urgency=0.5,
            expected_impact=0.5,
            estimated_latency_ms=1200,
            estimated_tokens=1800,
        )
    )
    assert decision.path == RoutePath.DELIBERATIVE
    assert "default_to_deliberative" in decision.reasons


def test_escalate_for_high_risk() -> None:
    router = DecisionRouter()
    decision = router.route(
        DecisionInput(
            action_name="system_mutation",
            risk_score=0.95,
            uncertainty=0.20,
            novelty=0.30,
            urgency=0.4,
            expected_impact=0.7,
        )
    )
    assert decision.path == RoutePath.ESCALATE
    assert decision.requires_human is True


def test_escalate_for_privileged_without_consent() -> None:
    router = DecisionRouter()
    decision = router.route(
        DecisionInput(
            action_name="write_protected_config",
            risk_score=0.2,
            uncertainty=0.2,
            novelty=0.2,
            urgency=0.8,
            expected_impact=0.6,
            privileged_action=True,
            requires_human_consent=False,
        )
    )
    assert decision.path == RoutePath.ESCALATE
    assert "privileged_without_consent" in decision.reasons


def test_explicit_confidence_overrides_calibration() -> None:
    router = DecisionRouter()
    item = DecisionInput(
        action_name="small_action",
        risk_score=0.7,
        uncertainty=0.6,
        novelty=0.5,
        urgency=0.2,
        expected_impact=0.3,
        explicit_confidence=0.93,
    )
    confidence = router.calibrate_confidence(item)
    assert abs(confidence - 0.93) < 1e-6


def test_collaboration_router_keeps_simple_low_risk_single_agent() -> None:
    router = DecisionRouter()
    decision = router.route_collaboration(
        DecisionInput(
            action_name="summarize_logs",
            risk_score=0.08,
            uncertainty=0.10,
            novelty=0.12,
            urgency=0.2,
            expected_impact=0.2,
            context={"complexity_score": 0.10},
        )
    )

    assert decision.mode == CollaborationMode.SINGLE_AGENT
    assert "simple_request_single_agent" in decision.reasons


def test_collaboration_router_fans_out_broad_domain_reasoning_task() -> None:
    router = DecisionRouter()
    decision = router.route_collaboration(
        DecisionInput(
            action_name="design_research",
            risk_score=0.30,
            uncertainty=0.48,
            novelty=0.52,
            urgency=0.55,
            expected_impact=0.60,
            context={
                "complexity_score": 0.72,
                "reasoning_markers": 2,
                "has_multi_step": True,
                "broad_domain": True,
                "requires_verification": True,
                "domain_count": 3,
            },
        )
    )

    assert decision.mode == CollaborationMode.MULTI_AGENT
    assert "collaboration_score>=0.58" in decision.reasons


def test_collaboration_router_keeps_sequential_reasoning_single_agent() -> None:
    router = DecisionRouter()
    decision = router.route_collaboration(
        DecisionInput(
            action_name="proof_sketch",
            risk_score=0.25,
            uncertainty=0.45,
            novelty=0.30,
            urgency=0.3,
            expected_impact=0.50,
            context={
                "complexity_score": 0.74,
                "reasoning_markers": 3,
                "sequential_reasoning_only": True,
            },
        )
    )

    assert decision.mode == CollaborationMode.SINGLE_AGENT
    assert "sequential_reasoning_prefers_single_agent" in decision.reasons
