from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from dharma_swarm.auto_grade.models import GradeCard, RewardSignal
from dharma_swarm.evolution import DarwinEngine
from dharma_swarm.optimizer_bridge import RuntimeFieldMutation
from dharma_swarm.runtime_fields import RuntimeFieldRegistry


@dataclass
class _Sampler:
    temperature: float = 0.7


@dataclass
class _Workflow:
    system_prompt: str = "Research carefully."
    sampler: _Sampler = field(default_factory=_Sampler)


def _reward_signal(*, final_score: float = 0.84, promotion_state: str = "candidate") -> RewardSignal:
    grade_card = GradeCard(
        task_id="task-runtime-field",
        report_id="report-runtime-field",
        groundedness=0.91,
        citation_precision=0.9,
        citation_coverage=0.9,
        source_quality=0.88,
        source_diversity=0.82,
        topical_coverage=0.86,
        contradiction_handling=0.84,
        freshness=0.9,
        structure=0.83,
        actionability=0.8,
        novelty=0.72,
        traceability=0.89,
        final_score=final_score,
        promotion_state=promotion_state,
        metadata={"cost_norm": 0.2, "latency_norm": 0.25, "token_norm": 0.3},
    )
    return RewardSignal(
        task_id=grade_card.task_id,
        report_id=grade_card.report_id,
        grade_card=grade_card,
        scalar_reward=final_score,
        gate_multiplier=1.0,
    )


@pytest.mark.asyncio
async def test_darwin_engine_runs_runtime_field_trial_and_archives_reward_fitness(tmp_path) -> None:
    workflow = _Workflow()
    registry = RuntimeFieldRegistry()
    registry.track(
        [
            (workflow, "system_prompt"),
            (workflow, "sampler.temperature", "temperature"),
        ]
    )

    engine = DarwinEngine(
        archive_path=tmp_path / "archive.jsonl",
        traces_path=tmp_path / "traces",
        predictor_path=tmp_path / "predictor.jsonl",
    )
    await engine.init()

    result = await engine.run_runtime_field_trial(
        component="auto_research",
        registry=registry,
        mutations=[
            RuntimeFieldMutation(field_name="temperature", candidate_value=0.2),
            RuntimeFieldMutation(
                field_name="system_prompt",
                candidate_value="Research carefully and challenge weak claims.",
            ),
        ],
        evaluate=lambda: _reward_signal(final_score=0.87, promotion_state="shared"),
        description="Tune runtime fields for research quality.",
    )

    stored = await engine.archive.get_entry(result.archive_entry_id)

    assert stored is not None
    assert stored.change_type == "runtime_field_trial"
    assert stored.fitness.correctness == pytest.approx(0.87)
    assert stored.promotion_state == "candidate"
    assert stored.test_results["runtime_field_trial"]["mutated_fields"] == [
        "temperature",
        "system_prompt",
    ]
    assert stored.test_results["runtime_field_trial"]["reward_promotion_state"] == "shared"
    assert result.trial_result.rolled_back is True
    assert workflow.sampler.temperature == 0.7
    assert workflow.system_prompt == "Research carefully."


@pytest.mark.asyncio
async def test_darwin_engine_archives_failed_runtime_field_trial_and_rolls_back(tmp_path) -> None:
    workflow = _Workflow()
    registry = RuntimeFieldRegistry()
    registry.track(
        [
            (workflow, "system_prompt"),
            (workflow, "sampler.temperature", "temperature"),
        ]
    )

    engine = DarwinEngine(
        archive_path=tmp_path / "archive.jsonl",
        traces_path=tmp_path / "traces",
        predictor_path=tmp_path / "predictor.jsonl",
    )
    await engine.init()

    def _fail() -> RewardSignal:
        raise RuntimeError("grade failed")

    result = await engine.run_runtime_field_trial(
        component="auto_research",
        registry=registry,
        mutations=[RuntimeFieldMutation(field_name="temperature", candidate_value=0.1)],
        evaluate=_fail,
        description="Failing runtime-field trial.",
    )

    stored = await engine.archive.get_entry(result.archive_entry_id)

    assert stored is not None
    assert stored.change_type == "runtime_field_trial"
    assert stored.fitness.safety == pytest.approx(0.0)
    assert stored.gates_failed == ["grade failed"]
    assert stored.test_results["runtime_field_trial"]["error"] == "grade failed"
    assert result.reward_signal is None
    assert result.trial_result.rolled_back is True
    assert workflow.sampler.temperature == 0.7
