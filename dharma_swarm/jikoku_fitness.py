"""JIKOKU fitness evaluators - performance metrics for evolution.

Integrates JIKOKU measurement data into fitness evaluation,
creating a closed feedback loop:
  Code changes → JIKOKU measures → Fitness rewards → Darwin selects → Better code

Three fitness dimensions:
  1. performance: Wall clock speedup (0.0 = slower, 1.0 = 2x+ faster)
  2. utilization: Concurrent execution (0.0 = worse, 1.0 = high parallelism)
  3. economic_value: Real $ ROI from API savings, time savings, throughput gains
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dharma_swarm.evolution import Proposal

logger = logging.getLogger(__name__)


def evaluate_performance_improvement(
    baseline_wall_clock: float,
    test_wall_clock: float,
) -> float:
    """Evaluate wall clock speedup from JIKOKU measurements.

    Args:
        baseline_wall_clock: Baseline session wall clock time (seconds)
        test_wall_clock: Test session wall clock time (seconds)

    Returns:
        Fitness score [0.0, 1.0]:
            0.0 = Regression (10%+ slower)
            0.5 = No change (within ±10%)
            1.0 = Significant speedup (2x+ faster)

    Formula:
        speedup = baseline / test
        score = (speedup - 0.9) / 1.1, clamped to [0.0, 1.0]

    Examples:
        baseline=289ms, test=180ms → speedup=1.61 → score=0.64
        baseline=100ms, test=50ms  → speedup=2.0  → score=1.0
        baseline=100ms, test=150ms → speedup=0.67 → score=0.0
    """
    if test_wall_clock <= 0:
        logger.warning("Invalid test_wall_clock: %s, returning neutral", test_wall_clock)
        return 0.5

    speedup = baseline_wall_clock / test_wall_clock

    # Map speedup to [0, 1]
    if speedup < 0.9:
        # Regression: >10% slower
        return 0.0
    elif speedup > 2.0:
        # Excellent: 2x+ speedup
        return 1.0
    else:
        # Linear scale: 0.9x → 0.0, 2.0x → 1.0
        return (speedup - 0.9) / 1.1


def evaluate_utilization_improvement(
    baseline_utilization: float,
    test_utilization: float,
) -> float:
    """Evaluate utilization (concurrent execution) from JIKOKU measurements.

    Args:
        baseline_utilization: Baseline session utilization % (0-300+)
        test_utilization: Test session utilization % (0-300+)

    Returns:
        Fitness score [0.0, 1.0]:
            0.0 = Utilization decreased significantly
            0.5 = No change
            1.0 = High parallel execution achieved

    Formula:
        improvement = test - baseline
        score = 0.5 + (improvement / 200), clamped to [0.0, 1.0]

    Examples:
        baseline=87%, test=226% → improvement=+139% → score=1.0 (clamped)
        baseline=100%, test=100% → improvement=0% → score=0.5
        baseline=200%, test=100% → improvement=-100% → score=0.0
    """
    improvement = test_utilization - baseline_utilization

    # Map improvement to [0, 1]
    # -100% improvement → 0.0
    # 0% improvement → 0.5
    # +100% improvement → 1.0
    score = 0.5 + (improvement / 200)

    # Clamp to [0, 1]
    return max(0.0, min(1.0, score))


async def evaluate_jikoku_metrics(
    proposal: Proposal,
    baseline_session_id: str | None = None,
    test_session_id: str | None = None,
) -> tuple[float, float]:
    """Evaluate both JIKOKU fitness dimensions from session data.

    Args:
        proposal: The proposal being evaluated
        baseline_session_id: JIKOKU session ID before the change
        test_session_id: JIKOKU session ID after the change

    Returns:
        (performance_score, utilization_score) tuple

    If session IDs are not provided, returns neutral scores (0.5, 0.5).
    """
    # If no JIKOKU sessions provided, return neutral
    if not baseline_session_id or not test_session_id:
        logger.debug(
            "No JIKOKU sessions for proposal %s, using neutral perf scores",
            proposal.id[:8],
        )
        return (0.5, 0.5)

    try:
        from dharma_swarm.jikoku_samaya import get_global_tracer

        tracer = get_global_tracer()

        # Get baseline metrics
        baseline_report = tracer.kaizen_report_for_session(baseline_session_id)
        if not baseline_report or "error" in baseline_report:
            logger.warning(
                "Failed to get baseline JIKOKU report for session %s",
                baseline_session_id,
            )
            return (0.5, 0.5)

        # Get test metrics
        test_report = tracer.kaizen_report_for_session(test_session_id)
        if not test_report or "error" in test_report:
            logger.warning(
                "Failed to get test JIKOKU report for session %s",
                test_session_id,
            )
            return (0.5, 0.5)

        # Extract metrics
        baseline_wall_clock = baseline_report.get("wall_clock_sec", 0.0)
        test_wall_clock = test_report.get("wall_clock_sec", 0.0)
        baseline_util = baseline_report.get("utilization_pct", 0.0)
        test_util = test_report.get("utilization_pct", 0.0)

        # Evaluate dimensions
        performance = evaluate_performance_improvement(
            baseline_wall_clock, test_wall_clock
        )
        utilization = evaluate_utilization_improvement(baseline_util, test_util)

        logger.info(
            "JIKOKU fitness for %s: perf=%.3f (%.0fms→%.0fms), util=%.3f (%.0f%%→%.0f%%)",
            proposal.id[:8],
            performance,
            baseline_wall_clock * 1000,
            test_wall_clock * 1000,
            utilization,
            baseline_util,
            test_util,
        )

        return (performance, utilization)

    except Exception as e:
        logger.error("Failed to evaluate JIKOKU metrics: %s", e, exc_info=True)
        return (0.5, 0.5)  # Return neutral on error


async def evaluate_economic_fitness_from_jikoku(
    baseline_session_id: str | None,
    test_session_id: str | None,
    usage_freq_per_day: int = 1000,
) -> tuple[float, dict]:
    """Evaluate economic fitness from JIKOKU session data.

    Args:
        baseline_session_id: JIKOKU session ID before the change
        test_session_id: JIKOKU session ID after the change
        usage_freq_per_day: Expected usage frequency per day (default 1000)

    Returns:
        Tuple of (economic_fitness [0,1], metrics_dict)

    This integrates dharma_swarm.economic_fitness with JIKOKU measurements,
    calculating real dollar ROI from:
    - API cost savings (fewer/cheaper LLM calls)
    - Time savings (faster wall clock)
    - Throughput gains (higher utilization)
    - Maintenance costs (diff size penalty)
    """
    if not baseline_session_id or not test_session_id:
        logger.debug("No JIKOKU sessions provided, using neutral economic fitness")
        return (0.5, {})

    try:
        from dharma_swarm.jikoku_samaya import get_global_tracer
        from dharma_swarm.economic_fitness import evaluate_economic_fitness

        tracer = get_global_tracer()

        # Get baseline report
        baseline_report = tracer.kaizen_report_for_session(baseline_session_id)
        if not baseline_report or "error" in baseline_report:
            logger.warning("Failed to get baseline report for %s", baseline_session_id)
            return (0.5, {})

        # Get test report
        test_report = tracer.kaizen_report_for_session(test_session_id)
        if not test_report or "error" in test_report:
            logger.warning("Failed to get test report for %s", test_session_id)
            return (0.5, {})

        # Build JIKOKU dicts for economic evaluation
        baseline_jikoku = {
            "wall_clock_ms": baseline_report.get("wall_clock_sec", 0) * 1000,
            "api_calls": baseline_report.get("api_calls", 0),
        }
        test_jikoku = {
            "wall_clock_ms": test_report.get("wall_clock_sec", 0) * 1000,
            "api_calls": test_report.get("api_calls", 0),
            "diff": "",  # Diff not available from JIKOKU, would need to pass separately
        }

        # Evaluate economic fitness
        fitness, metrics = evaluate_economic_fitness(
            baseline_jikoku, test_jikoku, usage_freq_per_day=usage_freq_per_day
        )

        metrics_dict = {
            "annual_value_usd": metrics.annual_value(usage_freq_per_day),
            "api_cost_saved": metrics.api_cost_saved_usd,
            "time_saved_ms": metrics.time_saved_ms,
            "throughput_gain_pct": metrics.throughput_gain_pct,
            "maintenance_cost": metrics.maintenance_cost_usd,
        }

        logger.info(
            "Economic fitness: %.3f (annual ROI: $%.2f, API: $%.4f/call, time: %.0fms)",
            fitness,
            metrics_dict["annual_value_usd"],
            metrics.api_cost_saved_usd,
            metrics.time_saved_ms,
        )

        return (fitness, metrics_dict)

    except Exception as e:
        logger.error("Failed to evaluate economic fitness: %s", e, exc_info=True)
        return (0.5, {})
