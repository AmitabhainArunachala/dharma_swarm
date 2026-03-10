"""Tests for Darwin execution profiles and promotion ladders."""

from dharma_swarm.execution_profile import (
    EvidenceTier,
    ExecutionProfileRegistry,
    PromotionState,
    derive_promotion_state,
)


def test_derive_promotion_state_follows_evidence_ladder():
    assert (
        derive_promotion_state(evidence_tier=EvidenceTier.PROBE, pass_rate=1.0)
        == PromotionState.PROBE_PASS
    )
    assert (
        derive_promotion_state(evidence_tier=EvidenceTier.COMPONENT, pass_rate=1.0)
        == PromotionState.COMPONENT_PASS
    )
    assert (
        derive_promotion_state(evidence_tier=EvidenceTier.SYSTEM, pass_rate=1.0)
        == PromotionState.SYSTEM_PASS
    )
    assert (
        derive_promotion_state(evidence_tier=EvidenceTier.LOCAL, pass_rate=0.5)
        == PromotionState.CANDIDATE
    )


def test_execution_profile_registry_resolves_richer_profile(tmp_path):
    registry = ExecutionProfileRegistry.from_configs(
        [
            {
                "name": "pkg-profile",
                "component_pattern": "pkg/*.py",
                "workspace": tmp_path / "pkg",
                "test_command": "python3 -m pytest tests/test_pkg.py -q",
                "timeout": 7.0,
                "risk_level": "low",
                "expected_metrics": ["pass_rate", "latency_ms"],
                "rollback_policy": "git_restore",
                "evidence_tier": "component",
            }
        ]
    )

    resolved = registry.resolve("pkg/example.py")

    assert resolved is not None
    assert resolved.profile_name == "pkg-profile"
    assert resolved.workspace == (tmp_path / "pkg").resolve()
    assert resolved.risk_level == "low"
    assert resolved.expected_metrics == ["pass_rate", "latency_ms"]
    assert resolved.rollback_policy == "git_restore"
    assert resolved.evidence_tier == EvidenceTier.COMPONENT
