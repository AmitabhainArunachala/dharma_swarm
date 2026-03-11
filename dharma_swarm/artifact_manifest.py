"""Machine-readable artifact manifests for canonical DGC artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from .engine.artifacts import ArtifactRef
from .runtime_state import ArtifactRecord


ARTIFACT_MANIFEST_VERSION = "1.0.0"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _guess_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "text/markdown"
    if suffix == ".py":
        return "text/x-python"
    if suffix == ".json":
        return "application/json"
    if suffix in {".txt", ".log", ".yaml", ".yml", ".toml"}:
        return "text/plain"
    return "application/octet-stream"


@dataclass(frozen=True, slots=True)
class ArtifactManifest:
    artifact_id: str
    artifact_kind: str
    session_id: str
    created_by: str
    payload_path: str
    payload_checksum: str
    manifest_version: str = ARTIFACT_MANIFEST_VERSION
    task_id: str = ""
    run_id: str = ""
    trace_id: str = ""
    version: int = 1
    content_type: str = "application/octet-stream"
    parent_artifact_id: str = ""
    promotion_state: str = "ephemeral"
    source_event_ids: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_version": self.manifest_version,
            "artifact_id": self.artifact_id,
            "artifact_kind": self.artifact_kind,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "created_by": self.created_by,
            "payload_path": self.payload_path,
            "payload_checksum": self.payload_checksum,
            "version": self.version,
            "content_type": self.content_type,
            "parent_artifact_id": self.parent_artifact_id,
            "promotion_state": self.promotion_state,
            "source_event_ids": list(self.source_event_ids),
            "citations": list(self.citations),
            "depends_on": list(self.depends_on),
            "provenance": dict(self.provenance),
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactManifest":
        return cls(
            manifest_version=str(data.get("manifest_version", ARTIFACT_MANIFEST_VERSION)),
            artifact_id=str(data.get("artifact_id", "")),
            artifact_kind=str(data.get("artifact_kind", "")),
            session_id=str(data.get("session_id", "")),
            task_id=str(data.get("task_id", "")),
            run_id=str(data.get("run_id", "")),
            trace_id=str(data.get("trace_id", "")),
            created_by=str(data.get("created_by", "")),
            payload_path=str(data.get("payload_path", "")),
            payload_checksum=str(data.get("payload_checksum", "")),
            version=int(data.get("version", 1)),
            content_type=str(data.get("content_type", "application/octet-stream")),
            parent_artifact_id=str(data.get("parent_artifact_id", "")),
            promotion_state=str(data.get("promotion_state", "ephemeral")),
            source_event_ids=list(data.get("source_event_ids", [])),
            citations=list(data.get("citations", [])),
            depends_on=list(data.get("depends_on", [])),
            provenance=dict(data.get("provenance", {})),
            metadata=dict(data.get("metadata", {})),
            created_at=str(data.get("created_at", _utc_now_iso())),
        )


class ArtifactManifestStore:
    """Build and persist sidecar manifests for existing artifact payloads."""

    def default_manifest_path(self, payload_path: Path | str) -> Path:
        path = Path(payload_path)
        return path.with_name(f"{path.name}.manifest.json")

    def build_manifest(
        self,
        ref: ArtifactRef,
        *,
        artifact_kind: str | None = None,
        task_id: str = "",
        run_id: str = "",
        trace_id: str = "",
        parent_artifact_id: str = "",
        promotion_state: str = "ephemeral",
        source_event_ids: list[str] | None = None,
        provenance: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> ArtifactManifest:
        payload_path = Path(ref.path)
        if not payload_path.exists():
            raise FileNotFoundError(payload_path)

        merged_metadata = dict(ref.metadata)
        if metadata:
            merged_metadata.update(metadata)

        return ArtifactManifest(
            artifact_id=ref.artifact_id,
            artifact_kind=artifact_kind or ref.artifact_type,
            session_id=ref.session_id,
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            created_by=ref.created_by,
            payload_path=str(payload_path),
            payload_checksum=_sha256_path(payload_path),
            version=ref.version,
            content_type=_guess_content_type(payload_path),
            parent_artifact_id=parent_artifact_id,
            promotion_state=promotion_state,
            source_event_ids=list(source_event_ids or []),
            citations=list(ref.citations),
            depends_on=list(ref.depends_on),
            provenance=dict(provenance or {}),
            metadata=merged_metadata,
            created_at=created_at or _utc_now_iso(),
        )

    def write_manifest(
        self,
        manifest: ArtifactManifest,
        *,
        manifest_path: Path | str | None = None,
    ) -> Path:
        path = Path(manifest_path) if manifest_path is not None else self.default_manifest_path(manifest.payload_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=True, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def read_manifest(self, manifest_path: Path | str) -> ArtifactManifest:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        return ArtifactManifest.from_dict(data)

    def record_manifest(
        self,
        ref: ArtifactRef,
        **kwargs: Any,
    ) -> tuple[ArtifactManifest, Path]:
        manifest = self.build_manifest(ref, **kwargs)
        path = self.write_manifest(manifest)
        return manifest, path

    def to_artifact_record(
        self,
        manifest: ArtifactManifest,
        *,
        manifest_path: Path | str,
    ) -> ArtifactRecord:
        return ArtifactRecord(
            artifact_id=manifest.artifact_id,
            artifact_kind=manifest.artifact_kind,
            session_id=manifest.session_id,
            task_id=manifest.task_id,
            run_id=manifest.run_id,
            manifest_path=str(manifest_path),
            payload_path=manifest.payload_path,
            checksum=manifest.payload_checksum,
            parent_artifact_id=manifest.parent_artifact_id,
            promotion_state=manifest.promotion_state,
            created_at=datetime.fromisoformat(manifest.created_at),
            metadata={
                "created_by": manifest.created_by,
                "content_type": manifest.content_type,
                "trace_id": manifest.trace_id,
                "source_event_ids": list(manifest.source_event_ids),
                "citations": list(manifest.citations),
                "depends_on": list(manifest.depends_on),
                "provenance": dict(manifest.provenance),
                **dict(manifest.metadata),
            },
        )
