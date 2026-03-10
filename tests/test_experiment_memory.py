"""Tests for Darwin experiment-memory analysis."""

from dharma_swarm.archive import FitnessScore
from dharma_swarm.experiment_log import ExperimentRecord
from dharma_swarm.experiment_memory import ExperimentMemory
from dharma_swarm.execution_profile import EvidenceTier, PromotionState


def test_experiment_memory_flags_caution_and_strategy():
    memory = ExperimentMemory()
    records = [
        ExperimentRecord(
            component="fragile.py",
            execution_profile="local_default",
            promotion_state=PromotionState.CANDIDATE,
            evidence_tier=EvidenceTier.LOCAL,
            pass_rate=0.0,
            weighted_fitness=0.1,
            fitness=FitnessScore(correctness=0.0),
        ),
        ExperimentRecord(
            component="fragile.py",
            execution_profile="local_default",
            promotion_state=PromotionState.CANDIDATE,
            evidence_tier=EvidenceTier.LOCAL,
            pass_rate=0.0,
            weighted_fitness=0.1,
            fitness=FitnessScore(correctness=0.0),
        ),
        ExperimentRecord(
            component="strong.py",
            execution_profile="pkg_profile",
            promotion_state=PromotionState.COMPONENT_PASS,
            evidence_tier=EvidenceTier.COMPONENT,
            pass_rate=1.0,
            weighted_fitness=0.8,
            fitness=FitnessScore(correctness=1.0, safety=1.0),
        ),
    ]

    snapshot = memory.analyze(records)

    assert snapshot.records_considered == 3
    assert snapshot.recommended_strategy in {"explore", "backtrack"}
    assert "fragile.py" in snapshot.caution_components
    assert snapshot.profile_scores["pkg_profile"] > snapshot.profile_scores["local_default"]
    assert snapshot.lessons


def test_experiment_memory_tracks_failure_patterns_and_mutation_bias():
    memory = ExperimentMemory()
    records = [
        ExperimentRecord(
            component="sample.py",
            execution_profile="llm_default",
            promotion_state=PromotionState.CANDIDATE,
            evidence_tier=EvidenceTier.LOCAL,
            pass_rate=0.0,
            weighted_fitness=0.1,
            failure_class="rollback",
            failure_signature="rollback:apply_or_test",
            fitness=FitnessScore(correctness=0.0),
        ),
        ExperimentRecord(
            component="sample.py",
            execution_profile="llm_default",
            promotion_state=PromotionState.CANDIDATE,
            evidence_tier=EvidenceTier.LOCAL,
            pass_rate=0.0,
            weighted_fitness=0.1,
            failure_class="rollback",
            failure_signature="rollback:apply_or_test",
            fitness=FitnessScore(correctness=0.0),
        ),
        ExperimentRecord(
            component="strong.py",
            execution_profile="pkg_profile",
            promotion_state=PromotionState.COMPONENT_PASS,
            evidence_tier=EvidenceTier.COMPONENT,
            pass_rate=1.0,
            weighted_fitness=0.85,
            fitness=FitnessScore(correctness=1.0, safety=1.0),
        ),
    ]

    snapshot = memory.analyze(records)

    assert snapshot.failure_classes["rollback"] == 2
    assert snapshot.failure_signatures["rollback:apply_or_test"] == 2
    assert snapshot.component_mutation_bias["sample.py"] < 1.0
    assert snapshot.profile_mutation_bias["pkg_profile"] > 1.0
    assert snapshot.avoidance_hints
