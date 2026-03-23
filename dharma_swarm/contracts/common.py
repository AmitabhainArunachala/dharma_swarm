"""Shared sovereign contract models.

These are intentionally lightweight and decoupled from the current runtime
implementation so that adapter layers can map existing stores into stable
DHARMA-owned shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RunStatus(str, Enum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"
    PAUSED = "paused"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STALE_RECOVERED = "stale_recovered"


class CheckpointStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    APPROVED = "approved"
    REJECTED = "rejected"
    RESUMED = "resumed"
    SUPERSEDED = "superseded"


class MemoryTruthState(str, Enum):
    CANDIDATE = "candidate"
    PROMOTED = "promoted"
    STALE = "stale"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class SkillPromotionState(str, Enum):
    DRAFT = "draft"
    CANDIDATE = "candidate"
    SHARED = "shared"
    PROMOTED = "promoted"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class RunDescriptor:
    run_id: str
    session_id: str = ""
    task_id: str = ""
    agent_id: str = ""
    parent_run_id: str = ""
    status: RunStatus = RunStatus.QUEUED
    current_artifact_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GatewayMessage:
    message_id: str
    channel: str
    sender: str
    recipient: str
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    record_id: str
    kind: str
    text: str
    truth_state: MemoryTruthState = MemoryTruthState.CANDIDATE
    session_id: str = ""
    task_id: str = ""
    agent_id: str = ""
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SkillArtifact:
    skill_id: str
    name: str
    version: str = "v1"
    description: str = ""
    promotion_state: SkillPromotionState = SkillPromotionState.DRAFT
    source_run_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvaluationRecord:
    evaluation_id: str
    subject_kind: str
    subject_id: str
    evaluator: str
    metric: str
    score: float
    session_id: str = ""
    task_id: str = ""
    run_id: str = ""
    evidence_refs: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CheckpointRecord:
    checkpoint_id: str
    session_id: str = ""
    task_id: str = ""
    run_id: str = ""
    status: CheckpointStatus = CheckpointStatus.DRAFT
    summary: str = ""
    artifact_refs: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    command: str
    workdir: str = ""
    timeout_seconds: float = 30.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
