"""Tests for dharma_swarm.stigmergy -- StigmergicMark, StigmergyStore."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dharma_swarm.stigmergy import StigmergicMark, StigmergyStore, leave_stigmergic_mark


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> StigmergyStore:
    return StigmergyStore(base_path=tmp_path / "stigmergy")


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
# leave_mark
# ---------------------------------------------------------------------------


async def test_leave_mark_returns_id(store: StigmergyStore):
    mark = _make_mark()
    result = await store.leave_mark(mark)
    assert isinstance(result, str)
    assert len(result) == 16
    assert result == mark.id


# ---------------------------------------------------------------------------
# read_marks
# ---------------------------------------------------------------------------


async def test_read_marks_empty(store: StigmergyStore):
    marks = await store.read_marks()
    assert marks == []


async def test_read_marks_after_leave(store: StigmergyStore):
    for i in range(3):
        await store.leave_mark(_make_mark(observation=f"obs {i}"))
    marks = await store.read_marks()
    assert len(marks) == 3


async def test_read_marks_filtered_by_path(store: StigmergyStore):
    await store.leave_mark(_make_mark(file_path="a.py"))
    await store.leave_mark(_make_mark(file_path="b.py"))
    await store.leave_mark(_make_mark(file_path="a.py"))

    a_marks = await store.read_marks(file_path="a.py")
    assert len(a_marks) == 2
    assert all(m.file_path == "a.py" for m in a_marks)

    b_marks = await store.read_marks(file_path="b.py")
    assert len(b_marks) == 1


async def test_read_marks_limit(store: StigmergyStore):
    now = datetime.now(timezone.utc)
    for i in range(5):
        m = _make_mark(observation=f"obs {i}")
        m.timestamp = now + timedelta(seconds=i)
        await store.leave_mark(m)

    marks = await store.read_marks(limit=2)
    assert len(marks) == 2
    # Most recent first
    assert marks[0].timestamp >= marks[1].timestamp


# ---------------------------------------------------------------------------
# hot_paths
# ---------------------------------------------------------------------------


async def test_hot_paths(store: StigmergyStore):
    for _ in range(4):
        await store.leave_mark(_make_mark(file_path="hot.py"))
    await store.leave_mark(_make_mark(file_path="cold.py"))

    hot = await store.hot_paths(window_hours=24, min_marks=3)
    assert len(hot) == 1
    assert hot[0][0] == "hot.py"
    assert hot[0][1] == 4


# ---------------------------------------------------------------------------
# high_salience
# ---------------------------------------------------------------------------


async def test_high_salience(store: StigmergyStore):
    await store.leave_mark(_make_mark(salience=0.3))
    await store.leave_mark(_make_mark(salience=0.8, observation="important"))
    await store.leave_mark(_make_mark(salience=0.9, observation="critical"))
    await store.leave_mark(_make_mark(salience=0.5))

    high = await store.high_salience(threshold=0.7)
    assert len(high) == 2
    assert high[0].salience == 0.9
    assert high[1].salience == 0.8


# ---------------------------------------------------------------------------
# connections_for
# ---------------------------------------------------------------------------


async def test_connections_for(store: StigmergyStore):
    await store.leave_mark(
        _make_mark(file_path="core.py", connections=["utils.py", "models.py"])
    )
    await store.leave_mark(
        _make_mark(file_path="core.py", connections=["models.py", "config.py"])
    )
    await store.leave_mark(
        _make_mark(file_path="other.py", connections=["unrelated.py"])
    )

    conns = await store.connections_for("core.py")
    assert conns == ["config.py", "models.py", "utils.py"]


# ---------------------------------------------------------------------------
# decay
# ---------------------------------------------------------------------------


async def test_decay(store: StigmergyStore):
    now = datetime.now(timezone.utc)

    old_mark = _make_mark(observation="ancient")
    old_mark.timestamp = now - timedelta(hours=200)
    await store.leave_mark(old_mark)

    fresh_mark = _make_mark(observation="recent")
    fresh_mark.timestamp = now
    await store.leave_mark(fresh_mark)

    archived = await store.decay(max_age_hours=168)
    assert archived == 1

    # Only the fresh mark remains
    remaining = await store.read_marks()
    assert len(remaining) == 1
    assert remaining[0].observation == "recent"

    # Archive file was created
    assert store._archive_file.exists()


# ---------------------------------------------------------------------------
# density
# ---------------------------------------------------------------------------


async def test_density(store: StigmergyStore):
    for _ in range(3):
        await store.leave_mark(_make_mark())
    assert store.density() == 3


async def test_density_empty(store: StigmergyStore):
    assert store.density() == 0


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------


async def test_leave_stigmergic_mark_convenience(tmp_path: Path, monkeypatch):
    """The module-level function creates a mark via a default store."""
    # Monkeypatch the default base path so we don't write to real ~/.dharma/
    monkeypatch.setattr(
        "dharma_swarm.stigmergy._DEFAULT_BASE",
        tmp_path / "stigmergy",
    )
    mark_id = await leave_stigmergic_mark(
        agent="conv-agent",
        file_path="test.py",
        observation="Quick note",
        salience=0.6,
        connections=["related.py"],
        action="scan",
    )
    assert isinstance(mark_id, str)
    assert len(mark_id) == 16

    # Verify the mark landed on disk
    store = StigmergyStore(base_path=tmp_path / "stigmergy")
    marks = await store.read_marks()
    assert len(marks) == 1
    assert marks[0].agent == "conv-agent"
    assert marks[0].action == "scan"
