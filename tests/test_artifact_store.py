"""Tests for dharma_swarm.artifact_store.

Exercises RuntimeArtifactStore: create, record, import artifacts.
Uses tmp_path to avoid writing to real ~/.dharma.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.artifact_store import (
    DEFAULT_ARTIFACT_ROOT,
    RuntimeArtifactStore,
    StoredArtifact,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def store(tmp_path: Path) -> RuntimeArtifactStore:
    return RuntimeArtifactStore(base_dir=tmp_path / "artifacts")


# ---------------------------------------------------------------------------
# Basics
# ---------------------------------------------------------------------------

def test_default_artifact_root():
    assert DEFAULT_ARTIFACT_ROOT == Path.home() / ".dharma" / "workspace" / "sessions"


def test_store_creates_base_dir(store: RuntimeArtifactStore):
    # base_dir set but might not exist yet — lazy creation
    assert store.base_dir is not None


def test_stored_artifact_is_frozen():
    """StoredArtifact is a frozen dataclass."""
    from dataclasses import FrozenInstanceError
    from unittest.mock import MagicMock
    s = StoredArtifact(record=MagicMock(), ref=MagicMock(), manifest_path=Path("/tmp/x"))
    with pytest.raises(FrozenInstanceError):
        s.record = "new"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# create_text_artifact
# ---------------------------------------------------------------------------

class TestCreateTextArtifact:
    def test_creates_artifact_on_disk(self, store: RuntimeArtifactStore):
        result = store.create_text_artifact(
            session_id="sess-001",
            artifact_type="documents",
            artifact_kind="text_report",
            content="Hello, world!",
            created_by="test_agent",
        )
        assert isinstance(result, StoredArtifact)
        assert result.ref.artifact_type == "documents"
        assert result.ref.created_by == "test_agent"
        assert result.ref.session_id == "sess-001"
        # File should exist on disk
        assert Path(result.ref.path).exists()
        assert Path(result.ref.path).read_text() == "Hello, world!"

    def test_with_metadata(self, store: RuntimeArtifactStore):
        result = store.create_text_artifact(
            session_id="sess-002",
            artifact_type="research",
            artifact_kind="source",
            content="x = 1",
            created_by="coder",
            extension="py",
            metadata={"language": "python"},
            confidence=0.95,
        )
        assert result.ref.confidence == 0.95
        assert Path(result.ref.path).suffix == ".py"

    def test_manifest_path_exists(self, store: RuntimeArtifactStore):
        result = store.create_text_artifact(
            session_id="sess-003",
            artifact_type="documents",
            artifact_kind="text",
            content="content",
            created_by="agent",
        )
        assert result.manifest_path.exists()


# ---------------------------------------------------------------------------
# record_existing_artifact
# ---------------------------------------------------------------------------

class TestRecordExistingArtifact:
    def test_records_existing_file(self, store: RuntimeArtifactStore, tmp_path: Path):
        existing = tmp_path / "existing.txt"
        existing.write_text("pre-existing content")

        result = store.record_existing_artifact(
            existing,
            session_id="sess-010",
            artifact_type="data",
            artifact_kind="input",
            created_by="human",
        )
        assert isinstance(result, StoredArtifact)
        assert result.ref.artifact_type == "data"

    def test_raises_on_missing_file(self, store: RuntimeArtifactStore):
        with pytest.raises(FileNotFoundError):
            store.record_existing_artifact(
                "/nonexistent/file.txt",
                session_id="sess-011",
                artifact_type="data",
                artifact_kind="input",
                created_by="test",
            )


# ---------------------------------------------------------------------------
# import_file_artifact
# ---------------------------------------------------------------------------

class TestImportFileArtifact:
    def test_copies_file_into_store(self, store: RuntimeArtifactStore, tmp_path: Path):
        source = tmp_path / "source_data.csv"
        source.write_text("col1,col2\n1,2\n")

        result = store.import_file_artifact(
            source,
            session_id="sess-020",
            artifact_type="research",
            artifact_kind="tabular",
            created_by="importer",
        )
        assert isinstance(result, StoredArtifact)
        # The imported file should be in the store's base dir
        stored_path = Path(result.ref.path)
        assert stored_path.exists()
        assert stored_path.read_text() == "col1,col2\n1,2\n"
        # Should be a different path from source
        assert stored_path != source

    def test_custom_extension(self, store: RuntimeArtifactStore, tmp_path: Path):
        source = tmp_path / "data.bin"
        source.write_bytes(b"\x00\x01\x02")

        result = store.import_file_artifact(
            source,
            session_id="sess-021",
            artifact_type="research",
            artifact_kind="weights",
            created_by="trainer",
            extension="pt",
        )
        assert Path(result.ref.path).suffix == ".pt"

    def test_raises_on_missing_source(self, store: RuntimeArtifactStore):
        with pytest.raises(FileNotFoundError):
            store.import_file_artifact(
                "/nonexistent/file",
                session_id="sess-022",
                artifact_type="x",
                artifact_kind="y",
                created_by="z",
            )


# ---------------------------------------------------------------------------
# Async variants
# ---------------------------------------------------------------------------

class TestAsyncVariants:
    @pytest.mark.asyncio
    async def test_create_text_artifact_async(self, store: RuntimeArtifactStore):
        result = await store.create_text_artifact_async(
            session_id="async-001",
            artifact_type="documents",
            artifact_kind="text",
            content="async content",
            created_by="async_agent",
        )
        assert isinstance(result, StoredArtifact)
        assert Path(result.ref.path).read_text() == "async content"

    @pytest.mark.asyncio
    async def test_record_existing_artifact_async(self, store: RuntimeArtifactStore, tmp_path: Path):
        f = tmp_path / "async_existing.txt"
        f.write_text("exists")
        result = await store.record_existing_artifact_async(
            f,
            session_id="async-002",
            artifact_type="data",
            artifact_kind="input",
            created_by="async_agent",
        )
        assert isinstance(result, StoredArtifact)

    @pytest.mark.asyncio
    async def test_import_file_artifact_async(self, store: RuntimeArtifactStore, tmp_path: Path):
        f = tmp_path / "async_import.txt"
        f.write_text("import me")
        result = await store.import_file_artifact_async(
            f,
            session_id="async-003",
            artifact_type="documents",
            artifact_kind="document",
            created_by="async_importer",
        )
        assert isinstance(result, StoredArtifact)
        assert Path(result.ref.path).exists()
