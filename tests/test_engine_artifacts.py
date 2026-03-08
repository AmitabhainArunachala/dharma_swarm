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


# ---------------------------------------------------------------------------
# ArtifactRef serialization round-trip
# ---------------------------------------------------------------------------


def test_artifact_ref_to_dict_from_dict_round_trip(store: ArtifactStore):
    """to_dict / from_dict should preserve all fields."""
    from dharma_swarm.engine.artifacts import ArtifactRef

    ref = store.create_artifact(
        session_id="sess-rt",
        artifact_type="evaluations",
        content="eval data",
        created_by="validator",
        confidence=0.75,
        citations=["ref-1", "ref-2"],
        depends_on=["dep-abc"],
        metadata={"score": 42},
    )

    d = ref.to_dict()
    restored = ArtifactRef.from_dict(d)

    assert restored.artifact_id == ref.artifact_id
    assert restored.artifact_type == ref.artifact_type
    assert restored.path == ref.path
    assert restored.created_by == ref.created_by
    assert restored.session_id == ref.session_id
    assert restored.version == ref.version
    assert restored.confidence == ref.confidence
    assert restored.citations == ref.citations
    assert restored.depends_on == ref.depends_on
    assert restored.metadata == ref.metadata


def test_artifact_ref_from_dict_defaults():
    """from_dict should handle missing optional fields gracefully."""
    from dharma_swarm.engine.artifacts import ArtifactRef

    minimal = {
        "artifact_id": "abc",
        "artifact_type": "research",
        "path": "/tmp/x",
        "created_by": "test",
        "session_id": "s1",
    }
    ref = ArtifactRef.from_dict(minimal)
    assert ref.version == 1
    assert ref.confidence == 0.0
    assert ref.citations == []
    assert ref.depends_on == []
    assert ref.metadata == {}


# ---------------------------------------------------------------------------
# update_artifact edge cases
# ---------------------------------------------------------------------------


def test_update_artifact_with_new_citations_and_depends(store: ArtifactStore):
    """update_artifact should replace citations and depends_on when provided."""
    ref = store.create_artifact(
        session_id="sess-up",
        artifact_type="research",
        content="v1",
        created_by="researcher",
        citations=["old-cite"],
        depends_on=["old-dep"],
    )
    ref2 = store.update_artifact(
        ref,
        new_content="v2",
        citations=["new-cite-a", "new-cite-b"],
        depends_on=["new-dep"],
    )
    assert ref2.citations == ["new-cite-a", "new-cite-b"]
    assert ref2.depends_on == ["new-dep"]
    assert ref2.version == 2


def test_update_artifact_preserves_fields_when_none(store: ArtifactStore):
    """update_artifact should keep old values when optional args are None."""
    ref = store.create_artifact(
        session_id="sess-pres",
        artifact_type="code",
        content="orig",
        created_by="builder",
        confidence=0.6,
        citations=["c1"],
        depends_on=["d1"],
        extension="py",
    )
    ref2 = store.update_artifact(ref, new_content="new")
    assert ref2.confidence == 0.6
    assert ref2.citations == ["c1"]
    assert ref2.depends_on == ["d1"]


# ---------------------------------------------------------------------------
# Custom extension
# ---------------------------------------------------------------------------


def test_create_artifact_with_custom_extension(store: ArtifactStore):
    """Artifacts with non-default extensions should use that extension on disk."""
    ref = store.create_artifact(
        session_id="sess-ext",
        artifact_type="code",
        content="import os",
        created_by="builder",
        extension="py",
    )
    assert ref.path.endswith(".py")
    assert Path(ref.path).read_text() == "import os"


def test_create_artifact_stores_metadata(store: ArtifactStore):
    """Metadata dict should be preserved in the returned ArtifactRef."""
    ref = store.create_artifact(
        session_id="sess-meta",
        artifact_type="research",
        content="data",
        created_by="analyst",
        metadata={"model": "mistral-7b", "layer": 27},
    )
    assert ref.metadata == {"model": "mistral-7b", "layer": 27}
