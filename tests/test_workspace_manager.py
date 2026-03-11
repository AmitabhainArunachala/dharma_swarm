from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.artifact_store import RuntimeArtifactStore
from dharma_swarm.runtime_state import RuntimeStateStore
from dharma_swarm.workspace_manager import WorkspaceManager


@pytest.mark.asyncio
async def test_workspace_manager_creates_agent_workspace_and_promotes_file(tmp_path: Path) -> None:
    runtime_state = RuntimeStateStore(tmp_path / "runtime.db")
    artifact_store = RuntimeArtifactStore(
        base_dir=tmp_path / "workspace" / "sessions",
        runtime_state=runtime_state,
    )
    manager = WorkspaceManager(
        base_dir=tmp_path / "workspace",
        runtime_state=runtime_state,
        artifact_store=artifact_store,
        lock_dir=tmp_path / "locks",
    )

    agent_ws = await manager.ensure_agent_workspace("run-1")
    draft = agent_ws / "draft.md"
    draft.write_text("draft output")

    promoted = await manager.promote_file(
        draft,
        holder_run_id="run-1",
        relative_dest="reports/final.md",
        session_id="sess-ws",
        task_id="task-ws",
        artifact_kind="published_report",
        created_by="codex",
    )

    leases = await runtime_state.list_workspace_leases(holder_run_id="run-1", active_only=False, limit=10)
    artifacts = await runtime_state.list_artifacts(task_id="task-ws", limit=10)

    assert agent_ws.exists()
    assert promoted.destination_path.exists()
    assert promoted.destination_path.read_text() == "draft output"
    assert promoted.lease.mode == "publish"
    assert leases[0].released_at is not None
    assert artifacts[0].artifact_kind == "published_report"
    assert artifacts[0].promotion_state == "published"
