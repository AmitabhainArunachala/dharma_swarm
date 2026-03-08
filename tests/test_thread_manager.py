"""Tests for dharma_swarm.thread_manager — thread rotation and overrides."""

import pytest

from dharma_swarm.daemon_config import DaemonConfig
from dharma_swarm.thread_manager import ThreadManager


@pytest.fixture
def state_dir(tmp_path):
    return tmp_path


@pytest.fixture
def config():
    return DaemonConfig(threads=["mechanistic", "phenomenological", "architectural"])


@pytest.fixture
def tm(config, state_dir):
    return ThreadManager(config, state_dir)


def test_initial_thread(tm):
    assert tm.current_thread == "mechanistic"


def test_sequential_rotation(tm):
    assert tm.rotate() == "phenomenological"
    assert tm.rotate() == "architectural"
    assert tm.rotate() == "mechanistic"  # wraps


def test_continuation_mode(state_dir):
    cfg = DaemonConfig(
        threads=["a", "b", "c"],
        rotation_mode="continuation",
    )
    tm = ThreadManager(cfg, state_dir)
    assert tm.rotate() == "a"  # stays on current
    assert tm.rotate() == "a"


def test_random_rotation(state_dir):
    cfg = DaemonConfig(
        threads=["a", "b", "c"],
        rotation_mode="random",
    )
    tm = ThreadManager(cfg, state_dir)
    results = {tm.rotate() for _ in range(30)}
    assert len(results) > 1  # should hit at least 2 of 3


def test_record_contribution(tm):
    tm.record_contribution()
    tm.record_contribution()
    stats = tm.stats()
    assert stats["contributions"]["mechanistic"] == 2
    assert stats["total"] == 2


def test_record_contribution_specific_thread(tm):
    tm.record_contribution("architectural")
    stats = tm.stats()
    assert stats["contributions"]["architectural"] == 1


def test_state_persistence(config, state_dir):
    tm1 = ThreadManager(config, state_dir)
    tm1.rotate()  # -> phenomenological
    tm1.record_contribution()

    tm2 = ThreadManager(config, state_dir)
    assert tm2.current_thread == "phenomenological"
    assert tm2.stats()["contributions"]["phenomenological"] == 1


def test_focus_override(tm, state_dir):
    assert tm.check_focus_override(state_dir) is None

    (state_dir / ".FOCUS").write_text("architectural")
    assert tm.check_focus_override(state_dir) == "architectural"

    # Invalid thread name returns None
    (state_dir / ".FOCUS").write_text("nonexistent")
    assert tm.check_focus_override(state_dir) is None


def test_inject_override(tm, state_dir):
    assert tm.check_inject_override(state_dir) is None

    (state_dir / ".INJECT").write_text("Focus on R_V paper")
    assert tm.check_inject_override(state_dir) == "Focus on R_V paper"

    # Empty inject returns None
    (state_dir / ".INJECT").write_text("")
    assert tm.check_inject_override(state_dir) is None


def test_stats(tm):
    stats = tm.stats()
    assert stats["current_thread"] == "mechanistic"
    assert stats["rotation_mode"] == "sequential"
    assert stats["total"] == 0


def test_current_prompt(tm):
    prompt = tm.current_prompt
    assert isinstance(prompt, str)
