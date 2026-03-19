"""A2A-inspired structured handoff protocol for dharma_swarm agents.

When agents hand off work, they pass typed artifacts with structured metadata
rather than raw text. This makes agent collaboration reliable and traceable.

Artifacts are typed (ArtifactType enum) so receivers know what they are getting.
Priority system (BLOCKING/IMPORTANT/INFORMATIONAL) enables triage.
JSONL persistence provides durability across restarts.
Handoff chain tracking gives full lineage of collaborative work.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _append_locked_jsonl(path: Path, line: str, *, encoding: str = "utf-8") -> None:
    """Append a single JSONL row durably under an advisory lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding=encoding) as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class ArtifactType(str, Enum):
    """Types of artifacts that can be handed off between agents."""

    CODE_DIFF = "code_diff"
    ANALYSIS = "analysis"
    TEST_RESULTS = "test_results"
    CONTEXT = "context"
    PLAN = "plan"
    FILE_LIST = "file_list"
    ERROR_REPORT = "error_report"
    METRIC = "metric"
    TPP_FRAGMENT = "tpp_fragment"  # TPP-formatted prompt fragment for injection


class HandoffPriority(str, Enum):
    """Priority levels for handoffs, controlling processing order."""

    BLOCKING = "blocking"  # Receiver cannot proceed without this
    IMPORTANT = "important"  # Should process soon
    INFORMATIONAL = "informational"  # FYI, process when convenient


# Sorting key: lower number = higher priority.
_PRIORITY_ORDER: dict[HandoffPriority, int] = {
    HandoffPriority.BLOCKING: 0,
    HandoffPriority.IMPORTANT: 1,
    HandoffPriority.INFORMATIONAL: 2,
}


class Artifact(BaseModel):
    """A typed piece of work output that can be handed between agents."""

    artifact_type: ArtifactType
    content: str
    summary: str = ""  # One-line summary for quick scanning
    files_touched: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Handoff(BaseModel):
    """A structured handoff from one agent to another."""

    id: str = ""  # auto-generated if empty
    from_agent: str
    to_agent: str  # or "*" for broadcast
    task_context: str  # What task this is part of
    artifacts: list[Artifact] = Field(default_factory=list)
    priority: HandoffPriority = HandoffPriority.IMPORTANT
    requires_ack: bool = False
    status: str = "pending"  # pending, delivered, acknowledged, rejected
    reject_reason: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # TPP telos threading — intent propagates through handoff chains
    intent_thread: dict[str, Any] = Field(default_factory=dict)
    telos_alignment: float = 0.0  # How well this handoff serves the root telos

    def summary(self) -> str:
        """One-line summary of this handoff."""
        types = ", ".join(a.artifact_type.value for a in self.artifacts)
        ctx = self.task_context[:60]
        return f"{self.from_agent}->{self.to_agent}: [{types}] {ctx}"


class HandoffProtocol:
    """Manages structured handoffs between agents.

    Stores handoffs in memory with optional JSONL persistence.
    Supports broadcast (to_agent="*"), priority-based triage,
    acknowledgement/rejection, artifact filtering, and lineage chains.
    """

    def __init__(self, store_path: Path | None = None) -> None:
        """Initialize with optional JSONL persistence path.

        Args:
            store_path: Path for JSONL persistence file.
                        Defaults to ~/.dharma/handoffs.jsonl.
        """
        self._store_path = store_path or Path.home() / ".dharma" / "handoffs.jsonl"
        self._pending: dict[str, Handoff] = {}  # id -> handoff
        self._history: list[Handoff] = []

    @staticmethod
    def _generate_id() -> str:
        """Generate a short unique identifier."""
        return uuid.uuid4().hex[:12]

    async def create_handoff(
        self,
        from_agent: str,
        to_agent: str,
        task_context: str,
        artifacts: list[Artifact],
        priority: HandoffPriority = HandoffPriority.IMPORTANT,
        requires_ack: bool = False,
        intent_thread: dict[str, Any] | None = None,
        telos_alignment: float = 0.0,
    ) -> Handoff:
        """Create and store a new handoff.

        Args:
            from_agent: Name of the sending agent.
            to_agent: Name of the receiving agent, or "*" for broadcast.
            task_context: Description of the task this handoff belongs to.
            artifacts: List of typed artifacts being handed off.
            priority: Processing priority for the receiver.
            requires_ack: Whether the sender requires acknowledgement.
            intent_thread: TPP intent thread dict for telos continuity.
            telos_alignment: Score (0-1) of how well this handoff serves root telos.

        Returns:
            The created Handoff with a generated ID.
        """
        handoff = Handoff(
            id=self._generate_id(),
            from_agent=from_agent,
            to_agent=to_agent,
            task_context=task_context,
            artifacts=artifacts,
            priority=priority,
            requires_ack=requires_ack,
            status="pending",
            intent_thread=intent_thread or {},
            telos_alignment=telos_alignment,
        )
        self._pending[handoff.id] = handoff
        self._history.append(handoff)
        await self._persist(handoff)
        logger.debug("Created handoff %s: %s", handoff.id, handoff.summary())
        return handoff

    async def create_tpp_handoff(
        self,
        from_agent: str,
        from_role: str,
        to_agent: str,
        task_context: str,
        findings: str,
        confidence: float = 0.5,
        telos_alignment: float = 0.5,
        intent_thread: dict[str, Any] | None = None,
        priority: HandoffPriority = HandoffPriority.IMPORTANT,
    ) -> Handoff:
        """Create a TPP-formatted handoff — findings structured for prompt injection.

        The findings are formatted as a TPP fragment (ArtifactType.TPP_FRAGMENT)
        that the receiving agent can directly inject into its prompt context.
        This preserves causal depth through the handoff chain.
        """
        tpp_content = f"[{from_agent} ({from_role})]: {findings}"
        try:
            from dharma_swarm.tpp import IntentThread, format_handoff_as_tpp

            thread_obj = None
            if isinstance(intent_thread, dict) and intent_thread:
                thread_obj = IntentThread.from_dict(intent_thread)
            tpp_content = format_handoff_as_tpp(
                from_agent=from_agent,
                from_role=from_role,
                findings=findings,
                confidence=confidence,
                telos_alignment=telos_alignment,
                intent_thread=thread_obj,
            )
        except Exception:
            logger.warning(
                "TPP handoff formatting failed; falling back to plain fragment",
                exc_info=True,
            )

        artifact = Artifact(
            artifact_type=ArtifactType.TPP_FRAGMENT,
            content=tpp_content,
            summary=findings[:120],
            metadata={
                "confidence": confidence,
                "telos_alignment": telos_alignment,
                "from_role": from_role,
            },
        )
        return await self.create_handoff(
            from_agent=from_agent,
            to_agent=to_agent,
            task_context=task_context,
            artifacts=[artifact],
            priority=priority,
            intent_thread=intent_thread,
            telos_alignment=telos_alignment,
        )

    async def get_pending(self, agent_name: str) -> list[Handoff]:
        """Get all pending handoffs for an agent.

        Includes both direct handoffs (to_agent == agent_name)
        and broadcast handoffs (to_agent == "*"). Excludes handoffs
        the agent sent to itself via broadcast.

        Args:
            agent_name: The agent to retrieve pending handoffs for.

        Returns:
            List of pending Handoff objects, sorted by priority.
        """
        results: list[Handoff] = []
        for handoff in self._pending.values():
            if handoff.status != "pending":
                continue
            is_direct = handoff.to_agent == agent_name
            is_broadcast = (
                handoff.to_agent == "*" and handoff.from_agent != agent_name
            )
            if is_direct or is_broadcast:
                results.append(handoff)
        results.sort(key=lambda h: _PRIORITY_ORDER.get(h.priority, 99))
        return results

    async def acknowledge(self, handoff_id: str) -> None:
        """Mark a handoff as acknowledged.

        Args:
            handoff_id: The ID of the handoff to acknowledge.

        Raises:
            KeyError: If the handoff ID is not found in pending.
        """
        if handoff_id not in self._pending:
            raise KeyError(f"Handoff {handoff_id} not found")
        handoff = self._pending[handoff_id]
        handoff.status = "acknowledged"
        await self._persist(handoff)
        logger.debug("Acknowledged handoff %s", handoff_id)

    async def reject(self, handoff_id: str, reason: str = "") -> None:
        """Reject a handoff (agent cannot handle it).

        Args:
            handoff_id: The ID of the handoff to reject.
            reason: Optional explanation for the rejection.

        Raises:
            KeyError: If the handoff ID is not found in pending.
        """
        if handoff_id not in self._pending:
            raise KeyError(f"Handoff {handoff_id} not found")
        handoff = self._pending[handoff_id]
        handoff.status = "rejected"
        handoff.reject_reason = reason
        await self._persist(handoff)
        logger.debug("Rejected handoff %s: %s", handoff_id, reason)

    async def get_artifacts(
        self,
        handoff_id: str,
        artifact_type: ArtifactType | None = None,
    ) -> list[Artifact]:
        """Get artifacts from a handoff, optionally filtered by type.

        Args:
            handoff_id: The handoff to retrieve artifacts from.
            artifact_type: If provided, only return artifacts of this type.

        Returns:
            List of matching Artifact objects.

        Raises:
            KeyError: If the handoff ID is not found.
        """
        handoff = self._pending.get(handoff_id)
        if handoff is None:
            # Also search history for acknowledged/rejected handoffs.
            for h in self._history:
                if h.id == handoff_id:
                    handoff = h
                    break
        if handoff is None:
            raise KeyError(f"Handoff {handoff_id} not found")
        if artifact_type is None:
            return list(handoff.artifacts)
        return [a for a in handoff.artifacts if a.artifact_type == artifact_type]

    async def build_context_from_handoffs(
        self, agent_name: str, budget: int = 5000
    ) -> str:
        """Build a context string from all pending handoffs for an agent.

        Prioritizes: blocking > important > informational.
        Truncates to budget characters.

        Args:
            agent_name: The agent to build context for.
            budget: Maximum character count for the resulting string.

        Returns:
            Formatted context string, or empty string if no pending handoffs.
        """
        pending = await self.get_pending(agent_name)
        if not pending:
            return ""

        sections: list[str] = ["# Handoff Context"]
        used = len(sections[0])

        for handoff in pending:
            header = (
                f"\n## [{handoff.priority.value.upper()}] "
                f"From {handoff.from_agent}: {handoff.task_context}"
            )
            body_parts: list[str] = [header]
            for artifact in handoff.artifacts:
                label = artifact.artifact_type.value
                summary = artifact.summary or artifact.content[:80]
                body_parts.append(f"- **{label}**: {summary}")
            section = "\n".join(body_parts)

            if used + len(section) > budget:
                remaining = budget - used
                if remaining > 40:
                    sections.append(section[:remaining] + "\n... [truncated]")
                break
            sections.append(section)
            used += len(section)

        return "\n".join(sections)

    async def handoff_chain(self, agent_name: str) -> list[Handoff]:
        """Get the chain of handoffs that led to this agent's current work.

        Walks backward through history: finds handoffs TO this agent,
        then traces FROM those senders, building a reverse-chronological chain.

        Args:
            agent_name: The agent whose inbound chain to trace.

        Returns:
            List of Handoff objects forming the chain (most recent first).
        """
        chain: list[Handoff] = []
        seen_ids: set[str] = set()
        current_agent = agent_name

        for handoff in reversed(self._history):
            if handoff.id in seen_ids:
                continue
            if handoff.to_agent == current_agent or (
                handoff.to_agent == "*" and handoff.from_agent != current_agent
            ):
                chain.append(handoff)
                seen_ids.add(handoff.id)
                current_agent = handoff.from_agent

        return chain

    async def _persist(self, handoff: Handoff) -> None:
        """Append handoff to JSONL store.

        Creates parent directories if they do not exist.

        Args:
            handoff: The Handoff to persist.
        """
        try:
            _append_locked_jsonl(self._store_path, handoff.model_dump_json() + "\n")
        except OSError as exc:
            logger.warning("Failed to persist handoff %s: %s", handoff.id, exc)

    async def load_from_store(self) -> int:
        """Load handoffs from JSONL store into memory.

        Returns:
            Number of handoffs loaded.
        """
        if not self._store_path.exists():
            return 0
        count = 0
        seen_ids: set[str] = set()
        loaded: list[Handoff] = []
        try:
            with open(self._store_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    handoff = Handoff.model_validate_json(line)
                    loaded.append(handoff)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Error loading handoff store: %s", exc)
            return 0

        # Deduplicate: last occurrence wins (reflects status updates).
        new_entries: list[Handoff] = []
        for handoff in reversed(loaded):
            if handoff.id not in seen_ids:
                seen_ids.add(handoff.id)
                if handoff.status == "pending":
                    self._pending[handoff.id] = handoff
                new_entries.append(handoff)
                count += 1

        # Restore chronological order for newly loaded entries only,
        # then prepend them before any existing in-memory history.
        new_entries.reverse()
        self._history = new_entries + self._history
        return count
