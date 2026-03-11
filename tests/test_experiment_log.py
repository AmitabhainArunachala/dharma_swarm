"""Tests for Darwin experiment log persistence."""

import pytest

from dharma_swarm.archive import FitnessScore
from dharma_swarm.execution_profile import EvidenceTier, PromotionState
from dharma_swarm.experiment_log import ExperimentLog, ExperimentRecord


@pytest.mark.asyncio
async def test_experiment_log_round_trip(tmp_path):
    log = ExperimentLog(path=tmp_path / "experiments.jsonl")
    record = ExperimentRecord(
        proposal_id="proposal-1",
        archive_entry_id="entry-1",
        component="pkg/example.py",
        execution_profile="pkg-profile",
        evidence_tier=EvidenceTier.COMPONENT,
        promotion_state=PromotionState.COMPONENT_PASS,
        weighted_fitness=0.88,
        fitness=FitnessScore(correctness=1.0, safety=1.0),
    )

    record_id = await log.append(record)
    recent = await log.get_recent(limit=5)

    assert record_id == record.id
    assert len(recent) == 1
    assert recent[0].component == "pkg/example.py"
    assert recent[0].promotion_state == PromotionState.COMPONENT_PASS
    assert recent[0].weighted_fitness == pytest.approx(0.88)
