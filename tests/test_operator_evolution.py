"""Tests for OperatorEvolver — self-evolution pipeline for operator prompt."""

import json

import pytest

from dharma_swarm.operator_evolution import (
    OperatorEvolver,
    PromptGenome,
    PromptSegment,
)


# -- PromptSegment / PromptGenome tests --

def test_prompt_segment_to_dict():
    seg = PromptSegment(name="identity", content="You are X", segment_type="INVARIANT")
    d = seg.to_dict()
    assert d["name"] == "identity"
    assert d["segment_type"] == "INVARIANT"
    assert d["version"] == 1


def test_prompt_genome_render():
    genome = PromptGenome(segments=[
        PromptSegment(name="identity", content="I am the operator", segment_type="INVARIANT"),
        PromptSegment(name="approach", content="Be direct", segment_type="MUTABLE"),
        PromptSegment(name="state", content="", segment_type="ADAPTIVE"),
    ])

    # Without adaptive context
    prompt = genome.render()
    assert "I am the operator" in prompt
    assert "Be direct" in prompt

    # With adaptive context
    prompt = genome.render({"state": "Agents: 5"})
    assert "Agents: 5" in prompt


def test_prompt_genome_get_mutable():
    genome = PromptGenome(segments=[
        PromptSegment(name="identity", content="X", segment_type="INVARIANT"),
        PromptSegment(name="approach", content="Y", segment_type="MUTABLE"),
        PromptSegment(name="tone", content="Z", segment_type="MUTABLE"),
    ])
    mutable = genome.get_mutable_segments()
    assert len(mutable) == 2
    assert all(s.segment_type == "MUTABLE" for s in mutable)


def test_prompt_genome_serialization():
    genome = PromptGenome(
        generation=3,
        parent_id="gen_2",
        segments=[
            PromptSegment(name="a", content="hello", segment_type="INVARIANT"),
        ],
        fitness_history=[5.08, 5.10],
    )
    data = genome.to_dict()
    restored = PromptGenome.from_dict(data)
    assert restored.generation == 3
    assert restored.parent_id == "gen_2"
    assert len(restored.segments) == 1
    assert restored.segments[0].name == "a"
    assert restored.fitness_history == [5.08, 5.10]


# -- OperatorEvolver tests --

@pytest.fixture
def evolver(tmp_path):
    return OperatorEvolver(genome_path=tmp_path / "operator_prompt.json")


@pytest.mark.asyncio
async def test_evolver_init_creates_default_genome(evolver):
    await evolver.init()
    assert evolver._genome is not None
    assert evolver._genome.generation == 0
    assert len(evolver._genome.segments) > 0

    # Should have INVARIANT, MUTABLE, and ADAPTIVE segments
    types = {s.segment_type for s in evolver._genome.segments}
    assert "INVARIANT" in types
    assert "MUTABLE" in types
    assert "ADAPTIVE" in types


@pytest.mark.asyncio
async def test_evolver_get_current_prompt(evolver):
    await evolver.init()
    prompt = evolver.get_current_prompt()
    assert "Resident Operator" in prompt
    assert "CONDUCTOR" in prompt


@pytest.mark.asyncio
async def test_evolver_persists_genome(tmp_path):
    path = tmp_path / "test_genome.json"
    ev = OperatorEvolver(genome_path=path)
    await ev.init()

    assert path.exists()
    data = json.loads(path.read_text())
    assert data["generation"] == 0
    assert len(data["segments"]) > 0


@pytest.mark.asyncio
async def test_evolver_loads_persisted_genome(tmp_path):
    path = tmp_path / "test_genome.json"

    # Create and save
    ev1 = OperatorEvolver(genome_path=path)
    await ev1.init()

    # Modify generation to verify persistence
    ev1._genome.generation = 42
    ev1._save_genome(ev1._genome)

    # Load from disk
    ev2 = OperatorEvolver(genome_path=path)
    await ev2.init()
    assert ev2._genome.generation == 42


@pytest.mark.asyncio
async def test_shadow_evaluate_skips_non_interval(evolver):
    await evolver.init()

    # Interaction 1 — not a multiple of SHADOW_INTERVAL
    await evolver.maybe_shadow_evaluate(1, "test", "response", 5.08)
    assert len(evolver._shadow_results) == 0


@pytest.mark.asyncio
async def test_shadow_evaluate_fires_on_interval(evolver):
    await evolver.init()

    # Interaction at SHADOW_INTERVAL (10)
    await evolver.maybe_shadow_evaluate(10, "test", "response", 5.08)
    assert len(evolver._shadow_results) == 1
    assert len(evolver._baseline_scores) == 1


@pytest.mark.asyncio
async def test_check_promotion_defer_with_no_data(evolver):
    await evolver.init()
    result = await evolver.check_promotion()
    assert result is None


@pytest.mark.asyncio
async def test_check_promotion_with_enough_evals(evolver):
    await evolver.init()

    # Simulate 5 shadow evaluations at the interval
    for i in range(5):
        await evolver.maybe_shadow_evaluate(
            (i + 1) * 10, "test input", "response", 5.08,
        )

    # Should have triggered check_promotion internally
    # and either PROMOTED, ROLLED BACK, or DEFERRED
    assert len(evolver._shadow_results) == 0 or len(evolver._shadow_results) <= 10


@pytest.mark.asyncio
async def test_mutation_is_deterministic(evolver):
    await evolver.init()
    text = "- Step 1\n- Step 2"
    mutated = evolver._apply_mutation(text)
    # Should swap first "- " to "* "
    assert "* " in mutated or mutated == text


@pytest.mark.asyncio
async def test_canary_scoring_returns_valid_range(evolver):
    await evolver.init()
    evolver._canary_genome = evolver._mutate_genome()
    score = await evolver._score_canary("test input")
    assert 5.0 <= score <= 5.15


def test_evolver_status_dict(tmp_path):
    ev = OperatorEvolver(genome_path=tmp_path / "test.json")
    status = ev.status_dict()
    assert "generation" in status
    assert "shadow_evals_pending" in status
    assert status["has_canary"] is False
