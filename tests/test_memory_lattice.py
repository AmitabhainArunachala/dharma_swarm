from __future__ import annotations

import pytest

from dharma_swarm.memory_lattice import MemoryLattice
from dharma_swarm.models import MemoryLayer
from dharma_swarm.runtime_contract import RuntimeEnvelope, RuntimeEventType


@pytest.mark.asyncio
async def test_memory_lattice_records_fact_indexes_memory_and_recalls(tmp_path) -> None:
    lattice = MemoryLattice(
        db_path=tmp_path / "runtime.db",
        event_log_dir=tmp_path / "events",
    )
    await lattice.init_db()

    await lattice.remember(
        "Development shift: isolated workspaces with publish/promote reduce collisions.",
        MemoryLayer.DEVELOPMENT,
        source="developer",
        development_marker=True,
    )
    await lattice.ingest_runtime_envelope(
        RuntimeEnvelope.create(
            event_type=RuntimeEventType.ACTION_EVENT,
            source="operator.bridge",
            agent_id="agent-1",
            session_id="sess-1",
            trace_id="trace-1",
            payload={
                "action_name": "workspace_publish",
                "decision": "recorded",
                "confidence": 1.0,
            },
        )
    )
    fact = await lattice.record_fact(
        "Use explicit publish/promote for shared workspace artifacts.",
        fact_kind="workspace_rule",
        truth_state="promoted",
        confidence=0.92,
        session_id="sess-1",
        task_id="task-1",
        metadata={"topic": "workspace"},
    )

    hits = await lattice.recall(
        "publish workspace artifacts",
        limit=5,
        session_id="sess-1",
    )
    always_on = await lattice.always_on_context(max_chars=800)

    assert fact.truth_state == "promoted"
    assert hits
    assert {hit.source_kind for hit in hits} >= {"memory_fact", "runtime_event"}
    assert "Recent Developments" in always_on

    await lattice.close()
