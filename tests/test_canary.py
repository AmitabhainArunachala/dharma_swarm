"""Tests for dharma_swarm.canary -- CanaryDeployer + CanaryConfig."""

import pytest

from dharma_swarm.archive import ArchiveEntry, EvolutionArchive, FitnessScore
from dharma_swarm.canary import (
    CanaryConfig,
    CanaryDecision,
    CanaryDeployer,
    CanaryResult,
)


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

_BASELINE_FITNESS = FitnessScore(
    correctness=0.7,
    elegance=0.6,
    dharmic_alignment=0.5,
    efficiency=0.6,
    safety=0.8,
)


@pytest.fixture
async def setup(tmp_path):
    """Create an archive with one baseline entry and a default deployer."""
    archive = EvolutionArchive(path=tmp_path / "archive.jsonl")
    await archive.load()

    entry = ArchiveEntry(
        component="test.py",
        change_type="mutation",
        description="test change",
        fitness=_BASELINE_FITNESS,
        status="applied",
    )
    entry_id = await archive.add_entry(entry)
    deployer = CanaryDeployer(archive=archive)
    return deployer, archive, entry_id, entry.fitness.weighted()


# ---------------------------------------------------------------------------
# evaluate_canary decisions
# ---------------------------------------------------------------------------


async def test_evaluate_promote(setup):
    """Canary fitness well above baseline triggers PROMOTE."""
    deployer, _archive, entry_id, baseline = setup
    result = await deployer.evaluate_canary(entry_id, baseline + 0.10)
    assert result.decision == CanaryDecision.PROMOTE


async def test_evaluate_rollback(setup):
    """Canary fitness well below baseline triggers ROLLBACK."""
    deployer, _archive, entry_id, baseline = setup
    result = await deployer.evaluate_canary(entry_id, baseline - 0.10)
    assert result.decision == CanaryDecision.ROLLBACK


async def test_evaluate_defer(setup):
    """Canary fitness within neutral zone triggers DEFER."""
    deployer, _archive, entry_id, baseline = setup
    # delta = +0.01, inside default [-0.02, +0.05]
    result = await deployer.evaluate_canary(entry_id, baseline + 0.01)
    assert result.decision == CanaryDecision.DEFER


# ---------------------------------------------------------------------------
# promote / rollback side-effects
# ---------------------------------------------------------------------------


async def test_promote_updates_status(setup):
    """After promote, entry status should be 'promoted'."""
    deployer, archive, entry_id, _baseline = setup
    ok = await deployer.promote(entry_id)
    assert ok is True
    entry = await archive.get_entry(entry_id)
    assert entry is not None
    assert entry.status == "promoted"


async def test_rollback_updates_status(setup):
    """After rollback, entry status should be 'rolled_back'."""
    deployer, archive, entry_id, _baseline = setup
    ok = await deployer.rollback(entry_id, reason="regression detected")
    assert ok is True
    entry = await archive.get_entry(entry_id)
    assert entry is not None
    assert entry.status == "rolled_back"


async def test_rollback_stores_reason(setup):
    """Rollback reason should be persisted on the entry."""
    deployer, archive, entry_id, _baseline = setup
    await deployer.rollback(entry_id, reason="p95 latency spike")
    entry = await archive.get_entry(entry_id)
    assert entry is not None
    assert entry.rollback_reason == "p95 latency spike"


# ---------------------------------------------------------------------------
# Missing entry handling
# ---------------------------------------------------------------------------


async def test_missing_entry_promote(setup):
    """Promoting a non-existent entry returns False."""
    deployer, _archive, _entry_id, _baseline = setup
    ok = await deployer.promote("does-not-exist")
    assert ok is False


async def test_missing_entry_rollback(setup):
    """Rolling back a non-existent entry returns False."""
    deployer, _archive, _entry_id, _baseline = setup
    ok = await deployer.rollback("does-not-exist")
    assert ok is False


# ---------------------------------------------------------------------------
# Custom config
# ---------------------------------------------------------------------------


async def test_custom_thresholds(tmp_path):
    """Custom CanaryConfig thresholds change decision boundaries."""
    archive = EvolutionArchive(path=tmp_path / "archive.jsonl")
    await archive.load()

    entry = ArchiveEntry(
        component="test.py",
        change_type="mutation",
        description="test change",
        fitness=_BASELINE_FITNESS,
        status="applied",
    )
    entry_id = await archive.add_entry(entry)
    baseline = entry.fitness.weighted()

    # Very tight promote threshold
    config = CanaryConfig(promote_threshold=0.001, rollback_threshold=-0.001)
    deployer = CanaryDeployer(archive=archive, config=config)

    # +0.01 would be DEFER under defaults but PROMOTE under tight config
    result = await deployer.evaluate_canary(entry_id, baseline + 0.01)
    assert result.decision == CanaryDecision.PROMOTE

    # -0.01 would be DEFER under defaults but ROLLBACK under tight config
    result = await deployer.evaluate_canary(entry_id, baseline - 0.01)
    assert result.decision == CanaryDecision.ROLLBACK


# ---------------------------------------------------------------------------
# Result value correctness
# ---------------------------------------------------------------------------


async def test_canary_result_values(setup):
    """CanaryResult contains accurate delta and fitness values."""
    deployer, _archive, entry_id, baseline = setup
    canary_fitness = baseline + 0.15
    result = await deployer.evaluate_canary(entry_id, canary_fitness)

    assert result.baseline_fitness == pytest.approx(baseline)
    assert result.canary_fitness == pytest.approx(canary_fitness)
    assert result.delta == pytest.approx(0.15)
    assert isinstance(result.reason, str)
    assert len(result.reason) > 0


# ---------------------------------------------------------------------------
# Archive rollback_entry directly
# ---------------------------------------------------------------------------


async def test_archive_rollback_entry(setup):
    """Directly test EvolutionArchive.rollback_entry."""
    _deployer, archive, entry_id, _baseline = setup
    ok = await archive.rollback_entry(entry_id, "direct rollback test")
    assert ok is True
    entry = await archive.get_entry(entry_id)
    assert entry is not None
    assert entry.status == "rolled_back"
    assert entry.rollback_reason == "direct rollback test"


async def test_archive_rollback_missing(setup):
    """rollback_entry returns False for non-existent entry id."""
    _deployer, archive, _entry_id, _baseline = setup
    ok = await archive.rollback_entry("nonexistent-id", "should fail")
    assert ok is False
