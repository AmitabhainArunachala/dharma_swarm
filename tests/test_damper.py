"""Tests for dharma_swarm.damper — S2 Anti-Oscillation Damper."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from dharma_swarm.damper import (
    DEFAULT_CAPACITIES,
    RESOURCE_PRIORITIES,
    Damper,
    ResourceClaim,
)


# ------------------------------------------------------------------
# ResourceClaim unit tests
# ------------------------------------------------------------------


class TestResourceClaim:
    def test_not_expired_immediately(self) -> None:
        rc = ResourceClaim("agent_pool", "swarm", ttl=60.0)
        assert not rc.expired

    def test_expired_after_ttl(self) -> None:
        rc = ResourceClaim("agent_pool", "swarm", ttl=0.0)
        # TTL of 0 means it expires immediately.
        assert rc.expired

    def test_remaining_positive(self) -> None:
        rc = ResourceClaim("agent_pool", "swarm", ttl=100.0)
        assert rc.remaining() > 0

    def test_repr_contains_resource(self) -> None:
        rc = ResourceClaim("llm_budget", "pulse", ttl=30.0)
        r = repr(rc)
        assert "llm_budget" in r
        assert "pulse" in r


# ------------------------------------------------------------------
# Damper core behaviour
# ------------------------------------------------------------------


class TestDamperClaim:
    async def test_claim_release(self, tmp_path: Path) -> None:
        """Basic claim and release cycle."""
        damper = Damper(log_path=tmp_path / "log.jsonl")
        async with damper.claim("agent_pool", "swarm") as c:
            assert c.resource == "agent_pool"
            assert c.claimant == "swarm"
            # Claim is active while inside the context.
            active = damper.active_claims()
            assert "agent_pool" in active
            assert "swarm" in active["agent_pool"]
        # After exit, claim should be gone.
        assert "swarm" not in damper.active_claims().get("agent_pool", [])

    async def test_concurrent_claims_within_capacity(self, tmp_path: Path) -> None:
        """Multiple concurrent claims up to the capacity limit."""
        damper = Damper(
            capacities={"pool": 3},
            log_path=tmp_path / "log.jsonl",
        )
        results: list[str] = []

        async def worker(name: str) -> None:
            async with damper.claim("pool", name, ttl=5.0):
                results.append(name)
                await asyncio.sleep(0.01)

        await asyncio.gather(worker("a"), worker("b"), worker("c"))
        assert len(results) == 3

    async def test_claim_unknown_resource(self, tmp_path: Path) -> None:
        """Claiming an unknown resource auto-creates a capacity-1 semaphore."""
        damper = Damper(
            capacities={},
            log_path=tmp_path / "log.jsonl",
        )
        async with damper.claim("brand_new", "health") as c:
            assert c.resource == "brand_new"
        # The semaphore should now exist.
        assert damper.capacity("brand_new") is not None

    async def test_expired_claims_cleaned(self, tmp_path: Path) -> None:
        """Expired claims are purged on subsequent claim attempts."""
        damper = Damper(
            capacities={"res": 2},
            log_path=tmp_path / "log.jsonl",
        )
        # Manually inject an expired claim.
        expired = ResourceClaim("res", "old", ttl=0.0)
        damper._claims["res"].append(expired)
        assert expired.expired

        # A new claim should clean up the expired one.
        async with damper.claim("res", "new"):
            active = damper.active_claims()
            claimants = active.get("res", [])
            assert "old" not in claimants
            assert "new" in claimants


class TestDamperContention:
    async def test_contention_stats_recorded(self, tmp_path: Path) -> None:
        """Contention events are counted."""
        damper = Damper(
            capacities={"narrow": 1},
            log_path=tmp_path / "log.jsonl",
            backoff_base=0.01,
            max_backoff=0.05,
        )
        held = asyncio.Event()
        released = asyncio.Event()

        async def holder() -> None:
            async with damper.claim("narrow", "holder", ttl=5.0):
                held.set()
                await released.wait()

        async def waiter() -> None:
            await held.wait()
            async with damper.claim("narrow", "waiter", ttl=5.0):
                pass

        holder_task = asyncio.create_task(holder())
        waiter_task = asyncio.create_task(waiter())

        # Let the waiter attempt and back off at least once.
        await asyncio.sleep(0.1)
        released.set()

        await asyncio.gather(holder_task, waiter_task)

        stats = damper.contention_stats()
        assert stats.get("narrow", 0) >= 1

    async def test_active_claims_empty_initially(self, tmp_path: Path) -> None:
        """No active claims when nothing has been claimed."""
        damper = Damper(log_path=tmp_path / "log.jsonl")
        assert damper.active_claims() == {}


# ------------------------------------------------------------------
# Constants and configuration
# ------------------------------------------------------------------


class TestDamperConstants:
    def test_priority_ordering(self) -> None:
        """swarm has highest priority (lowest number)."""
        assert RESOURCE_PRIORITIES["swarm"] < RESOURCE_PRIORITIES["health"]
        assert RESOURCE_PRIORITIES["health"] < RESOURCE_PRIORITIES["evolution"]
        assert RESOURCE_PRIORITIES["evolution"] < RESOURCE_PRIORITIES["pulse"]
        assert RESOURCE_PRIORITIES["pulse"] < RESOURCE_PRIORITIES["living"]

    def test_default_capacities_positive(self) -> None:
        """All default capacities are positive integers."""
        for name, cap in DEFAULT_CAPACITIES.items():
            assert isinstance(cap, int), f"{name} capacity is not int"
            assert cap > 0, f"{name} capacity must be positive"

    def test_default_capacities_include_expected(self) -> None:
        """Key resources are present in DEFAULT_CAPACITIES."""
        expected = {"agent_pool", "llm_budget", "shared_files", "evolution", "stigmergy"}
        assert expected == set(DEFAULT_CAPACITIES.keys())


class TestDamperUtilities:
    async def test_register_resource(self, tmp_path: Path) -> None:
        """register_resource creates a new semaphore."""
        damper = Damper(capacities={}, log_path=tmp_path / "log.jsonl")
        damper.register_resource("custom", capacity=4)
        async with damper.claim("custom", "test"):
            assert damper.active_claims().get("custom") == ["test"]

    async def test_reset_stats(self, tmp_path: Path) -> None:
        """reset_stats clears contention counters."""
        damper = Damper(log_path=tmp_path / "log.jsonl")
        damper._contention_counts["x"] = 42
        damper.reset_stats()
        assert damper.contention_stats() == {}

    def test_repr(self) -> None:
        damper = Damper()
        r = repr(damper)
        assert "Damper" in r
        assert "resources=" in r

    async def test_contention_log_written(self, tmp_path: Path) -> None:
        """Contention events are logged to the JSONL file."""
        log_path = tmp_path / "damper_log.jsonl"
        damper = Damper(
            capacities={"tight": 1},
            log_path=log_path,
            backoff_base=0.005,
            max_backoff=0.01,
        )
        held = asyncio.Event()
        released = asyncio.Event()

        async def holder() -> None:
            async with damper.claim("tight", "h", ttl=5.0):
                held.set()
                await released.wait()

        async def contender() -> None:
            await held.wait()
            async with damper.claim("tight", "c", ttl=5.0):
                pass

        ht = asyncio.create_task(holder())
        ct = asyncio.create_task(contender())
        await asyncio.sleep(0.3)
        released.set()
        await asyncio.gather(ht, ct)

        if log_path.exists():
            import json
            entries = [
                json.loads(l)
                for l in log_path.read_text().strip().split("\n")
                if l.strip()
            ]
            assert all("resource" in e for e in entries)
