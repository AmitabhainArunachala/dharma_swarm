"""Tests for dharma_swarm.system_rv -- SystemRV participation ratio tracking."""

import json
import math

import pytest

from dharma_swarm.system_rv import SystemRV
from dharma_swarm.models import SystemVitals


# ---------------------------------------------------------------------------
# _compute_pr unit tests
# ---------------------------------------------------------------------------


def test_compute_pr_uniform():
    """Uniform vector [1,1,1,1] -> PR = 4.0 (maximum spread)."""
    srv = SystemRV()
    assert srv._compute_pr([1.0, 1.0, 1.0, 1.0]) == pytest.approx(4.0)


def test_compute_pr_single():
    """One-hot vector [1,0,0,0] -> PR = 1.0 (all energy in one dim)."""
    srv = SystemRV()
    assert srv._compute_pr([1.0, 0.0, 0.0, 0.0]) == pytest.approx(1.0)


def test_compute_pr_zero():
    """Zero vector [0,0,0] -> NaN (undefined)."""
    srv = SystemRV()
    result = srv._compute_pr([0.0, 0.0, 0.0])
    assert math.isnan(result)


def test_compute_pr_two_dim():
    """Two-element vector [3,4] -> known PR value.

    sq = [9, 16], total = 25
    probs = [9/25, 16/25] = [0.36, 0.64]
    sum(p^2) = 0.1296 + 0.4096 = 0.5392
    PR = 1 / 0.5392 ~ 1.8546
    """
    srv = SystemRV()
    pr = srv._compute_pr([3.0, 4.0])
    expected = 1.0 / (0.36**2 + 0.64**2)
    assert pr == pytest.approx(expected, rel=1e-6)


def test_compute_pr_negative_values():
    """Negative values should work (squared before use)."""
    srv = SystemRV()
    # [-1, 1, 1, 1] has same PR as [1, 1, 1, 1] since we square first
    assert srv._compute_pr([-1.0, 1.0, 1.0, 1.0]) == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# init and persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_creates_meta_dir(tmp_path):
    """init() creates the meta directory under state_dir."""
    state = tmp_path / ".dharma"
    srv = SystemRV(state_dir=state)
    await srv.init()
    assert (state / "meta").is_dir()


@pytest.mark.asyncio
async def test_init_loads_existing_history(tmp_path):
    """init() loads history from an existing system_rv.json file."""
    state = tmp_path / ".dharma"
    meta = state / "meta"
    meta.mkdir(parents=True)
    history = [{"timestamp": "2026-01-01T00:00:00+00:00", "pr": 3.5, "rv": 1.0, "regime": "static", "dims": 4}]
    (meta / "system_rv.json").write_text(json.dumps(history))

    srv = SystemRV(state_dir=state)
    await srv.init()
    assert len(srv.history) == 1
    assert srv.history[0]["pr"] == 3.5


@pytest.mark.asyncio
async def test_init_handles_corrupt_json(tmp_path):
    """init() gracefully handles a corrupt history file."""
    state = tmp_path / ".dharma"
    meta = state / "meta"
    meta.mkdir(parents=True)
    (meta / "system_rv.json").write_text("{{{bad json")

    srv = SystemRV(state_dir=state)
    await srv.init()
    assert srv.history == []


# ---------------------------------------------------------------------------
# measure()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_measure_returns_vitals(tmp_path):
    """measure() returns a SystemVitals instance."""
    state = tmp_path / ".dharma"
    srv = SystemRV(state_dir=state)
    await srv.init()
    vitals = await srv.measure()
    assert isinstance(vitals, SystemVitals)
    assert vitals.dimension_count >= 2


@pytest.mark.asyncio
async def test_measure_first_time(tmp_path):
    """First measurement has rv=1.0 (pr_current == pr_previous)."""
    state = tmp_path / ".dharma"
    srv = SystemRV(state_dir=state)
    await srv.init()
    vitals = await srv.measure()
    # First measurement: pr_previous = pr_current, so rv = 1.0
    assert vitals.system_rv == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Regime classification
# ---------------------------------------------------------------------------


def test_regime_converging():
    """rv < 0.8 -> regime='converging', factor=0.7."""
    regime, factor = SystemRV._classify_regime(0.5)
    assert regime == "converging"
    assert factor == 0.7


def test_regime_exploring():
    """rv > 1.2 -> regime='exploring', factor=1.0."""
    regime, factor = SystemRV._classify_regime(1.5)
    assert regime == "exploring"
    assert factor == 1.0


def test_regime_static():
    """0.9 <= rv <= 1.1 -> regime='static', factor=1.3."""
    regime, factor = SystemRV._classify_regime(1.0)
    assert regime == "static"
    assert factor == 1.3


def test_regime_transitional():
    """rv in (0.8, 0.9) or (1.1, 1.2) -> regime='transitional', factor=1.0."""
    regime, factor = SystemRV._classify_regime(0.85)
    assert regime == "transitional"
    assert factor == 1.0

    regime2, factor2 = SystemRV._classify_regime(1.15)
    assert regime2 == "transitional"
    assert factor2 == 1.0


# ---------------------------------------------------------------------------
# History persistence and capping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_persistence(tmp_path):
    """measure() saves to disk; a new instance with init() reads it back."""
    state = tmp_path / ".dharma"
    srv = SystemRV(state_dir=state)
    await srv.init()
    await srv.measure()
    assert len(srv.history) == 1

    # New instance should load the persisted history
    srv2 = SystemRV(state_dir=state)
    await srv2.init()
    assert len(srv2.history) == 1
    assert srv2.history[0]["rv"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_history_capped_at_100(tmp_path):
    """History never grows beyond 100 entries."""
    state = tmp_path / ".dharma"
    srv = SystemRV(state_dir=state)
    await srv.init()

    # Pre-fill with 98 entries
    srv._history = [
        {"timestamp": f"2026-01-01T00:{i:02d}:00+00:00", "pr": 2.0, "rv": 1.0, "regime": "static", "dims": 2}
        for i in range(98)
    ]

    # Take 5 more measurements (total would be 103 without cap)
    for _ in range(5):
        await srv.measure()

    assert len(srv.history) <= 100


# ---------------------------------------------------------------------------
# get_exploration_factor
# ---------------------------------------------------------------------------


def test_get_exploration_factor_default():
    """No history returns 1.0 (neutral factor)."""
    srv = SystemRV()
    assert srv.get_exploration_factor() == 1.0


def test_get_exploration_factor_from_history():
    """Factor derived from last history entry's rv value."""
    srv = SystemRV()
    srv._history = [{"rv": 0.5, "regime": "converging"}]
    assert srv.get_exploration_factor() == 0.7

    srv._history = [{"rv": 1.5, "regime": "exploring"}]
    assert srv.get_exploration_factor() == 1.0

    srv._history = [{"rv": 1.0, "regime": "static"}]
    assert srv.get_exploration_factor() == 1.3


# ---------------------------------------------------------------------------
# collect_state_vector
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_state_vector_minimum(tmp_path):
    """Even with no stores present, returns at least 2 elements."""
    state = tmp_path / ".dharma"
    state.mkdir(parents=True)
    srv = SystemRV(state_dir=state)
    vector = await srv.collect_state_vector()
    assert len(vector) >= 2


@pytest.mark.asyncio
async def test_collect_state_vector_includes_shared_notes(tmp_path):
    """Shared notes directory contributes to the state vector."""
    state = tmp_path / ".dharma"
    shared = state / "shared"
    shared.mkdir(parents=True)
    # Create 3 fake note files
    for i in range(3):
        (shared / f"note_{i}.md").write_text(f"note {i}")

    srv = SystemRV(state_dir=state)
    vector = await srv.collect_state_vector()
    # The note count (3.0) should be in the vector
    assert 3.0 in vector
