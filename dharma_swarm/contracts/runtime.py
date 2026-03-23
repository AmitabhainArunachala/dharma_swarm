"""Sovereign runtime-side contracts."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .common import CheckpointRecord, ExecutionRequest, ExecutionResult, GatewayMessage, RunDescriptor


@runtime_checkable
class AgentRuntime(Protocol):
    """Canonical interface for run lifecycle management."""

    async def start_run(self, run: RunDescriptor) -> RunDescriptor:
        """Start or register a run."""

    async def update_run(self, run: RunDescriptor) -> RunDescriptor:
        """Persist a run status transition."""

    async def get_run(self, run_id: str) -> RunDescriptor | None:
        """Load a run by ID."""

    async def list_runs(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        limit: int = 50,
    ) -> list[RunDescriptor]:
        """List runs in descending operational relevance."""


@runtime_checkable
class GatewayAdapter(Protocol):
    """Canonical interface for channel and delivery operations."""

    async def send_message(self, message: GatewayMessage) -> str:
        """Send a message to a channel recipient and return its ID."""

    async def receive_messages(
        self,
        *,
        recipient: str,
        channel: str | None = None,
        limit: int = 50,
    ) -> list[GatewayMessage]:
        """Receive recent messages for a recipient."""

    async def acknowledge_delivery(
        self,
        *,
        message_id: str,
        acknowledged_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Mark a delivery as seen or accepted."""

    async def list_channels(self) -> list[str]:
        """Return known channels."""


@runtime_checkable
class CheckpointStore(Protocol):
    """Canonical interface for pause/resume state."""

    async def save_checkpoint(self, checkpoint: CheckpointRecord) -> CheckpointRecord:
        """Persist a checkpoint."""

    async def get_checkpoint(self, checkpoint_id: str) -> CheckpointRecord | None:
        """Load a checkpoint by ID."""

    async def list_checkpoints(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        limit: int = 50,
    ) -> list[CheckpointRecord]:
        """List checkpoints for a run or session."""

    async def resolve_checkpoint(
        self,
        *,
        checkpoint_id: str,
        status: str,
        resolved_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> CheckpointRecord:
        """Approve, reject, resume, or supersede a checkpoint."""


@runtime_checkable
class SandboxProvider(Protocol):
    """Canonical interface for executable sandboxes."""

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Run a command under a sandbox policy."""

    async def describe_capabilities(self) -> dict[str, Any]:
        """Describe backend capabilities and limits."""


@runtime_checkable
class InteropAdapter(Protocol):
    """Canonical interface for external import/export or compatibility."""

    async def export_snapshot(self, *, format_name: str) -> dict[str, Any]:
        """Export DHARMA state into a named interop format."""

    async def import_snapshot(self, payload: dict[str, Any], *, source: str) -> dict[str, Any]:
        """Import a donor snapshot into DHARMA-owned structures."""
