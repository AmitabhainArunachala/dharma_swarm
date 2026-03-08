"""Property-based tests for FitnessScore.

Tests that fitness calculations are always valid, bounded, and consistent.
"""

from hypothesis import given, strategies as st
import pytest

try:
    from dharma_swarm.archive import FitnessScore
    ARCHIVE_AVAILABLE = True
except ImportError:
    ARCHIVE_AVAILABLE = False
    pytestmark = pytest.mark.skip(reason="archive module not available")


def fitness_score_strategy():
    """Generate random but valid FitnessScore instances."""
    return st.builds(
        FitnessScore,
        correctness=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        dharmic_alignment=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        performance=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        utilization=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        elegance=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        efficiency=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        safety=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )


if ARCHIVE_AVAILABLE:
    @given(fitness_score_strategy())
    def test_fitness_all_dimensions_bounded(fitness):
        """Property: All fitness dimensions must be in [0, 1]."""
        assert 0.0 <= fitness.correctness <= 1.0
        assert 0.0 <= fitness.dharmic_alignment <= 1.0
        assert 0.0 <= fitness.performance <= 1.0
        assert 0.0 <= fitness.utilization <= 1.0
        assert 0.0 <= fitness.elegance <= 1.0
        assert 0.0 <= fitness.efficiency <= 1.0
        assert 0.0 <= fitness.safety <= 1.0


    @given(fitness_score_strategy())
    def test_fitness_weighted_bounded(fitness):
        """Property: Weighted fitness score must be in [0, 1]."""
        weighted = fitness.weighted()
        assert 0.0 <= weighted <= 1.0, \
            f"Weighted fitness {weighted} out of bounds [0, 1]"


    @given(fitness_score_strategy())
    def test_fitness_weighted_not_nan(fitness):
        """Property: Weighted fitness should never be NaN."""
        import math
        weighted = fitness.weighted()
        assert not math.isnan(weighted), "Weighted fitness is NaN"


    @given(fitness_score_strategy(), st.dictionaries(
        st.sampled_from(['correctness', 'dharmic_alignment', 'performance', 'utilization', 'elegance', 'efficiency', 'safety']),
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        min_size=1
    ))
    def test_fitness_custom_weights_sum_not_required(fitness, weights):
        """Property: Custom weights don't need to sum to 1.0 (just positive)."""
        # Should not raise even if weights don't sum to 1
        try:
            weighted = fitness.weighted(weights)
            # Should still be a valid number
            import math
            assert not math.isnan(weighted)
            assert not math.isinf(weighted)
        except Exception as e:
            pytest.fail(f"Custom weights raised exception: {e}")


    @given(fitness_score_strategy())
    def test_fitness_json_roundtrip(fitness):
        """Property: FitnessScore serialization preserves values."""
        json_str = fitness.model_dump_json()
        restored = FitnessScore.model_validate_json(json_str)

        assert restored.correctness == fitness.correctness
        assert restored.dharmic_alignment == fitness.dharmic_alignment
        assert restored.performance == fitness.performance
        assert restored.utilization == fitness.utilization
        assert restored.elegance == fitness.elegance
        assert restored.efficiency == fitness.efficiency
        assert restored.safety == fitness.safety


    @given(fitness_score_strategy())
    def test_fitness_perfect_score_is_one(fitness):
        """Property: If all dimensions are 1.0, weighted should be 1.0."""
        perfect = FitnessScore(
            correctness=1.0,
            dharmic_alignment=1.0,
            performance=1.0,
            utilization=1.0,
            economic_value=1.0,  # Added in Phase 1
            elegance=1.0,
            efficiency=1.0,
            safety=1.0
        )
        assert abs(perfect.weighted() - 1.0) < 0.001, \
            f"Perfect score weighted to {perfect.weighted()}, expected 1.0"


    @given(fitness_score_strategy())
    def test_fitness_zero_score_is_zero(fitness):
        """Property: If all dimensions are 0.0, weighted should be 0.0."""
        zero = FitnessScore(
            correctness=0.0,
            dharmic_alignment=0.0,
            performance=0.0,
            utilization=0.0,
            economic_value=0.0,  # Added in Phase 1
            elegance=0.0,
            efficiency=0.0,
            safety=0.0
        )
        assert abs(zero.weighted() - 0.0) < 0.001, \
            f"Zero score weighted to {zero.weighted()}, expected 0.0"
