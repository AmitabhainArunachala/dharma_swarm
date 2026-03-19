"""Tests for loop_detector.py — 4-signal stuck detection."""

import pytest

from dharma_swarm.loop_detector import (
    ActionRecord,
    LoopDetector,
    LoopSeverity,
    LoopSignal,
)


@pytest.fixture
def detector():
    return LoopDetector(
        window_size=20,
        signature_threshold=3,
        error_threshold=0.80,
        semantic_threshold=0.60,
        resource_limit=50,
    )


def test_no_loop_on_empty(detector):
    """No loop detected with insufficient data."""
    result = detector.check()
    assert not result.detected
    assert result.severity == LoopSeverity.NONE


def test_signature_repeat_detection(detector):
    """Detect repeated action signatures."""
    for _ in range(4):
        detector.record(ActionRecord(
            action_type="write_file",
            target="foo.py",
            result="error",
        ))

    result = detector.check()
    assert result.detected
    assert LoopSignal.SIGNATURE_REPEAT in result.signals


def test_error_pattern_detection(detector):
    """Detect consistent error patterns."""
    for _ in range(5):
        detector.record(ActionRecord(
            action_type=f"action_{_}",  # Different actions
            target=f"file_{_}.py",
            result="error",
            error_type="SyntaxError",
        ))

    result = detector.check()
    assert result.detected
    assert LoopSignal.ERROR_PATTERN in result.signals


def test_semantic_repeat_detection(detector):
    """Detect semantically similar consecutive actions."""
    for i in range(5):
        detector.record(ActionRecord(
            action_type="write_file",
            target="same_file.py",
            result="success",
            keywords=["write", "python", "module"],
        ))

    result = detector.check()
    assert result.detected
    # Should detect both signature repeat AND semantic repeat
    assert LoopSignal.SIGNATURE_REPEAT in result.signals


def test_resource_limit_detection():
    """Detect resource budget exhaustion."""
    detector = LoopDetector(resource_limit=5)
    for i in range(6):
        detector.record(ActionRecord(
            action_type=f"action_{i}",
            target=f"target_{i}",
        ))

    result = detector.check()
    assert result.detected
    assert LoopSignal.RESOURCE_LIMIT in result.signals


def test_resource_limit_does_not_trigger_at_exact_budget():
    """The resource-limit signal should fire only after the budget is exceeded."""
    detector = LoopDetector(resource_limit=5)
    for i in range(5):
        detector.record(ActionRecord(
            action_type=f"action_{i}",
            target=f"target_{i}",
            keywords=[f"kw_{i}"],
        ))

    result = detector.check()
    assert LoopSignal.RESOURCE_LIMIT not in result.signals
    assert result.severity == LoopSeverity.NONE


def test_resource_limit_uses_sliding_window_not_lifetime_total():
    """Old actions outside the window should not keep tripping the resource signal."""
    detector = LoopDetector(window_size=3, resource_limit=3)
    for i in range(4):
        detector.record(ActionRecord(
            action_type=f"action_{i}",
            target=f"target_{i}",
            keywords=[f"kw_{i}"],
            tokens_used=10,
        ))

    result = detector.check()

    assert LoopSignal.RESOURCE_LIMIT not in result.signals
    assert result.severity == LoopSeverity.NONE


def test_severity_escalation(detector):
    """Severity escalates with more signals."""
    # Create both signature repeat and error pattern
    for i in range(5):
        detector.record(ActionRecord(
            action_type="write_file",
            target="foo.py",
            result="error",
            error_type="SyntaxError",
            keywords=["write", "python"],
        ))

    result = detector.check()
    assert result.severity in (LoopSeverity.LIKELY, LoopSeverity.CERTAIN)
    assert result.should_break


def test_reset(detector):
    """Reset clears all state."""
    for _ in range(5):
        detector.record(ActionRecord(action_type="x", target="y"))

    detector.reset()
    result = detector.check()
    assert not result.detected
    assert detector.total_actions == 0


def test_diverse_actions_no_loop(detector):
    """Diverse actions should not trigger loop detection."""
    actions = ["read", "write", "test", "search", "deploy"]
    for i, action in enumerate(actions):
        detector.record(ActionRecord(
            action_type=action,
            target=f"file_{i}.py",
            result="success",
            keywords=[action, f"unique_{i}"],
        ))

    result = detector.check()
    assert result.severity == LoopSeverity.NONE
