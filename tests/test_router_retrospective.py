"""Tests for router_retrospective.py — router retrospectives and drift guards."""

from __future__ import annotations

import pytest

from dharma_swarm.router_retrospective import (
    DriftGuardDecision,
    DriftGuardThresholds,
    RouteOutcomeRecord,
    RoutePolicyArchiveEntry,
    RouteRetrospectiveArtifact,
    _clamp01,
    build_route_policy_archive_entry,
    build_route_retrospective,
    evaluate_router_drift,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestClamp01:
    def test_within_range(self):
        assert _clamp01(0.5) == 0.5

    def test_below_zero(self):
        assert _clamp01(-0.5) == 0.0

    def test_above_one(self):
        assert _clamp01(1.5) == 1.0

    def test_boundaries(self):
        assert _clamp01(0.0) == 0.0
        assert _clamp01(1.0) == 1.0


# ---------------------------------------------------------------------------
# RouteOutcomeRecord
# ---------------------------------------------------------------------------


class TestRouteOutcomeRecord:
    def test_construction(self):
        r = RouteOutcomeRecord(
            action_name="test",
            route_path="reflex",
            selected_provider="anthropic",
            confidence=0.9,
        )
        assert r.action_name == "test"
        assert r.result == "success"

    def test_confidence_clamped(self):
        r = RouteOutcomeRecord(
            action_name="x",
            route_path="y",
            selected_provider="z",
            confidence=1.5,
        )
        assert r.confidence == 1.0

    def test_quality_score_clamped(self):
        r = RouteOutcomeRecord(
            action_name="x",
            route_path="y",
            selected_provider="z",
            confidence=0.5,
            quality_score=-0.3,
        )
        assert r.quality_score == 0.0

    def test_effective_quality_from_score(self):
        r = RouteOutcomeRecord(
            action_name="x",
            route_path="y",
            selected_provider="z",
            confidence=0.5,
            quality_score=0.8,
        )
        assert r.effective_quality == 0.8

    def test_effective_quality_success_no_score(self):
        r = RouteOutcomeRecord(
            action_name="x",
            route_path="y",
            selected_provider="z",
            confidence=0.5,
        )
        assert r.effective_quality == 1.0

    def test_effective_quality_failure_no_score(self):
        r = RouteOutcomeRecord(
            action_name="x",
            route_path="y",
            selected_provider="z",
            confidence=0.5,
            result="failure",
        )
        assert r.effective_quality == 0.0


# ---------------------------------------------------------------------------
# build_route_retrospective
# ---------------------------------------------------------------------------


class TestBuildRouteRetrospective:
    def _make_record(self, confidence=0.9, quality=0.3, **kwargs):
        return RouteOutcomeRecord(
            action_name="test_action",
            route_path="reflex",
            selected_provider="anthropic",
            selected_model="claude-3",
            confidence=confidence,
            quality_score=quality,
            **kwargs,
        )

    def test_returns_none_low_confidence(self):
        record = self._make_record(confidence=0.5, quality=0.3)
        assert build_route_retrospective(record) is None

    def test_returns_none_high_quality(self):
        record = self._make_record(confidence=0.9, quality=0.9)
        assert build_route_retrospective(record) is None

    def test_returns_artifact_high_confidence_low_quality(self):
        record = self._make_record(confidence=0.9, quality=0.5)
        result = build_route_retrospective(record)
        assert result is not None
        assert isinstance(result, RouteRetrospectiveArtifact)
        assert result.severity == "review"
        assert len(result.recommended_actions) > 0

    def test_critical_severity(self):
        record = self._make_record(confidence=0.95, quality=0.2)
        result = build_route_retrospective(record)
        assert result is not None
        assert result.severity == "critical"

    def test_reflex_complex_action(self):
        record = self._make_record(
            confidence=0.9,
            quality=0.3,
            signals={"complexity_tier": "complex"},
        )
        result = build_route_retrospective(record)
        assert result is not None
        assert any("reflex-to-deliberative" in a for a in result.recommended_actions)

    def test_failure_action(self):
        record = self._make_record(
            confidence=0.9,
            quality=0.3,
            failures=[{"error": "timeout"}],
        )
        result = build_route_retrospective(record)
        assert result is not None
        assert any("shadow mode" in a for a in result.recommended_actions)

    def test_multilingual_action(self):
        record = self._make_record(
            confidence=0.9,
            quality=0.3,
            signals={"language_code": "ja"},
        )
        result = build_route_retrospective(record)
        assert result is not None
        assert any("multilingual" in a for a in result.recommended_actions)

    def test_hypothesis_format(self):
        record = self._make_record(confidence=0.85, quality=0.5)
        result = build_route_retrospective(record)
        assert result is not None
        assert "reflex" in result.hypothesis
        assert "0.85" in result.hypothesis

    def test_policy_entry_fields(self):
        record = self._make_record(confidence=0.9, quality=0.4)
        result = build_route_retrospective(record)
        assert result is not None
        pe = result.policy_archive_entry
        assert pe.shadow_mode_required is True
        assert pe.promotion_state == "candidate"
        assert "test_action" in pe.change_summary


# ---------------------------------------------------------------------------
# build_route_policy_archive_entry
# ---------------------------------------------------------------------------


class TestBuildRoutePolicyArchiveEntry:
    def test_produces_archive_entry(self):
        record = RouteOutcomeRecord(
            action_name="test",
            route_path="reflex",
            selected_provider="anthropic",
            confidence=0.9,
            quality_score=0.3,
        )
        artifact = build_route_retrospective(record)
        assert artifact is not None
        entry = build_route_policy_archive_entry(artifact)
        assert entry.component == "router_policy_review"
        assert entry.change_type == "route_retrospective"
        assert "RETROSPECTIVE_AUDIT" in entry.gates_passed


# ---------------------------------------------------------------------------
# evaluate_router_drift
# ---------------------------------------------------------------------------


class TestEvaluateRouterDrift:
    def test_safe_promotion(self):
        d = evaluate_router_drift(
            goal_drift_index=0.1,
            constraint_preservation=0.999,
        )
        assert d.allow_promotion is True
        assert "promotion_safe" in d.reasons

    def test_drift_blocks_promotion(self):
        d = evaluate_router_drift(
            goal_drift_index=0.5,  # above 0.44 threshold
            constraint_preservation=0.999,
        )
        assert d.allow_promotion is False
        assert any("goal_drift_index" in r for r in d.reasons)

    def test_constraint_violation_blocks(self):
        d = evaluate_router_drift(
            goal_drift_index=0.1,
            constraint_preservation=0.95,  # below 0.987
        )
        assert d.allow_promotion is False
        assert any("constraint_preservation" in r for r in d.reasons)

    def test_both_violations(self):
        d = evaluate_router_drift(
            goal_drift_index=0.6,
            constraint_preservation=0.9,
        )
        assert d.allow_promotion is False
        assert len(d.reasons) == 2

    def test_custom_thresholds(self):
        thresholds = DriftGuardThresholds(
            goal_drift_index_critical=0.8,
            constraint_preservation_floor=0.5,
        )
        d = evaluate_router_drift(
            goal_drift_index=0.6,
            constraint_preservation=0.7,
            thresholds=thresholds,
        )
        assert d.allow_promotion is True

    def test_values_clamped(self):
        d = evaluate_router_drift(
            goal_drift_index=1.5,
            constraint_preservation=-0.1,
        )
        assert d.goal_drift_index == 1.0
        assert d.constraint_preservation == 0.0


# ---------------------------------------------------------------------------
# DriftGuardThresholds
# ---------------------------------------------------------------------------


class TestDriftGuardThresholds:
    def test_defaults(self):
        t = DriftGuardThresholds()
        assert t.goal_drift_index_critical == 0.44
        assert t.constraint_preservation_floor == 0.987
