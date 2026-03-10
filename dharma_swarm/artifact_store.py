"""Canonical artifact store with manifests and runtime-state recording."""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from dharma_swarm.artifact_manifest import ArtifactManifestStore
from dharma_swarm.engine.artifacts import ArtifactRef, ArtifactStore as EngineArtifactStore
from dharma_swarm.runtime_state import ArtifactRecord, RuntimeStateStore

DEFAULT_ARTIFACT_ROOT = Path.home() / ".dharma" / "workspace" / "sessions"


@dataclass(frozen=True)
class StoredArtifact:
    record: ArtifactRecord
    ref: ArtifactRef
    manifest_path: Path


class RuntimeArtifactStore:
    """Wrap filesystem artifacts with machine-readable manifests and runtime rows."""

    def __init__(
        self,
        base_dir: Path | str | None = None,
        *,
        runtime_state: RuntimeStateStore | None = None,
    ) -> None:
        self.base_dir = Path(base_dir or DEFAULT_ARTIFACT_ROOT)
        self.runtime_state = runtime_state
        self._engine = EngineArtifactStore(self.base_dir)
        self._manifests = ArtifactManifestStore()

    def create_text_artifact(
        self,
        *,
        session_id: str,
        artifact_type: str,
        artifact_kind: str,
        content: str,
        created_by: str,
        extension: str = "md",
        task_id: str = "",
        run_id: str = "",
        trace_id: str = "",
        parent_artifact_id: str = "",
        promotion_state: str = "ephemeral",
        source_event_ids: list[str] | None = None,
        provenance: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        citations: list[str] | None = None,
        depends_on: list[str] | None = None,
        confidence: float = 0.0,
    ) -> StoredArtifact:
        ref = self._engine.create_artifact(
            session_id=session_id,
            artifact_type=artifact_type,
            content=content,
            created_by=created_by,
            extension=extension,
            confidence=confidence,
            citations=citations,
            depends_on=depends_on,
            metadata=metadata,
        )
        return self._record_ref(
            ref,
            artifact_kind=artifact_kind,
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            parent_artifact_id=parent_artifact_id,
            promotion_state=promotion_state,
            source_event_ids=source_event_ids,
            provenance=provenance,
            metadata=metadata,
        )

    async def create_text_artifact_async(
        self,
        *,
        session_id: str,
        artifact_type: str,
        artifact_kind: str,
        content: str,
        created_by: str,
        extension: str = "md",
        task_id: str = "",
        run_id: str = "",
        trace_id: str = "",
        parent_artifact_id: str = "",
        promotion_state: str = "ephemeral",
        source_event_ids: list[str] | None = None,
        provenance: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        citations: list[str] | None = None,
        depends_on: list[str] | None = None,
        confidence: float = 0.0,
    ) -> StoredArtifact:
        stored = self.create_text_artifact(
            session_id=session_id,
            artifact_type=artifact_type,
            artifact_kind=artifact_kind,
            content=content,
            created_by=created_by,
            extension=extension,
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            parent_artifact_id=parent_artifact_id,
            promotion_state=promotion_state,
            source_event_ids=source_event_ids,
            provenance=provenance,
            metadata=metadata,
            citations=citations,
            depends_on=depends_on,
            confidence=confidence,
        )
        return await self._persist_stored_artifact(stored)

    def record_existing_artifact(
        self,
        path: Path | str,
        *,
        session_id: str,
        artifact_type: str,
        artifact_kind: str,
        created_by: str,
        task_id: str = "",
        run_id: str = "",
        trace_id: str = "",
        parent_artifact_id: str = "",
        promotion_state: str = "ephemeral",
        source_event_ids: list[str] | None = None,
        provenance: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        citations: list[str] | None = None,
        depends_on: list[str] | None = None,
        confidence: float = 0.0,
    ) -> StoredArtifact:
        payload_path = Path(path)
        if not payload_path.exists():
            raise FileNotFoundError(payload_path)
        ref = ArtifactRef(
            artifact_id=uuid4().hex[:16],
            artifact_type=artifact_type,
            path=str(payload_path),
            created_by=created_by,
            session_id=session_id,
            version=1,
            confidence=confidence,
            citations=list(citations or []),
            depends_on=list(depends_on or []),
            metadata=dict(metadata or {}),
        )
        return self._record_ref(
            ref,
            artifact_kind=artifact_kind,
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            parent_artifact_id=parent_artifact_id,
            promotion_state=promotion_state,
            source_event_ids=source_event_ids,
            provenance=provenance,
            metadata=metadata,
        )

    async def record_existing_artifact_async(
        self,
        path: Path | str,
        *,
        session_id: str,
        artifact_type: str,
        artifact_kind: str,
        created_by: str,
        task_id: str = "",
        run_id: str = "",
        trace_id: str = "",
        parent_artifact_id: str = "",
        promotion_state: str = "ephemeral",
        source_event_ids: list[str] | None = None,
        provenance: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        citations: list[str] | None = None,
        depends_on: list[str] | None = None,
        confidence: float = 0.0,
    ) -> StoredArtifact:
        stored = self.record_existing_artifact(
            path,
            session_id=session_id,
            artifact_type=artifact_type,
            artifact_kind=artifact_kind,
            created_by=created_by,
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            parent_artifact_id=parent_artifact_id,
            promotion_state=promotion_state,
            source_event_ids=source_event_ids,
            provenance=provenance,
            metadata=metadata,
            citations=citations,
            depends_on=depends_on,
            confidence=confidence,
        )
        return await self._persist_stored_artifact(stored)

    def import_file_artifact(
        self,
        source_path: Path | str,
        *,
        session_id: str,
        artifact_type: str,
        artifact_kind: str,
        created_by: str,
        task_id: str = "",
        run_id: str = "",
        trace_id: str = "",
        extension: str | None = None,
        metadata: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        promotion_state: str = "ephemeral",
    ) -> StoredArtifact:
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(source)
        self._engine.ensure_session_dirs(session_id)
        artifact_id = uuid4().hex[:16]
        ext = extension or source.suffix.lstrip(".") or "bin"
        dest = self._engine._artifact_path(
            session_id=session_id,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            version=1,
            extension=ext,
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        ref = ArtifactRef(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            path=str(dest),
            created_by=created_by,
            session_id=session_id,
            version=1,
            metadata=dict(metadata or {}),
        )
        return self._record_ref(
            ref,
            artifact_kind=artifact_kind,
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            promotion_state=promotion_state,
            provenance=provenance,
            metadata=metadata,
        )

    async def import_file_artifact_async(
        self,
        source_path: Path | str,
        *,
        session_id: str,
        artifact_type: str,
        artifact_kind: str,
        created_by: str,
        task_id: str = "",
        run_id: str = "",
        trace_id: str = "",
        extension: str | None = None,
        metadata: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        promotion_state: str = "ephemeral",
    ) -> StoredArtifact:
        stored = self.import_file_artifact(
            source_path,
            session_id=session_id,
            artifact_type=artifact_type,
            artifact_kind=artifact_kind,
            created_by=created_by,
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            extension=extension,
            metadata=metadata,
            provenance=provenance,
            promotion_state=promotion_state,
        )
        return await self._persist_stored_artifact(stored)

    def _record_ref(
        self,
        ref: ArtifactRef,
        *,
        artifact_kind: str,
        task_id: str,
        run_id: str,
        trace_id: str,
        parent_artifact_id: str = "",
        promotion_state: str = "ephemeral",
        source_event_ids: list[str] | None = None,
        provenance: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StoredArtifact:
        manifest, manifest_path = self._manifests.record_manifest(
            ref,
            artifact_kind=artifact_kind,
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            parent_artifact_id=parent_artifact_id,
            promotion_state=promotion_state,
            source_event_ids=source_event_ids,
            provenance=provenance,
            metadata=metadata,
        )
        record = self._manifests.to_artifact_record(
            manifest,
            manifest_path=manifest_path,
        )
        if self.runtime_state is not None:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                async def _persist() -> ArtifactRecord:
                    await self.runtime_state.init_db()
                    return await self.runtime_state.record_artifact(record)

                record = asyncio.run(_persist())
        return StoredArtifact(record=record, ref=ref, manifest_path=manifest_path)

    async def record_artifact_async(
        self,
        stored: StoredArtifact,
    ) -> ArtifactRecord:
        if self.runtime_state is None:
            return stored.record
        await self.runtime_state.init_db()
        return await self.runtime_state.record_artifact(stored.record)

    async def _persist_stored_artifact(self, stored: StoredArtifact) -> StoredArtifact:
        record = await self.record_artifact_async(stored)
        return StoredArtifact(
            record=record,
            ref=stored.ref,
            manifest_path=stored.manifest_path,
        )
