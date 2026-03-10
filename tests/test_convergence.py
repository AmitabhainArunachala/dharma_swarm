"""Tests for Darwin convergence detection."""

import pytest

from dharma_swarm.convergence import ConvergenceConfig, ConvergenceDetector


def test_detects_low_variance_convergence():
    detector = ConvergenceDetector(
        ConvergenceConfig(
            window_size=10,
            variance_threshold=0.0001,
            improvement_threshold=0.05,
        )
    )

    for _ in range(15):
        detector.update(0.5)

    assert detector.state.converged is True


def test_detects_plateau_from_tiny_improvement():
    detector = ConvergenceDetector(
        ConvergenceConfig(
            window_size=10,
            variance_threshold=0.01,
            improvement_threshold=0.05,
        )
    )

    for idx in range(25):
        detector.update(0.5 + (0.001 * idx))

    assert detector.state.plateau_detected is True


def test_restart_triggered_and_mutation_rate_amplified():
    detector = ConvergenceDetector(
        ConvergenceConfig(
            window_size=5,
            variance_threshold=0.0001,
            improvement_threshold=0.01,
            restart_mutation_multiplier=3.0,
            restart_duration=4,
        )
    )

    triggered = False
    for _ in range(10):
        triggered = detector.update(0.42) or triggered

    assert triggered is True
    assert detector.is_restart_active() is True
    assert detector.get_restart_mutation_rate(0.2) == pytest.approx(0.6)
