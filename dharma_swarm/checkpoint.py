"""Checkpoint / Resume / Interrupt primitives for cascade loops and workflows.

Stolen from LangGraph's best ideas, adapted to dharma_swarm's eigenform engine:

  1. **LoopCheckpoint** — serializable snapshot of a LoopEngine mid-run.
     Saved after every iteration. On crash, resume from exact state.

  2. **InterruptGate** — async primitive that pauses execution and waits
     for operator input. Used in cascade GATE phase and workflow steps.
     The operator can APPROVE, REJECT, or MODIFY the artifact.

  3. **CheckpointStore** — filesystem-backed store for checkpoint data.
     One JSON file per (domain, cycle_id) pair in ~/.dharma/checkpoints/.

Design principles:
  - No new dependencies (pure stdlib + pydantic)
  - Crash-safe: atomic writes via tmp+rename
  - Integrates with existing telos_gates (interrupt on Tier B/C review)
  - Integrates with existing workflow.py checkpointing
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = Path(os.getenv(
    "DHARMA_CHECKPOINT_DIR",
    str(Path.home() / ".dharma" / "checkpoints"),
))


# ---------------------------------------------------------------------------
# Interrupt protocol
# ---------------------------------------------------------------------------


class InterruptDecision(str, Enum):
    """Operator's response to an interrupt."""
    APPROVE = "approve"
    REJECT = "reject"
    MODIFY = "modify"


class InterruptRequest(BaseModel):
    """A request for human-in-the-loop intervention."""
    id: str = Field(default_factory=lambda: _new_id())
    domain: str = ""
    cycle_id: str = ""
    iteration: int = 0
    phase: str = ""  # Which phase triggered the interrupt (gate, score, etc.)
    reason: str = ""
    artifact: dict[str, Any] = Field(default_factory=dict)
    gate_results: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class InterruptResponse(BaseModel):
    """Operator's response to an interrupt request."""
    request_id: str
    decision: InterruptDecision
    reason: str = ""
    modified_artifact: dict[str, Any] | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class InterruptGate:
    """Async gate that pauses execution until operator responds.

    Usage in cascade GATE phase::

        gate = InterruptGate(callback=my_callback)
        response = await gate.interrupt(request)
        if response.decision == InterruptDecision.REJECT:
            # skip this iteration
            ...

    The callback is how the interrupt reaches the operator:
      - CLI: writes to ~/.dharma/interrupts/ and polls for response
      - API: emits WebSocket event and awaits response
      - TUI: shows modal dialog

    If no callback is set, interrupts auto-approve (backward compatible).
    """

    def __init__(
        self,
        callback: Callable[[InterruptRequest], Any] | None = None,
        timeout_seconds: float = 300.0,
        auto_approve: bool = True,
    ) -> None:
        self._callback = callback
        self._timeout = timeout_seconds
        self._auto_approve = auto_approve
        self._pending: dict[str, asyncio.Future[InterruptResponse]] = {}

    async def interrupt(self, request: InterruptRequest) -> InterruptResponse:
        """Pause execution and wait for operator response.

        If no callback is registered and auto_approve is True, returns
        APPROVE immediately (backward compatible with existing behavior).
        """
        if self._callback is None and self._auto_approve:
            return InterruptResponse(
                request_id=request.id,
                decision=InterruptDecision.APPROVE,
                reason="auto-approved (no interrupt handler registered)",
            )

        # Create a future for the response
        loop = asyncio.get_running_loop()
        future: asyncio.Future[InterruptResponse] = loop.create_future()
        self._pending[request.id] = future

        # Notify the operator
        if self._callback is not None:
            result = self._callback(request)
            if asyncio.iscoroutine(result):
                await result

        # Also persist to filesystem for CLI pickup
        _write_interrupt_request(request)

        try:
            response = await asyncio.wait_for(future, timeout=self._timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "Interrupt %s timed out after %.0fs, auto-%s",
                request.id,
                self._timeout,
                "approving" if self._auto_approve else "rejecting",
            )
            response = InterruptResponse(
                request_id=request.id,
                decision=InterruptDecision.APPROVE if self._auto_approve else InterruptDecision.REJECT,
                reason=f"timeout after {self._timeout}s",
            )
        finally:
            self._pending.pop(request.id, None)

        return response

    def resolve(self, response: InterruptResponse) -> bool:
        """Resolve a pending interrupt with an operator response.

        Called by the API/CLI/TUI when the operator responds.
        Returns True if the interrupt was found and resolved.
        """
        future = self._pending.get(response.request_id)
        if future is None or future.done():
            return False
        future.set_result(response)
        return True

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def pending_ids(self) -> list[str]:
        return list(self._pending.keys())


# ---------------------------------------------------------------------------
# Loop checkpoint
# ---------------------------------------------------------------------------


class LoopCheckpoint(BaseModel):
    """Serializable snapshot of a LoopEngine mid-run.

    Saved after every iteration. On crash/restart, the engine can
    resume from the exact iteration with full state.
    """
    domain: str
    cycle_id: str
    iteration: int = 0
    current: dict[str, Any] | None = None
    previous: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    best_score: float = 0.0
    fitness_trajectory: list[float] = Field(default_factory=list)
    eigenform_trajectory: list[float] = Field(default_factory=list)
    elapsed_seconds: float = 0.0
    converged: bool = False
    convergence_reason: str = ""
    interrupted: bool = False
    interrupt_reason: str = ""
    version: str = "1"
    saved_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CheckpointStore:
    """Filesystem-backed checkpoint store.

    Layout: {checkpoint_dir}/{domain}/{cycle_id}.json
    Atomic writes via tmp+rename.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or CHECKPOINT_DIR

    def _path(self, domain: str, cycle_id: str) -> Path:
        return self.base_dir / domain / f"{cycle_id}.json"

    def save(self, checkpoint: LoopCheckpoint) -> Path:
        """Atomically save a checkpoint. Returns the file path."""
        target = self._path(checkpoint.domain, checkpoint.cycle_id)
        target.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(
            dir=str(target.parent), suffix=".tmp", prefix=".cp_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(checkpoint.model_dump_json(indent=2))
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, target)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        return target

    def load(self, domain: str, cycle_id: str) -> LoopCheckpoint | None:
        """Load a checkpoint if it exists."""
        path = self._path(domain, cycle_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return LoopCheckpoint(**data)
        except (json.JSONDecodeError, OSError, ValueError) as e:
            logger.warning("Failed to load checkpoint %s: %s", path, e)
            return None

    def delete(self, domain: str, cycle_id: str) -> bool:
        """Delete a checkpoint after successful completion."""
        path = self._path(domain, cycle_id)
        try:
            path.unlink(missing_ok=True)
            return True
        except OSError:
            return False

    def list_checkpoints(self, domain: str | None = None) -> list[LoopCheckpoint]:
        """List all saved checkpoints, optionally filtered by domain."""
        results: list[LoopCheckpoint] = []
        if domain:
            search_dir = self.base_dir / domain
            if not search_dir.is_dir():
                return []
            files = search_dir.glob("*.json")
        else:
            files = self.base_dir.rglob("*.json")

        for path in files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                results.append(LoopCheckpoint(**data))
            except (json.JSONDecodeError, OSError, ValueError):
                continue

        return sorted(results, key=lambda c: c.saved_at, reverse=True)


# ---------------------------------------------------------------------------
# Filesystem interrupt transport (for CLI)
# ---------------------------------------------------------------------------

INTERRUPT_DIR = Path(os.getenv(
    "DHARMA_INTERRUPT_DIR",
    str(Path.home() / ".dharma" / "interrupts"),
))


def _new_id() -> str:
    import uuid
    return uuid.uuid4().hex[:16]


def _write_interrupt_request(request: InterruptRequest) -> Path:
    """Write an interrupt request to the filesystem for CLI pickup."""
    INTERRUPT_DIR.mkdir(parents=True, exist_ok=True)
    path = INTERRUPT_DIR / f"{request.id}.request.json"
    path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def read_pending_interrupts() -> list[InterruptRequest]:
    """Read all pending interrupt requests from the filesystem."""
    if not INTERRUPT_DIR.is_dir():
        return []
    results = []
    for path in sorted(INTERRUPT_DIR.glob("*.request.json")):
        response_path = path.with_suffix("").with_suffix(".response.json")
        if response_path.exists():
            continue  # Already responded
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            results.append(InterruptRequest(**data))
        except (json.JSONDecodeError, OSError, ValueError):
            continue
    return results


def write_interrupt_response(response: InterruptResponse) -> Path:
    """Write an interrupt response to the filesystem."""
    INTERRUPT_DIR.mkdir(parents=True, exist_ok=True)
    path = INTERRUPT_DIR / f"{response.request_id}.response.json"
    path.write_text(response.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def read_interrupt_response(request_id: str) -> InterruptResponse | None:
    """Read an interrupt response from the filesystem."""
    path = INTERRUPT_DIR / f"{request_id}.response.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return InterruptResponse(**data)
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def cleanup_interrupt(request_id: str) -> None:
    """Remove interrupt request and response files."""
    for suffix in (".request.json", ".response.json"):
        path = INTERRUPT_DIR / f"{request_id}{suffix}"
        path.unlink(missing_ok=True)
