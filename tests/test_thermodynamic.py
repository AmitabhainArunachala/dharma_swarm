"""Tests for dharma_swarm.thermodynamic -- ThermodynamicMonitor."""

import json

import pytest

from dharma_swarm.thermodynamic import (
    DOMAIN_BUDGETS,
    EfficiencyReading,
    ThermodynamicMonitor,
)


# ---------------------------------------------------------------------------
# Basic recording
# ---------------------------------------------------------------------------


def test_record_first_iteration():
    """First record sets EMA equal to raw efficiency."""
    mon = ThermodynamicMonitor()
    reading = mon.record(quality_delta=0.5, tokens_used=1000)

    assert reading.iteration == 0
    assert reading.efficiency == pytest.approx(0.5 / 1000, abs=1e-9)
    # First iteration: EMA == raw efficiency
    assert reading.ema_efficiency == pytest.approx(0.5 / 1000, abs=1e-9)
    assert mon.current_ema == pytest.approx(0.5 / 1000, abs=1e-9)


def test_warmup_exempt():
    """First 2 iterations never suggest stop, even with zero quality delta."""
    mon = ThermodynamicMonitor()
    r0 = mon.record(quality_delta=0.0, tokens_used=100)
    r1 = mon.record(quality_delta=0.0, tokens_used=100)

    assert not r0.should_stop
    assert not r1.should_stop
    assert r0.stop_reason == ""
    assert r1.stop_reason == ""


# ---------------------------------------------------------------------------
# Stopping criteria
# ---------------------------------------------------------------------------


def test_carnot_limit_triggers():
    """EMA below 1e-7 after warmup triggers Carnot stop."""
    mon = ThermodynamicMonitor()
    # Warmup with tiny efficiency
    mon.record(quality_delta=0.0, tokens_used=1000)
    mon.record(quality_delta=0.0, tokens_used=1000)
    # Post-warmup: still zero efficiency
    r = mon.record(quality_delta=0.0, tokens_used=1000)

    assert r.should_stop is True
    assert "Carnot limit" in r.stop_reason


def test_diminishing_returns():
    """3 consecutive sub-epsilon iterations after warmup triggers stop."""
    mon = ThermodynamicMonitor()
    # Warmup with real progress
    mon.record(quality_delta=1.0, tokens_used=100)
    mon.record(quality_delta=1.0, tokens_used=100)
    # 3 sub-epsilon iterations post-warmup
    mon.record(quality_delta=0.0001, tokens_used=100)
    mon.record(quality_delta=0.0001, tokens_used=100)
    r = mon.record(quality_delta=0.0001, tokens_used=100)

    assert r.should_stop is True
    assert "Diminishing returns" in r.stop_reason


def test_no_stop_with_progress():
    """Good quality deltas do not trigger stop."""
    mon = ThermodynamicMonitor()
    for i in range(10):
        r = mon.record(quality_delta=0.5, tokens_used=100)
        assert r.should_stop is False


# ---------------------------------------------------------------------------
# EMA smoothing
# ---------------------------------------------------------------------------


def test_ema_smoothing():
    """EMA updates correctly with the configured alpha."""
    alpha = ThermodynamicMonitor.EMA_ALPHA
    mon = ThermodynamicMonitor()

    r0 = mon.record(quality_delta=1.0, tokens_used=100)
    eff0 = 1.0 / 100
    assert r0.ema_efficiency == pytest.approx(eff0, abs=1e-9)

    r1 = mon.record(quality_delta=0.0, tokens_used=100)
    eff1 = 0.0
    expected_ema = alpha * eff1 + (1 - alpha) * eff0
    assert r1.ema_efficiency == pytest.approx(expected_ema, abs=1e-9)


# ---------------------------------------------------------------------------
# Domain budgets
# ---------------------------------------------------------------------------


def test_domain_budgets():
    """DOMAIN_BUDGETS contains the expected domains."""
    expected = {"evolution", "autoresearch", "pulse", "cascade", "recognition", "audit"}
    assert set(DOMAIN_BUDGETS.keys()) == expected


def test_suggest_reallocation():
    """Suggests increased budget for an efficient domain."""
    mon = ThermodynamicMonitor(domain="evolution")
    mon.record(quality_delta=1.0, tokens_used=100)  # positive efficiency

    suggestions = mon.suggest_budget_reallocation()
    # evolution baseline is 1.0; positive efficiency -> 1.5
    assert suggestions["evolution"] == pytest.approx(1.5)
    # Other domains unchanged
    assert suggestions["pulse"] == pytest.approx(DOMAIN_BUDGETS["pulse"])


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_save_load(tmp_path):
    """save() then load() preserves readings and EMA."""
    persist = tmp_path / "eff.json"
    mon = ThermodynamicMonitor(domain="audit", persist_path=persist)
    mon.record(quality_delta=0.5, tokens_used=200)
    mon.record(quality_delta=0.3, tokens_used=150)
    mon.save()

    assert persist.exists()

    mon2 = ThermodynamicMonitor(domain="audit", persist_path=persist)
    assert mon2.load() is True
    assert len(mon2.readings) == 2
    assert mon2.readings[0].quality_delta == pytest.approx(0.5)
    assert mon2.readings[1].quality_delta == pytest.approx(0.3)
    assert mon2.current_ema == pytest.approx(mon.current_ema)


# ---------------------------------------------------------------------------
# Properties and reset
# ---------------------------------------------------------------------------


def test_total_tokens():
    """total_tokens tracks the sum across all recorded iterations."""
    mon = ThermodynamicMonitor()
    mon.record(quality_delta=0.1, tokens_used=100)
    mon.record(quality_delta=0.2, tokens_used=250)
    mon.record(quality_delta=0.05, tokens_used=50)

    assert mon.total_tokens == 400


def test_reset():
    """reset() clears all state."""
    mon = ThermodynamicMonitor()
    mon.record(quality_delta=0.5, tokens_used=100)
    mon.record(quality_delta=0.3, tokens_used=200)
    mon.reset()

    assert len(mon.readings) == 0
    assert mon.current_ema == 0.0
    assert mon.total_tokens == 0


def test_zero_tokens():
    """Handles zero tokens gracefully (efficiency = 0)."""
    mon = ThermodynamicMonitor()
    r = mon.record(quality_delta=1.0, tokens_used=0)

    assert r.efficiency == 0.0
    assert r.ema_efficiency == 0.0
    assert not r.should_stop
