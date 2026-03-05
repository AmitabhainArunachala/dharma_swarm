"""Tests for dharma_swarm.subconscious -- SubconsciousStream, associations."""

from pathlib import Path

import pytest

from dharma_swarm.stigmergy import StigmergicMark, StigmergyStore
from dharma_swarm.subconscious import SubconsciousAssociation, SubconsciousStream


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def stigmergy_store(tmp_path: Path) -> StigmergyStore:
    return StigmergyStore(base_path=tmp_path / "stigmergy")


@pytest.fixture
def stream(stigmergy_store: StigmergyStore, tmp_path: Path) -> SubconsciousStream:
    return SubconsciousStream(
        stigmergy=stigmergy_store,
        hum_path=tmp_path / "subconscious",
    )


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
# _find_resonance
# ---------------------------------------------------------------------------


def test_find_resonance_identical():
    assert SubconsciousStream._find_resonance("hello world", "hello world") == 1.0


def test_find_resonance_no_overlap():
    assert SubconsciousStream._find_resonance("cat dog", "fish bird") == 0.0


def test_find_resonance_partial():
    # words_a = {"hello", "world", "foo"}, words_b = {"hello", "world", "bar"}
    # overlap=2, union=4 => 0.5
    result = SubconsciousStream._find_resonance("hello world foo", "hello world bar")
    assert result == pytest.approx(0.5)


def test_find_resonance_empty():
    assert SubconsciousStream._find_resonance("", "") == 0.0


# ---------------------------------------------------------------------------
# should_wake
# ---------------------------------------------------------------------------


async def test_should_wake_below_threshold(
    stigmergy_store: StigmergyStore,
    stream: SubconsciousStream,
):
    for i in range(10):
        await stigmergy_store.leave_mark(
            _make_mark(observation=f"mark {i}", file_path=f"file_{i}.py")
        )
    assert await stream.should_wake() is False


async def test_should_wake_above_threshold(
    stigmergy_store: StigmergyStore,
    stream: SubconsciousStream,
):
    for i in range(55):
        await stigmergy_store.leave_mark(
            _make_mark(observation=f"mark {i}", file_path=f"file_{i}.py")
        )
    assert await stream.should_wake() is True


# ---------------------------------------------------------------------------
# dream
# ---------------------------------------------------------------------------


async def test_dream_empty(stream: SubconsciousStream):
    associations = await stream.dream()
    assert associations == []


async def test_dream_with_marks(
    stigmergy_store: StigmergyStore,
    stream: SubconsciousStream,
):
    for i in range(8):
        await stigmergy_store.leave_mark(
            _make_mark(
                observation=f"observation about module {i}",
                file_path=f"module_{i}.py",
            )
        )

    associations = await stream.dream(sample_size=5)
    assert len(associations) > 0

    for assoc in associations:
        assert isinstance(assoc, SubconsciousAssociation)
        assert assoc.source_a != ""
        assert assoc.source_b != ""
        assert 0.0 <= assoc.strength <= 1.0

    # Hum file should have been written
    assert stream._hum_file.exists()
