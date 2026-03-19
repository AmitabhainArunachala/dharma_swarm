"""Tests for viveka.py — the discernment gate."""

import pytest

from dharma_swarm.viveka import (
    ExperienceBase,
    ExperienceRecord,
    VivekaDecision,
    VivekaGate,
)


@pytest.fixture
def gate():
    return VivekaGate(precision=0.5)


@pytest.fixture
def experienced_gate():
    """Gate with a populated experience base."""
    exp = ExperienceBase()
    for i in range(10):
        exp.add(ExperienceRecord(
            situation_hash="known_situation",
            action_type="write_file",
            outcome="success",
            fitness_score=0.8,
        ))
    gate = VivekaGate(experience_base=exp, precision=0.7)
    return gate


# ---- Core decisions ----

def test_commit_on_known_fast_path(experienced_gate):
    """Known situation + fast path → immediate COMMIT."""
    result = experienced_gate.evaluate(
        action_type="write_file",
        situation_hash="known_situation",
    )
    assert result.decision == VivekaDecision.COMMIT
    assert result.should_act


def test_escalate_on_fatal_flaw(gate):
    """Fatal flaws → ESCALATE to human."""
    result = gate.evaluate(
        action_type="delete_database",
        fatal_flaws=["irreversible data loss", "no backup exists"],
    )
    assert result.decision == VivekaDecision.ESCALATE
    assert not result.should_act
    assert len(result.fatal_flaws) == 2


def test_wait_on_telos_misalignment(gate):
    """Telos misalignment → WAIT."""
    result = gate.evaluate(
        action_type="write_file",
        telos_aligned=False,
    )
    assert result.decision == VivekaDecision.WAIT


def test_commit_when_no_disqualifiers(gate):
    """No disqualifying conditions → COMMIT (negative test)."""
    # Add some experience so EFE is reasonable
    gate.experience.add(ExperienceRecord(
        action_type="read_file", outcome="success", fitness_score=0.6,
    ))
    result = gate.evaluate(
        action_type="read_file",
        telos_aligned=True,
    )
    assert result.decision == VivekaDecision.COMMIT


def test_wait_or_explore_on_high_uncertainty(gate):
    """High uncertainty with no experience → WAIT or EXPLORE."""
    gate.precision = 0.1  # Very uncertain
    result = gate.evaluate(
        action_type="completely_unknown_action",
        domains=["code", "research", "meta"],
        affected_agents=["a", "b", "c", "d", "e"],
    )
    assert result.decision in (VivekaDecision.WAIT, VivekaDecision.EXPLORE)


# ---- Precision dynamics ----

def test_precision_threshold_inversely_related(gate):
    """Higher precision → lower threshold → easier to commit."""
    gate.precision = 0.9
    high_prec_threshold = gate.precision_threshold
    gate.precision = 0.2
    low_prec_threshold = gate.precision_threshold
    assert low_prec_threshold > high_prec_threshold


def test_update_precision_from_error(gate):
    """Precision updates based on prediction errors."""
    initial = gate.precision
    gate.update_precision(0.0)  # Perfect prediction
    assert gate.precision > initial


# ---- Experience base ----

def test_experience_confidence():
    """Confidence reflects success rate."""
    exp = ExperienceBase()
    for i in range(8):
        exp.add(ExperienceRecord(action_type="test", outcome="success", fitness_score=0.8))
    for i in range(2):
        exp.add(ExperienceRecord(action_type="test", outcome="failure", fitness_score=0.2))

    assert exp.confidence_for("test") == pytest.approx(0.8)
    assert exp.confidence_for("unknown") == 0.0


def test_experience_marginal_value():
    """Marginal value relative to system average."""
    exp = ExperienceBase()
    exp.add(ExperienceRecord(action_type="good", outcome="success", fitness_score=0.9))
    exp.add(ExperienceRecord(action_type="bad", outcome="failure", fitness_score=0.1))

    assert exp.marginal_value("good") > 0  # Above average
    assert exp.marginal_value("bad") < 0   # Below average


# ---- Evaluation timing ----

def test_evaluation_is_fast(gate):
    """Viveka evaluation should be very fast (no LLM calls)."""
    result = gate.evaluate(action_type="read_file")
    assert result.evaluation_ms < 100  # Well under 100ms
