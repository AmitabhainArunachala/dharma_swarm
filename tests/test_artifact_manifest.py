from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.artifact_manifest import (
    ARTIFACT_MANIFEST_VERSION,
    ArtifactManifestStore,
)
from dharma_swarm.engine.artifacts import ArtifactStore
from dharma_swarm.runtime_state import RuntimeStateStore


@pytest.fixture
def artifact_store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(base_dir=tmp_path / "workspace" / "sessions")


def test_record_manifest_writes_sidecar_with_checksum(artifact_store: ArtifactStore) -> None:
    ref = artifact_store.create_artifact(
        session_id="sess-manifest",
        artifact_type="research",
        content="# canonical findings\n",
        created_by="builder",
        citations=["doi:10.1/example"],
        depends_on=["parent-a"],
        metadata={"lane": "research"},
    )

    store = ArtifactManifestStore()
    manifest, manifest_path = store.record_manifest(
        ref,
        task_id="task-1",
        run_id="run-1",
        trace_id="trace-1",
        promotion_state="published",
        source_event_ids=["evt-1"],
        provenance={"agent": "builder", "model": "nim"},
        metadata={"score": 0.98},
    )

    on_disk = json.loads(Path(manifest_path).read_text(encoding="utf-8"))

    assert manifest_path.exists()
    assert manifest.manifest_version == ARTIFACT_MANIFEST_VERSION
    assert manifest.payload_path == ref.path
    assert len(manifest.payload_checksum) == 64
    assert manifest.promotion_state == "published"
    assert manifest.citations == ["doi:10.1/example"]
    assert manifest.depends_on == ["parent-a"]
    assert manifest.metadata["lane"] == "research"
    assert manifest.metadata["score"] == 0.98
    assert on_disk["artifact_id"] == ref.artifact_id
    assert on_disk["trace_id"] == "trace-1"
    assert on_disk["source_event_ids"] == ["evt-1"]


def test_read_manifest_round_trip(artifact_store: ArtifactStore) -> None:
    ref = artifact_store.create_artifact(
        session_id="sess-roundtrip",
        artifact_type="code",
        content="print('ok')\n",
        created_by="builder",
        extension="py",
    )

    store = ArtifactManifestStore()
    written, manifest_path = store.record_manifest(ref, task_id="task-2")
    loaded = store.read_manifest(manifest_path)

    assert loaded == written
    assert loaded.content_type == "text/x-python"


@pytest.mark.asyncio
async def test_manifest_converts_to_runtime_artifact_record(artifact_store: ArtifactStore, tmp_path: Path) -> None:
    ref = artifact_store.create_artifact(
        session_id="sess-runtime",
        artifact_type="evaluations",
        content='{"score": 1.0}\n',
        created_by="validator",
        extension="json",
        metadata={"workload": "routing"},
    )

    store = ArtifactManifestStore()
    manifest, manifest_path = store.record_manifest(
        ref,
        task_id="task-runtime",
        run_id="run-runtime",
        trace_id="trace-runtime",
        promotion_state="candidate",
        provenance={"session": "sess-runtime"},
    )

    runtime_store = RuntimeStateStore(tmp_path / "runtime.db")
    await runtime_store.init_db()
    record = await runtime_store.record_artifact(
        store.to_artifact_record(manifest, manifest_path=manifest_path)
    )

    assert record.artifact_id == ref.artifact_id
    assert record.manifest_path == str(manifest_path)
    assert record.payload_path == ref.path
    assert record.checksum == manifest.payload_checksum
    assert record.promotion_state == "candidate"
    assert record.metadata["workload"] == "routing"
    assert record.metadata["trace_id"] == "trace-runtime"
    assert record.metadata["provenance"] == {"session": "sess-runtime"}
