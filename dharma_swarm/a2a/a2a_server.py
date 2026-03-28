"""A2A Server -- accepts task delegations from other agents.

Receives A2A task requests and dispatches them to the dharma_swarm
task board and orchestrator. Manages the A2A task lifecycle:

    submitted -> working -> input-required -> completed/failed

For local agents: direct function calls (no HTTP).
For remote agents (AGNI/RUSHABDEV): HTTP endpoint (future milestone).

The server maintains an in-memory task store with A2A-specific metadata
layered on top of dharma_swarm's Task model. This keeps the protocol
boundary clean while reusing existing infrastructure.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# A2A task lifecycle
# ---------------------------------------------------------------------------


class A2ATaskStatus(str, Enum):
    """Task lifecycle states per A2A protocol."""

    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class A2APartType(str, Enum):
    """Message part types per A2A protocol."""

    TEXT = "text"
    FILE = "file"
    DATA = "data"


@dataclass
class A2APart:
    """A single part of an A2A message.

    Simplified from the full spec -- covers the 80% case.

    Attributes:
        type: One of text, file, data.
        content: The actual content (text string, file path, or serialized data).
        metadata: Optional extra context (e.g., mime_type, filename).
    """

    type: A2APartType = A2APartType.TEXT
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class A2AMessage:
    """A message in the A2A protocol.

    Messages contain one or more parts and travel between agents.
    """

    role: str = "user"  # "user" (requester) or "agent" (responder)
    parts: list[A2APart] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def text(cls, content: str, role: str = "user") -> A2AMessage:
        """Convenience: create a single-text-part message."""
        return cls(role=role, parts=[A2APart(type=A2APartType.TEXT, content=content)])


@dataclass
class A2ATask:
    """An A2A task -- the core unit of work in the protocol.

    Maps to dharma_swarm Task but adds A2A-specific lifecycle tracking.

    Attributes:
        id: Unique task identifier.
        from_agent: Name of the requesting agent.
        to_agent: Name of the target agent (or empty for capability-based routing).
        status: Current lifecycle state.
        messages: Conversation history (request + responses).
        capability: The capability being requested (for discovery-based routing).
        dharma_task_id: ID of the corresponding dharma_swarm Task (if created).
        created_at: ISO-8601 creation timestamp.
        updated_at: ISO-8601 last update timestamp.
        result: Final result (populated on completion).
        error: Error message (populated on failure).
        metadata: Arbitrary extra data.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    from_agent: str = ""
    to_agent: str = ""
    status: A2ATaskStatus = A2ATaskStatus.SUBMITTED
    messages: list[A2AMessage] = field(default_factory=list)
    capability: str = ""
    dharma_task_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# Type alias for task handler callbacks
TaskHandler = Callable[[A2ATask], A2ATask]


# ---------------------------------------------------------------------------
# A2A Server
# ---------------------------------------------------------------------------


class A2AServer:
    """Accepts A2A task delegations and dispatches to dharma_swarm.

    Local-first: tasks are dispatched via direct function calls.
    The server maintains its own task store for A2A lifecycle tracking,
    separate from (but linked to) the dharma_swarm task board.

    Usage::

        server = A2AServer()
        server.register_handler("code_review", my_review_handler)

        task = server.submit(A2ATask(
            from_agent="orchestrator",
            to_agent="reviewer",
            capability="code_review",
            messages=[A2AMessage.text("Review this PR")],
        ))

        # Later: check status
        status = server.get_status(task.id)

    Attributes:
        tasks: In-memory store of A2A tasks keyed by task ID.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, A2ATask] = {}
        self._handlers: dict[str, TaskHandler] = {}
        self._default_handler: TaskHandler | None = None

    # -- handler registration ------------------------------------------------

    def register_handler(
        self,
        capability: str,
        handler: TaskHandler,
    ) -> None:
        """Register a handler for a specific capability.

        When a task targeting this capability is submitted, the handler
        is called to process it.

        Args:
            capability: Capability name (e.g., "code_review").
            handler: Callable that takes A2ATask and returns updated A2ATask.
        """
        self._handlers[capability] = handler
        logger.info("Registered A2A handler for capability: %s", capability)

    def set_default_handler(self, handler: TaskHandler) -> None:
        """Set a fallback handler for tasks with no matching capability handler."""
        self._default_handler = handler

    # -- task lifecycle ------------------------------------------------------

    def submit(self, task: A2ATask) -> A2ATask:
        """Submit a new task for processing.

        The task is stored, then dispatched to the appropriate handler
        based on the requested capability. If no handler matches,
        the default handler is tried. If no default handler exists,
        the task fails immediately.

        Args:
            task: The A2ATask to submit.

        Returns:
            The task with updated status.
        """
        task.status = A2ATaskStatus.SUBMITTED
        task.updated_at = datetime.now(timezone.utc).isoformat()
        self._tasks[task.id] = task

        logger.info(
            "A2A task submitted: %s (from=%s, to=%s, cap=%s)",
            task.id, task.from_agent, task.to_agent, task.capability,
        )

        # Dispatch to handler
        return self._dispatch(task)

    def _dispatch(self, task: A2ATask) -> A2ATask:
        """Route task to appropriate handler and execute."""
        handler = self._handlers.get(task.capability)
        if handler is None:
            handler = self._default_handler

        if handler is None:
            task.status = A2ATaskStatus.FAILED
            task.error = f"No handler registered for capability: {task.capability!r}"
            task.updated_at = datetime.now(timezone.utc).isoformat()
            logger.warning("A2A task %s failed: no handler for %s", task.id, task.capability)
            return task

        task.status = A2ATaskStatus.WORKING
        task.updated_at = datetime.now(timezone.utc).isoformat()

        try:
            task = handler(task)
            if task.status == A2ATaskStatus.WORKING:
                # Handler didn't set final status -- mark completed
                task.status = A2ATaskStatus.COMPLETED
            task.updated_at = datetime.now(timezone.utc).isoformat()
            logger.info("A2A task %s completed (status=%s)", task.id, task.status.value)
        except Exception as exc:
            task.status = A2ATaskStatus.FAILED
            task.error = str(exc)
            task.updated_at = datetime.now(timezone.utc).isoformat()
            logger.error("A2A task %s failed: %s", task.id, exc)

        return task

    def get_task(self, task_id: str) -> A2ATask | None:
        """Retrieve a task by ID."""
        return self._tasks.get(task_id)

    def get_status(self, task_id: str) -> A2ATaskStatus | None:
        """Get the status of a task. Returns None if task not found."""
        task = self._tasks.get(task_id)
        return task.status if task else None

    def cancel(self, task_id: str) -> bool:
        """Cancel a task. Returns True if successful.

        Only submitted or working tasks can be cancelled.
        """
        task = self._tasks.get(task_id)
        if task is None:
            return False
        if task.status in (A2ATaskStatus.COMPLETED, A2ATaskStatus.FAILED, A2ATaskStatus.CANCELLED):
            return False
        task.status = A2ATaskStatus.CANCELLED
        task.updated_at = datetime.now(timezone.utc).isoformat()
        logger.info("A2A task %s cancelled", task_id)
        return True

    def list_tasks(
        self,
        status: A2ATaskStatus | None = None,
        from_agent: str | None = None,
        to_agent: str | None = None,
    ) -> list[A2ATask]:
        """List tasks with optional filters.

        Args:
            status: Filter by task status.
            from_agent: Filter by requesting agent.
            to_agent: Filter by target agent.

        Returns:
            List of matching tasks.
        """
        tasks = list(self._tasks.values())
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        if from_agent is not None:
            tasks = [t for t in tasks if t.from_agent == from_agent]
        if to_agent is not None:
            tasks = [t for t in tasks if t.to_agent == to_agent]
        return tasks

    def task_count(self) -> int:
        """Total number of tracked tasks."""
        return len(self._tasks)

    def summary(self) -> dict[str, int]:
        """Return counts by status."""
        counts: dict[str, int] = {}
        for task in self._tasks.values():
            key = task.status.value
            counts[key] = counts.get(key, 0) + 1
        return counts
