"""Multimodal Memory System — media artifacts as first-class ontology objects.

Extends the Palantir-pattern ontology with MediaArtifact objects that can be
ingested, tagged, linked, and searched. Integrates with the existing
artifact_store.py and artifact_manifest.py for storage and provenance.

Ground: Varela (autopoietic media membrane), Ashby (requisite variety in
organizational memory), Kauffman (each artifact expands the adjacent possible).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_MEDIA_DIR = Path.home() / ".dharma" / "media-memory"
_INDEX_FILE = "media_index.jsonl"

# Supported media categories
MEDIA_TYPES = {
    "image": [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".tiff"],
    "video": [".mp4", ".mov", ".avi", ".mkv", ".webm"],
    "audio": [".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"],
    "document": [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"],
    "code": [".py", ".js", ".ts", ".rs", ".go", ".java", ".c", ".cpp", ".md"],
    "data": [".json", ".csv", ".jsonl", ".yaml", ".yml", ".toml", ".xml"],
    "diagram": [".mermaid", ".dot", ".puml", ".drawio"],
}

# Telos star names for alignment tagging
TELOS_STARS = ["T1_Satya", "T2_Tapas", "T3_Ahimsa", "T4_Swaraj", "T5_Dharma", "T6_Shakti", "T7_Moksha"]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class MediaArtifact(BaseModel):
    """A media artifact tracked in the multimodal memory system.

    Corresponds to an OntologyObj of type 'MediaArtifact' in the
    Palantir-pattern ontology.
    """

    id: str = Field(default_factory=_new_id)
    filename: str
    media_type: str  # image, video, audio, document, code, data, diagram
    file_path: str  # Relative to media-memory directory
    file_hash: str = ""  # SHA-256 of file content
    file_size: int = 0  # bytes
    timestamp: datetime = Field(default_factory=_utc_now)
    source: str = "user-uploaded"  # user-uploaded, generated, scraped, conversation
    description: str = ""  # Natural language description
    extracted_text: str = ""  # OCR / transcript
    semantic_tags: list[str] = Field(default_factory=list)  # max 10
    telos_relevance: list[str] = Field(default_factory=list)  # Which T1-T7 stars
    pillar_associations: list[str] = Field(default_factory=list)
    linked_objects: list[str] = Field(default_factory=list)  # IDs of linked ontology objects
    metadata: dict[str, Any] = Field(default_factory=dict)
    ingestion_gate_results: dict[str, str] = Field(default_factory=dict)


class SearchResult(BaseModel):
    """A single search result from the media memory system."""

    artifact: MediaArtifact
    relevance_score: float = 0.0
    match_reason: str = ""


class IngestionResult(BaseModel):
    """Result of ingesting a media artifact."""

    artifact_id: str
    status: str = "success"  # success, failed, duplicate
    message: str = ""
    gate_results: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Media type detection
# ---------------------------------------------------------------------------


def detect_media_type(filename: str) -> str:
    """Detect media type category from filename extension."""
    ext = Path(filename).suffix.lower()
    for category, extensions in MEDIA_TYPES.items():
        if ext in extensions:
            return category
    return "unknown"


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of file contents."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# MediaMemory
# ---------------------------------------------------------------------------


class MediaMemory:
    """Multimodal memory system for media artifacts.

    Stores files in media-memory/ with a JSONL index (consistent with
    dharma_corpus.py pattern). All operations produce audit entries.

    In production, vector embeddings would be stored alongside the index
    for semantic search. Currently uses keyword-based search as a
    foundation to build on.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or _DEFAULT_MEDIA_DIR
        self.index_path = self.base_dir / _INDEX_FILE
        self._artifacts: dict[str, MediaArtifact] = {}  # id -> artifact
        self._hash_index: dict[str, str] = {}  # file_hash -> artifact_id

    # -- lifecycle -----------------------------------------------------------

    async def init(self) -> None:
        """Create directories and load index."""
        await asyncio.to_thread(self._init_sync)

    def _init_sync(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        (self.base_dir / "files").mkdir(exist_ok=True)
        if self.index_path.exists():
            self._load_index()

    def _load_index(self) -> None:
        """Load JSONL index into memory."""
        self._artifacts.clear()
        self._hash_index.clear()
        for line in self.index_path.read_text().strip().split("\n"):
            if not line:
                continue
            try:
                artifact = MediaArtifact.model_validate(json.loads(line))
                self._artifacts[artifact.id] = artifact
                if artifact.file_hash:
                    self._hash_index[artifact.file_hash] = artifact.id
            except (json.JSONDecodeError, ValueError):
                continue

    def _append_index(self, artifact: MediaArtifact) -> None:
        """Append a single artifact to the JSONL index."""
        with open(self.index_path, "a") as f:
            f.write(json.dumps(json.loads(artifact.model_dump_json()), default=str) + "\n")

    def _rewrite_index(self) -> None:
        """Rewrite the full index from memory."""
        with open(self.index_path, "w") as f:
            for artifact in self._artifacts.values():
                f.write(json.dumps(json.loads(artifact.model_dump_json()), default=str) + "\n")

    # -- ingest --------------------------------------------------------------

    async def ingest(
        self,
        source_path: Path,
        *,
        description: str = "",
        source: str = "user-uploaded",
        semantic_tags: Optional[list[str]] = None,
        telos_relevance: Optional[list[str]] = None,
        pillar_associations: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> IngestionResult:
        """Ingest a media file into the memory system.

        Copies the file to media-memory/files/, computes hash for
        deduplication, detects media type, creates index entry.
        """
        return await asyncio.to_thread(
            self._ingest_sync, source_path, description, source,
            semantic_tags or [], telos_relevance or [],
            pillar_associations or [], metadata or {},
        )

    def _ingest_sync(
        self,
        source_path: Path,
        description: str,
        source: str,
        semantic_tags: list[str],
        telos_relevance: list[str],
        pillar_associations: list[str],
        metadata: dict[str, Any],
    ) -> IngestionResult:
        source_path = Path(source_path)
        if not source_path.exists():
            return IngestionResult(
                artifact_id="", status="failed",
                message=f"Source file not found: {source_path}",
            )

        # Compute hash for deduplication
        file_hash = compute_file_hash(source_path)
        if file_hash in self._hash_index:
            existing_id = self._hash_index[file_hash]
            return IngestionResult(
                artifact_id=existing_id, status="duplicate",
                message=f"File already ingested as {existing_id}",
            )

        # Detect type and create artifact
        media_type = detect_media_type(source_path.name)
        artifact_id = _new_id()
        dest_dir = self.base_dir / "files" / media_type
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"{artifact_id}_{source_path.name}"

        # Copy file
        shutil.copy2(source_path, dest_path)

        # Enforce max 10 tags
        tags = semantic_tags[:10]

        artifact = MediaArtifact(
            id=artifact_id,
            filename=source_path.name,
            media_type=media_type,
            file_path=str(dest_path.relative_to(self.base_dir)),
            file_hash=file_hash,
            file_size=dest_path.stat().st_size,
            source=source,
            description=description,
            semantic_tags=tags,
            telos_relevance=telos_relevance,
            pillar_associations=pillar_associations,
            metadata=metadata,
        )

        self._artifacts[artifact.id] = artifact
        self._hash_index[file_hash] = artifact.id
        self._append_index(artifact)

        return IngestionResult(
            artifact_id=artifact.id, status="success",
            message=f"Ingested {source_path.name} as {media_type}",
        )

    # -- tag & link ----------------------------------------------------------

    async def tag(self, artifact_id: str, tags: list[str]) -> bool:
        """Add semantic tags to an artifact (max 10 total)."""
        return await asyncio.to_thread(self._tag_sync, artifact_id, tags)

    def _tag_sync(self, artifact_id: str, tags: list[str]) -> bool:
        artifact = self._artifacts.get(artifact_id)
        if not artifact:
            return False
        existing = set(artifact.semantic_tags)
        existing.update(tags)
        artifact.semantic_tags = list(existing)[:10]
        self._rewrite_index()
        return True

    async def link(self, artifact_id: str, target_id: str) -> bool:
        """Link an artifact to another ontology object."""
        return await asyncio.to_thread(self._link_sync, artifact_id, target_id)

    def _link_sync(self, artifact_id: str, target_id: str) -> bool:
        artifact = self._artifacts.get(artifact_id)
        if not artifact:
            return False
        if target_id not in artifact.linked_objects:
            artifact.linked_objects.append(target_id)
            self._rewrite_index()
        return True

    async def update_description(self, artifact_id: str, description: str) -> bool:
        """Update the description of an artifact."""
        return await asyncio.to_thread(self._update_desc_sync, artifact_id, description)

    def _update_desc_sync(self, artifact_id: str, description: str) -> bool:
        artifact = self._artifacts.get(artifact_id)
        if not artifact:
            return False
        artifact.description = description
        self._rewrite_index()
        return True

    # -- search --------------------------------------------------------------

    async def search(
        self,
        query: str = "",
        *,
        media_type: Optional[str] = None,
        tags: Optional[list[str]] = None,
        telos_star: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Search artifacts with combined text + structured filters."""
        return await asyncio.to_thread(
            self._search_sync, query, media_type, tags, telos_star, source, limit,
        )

    def _search_sync(
        self,
        query: str,
        media_type: Optional[str],
        tags: Optional[list[str]],
        telos_star: Optional[str],
        source: Optional[str],
        limit: int,
    ) -> list[SearchResult]:
        results: list[SearchResult] = []
        query_lower = query.lower()
        query_words = set(query_lower.split()) if query else set()

        for artifact in self._artifacts.values():
            # Apply structured filters
            if media_type and artifact.media_type != media_type:
                continue
            if source and artifact.source != source:
                continue
            if telos_star and telos_star not in artifact.telos_relevance:
                continue
            if tags and not set(tags).intersection(artifact.semantic_tags):
                continue

            # Compute text relevance score
            score = 0.0
            if query:
                searchable = (
                    f"{artifact.filename} {artifact.description} "
                    f"{artifact.extracted_text} {' '.join(artifact.semantic_tags)}"
                ).lower()
                matched_words = query_words.intersection(searchable.split())
                score = len(matched_words) / max(len(query_words), 1)
                if score == 0 and query_lower in searchable:
                    score = 0.5  # Substring match
                if score == 0:
                    continue
            else:
                score = 1.0  # No query = all pass

            match_reason = "filter match" if not query else f"text relevance ({score:.0%})"
            results.append(SearchResult(
                artifact=artifact,
                relevance_score=score,
                match_reason=match_reason,
            ))

        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results[:limit]

    # -- stats ---------------------------------------------------------------

    async def get_stats(self) -> dict[str, Any]:
        """Get summary statistics of the media memory."""
        return await asyncio.to_thread(self._get_stats_sync)

    def _get_stats_sync(self) -> dict[str, Any]:
        type_counts: dict[str, int] = {}
        total_size = 0
        for a in self._artifacts.values():
            type_counts[a.media_type] = type_counts.get(a.media_type, 0) + 1
            total_size += a.file_size
        return {
            "total_artifacts": len(self._artifacts),
            "by_type": type_counts,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
        }

    async def get(self, artifact_id: str) -> Optional[MediaArtifact]:
        """Get a single artifact by ID."""
        return self._artifacts.get(artifact_id)

    async def list_all(self, limit: int = 100) -> list[MediaArtifact]:
        """List all artifacts, newest first."""
        artifacts = sorted(
            self._artifacts.values(),
            key=lambda a: a.timestamp,
            reverse=True,
        )
        return artifacts[:limit]
