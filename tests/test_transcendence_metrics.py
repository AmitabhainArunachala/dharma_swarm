"""Tests for transcendence_metrics.py — pure metric functions."""

import pytest

from dharma_swarm.transcendence_metrics import (
    aggregation_lift,
    behavioral_diversity,
    brier_aggregation_lift,
    brier_transcendence_margin,
    diversity_health,
    error_decorrelation,
    krogh_vedelsby_diversity,
    transcendence_margin,
)


class TestBehavioralDiversity:
    def test_identical_outputs(self):
        assert behavioral_diversity(["hello world", "hello world"]) == 0.0

    def test_completely_different(self):
        d = behavioral_diversity(["alpha beta", "gamma delta"])
        assert d == 1.0

    def test_partial_overlap(self):
        d = behavioral_diversity(["the cat sat", "the dog sat"])
        assert 0.0 < d < 1.0

    def test_single_output(self):
        assert behavioral_diversity(["only one"]) == 0.0

    def test_empty(self):
        assert behavioral_diversity([]) == 0.0

    def test_three_outputs(self):
        d = behavioral_diversity(["a b c", "a b d", "a e f"])
        assert 0.0 < d < 1.0


class TestErrorDecorrelation:
    def test_identical_errors(self):
        # All agents have the same error — perfectly correlated
        d = error_decorrelation([0.3, 0.3, 0.3])
        assert d == 0.0

    def test_varied_errors(self):
        # Agents have different errors — decorrelated
        d = error_decorrelation([0.1, 0.5, 0.9])
        assert d > 0.0

    def test_single_agent(self):
        assert error_decorrelation([0.5]) == 0.0

    def test_zero_errors(self):
        assert error_decorrelation([0.0, 0.0]) == 1.0


class TestKroghVedelsbyDiversity:
    def test_positive_diversity(self):
        # Individual errors: [0.3, 0.5, 0.7], mean = 0.5
        # Ensemble error: 0.2 (ensemble is better)
        # Diversity term: 0.5 - 0.2 = 0.3
        kv = krogh_vedelsby_diversity([0.3, 0.5, 0.7], 0.2)
        assert abs(kv - 0.3) < 1e-10

    def test_zero_diversity(self):
        # Ensemble equals mean individual — no diversity benefit
        kv = krogh_vedelsby_diversity([0.5, 0.5], 0.5)
        assert kv == 0.0

    def test_negative_diversity(self):
        # Ensemble WORSE than mean — aggregation is hurting
        kv = krogh_vedelsby_diversity([0.3, 0.3], 0.5)
        assert kv < 0.0

    def test_empty(self):
        assert krogh_vedelsby_diversity([], 0.5) == 0.0


class TestTranscendenceMargin:
    def test_positive_margin(self):
        # Ensemble (0.9) beats best individual (0.8)
        assert transcendence_margin(0.9, 0.8) == pytest.approx(0.1)

    def test_negative_margin(self):
        # Ensemble (0.7) loses to best individual (0.8)
        assert transcendence_margin(0.7, 0.8) == pytest.approx(-0.1)

    def test_zero_margin(self):
        assert transcendence_margin(0.8, 0.8) == 0.0


class TestBrierTranscendenceMargin:
    def test_ensemble_wins(self):
        # Ensemble Brier 0.1 < best individual Brier 0.15 (lower is better)
        m = brier_transcendence_margin(0.1, 0.15)
        assert m == pytest.approx(0.05)

    def test_ensemble_loses(self):
        m = brier_transcendence_margin(0.2, 0.15)
        assert m == pytest.approx(-0.05)


class TestAggregationLift:
    def test_positive_lift(self):
        assert aggregation_lift(0.9, 0.7) == pytest.approx(0.2)

    def test_negative_lift(self):
        assert aggregation_lift(0.5, 0.7) == pytest.approx(-0.2)


class TestBrierAggregationLift:
    def test_positive_lift(self):
        m = brier_aggregation_lift(0.1, 0.2)
        assert m == pytest.approx(0.1)


class TestDiversityHealth:
    def test_healthy(self):
        h = diversity_health(0.8, 0.7, 0.6)
        assert h["status"] == "healthy"
        assert float(h["composite"]) > 0.5

    def test_critical(self):
        h = diversity_health(0.1, 0.1, 0.0)
        assert h["status"] == "critical"
        assert float(h["composite"]) < 0.25

    def test_degraded(self):
        h = diversity_health(0.4, 0.3, 0.2)
        assert h["status"] == "degraded"
