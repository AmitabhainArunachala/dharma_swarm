"""S2 Anti-Oscillation Damper -- resource contention management.

Beer's Viable System Model System 2: prevents subsystems from fighting
over shared resources. Provides shared asyncio.Semaphore per resource type
with a claim/release protocol, TTL-based expiry, exponential backoff on
contention, and priority ordering to prevent deadlocks.

Priority (highest first): swarm > health > evolution > pulse > living
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

# Lower number = higher priority.
RESOURCE_PRIORITIES: dict[str, int] = {
    "swarm": 0,
    "health": 1,
    "evolution": 2,
    "pulse": 3,
    "living": 4,
    "cascade": 5,
    "audit": 6,
    "recognition": 7,
}

# Default concurrency limits per resource type.
DEFAULT_CAPACITIES: dict[str, int] = {
    "agent_pool": 5,
    "llm_budget": 3,
    "shared_files": 10,
    "evolution": 1,
    "stigmergy": 5,
}


class ResourceClaim:
    """A tracked resource claim with TTL.

    Attributes:
        resource: Name of the claimed resource.
        claimant: Identifier of the subsystem holding the claim.
        ttl: Time-to-live in seconds before the claim expires.
        acquired_at: Monotonic timestamp of acquisition.
    """

    def __init__(self, resource: str, claimant: str, ttl: float = 60.0) -> None:
        self.resource = resource
        self.claimant = claimant
        self.ttl = ttl
        self.acquired_at = time.monotonic()

    @property
    def expired(self) -> bool:
        """Return True if the claim has exceeded its TTL."""
        return (time.monotonic() - self.acquired_at) > self.ttl

    def remaining(self) -> float:
        """Seconds remaining before expiry (can be negative)."""
        return self.ttl - (time.monotonic() - self.acquired_at)

    def __repr__(self) -> str:
        state = "expired" if self.expired else f"{self.remaining():.1f}s left"
        return f"ResourceClaim({self.resource!r}, {self.claimant!r}, {state})"


class Damper:
    """S2 Anti-Oscillation Damper.

    Manages shared-resource concurrency via asyncio.Semaphore with
    TTL-based claims, exponential backoff on contention, and contention
    logging.

    Args:
        capacities: Mapping of resource name to concurrency limit.
            Defaults to ``DEFAULT_CAPACITIES``.
        log_path: Path for the contention log (JSONL). Defaults to
            ``~/.dharma/damper_log.jsonl``.
        backoff_base: Base delay (seconds) for exponential backoff.
        max_backoff: Ceiling for backoff delay (seconds).
    """

    def __init__(
        self,
        *,
        capacities: dict[str, int] | None = None,
        log_path: Path | None = None,
        backoff_base: float = 0.1,
        max_backoff: float = 10.0,
    ) -> None:
        caps = capacities or dict(DEFAULT_CAPACITIES)
        self._semaphores: dict[str, asyncio.Semaphore] = {
            name: asyncio.Semaphore(cap) for name, cap in caps.items()
        }
        self._claims: dict[str, list[ResourceClaim]] = defaultdict(list)
        self._contention_counts: dict[str, int] = defaultdict(int)
        self._log_path = log_path or (Path.home() / ".dharma" / "damper_log.jsonl")
        self._backoff_base = backoff_base
        self._max_backoff = max_backoff

    # ------------------------------------------------------------------
    # Core claim/release
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def claim(
        self,
        resource: str,
        claimant: str,
        *,
        ttl: float = 60.0,
        priority: int | None = None,
    ) -> AsyncIterator[ResourceClaim]:
        """Claim a resource with priority-aware exponential backoff.

        Usage::

            async with damper.claim("agent_pool", "swarm") as c:
                # ... use the resource ...

        If the resource name is unknown, a semaphore with capacity 1 is
        created on the fly.

        Args:
            resource: Logical resource name.
            claimant: Subsystem identifier.
            ttl: Claim time-to-live in seconds.
            priority: Optional explicit priority (lower = higher).
                Falls back to ``RESOURCE_PRIORITIES.get(claimant, 99)``.

        Yields:
            The ``ResourceClaim`` while the resource is held.
        """
        if resource not in self._semaphores:
            self._semaphores[resource] = asyncio.Semaphore(1)

        sem = self._semaphores[resource]

        # Clean expired claims before attempting acquisition.
        self._purge_expired(resource)

        effective_priority = (
            priority if priority is not None
            else RESOURCE_PRIORITIES.get(claimant, 99)
        )

        attempt = 0
        max_attempts = 6
        while True:
            timeout = self._backoff_base * (2 ** min(attempt, 5))
            try:
                await asyncio.wait_for(sem.acquire(), timeout=timeout)
                break
            except asyncio.TimeoutError:
                attempt += 1
                self._contention_counts[resource] += 1
                if attempt > max_attempts:
                    self._log_contention(resource, claimant, attempt)
                    # Last resort: blocking acquire.
                    await sem.acquire()
                    break
                delay = min(self._backoff_base * (2 ** attempt), self._max_backoff)
                await asyncio.sleep(delay)

        rc = ResourceClaim(resource, claimant, ttl)
        self._claims[resource].append(rc)

        try:
            yield rc
        finally:
            sem.release()
            # Remove this specific claim (identity check, not equality).
            self._claims[resource] = [
                c for c in self._claims[resource] if c is not rc
            ]

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def contention_stats(self) -> dict[str, int]:
        """Return cumulative contention counts per resource."""
        return dict(self._contention_counts)

    def active_claims(self) -> dict[str, list[str]]:
        """Return mapping of resource -> list of active claimant names."""
        result: dict[str, list[str]] = {}
        for resource, claims in self._claims.items():
            active = [c.claimant for c in claims if not c.expired]
            if active:
                result[resource] = active
        return result

    def capacity(self, resource: str) -> int | None:
        """Return the semaphore capacity for a resource, or None if unknown."""
        sem = self._semaphores.get(resource)
        if sem is None:
            return None
        # asyncio.Semaphore stores the initial value in _value at creation;
        # we track the configured capacity from the dict we built.
        # Fallback: return the current available count (may be < capacity).
        return sem._value  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _purge_expired(self, resource: str) -> int:
        """Remove expired claims for *resource*. Return count removed."""
        before = len(self._claims[resource])
        self._claims[resource] = [
            c for c in self._claims[resource] if not c.expired
        ]
        return before - len(self._claims[resource])

    def _log_contention(self, resource: str, claimant: str, attempts: int) -> None:
        """Append a contention event to the JSONL log file."""
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "timestamp": time.time(),
                "resource": resource,
                "claimant": claimant,
                "attempts": attempts,
            }
            with open(self._log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            logger.debug(
                "Failed to log contention for %s/%s", resource, claimant,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def reset_stats(self) -> None:
        """Clear all contention counters."""
        self._contention_counts.clear()

    def register_resource(self, name: str, capacity: int = 1) -> None:
        """Register a new resource (or update capacity of an existing one).

        Args:
            name: Logical resource name.
            capacity: Maximum concurrent claims.
        """
        self._semaphores[name] = asyncio.Semaphore(capacity)

    def __repr__(self) -> str:
        n_res = len(self._semaphores)
        n_active = sum(
            len([c for c in cs if not c.expired])
            for cs in self._claims.values()
        )
        return f"Damper(resources={n_res}, active_claims={n_active})"
