"""Tests for GraduationEngine — operator autonomy level management."""

import pytest

from dharma_swarm.graduation_engine import (
    AutonomyLevel,
    GraduationEngine,
    RiskLevel,
    _PROMOTE_TO_3_SUCCESSES,
    _PROMOTE_TO_3_MIN_YSD,
    _PROMOTE_TO_4_SUCCESSES,
    _PROMOTE_TO_4_MIN_YSD,
    _DEMOTION_FAILURES,
)


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test_graduation.db"


@pytest.fixture
def engine(tmp_db):
    return GraduationEngine(db_path=tmp_db)


@pytest.mark.asyncio
async def test_init_starts_at_level_2(engine):
    await engine.init_db()
    assert engine.level == AutonomyLevel.HUMAN_ON_LOOP
    assert engine.consecutive_successes == 0
    assert engine.consecutive_failures == 0
    await engine.close()


@pytest.mark.asyncio
async def test_record_success_increments_counter(engine):
    await engine.init_db()
    await engine.record_action("test", success=True, ysd_score=5.1)
    assert engine.consecutive_successes == 1
    assert engine.consecutive_failures == 0
    await engine.close()


@pytest.mark.asyncio
async def test_record_failure_increments_failure_counter(engine):
    await engine.init_db()
    await engine.record_action("test", success=True, ysd_score=5.1)
    await engine.record_action("test", success=False)
    assert engine.consecutive_successes == 0
    assert engine.consecutive_failures == 1
    await engine.close()


@pytest.mark.asyncio
async def test_promote_to_level_3(engine):
    await engine.init_db()
    for _ in range(_PROMOTE_TO_3_SUCCESSES):
        level = await engine.record_action("test", success=True, ysd_score=5.1)

    assert level == AutonomyLevel.AUTONOMOUS_ALERT
    assert engine.level == AutonomyLevel.AUTONOMOUS_ALERT
    await engine.close()


@pytest.mark.asyncio
async def test_no_promote_if_ysd_too_low(engine):
    await engine.init_db()
    for _ in range(_PROMOTE_TO_3_SUCCESSES + 10):
        level = await engine.record_action("test", success=True, ysd_score=5.0)

    # YSD=5.0 < 5.08 threshold, should NOT promote
    assert level == AutonomyLevel.HUMAN_ON_LOOP
    await engine.close()


@pytest.mark.asyncio
async def test_promote_to_level_4(engine):
    await engine.init_db()

    # First promote to level 3
    for _ in range(_PROMOTE_TO_3_SUCCESSES):
        await engine.record_action("test", success=True, ysd_score=5.1)
    assert engine.level == AutonomyLevel.AUTONOMOUS_ALERT

    # Then promote to level 4
    for _ in range(_PROMOTE_TO_4_SUCCESSES):
        level = await engine.record_action("test", success=True, ysd_score=5.12)

    assert level == AutonomyLevel.FULLY_AUTONOMOUS
    await engine.close()


@pytest.mark.asyncio
async def test_demotion_on_consecutive_failures(engine):
    await engine.init_db()

    # Promote to level 3 first
    for _ in range(_PROMOTE_TO_3_SUCCESSES):
        await engine.record_action("test", success=True, ysd_score=5.1)
    assert engine.level == AutonomyLevel.AUTONOMOUS_ALERT

    # 3 failures = demotion
    for _ in range(_DEMOTION_FAILURES):
        level = await engine.record_action("test", success=False)

    assert level == AutonomyLevel.HUMAN_ON_LOOP
    await engine.close()


@pytest.mark.asyncio
async def test_gate_block_causes_immediate_demotion(engine):
    await engine.init_db()

    # Promote to level 3
    for _ in range(_PROMOTE_TO_3_SUCCESSES):
        await engine.record_action("test", success=True, ysd_score=5.1)
    assert engine.level == AutonomyLevel.AUTONOMOUS_ALERT

    # Single gate block = demotion
    level = await engine.record_action("test", success=True, gate_blocked=True)
    assert level == AutonomyLevel.HUMAN_ON_LOOP
    await engine.close()


@pytest.mark.asyncio
async def test_cannot_demote_below_level_2(engine):
    await engine.init_db()
    assert engine.level == AutonomyLevel.HUMAN_ON_LOOP

    for _ in range(10):
        await engine.record_action("test", success=False)

    assert engine.level == AutonomyLevel.HUMAN_ON_LOOP
    await engine.close()


# -- should_require_approval tests --

@pytest.mark.asyncio
async def test_approval_level_2(engine):
    await engine.init_db()
    assert engine.level == AutonomyLevel.HUMAN_ON_LOOP

    assert not engine.should_require_approval(RiskLevel.LOW)
    assert engine.should_require_approval(RiskLevel.MEDIUM)
    assert engine.should_require_approval(RiskLevel.HIGH)
    assert engine.should_require_approval(RiskLevel.CRITICAL)
    await engine.close()


@pytest.mark.asyncio
async def test_approval_level_3(engine):
    await engine.init_db()

    # Promote to 3
    for _ in range(_PROMOTE_TO_3_SUCCESSES):
        await engine.record_action("test", success=True, ysd_score=5.1)

    assert not engine.should_require_approval(RiskLevel.LOW)
    assert not engine.should_require_approval(RiskLevel.MEDIUM)
    assert engine.should_require_approval(RiskLevel.HIGH)
    assert engine.should_require_approval(RiskLevel.CRITICAL)
    await engine.close()


@pytest.mark.asyncio
async def test_approval_level_4(engine):
    await engine.init_db()

    # Promote to 3 then 4
    for _ in range(_PROMOTE_TO_3_SUCCESSES):
        await engine.record_action("test", success=True, ysd_score=5.1)
    for _ in range(_PROMOTE_TO_4_SUCCESSES):
        await engine.record_action("test", success=True, ysd_score=5.12)

    assert not engine.should_require_approval(RiskLevel.LOW)
    assert not engine.should_require_approval(RiskLevel.MEDIUM)
    assert not engine.should_require_approval(RiskLevel.HIGH)
    # CRITICAL always needs approval — hardcoded
    assert engine.should_require_approval(RiskLevel.CRITICAL)
    await engine.close()


@pytest.mark.asyncio
async def test_mean_ysd_calculation(engine):
    await engine.init_db()
    assert engine.mean_ysd == 5.0  # Default with no data

    await engine.record_action("test", success=True, ysd_score=5.10)
    await engine.record_action("test", success=True, ysd_score=5.12)
    assert abs(engine.mean_ysd - 5.11) < 0.001
    await engine.close()


@pytest.mark.asyncio
async def test_status_dict(engine):
    await engine.init_db()
    status = engine.status_dict()
    assert status["level"] == "HUMAN_ON_LOOP"
    assert status["level_value"] == 2
    assert status["consecutive_successes"] == 0
    await engine.close()


@pytest.mark.asyncio
async def test_persistence_across_connections(tmp_db):
    """State survives close + reopen."""
    eng1 = GraduationEngine(db_path=tmp_db)
    await eng1.init_db()
    for _ in range(10):
        await eng1.record_action("test", success=True, ysd_score=5.1)
    await eng1.close()

    eng2 = GraduationEngine(db_path=tmp_db)
    await eng2.init_db()
    assert eng2.consecutive_successes == 10
    assert eng2.level == AutonomyLevel.HUMAN_ON_LOOP
    await eng2.close()
