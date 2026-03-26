from __future__ import annotations

import pytest

from dharma_swarm.archive import ArchiveEntry, EvolutionArchive, research_reward_to_fitness
from dharma_swarm.evaluation_registry import EvaluationRegistry
from dharma_swarm.evaluator import ResearchEvaluator
from dharma_swarm.memory_lattice import MemoryLattice
from dharma_swarm.runtime_state import DelegationRun, RuntimeStateStore, SessionState
from dharma_swarm.auto_research.models import ClaimRecord, ResearchBrief, ResearchReport, SourceDocument


def _research_payload() -> tuple[ResearchReport, list[SourceDocument]]:
    brief = ResearchBrief(
        task_id="task-research-eval",
        topic="Research evaluation",
        question="How should reports be registered?",
        requires_recency=True,
        metadata={"sources_requested": True},
    )
    sources = [
        SourceDocument(
            source_id="src-1",
            url="https://docs.example.org/spec",
            authority_score=0.95,
            freshness_score=0.94,
            source_type="docs",
        ),
        SourceDocument(
            source_id="src-2",
            url="https://research.example.com/paper",
            authority_score=0.91,
            freshness_score=0.90,
            source_type="paper",
        ),
        SourceDocument(
            source_id="src-3",
            url="https://ops.example.net/report",
            authority_score=0.88,
            freshness_score=0.86,
            source_type="web",
        ),
    ]
    report = ResearchReport(
        report_id="report-task-research-eval",
        task_id="task-research-eval",
        brief=brief,
        summary="Registered research summary.",
        body="- Registration should preserve final scores. [src-1]\n- Promotion decisions should be persisted canonically. [src-2] [src-3]\nRecommended next step: register the reward signal.",
        claims=[
            ClaimRecord(
                claim_id="claim-1",
                text="Registration should preserve final scores.",
                support_level="supported",
                supporting_source_ids=["src-1"],
                citations=["[src-1]"],
                confidence=0.93,
            ),
            ClaimRecord(
                claim_id="claim-2",
                text="Promotion decisions should be persisted canonically.",
                support_level="supported",
                supporting_source_ids=["src-2", "src-3"],
                citations=["[src-2]", "[src-3]"],
                confidence=0.90,
            ),
        ],
        source_ids=["src-1", "src-2", "src-3"],
        metadata={"topical_coverage": 0.91, "novelty": 0.70},
    )
    return report, sources


@pytest.mark.asyncio
async def test_evaluation_registry_records_research_grade_into_canonical_truth(tmp_path) -> None:
    db_path = tmp_path / "runtime.db"
    runtime_state = RuntimeStateStore(db_path)
    memory_lattice = MemoryLattice(db_path=db_path, event_log_dir=tmp_path / "events")
    await runtime_state.init_db()
    await memory_lattice.init_db()

    await runtime_state.upsert_session(
        SessionState(
            session_id="sess-research",
            operator_id="operator",
            status="active",
            current_task_id="task-research-eval",
        )
    )
    await runtime_state.record_delegation_run(
        DelegationRun(
            run_id="run-research",
            session_id="sess-research",
            task_id="task-research-eval",
            assigned_to="agent-research",
            assigned_by="operator",
            status="completed",
            metadata={"trace_id": "trace-research"},
        )
    )

    report, sources = _research_payload()
    reward = ResearchEvaluator().evaluate(
        report,
        sources,
        latency_ms=1400,
        token_cost_usd=0.05,
        total_tokens=1800,
        cost_budget_usd=1.0,
        latency_budget_ms=6000,
        token_budget=6000,
    )

    registry = EvaluationRegistry(
        runtime_state=runtime_state,
        memory_lattice=memory_lattice,
        workspace_root=tmp_path / "workspace" / "sessions",
        provenance_root=tmp_path / "workspace" / "sessions",
    )
    result = await registry.record_research_grade(
        reward.model_dump(),
        run_id="run-research",
        created_by="codex",
    )

    artifact_path = tmp_path / "workspace" / "sessions" / "sess-research" / "artifacts" / "evaluations"
    provenance_log = tmp_path / "workspace" / "sessions" / "sess-research" / "provenance" / "log.jsonl"
    stream_rows = memory_lattice.event_log.read_envelopes(
        stream="research_evaluations",
        session_id="sess-research",
    )
    persisted_artifact = await runtime_state.get_artifact(result.artifact.artifact_id)

    assert persisted_artifact is not None
    assert persisted_artifact.artifact_kind == "research_reward_signal"
    assert artifact_path.exists()
    assert result.manifest_path.exists()
    assert {fact.fact_kind for fact in result.facts} == {"research_grade", "research_promotion_decision"}
    assert result.summary["final_score"] == pytest.approx(reward.grade_card.final_score)
    assert result.summary["promotion_state"] == reward.grade_card.promotion_state
    assert stream_rows[-1]["payload"]["action_name"] == "record_research_grade"
    assert provenance_log.exists()
    assert "research_grade_recorded" in provenance_log.read_text(encoding="utf-8")

    await memory_lattice.close()


@pytest.mark.asyncio
async def test_research_reward_projects_into_archive_fitness(tmp_path) -> None:
    report, sources = _research_payload()
    reward = ResearchEvaluator().evaluate(
        report,
        sources,
        latency_ms=1600,
        token_cost_usd=0.07,
        total_tokens=2000,
        cost_budget_usd=1.0,
        latency_budget_ms=6000,
        token_budget=6000,
    )
    archive = EvolutionArchive(path=tmp_path / "archive.jsonl")
    await archive.load()

    fitness = research_reward_to_fitness(reward)
    entry = ArchiveEntry(
        component="auto_research",
        change_type="evaluation",
        description="Research reward projection",
        fitness=fitness,
        status="applied",
        promotion_state=reward.grade_card.promotion_state,
    )
    await archive.add_entry(entry)

    best = await archive.get_best(n=1, component="auto_research")

    assert fitness.correctness == pytest.approx(reward.grade_card.final_score)
    assert fitness.safety == pytest.approx(1.0)
    assert best[0].fitness.correctness == pytest.approx(reward.grade_card.final_score)
