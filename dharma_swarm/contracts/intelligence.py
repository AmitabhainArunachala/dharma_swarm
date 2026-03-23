"""Sovereign intelligence-side contracts."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .common import EvaluationRecord, MemoryRecord, MemoryTruthState, SkillArtifact, SkillPromotionState


@runtime_checkable
class MemoryPlane(Protocol):
    """Canonical interface for memory writes, promotion, and retrieval."""

    async def write_memory(self, record: MemoryRecord) -> MemoryRecord:
        """Persist a memory candidate or update."""

    async def get_memory(self, record_id: str) -> MemoryRecord | None:
        """Load one memory record."""

    async def query_memory(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        truth_state: MemoryTruthState | None = None,
        limit: int = 50,
    ) -> list[MemoryRecord]:
        """Query memory records."""

    async def set_truth_state(
        self,
        *,
        record_id: str,
        truth_state: MemoryTruthState,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        """Promote, decay, reject, or archive memory."""


@runtime_checkable
class LearningEngine(Protocol):
    """Canonical interface for trace-to-skill and model updates."""

    async def extract_skill_candidates(
        self,
        *,
        session_id: str = "",
        run_id: str = "",
        task_id: str = "",
    ) -> list[SkillArtifact]:
        """Extract reusable skills from prior work."""

    async def update_user_model(
        self,
        *,
        user_id: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        """Update the DHARMA-owned user model."""

    async def update_agent_model(
        self,
        *,
        agent_id: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        """Update the DHARMA-owned agent model."""

    async def propose_routing_hints(
        self,
        *,
        task_id: str,
        session_id: str = "",
    ) -> list[dict[str, Any]]:
        """Generate routing hints grounded in observed outcomes."""


@runtime_checkable
class SkillStore(Protocol):
    """Canonical interface for learned and curated skills."""

    async def save_skill(self, skill: SkillArtifact) -> SkillArtifact:
        """Persist a skill artifact."""

    async def get_skill(self, skill_id: str) -> SkillArtifact | None:
        """Load one skill."""

    async def list_skills(
        self,
        *,
        promotion_state: SkillPromotionState | None = None,
        limit: int = 100,
    ) -> list[SkillArtifact]:
        """List known skills."""

    async def promote_skill(
        self,
        *,
        skill_id: str,
        promotion_state: SkillPromotionState,
        metadata: dict[str, Any] | None = None,
    ) -> SkillArtifact:
        """Promote, share, or retire a skill."""


@runtime_checkable
class EvaluationSink(Protocol):
    """Canonical landing zone for scoring and experiment outcomes."""

    async def record_evaluation(self, record: EvaluationRecord) -> EvaluationRecord:
        """Persist one evaluation event."""

    async def list_evaluations(
        self,
        *,
        subject_kind: str | None = None,
        subject_id: str | None = None,
        metric: str | None = None,
        limit: int = 100,
    ) -> list[EvaluationRecord]:
        """Query evaluation records."""

    async def summarize_subject(
        self,
        *,
        subject_kind: str,
        subject_id: str,
    ) -> dict[str, Any]:
        """Return a compact summary for a subject."""
