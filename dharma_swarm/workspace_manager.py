"""Canonical workspace isolation, leases, and promotion management."""

from __future__ import annotations

import asyncio
import hashlib
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from dharma_swarm.artifact_store import RuntimeArtifactStore
from dharma_swarm.file_lock import AsyncFileLock
from dharma_swarm.runtime_state import ArtifactRecord, RuntimeStateStore, WorkspaceLease

DEFAULT_WORKSPACE_ROOT = Path.home() / ".dharma" / "workspace"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_path(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class WorkspacePromotion:
    destination_path: Path
    lease: WorkspaceLease
    artifact: ArtifactRecord | None


class WorkspaceManager:
    """Manage isolated run workspaces and shared publication zones."""

    def __init__(
        self,
        base_dir: Path | str | None = None,
        *,
        runtime_state: RuntimeStateStore | None = None,
        artifact_store: RuntimeArtifactStore | None = None,
        lock_dir: Path | None = None,
    ) -> None:
        self.base_dir = Path(base_dir or DEFAULT_WORKSPACE_ROOT)
        self.runtime_state = runtime_state
        self.artifact_store = artifact_store
        self.lock_dir = lock_dir
        self._locks: dict[str, AsyncFileLock] = {}

    async def init_layout(self) -> None:
        for path in (
            self.base_dir / "agents",
            self.base_dir / "shared" / "published",
            self.base_dir / "shared" / "inbox",
            self.base_dir / "shared" / "scratch",
        ):
            path.mkdir(parents=True, exist_ok=True)
        if self.runtime_state is not None:
            await self.runtime_state.init_db()

    async def ensure_agent_workspace(self, run_id: str) -> Path:
        await self.init_layout()
        path = self.base_dir / "agents" / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def shared_zone(self, zone: str) -> Path:
        return self.base_dir / "shared" / zone

    async def acquire_shared_lease(
        self,
        *,
        holder_run_id: str,
        relative_path: str,
        zone: str = "published",
        mode: str = "write",
        ttl_seconds: int = 300,
        timeout_seconds: int = 30,
        metadata: dict[str, Any] | None = None,
    ) -> WorkspaceLease:
        await self.init_layout()
        target = self.shared_zone(zone) / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)

        lock = AsyncFileLock(
            target,
            agent_id=holder_run_id,
            ttl_seconds=ttl_seconds,
            timeout_seconds=timeout_seconds,
            lock_dir=self.lock_dir,
        )
        await lock.acquire()

        lease_id = (
            self.runtime_state.new_lease_id()
            if self.runtime_state is not None
            else f"lease_{uuid4().hex[:16]}"
        )
        lease = WorkspaceLease(
            lease_id=lease_id,
            zone_path=str(target),
            holder_run_id=holder_run_id,
            mode=mode,
            base_hash=_sha256_path(target),
            acquired_at=_utc_now(),
            expires_at=_utc_now() + timedelta(seconds=ttl_seconds),
            metadata=dict(metadata or {}),
        )
        self._locks[lease_id] = lock
        if self.runtime_state is not None:
            await self.runtime_state.record_workspace_lease(lease)
        return lease

    async def release_lease(self, lease_id: str) -> WorkspaceLease | None:
        lock = self._locks.pop(lease_id, None)
        if lock is not None:
            await lock.release()
        if self.runtime_state is None:
            return None
        return await self.runtime_state.release_workspace_lease(lease_id)

    async def promote_file(
        self,
        source_path: Path | str,
        *,
        holder_run_id: str,
        relative_dest: str,
        zone: str = "published",
        session_id: str = "",
        task_id: str = "",
        artifact_type: str = "documents",
        artifact_kind: str = "published_file",
        created_by: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> WorkspacePromotion:
        await self.init_layout()
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(source)
        dest = self.shared_zone(zone) / relative_dest
        dest.parent.mkdir(parents=True, exist_ok=True)

        lease = await self.acquire_shared_lease(
            holder_run_id=holder_run_id,
            relative_path=relative_dest,
            zone=zone,
            mode="publish",
            metadata={"source_path": str(source)},
        )
        try:
            await asyncio.to_thread(shutil.copy2, source, dest)
            artifact: ArtifactRecord | None = None
            if self.artifact_store is not None and session_id:
                stored = await self.artifact_store.record_existing_artifact_async(
                    dest,
                    session_id=session_id,
                    artifact_type=artifact_type,
                    artifact_kind=artifact_kind,
                    created_by=created_by or holder_run_id,
                    task_id=task_id,
                    run_id=holder_run_id,
                    promotion_state="published",
                    metadata={
                        "source_path": str(source),
                        **dict(metadata or {}),
                    },
                )
                artifact = stored.record
            elif self.runtime_state is not None:
                artifact = await self.runtime_state.record_artifact(
                    ArtifactRecord(
                        artifact_id=self.runtime_state.new_artifact_id(),
                        artifact_kind=artifact_kind,
                        session_id=session_id,
                        task_id=task_id,
                        run_id=holder_run_id,
                        payload_path=str(dest),
                        checksum=_sha256_path(dest),
                        promotion_state="published",
                        metadata={"source_path": str(source), **dict(metadata or {})},
                    )
                )
            return WorkspacePromotion(
                destination_path=dest,
                lease=lease,
                artifact=artifact,
            )
        finally:
            await self.release_lease(lease.lease_id)
