"""Economic fitness evaluation for evolution mutations.

Tracks the actual $$ value created by code changes based on:
- API cost savings (fewer/cheaper LLM calls)
- Time savings (faster execution)
- Throughput gains (more tasks/sec)
- Maintenance costs (code complexity)

This extends the existing fitness evaluation with economic ROI measurement,
creating a closed loop: Code changes → Economic impact → Fitness rewards → Darwin selects → Profitable evolution.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Dict

logger = logging.getLogger(__name__)


@dataclass
class EconomicMetrics:
    """Economic impact of a mutation in dollars."""

    api_cost_saved_usd: float        # $ saved on API calls
    time_saved_ms: float             # Latency improvement (milliseconds)
    throughput_gain_pct: float       # Tasks/sec improvement (percentage)
    maintenance_cost_usd: float      # Annual technical debt cost

    def annual_value(self, usage_freq_per_day: int = 1000) -> float:
        """Calculate annual economic value in USD.

        Args:
            usage_freq_per_day: How many times/day this code runs (default 1000)

        Returns:
            Annual ROI in dollars (positive = profitable, negative = costly)

        Formula:
            Daily value = (API savings + time savings + throughput value) * frequency
            Annual value = daily * 250 working days - maintenance cost
        """
        # Convert time savings to $ (assume $0.05/second engineer time)
        time_savings_per_call = (self.time_saved_ms / 1000) * 0.05

        # Throughput gains create business value ($100 per 1% gain)
        throughput_value_per_call = self.throughput_gain_pct * 100

        # Daily value
        daily_api_savings = self.api_cost_saved_usd * usage_freq_per_day
        daily_time_savings = time_savings_per_call * usage_freq_per_day
        daily_throughput_value = throughput_value_per_call * usage_freq_per_day

        # Annual projection (250 working days/year)
        annual_gross = (daily_api_savings + daily_time_savings + daily_throughput_value) * 250

        # Subtract ongoing maintenance cost
        annual_net = annual_gross - self.maintenance_cost_usd

        return annual_net


def evaluate_economic_fitness(
    baseline_jikoku: dict,
    test_jikoku: dict,
    api_costs: Dict[str, float] | None = None,
    usage_freq_per_day: int = 1000
) -> tuple[float, EconomicMetrics]:
    """Calculate economic fitness score [0,1] based on ROI.

    Args:
        baseline_jikoku: Baseline JIKOKU measurement (before mutation)
        test_jikoku: Test JIKOKU measurement (after mutation)
        api_costs: Cost per API call by provider (default: {"claude": 0.015, "gpt4": 0.03})
        usage_freq_per_day: How many times/day this code runs

    Returns:
        Tuple of (fitness_score [0,1], detailed_metrics)

    Fitness score formula:
        annual_value >= $10K → 1.0 (excellent ROI)
        annual_value = $0    → 0.5 (neutral)
        annual_value <= -$10K → 0.0 (costly regression)

    Examples:
        >>> baseline = {"wall_clock_ms": 1000, "api_calls": 5}
        >>> test = {"wall_clock_ms": 500, "api_calls": 3}
        >>> score, metrics = evaluate_economic_fitness(baseline, test)
        >>> # 2x speedup, 2 fewer API calls → high economic value
    """
    if api_costs is None:
        api_costs = {
            "claude": 0.015,  # $0.015/call (Claude Sonnet avg)
            "gpt4": 0.03,     # $0.03/call (GPT-4 avg)
            "openai": 0.02,   # $0.02/call (generic)
        }

    # Extract metrics from JIKOKU data
    baseline_time = baseline_jikoku.get("wall_clock_ms", 0)
    test_time = test_jikoku.get("wall_clock_ms", 0)
    baseline_api_calls = baseline_jikoku.get("api_calls", 0)
    test_api_calls = test_jikoku.get("api_calls", 0)

    # Calculate savings
    time_saved = baseline_time - test_time  # Positive = faster
    api_calls_saved = baseline_api_calls - test_api_calls  # Positive = fewer calls

    # Estimate API cost savings (use average cost if provider unknown)
    avg_api_cost = sum(api_costs.values()) / len(api_costs)
    api_cost_saved = api_calls_saved * avg_api_cost

    # Calculate throughput gain (speedup ratio)
    if test_time > 0 and baseline_time > 0:
        speedup = baseline_time / test_time
        throughput_gain = (speedup - 1.0) * 100  # Convert to percentage
    else:
        throughput_gain = 0.0

    # Estimate maintenance cost based on diff size (technical debt)
    diff_str = test_jikoku.get("diff", "")
    lines_changed = len(diff_str.split("\n")) if diff_str else 0
    # $0.10/line/year for maintenance (industry average)
    maintenance_cost = lines_changed * 0.10

    # Build metrics object
    metrics = EconomicMetrics(
        api_cost_saved_usd=api_cost_saved,
        time_saved_ms=time_saved,
        throughput_gain_pct=throughput_gain,
        maintenance_cost_usd=maintenance_cost
    )

    # Calculate annual value
    annual_value = metrics.annual_value(usage_freq_per_day)

    # Normalize to [0, 1] fitness score
    # annual_value >= $10K → 1.0
    # annual_value = $0 → 0.5
    # annual_value <= -$10K → 0.0
    if annual_value >= 10000:
        fitness = 1.0
    elif annual_value <= -10000:
        fitness = 0.0
    elif annual_value >= 0:
        # Map [0, 10K] → [0.5, 1.0]
        fitness = 0.5 + (annual_value / 20000)
    else:
        # Map [-10K, 0] → [0.0, 0.5]
        fitness = 0.5 + (annual_value / 20000)

    # Clamp to [0, 1]
    fitness = max(0.0, min(1.0, fitness))

    logger.info(
        f"Economic fitness: {fitness:.3f} (annual ROI: ${annual_value:,.2f}, "
        f"API savings: ${api_cost_saved:.2f}/call, time saved: {time_saved:.0f}ms)"
    )

    return fitness, metrics


def format_economic_report(metrics: EconomicMetrics, usage_freq: int = 1000) -> str:
    """Generate human-readable economic impact report.

    Args:
        metrics: Economic metrics to report
        usage_freq: Usage frequency per day

    Returns:
        Formatted report string

    Example:
        Economic Impact Report
        ━━━━━━━━━━━━━━━━━━━━━
        API Cost Savings:    $250.00/year
        Time Savings:        1200ms/call → $15,000/year
        Throughput Gain:     +25% → $6,250/year
        Maintenance Cost:    -$50/year
        ─────────────────────
        Net Annual Value:    $21,450/year
        Payback Period:      Immediate
        ROI:                 42,900%
    """
    annual_value = metrics.annual_value(usage_freq)

    # Calculate daily values
    daily_api = metrics.api_cost_saved_usd * usage_freq * 250
    daily_time = (metrics.time_saved_ms / 1000) * 0.05 * usage_freq * 250
    daily_throughput = metrics.throughput_gain_pct * 100 * usage_freq * 250

    report = f"""Economic Impact Report
━━━━━━━━━━━━━━━━━━━━━
API Cost Savings:    ${daily_api:,.2f}/year ({metrics.api_cost_saved_usd:.4f}/call)
Time Savings:        {metrics.time_saved_ms:.0f}ms/call → ${daily_time:,.2f}/year
Throughput Gain:     +{metrics.throughput_gain_pct:.1f}% → ${daily_throughput:,.2f}/year
Maintenance Cost:    -${metrics.maintenance_cost_usd:,.2f}/year
─────────────────────
Net Annual Value:    ${annual_value:,.2f}/year
"""

    if annual_value > 0:
        report += f"Status:              ✅ PROFITABLE\n"
    elif annual_value < 0:
        report += f"Status:              ❌ COSTLY\n"
    else:
        report += f"Status:              ⚖️ NEUTRAL\n"

    return report
