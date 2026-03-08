"""
Statistical analysis tools for JIKOKU SAMAYA kaizen methodology.

Implements rigorous metrics from KAIZEN_EFFICIENCY_ANALYSIS.md:
- Bootstrap confidence intervals for utilization
- Statistical Process Control (SPC) anomaly detection
- Mann-Kendall trend testing
- ROI-based optimization prioritization
- Pareto analysis (80/20 rule)
- PDCA cycle validation
"""

import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from scipy import stats


@dataclass
class UtilizationCI:
    """Bootstrap confidence interval for utilization."""
    mean: float
    ci_lower: float
    ci_upper: float
    std_error: float


@dataclass
class TrendResult:
    """Mann-Kendall trend test result."""
    tau: float
    p_value: float
    trend: str  # 'increasing', 'decreasing', 'no trend'
    interpretation: str


@dataclass
class OptimizationTarget:
    """ROI-scored optimization target."""
    category: str
    intent: str
    frequency: int
    avg_duration_sec: float
    total_duration_sec: float
    ease_score: float
    roi_score: float
    potential_gain_sec: float


# Ease scores by category (expert estimates, can be refined with data)
EASE_SCORES = {
    'boot': 0.5,          # Medium - one-time initialization
    'orient': 0.6,        # Easier - often just analysis
    'execute.llm_call': 0.2,   # Very hard - core logic
    'execute.tool_use': 0.4,   # Hard - complex interactions
    'execute.code_gen': 0.3,   # Hard - generation logic
    'api_call': 0.3,      # Hard - external dependency
    'file_op': 0.7,       # Easy - often just caching
    'update': 0.6,        # Easier - incremental changes
    'interrupt': 0.1,     # Very hard - rare edge case
}


def bootstrap_utilization_ci(
    total_durations: List[float],
    wall_clock_times: List[float],
    n_bootstrap: int = 1000,
    alpha: float = 0.05
) -> UtilizationCI:
    """
    Calculate bootstrap confidence interval for utilization.

    Handles session-level aggregates (not individual spans).

    Args:
        total_durations: List of total compute time per session (seconds)
        wall_clock_times: List of wall clock time per session (seconds)
        n_bootstrap: Number of bootstrap samples (default 1000)
        alpha: Significance level (default 0.05 for 95% CI)

    Returns:
        UtilizationCI with mean, CI bounds, and standard error
    """
    if len(total_durations) != len(wall_clock_times):
        raise ValueError("total_durations and wall_clock_times must have same length")

    n = len(total_durations)
    if n == 0:
        return UtilizationCI(0.0, 0.0, 0.0, 0.0)

    utilizations = []

    for _ in range(n_bootstrap):
        # Resample sessions with replacement
        indices = np.random.choice(n, size=n, replace=True)

        sample_compute = [total_durations[i] for i in indices]
        sample_wall = [wall_clock_times[i] for i in indices]

        # Calculate utilization for this bootstrap sample
        total_compute = sum(sample_compute)
        total_wall = sum(sample_wall)

        if total_wall > 0:
            util = (total_compute / total_wall) * 100
            utilizations.append(util)

    utilizations = np.array(utilizations)

    return UtilizationCI(
        mean=float(np.mean(utilizations)),
        ci_lower=float(np.percentile(utilizations, 100 * alpha / 2)),
        ci_upper=float(np.percentile(utilizations, 100 * (1 - alpha / 2))),
        std_error=float(np.std(utilizations))
    )


def detect_utilization_anomalies(
    session_utilizations: List[Tuple[str, float]],
    window_size: int = 20
) -> List[Dict[str, Any]]:
    """
    Detect anomalous utilization using 3-sigma control limits (SPC).

    Args:
        session_utilizations: List of (session_id, utilization_pct) tuples
        window_size: Number of recent sessions for baseline (default 20)

    Returns:
        List of anomalies with session_id, utilization, type, reason, severity
    """
    if len(session_utilizations) < window_size:
        return []  # Not enough data for baseline

    # Use recent sessions as baseline
    recent_utils = [u for _, u in session_utilizations[-window_size:]]

    mean_util = np.mean(recent_utils)
    std_util = np.std(recent_utils, ddof=1) if len(recent_utils) > 1 else 0

    # 3-sigma control limits
    ucl = mean_util + 3 * std_util
    lcl = max(0, mean_util - 3 * std_util)  # Utilization can't be negative

    anomalies = []
    for session_id, util in session_utilizations:
        if util > ucl:
            anomalies.append({
                'session_id': session_id,
                'utilization': util,
                'type': 'high',
                'reason': f'Utilization {util:.1f}% exceeds UCL {ucl:.1f}%',
                'severity': 'medium'  # High utilization is good, but unusual
            })
        elif util < lcl:
            anomalies.append({
                'session_id': session_id,
                'utilization': util,
                'type': 'low',
                'reason': f'Utilization {util:.1f}% below LCL {lcl:.1f}%',
                'severity': 'high'  # Low utilization is pramāda
            })

    return anomalies


def detect_anomalies_iqr(
    session_utilizations: List[Tuple[str, float]]
) -> List[Dict[str, Any]]:
    """
    Detect anomalies using Interquartile Range (IQR) method.

    More robust to outliers than 3-sigma method.

    Args:
        session_utilizations: List of (session_id, utilization_pct) tuples

    Returns:
        List of anomalies with session_id, utilization, type, reason
    """
    if len(session_utilizations) < 4:
        return []

    utils = [u for _, u in session_utilizations]
    q1 = np.percentile(utils, 25)
    q3 = np.percentile(utils, 75)
    iqr = q3 - q1

    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr

    anomalies = []
    for session_id, util in session_utilizations:
        if util < lower_bound or util > upper_bound:
            anomalies.append({
                'session_id': session_id,
                'utilization': util,
                'type': 'outlier',
                'reason': f'Outside IQR bounds [{lower_bound:.1f}%, {upper_bound:.1f}%]'
            })

    return anomalies


def mann_kendall_trend(
    session_utilizations: List[Tuple[str, float]]
) -> TrendResult:
    """
    Test for monotonic trend in utilization over time using Mann-Kendall test.

    Non-parametric test, robust to outliers.

    Args:
        session_utilizations: List of (session_id, utilization_pct) tuples in temporal order

    Returns:
        TrendResult with tau, p_value, trend classification, interpretation
    """
    utils = [u for _, u in session_utilizations]
    n = len(utils)

    if n < 3:
        return TrendResult(
            tau=0.0,
            p_value=1.0,
            trend='insufficient_data',
            interpretation=f"Need at least 3 sessions for trend test, have {n}"
        )

    # Count concordant and discordant pairs
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            if utils[j] > utils[i]:
                s += 1
            elif utils[j] < utils[i]:
                s -= 1

    # Variance (simplified, ignoring ties)
    var_s = n * (n - 1) * (2 * n + 5) / 18

    # Z-statistic
    if s > 0:
        z = (s - 1) / np.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / np.sqrt(var_s)
    else:
        z = 0

    # Two-tailed p-value
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))

    # Kendall's tau
    tau = s / (n * (n - 1) / 2)

    # Interpret
    if p_value < 0.05:
        trend = 'increasing' if tau > 0 else 'decreasing'
    else:
        trend = 'no trend'

    interpretation = (
        f"{'Significant' if p_value < 0.05 else 'No significant'} {trend} "
        f"(τ={tau:.3f}, p={p_value:.4f}, n={n})"
    )

    return TrendResult(
        tau=tau,
        p_value=p_value,
        trend=trend,
        interpretation=interpretation
    )


def calculate_optimization_roi(
    category_breakdown: Dict[str, Dict[str, Any]]
) -> List[OptimizationTarget]:
    """
    Calculate ROI for each optimization target.

    ROI = frequency × avg_duration × ease_score

    Args:
        category_breakdown: Dict mapping category name to {'count': int, 'total_sec': float}
                           (from jikoku_kaizen report)

    Returns:
        List of OptimizationTarget sorted by ROI descending
    """
    targets = []

    for category, stats in category_breakdown.items():
        frequency = stats['count']
        total_duration = stats['total_sec']
        avg_duration = total_duration / frequency if frequency > 0 else 0

        # Get ease score (default to 0.5 if category not in lookup)
        ease = EASE_SCORES.get(category, 0.5)

        # ROI score
        roi = frequency * avg_duration * ease

        # Potential gain (assume 50% optimization possible)
        potential_gain = total_duration * 0.5

        targets.append(OptimizationTarget(
            category=category,
            intent=category,  # category_breakdown doesn't separate intent
            frequency=frequency,
            avg_duration_sec=avg_duration,
            total_duration_sec=total_duration,
            ease_score=ease,
            roi_score=roi,
            potential_gain_sec=potential_gain
        ))

    # Sort by ROI descending
    targets.sort(key=lambda t: t.roi_score, reverse=True)

    return targets


def pareto_analysis(
    category_breakdown: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Identify which categories account for 80% of total time (Pareto principle).

    Args:
        category_breakdown: Dict mapping category name to {'count': int, 'total_sec': float}

    Returns:
        Dict with pareto_categories, total_duration, num_categories_for_80pct, pareto_ratio
    """
    # Sort by duration descending
    sorted_cats = sorted(
        category_breakdown.items(),
        key=lambda x: x[1]['total_sec'],
        reverse=True
    )

    total_duration = sum(stats['total_sec'] for stats in category_breakdown.values())

    if total_duration == 0:
        return {
            'total_duration': 0,
            'pareto_categories': [],
            'num_categories_for_80pct': 0,
            'total_categories': len(category_breakdown),
            'pareto_ratio': 0,
            'message': "No duration data available"
        }

    cumulative = 0
    pareto_categories = []

    for category, stats in sorted_cats:
        duration = stats['total_sec']
        cumulative += duration
        pct_of_total = (duration / total_duration) * 100
        cumulative_pct = (cumulative / total_duration) * 100

        pareto_categories.append({
            'category': category,
            'duration_sec': duration,
            'pct_of_total': pct_of_total,
            'cumulative_pct': cumulative_pct
        })

        if cumulative_pct >= 80:
            break

    num_pareto = len(pareto_categories)
    total_cats = len(category_breakdown)
    ratio = num_pareto / total_cats if total_cats > 0 else 0

    return {
        'total_duration': total_duration,
        'pareto_categories': pareto_categories,
        'num_categories_for_80pct': num_pareto,
        'total_categories': total_cats,
        'pareto_ratio': ratio,
        'message': f"{num_pareto}/{total_cats} categories ({ratio*100:.0f}%) account for 80% of time"
    }


def validate_milestone_achievement(
    session_utilizations: List[Tuple[str, float]],
    milestone_target: float
) -> Dict[str, Any]:
    """
    Validate that a milestone has been reliably achieved.

    Requires 14 sessions (2 kaizen windows) at or above target with:
    - Mean utilization >= target
    - Coefficient of variation < 20% (stable)
    - No significant decreasing trend

    Args:
        session_utilizations: List of (session_id, utilization_pct) tuples
        milestone_target: Target utilization % for this milestone

    Returns:
        Dict with achievement status, mean, stability, trend, checks
    """
    recent_14 = [u for _, u in session_utilizations[-14:]]

    if len(recent_14) < 14:
        return {
            'achieved': False,
            'reason': f'Need 14 sessions for validation, have {len(recent_14)}',
            'mean_utilization': None,
            'target_utilization': milestone_target
        }

    mean_util = np.mean(recent_14)
    std_util = np.std(recent_14, ddof=1)
    cv = (std_util / mean_util) if mean_util > 0 else float('inf')

    trend = mann_kendall_trend(session_utilizations[-14:])

    checks = {
        'mean_sufficient': mean_util >= milestone_target,
        'stable': cv < 0.20,  # Coefficient of variation < 20%
        'not_decreasing': trend.trend != 'decreasing' or trend.p_value > 0.05
    }

    achieved = all(checks.values())

    message = (
        f"Milestone {'ACHIEVED' if achieved else 'NOT ACHIEVED'}: "
        f"{mean_util:.1f}% (target: {milestone_target:.1f}%)"
    )

    return {
        'achieved': achieved,
        'mean_utilization': mean_util,
        'target_utilization': milestone_target,
        'stability_cv': cv,
        'trend': trend.trend,
        'trend_p_value': trend.p_value,
        'checks': checks,
        'message': message
    }


def kaizen_check_before_after(
    before_utilizations: List[float],
    after_utilizations: List[float],
    alpha: float = 0.05
) -> Dict[str, Any]:
    """
    Statistical test for kaizen CHECK phase (before vs after optimization).

    Uses independent t-test (assumes different sessions before/after).

    Args:
        before_utilizations: List of utilization % before optimization
        after_utilizations: List of utilization % after optimization
        alpha: Significance level (default 0.05)

    Returns:
        Dict with before/after means, improvement, t-statistic, p-value, significance
    """
    if len(before_utilizations) == 0 or len(after_utilizations) == 0:
        return {
            'error': 'Need at least one session in before and after groups'
        }

    mean_before = np.mean(before_utilizations)
    mean_after = np.mean(after_utilizations)
    improvement = mean_after - mean_before
    improvement_pct = (improvement / mean_before * 100) if mean_before > 0 else 0

    # Independent t-test (one-tailed: after > before)
    t_stat, p_value = stats.ttest_ind(
        after_utilizations,
        before_utilizations,
        alternative='greater'
    )

    significant = p_value < alpha

    return {
        'mean_before': mean_before,
        'mean_after': mean_after,
        'improvement_absolute': improvement,
        'improvement_percent': improvement_pct,
        't_statistic': t_stat,
        'p_value': p_value,
        'significant': significant,
        'alpha': alpha,
        'message': (
            f"{'SIGNIFICANT' if significant else 'NOT SIGNIFICANT'} improvement: "
            f"{mean_before:.1f}% → {mean_after:.1f}% "
            f"(+{improvement:.1f} points, p={p_value:.4f})"
        )
    }


# Milestone definitions
MILESTONES = [
    {'target': 10.0, 'gain_vs_baseline': 2.0, 'description': 'First doubling'},
    {'target': 20.0, 'gain_vs_baseline': 4.0, 'description': 'Industry bottom quartile'},
    {'target': 30.0, 'gain_vs_baseline': 6.0, 'description': 'Industry median'},
    {'target': 40.0, 'gain_vs_baseline': 8.0, 'description': 'Industry top quartile'},
    {'target': 50.0, 'gain_vs_baseline': 10.0, 'description': 'GOAL: 10x efficiency'},
]


def track_milestone_progress(
    session_utilizations: List[Tuple[str, float]],
    baseline: float = 5.0
) -> Dict[str, Any]:
    """
    Track progress toward utilization milestones.

    Args:
        session_utilizations: List of (session_id, utilization_pct) tuples
        baseline: Starting utilization % (default 5.0)

    Returns:
        Dict with current state, next milestone, distance, trend, projections
    """
    if len(session_utilizations) == 0:
        return {
            'error': 'No session data available'
        }

    # Current utilization (7-session rolling average)
    recent_7 = [u for _, u in session_utilizations[-7:]]
    current_util = np.mean(recent_7) if recent_7 else baseline

    # Trend analysis
    trend = mann_kendall_trend(session_utilizations)

    # Find next milestone
    next_milestone = None
    for m in MILESTONES:
        if current_util < m['target']:
            next_milestone = m
            break

    if next_milestone is None:
        return {
            'current_utilization': current_util,
            'baseline_utilization': baseline,
            'improvement_vs_baseline': current_util - baseline,
            'current_gain_factor': current_util / baseline if baseline > 0 else None,
            'status': 'GOAL_ACHIEVED',
            'message': 'All milestones completed! 🎉'
        }

    # Distance to next milestone
    distance = next_milestone['target'] - current_util

    # Estimate sessions to milestone (if trend is increasing)
    sessions_to_milestone = None
    if trend.trend == 'increasing' and trend.tau > 0:
        # Rough estimate: assume linear improvement at current rate
        # tau is correlation (-1 to 1), scale to improvement rate
        improvement_per_session = trend.tau * 2  # Heuristic scaling
        if improvement_per_session > 0:
            sessions_to_milestone = int(np.ceil(distance / improvement_per_session))

    return {
        'current_utilization': current_util,
        'baseline_utilization': baseline,
        'improvement_vs_baseline': current_util - baseline,
        'current_gain_factor': current_util / baseline if baseline > 0 else None,
        'next_milestone': next_milestone,
        'distance_to_milestone': distance,
        'sessions_to_milestone': sessions_to_milestone,
        'trend': trend.trend,
        'trend_tau': trend.tau,
        'trend_p_value': trend.p_value,
        'message': f"Current: {current_util:.1f}% | Next: {next_milestone['target']:.0f}% ({distance:.1f} points away)"
    }
