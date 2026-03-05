"""Darwin Engine -- self-improvement orchestration loop.

Coordinates the full evolution cycle: propose mutations, gate-check them,
evaluate fitness, archive results, and select parents for the next generation.

Pipeline:
    PROPOSE -> GATE CHECK -> WRITE CODE -> TEST -> EVALUATE FITNESS -> ARCHIVE -> SELECT NEXT PARENT
"""

from __future__ import annotations

import logging
import re
import time
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from dharma_swarm.archive import ArchiveEntry, EvolutionArchive, FitnessScore
from dharma_swarm.elegance import evaluate_elegance
from dharma_swarm.fitness_predictor import FitnessPredictor, ProposalFeatures
from dharma_swarm.models import GateDecision, SandboxResult, _new_id, _utc_now
from dharma_swarm.selector import select_parent
from dharma_swarm.telos_gates import DEFAULT_GATEKEEPER
from dharma_swarm.traces import TraceEntry, TraceStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EvolutionStatus(str, Enum):
    """Lifecycle status of an evolution proposal."""

    PENDING = "pending"
    GATED = "gated"
    WRITING = "writing"
    TESTING = "testing"
    EVALUATED = "evaluated"
    ARCHIVED = "archived"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class Proposal(BaseModel):
    """A proposed code change to be evaluated by the Darwin Engine."""

    id: str = Field(default_factory=_new_id)
    component: str
    change_type: str  # "mutation", "crossover", "ablation"
    description: str
    parent_id: Optional[str] = None
    diff: str = ""
    status: EvolutionStatus = EvolutionStatus.PENDING
    predicted_fitness: float = 0.0
    actual_fitness: Optional[FitnessScore] = None
    gate_decision: Optional[str] = None
    gate_reason: Optional[str] = None


class CycleResult(BaseModel):
    """Summary of a single evolution cycle run."""

    cycle_id: str = Field(default_factory=_new_id)
    proposals_submitted: int = 0
    proposals_gated: int = 0
    proposals_tested: int = 0
    proposals_archived: int = 0
    best_fitness: float = 0.0
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Darwin Engine
# ---------------------------------------------------------------------------


class DarwinEngine:
    """Orchestrates the full evolution cycle.

    Creates proposals, runs them through dharmic safety gates, evaluates
    fitness, archives results, and selects parents for the next generation.

    Args:
        archive_path: Path to the JSONL evolution archive. Defaults to
            ``~/.dharma/evolution/archive.jsonl``.
        traces_path: Base path for the trace store. Defaults to
            ``~/.dharma/traces``.
        predictor_path: Path to the fitness predictor history file.
            Defaults to ``~/.dharma/evolution/predictor_data.jsonl``.
    """

    def __init__(
        self,
        archive_path: Path | None = None,
        traces_path: Path | None = None,
        predictor_path: Path | None = None,
    ) -> None:
        self.archive = EvolutionArchive(path=archive_path)
        self.traces = TraceStore(base_path=traces_path)
        self.predictor = FitnessPredictor(history_path=predictor_path)
        self._initialized: bool = False

    async def init(self) -> None:
        """Load archive, initialize traces, and load predictor history."""
        await self.archive.load()
        await self.traces.init()
        await self.predictor.load()
        self._initialized = True
        logger.info("DarwinEngine initialized")

    # -- proposal creation ---------------------------------------------------

    async def propose(
        self,
        component: str,
        change_type: str,
        description: str,
        diff: str = "",
        parent_id: str | None = None,
    ) -> Proposal:
        """Create a new evolution proposal and predict its fitness.

        Args:
            component: The module or file being changed.
            change_type: One of ``"mutation"``, ``"crossover"``, ``"ablation"``.
            description: Human-readable description of the change.
            diff: The code diff (patch text).
            parent_id: Optional archive entry id this proposal evolves from.

        Returns:
            A ``Proposal`` with predicted fitness populated.
        """
        features = ProposalFeatures(
            component=component,
            change_type=change_type,
            diff_size=len(diff.splitlines()),
        )
        predicted = self.predictor.predict(features)

        proposal = Proposal(
            component=component,
            change_type=change_type,
            description=description,
            diff=diff,
            parent_id=parent_id,
            predicted_fitness=predicted,
        )

        logger.debug(
            "Proposal %s created: predicted_fitness=%.3f",
            proposal.id,
            predicted,
        )
        return proposal

    # -- gate checking -------------------------------------------------------

    async def gate_check(self, proposal: Proposal) -> Proposal:
        """Run dharmic safety gates against a proposal.

        Updates the proposal status to ``GATED`` if the gates allow or
        advise review, or ``REJECTED`` if any gate blocks.

        Args:
            proposal: The proposal to gate-check.

        Returns:
            The same ``Proposal`` instance with updated status and gate fields.
        """
        result = DEFAULT_GATEKEEPER.check(
            action=proposal.description,
            content=proposal.diff,
        )

        proposal.gate_decision = result.decision.value
        proposal.gate_reason = result.reason

        if result.decision == GateDecision.BLOCK:
            proposal.status = EvolutionStatus.REJECTED
            logger.warning(
                "Proposal %s REJECTED by gates: %s",
                proposal.id,
                result.reason,
            )
        else:
            proposal.status = EvolutionStatus.GATED
            logger.info(
                "Proposal %s passed gates (%s): %s",
                proposal.id,
                result.decision.value,
                result.reason,
            )

        # Log trace for gate check
        await self.traces.log_entry(
            TraceEntry(
                agent="darwin_engine",
                action="gate_check",
                state=proposal.status.value,
                metadata={
                    "proposal_id": proposal.id,
                    "decision": result.decision.value,
                    "reason": result.reason,
                },
            )
        )

        return proposal

    # -- fitness evaluation --------------------------------------------------

    async def evaluate(
        self,
        proposal: Proposal,
        test_results: dict[str, Any] | None = None,
        code: str | None = None,
    ) -> Proposal:
        """Evaluate the fitness of a gated proposal.

        Builds a ``FitnessScore`` from test results, code elegance,
        gate outcomes, and diff efficiency.

        Args:
            proposal: The proposal to evaluate (should be GATED).
            test_results: Dict with test outcome data; key ``"pass_rate"``
                (float 0-1) is used for correctness.
            code: Optional Python source for elegance scoring.

        Returns:
            The proposal with ``actual_fitness`` populated and status
            set to ``EVALUATED``.
        """
        test_results = test_results or {}

        correctness = float(test_results.get("pass_rate", 0.0))

        if code:
            elegance_score = evaluate_elegance(code)
            elegance = elegance_score.overall
        else:
            elegance = 0.5

        # Dharmic alignment from gate outcome
        if proposal.gate_decision == GateDecision.ALLOW.value:
            dharmic_alignment = 0.8
        elif proposal.gate_decision == GateDecision.REVIEW.value:
            dharmic_alignment = 0.5
        else:
            dharmic_alignment = 0.0

        # Efficiency: smaller diffs are more efficient
        diff_lines = len(proposal.diff.splitlines()) if proposal.diff else 0
        efficiency = 1.0 - min(diff_lines / 1000.0, 1.0)

        # Safety: full marks if gate passed (not blocked)
        safety = 1.0 if proposal.status != EvolutionStatus.REJECTED else 0.0

        # Safety floor: if safety == 0, the entire composite fitness is 0
        # regardless of other scores. This enforces the invariant that
        # rejected proposals cannot accumulate fitness.
        if safety == 0.0:
            fitness = FitnessScore(
                correctness=0.0,
                elegance=0.0,
                dharmic_alignment=0.0,
                efficiency=0.0,
                safety=0.0,
            )
        else:
            fitness = FitnessScore(
                correctness=correctness,
                elegance=elegance,
                dharmic_alignment=dharmic_alignment,
                efficiency=efficiency,
                safety=safety,
            )

        proposal.actual_fitness = fitness
        proposal.status = EvolutionStatus.EVALUATED

        logger.info(
            "Proposal %s evaluated: weighted=%.3f",
            proposal.id,
            fitness.weighted(),
        )
        return proposal

    # -- archiving -----------------------------------------------------------

    async def archive_result(self, proposal: Proposal) -> str:
        """Store an evaluated proposal in the evolution archive.

        Creates an ``ArchiveEntry`` from the proposal, persists it,
        records the outcome in the fitness predictor, and logs a trace.

        Args:
            proposal: The evaluated proposal to archive.

        Returns:
            The archive entry id.
        """
        fitness = proposal.actual_fitness or FitnessScore()

        entry = ArchiveEntry(
            component=proposal.component,
            change_type=proposal.change_type,
            description=proposal.description,
            diff=proposal.diff,
            parent_id=proposal.parent_id,
            fitness=fitness,
            status="applied",
            gates_passed=(
                ["ALL"]
                if proposal.gate_decision != GateDecision.BLOCK.value
                else []
            ),
            gates_failed=(
                [proposal.gate_reason or "unknown"]
                if proposal.gate_decision == GateDecision.BLOCK.value
                else []
            ),
        )

        entry_id = await self.archive.add_entry(entry)
        proposal.status = EvolutionStatus.ARCHIVED

        # Record outcome in predictor for future predictions
        features = ProposalFeatures(
            component=proposal.component,
            change_type=proposal.change_type,
            diff_size=len(proposal.diff.splitlines()) if proposal.diff else 0,
        )
        await self.predictor.record_outcome(features, fitness.weighted())

        # Log trace
        await self.traces.log_entry(
            TraceEntry(
                agent="darwin_engine",
                action="archive_result",
                state="archived",
                metadata={
                    "proposal_id": proposal.id,
                    "entry_id": entry_id,
                    "weighted_fitness": fitness.weighted(),
                },
            )
        )

        logger.info(
            "Proposal %s archived as %s (fitness=%.3f)",
            proposal.id,
            entry_id,
            fitness.weighted(),
        )
        return entry_id

    # -- full cycle ----------------------------------------------------------

    async def run_cycle(self, proposals: list[Proposal]) -> CycleResult:
        """Execute a full evolution cycle on a batch of proposals.

        For each proposal: gate-check, and if it passes, evaluate and
        archive. Tracks aggregate statistics.

        Args:
            proposals: List of proposals to process.

        Returns:
            A ``CycleResult`` summarising the cycle.
        """
        start = time.monotonic()
        result = CycleResult(proposals_submitted=len(proposals))
        best_fitness = 0.0

        for proposal in proposals:
            # Gate check
            await self.gate_check(proposal)
            if proposal.status == EvolutionStatus.REJECTED:
                continue

            result.proposals_gated += 1

            # Evaluate
            await self.evaluate(proposal)
            result.proposals_tested += 1

            # Archive
            await self.archive_result(proposal)
            result.proposals_archived += 1

            # Track best
            if proposal.actual_fitness:
                weighted = proposal.actual_fitness.weighted()
                if weighted > best_fitness:
                    best_fitness = weighted

        result.best_fitness = best_fitness
        result.duration_seconds = time.monotonic() - start

        logger.info(
            "Cycle %s complete: %d submitted, %d gated, %d archived, "
            "best_fitness=%.3f, duration=%.2fs",
            result.cycle_id,
            result.proposals_submitted,
            result.proposals_gated,
            result.proposals_archived,
            result.best_fitness,
            result.duration_seconds,
        )
        return result

    # -- sandbox execution ---------------------------------------------------

    @staticmethod
    def _parse_sandbox_result(sr: SandboxResult) -> dict[str, Any]:
        """Parse pytest-style output from a sandbox result.

        Extracts pass/fail counts from stdout and computes a pass rate.
        Falls back to exit code when no recognisable pytest summary is found.

        Args:
            sr: The :class:`SandboxResult` to parse.

        Returns:
            Dict with ``"pass_rate"`` (float 0-1) and ``"exit_code"`` (int).
        """
        passed = 0
        failed = 0

        # Match patterns like "10 passed", "2 failed", "1 error"
        passed_match = re.search(r"(\d+)\s+passed", sr.stdout)
        failed_match = re.search(r"(\d+)\s+failed", sr.stdout)

        if passed_match:
            passed = int(passed_match.group(1))
        if failed_match:
            failed = int(failed_match.group(1))

        total = passed + failed
        if total > 0:
            pass_rate = passed / total
        else:
            # No recognisable test output; use exit code as heuristic
            pass_rate = 1.0 if sr.exit_code == 0 else 0.0

        return {"pass_rate": pass_rate, "exit_code": sr.exit_code}

    async def apply_in_sandbox(
        self,
        proposal: Proposal,
        test_command: str = "python3 -m pytest tests/ -q --tb=short",
        timeout: float = 60.0,
    ) -> tuple[Proposal, SandboxResult]:
        """Run a test command in a sandbox and record the result.

        Sets the proposal through WRITING -> TESTING status transitions,
        executes the command in a :class:`LocalSandbox`, and logs a trace.

        Args:
            proposal: The gated proposal to test.
            test_command: Shell command to run inside the sandbox.
            timeout: Maximum seconds before the command is killed.

        Returns:
            A tuple of ``(proposal, SandboxResult)``.
        """
        from dharma_swarm.sandbox import LocalSandbox

        proposal.status = EvolutionStatus.WRITING
        sandbox = LocalSandbox()
        try:
            proposal.status = EvolutionStatus.TESTING
            result = await sandbox.execute(test_command, timeout=timeout)

            # Log trace
            await self.traces.log_entry(
                TraceEntry(
                    agent="darwin_engine",
                    action="sandbox_test",
                    state=proposal.status.value,
                    metadata={
                        "proposal_id": proposal.id,
                        "exit_code": result.exit_code,
                        "stdout_preview": result.stdout[:200],
                    },
                )
            )
        finally:
            await sandbox.cleanup()

        return (proposal, result)

    async def run_cycle_with_sandbox(
        self,
        proposals: list[Proposal],
        test_command: str = "python3 -m pytest tests/ -q --tb=short",
        timeout: float = 60.0,
    ) -> CycleResult:
        """Execute a full evolution cycle with sandbox testing.

        Like :meth:`run_cycle`, but after gate-check each proposal is tested
        in a :class:`LocalSandbox` and the parsed test results are fed into
        the fitness evaluator.

        Args:
            proposals: List of proposals to process.
            test_command: Shell command for sandbox testing.
            timeout: Maximum seconds per sandbox execution.

        Returns:
            A :class:`CycleResult` summarising the cycle.
        """
        start = time.monotonic()
        result = CycleResult(proposals_submitted=len(proposals))
        best_fitness = 0.0

        for proposal in proposals:
            # Gate check
            await self.gate_check(proposal)
            if proposal.status == EvolutionStatus.REJECTED:
                continue

            result.proposals_gated += 1

            # Sandbox test
            proposal, sr = await self.apply_in_sandbox(
                proposal, test_command=test_command, timeout=timeout
            )
            test_results = self._parse_sandbox_result(sr)

            # Evaluate with sandbox results
            await self.evaluate(proposal, test_results=test_results)
            result.proposals_tested += 1

            # Archive
            await self.archive_result(proposal)
            result.proposals_archived += 1

            # Track best
            if proposal.actual_fitness:
                weighted = proposal.actual_fitness.weighted()
                if weighted > best_fitness:
                    best_fitness = weighted

        result.best_fitness = best_fitness
        result.duration_seconds = time.monotonic() - start

        logger.info(
            "Sandbox cycle %s complete: %d submitted, %d gated, %d archived, "
            "best_fitness=%.3f, duration=%.2fs",
            result.cycle_id,
            result.proposals_submitted,
            result.proposals_gated,
            result.proposals_archived,
            result.best_fitness,
            result.duration_seconds,
        )
        return result

    # -- parent selection ----------------------------------------------------

    async def select_next_parent(
        self, strategy: str = "tournament", **kwargs: Any
    ) -> ArchiveEntry | None:
        """Select a parent entry for the next evolution round.

        Delegates to the selector module's ``select_parent`` dispatch.

        Args:
            strategy: Selection strategy name (``"tournament"``,
                ``"roulette"``, ``"rank"``, ``"elite"``).
            **kwargs: Forwarded to the strategy function.

        Returns:
            An ``ArchiveEntry``, or ``None`` if the archive is empty.
        """
        return await select_parent(
            self.archive, strategy=strategy, **kwargs
        )

    # -- analytics -----------------------------------------------------------

    async def get_fitness_trend(
        self,
        component: str | None = None,
        limit: int = 20,
    ) -> list[tuple[str, float]]:
        """Return recent fitness trajectory from the archive.

        Args:
            component: Optional filter by component name.
            limit: Maximum number of data points to return.

        Returns:
            List of ``(timestamp, weighted_fitness)`` pairs, oldest first.
        """
        trajectory = self.archive.fitness_over_time(component=component)
        return trajectory[-limit:]
