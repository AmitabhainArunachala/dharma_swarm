"""Tests for the Darwin meta-learning prototype."""

import pytest

from dharma_swarm.evolution import DarwinEngine, EvolutionStatus, Proposal
from dharma_swarm.meta_learning_prototype import MetaLearningPrototype


@pytest.fixture
def engine_paths(tmp_path):
    return {
        "archive_path": tmp_path / "archive.jsonl",
        "traces_path": tmp_path / "traces",
        "predictor_path": tmp_path / "predictor.jsonl",
    }


@pytest.fixture
async def engine(engine_paths):
    eng = DarwinEngine(**engine_paths)
    await eng.init()
    return eng


@pytest.mark.asyncio
async def test_meta_learning_can_improve_with_custom_scorer(engine):
    meta = MetaLearningPrototype(engine, mutation_scale=0.7, seed=3)
    target = {
        "correctness": 0.05,
        "dharmic_alignment": 0.05,
        "performance": 0.05,
        "utilization": 0.05,
        "economic_value": 0.05,
        "elegance": 0.55,
        "efficiency": 0.15,
        "safety": 0.05,
    }

    async def scorer(weights, proposals):
        del proposals
        distance = sum(abs(weights[key] - target[key]) for key in target)
        return 1.0 - (distance / 2.0)

    result = await meta.run_meta_experiment(
        [],
        n_meta_cycles=5,
        candidates_per_cycle=8,
        scorer=scorer,
    )

    assert result.final_score > result.baseline_score
    assert result.fitness_improvement > 0.0
    actual = engine.get_fitness_weights()
    expected = result.weight_history[-1]
    for key in expected:
        assert actual[key] == pytest.approx(expected[key], rel=1e-9)


@pytest.mark.asyncio
async def test_evaluate_weights_does_not_mutate_input_proposals(engine):
    meta = MetaLearningPrototype(engine, seed=11)
    proposal = Proposal(
        component="module.py",
        change_type="mutation",
        description="Improve safety checks",
        diff="+ check = True\n",
        think_notes="Risk: low. Rollback: revert single change.",
    )

    score = await meta.evaluate_weights([proposal], meta.fitness_weights)

    assert score >= 0.0
    assert proposal.status == EvolutionStatus.PENDING
    assert proposal.actual_fitness is None


def test_format_weights_uses_canonical_order():
    meta = MetaLearningPrototype(DarwinEngine())
    formatted = meta.format_weights(meta.fitness_weights)
    assert formatted.startswith("cor=")
    assert "saf=" in formatted
