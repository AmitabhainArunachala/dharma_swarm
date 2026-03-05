"""Tests for dharma_swarm.fitness_predictor."""

import json

import pytest

from dharma_swarm.fitness_predictor import (
    FitnessPredictor,
    PredictionOutcome,
    ProposalFeatures,
    _LARGE_DIFF_PENALTY,
    _LARGE_DIFF_THRESHOLD,
    _NEUTRAL_PRIOR,
    _SMALL_DIFF_BONUS,
    _SMALL_DIFF_THRESHOLD,
    _TEST_COVERAGE_BONUS,
)


# === Fixtures ===


@pytest.fixture
def history_path(tmp_path):
    """Return a temporary JSONL history file path."""
    return tmp_path / "predictor_data.jsonl"


@pytest.fixture
def predictor(history_path):
    """Return a FitnessPredictor with a tmp history path."""
    return FitnessPredictor(history_path=history_path)


def _make_features(
    component: str = "models.py",
    change_type: str = "mutation",
    diff_size: int = 30,
    complexity_delta: float = 0.0,
    test_coverage_exists: bool = False,
    gates_likely_to_pass: int = 4,
) -> ProposalFeatures:
    """Helper to build ProposalFeatures with sensible defaults."""
    return ProposalFeatures(
        component=component,
        change_type=change_type,
        diff_size=diff_size,
        complexity_delta=complexity_delta,
        test_coverage_exists=test_coverage_exists,
        gates_likely_to_pass=gates_likely_to_pass,
    )


# === ProposalFeatures model tests ===


def test_proposal_features_defaults():
    f = ProposalFeatures(component="x.py", change_type="mutation", diff_size=10)
    assert f.complexity_delta == 0.0
    assert f.test_coverage_exists is False
    assert f.gates_likely_to_pass == 0


def test_proposal_features_json_roundtrip():
    f = _make_features(component="runner.py", change_type="crossover", diff_size=77)
    data = f.model_dump_json()
    f2 = ProposalFeatures.model_validate_json(data)
    assert f2.component == "runner.py"
    assert f2.diff_size == 77


# === Predict with no history ===


@pytest.mark.asyncio
async def test_predict_no_history_returns_neutral(predictor):
    await predictor.load()
    features = _make_features(diff_size=80)
    score = predictor.predict(features)
    # No history, medium diff, no test coverage -> neutral prior
    assert score == _NEUTRAL_PRIOR


@pytest.mark.asyncio
async def test_predict_no_history_small_diff_bonus(predictor):
    await predictor.load()
    features = _make_features(diff_size=10)
    score = predictor.predict(features)
    assert score == pytest.approx(_NEUTRAL_PRIOR + _SMALL_DIFF_BONUS)


@pytest.mark.asyncio
async def test_predict_no_history_large_diff_penalty(predictor):
    await predictor.load()
    features = _make_features(diff_size=300)
    score = predictor.predict(features)
    assert score == pytest.approx(_NEUTRAL_PRIOR - _LARGE_DIFF_PENALTY)


@pytest.mark.asyncio
async def test_predict_no_history_test_coverage_bonus(predictor):
    await predictor.load()
    features = _make_features(diff_size=80, test_coverage_exists=True)
    score = predictor.predict(features)
    assert score == pytest.approx(_NEUTRAL_PRIOR + _TEST_COVERAGE_BONUS)


# === Record outcome + predict ===


@pytest.mark.asyncio
async def test_record_then_predict_uses_history(predictor):
    await predictor.load()
    features = _make_features(component="gates.py", change_type="mutation", diff_size=80)

    # Record two outcomes for this group
    await predictor.record_outcome(features, 0.8)
    await predictor.record_outcome(features, 0.6)

    # Mean for (gates.py, mutation) is 0.7
    score = predictor.predict(features)
    assert score == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_record_different_groups(predictor):
    await predictor.load()

    f1 = _make_features(component="a.py", change_type="mutation", diff_size=80)
    f2 = _make_features(component="b.py", change_type="crossover", diff_size=80)

    await predictor.record_outcome(f1, 0.9)
    await predictor.record_outcome(f2, 0.3)

    assert predictor.predict(f1) == pytest.approx(0.9)
    assert predictor.predict(f2) == pytest.approx(0.3)
    assert predictor.group_count == 2


# === should_attempt ===


@pytest.mark.asyncio
async def test_should_attempt_above_threshold(predictor):
    await predictor.load()
    features = _make_features(diff_size=80)
    # Neutral prior (0.5) > default threshold (0.3)
    assert predictor.should_attempt(features) is True


@pytest.mark.asyncio
async def test_should_attempt_below_threshold(predictor):
    await predictor.load()
    features = _make_features(component="low.py", change_type="ablation", diff_size=80)
    await predictor.record_outcome(features, 0.1)
    await predictor.record_outcome(features, 0.15)

    # Mean is 0.125, below default threshold 0.3
    assert predictor.should_attempt(features) is False


@pytest.mark.asyncio
async def test_should_attempt_custom_threshold(predictor):
    await predictor.load()
    features = _make_features(diff_size=80)
    # Neutral 0.5 > 0.4
    assert predictor.should_attempt(features, threshold=0.4) is True
    # Neutral 0.5 < 0.6 — not above threshold
    assert predictor.should_attempt(features, threshold=0.6) is False


# === Persistence across load/save cycles ===


@pytest.mark.asyncio
async def test_persistence_across_load_cycles(history_path):
    # First predictor: record outcomes
    p1 = FitnessPredictor(history_path=history_path)
    await p1.load()
    features = _make_features(component="persist.py", change_type="mutation", diff_size=80)
    await p1.record_outcome(features, 0.8)
    await p1.record_outcome(features, 0.6)

    # Second predictor: load from same file
    p2 = FitnessPredictor(history_path=history_path)
    await p2.load()

    assert p2.outcome_count == 2
    score = p2.predict(features)
    assert score == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_jsonl_file_format(predictor, history_path):
    await predictor.load()
    features = _make_features()
    await predictor.record_outcome(features, 0.75)

    lines = history_path.read_text().strip().split("\n")
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["actual_fitness"] == 0.75
    assert data["features"]["component"] == "models.py"


# === Clamping ===


@pytest.mark.asyncio
async def test_predict_clamps_to_zero(predictor):
    await predictor.load()
    features = _make_features(
        component="bad.py", change_type="ablation", diff_size=300
    )
    # Record very low fitness so base is near 0, then large diff penalty pushes below
    await predictor.record_outcome(features, 0.05)
    score = predictor.predict(features)
    assert score >= 0.0


@pytest.mark.asyncio
async def test_predict_clamps_to_one(predictor):
    await predictor.load()
    features = _make_features(
        component="great.py",
        change_type="mutation",
        diff_size=10,
        test_coverage_exists=True,
    )
    # Record very high fitness, then bonuses push toward/above 1.0
    await predictor.record_outcome(features, 0.99)
    score = predictor.predict(features)
    assert score <= 1.0


# === Properties ===


@pytest.mark.asyncio
async def test_outcome_count(predictor):
    await predictor.load()
    assert predictor.outcome_count == 0
    await predictor.record_outcome(_make_features(), 0.5)
    assert predictor.outcome_count == 1
    await predictor.record_outcome(_make_features(component="other.py"), 0.6)
    assert predictor.outcome_count == 2


@pytest.mark.asyncio
async def test_group_count(predictor):
    await predictor.load()
    assert predictor.group_count == 0

    await predictor.record_outcome(
        _make_features(component="a.py", change_type="mutation"), 0.5
    )
    assert predictor.group_count == 1

    # Same group
    await predictor.record_outcome(
        _make_features(component="a.py", change_type="mutation"), 0.6
    )
    assert predictor.group_count == 1

    # New group
    await predictor.record_outcome(
        _make_features(component="a.py", change_type="crossover"), 0.7
    )
    assert predictor.group_count == 2


# === Edge cases ===


@pytest.mark.asyncio
async def test_load_empty_file(predictor, history_path):
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text("")
    await predictor.load()
    assert predictor.outcome_count == 0


@pytest.mark.asyncio
async def test_load_corrupt_lines(predictor, history_path):
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text("not json\n{\"bad\": true}\n")
    await predictor.load()
    # Both lines are invalid PredictionOutcome, should be skipped
    assert predictor.outcome_count == 0


@pytest.mark.asyncio
async def test_combined_bonuses_stack(predictor):
    """Small diff + test coverage both apply."""
    await predictor.load()
    features = _make_features(diff_size=10, test_coverage_exists=True)
    score = predictor.predict(features)
    expected = _NEUTRAL_PRIOR + _SMALL_DIFF_BONUS + _TEST_COVERAGE_BONUS
    assert score == pytest.approx(expected)


@pytest.mark.asyncio
async def test_large_diff_and_test_coverage(predictor):
    """Large diff penalty + test coverage bonus partially offset."""
    await predictor.load()
    features = _make_features(diff_size=300, test_coverage_exists=True)
    score = predictor.predict(features)
    expected = _NEUTRAL_PRIOR - _LARGE_DIFF_PENALTY + _TEST_COVERAGE_BONUS
    assert score == pytest.approx(expected)


@pytest.mark.asyncio
async def test_boundary_diff_sizes(predictor):
    """Exactly at thresholds: no bonus or penalty."""
    await predictor.load()

    # Exactly at small threshold boundary -- not < 50, so no bonus
    f_at_small = _make_features(diff_size=_SMALL_DIFF_THRESHOLD)
    assert predictor.predict(f_at_small) == pytest.approx(_NEUTRAL_PRIOR)

    # Exactly at large threshold boundary -- not > 200, so no penalty
    f_at_large = _make_features(diff_size=_LARGE_DIFF_THRESHOLD)
    assert predictor.predict(f_at_large) == pytest.approx(_NEUTRAL_PRIOR)
