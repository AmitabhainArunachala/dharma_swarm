"""Artifact references and versioned filesystem storage."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4


ALLOWED_ARTIFACT_TYPES = frozenset({"research", "code", "documents", "evaluations"})


@dataclass(slots=True)
class ArtifactRef:
    """Reference to a persisted artifact on disk."""

    artifact_id: str
    artifact_type: str
    path: str
    created_by: str
    session_id: str
    version: int = 1
    confidence: float = 0.0
    citations: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "path": self.path,
            "created_by": self.created_by,
            "session_id": self.session_id,
            "version": self.version,
            "confidence": self.confidence,
            "citations": list(self.citations),
            "depends_on": list(self.depends_on),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactRef":
        return cls(
            artifact_id=str(data["artifact_id"]),
            artifact_type=str(data["artifact_type"]),
            path=str(data["path"]),
            created_by=str(data["created_by"]),
            session_id=str(data["session_id"]),
            version=int(data.get("version", 1)),
            confidence=float(data.get("confidence", 0.0)),
            citations=list(data.get("citations", [])),
            depends_on=list(data.get("depends_on", [])),
            metadata=dict(data.get("metadata", {})),
        )


class ArtifactStore:
    """Writes versioned artifacts and returns stable references."""

    def __init__(self, base_dir: Path | str = Path("workspace") / "sessions") -> None:
        self.base_dir = Path(base_dir)

    def session_root(self, session_id: str) -> Path:
        return self.base_dir / session_id

    def ensure_session_dirs(self, session_id: str) -> None:
        root = self.session_root(session_id)
        (root / "artifacts" / "research").mkdir(parents=True, exist_ok=True)
        (root / "artifacts" / "code").mkdir(parents=True, exist_ok=True)
        (root / "artifacts" / "documents").mkdir(parents=True, exist_ok=True)
        (root / "artifacts" / "evaluations").mkdir(parents=True, exist_ok=True)
        (root / "knowledge").mkdir(parents=True, exist_ok=True)
        (root / "provenance").mkdir(parents=True, exist_ok=True)

    def _artifact_path(
        self,
        *,
        session_id: str,
        artifact_type: str,
        artifact_id: str,
        version: int,
        extension: str,
    ) -> Path:
        root = self.session_root(session_id)
        ext = extension.strip(".")
        return root / "artifacts" / artifact_type / f"{artifact_id}_v{version}.{ext}"

    def create_artifact(
        self,
        *,
        session_id: str,
        artifact_type: str,
        content: str,
        created_by: str,
        extension: str = "md",
        confidence: float = 0.0,
        citations: list[str] | None = None,
        depends_on: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRef:
        if artifact_type not in ALLOWED_ARTIFACT_TYPES:
            raise ValueError(
                f"Unknown artifact_type '{artifact_type}'. "
                f"Expected one of {sorted(ALLOWED_ARTIFACT_TYPES)}."
            )

        self.ensure_session_dirs(session_id)

        artifact_id = uuid4().hex[:16]
        version = 1
        path = self._artifact_path(
            session_id=session_id,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            version=version,
            extension=extension,
        )
        path.write_text(content)

        return ArtifactRef(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            path=str(path),
            created_by=created_by,
            session_id=session_id,
            version=version,
            confidence=confidence,
            citations=list(citations or []),
            depends_on=list(depends_on or []),
            metadata=dict(metadata or {}),
        )

    def read_artifact(self, ref: ArtifactRef) -> str:
        return Path(ref.path).read_text()

    def update_artifact(
        self,
        ref: ArtifactRef,
        *,
        new_content: str,
        confidence: float | None = None,
        citations: list[str] | None = None,
        depends_on: list[str] | None = None,
    ) -> ArtifactRef:
        old_path = Path(ref.path)
        extension = old_path.suffix.lstrip(".") or "md"
        new_version = ref.version + 1
        new_path = self._artifact_path(
            session_id=ref.session_id,
            artifact_type=ref.artifact_type,
            artifact_id=ref.artifact_id,
            version=new_version,
            extension=extension,
        )
        new_path.parent.mkdir(parents=True, exist_ok=True)
        new_path.write_text(new_content)

        return ArtifactRef(
            artifact_id=ref.artifact_id,
            artifact_type=ref.artifact_type,
            path=str(new_path),
            created_by=ref.created_by,
            session_id=ref.session_id,
            version=new_version,
            confidence=ref.confidence if confidence is None else confidence,
            citations=ref.citations if citations is None else list(citations),
            depends_on=ref.depends_on if depends_on is None else list(depends_on),
            metadata=dict(ref.metadata),
        )

