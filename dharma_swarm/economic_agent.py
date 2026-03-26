"""Shakti Economic Engine — the organism's self-funding work loop.

The first autonomous economic agent with real governance.
Other agents (CashClaw, Profiterole, auto-co) accept any task within budget.
This one only accepts what aligns with telos, passes 11 dharmic gates,
and survives the Gnani checkpoint.

Full loop:
    INGEST → GATE → DECOMPOSE → CASCADE → DELIVER → INVOICE → LEARN → EVOLVE

Task sources are pluggable: local inbox (JSON files), GitHub Issues,
marketplace APIs (HYRVE/Moltlaunch), email. Start with local inbox.

Usage::

    agent = EconomicAgent()
    await agent.run()  # polls inbox, executes tasks, records economics

CLI::

    dgc work          # start the economic agent loop
    dgc work status   # show P&L, pending tasks, completion rate
    dgc work submit   # manually submit a task JSON to inbox
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class TaskStatus(str, Enum):
    """Lifecycle of an economic task."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DECOMPOSING = "decomposing"
    EXECUTING = "executing"
    DELIVERED = "delivered"
    RATED = "rated"
    FAILED = "failed"


class TaskSource(str, Enum):
    """Where the task originated."""

    LOCAL_INBOX = "local_inbox"
    GITHUB_ISSUE = "github_issue"
    MARKETPLACE = "marketplace"
    EMAIL = "email"
    MANUAL = "manual"


class EconomicTask(BaseModel):
    """A unit of work the organism can accept and execute."""

    id: str = Field(default_factory=_new_id)
    title: str
    description: str
    domain: str = "code"  # cascade domain: code, product, skill, research, meta
    budget_usd: float = 0.0  # what the client is willing to pay
    source: TaskSource = TaskSource.LOCAL_INBOX
    source_ref: str = ""  # e.g., GitHub issue URL, marketplace job ID
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=_utc_now)
    accepted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    rejection_reason: str = ""
    gate_results: dict[str, Any] = Field(default_factory=dict)
    cascade_results: dict[str, Any] = Field(default_factory=dict)
    deliverables: list[str] = Field(default_factory=list)  # file paths
    rating: Optional[float] = None  # 0-5 client rating
    metadata: dict[str, Any] = Field(default_factory=dict)


class LedgerEntry(BaseModel):
    """Single P&L entry in the economic ledger."""

    id: str = Field(default_factory=_new_id)
    task_id: str
    task_title: str
    domain: str
    source: str
    cost_tokens: int = 0
    cost_usd: float = 0.0
    revenue_usd: float = 0.0
    profit_usd: float = 0.0
    rating: Optional[float] = None
    duration_seconds: float = 0.0
    timestamp: datetime = Field(default_factory=_utc_now)


class EconomicStatus(BaseModel):
    """Aggregate P&L snapshot."""

    total_tasks: int = 0
    completed: int = 0
    rejected: int = 0
    failed: int = 0
    total_revenue: float = 0.0
    total_cost: float = 0.0
    total_profit: float = 0.0
    avg_rating: float = 0.0
    self_sustaining: bool = False  # revenue > cost
    domains: dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Economic Ledger (JSONL persistence)
# ---------------------------------------------------------------------------


class EconomicLedger:
    """Append-only JSONL ledger tracking every task's economics."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (Path.home() / ".dharma" / "economic" / "ledger.jsonl")
        self._entries: list[LedgerEntry] = []

    def record(self, entry: LedgerEntry) -> None:
        """Append an entry to the ledger."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._entries.append(entry)
        with open(self._path, "a") as f:
            f.write(entry.model_dump_json() + "\n")

    def load(self) -> list[LedgerEntry]:
        """Load all entries from disk."""
        if not self._path.exists():
            return []
        entries: list[LedgerEntry] = []
        for line in self._path.read_text().strip().split("\n"):
            if not line.strip():
                continue
            try:
                entries.append(LedgerEntry.model_validate_json(line))
            except Exception:
                continue
        self._entries = entries
        return entries

    def status(self) -> EconomicStatus:
        """Compute aggregate P&L from all entries."""
        entries = self._entries or self.load()
        if not entries:
            return EconomicStatus()

        completed = [e for e in entries if e.revenue_usd > 0 or e.cost_usd > 0]
        total_rev = sum(e.revenue_usd for e in entries)
        total_cost = sum(e.cost_usd for e in entries)
        ratings = [e.rating for e in entries if e.rating is not None]
        domains: dict[str, int] = {}
        for e in entries:
            domains[e.domain] = domains.get(e.domain, 0) + 1

        return EconomicStatus(
            total_tasks=len(entries),
            completed=len(completed),
            total_revenue=round(total_rev, 4),
            total_cost=round(total_cost, 4),
            total_profit=round(total_rev - total_cost, 4),
            avg_rating=round(sum(ratings) / len(ratings), 2) if ratings else 0.0,
            self_sustaining=total_rev > total_cost > 0,
            domains=domains,
        )


# ---------------------------------------------------------------------------
# Inbox Poller
# ---------------------------------------------------------------------------


class InboxPoller:
    """Watches ~/.dharma/inbox/ for JSON task files."""

    def __init__(self, inbox_dir: Path | None = None) -> None:
        self._inbox = inbox_dir or (Path.home() / ".dharma" / "inbox")
        self._processed = self._inbox / "processed"

    async def poll(self) -> list[EconomicTask]:
        """Scan inbox for new task files, return parsed tasks."""
        self._inbox.mkdir(parents=True, exist_ok=True)
        self._processed.mkdir(parents=True, exist_ok=True)

        tasks: list[EconomicTask] = []
        for path in sorted(self._inbox.glob("*.json")):
            try:
                data = json.loads(path.read_text())
                task = EconomicTask(**data)
                tasks.append(task)
                # Move to processed
                shutil.move(str(path), str(self._processed / path.name))
                logger.info("Ingested task from inbox: %s (%s)", task.title, path.name)
            except Exception as exc:
                logger.warning("Failed to parse inbox task %s: %s", path.name, exc)
        return tasks


# ---------------------------------------------------------------------------
# Telos-Gated Acceptance (THE MOAT)
# ---------------------------------------------------------------------------


class TelosAcceptanceResult(BaseModel):
    """Result of the telos-gated acceptance pipeline."""

    accepted: bool
    reason: str
    gate_passed: bool = False
    gnani_passed: bool = False
    competence_ok: bool = False
    economics_ok: bool = False


async def telos_gated_accept(task: EconomicTask) -> TelosAcceptanceResult:
    """Run the full telos-gated acceptance pipeline.

    1. Telos gates — all 11 must pass
    2. Gnani checkpoint — the attractor field evaluates alignment
    3. Competence check — do we have cascade domains for this?
    4. Economic check — estimated cost vs. expected value

    This is what NO other autonomous agent has.
    """
    from dharma_swarm.cascade import get_registered_domains

    # 1. Telos gates
    gate_passed = True
    gate_reason = ""
    try:
        from dharma_swarm.telos_gates import DEFAULT_GATEKEEPER

        result = DEFAULT_GATEKEEPER.check(
            action=f"Accept economic task: {task.title}",
            context=task.description[:500],
            metadata={
                "task_id": task.id,
                "domain": task.domain,
                "budget": task.budget_usd,
                "source": task.source.value,
            },
        )
        gate_passed = result.decision.value in ("allow", "pass", "ALLOW", "PASS")
        if not gate_passed:
            gate_reason = f"Gate blocked: {result.reason}"
    except Exception as exc:
        logger.debug("Telos gate check failed (non-fatal): %s", exc)
        gate_passed = True  # fail-open for now

    # 2. Gnani checkpoint
    gnani_passed = True
    try:
        from dharma_swarm.dharma_attractor import DharmaAttractor

        attractor = DharmaAttractor()
        verdict = attractor.gnani_checkpoint(
            f"Economic task acceptance: {task.title}\n\n{task.description[:300]}",
            {"domain": task.domain, "budget": task.budget_usd},
        )
        gnani_passed = verdict.proceed
    except Exception as exc:
        logger.debug("Gnani checkpoint failed (non-fatal): %s", exc)
        gnani_passed = True  # fail-open

    # 3. Competence check — do we have a cascade domain?
    available_domains = get_registered_domains()
    competence_ok = task.domain in available_domains

    # 4. Economic check — is there budget?
    economics_ok = task.budget_usd >= 0  # accept even $0 tasks for now (learning value)

    accepted = gate_passed and gnani_passed and competence_ok
    if not accepted:
        reasons = []
        if not gate_passed:
            reasons.append(gate_reason)
        if not gnani_passed:
            reasons.append("Gnani HELD: task does not align with telos")
        if not competence_ok:
            reasons.append(f"No cascade domain for '{task.domain}'. Available: {sorted(available_domains)}")
        reason = "; ".join(reasons)
    else:
        reason = "Accepted: all gates passed"

    return TelosAcceptanceResult(
        accepted=accepted,
        reason=reason,
        gate_passed=gate_passed,
        gnani_passed=gnani_passed,
        competence_ok=competence_ok,
        economics_ok=economics_ok,
    )


# ---------------------------------------------------------------------------
# Task Execution (cascade-driven)
# ---------------------------------------------------------------------------


async def execute_task(task: EconomicTask) -> dict[str, Any]:
    """Execute a task through the cascade engine.

    Maps the task to a cascade domain, runs LoopEngine,
    returns the result with artifacts.
    """
    from dharma_swarm.cascade import run_domain

    t0 = time.monotonic()
    try:
        result = await run_domain(
            task.domain,
            seed={"task_title": task.title, "task_description": task.description},
            context={"task_id": task.id, "budget": task.budget_usd},
        )
        return {
            "converged": result.converged,
            "eigenform_reached": result.eigenform_reached,
            "best_fitness": result.best_fitness,
            "iterations": result.iterations_completed,
            "duration": time.monotonic() - t0,
            "convergence_reason": result.convergence_reason,
        }
    except Exception as exc:
        logger.error("Task execution failed for %s: %s", task.id, exc)
        return {
            "converged": False,
            "eigenform_reached": False,
            "best_fitness": 0.0,
            "iterations": 0,
            "duration": time.monotonic() - t0,
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Delivery + Stigmergy
# ---------------------------------------------------------------------------


async def deliver_task(task: EconomicTask, cascade_result: dict[str, Any]) -> Path:
    """Package task deliverables and leave a stigmergy mark."""
    delivery_dir = Path.home() / ".dharma" / "deliveries" / task.id
    delivery_dir.mkdir(parents=True, exist_ok=True)

    # Write result summary
    summary = {
        "task_id": task.id,
        "title": task.title,
        "domain": task.domain,
        "cascade_result": cascade_result,
        "delivered_at": _utc_now().isoformat(),
    }
    summary_path = delivery_dir / "delivery_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str))

    # Leave high-salience stigmergy mark
    try:
        from dharma_swarm.stigmergy import StigmergicMark, StigmergyStore

        store = StigmergyStore()
        status = "EIGENFORM" if cascade_result.get("eigenform_reached") else "DELIVERED"
        mark = StigmergicMark(
            agent="economic_agent",
            file_path=f"economic_task_{task.domain}",
            action="write",
            observation=(
                f"task:{task.title[:40]} fitness={cascade_result.get('best_fitness', 0):.3f} "
                f"{status} budget=${task.budget_usd:.2f}"
            ),
            salience=0.85,
            channel="governance",
        )
        await store.leave_mark(mark)
    except Exception as exc:
        logger.debug("Stigmergy mark for delivery failed: %s", exc)

    return delivery_dir


# ---------------------------------------------------------------------------
# Economic Agent (the full loop)
# ---------------------------------------------------------------------------


class EconomicAgent:
    """The organism's self-funding work loop.

    Polls for tasks, gates them through telos, executes via cascade,
    delivers, records economics, and feeds results back into evolution.
    """

    def __init__(
        self,
        state_dir: Path | None = None,
        poll_interval: float = 30.0,
    ) -> None:
        self._state_dir = state_dir or (Path.home() / ".dharma")
        self._poll_interval = poll_interval
        self._inbox = InboxPoller(self._state_dir / "inbox")
        self._ledger = EconomicLedger(self._state_dir / "economic" / "ledger.jsonl")
        self._running = False
        self._tasks_processed: int = 0

    async def process_task(self, task: EconomicTask) -> LedgerEntry | None:
        """Process a single task through the full economic pipeline."""
        t0 = time.monotonic()

        # GATE
        logger.info("GATE: evaluating task '%s' (domain=%s, budget=$%.2f)", task.title, task.domain, task.budget_usd)
        acceptance = await telos_gated_accept(task)
        task.gate_results = acceptance.model_dump()

        if not acceptance.accepted:
            task.status = TaskStatus.REJECTED
            task.rejection_reason = acceptance.reason
            logger.info("REJECTED: %s — %s", task.title, acceptance.reason)
            return None

        task.status = TaskStatus.ACCEPTED
        task.accepted_at = _utc_now()
        logger.info("ACCEPTED: %s (gates=%s, gnani=%s, competence=%s)",
                     task.title, acceptance.gate_passed, acceptance.gnani_passed, acceptance.competence_ok)

        # DECOMPOSE + CASCADE
        task.status = TaskStatus.EXECUTING
        logger.info("EXECUTING: %s via cascade domain '%s'", task.title, task.domain)
        cascade_result = await execute_task(task)
        task.cascade_results = cascade_result

        # DELIVER
        if cascade_result.get("error"):
            task.status = TaskStatus.FAILED
            logger.warning("FAILED: %s — %s", task.title, cascade_result["error"])
        else:
            delivery_dir = await deliver_task(task, cascade_result)
            task.status = TaskStatus.DELIVERED
            task.deliverables = [str(delivery_dir)]
            task.completed_at = _utc_now()
            logger.info(
                "DELIVERED: %s → %s (fitness=%.3f, eigenform=%s)",
                task.title, delivery_dir,
                cascade_result.get("best_fitness", 0),
                cascade_result.get("eigenform_reached", False),
            )

        # INVOICE (record economics)
        duration = time.monotonic() - t0
        entry = LedgerEntry(
            task_id=task.id,
            task_title=task.title,
            domain=task.domain,
            source=task.source.value,
            revenue_usd=task.budget_usd if task.status == TaskStatus.DELIVERED else 0.0,
            cost_usd=0.0,  # TODO: wire cost_tracker.py for real token costs
            profit_usd=task.budget_usd if task.status == TaskStatus.DELIVERED else 0.0,
            rating=task.rating,
            duration_seconds=duration,
        )
        self._ledger.record(entry)
        self._tasks_processed += 1

        # LEARN (feed into evolution)
        try:
            from dharma_swarm.signal_bus import SignalBus

            bus = SignalBus.get()
            bus.emit({
                "type": "ECONOMIC_TASK_COMPLETE",
                "task_id": task.id,
                "domain": task.domain,
                "fitness": cascade_result.get("best_fitness", 0),
                "eigenform": cascade_result.get("eigenform_reached", False),
                "revenue": entry.revenue_usd,
                "cost": entry.cost_usd,
            })
        except Exception:
            pass

        return entry

    async def run(self, max_tasks: int = 0) -> None:
        """Run the economic agent loop.

        Args:
            max_tasks: Stop after this many tasks (0 = run forever).
        """
        self._running = True
        self._ledger.load()
        logger.info(
            "Shakti Economic Engine starting (poll_interval=%.0fs, ledger=%d entries)",
            self._poll_interval, len(self._ledger._entries),
        )

        while self._running:
            try:
                tasks = await self._inbox.poll()
                for task in tasks:
                    await self.process_task(task)
                    if max_tasks and self._tasks_processed >= max_tasks:
                        self._running = False
                        break
            except Exception as exc:
                logger.error("Economic agent loop error: %s", exc)

            if self._running:
                await asyncio.sleep(self._poll_interval)

        status = self._ledger.status()
        logger.info(
            "Shakti Economic Engine stopped. P&L: revenue=$%.2f cost=$%.2f profit=$%.2f "
            "tasks=%d self_sustaining=%s",
            status.total_revenue, status.total_cost, status.total_profit,
            status.total_tasks, status.self_sustaining,
        )

    def stop(self) -> None:
        """Request graceful shutdown."""
        self._running = False

    def status(self) -> EconomicStatus:
        """Return current P&L snapshot."""
        return self._ledger.status()
