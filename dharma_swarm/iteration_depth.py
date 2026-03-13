"""Iteration Depth Tracker — the quality ratchet that only turns one way.

Persistent JSONL ledger tracking every initiative across review cycles.
Anti-noise: nothing "solid" until iteration_count >= 3 AND quality_score >= 0.7.
Anti-amnesia: every review reads ALL active initiatives and decides: deepen, ship, or abandon.

Storage: ~/.dharma/iteration/initiatives.jsonl + queue.jsonl
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────

DHARMA_DIR = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma"))
ITERATION_DIR = DHARMA_DIR / "iteration"
INITIATIVES_FILE = ITERATION_DIR / "initiatives.jsonl"
QUEUE_FILE = ITERATION_DIR / "queue.jsonl"

# Quality ratchet thresholds
MIN_ITERATIONS_FOR_SOLID = 3
MIN_QUALITY_FOR_SOLID = 0.7
MIN_QUALITY_FOR_SHIPPED = 0.85


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# ── Status Model ─────────────────────────────────────────────────────


class InitiativeStatus(str, Enum):
    """Lifecycle status — the ratchet only turns one way."""
    SEED = "seed"             # Idea captured, no iterations yet
    GROWING = "growing"       # Active iteration, not yet solid
    SOLID = "solid"           # >= 3 iterations AND quality >= 0.7
    SHIPPED = "shipped"       # Deployed / user-facing
    ABANDONED = "abandoned"   # Explicit decision, logged with reason


# ── Data Models ──────────────────────────────────────────────────────


class IterationRecord(BaseModel):
    """Single iteration pass on an initiative."""
    timestamp: str = Field(default_factory=lambda: _utc_now().isoformat())
    action: str = ""          # What was done: "added tests", "refactored API", etc.
    quality_delta: float = 0.0  # Change in quality score
    evidence: str = ""        # Concrete evidence: test counts, file paths, etc.
    reviewer: str = "auto"    # "auto" for review cycle, "human" for manual


class QueueItem(BaseModel):
    """Improvement task queued for the next cycle."""
    id: str = Field(default_factory=_new_id)
    initiative_id: str
    task: str                 # What needs to be done
    priority: float = 0.5    # 0-1, higher = more urgent
    created_at: str = Field(default_factory=lambda: _utc_now().isoformat())
    completed: bool = False
    completed_at: str | None = None


class Initiative(BaseModel):
    """A tracked initiative in the iteration depth ledger."""
    id: str = Field(default_factory=_new_id)
    title: str
    description: str = ""
    created_at: str = Field(default_factory=lambda: _utc_now().isoformat())
    updated_at: str = Field(default_factory=lambda: _utc_now().isoformat())
    status: InitiativeStatus = InitiativeStatus.SEED
    iteration_count: int = 0
    quality_score: float = 0.0
    history: list[IterationRecord] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    abandon_reason: str | None = None

    # Project this initiative belongs to (path or short name)
    project: str = "dharma_swarm"

    # Quality dimensions (each 0-1, averaged for quality_score)
    has_tests: float = 0.0
    tests_pass: float = 0.0
    error_handling: float = 0.0   # Files with try/except/raise / total files
    documented: float = 0.0
    edge_cases_covered: float = 0.0  # Functions with >1 test / total functions

    def compute_quality(self) -> float:
        """Recompute quality_score from dimensions."""
        dimensions = [
            self.has_tests,
            self.tests_pass,
            self.error_handling,
            self.documented,
            self.edge_cases_covered,
        ]
        self.quality_score = round(sum(dimensions) / len(dimensions), 3)
        return self.quality_score

    def can_promote_to_solid(self) -> bool:
        """Anti-noise rule: must have iterated deeply with real quality."""
        return (
            self.iteration_count >= MIN_ITERATIONS_FOR_SOLID
            and self.quality_score >= MIN_QUALITY_FOR_SOLID
        )

    def can_promote_to_shipped(self) -> bool:
        """Shipped requires solid status and high quality."""
        return (
            self.status == InitiativeStatus.SOLID
            and self.quality_score >= MIN_QUALITY_FOR_SHIPPED
        )


# ── Persistence ──────────────────────────────────────────────────────


def _ensure_dirs() -> None:
    ITERATION_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write(path: Path, lines: list[str]) -> None:
    """Atomically write lines to a JSONL file."""
    _ensure_dirs()
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp", prefix=".iter_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for line in lines:
                f.write(line.rstrip("\n") + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ── Initiative Ledger ────────────────────────────────────────────────


class IterationLedger:
    """JSONL-backed initiative ledger with quality ratchet semantics.

    Anti-amnesia: load_all() always reads everything.
    Anti-noise: promote() enforces iteration + quality thresholds.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or INITIATIVES_FILE
        self._initiatives: dict[str, Initiative] = {}

    def load(self) -> list[Initiative]:
        """Load ALL initiatives from JSONL. Anti-amnesia: nothing skipped."""
        self._initiatives.clear()
        if not self.path.exists():
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                    init = Initiative(**data)
                    self._initiatives[init.id] = init
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning("Skipping malformed initiative line: %s", e)
        return list(self._initiatives.values())

    def save(self) -> None:
        """Rewrite all initiatives atomically."""
        lines = [init.model_dump_json() for init in self._initiatives.values()]
        _atomic_write(self.path, lines)

    def get(self, initiative_id: str) -> Initiative | None:
        return self._initiatives.get(initiative_id)

    def get_all(self) -> list[Initiative]:
        return list(self._initiatives.values())

    def get_active(self) -> list[Initiative]:
        """All initiatives that are NOT abandoned or shipped."""
        return [
            i for i in self._initiatives.values()
            if i.status not in (InitiativeStatus.ABANDONED, InitiativeStatus.SHIPPED)
        ]

    def get_by_status(self, status: InitiativeStatus) -> list[Initiative]:
        return [i for i in self._initiatives.values() if i.status == status]

    # -- mutations -----------------------------------------------------------

    def create(
        self,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
    ) -> Initiative:
        """Create a new seed initiative."""
        init = Initiative(
            title=title,
            description=description,
            tags=tags or [],
        )
        self._initiatives[init.id] = init
        self.save()
        return init

    def record_iteration(
        self,
        initiative_id: str,
        action: str,
        evidence: str = "",
        quality_updates: dict[str, float] | None = None,
        reviewer: str = "auto",
    ) -> Initiative | None:
        """Record an iteration pass. Ratchet: quality can only increase."""
        init = self._initiatives.get(initiative_id)
        if init is None:
            return None

        # Apply quality dimension updates (ratchet: max of old and new)
        if quality_updates:
            for dim, value in quality_updates.items():
                if hasattr(init, dim):
                    old = getattr(init, dim)
                    setattr(init, dim, max(old, min(1.0, value)))

        old_quality = init.quality_score
        new_quality = init.compute_quality()
        quality_delta = round(new_quality - old_quality, 3)

        record = IterationRecord(
            action=action,
            quality_delta=quality_delta,
            evidence=evidence,
            reviewer=reviewer,
        )
        init.history.append(record)
        init.iteration_count += 1
        init.updated_at = _utc_now().isoformat()

        # Auto-promote seed → growing on first iteration
        if init.status == InitiativeStatus.SEED and init.iteration_count >= 1:
            init.status = InitiativeStatus.GROWING

        self.save()
        return init

    def promote(self, initiative_id: str) -> tuple[bool, str]:
        """Try to promote an initiative to the next status level.

        Returns (success, reason).
        Anti-noise: enforces thresholds.
        """
        init = self._initiatives.get(initiative_id)
        if init is None:
            return False, "Initiative not found"

        if init.status == InitiativeStatus.GROWING:
            if not init.can_promote_to_solid():
                needed_iters = max(0, MIN_ITERATIONS_FOR_SOLID - init.iteration_count)
                needed_quality = max(0.0, MIN_QUALITY_FOR_SOLID - init.quality_score)
                return False, (
                    f"Not ready for solid. Need {needed_iters} more iterations "
                    f"and {needed_quality:.2f} more quality"
                )
            init.status = InitiativeStatus.SOLID
            init.updated_at = _utc_now().isoformat()
            self.save()
            return True, "Promoted to solid"

        elif init.status == InitiativeStatus.SOLID:
            if not init.can_promote_to_shipped():
                needed = max(0.0, MIN_QUALITY_FOR_SHIPPED - init.quality_score)
                return False, f"Not ready for shipped. Need {needed:.2f} more quality"
            init.status = InitiativeStatus.SHIPPED
            init.updated_at = _utc_now().isoformat()
            self.save()
            return True, "Promoted to shipped"

        return False, f"Cannot promote from {init.status.value}"

    def abandon(self, initiative_id: str, reason: str) -> bool:
        """Explicitly abandon an initiative. Anti-amnesia: reason is logged."""
        init = self._initiatives.get(initiative_id)
        if init is None:
            return False
        init.status = InitiativeStatus.ABANDONED
        init.abandon_reason = reason
        init.updated_at = _utc_now().isoformat()
        init.history.append(IterationRecord(
            action=f"ABANDONED: {reason}",
            reviewer="human",
        ))
        self.save()
        return True

    # -- reporting -----------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Compact summary for review cycles."""
        all_inits = list(self._initiatives.values())
        by_status: dict[str, int] = {}
        for init in all_inits:
            by_status[init.status.value] = by_status.get(init.status.value, 0) + 1

        active = self.get_active()
        shallow = [i for i in active if i.iteration_count < MIN_ITERATIONS_FOR_SOLID]
        ready_to_promote = [
            i for i in active
            if i.status == InitiativeStatus.GROWING and i.can_promote_to_solid()
        ]

        return {
            "total": len(all_inits),
            "by_status": by_status,
            "active_count": len(active),
            "shallow_count": len(shallow),
            "shallow": [
                {"id": i.id, "title": i.title, "iterations": i.iteration_count,
                 "quality": i.quality_score}
                for i in shallow
            ],
            "ready_to_promote": [
                {"id": i.id, "title": i.title, "iterations": i.iteration_count,
                 "quality": i.quality_score}
                for i in ready_to_promote
            ],
            "avg_iterations": (
                round(sum(i.iteration_count for i in active) / len(active), 1)
                if active else 0.0
            ),
            "avg_quality": (
                round(sum(i.quality_score for i in active) / len(active), 3)
                if active else 0.0
            ),
        }


# ── Compounding Queue ────────────────────────────────────────────────


class CompoundingQueue:
    """Improvement tasks queued for next review cycle.

    Anti-amnesia: tasks persist until explicitly completed or removed.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or QUEUE_FILE
        self._items: list[QueueItem] = []

    def load(self) -> list[QueueItem]:
        self._items.clear()
        if not self.path.exists():
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    self._items.append(QueueItem(**json.loads(stripped)))
                except (json.JSONDecodeError, ValueError):
                    continue
        return list(self._items)

    def save(self) -> None:
        lines = [item.model_dump_json() for item in self._items]
        _atomic_write(self.path, lines)

    def add(
        self,
        initiative_id: str,
        task: str,
        priority: float = 0.5,
    ) -> QueueItem:
        """Queue an improvement task for the next cycle."""
        item = QueueItem(
            initiative_id=initiative_id,
            task=task,
            priority=priority,
        )
        self._items.append(item)
        self.save()
        return item

    def get_pending(self) -> list[QueueItem]:
        """All incomplete items, sorted by priority descending."""
        pending = [i for i in self._items if not i.completed]
        pending.sort(key=lambda i: i.priority, reverse=True)
        return pending

    def get_for_initiative(self, initiative_id: str) -> list[QueueItem]:
        return [i for i in self._items if i.initiative_id == initiative_id]

    def complete(self, item_id: str) -> bool:
        for item in self._items:
            if item.id == item_id:
                item.completed = True
                item.completed_at = _utc_now().isoformat()
                self.save()
                return True
        return False

    def remove(self, item_id: str) -> bool:
        original = len(self._items)
        self._items = [i for i in self._items if i.id != item_id]
        if len(self._items) < original:
            self.save()
            return True
        return False

    def summary(self) -> dict[str, Any]:
        pending = self.get_pending()
        return {
            "total": len(self._items),
            "pending": len(pending),
            "completed": len(self._items) - len(pending),
            "top_tasks": [
                {"initiative_id": i.initiative_id, "task": i.task, "priority": i.priority}
                for i in pending[:5]
            ],
        }
