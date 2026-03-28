"""Tests for transcendence_aggregation.py — pure aggregation functions."""

import pytest

from dharma_swarm.transcendence_aggregation import (
    inverse_brier_weights,
    majority_vote,
    quality_weighted_average,
    softmax_select,
    temperature_concentrate,
)


class TestMajorityVote:
    def test_unanimous(self):
        winner, share = majority_vote(["yes", "yes", "yes"])
        assert winner == "yes"
        assert share == 1.0

    def test_simple_majority(self):
        winner, share = majority_vote(["yes", "yes", "no"])
        assert winner == "yes"
        assert share == pytest.approx(2.0 / 3.0)

    def test_weighted_vote(self):
        # "no" has higher total weight despite fewer votes
        winner, share = majority_vote(
            ["yes", "no", "no"],
            weights=[0.1, 0.5, 0.5],
        )
        assert winner == "no"

    def test_empty(self):
        winner, share = majority_vote([])
        assert winner == ""

    def test_single(self):
        winner, share = majority_vote(["only"])
        assert winner == "only"
        assert share == 1.0

    def test_tie_broken_by_iteration(self):
        winner, _ = majority_vote(["a", "b"])
        assert winner in ("a", "b")


class TestQualityWeightedAverage:
    def test_uniform_weights(self):
        avg = quality_weighted_average([0.6, 0.7, 0.8])
        assert avg == pytest.approx(0.7)

    def test_weighted(self):
        # Agent with score 0.8 (quality=0.9) dominates
        avg = quality_weighted_average([0.3, 0.8], [0.1, 0.9])
        assert avg > 0.5

    def test_empty(self):
        assert quality_weighted_average([]) == 0.5

    def test_clamped(self):
        # Even with extreme weights, result stays in [0, 1]
        avg = quality_weighted_average([0.99, 0.99], [100.0, 100.0])
        assert 0.0 <= avg <= 1.0

    def test_zero_weights(self):
        avg = quality_weighted_average([0.3, 0.7], [0.0, 0.0])
        assert avg == pytest.approx(0.5)


class TestTemperatureConcentrate:
    def test_moderate_concentration(self):
        # Three agents lean toward "yes" (>0.5)
        result = temperature_concentrate([0.6, 0.65, 0.7], temperature=0.5)
        # Should be pushed beyond the average (0.65) toward 1.0
        assert result > 0.65

    def test_high_temperature_no_change(self):
        # Very high temp = no concentration
        result = temperature_concentrate([0.6, 0.7], temperature=10.0)
        assert result == pytest.approx(0.65, abs=0.01)

    def test_zero_temperature_hard_decision(self):
        # Zero temp = argmax
        result = temperature_concentrate([0.6, 0.7], temperature=0.0)
        assert result == 1.0

    def test_below_half_concentrates_down(self):
        result = temperature_concentrate([0.3, 0.35, 0.4], temperature=0.5)
        assert result < 0.35

    def test_empty(self):
        assert temperature_concentrate([]) == 0.5

    def test_preserves_midpoint(self):
        result = temperature_concentrate([0.5, 0.5], temperature=0.5)
        assert abs(result - 0.5) < 0.01


class TestSoftmaxSelect:
    def test_uniform_scores(self):
        weights = softmax_select([1.0, 1.0, 1.0])
        assert len(weights) == 3
        assert all(abs(w - 1.0 / 3.0) < 0.01 for w in weights)

    def test_low_temperature_concentrates(self):
        weights = softmax_select([0.5, 1.0, 0.5], temperature=0.1)
        # Almost all weight on index 1
        assert weights[1] > 0.9

    def test_sums_to_one(self):
        weights = softmax_select([0.3, 0.7, 0.5])
        assert abs(sum(weights) - 1.0) < 1e-6

    def test_zero_temperature(self):
        weights = softmax_select([0.1, 0.9, 0.5], temperature=0.0)
        assert weights[1] == 1.0
        assert weights[0] == 0.0

    def test_empty(self):
        assert softmax_select([]) == []


class TestInverseBrierWeights:
    def test_perfect_predictor(self):
        w = inverse_brier_weights([0.0])
        assert w == [1.0]

    def test_random_predictor(self):
        w = inverse_brier_weights([0.25])
        assert w == [0.75]

    def test_ordering(self):
        w = inverse_brier_weights([0.1, 0.3, 0.5])
        assert w[0] > w[1] > w[2]

    def test_empty(self):
        assert inverse_brier_weights([]) == []
