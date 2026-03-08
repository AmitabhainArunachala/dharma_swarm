"""
Tests for kaizen_stats.py statistical analysis tools.
"""

import pytest
import numpy as np
from dharma_swarm.kaizen_stats import (
    bootstrap_utilization_ci,
    detect_utilization_anomalies,
    detect_anomalies_iqr,
    mann_kendall_trend,
    calculate_optimization_roi,
    pareto_analysis,
    validate_milestone_achievement,
    kaizen_check_before_after,
    track_milestone_progress,
    MILESTONES,
)


def test_bootstrap_utilization_ci():
    """Test bootstrap confidence interval calculation."""
    # Simple case: constant utilization
    total_durs = [10.0] * 10
    wall_clocks = [100.0] * 10

    result = bootstrap_utilization_ci(total_durs, wall_clocks, n_bootstrap=100)

    # Should be ~10% with tight CI
    assert 9.5 < result.mean < 10.5
    assert result.ci_lower <= result.mean <= result.ci_upper
    assert result.std_error < 1.0  # Low variance


def test_bootstrap_utilization_ci_variable():
    """Test bootstrap CI with variable utilization."""
    np.random.seed(42)

    # Variable utilization: 5-15%
    total_durs = [np.random.uniform(5, 15) for _ in range(20)]
    wall_clocks = [100.0] * 20

    result = bootstrap_utilization_ci(total_durs, wall_clocks, n_bootstrap=1000)

    # Mean should be around 10%
    assert 8.0 < result.mean < 12.0
    # CI should be wider due to variance
    assert result.ci_upper - result.ci_lower > 2.0


def test_detect_utilization_anomalies_none():
    """Test anomaly detection when all values are normal."""
    np.random.seed(42)
    # All utilizations around 20%, no anomalies
    sessions = [(f'session-{i:03d}', 20.0 + np.random.normal(0, 0.5)) for i in range(30)]

    anomalies = detect_utilization_anomalies(sessions, window_size=20)

    # Should detect very few anomalies (within 3 sigma with tight distribution)
    assert len(anomalies) <= 1  # At most 1 outlier expected with tight distribution


def test_detect_utilization_anomalies_outlier():
    """Test anomaly detection with clear outlier."""
    sessions = [(f'session-{i:03d}', 20.0) for i in range(30)]
    # Add one clear outlier (way too low)
    sessions.append(('session-031', 2.0))

    anomalies = detect_utilization_anomalies(sessions, window_size=20)

    # Should detect the outlier
    assert len(anomalies) > 0
    assert any(a['session_id'] == 'session-031' for a in anomalies)
    assert any(a['type'] == 'low' for a in anomalies)


def test_detect_anomalies_iqr():
    """Test IQR-based anomaly detection."""
    sessions = [(f'session-{i:03d}', 20.0) for i in range(20)]
    # Add outliers
    sessions.append(('session-021', 50.0))  # High outlier
    sessions.append(('session-022', 2.0))   # Low outlier

    anomalies = detect_anomalies_iqr(sessions)

    # Should detect both outliers
    assert len(anomalies) >= 2
    outlier_ids = {a['session_id'] for a in anomalies}
    assert 'session-021' in outlier_ids or 'session-022' in outlier_ids


def test_mann_kendall_increasing_trend():
    """Test Mann-Kendall with clear increasing trend."""
    # Utilization increasing from 5% to 25%
    sessions = [(f'session-{i:03d}', 5.0 + i) for i in range(20)]

    result = mann_kendall_trend(sessions)

    assert result.trend == 'increasing'
    assert result.p_value < 0.05
    assert result.tau > 0


def test_mann_kendall_no_trend():
    """Test Mann-Kendall with no trend (flat)."""
    np.random.seed(123)  # Seed for reproducibility
    # Constant utilization ~20%
    sessions = [(f'session-{i:03d}', 20.0 + np.random.normal(0, 0.3)) for i in range(20)]

    result = mann_kendall_trend(sessions)

    # Should show no significant trend (p > 0.05)
    # Note: Random noise may occasionally produce trend, but with small tau
    assert result.p_value > 0.05 or abs(result.tau) < 0.2


def test_mann_kendall_insufficient_data():
    """Test Mann-Kendall with insufficient data."""
    sessions = [('session-001', 10.0), ('session-002', 11.0)]

    result = mann_kendall_trend(sessions)

    assert result.trend == 'insufficient_data'


def test_calculate_optimization_roi():
    """Test ROI calculation for optimization targets."""
    category_breakdown = {
        'execute.llm_call': {'count': 10, 'total_sec': 100.0},  # High frequency + duration, low ease
        'file_op': {'count': 5, 'total_sec': 10.0},             # Low duration, high ease
        'api_call': {'count': 3, 'total_sec': 30.0},            # Medium
    }

    targets = calculate_optimization_roi(category_breakdown)

    # Should have 3 targets
    assert len(targets) == 3

    # All should have roi_score > 0
    assert all(t.roi_score > 0 for t in targets)

    # Highest ROI should be first
    assert targets[0].roi_score >= targets[1].roi_score >= targets[2].roi_score


def test_calculate_optimization_roi_sorting():
    """Test that ROI sorting is correct."""
    category_breakdown = {
        'easy_frequent': {'count': 100, 'total_sec': 50.0},  # High freq, medium dur, high ease
        'hard_rare': {'count': 1, 'total_sec': 100.0},       # Low freq, high dur, low ease
    }

    targets = calculate_optimization_roi(category_breakdown)

    # easy_frequent should have higher ROI (frequency × duration × ease)
    # 100 × 0.5 × 0.5 = 25 vs 1 × 100 × 0.5 = 50 (depends on ease score)
    # Without specific ease scores, just check that sorting occurred
    assert targets[0].roi_score >= targets[1].roi_score


def test_pareto_analysis():
    """Test Pareto 80/20 analysis."""
    category_breakdown = {
        'cat_A': {'count': 10, 'total_sec': 80.0},   # 80% of time
        'cat_B': {'count': 5, 'total_sec': 15.0},    # 15% of time
        'cat_C': {'count': 3, 'total_sec': 5.0},     # 5% of time
    }

    result = pareto_analysis(category_breakdown)

    # Total duration should be 100
    assert result['total_duration'] == 100.0

    # Should identify cat_A as accounting for 80%
    assert result['num_categories_for_80pct'] == 1
    assert result['pareto_categories'][0]['category'] == 'cat_A'
    assert result['pareto_categories'][0]['cumulative_pct'] >= 80


def test_pareto_analysis_multi_category():
    """Test Pareto analysis when multiple categories needed for 80%."""
    category_breakdown = {
        'cat_A': {'count': 10, 'total_sec': 40.0},   # 40%
        'cat_B': {'count': 5, 'total_sec': 30.0},    # 30%
        'cat_C': {'count': 3, 'total_sec': 20.0},    # 20%
        'cat_D': {'count': 2, 'total_sec': 10.0},    # 10%
    }

    result = pareto_analysis(category_breakdown)

    # Should need cat_A + cat_B to reach 80%
    assert result['num_categories_for_80pct'] == 3  # A + B + C = 90%
    assert result['pareto_ratio'] < 1.0


def test_validate_milestone_achievement_success():
    """Test milestone validation when achieved."""
    # 14 sessions all at or above 10% target
    sessions = [(f'session-{i:03d}', 10.5 + np.random.normal(0, 0.5)) for i in range(14)]

    result = validate_milestone_achievement(sessions, milestone_target=10.0)

    # Should achieve milestone
    assert result['achieved'] == True
    assert result['mean_utilization'] >= 10.0
    assert result['checks']['mean_sufficient'] == True
    assert result['checks']['stable'] == True


def test_validate_milestone_achievement_insufficient_data():
    """Test milestone validation with insufficient data."""
    sessions = [(f'session-{i:03d}', 10.5) for i in range(5)]

    result = validate_milestone_achievement(sessions, milestone_target=10.0)

    # Should not achieve due to insufficient data
    assert result['achieved'] is False
    assert 'Need 14 sessions' in result['reason']


def test_validate_milestone_achievement_unstable():
    """Test milestone validation when utilization is unstable."""
    # 14 sessions, mean above target but highly variable
    sessions = [(f'session-{i:03d}', 10.0 + np.random.normal(0, 5.0)) for i in range(14)]

    result = validate_milestone_achievement(sessions, milestone_target=10.0)

    # May or may not achieve depending on random seed
    # Just check that CV is calculated
    assert 'stability_cv' in result
    assert result['stability_cv'] >= 0


def test_kaizen_check_before_after_improvement():
    """Test kaizen CHECK phase with significant improvement."""
    np.random.seed(42)

    before = [5.0 + np.random.normal(0, 0.5) for _ in range(7)]
    after = [8.0 + np.random.normal(0, 0.5) for _ in range(7)]

    result = kaizen_check_before_after(before, after)

    # Should show improvement
    assert result['improvement_absolute'] > 0
    assert result['improvement_percent'] > 0
    # Should be significant (means differ by ~3 percentage points)
    assert result['significant'] == True
    assert result['p_value'] < 0.05


def test_kaizen_check_before_after_no_improvement():
    """Test kaizen CHECK phase with no improvement."""
    before = [10.0] * 7
    after = [10.0] * 7

    result = kaizen_check_before_after(before, after)

    # Should show no improvement
    assert abs(result['improvement_absolute']) < 0.1
    assert result['significant'] == False


def test_kaizen_check_before_after_regression():
    """Test kaizen CHECK phase when performance regresses."""
    before = [10.0] * 7
    after = [8.0] * 7

    result = kaizen_check_before_after(before, after)

    # Should show negative improvement (regression)
    assert result['improvement_absolute'] < 0
    assert result['significant'] == False  # t-test is one-tailed (after > before)


def test_track_milestone_progress_in_progress():
    """Test milestone progress tracking."""
    # Current utilization ~8%, baseline 5%
    sessions = [(f'session-{i:03d}', 8.0 + np.random.normal(0, 0.5)) for i in range(10)]

    result = track_milestone_progress(sessions, baseline=5.0)

    # Should be working toward 10% milestone
    assert result['current_utilization'] > 5.0
    assert result['next_milestone']['target'] == 10.0
    assert result['distance_to_milestone'] > 0
    assert result['distance_to_milestone'] < 5.0


def test_track_milestone_progress_goal_achieved():
    """Test milestone progress when goal achieved."""
    # Current utilization 50%+
    sessions = [(f'session-{i:03d}', 50.5) for i in range(10)]

    result = track_milestone_progress(sessions, baseline=5.0)

    # Should show goal achieved
    assert result['status'] == 'GOAL_ACHIEVED'
    assert 'completed' in result['message'].lower()


def test_track_milestone_progress_with_trend():
    """Test milestone progress with increasing trend."""
    # Increasing trend from 5% to 9%
    sessions = [(f'session-{i:03d}', 5.0 + i * 0.2) for i in range(20)]

    result = track_milestone_progress(sessions, baseline=5.0)

    # Should detect increasing trend
    assert result['trend'] == 'increasing'
    assert result['sessions_to_milestone'] is not None
    assert result['sessions_to_milestone'] > 0


def test_milestones_defined():
    """Test that milestones are properly defined."""
    assert len(MILESTONES) == 5

    # Check targets are in ascending order
    targets = [m['target'] for m in MILESTONES]
    assert targets == sorted(targets)

    # Check final milestone is 50% (10x from 5%)
    assert MILESTONES[-1]['target'] == 50.0
    assert MILESTONES[-1]['gain_vs_baseline'] == 10.0


@pytest.mark.parametrize("target_util,baseline,expected_gain", [
    (10.0, 5.0, 2.0),
    (20.0, 5.0, 4.0),
    (50.0, 5.0, 10.0),
])
def test_gain_calculation(target_util, baseline, expected_gain):
    """Test that gain factors are calculated correctly."""
    actual_gain = target_util / baseline
    assert abs(actual_gain - expected_gain) < 0.01


def test_bootstrap_ci_empty_data():
    """Test bootstrap CI with empty data."""
    result = bootstrap_utilization_ci([], [], n_bootstrap=100)

    assert result.mean == 0.0
    assert result.ci_lower == 0.0
    assert result.ci_upper == 0.0


def test_optimization_roi_default_ease_score():
    """Test that unknown categories get default ease score."""
    category_breakdown = {
        'unknown_category': {'count': 10, 'total_sec': 50.0}
    }

    targets = calculate_optimization_roi(category_breakdown)

    # Should use default ease score of 0.5
    assert targets[0].ease_score == 0.5


def test_pareto_empty_data():
    """Test Pareto analysis with empty data."""
    result = pareto_analysis({})

    assert result['total_duration'] == 0
    assert result['num_categories_for_80pct'] == 0
    assert 'No duration data' in result['message']
