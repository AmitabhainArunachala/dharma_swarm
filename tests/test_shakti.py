"""Tests for dharma_swarm.shakti -- ShaktiEnergy, ShaktiPerception, ShaktiLoop."""

from pathlib import Path

import pytest

from dharma_swarm.shakti import (
    ShaktiEnergy,
    ShaktiLoop,
    ShaktiPerception,
    classify_energy,
)
from dharma_swarm.stigmergy import StigmergicMark, StigmergyStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def stigmergy_store(tmp_path: Path) -> StigmergyStore:
    return StigmergyStore(base_path=tmp_path / "stigmergy")


@pytest.fixture
def shakti_loop(stigmergy_store: StigmergyStore) -> ShaktiLoop:
    return ShaktiLoop(stigmergy=stigmergy_store)


def _make_mark(**kwargs) -> StigmergicMark:
    """Shorthand for building test marks with sensible defaults."""
    defaults = {
        "agent": "test-agent",
        "file_path": "src/main.py",
        "action": "write",
        "observation": "Refactored core loop",
        "salience": 0.5,
    }
    defaults.update(kwargs)
    return StigmergicMark(**defaults)


# ---------------------------------------------------------------------------
# classify_energy
# ---------------------------------------------------------------------------


def test_classify_energy_maheshwari():
    assert classify_energy("vision and architecture pattern") == ShaktiEnergy.MAHESHWARI


def test_classify_energy_mahakali():
    assert classify_energy("force action deploy") == ShaktiEnergy.MAHAKALI


def test_classify_energy_mahalakshmi():
    assert classify_energy("harmony balance beauty") == ShaktiEnergy.MAHALAKSHMI


def test_classify_energy_mahasaraswati():
    assert classify_energy("precision detail exact") == ShaktiEnergy.MAHASARASWATI


def test_classify_energy_default():
    assert classify_energy("nothing relevant here") == ShaktiEnergy.MAHASARASWATI


# ---------------------------------------------------------------------------
# perceive
# ---------------------------------------------------------------------------


async def test_perceive_empty(shakti_loop: ShaktiLoop):
    perceptions = await shakti_loop.perceive()
    assert perceptions == []


async def test_perceive_with_hot_paths(
    stigmergy_store: StigmergyStore,
    shakti_loop: ShaktiLoop,
):
    # Leave enough marks on one path to exceed min_marks=3
    for i in range(6):
        await stigmergy_store.leave_mark(
            _make_mark(file_path="hot_module.py", observation=f"touch {i}")
        )

    perceptions = await shakti_loop.perceive()
    assert len(perceptions) >= 1

    hot_p = [p for p in perceptions if "hot_module.py" in p.observation]
    assert len(hot_p) == 1
    assert hot_p[0].connection == "hot_module.py"
    assert hot_p[0].impact_level == "module"  # 6 > 5


# ---------------------------------------------------------------------------
# propose_local / escalate
# ---------------------------------------------------------------------------


async def test_propose_local(shakti_loop: ShaktiLoop):
    p = ShaktiPerception(
        observation="small fix",
        connection="file.py",
        energy=ShaktiEnergy.MAHASARASWATI,
        impact_level="local",
        proposal="tighten the loop",
    )
    result = await shakti_loop.propose_local(p)
    assert result is not None
    assert result["type"] == "local"
    assert result["proposal"] == "tighten the loop"
    assert result["energy"] == "mahasaraswati"


async def test_propose_local_rejects_system(shakti_loop: ShaktiLoop):
    p = ShaktiPerception(
        observation="big shift",
        connection="core.py",
        energy=ShaktiEnergy.MAHESHWARI,
        impact_level="system",
    )
    result = await shakti_loop.propose_local(p)
    assert result is None


async def test_escalate(shakti_loop: ShaktiLoop):
    p = ShaktiPerception(
        observation="cross-module coupling detected",
        connection="bridge.py",
        energy=ShaktiEnergy.MAHESHWARI,
        impact_level="system",
        proposal="refactor the bridge",
    )
    result = await shakti_loop.escalate(p)
    assert result["type"] == "escalation"
    assert result["impact"] == "system"
    assert result["observation"] == "cross-module coupling detected"
    assert result["proposal"] == "refactor the bridge"
    assert result["energy"] == "maheshwari"
