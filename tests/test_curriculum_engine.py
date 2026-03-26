from __future__ import annotations

import pytest

from dharma_swarm.agent_registry import AgentRegistry
from dharma_swarm.auto_grade.models import GradeCard, RewardSignal
from dharma_swarm.auto_research.models import ClaimRecord, ResearchBrief, ResearchReport
from dharma_swarm.evolution import DarwinEngine


def _report_with_frontier_signals() -> ResearchReport:
    brief = ResearchBrief(
        task_id="task-frontier",
        topic="Curriculum generation",
        question="What should the system learn next?",
        requires_recency=True,
        metadata={"sources_requested": True},
    )
    return ResearchReport(
        report_id="report-frontier",
        task_id="task-frontier",
        brief=brief,
        summary="Weak research report.",
        body="This report is stale, uncertain, and contains unresolved contradictions.",
        claims=[
            ClaimRecord(
                claim_id="claim-low-confidence",
                text="This claim is uncertain.",
                support_level="inferred",
                confidence=0.32,
            )
        ],
        source_ids=["src-1"],
        contradictions=[
            {"claim_id": "claim-low-confidence", "severity": "high", "status": "unresolved"},
        ],
        metadata={"topical_coverage": 0.4, "novelty": 0.2},
    )


def _poor_reward_signal() -> RewardSignal:
    grade_card = GradeCard(
        task_id="task-frontier",
        report_id="report-frontier",
        groundedness=0.42,
        citation_precision=0.35,
        citation_coverage=0.4,
        source_quality=0.45,
        source_diversity=0.3,
        topical_coverage=0.4,
        contradiction_handling=0.1,
        freshness=0.2,
        structure=0.5,
        actionability=0.3,
        novelty=0.2,
        traceability=0.3,
        gate_failures=["freshness", "citation_precision", "unresolved_high_severity_contradictions"],
        final_score=0.28,
        promotion_state="rollback_or_revise",
        metadata={"unsupported_claim_ratio": 0.6},
    )
    return RewardSignal(
        task_id=grade_card.task_id,
        report_id=grade_card.report_id,
        grade_card=grade_card,
        scalar_reward=-0.44,
        gate_multiplier=0.0,
    )


def test_frontier_task_contract_roundtrip_preserves_provenance() -> None:
    from dharma_swarm.curriculum_engine import FrontierTask

    task = FrontierTask(
        frontier_id="frontier-1",
        title="Refresh stale research",
        description="Re-run retrieval with recency constraints.",
        source="staleness",
        verifier_type="research_grade",
        difficulty="medium",
        provenance={"report_id": "report-frontier", "task_id": "task-frontier"},
        metadata={"seed_kind": "freshness"},
    )
    clone = FrontierTask.model_validate_json(task.model_dump_json())

    assert clone.source == "staleness"
    assert clone.verifier_type == "research_grade"
    assert clone.difficulty == "medium"
    assert clone.provenance["report_id"] == "report-frontier"


def test_curriculum_engine_derives_frontier_tasks_from_failures_and_uncertainty() -> None:
    from dharma_swarm.curriculum_engine import CurriculumEngine

    engine = CurriculumEngine()
    tasks = engine.derive_frontier_tasks(
        report=_report_with_frontier_signals(),
        reward_signal=_poor_reward_signal(),
    )
    sources = {task.source for task in tasks}

    assert {"gate_failure", "contradiction", "staleness", "uncertainty"} <= sources
    assert all(task.provenance["report_id"] == "report-frontier" for task in tasks)
    assert any(task.provenance.get("gate_failure") == "freshness" for task in tasks)
    assert any(task.provenance.get("claim_id") == "claim-low-confidence" for task in tasks)


@pytest.mark.asyncio
async def test_darwin_engine_exposes_explicit_curriculum_hook_without_archive_side_effects(
    tmp_path,
) -> None:
    from dharma_swarm.curriculum_engine import CurriculumEngine

    engine = DarwinEngine(
        archive_path=tmp_path / "archive.jsonl",
        traces_path=tmp_path / "traces",
        predictor_path=tmp_path / "predictor.jsonl",
    )
    await engine.init()

    tasks = engine.propose_curriculum_tasks(
        report=_report_with_frontier_signals(),
        reward_signal=_poor_reward_signal(),
        curriculum_engine=CurriculumEngine(),
    )
    best = await engine.archive.get_best(n=1)

    assert tasks
    assert any(task.source == "gate_failure" for task in tasks)
    assert best == []


def test_agent_registry_persists_frontier_tasks(tmp_path) -> None:
    from dharma_swarm.curriculum_engine import FrontierTask

    registry = AgentRegistry(agents_dir=tmp_path / "agents")
    registry.register_agent(
        name="Curriculum Agent",
        role="researcher",
        model="local-model",
        system_prompt="Derive the next frontier tasks.",
    )

    frontier_task = FrontierTask(
        frontier_id="frontier-1",
        title="Resolve contradiction",
        description="Investigate the unresolved contradiction.",
        source="contradiction",
        verifier_type="research_grade",
        difficulty="high",
        provenance={"report_id": "report-frontier", "claim_id": "claim-low-confidence"},
        metadata={"seed_kind": "contradiction"},
    )

    registry.append_frontier_tasks("Curriculum Agent", [frontier_task])
    rows = registry.get_frontier_tasks("Curriculum Agent")

    assert rows[0]["source"] == "contradiction"
    assert rows[0]["difficulty"] == "high"
    assert rows[0]["provenance"]["claim_id"] == "claim-low-confidence"
