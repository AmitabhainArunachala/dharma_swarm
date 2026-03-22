from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.contracts import (
    EvaluationSink,
    LearningEngine,
    MemoryPlane,
    MemoryRecord,
    MemoryTruthState,
    SkillPromotionState,
    SkillStore,
)
from dharma_swarm.contracts.common import EvaluationRecord
from dharma_swarm.contracts.intelligence_adapters import (
    SovereignEvaluationSinkAdapter,
    SovereignLearningEngineAdapter,
    SovereignMemoryPlaneAdapter,
    SovereignSkillStoreAdapter,
)
from dharma_swarm.engine.event_memory import EventMemoryStore
from dharma_swarm.runtime_state import DelegationRun, RuntimeStateStore, SessionState


@pytest.fixture
def skill_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "skills"
    directory.mkdir()
    (directory / "surgeon.skill.md").write_text(
        "---\n"
        "name: surgeon\n"
        "tags: [debug, patch]\n"
        "keywords: [fix, bug, repair]\n"
        "---\n"
        "# Surgeon\n\n"
        "Repairs bugs and stabilizes failing code paths.\n",
        encoding="utf-8",
    )
    return directory


async def _runtime_env(tmp_path: Path) -> tuple[RuntimeStateStore, EventMemoryStore]:
    db_path = tmp_path / "runtime.db"
    runtime_state = RuntimeStateStore(db_path)
    event_store = EventMemoryStore(db_path)
    await runtime_state.init_db()
    await runtime_state.upsert_session(
        SessionState(
            session_id="sess-intel",
            operator_id="operator",
            status="active",
            current_task_id="task-intel",
        )
    )
    await runtime_state.record_delegation_run(
        DelegationRun(
            run_id="run-intel",
            session_id="sess-intel",
            task_id="task-intel",
            assigned_to="agent-intel",
            assigned_by="operator",
            status="completed",
            metadata={"trace_id": "trace-intel"},
        )
    )
    return runtime_state, event_store


@pytest.mark.asyncio
async def test_memory_plane_persists_queries_and_promotes_records(tmp_path: Path) -> None:
    runtime_state, event_store = await _runtime_env(tmp_path)
    plane = SovereignMemoryPlaneAdapter(
        runtime_state=runtime_state,
        event_store=event_store,
    )

    assert isinstance(plane, MemoryPlane)

    saved = await plane.write_memory(
        MemoryRecord(
            record_id="mem-intel-1",
            kind="lesson",
            text="Fix the bug by checking retry state before requeueing work.",
            truth_state=MemoryTruthState.CANDIDATE,
            session_id="sess-intel",
            task_id="task-intel",
            agent_id="agent-intel",
            score=0.82,
            metadata={"topic": "retries"},
            provenance={"source_event_id": "evt-source-1"},
        )
    )
    loaded = await plane.get_memory("mem-intel-1")
    queried = await plane.query_memory(
        session_id="sess-intel",
        task_id="task-intel",
        agent_id="agent-intel",
        limit=10,
    )
    promoted = await plane.set_truth_state(
        record_id="mem-intel-1",
        truth_state=MemoryTruthState.PROMOTED,
        metadata={"promoted_by": "beta"},
    )
    audit_hits = await event_store.search_events("set_memory_truth_state mem-intel-1", limit=10)

    assert saved.record_id == "mem-intel-1"
    assert loaded is not None
    assert loaded.provenance["source_event_id"] == "evt-source-1"
    assert queried and queried[0].record_id == "mem-intel-1"
    assert promoted.truth_state is MemoryTruthState.PROMOTED
    assert promoted.metadata["promoted_by"] == "beta"
    assert any(hit["payload"].get("record_id") == "mem-intel-1" for hit in audit_hits)


@pytest.mark.asyncio
async def test_evaluation_sink_records_lists_and_summarizes_subjects(
    tmp_path: Path,
) -> None:
    runtime_state, event_store = await _runtime_env(tmp_path)
    plane = SovereignMemoryPlaneAdapter(runtime_state=runtime_state, event_store=event_store)
    sink = SovereignEvaluationSinkAdapter(
        runtime_state=runtime_state,
        event_store=event_store,
        memory_plane=plane,
    )

    assert isinstance(sink, EvaluationSink)

    first = await sink.record_evaluation(
        EvaluationRecord(
            evaluation_id="eval-intel-1",
            subject_kind="task",
            subject_id="task-intel",
            evaluator="reviewer",
            metric="quality",
            score=0.9,
            run_id="run-intel",
            metadata={
                "preferred_roles": ["surgeon"],
                "recommended_model": "openai/gpt-5-mini",
            },
        )
    )
    await sink.record_evaluation(
        EvaluationRecord(
            evaluation_id="eval-intel-2",
            subject_kind="task",
            subject_id="task-intel",
            evaluator="reviewer",
            metric="latency",
            score=0.6,
            session_id="sess-intel",
            task_id="task-intel",
            metadata={"preferred_roles": ["surgeon"]},
        )
    )

    listed = await sink.list_evaluations(
        subject_kind="task",
        subject_id="task-intel",
        limit=10,
    )
    summary = await sink.summarize_subject(
        subject_kind="task",
        subject_id="task-intel",
    )
    memory_rows = await plane.query_memory(
        task_id="task-intel",
        truth_state=MemoryTruthState.PROMOTED,
        limit=20,
    )
    audit_hits = await event_store.search_events("record_evaluation quality", limit=10)

    assert first.session_id == "sess-intel"
    assert first.task_id == "task-intel"
    assert [row.evaluation_id for row in listed] == ["eval-intel-2", "eval-intel-1"]
    assert summary["evaluation_count"] == 2
    assert summary["metrics"]["quality"]["avg_score"] == 0.9
    assert any(row.kind == "evaluation_metric" for row in memory_rows)
    assert any(hit["payload"].get("evaluation_id") == "eval-intel-1" for hit in audit_hits)


@pytest.mark.asyncio
async def test_learning_engine_drives_a_basic_end_to_end_intelligence_slice(
    tmp_path: Path,
    skill_dir: Path,
) -> None:
    runtime_state, event_store = await _runtime_env(tmp_path)
    plane = SovereignMemoryPlaneAdapter(runtime_state=runtime_state, event_store=event_store)
    skill_store = SovereignSkillStoreAdapter(
        runtime_state=runtime_state,
        skill_dirs=[skill_dir],
    )
    sink = SovereignEvaluationSinkAdapter(
        runtime_state=runtime_state,
        event_store=event_store,
        memory_plane=plane,
    )
    learning = SovereignLearningEngineAdapter(
        runtime_state=runtime_state,
        event_store=event_store,
        memory_plane=plane,
        skill_store=skill_store,
        evaluation_sink=sink,
        skill_dirs=[skill_dir],
    )

    assert isinstance(skill_store, SkillStore)
    assert isinstance(learning, LearningEngine)

    await plane.write_memory(
        MemoryRecord(
            record_id="mem-intel-task",
            kind="task_context",
            text="Fix the failing bug and repair the broken retry path before release.",
            truth_state=MemoryTruthState.CANDIDATE,
            session_id="sess-intel",
            task_id="task-intel",
            agent_id="agent-intel",
            score=0.88,
        )
    )
    await sink.record_evaluation(
        EvaluationRecord(
            evaluation_id="eval-routing-1",
            subject_kind="task",
            subject_id="task-intel",
            evaluator="reviewer",
            metric="routing_fit",
            score=0.95,
            run_id="run-intel",
            metadata={
                "preferred_roles": ["surgeon"],
                "recommended_model": "openai/gpt-5-mini",
            },
        )
    )

    agent_model = await learning.update_agent_model(
        agent_id="agent-intel",
        evidence={
            "session_id": "sess-intel",
            "task_id": "task-intel",
            "preferred_roles": ["surgeon"],
            "preferred_skills": ["surgical-debugging"],
            "traits": {"precision": "high"},
        },
    )
    user_model = await learning.update_user_model(
        user_id="operator-1",
        evidence={
            "session_id": "sess-intel",
            "task_id": "task-intel",
            "preferences": {"risk_tolerance": "low"},
        },
    )
    candidates = await learning.extract_skill_candidates(run_id="run-intel")
    saved = await skill_store.save_skill(candidates[0])
    promoted = await skill_store.promote_skill(
        skill_id=saved.skill_id,
        promotion_state=SkillPromotionState.PROMOTED,
        metadata={"approved_by": "beta"},
    )
    fetched = await skill_store.get_skill(promoted.skill_id)
    skills = await skill_store.list_skills(limit=10)
    hints = await learning.propose_routing_hints(
        task_id="task-intel",
        session_id="sess-intel",
    )

    assert agent_model["preferred_roles"] == ["surgeon"]
    assert user_model["preferences"]["risk_tolerance"] == "low"
    assert candidates
    assert any(candidate.name == "surgeon" for candidate in candidates)
    assert promoted.promotion_state is SkillPromotionState.PROMOTED
    assert promoted.metadata["approved_by"] == "beta"
    assert fetched is not None and fetched.skill_id == promoted.skill_id
    assert any(skill.skill_id == promoted.skill_id for skill in skills)
    assert any(hint.get("preferred_role") == "surgeon" for hint in hints)
    assert any(hint.get("recommended_model") == "openai/gpt-5-mini" for hint in hints)
