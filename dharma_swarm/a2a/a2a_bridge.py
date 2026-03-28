"""A2A Bridge -- backward-compatible bridge to TRISHULA and signal_bus.

Provides a smooth migration path from file-based TRISHULA messaging
to the A2A protocol. Does not break existing TRISHULA -- builds alongside.

Responsibilities:
    1. Convert TRISHULA inbox messages into A2A tasks (inbound).
    2. Convert A2A task results into TRISHULA outbox messages (outbound).
    3. Emit A2A lifecycle events onto the signal bus.
    4. Wrap the existing TrishulaBridge for backward compatibility.

The bridge ensures that during the transition period, agents using
TRISHULA and agents using A2A can coexist and communicate.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.a2a.agent_card import CardRegistry
from dharma_swarm.a2a.a2a_server import (
    A2AMessage,
    A2APart,
    A2APartType,
    A2AServer,
    A2ATask,
    A2ATaskStatus,
)

logger = logging.getLogger(__name__)

_DHARMA_HOME = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma"))

# Signal types emitted onto the signal bus
SIGNAL_A2A_TASK_SUBMITTED = "A2A_TASK_SUBMITTED"
SIGNAL_A2A_TASK_COMPLETED = "A2A_TASK_COMPLETED"
SIGNAL_A2A_TASK_FAILED = "A2A_TASK_FAILED"


class A2ABridge:
    """Bridge between A2A protocol and TRISHULA / signal_bus.

    Wraps the TrishulaBridge and translates between the two systems.
    Optionally emits signals onto the dharma_swarm signal bus for
    other subsystems to react to A2A events.

    Args:
        server: A2AServer instance for task dispatch.
        registry: CardRegistry for agent discovery.
        signal_bus: Optional SignalBus instance for event emission.
        trishula_outbox: Path to TRISHULA outbox directory.
    """

    def __init__(
        self,
        server: A2AServer,
        registry: CardRegistry,
        signal_bus: Any | None = None,
        trishula_outbox: Path | None = None,
    ) -> None:
        self._server = server
        self._registry = registry
        self._signal_bus = signal_bus
        self._trishula_outbox = trishula_outbox or (
            Path.home() / "trishula" / "outbox"
        )

    # -- TRISHULA -> A2A (inbound) ------------------------------------------

    def trishula_message_to_a2a_task(
        self,
        message: dict[str, Any],
    ) -> A2ATask:
        """Convert a TRISHULA message dict into an A2ATask.

        Handles the TRISHULA message format:
            {id, from, to, type, priority, subject, body, created_at, ...}

        Maps TRISHULA fields to A2A fields:
            - from -> from_agent
            - to -> to_agent
            - subject + body -> A2AMessage with TextPart
            - type -> metadata["trishula_type"]
            - priority -> metadata["priority"]

        Args:
            message: TRISHULA message dict.

        Returns:
            An A2ATask ready for submission.
        """
        from_agent = message.get("from", "unknown")
        to_agent = message.get("to", "")
        subject = message.get("subject", "")
        body = message.get("body", "")
        msg_type = message.get("type", "task")
        priority = message.get("priority", "normal")
        created_at = message.get("created_at", "")

        # Build message content from subject + body
        content = f"{subject}\n\n{body}".strip() if subject else body

        parts = [A2APart(type=A2APartType.TEXT, content=content)]

        # Include attachments as file parts
        attachments = message.get("attachments", [])
        for att in attachments:
            parts.append(A2APart(
                type=A2APartType.FILE,
                content=str(att),
                metadata={"source": "trishula"},
            ))

        task = A2ATask(
            from_agent=from_agent,
            to_agent=to_agent,
            messages=[A2AMessage(role="user", parts=parts)],
            capability=_infer_capability_from_type(msg_type),
            metadata={
                "source": "trishula",
                "trishula_type": msg_type,
                "trishula_id": message.get("id", ""),
                "priority": priority,
                "created_at": created_at,
            },
        )

        return task

    def ingest_trishula_inbox(
        self,
        inbox_path: Path | None = None,
    ) -> list[A2ATask]:
        """Read TRISHULA inbox files and convert to A2A tasks.

        Reads JSON files from the inbox, converts each to an A2ATask,
        and submits to the A2A server. Does NOT delete or move the files
        (that's still TrishulaBridge's responsibility for backward compat).

        Args:
            inbox_path: Path to TRISHULA inbox. Defaults to ~/trishula/inbox.

        Returns:
            List of submitted A2ATasks.
        """
        inbox = inbox_path or (Path.home() / "trishula" / "inbox")
        if not inbox.is_dir():
            logger.debug("Trishula inbox not found: %s", inbox)
            return []

        tasks: list[A2ATask] = []
        for path in sorted(inbox.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue

                # Skip ack messages
                if data.get("type") == "ack":
                    continue

                task = self.trishula_message_to_a2a_task(data)
                submitted = self._server.submit(task)
                tasks.append(submitted)
                self._emit_signal(SIGNAL_A2A_TASK_SUBMITTED, {
                    "task_id": submitted.id,
                    "from": submitted.from_agent,
                    "to": submitted.to_agent,
                    "source": "trishula",
                })
            except Exception as exc:
                logger.warning("Failed to ingest trishula message %s: %s", path.name, exc)

        if tasks:
            logger.info("Ingested %d trishula messages as A2A tasks", len(tasks))
        return tasks

    # -- A2A -> TRISHULA (outbound) -----------------------------------------

    def a2a_task_to_trishula_message(
        self,
        task: A2ATask,
    ) -> dict[str, Any]:
        """Convert an A2ATask result into a TRISHULA message dict.

        For sending A2A results back through the TRISHULA channel
        (e.g., to remote agents on AGNI/RUSHABDEV that don't speak A2A yet).

        Args:
            task: Completed A2ATask.

        Returns:
            TRISHULA-format message dict.
        """
        # Extract text content from task messages
        body_parts = []
        for msg in task.messages:
            if msg.role == "agent":
                for part in msg.parts:
                    if part.type == A2APartType.TEXT:
                        body_parts.append(part.content)

        body = "\n\n".join(body_parts) if body_parts else task.result

        now = datetime.now(timezone.utc).isoformat()
        slug = task.capability or "a2a_result"
        safe_slug = slug.replace(" ", "_").replace("/", "_")[:40]

        return {
            "id": f"{now.replace(':', '').replace('-', '').replace('.', '_')}_{task.to_agent}_to_{task.from_agent}_{safe_slug}",
            "from": task.to_agent,
            "to": task.from_agent,
            "type": "response",
            "priority": task.metadata.get("priority", "normal"),
            "subject": f"A2A result: {task.capability}",
            "body": body,
            "created_at": now,
            "reply_to": task.metadata.get("trishula_id", ""),
            "attachments": [],
            "metadata": {
                "a2a_task_id": task.id,
                "a2a_status": task.status.value,
            },
        }

    def send_result_to_trishula(self, task: A2ATask) -> Path | None:
        """Write an A2A task result as a TRISHULA outbox message.

        Args:
            task: Completed A2ATask to convert and send.

        Returns:
            Path to the written file, or None if outbox doesn't exist.
        """
        if not self._trishula_outbox.is_dir():
            logger.debug("Trishula outbox not available: %s", self._trishula_outbox)
            return None

        message = self.a2a_task_to_trishula_message(task)
        filename = f"{message['id']}.json"
        path = self._trishula_outbox / filename

        try:
            path.write_text(
                json.dumps(message, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
            logger.info("Sent A2A result to trishula outbox: %s", filename)
            return path
        except Exception as exc:
            logger.error("Failed to write trishula outbox message: %s", exc)
            return None

    # -- signal bus integration ----------------------------------------------

    def _emit_signal(self, signal_type: str, data: dict[str, Any]) -> None:
        """Emit a signal onto the signal bus (if available)."""
        if self._signal_bus is None:
            return
        try:
            self._signal_bus.emit({"type": signal_type, **data})
        except Exception as exc:
            logger.debug("Signal emission failed: %s", exc)

    def emit_task_completed(self, task: A2ATask) -> None:
        """Emit a task-completed signal."""
        self._emit_signal(SIGNAL_A2A_TASK_COMPLETED, {
            "task_id": task.id,
            "from": task.from_agent,
            "to": task.to_agent,
            "capability": task.capability,
            "status": task.status.value,
        })

    def emit_task_failed(self, task: A2ATask) -> None:
        """Emit a task-failed signal."""
        self._emit_signal(SIGNAL_A2A_TASK_FAILED, {
            "task_id": task.id,
            "from": task.from_agent,
            "to": task.to_agent,
            "capability": task.capability,
            "error": task.error,
        })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _infer_capability_from_type(trishula_type: str) -> str:
    """Map TRISHULA message type to an A2A capability name.

    This is a best-effort heuristic. Custom types map to themselves.
    """
    _MAP = {
        "task": "task_execution",
        "response": "task_execution",
        "standup": "reporting",
        "file_share": "file_transfer",
        "proposal": "strategic_planning",
        "broadcast": "notification",
    }
    return _MAP.get(trishula_type, trishula_type)
