"""Tests for perception_action_loop.py — the endogenous heartbeat."""

import asyncio

import pytest

from dharma_swarm.perception_action_loop import (
    CandidateAction,
    LoopConfig,
    Percept,
    PerceptionActionLoop,
    PerceptionModality,
    WorldModel,
)


@pytest.fixture
def config():
    return LoopConfig(
        base_period_seconds=60.0,
        min_period_seconds=10.0,
        max_period_seconds=600.0,
    )


@pytest.fixture
def loop(config):
    return PerceptionActionLoop(config=config)


# ---- Precision mechanics ----

def test_initial_precision(loop):
    """Precision starts at configured initial value."""
    assert loop.precision == 0.5


def test_precision_increases_on_small_error(loop):
    """Small prediction errors increase precision."""
    initial = loop.precision
    loop._update_precision(0.1)  # Small error
    assert loop.precision > initial


def test_precision_decreases_on_large_error(loop):
    """Large prediction errors decrease precision."""
    loop.precision = 0.8
    loop._update_precision(0.9)  # Large error
    assert loop.precision < 0.8


def test_precision_bounded(loop):
    """Precision stays within [0.05, 0.95]."""
    for _ in range(100):
        loop._update_precision(0.0)  # Perfect predictions
    assert loop.precision <= 0.95

    for _ in range(100):
        loop._update_precision(1.0)  # Maximum error
    assert loop.precision >= 0.05


# ---- Period mechanics ----

def test_period_shortens_with_low_precision(loop):
    """Low precision (surprised) → shorter period → faster sensing."""
    loop.precision = 0.9
    high_prec_period = loop.current_period
    loop.precision = 0.2
    low_prec_period = loop.current_period
    assert low_prec_period < high_prec_period


def test_period_bounded(loop):
    """Period stays within min/max bounds."""
    loop.precision = 0.01
    assert loop.current_period >= loop.config.min_period_seconds

    loop.precision = 0.99
    assert loop.current_period <= loop.config.max_period_seconds


# ---- World model ----

def test_world_model_prediction_error():
    """World model computes aggregate prediction error."""
    model = WorldModel()
    model.expected_daemon_alive = {"dharma_swarm": True}
    model.observed_daemon_alive = {"dharma_swarm": False}
    error = model.compute_prediction_error()
    assert error > 0.0


def test_world_model_no_error():
    """Zero error when observations match expectations."""
    model = WorldModel()
    model.expected_daemon_alive = {"dharma_swarm": True}
    model.observed_daemon_alive = {"dharma_swarm": True}
    model.expected_stigmergy_density = 50
    model.observed_stigmergy_density = 50
    error = model.compute_prediction_error()
    assert error == 0.0


def test_world_model_update_expectations():
    """Expectations track observations."""
    model = WorldModel()
    model.expected_stigmergy_density = 50
    model.observed_stigmergy_density = 100
    model.update_expectations()
    # Should move toward observed (0.7 * 100 + 0.3 * 50 = 85)
    assert model.expected_stigmergy_density == 85


# ---- Perceive ----

@pytest.mark.asyncio
async def test_perceive_with_sensor(config):
    """PERCEIVE phase collects from sensors."""
    async def mock_sensor():
        return [
            Percept(
                modality=PerceptionModality.HEALTH,
                observation="test health check",
                salience=0.8,
            ),
        ]

    loop = PerceptionActionLoop(config=config, sensors=[mock_sensor])
    percepts = await loop.perceive()
    assert len(percepts) == 1
    assert percepts[0].salience == 0.8


@pytest.mark.asyncio
async def test_perceive_filters_low_salience(config):
    """Low-salience percepts are filtered out."""
    async def noisy_sensor():
        return [
            Percept(modality=PerceptionModality.HEALTH, salience=0.1, observation="low"),
            Percept(modality=PerceptionModality.HEALTH, salience=0.8, observation="high"),
        ]

    loop = PerceptionActionLoop(
        config=LoopConfig(salience_threshold=0.5),
        sensors=[noisy_sensor],
    )
    percepts = await loop.perceive()
    assert len(percepts) == 1
    assert percepts[0].observation == "high"


# ---- Deliberate ----

@pytest.mark.asyncio
async def test_deliberate_generates_candidates(loop):
    """DELIBERATE converts percepts to candidates."""
    percepts = [
        Percept(
            modality=PerceptionModality.HEALTH,
            observation="daemon dead",
            salience=0.9,
            data={"target": "dharma_swarm"},
        ),
    ]
    candidates = await loop.deliberate(percepts)
    assert len(candidates) == 1
    assert candidates[0].action_type == "health_check"


# ---- Commit ----

@pytest.mark.asyncio
@pytest.mark.real_budget
async def test_commit_respects_budget(config):
    """COMMIT skips when budget exhausted."""
    from dharma_swarm.cost_ledger import BudgetConfig, CostLedger, InvocationCost

    ledger = CostLedger(budget=BudgetConfig(daily_limit_usd=0.01))
    ledger.record(InvocationCost(cost_usd=1.0))  # Way over budget

    loop = PerceptionActionLoop(config=config, cost_ledger=ledger)
    result = await loop.commit(CandidateAction(action_type="test"))
    assert result["skipped"] is True
    assert result["reason"] == "budget_exhausted"


@pytest.mark.asyncio
async def test_commit_preserves_handler_non_execution(config, tmp_path):
    """COMMIT should preserve an explicit executed=False result from the handler."""
    from dharma_swarm.cost_ledger import BudgetConfig, CostLedger

    async def non_executing_handler(candidate):
        del candidate
        return {"executed": False, "reason": "noop"}

    loop = PerceptionActionLoop(
        config=config,
        action_handler=non_executing_handler,
        cost_ledger=CostLedger(base_dir=tmp_path, budget=BudgetConfig(daily_limit_usd=5.0)),
    )
    result = await loop.commit(CandidateAction(action_type="test", target="noop.txt"))

    assert result["executed"] is False
    assert result["reason"] == "noop"
    assert loop.total_actions_taken == 0


@pytest.mark.asyncio
async def test_commit_defaults_missing_executed_to_success(config, tmp_path):
    """COMMIT should preserve legacy handlers that omit the executed flag."""
    from dharma_swarm.cost_ledger import BudgetConfig, CostLedger

    async def legacy_handler(candidate):
        del candidate
        return {"output": "done"}

    loop = PerceptionActionLoop(
        config=config,
        action_handler=legacy_handler,
        cost_ledger=CostLedger(base_dir=tmp_path, budget=BudgetConfig(daily_limit_usd=5.0)),
    )
    result = await loop.commit(CandidateAction(action_type="test", target="ok.txt"))

    assert result["executed"] is True
    assert result["output"] == "done"
    assert loop.total_actions_taken == 1


@pytest.mark.asyncio
async def test_commit_records_non_executed_handler_as_error(config, tmp_path):
    """COMMIT should record non-executed handler results as non-success for loop detection."""
    from dharma_swarm.cost_ledger import BudgetConfig, CostLedger

    async def non_executing_handler(candidate):
        del candidate
        return {"executed": False, "error": "skipped_by_handler"}

    loop = PerceptionActionLoop(
        config=config,
        action_handler=non_executing_handler,
        cost_ledger=CostLedger(base_dir=tmp_path, budget=BudgetConfig(daily_limit_usd=5.0)),
    )
    await loop.commit(CandidateAction(action_type="test", target="noop.txt"))

    recorded = loop.loop_detector.window[-1]
    assert recorded.result == "error"
    assert recorded.error_type == "skipped_by_handler"


# ---- Verify ----

@pytest.mark.asyncio
async def test_verify_updates_precision_and_world_model_once(config, monkeypatch):
    """VERIFY applies prediction error and updates expectations once."""
    loop = PerceptionActionLoop(config=config)
    candidate = CandidateAction(action_type="write", target="foo.py")
    initial_precision = loop.precision

    async def fake_verify_action(**kwargs):
        assert kwargs["action_id"] == candidate.id
        assert kwargs["action_type"] == "write"
        assert kwargs["target"] == "foo.py"

        class _Verification:
            prediction_error = 0.25

        return _Verification()

    monkeypatch.setattr(
        "dharma_swarm.perception_action_loop.verify_action",
        fake_verify_action,
    )

    prediction_error = await loop.verify(candidate, {"executed": True})

    assert prediction_error == 0.25
    assert loop.precision != initial_precision
    assert loop.world_model.total_prediction_errors == pytest.approx(0.25)
    assert loop.world_model.update_count == 1


@pytest.mark.asyncio
async def test_verify_non_executed_action_still_updates_precision(config):
    """VERIFY treats non-executed actions as uncertainty instead of no-op."""
    loop = PerceptionActionLoop(config=config)
    # Start at non-equilibrium precision so the update is visible
    loop.precision = 0.8
    initial_precision = loop.precision

    prediction_error = await loop.verify(CandidateAction(action_type="test"), {"executed": False})

    assert prediction_error == 0.5
    # error=0.5 → target=0.5, alpha=0.3 → 0.7*0.8 + 0.3*0.5 = 0.71
    assert loop.precision != initial_precision
    assert loop.precision < initial_precision  # Moved toward 0.5
    assert loop.world_model.total_prediction_errors == pytest.approx(0.5)
    assert loop.world_model.update_count == 0


@pytest.mark.asyncio
async def test_verify_degrades_gracefully_when_verifier_raises(config, monkeypatch):
    """VERIFY should not crash the whole cycle when the verifier fails."""
    loop = PerceptionActionLoop(config=config)
    loop.precision = 0.8
    initial_precision = loop.precision

    async def failing_verify_action(**kwargs):
        del kwargs
        raise RuntimeError("verifier backend unavailable")

    monkeypatch.setattr(
        "dharma_swarm.perception_action_loop.verify_action",
        failing_verify_action,
    )

    prediction_error = await loop.verify(
        CandidateAction(action_type="write", target="foo.py"),
        {"executed": True},
    )

    assert prediction_error == 1.0
    assert loop.precision != initial_precision
    assert loop.precision_history[-1] == loop.precision
    assert loop.world_model.total_prediction_errors == pytest.approx(1.0)
    assert loop.world_model.update_count == 0


@pytest.mark.asyncio
async def test_verify_failed_result_does_not_update_world_model(config, monkeypatch):
    """VERIFY should not advance expectations when explicit verification fails."""
    from dharma_swarm.environmental_verifier import VerificationResult, VerificationStatus

    loop = PerceptionActionLoop(config=config)
    loop.precision = 0.8
    initial_precision = loop.precision

    async def failed_verify_action(**kwargs):
        del kwargs
        return VerificationResult(
            action_id="act-fail",
            overall=VerificationStatus.FAIL,
            prediction_error=1.0,
        )

    monkeypatch.setattr(
        "dharma_swarm.perception_action_loop.verify_action",
        failed_verify_action,
    )

    prediction_error = await loop.verify(
        CandidateAction(action_type="write", target="broken.py"),
        {"executed": True},
    )

    assert prediction_error == 1.0
    assert loop.precision != initial_precision
    assert loop.world_model.total_prediction_errors == pytest.approx(1.0)
    assert loop.world_model.update_count == 0


# ---- Status ----

def test_status(loop):
    """Status returns meaningful info."""
    status = loop.status()
    assert "precision" in status
    assert "cycle_count" in status
    assert "current_period_seconds" in status
    assert status["cycle_count"] == 0


# ---- State persistence ----

def test_save_and_load_state(loop, tmp_path):
    """Loop state persists across restarts."""
    loop._state_dir = tmp_path
    loop.precision = 0.77
    loop.cycle_count = 42
    loop._save_cycle_state()

    new_loop = PerceptionActionLoop()
    new_loop._state_dir = tmp_path
    assert new_loop.load_state()
    assert new_loop.precision == 0.77
    assert new_loop.cycle_count == 42
