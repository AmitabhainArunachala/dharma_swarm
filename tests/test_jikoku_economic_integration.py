"""Tests for economic fitness integration with JIKOKU.

Verifies that:
1. Economic fitness can be calculated from JIKOKU session data
2. Metrics are correctly extracted from JIKOKU reports
3. Fitness scoring matches expected ranges
"""

import pytest
from unittest.mock import Mock, AsyncMock

from dharma_swarm.jikoku_fitness import evaluate_economic_fitness_from_jikoku


@pytest.mark.asyncio
async def test_economic_fitness_neutral_when_no_sessions():
    """Test that economic fitness is neutral (0.5) when no session IDs provided."""
    fitness, metrics = await evaluate_economic_fitness_from_jikoku(None, None)

    assert fitness == 0.5
    assert metrics == {}


@pytest.mark.asyncio
async def test_economic_fitness_calculates_from_jikoku_data(monkeypatch):
    """Test economic fitness calculation from JIKOKU session reports."""

    # Mock the tracer
    mock_tracer = Mock()

    # Baseline: slow, many API calls
    baseline_report = {
        "wall_clock_sec": 2.0,
        "api_calls": 5,
        "utilization_pct": 87.0,
    }

    # Test: faster, fewer API calls
    test_report = {
        "wall_clock_sec": 1.0,  # 2x speedup
        "api_calls": 3,         # 2 fewer calls
        "utilization_pct": 226.0,
    }

    mock_tracer.kaizen_report_for_session = Mock()
    mock_tracer.kaizen_report_for_session.side_effect = [baseline_report, test_report]

    def mock_get_tracer():
        return mock_tracer

    # Monkey patch the tracer in jikoku_samaya (where it's defined)
    import dharma_swarm.jikoku_samaya as js
    monkeypatch.setattr(js, "get_global_tracer", mock_get_tracer)

    fitness, metrics = await evaluate_economic_fitness_from_jikoku(
        "baseline_session",
        "test_session",
        usage_freq_per_day=1000
    )

    # Fitness should be positive (improvement)
    assert fitness > 0.5, f"Expected positive fitness, got {fitness}"

    # Metrics should be populated
    assert "annual_value_usd" in metrics
    assert "api_cost_saved" in metrics
    assert "time_saved_ms" in metrics
    assert "throughput_gain_pct" in metrics

    # Time savings: 1000ms faster (2.0s → 1.0s)
    assert metrics["time_saved_ms"] == 1000

    # API cost savings: 2 fewer calls
    # Should be positive (saved money)
    assert metrics["api_cost_saved"] > 0


@pytest.mark.asyncio
async def test_economic_fitness_handles_regression(monkeypatch):
    """Test that economic fitness detects regressions (slower code)."""

    mock_tracer = Mock()

    # Baseline: fast
    baseline_report = {
        "wall_clock_sec": 1.0,
        "api_calls": 3,
        "utilization_pct": 150.0,
    }

    # Test: slower (regression)
    test_report = {
        "wall_clock_sec": 2.0,  # 2x slower
        "api_calls": 5,         # more API calls
        "utilization_pct": 100.0,
    }

    mock_tracer.kaizen_report_for_session = Mock()
    mock_tracer.kaizen_report_for_session.side_effect = [baseline_report, test_report]

    def mock_get_tracer():
        return mock_tracer

    import dharma_swarm.jikoku_samaya as js
    monkeypatch.setattr(js, "get_global_tracer", mock_get_tracer)

    fitness, metrics = await evaluate_economic_fitness_from_jikoku(
        "baseline_session",
        "test_session",
        usage_freq_per_day=1000
    )

    # Fitness should be negative (regression)
    assert fitness < 0.5, f"Expected negative fitness for regression, got {fitness}"

    # Time savings should be negative (got slower)
    assert metrics["time_saved_ms"] < 0

    # API cost savings should be negative (more expensive)
    assert metrics["api_cost_saved"] < 0

    # Annual value should be negative (costly regression)
    assert metrics["annual_value_usd"] < 0


@pytest.mark.asyncio
async def test_economic_fitness_handles_missing_report(monkeypatch):
    """Test graceful handling when JIKOKU report is missing."""

    mock_tracer = Mock()
    mock_tracer.kaizen_report_for_session = Mock(return_value=None)

    def mock_get_tracer():
        return mock_tracer

    import dharma_swarm.jikoku_samaya as js
    monkeypatch.setattr(js, "get_global_tracer", mock_get_tracer)

    fitness, metrics = await evaluate_economic_fitness_from_jikoku(
        "baseline_session",
        "test_session"
    )

    # Should return neutral when report unavailable
    assert fitness == 0.5
    assert metrics == {}
