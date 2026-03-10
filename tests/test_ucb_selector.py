"""Tests for the Darwin UCB selector."""

import pytest

from dharma_swarm.archive import ArchiveEntry, EvolutionArchive, FitnessScore
from dharma_swarm.ucb_selector import UCBConfig, UCBParentSelector


@pytest.fixture
async def archive(tmp_path):
    path = tmp_path / "ucb_archive.jsonl"
    archive = EvolutionArchive(path=path)
    await archive.load()

    for idx, score in enumerate([0.1, 0.5, 0.9]):
        await archive.add_entry(
            ArchiveEntry(
                component=f"parent_{idx}.py",
                change_type="mutation",
                description=f"Parent {idx}",
                fitness=FitnessScore(correctness=score),
                status="applied",
            )
        )
    return archive


@pytest.mark.asyncio
async def test_ucb_explores_all_parents(archive):
    selector = UCBParentSelector(UCBConfig(min_pulls=2, annealing_rate=1.0))

    selected_ids: list[str] = []
    for _ in range(6):
        parent = await selector.select_parent(archive)
        assert parent is not None
        selected_ids.append(parent.id)

    assert len(set(selected_ids)) == 3
    assert all(count >= 2 for count in selector.state.child_counts.values())


@pytest.mark.asyncio
async def test_ucb_anneals_exploration(archive):
    selector = UCBParentSelector(UCBConfig(annealing_rate=0.9))
    initial = selector.state.exploration_coeff

    for _ in range(3):
        parent = await selector.select_parent(archive)
        assert parent is not None

    assert selector.state.exploration_coeff < initial
    assert selector.get_exploration_ratio() < 1.0


@pytest.mark.asyncio
async def test_ucb_respects_weighted_fitness(tmp_path):
    path = tmp_path / "ucb_weighted_archive.jsonl"
    archive = EvolutionArchive(path=path)
    await archive.load()
    await archive.add_entry(
        ArchiveEntry(
            component="correct.py",
            change_type="mutation",
            description="High correctness",
            fitness=FitnessScore(correctness=1.0, elegance=0.0, safety=1.0),
            status="applied",
        )
    )
    await archive.add_entry(
        ArchiveEntry(
            component="elegant.py",
            change_type="mutation",
            description="High elegance",
            fitness=FitnessScore(correctness=0.0, elegance=1.0, safety=1.0),
            status="applied",
        )
    )

    selector = UCBParentSelector(UCBConfig(exploration_coeff=0.0, min_pulls=0))
    parent = await selector.select_parent(
        archive,
        weights={
            "correctness": 0.0,
            "dharmic_alignment": 0.0,
            "performance": 0.0,
            "utilization": 0.0,
            "economic_value": 0.0,
            "elegance": 1.0,
            "efficiency": 0.0,
            "safety": 0.0,
        },
    )

    assert parent is not None
    assert parent.component == "elegant.py"
