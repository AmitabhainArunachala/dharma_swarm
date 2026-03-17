"""Tests for Ginko orchestrator."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

_temp_dir = tempfile.mkdtemp()
os.environ.setdefault("DHARMA_HOME", _temp_dir)

from dharma_swarm.ginko_orchestrator import (
    AUTONOMY_REQUIREMENTS,
    GinkoState,
    check_autonomy_advancement,
    check_telos_gates,
    compute_position_size,
    ginko_status,
    load_state,
    save_state,
    STATE_FILE,
)


@pytest.fixture(autouse=True)
def clean_state():
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    yield
    if STATE_FILE.exists():
        STATE_FILE.unlink()


class TestGinkoState:
    def test_default_state(self):
        state = GinkoState()
        assert state.autonomy_stage == 1
        assert state.current_regime == "unknown"
        assert state.edge_validated is False

    def test_save_load(self):
        state = GinkoState(
            autonomy_stage=2,
            current_regime="bull",
            regime_confidence=0.85,
            total_predictions=100,
        )
        save_state(state)
        loaded = load_state()
        assert loaded.autonomy_stage == 2
        assert loaded.current_regime == "bull"
        assert loaded.total_predictions == 100

    def test_load_missing(self):
        """Loading when no state file → default state."""
        state = load_state()
        assert state.autonomy_stage == 1


class TestTelosGates:
    def test_ahimsa_pass(self):
        results = check_telos_gates("execute_trade", {"position_pct": 2.0})
        assert results["AHIMSA"] == "pass"

    def test_ahimsa_warn(self):
        results = check_telos_gates("execute_trade", {"position_pct": 4.0})
        assert results["AHIMSA"] == "warn"

    def test_ahimsa_fail(self):
        results = check_telos_gates("execute_trade", {"position_pct": 6.0})
        assert results["AHIMSA"] == "fail"

    def test_reversibility_pass(self):
        results = check_telos_gates("execute_trade", {
            "position_pct": 1.0,
            "can_exit_24h": True,
        })
        assert results["REVERSIBILITY"] == "pass"

    def test_reversibility_fail(self):
        results = check_telos_gates("execute_trade", {
            "position_pct": 1.0,
            "can_exit_24h": False,
        })
        assert results["REVERSIBILITY"] == "fail"

    def test_satya_always_passes(self):
        results = check_telos_gates("generate_report", {})
        assert results["SATYA"] == "pass"

    def test_non_trade_action(self):
        """Non-trade actions should have no AHIMSA gate."""
        results = check_telos_gates("generate_report", {})
        assert "AHIMSA" not in results


class TestAutonomyAdvancement:
    def test_stage_1_to_2_blocked(self):
        state = GinkoState(autonomy_stage=1, resolved_predictions=50)
        result = check_autonomy_advancement(state)
        assert result["can_advance"] is False
        assert len(result["unmet"]) > 0

    def test_stage_1_to_2_ready(self):
        state = GinkoState(
            autonomy_stage=1,
            resolved_predictions=150,
            brier_score=0.15,
        )
        result = check_autonomy_advancement(state)
        assert result["can_advance"] is True
        assert result["next_stage"] == 2

    def test_stage_2_to_3_blocked(self):
        state = GinkoState(
            autonomy_stage=2,
            resolved_predictions=200,
            brier_score=0.15,  # Too high for stage 3
        )
        result = check_autonomy_advancement(state)
        assert result["can_advance"] is False

    def test_stage_5_no_further(self):
        state = GinkoState(autonomy_stage=5)
        result = check_autonomy_advancement(state)
        assert result["can_advance"] is False

    def test_requirements_exist(self):
        for stage in (2, 3, 4, 5):
            assert stage in AUTONOMY_REQUIREMENTS


class TestPositionSizing:
    def test_half_kelly(self):
        result = compute_position_size(
            win_rate=0.60,
            avg_win=0.02,
            avg_loss=0.01,
            capital=10000,
        )
        assert result["kelly_fraction"] > 0
        assert result["half_kelly"] > 0
        assert result["half_kelly"] < result["kelly_fraction"]
        assert result["position_size_usd"] > 0

    def test_max_position_cap(self):
        """Position should never exceed max_position_pct."""
        result = compute_position_size(
            win_rate=0.90,
            avg_win=0.10,
            avg_loss=0.01,
            capital=10000,
            max_position_pct=0.05,
        )
        assert result["position_pct"] <= 5.0

    def test_zero_edge(self):
        """With zero avg_win → no position."""
        result = compute_position_size(
            win_rate=0.50,
            avg_win=0.0,
            avg_loss=0.01,
            capital=10000,
        )
        assert result["position_size_usd"] == 0

    def test_losing_strategy(self):
        """Negative Kelly → zero position."""
        result = compute_position_size(
            win_rate=0.30,
            avg_win=0.01,
            avg_loss=0.03,
            capital=10000,
        )
        assert result["half_kelly"] == 0
        assert result["position_size_usd"] == 0


class TestGinkoStatus:
    def test_status_output(self):
        status = ginko_status()
        assert "Shakti Ginko" in status
        assert "Autonomy stage" in status
        assert "Brier" in status

    def test_status_with_state(self):
        state = GinkoState(
            autonomy_stage=2,
            current_regime="bull",
            regime_confidence=0.9,
            total_predictions=200,
            resolved_predictions=180,
            brier_score=0.11,
        )
        save_state(state)
        status = ginko_status()
        assert "2/5" in status
        assert "bull" in status
        assert "0.11" in status
