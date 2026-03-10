from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.artifact_store import RuntimeArtifactStore
from dharma_swarm.runtime_state import RuntimeStateStore


def test_runtime_artifact_store_writes_manifest_and_records_runtime_state(tmp_path: Path) -> None:
    runtime_state = RuntimeStateStore(tmp_path / "runtime.db")
    store = RuntimeArtifactStore(
        base_dir=tmp_path / "workspace" / "sessions",
        runtime_state=runtime_state,
    )

    stored = store.create_text_artifact(
        session_id="sess-art",
        artifact_type="documents",
        artifact_kind="report",
        content="# Report\n\nworld class artifact",
        created_by="codex",
        task_id="task-art",
        run_id="run-art",
        promotion_state="published",
        metadata={"topic": "runtime"},
        provenance={"source": "test"},
    )

    manifest_path = stored.manifest_path
    payload = Path(stored.record.payload_path)

    assert payload.exists()
    assert payload.read_text() == "# Report\n\nworld class artifact"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["artifact_kind"] == "report"
    assert manifest["promotion_state"] == "published"
    assert stored.record.manifest_path == str(manifest_path)
    assert stored.record.metadata["topic"] == "runtime"


def test_runtime_artifact_store_records_existing_file(tmp_path: Path) -> None:
    source = tmp_path / "existing.md"
    source.write_text("checkpoint")
    store = RuntimeArtifactStore(base_dir=tmp_path / "workspace" / "sessions")

    stored = store.record_existing_artifact(
        source,
        session_id="sess-existing",
        artifact_type="documents",
        artifact_kind="checkpoint",
        created_by="codex",
        promotion_state="shared",
    )

    assert stored.record.payload_path == str(source)
    assert stored.record.promotion_state == "shared"
    assert stored.manifest_path.exists()


@pytest.mark.asyncio
async def test_runtime_artifact_store_async_creation_persists_runtime_row(tmp_path: Path) -> None:
    runtime_state = RuntimeStateStore(tmp_path / "runtime.db")
    store = RuntimeArtifactStore(
        base_dir=tmp_path / "workspace" / "sessions",
        runtime_state=runtime_state,
    )

    stored = await store.create_text_artifact_async(
        session_id="sess-async-art",
        artifact_type="documents",
        artifact_kind="report",
        content="async persistence path",
        created_by="codex",
        task_id="task-async-art",
        run_id="run-async-art",
        trace_id="trace-async-art",
        promotion_state="shared",
        metadata={"mode": "async"},
    )

    persisted = await runtime_state.get_artifact(stored.record.artifact_id)

    assert persisted is not None
    assert persisted.artifact_id == stored.record.artifact_id
    assert persisted.payload_path == stored.record.payload_path
    assert persisted.metadata["trace_id"] == "trace-async-art"
    assert persisted.metadata["mode"] == "async"
