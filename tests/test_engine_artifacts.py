"""Tests for dharma_swarm.engine.artifacts."""

from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.engine.artifacts import ArtifactStore, ALLOWED_ARTIFACT_TYPES


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(base_dir=tmp_path / "workspace" / "sessions")


def test_create_artifact_writes_file_and_ref(store: ArtifactStore):
    ref = store.create_artifact(
        session_id="sess-1",
        artifact_type="research",
        content="# findings",
        created_by="researcher",
        citations=["doi:10.1000/x"],
    )

    assert ref.version == 1
    assert ref.artifact_type == "research"
    assert ref.created_by == "researcher"
    assert ref.citations == ["doi:10.1000/x"]
    assert Path(ref.path).exists()
    assert Path(ref.path).read_text() == "# findings"


def test_update_artifact_bumps_version_keeps_identity(store: ArtifactStore):
    ref1 = store.create_artifact(
        session_id="sess-1",
        artifact_type="code",
        content="print('v1')",
        created_by="builder",
        extension="py",
    )
    ref2 = store.update_artifact(ref1, new_content="print('v2')", confidence=0.8)

    assert ref2.artifact_id == ref1.artifact_id
    assert ref2.version == ref1.version + 1
    assert ref2.confidence == 0.8
    assert Path(ref2.path).read_text() == "print('v2')"
    assert Path(ref1.path).read_text() == "print('v1')"


def test_read_artifact_returns_content(store: ArtifactStore):
    ref = store.create_artifact(
        session_id="sess-1",
        artifact_type="documents",
        content="doc body",
        created_by="builder",
    )
    assert store.read_artifact(ref) == "doc body"


def test_invalid_artifact_type_raises(store: ArtifactStore):
    bad = "notes"
    assert bad not in ALLOWED_ARTIFACT_TYPES
    with pytest.raises(ValueError, match="Unknown artifact_type"):
        store.create_artifact(
            session_id="sess-1",
            artifact_type=bad,
            content="x",
            created_by="builder",
        )


def test_ensure_session_dirs_creates_expected_layout(store: ArtifactStore):
    store.ensure_session_dirs("sess-99")
    root = store.session_root("sess-99")
    assert (root / "artifacts" / "research").exists()
    assert (root / "artifacts" / "code").exists()
    assert (root / "artifacts" / "documents").exists()
    assert (root / "artifacts" / "evaluations").exists()
    assert (root / "knowledge").exists()
    assert (root / "provenance").exists()
