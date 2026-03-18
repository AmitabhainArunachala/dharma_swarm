"""Tests for the multimodal media memory system."""

from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.media_memory import (
    MediaArtifact,
    MediaMemory,
    detect_media_type,
)


def test_detect_media_type():
    assert detect_media_type("photo.png") == "image"
    assert detect_media_type("video.mp4") == "video"
    assert detect_media_type("song.mp3") == "audio"
    assert detect_media_type("paper.pdf") == "document"
    assert detect_media_type("main.py") == "code"
    assert detect_media_type("data.json") == "data"
    assert detect_media_type("flow.mermaid") == "diagram"
    assert detect_media_type("unknown.xyz") == "unknown"


@pytest.fixture
def media_dir(tmp_path: Path) -> Path:
    return tmp_path / "media"


@pytest.fixture
def media(media_dir: Path) -> MediaMemory:
    return MediaMemory(base_dir=media_dir)


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    f = tmp_path / "test_image.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    return f


@pytest.mark.asyncio
async def test_init_creates_dirs(media: MediaMemory, media_dir: Path):
    await media.init()
    assert media_dir.exists()
    assert (media_dir / "files").exists()


@pytest.mark.asyncio
async def test_ingest_file(media: MediaMemory, sample_file: Path):
    await media.init()
    result = await media.ingest(
        sample_file,
        description="Test image for unit testing",
        semantic_tags=["test", "image"],
        telos_relevance=["T1_Satya"],
    )
    assert result.status == "success"
    assert result.artifact_id != ""

    # Verify stored
    artifact = await media.get(result.artifact_id)
    assert artifact is not None
    assert artifact.filename == "test_image.png"
    assert artifact.media_type == "image"
    assert "test" in artifact.semantic_tags


@pytest.mark.asyncio
async def test_ingest_duplicate(media: MediaMemory, sample_file: Path):
    await media.init()
    r1 = await media.ingest(sample_file)
    assert r1.status == "success"

    r2 = await media.ingest(sample_file)
    assert r2.status == "duplicate"
    assert r2.artifact_id == r1.artifact_id


@pytest.mark.asyncio
async def test_ingest_missing_file(media: MediaMemory):
    await media.init()
    result = await media.ingest(Path("/nonexistent/file.png"))
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_tag_artifact(media: MediaMemory, sample_file: Path):
    await media.init()
    r = await media.ingest(sample_file, semantic_tags=["original"])
    ok = await media.tag(r.artifact_id, ["new_tag"])
    assert ok is True

    artifact = await media.get(r.artifact_id)
    assert "new_tag" in artifact.semantic_tags
    assert "original" in artifact.semantic_tags


@pytest.mark.asyncio
async def test_link_artifact(media: MediaMemory, sample_file: Path):
    await media.init()
    r = await media.ingest(sample_file)
    ok = await media.link(r.artifact_id, "target_obj_123")
    assert ok is True

    artifact = await media.get(r.artifact_id)
    assert "target_obj_123" in artifact.linked_objects


@pytest.mark.asyncio
async def test_search_by_text(media: MediaMemory, sample_file: Path):
    await media.init()
    await media.ingest(sample_file, description="Architecture diagram for gates")

    results = await media.search("architecture diagram")
    assert len(results) == 1
    assert results[0].relevance_score > 0


@pytest.mark.asyncio
async def test_search_by_type(media: MediaMemory, sample_file: Path, tmp_path: Path):
    await media.init()
    await media.ingest(sample_file)

    txt = tmp_path / "notes.txt"
    txt.write_text("Some notes")
    await media.ingest(txt)

    results = await media.search(media_type="image")
    assert len(results) == 1
    assert results[0].artifact.media_type == "image"


@pytest.mark.asyncio
async def test_search_by_tags(media: MediaMemory, sample_file: Path):
    await media.init()
    await media.ingest(sample_file, semantic_tags=["vsm", "beer"])

    results = await media.search(tags=["vsm"])
    assert len(results) == 1


@pytest.mark.asyncio
async def test_stats(media: MediaMemory, sample_file: Path):
    await media.init()
    await media.ingest(sample_file)

    stats = await media.get_stats()
    assert stats["total_artifacts"] == 1
    assert "image" in stats["by_type"]


@pytest.mark.asyncio
async def test_list_all(media: MediaMemory, sample_file: Path):
    await media.init()
    await media.ingest(sample_file)

    artifacts = await media.list_all()
    assert len(artifacts) == 1
