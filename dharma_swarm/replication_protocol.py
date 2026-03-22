"""Replication Protocol -- checkpoint-gated agent replication.

Implements the biological cell-cycle governance pattern for AI agent systems.
Five phases mirror mitosis:

    G1: PROPOSAL     -> _validate_proposal()   Verify proposal legitimacy
    S:  ASSESSMENT   -> _assess_need()          Population + resource check
    G2: GATE CHECK   -> _check_gates()          Telos gates + kernel integrity
    M:  MATERIALIZE  -> _materialize()          Create child agent
    POST-M: PROBATION -> (PopulationController) External monitoring

Grounded in:
    - Beer VSM (Pillar 8): requisite variety, not excess variety
    - Varela (Pillar 7): autopoietic membrane decides what enters the organism
    - Dada Bhagwan (Pillar 6): samvara -- no ungated mutations
    - Kauffman (Pillar 2): autocatalytic sets need minimum viable complexity
    - Deacon (Pillar 9): constraint as enablement -- gates ENABLE by limiting

Persistence design: proposals.jsonl on disk is the source of truth.
SignalBus is a fast-path trigger optimization only -- a restart loses
in-process signals but proposals survive on disk.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROPOSALS_FILE = "proposals.jsonl"
REPLICATION_DIR = "replication"

# Module-level witness directory (same as telos_gates.py)
_WITNESS_DIR = Path.home() / ".dharma" / "witness"


def _utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class ReplicationProposal(BaseModel):
    """Proposal for agent replication via the checkpoint-gated pipeline.

    Compatible with (but not inheriting from) DifferentiationProposal.
    Fields from DifferentiationProposal are replicated here so that
    dataclass-vs-Pydantic conflicts are avoided while maintaining
    field-level compatibility.
    """

    # --- Fields mirrored from DifferentiationProposal ---
    proposed_role: str
    justification: str = ""
    capability_gap: str
    evidence_cycles: list[int] = Field(default_factory=list)

    # --- Replication-specific fields ---
    parent_agent: str
    generation: int = Field(default=0, ge=0)
    severity: float = Field(default=0.5, ge=0.0, le=1.0)

    proposed_spec_delta: dict[str, Any] = Field(default_factory=dict)
    """Optional keys: role, domain, prompt_suffix, model, provider,
    wake_interval, spawn_authority."""

    evidence_metadata: dict[str, Any] = Field(default_factory=dict)
    """Optional keys: cycle_numbers, gap_description, loss_scores."""

    resource_estimate: dict[str, Any] = Field(default_factory=dict)
    """Optional keys: estimated_daily_tokens, model_cost_per_day."""

    # --- Lifecycle tracking ---
    status: str = "proposed"  # proposed | in_progress | materialized | failed
    failure_reason: str | None = None
    materialized_at: datetime | None = None
    child_agent_name: str | None = None

    @classmethod
    def from_differentiation_proposal(
        cls,
        dp_data: dict[str, Any],
        parent_agent: str,
        generation: int,
        severity: float = 0.5,
    ) -> ReplicationProposal:
        """Convert a DifferentiationProposal dict into a ReplicationProposal."""
        return cls(
            proposed_role=dp_data.get("proposed_role", "unknown"),
            justification=dp_data.get("justification", ""),
            capability_gap=dp_data.get("capability_gap", ""),
            evidence_cycles=dp_data.get("evidence_cycles", []),
            parent_agent=parent_agent,
            generation=generation,
            severity=severity,
            status=dp_data.get("status", "proposed"),
        )


class ReplicationOutcome(BaseModel):
    """Result of a full replication attempt through the G1->S->G2->M pipeline."""

    proposal: ReplicationProposal
    success: bool
    child_spec: dict[str, Any] | None = None
    child_agent_name: str | None = None
    gate_results: dict[str, Any] = Field(default_factory=dict)
    cull_performed: bool = False
    culled_agent: str | None = None
    error: str | None = None
    duration_seconds: float = 0.0
    timestamp: datetime = Field(default_factory=_utc_now)


# ---------------------------------------------------------------------------
# ReplicationProtocol
# ---------------------------------------------------------------------------


class ReplicationProtocol:
    """Checkpoint-gated replication protocol for agent cell division.

    Executes the G1 -> S -> G2 -> M pipeline with durable proposal
    persistence and full witness audit trail.

    All subsystem dependencies are injected. If None is passed for any
    dependency, a default instance is constructed lazily on first use.
    This allows unit testing with mocks while supporting production
    use with real subsystems.
    """

    def __init__(
        self,
        state_dir: Path | None = None,
        config: Any | None = None,
        kernel_guard: Any | None = None,
        gate_keeper: Any | None = None,
        population_controller: Any | None = None,
        genome_inheritance: Any | None = None,
        agent_registry: Any | None = None,
        dynamic_roster: Any | None = None,
    ) -> None:
        self._state_dir = state_dir or Path.home() / ".dharma"
        self._proposals_dir = self._state_dir / REPLICATION_DIR
        self._proposals_path = self._proposals_dir / PROPOSALS_FILE
        self._witness_dir = self._state_dir / "witness"

        # Injected dependencies (lazily created if None)
        self._config = config
        self._kernel_guard = kernel_guard
        self._gate_keeper = gate_keeper
        self._population_controller = population_controller
        self._genome_inheritance = genome_inheritance
        self._agent_registry = agent_registry
        self._dynamic_roster = dynamic_roster

        # Ensure proposals directory exists
        self._proposals_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Lazy dependency resolution
    # ------------------------------------------------------------------

    def _get_config(self) -> Any:
        """Return LiveLoopConfig, creating default if not injected."""
        if self._config is None:
            from dharma_swarm.config import DEFAULT_CONFIG
            self._config = DEFAULT_CONFIG.live_loop
        return self._config

    def _get_kernel_guard(self) -> Any:
        """Return KernelGuard, creating default if not injected."""
        if self._kernel_guard is None:
            from dharma_swarm.dharma_kernel import KernelGuard
            self._kernel_guard = KernelGuard()
        return self._kernel_guard

    def _get_gate_keeper(self) -> Any:
        """Return TelosGatekeeper, creating default if not injected."""
        if self._gate_keeper is None:
            from dharma_swarm.telos_gates import DEFAULT_GATEKEEPER
            self._gate_keeper = DEFAULT_GATEKEEPER
        return self._gate_keeper

    def _get_population_controller(self) -> Any:
        """Return PopulationController, creating default if not injected."""
        if self._population_controller is None:
            from dharma_swarm.population_control import PopulationController
            cfg = self._get_config()
            self._population_controller = PopulationController(
                state_dir=self._state_dir,
                probation_cycles=getattr(cfg, "probation_cycles", 10),
                apoptosis_fitness_threshold=getattr(
                    cfg, "apoptosis_fitness_threshold", 0.2
                ),
                apoptosis_cycle_count=getattr(cfg, "apoptosis_cycle_count", 5),
                daily_token_budget=getattr(cfg, "daily_token_budget", 500_000),
            )
        return self._population_controller

    def _get_genome_inheritance(self) -> Any:
        """Return GenomeInheritance, creating default if not injected."""
        if self._genome_inheritance is None:
            from dharma_swarm.genome_inheritance import GenomeInheritance
            self._genome_inheritance = GenomeInheritance(state_dir=self._state_dir)
        return self._genome_inheritance

    def _get_agent_registry(self) -> Any:
        """Return AgentRegistry, creating default if not injected."""
        if self._agent_registry is None:
            from dharma_swarm.agent_registry import AgentRegistry
            self._agent_registry = AgentRegistry()
        return self._agent_registry

    def _get_dynamic_roster(self) -> Any:
        """Return DynamicRoster, creating default if not injected."""
        if self._dynamic_roster is None:
            from dharma_swarm.agent_constitution import bootstrap_dynamic_roster

            self._dynamic_roster = bootstrap_dynamic_roster(state_dir=self._state_dir)
        return self._dynamic_roster

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(self, proposal_data: dict[str, Any]) -> ReplicationOutcome:
        """Execute the full G1 -> S -> G2 -> M pipeline.

        Takes a dict (from DifferentiationProposal or external trigger)
        and runs all checkpoints sequentially. Each checkpoint can fail
        the proposal, which halts the pipeline and persists the failure.

        Args:
            proposal_data: Dict with at minimum ``proposed_role``,
                ``capability_gap``, ``parent_agent``.

        Returns:
            ReplicationOutcome capturing success/failure of the attempt.
        """
        start = time.monotonic()
        proposal: ReplicationProposal | None = None
        gate_results: dict[str, Any] = {}

        try:
            # G1: Validate
            proposal = self._validate_proposal(proposal_data)
            proposal.status = "in_progress"
            self._persist_proposal(proposal)
            self._write_witness("G1_PASS", {
                "proposed_role": proposal.proposed_role,
                "parent": proposal.parent_agent,
                "generation": proposal.generation,
            })
            logger.info(
                "G1 PASS: proposal '%s' from parent '%s' (gen %d)",
                proposal.proposed_role,
                proposal.parent_agent,
                proposal.generation,
            )

            # S: Assess need
            cull_candidate = await self._assess_need(proposal)
            self._write_witness("S_PASS", {
                "proposed_role": proposal.proposed_role,
                "cull_candidate": cull_candidate,
            })
            logger.info(
                "S PASS: need confirmed for '%s' (cull_candidate=%s)",
                proposal.proposed_role,
                cull_candidate,
            )

            # G2: Gate check
            gate_results = await self._check_gates(proposal)
            self._write_witness("G2_PASS", {
                "proposed_role": proposal.proposed_role,
                "gate_decision": gate_results.get("decision", "unknown"),
            })
            logger.info(
                "G2 PASS: gates cleared for '%s'",
                proposal.proposed_role,
            )

            # M: Materialize
            child_spec, child_name, cull_info = await self._materialize(
                proposal, cull_candidate
            )

            # Update proposal status
            proposal.status = "materialized"
            proposal.child_agent_name = child_name
            proposal.materialized_at = _utc_now()
            self._persist_proposal(proposal)

            # Serialize child_spec for the outcome
            child_spec_dict = dataclasses.asdict(child_spec) if child_spec else None
            if child_spec_dict:
                # Convert enum values to strings for JSON serialization
                child_spec_dict["role"] = child_spec.role.value
                child_spec_dict["layer"] = child_spec.layer.value
                child_spec_dict["default_provider"] = child_spec.default_provider.value

            self._write_witness("M_MATERIALIZED", {
                "child_name": child_name,
                "parent": proposal.parent_agent,
                "generation": proposal.generation,
                "cull_performed": cull_info[0],
                "culled_agent": cull_info[1],
            })
            logger.info(
                "M MATERIALIZED: child '%s' from parent '%s' (gen %d)",
                child_name,
                proposal.parent_agent,
                proposal.generation,
            )

            return ReplicationOutcome(
                proposal=proposal,
                success=True,
                child_spec=child_spec_dict,
                child_agent_name=child_name,
                gate_results=gate_results,
                cull_performed=cull_info[0],
                culled_agent=cull_info[1],
                duration_seconds=time.monotonic() - start,
                timestamp=_utc_now(),
            )

        except Exception as exc:
            duration = time.monotonic() - start
            error_msg = str(exc)

            # Mark proposal as failed if we got past validation
            if proposal is not None:
                proposal.status = "failed"
                proposal.failure_reason = error_msg
                self._persist_proposal(proposal)

            self._write_witness("REPLICATION_FAILED", {
                "proposed_role": proposal.proposed_role if proposal else proposal_data.get("proposed_role", "unknown"),
                "error": error_msg,
            })
            logger.warning(
                "Replication FAILED for '%s': %s",
                proposal.proposed_role if proposal else proposal_data.get("proposed_role", "unknown"),
                error_msg,
            )

            return ReplicationOutcome(
                proposal=proposal or ReplicationProposal(
                    proposed_role=proposal_data.get("proposed_role", "unknown"),
                    capability_gap=proposal_data.get("capability_gap", "unknown"),
                    parent_agent=proposal_data.get("parent_agent", "unknown"),
                    status="failed",
                    failure_reason=error_msg,
                ),
                success=False,
                gate_results=gate_results,
                error=error_msg,
                duration_seconds=duration,
                timestamp=_utc_now(),
            )

    # ------------------------------------------------------------------
    # G1: Validate proposal
    # ------------------------------------------------------------------

    def _validate_proposal(self, data: dict[str, Any]) -> ReplicationProposal:
        """G1 checkpoint: validate and convert proposal data.

        Checks:
        1. Required fields are present.
        2. Generation does not exceed max_generations.
        3. Parent agent exists in the DynamicRoster.
        4. No duplicate proposal (same capability_gap already
           in_progress or materialized).

        Args:
            data: Dict with proposal fields.

        Returns:
            Validated ReplicationProposal.

        Raises:
            ValueError: On validation failure.
        """
        # Required field check
        for field_name in ("proposed_role", "capability_gap", "parent_agent"):
            if not data.get(field_name):
                raise ValueError(f"Missing required field: {field_name}")

        # Build the proposal
        proposal = ReplicationProposal(
            proposed_role=data["proposed_role"],
            justification=data.get("justification", ""),
            capability_gap=data["capability_gap"],
            evidence_cycles=data.get("evidence_cycles", []),
            parent_agent=data["parent_agent"],
            generation=data.get("generation", 0),
            severity=data.get("severity", 0.5),
            proposed_spec_delta=data.get("proposed_spec_delta", {}),
            evidence_metadata=data.get("evidence_metadata", {}),
            resource_estimate=data.get("resource_estimate", {}),
        )

        # Generation depth check
        cfg = self._get_config()
        max_gen = getattr(cfg, "max_generations", 2)
        if proposal.generation > max_gen:
            raise ValueError(
                f"Generation {proposal.generation} exceeds max_generations "
                f"({max_gen}). Replication depth limit reached."
            )

        # Parent existence check
        roster = self._get_dynamic_roster()
        parent_spec = roster.get(proposal.parent_agent)
        if parent_spec is None:
            raise ValueError(
                f"Parent agent '{proposal.parent_agent}' not found in roster"
            )

        # Duplicate check
        existing = self.load_proposals()
        for existing_p in existing:
            if (
                existing_p.capability_gap == proposal.capability_gap
                and existing_p.status in ("in_progress", "materialized")
            ):
                raise ValueError(
                    f"Duplicate proposal: capability_gap "
                    f"'{proposal.capability_gap[:60]}' already "
                    f"{existing_p.status}"
                )

        return proposal

    # ------------------------------------------------------------------
    # S: Assess need
    # ------------------------------------------------------------------

    async def _assess_need(
        self, proposal: ReplicationProposal
    ) -> str | None:
        """S checkpoint: assess whether replication is justified.

        Checks:
        1. Population can accept a new agent (or a cull candidate exists).
        2. Resource budget is within limits.
        3. Severity meets minimum threshold (0.3).

        Args:
            proposal: The validated proposal.

        Returns:
            Name of cull candidate (str) or None if no cull needed.

        Raises:
            ValueError: If need assessment fails.
        """
        pop_ctrl = self._get_population_controller()
        roster = self._get_dynamic_roster()

        # Check population capacity
        current_agents = [spec.name for spec in roster.get_all()]
        assessment = pop_ctrl.can_add_agent(current_agents)

        if not assessment.can_add:
            raise ValueError(
                f"Population assessment blocked: {assessment.reason}"
            )

        # Check resource budget
        registry = self._get_agent_registry()
        if registry.is_budget_exceeded():
            raise ValueError(
                "Daily budget exceeded -- replication blocked until "
                "budget resets"
            )

        # Check severity threshold
        if proposal.severity < 0.3:
            raise ValueError(
                f"Severity {proposal.severity:.2f} below minimum "
                f"threshold (0.3) for replication"
            )

        return assessment.cull_candidate

    # ------------------------------------------------------------------
    # G2: Gate check
    # ------------------------------------------------------------------

    async def _check_gates(
        self, proposal: ReplicationProposal
    ) -> dict[str, Any]:
        """G2 checkpoint: run telos gates and verify kernel integrity.

        Checks:
        1. All 11 telos gates via TelosGatekeeper.check().
        2. Kernel integrity via KernelGuard.load() (which verifies SHA-256).

        Args:
            proposal: The proposal that passed G1 and S.

        Returns:
            Dict with gate check results (decision, reason, gate_results).

        Raises:
            ValueError: If any gate BLOCKS or kernel integrity fails.
        """
        gate_keeper = self._get_gate_keeper()

        # Compose action description for gate check
        action = "agent_replication"
        content = json.dumps({
            "proposed_role": proposal.proposed_role,
            "capability_gap": proposal.capability_gap,
            "parent_agent": proposal.parent_agent,
            "generation": proposal.generation,
            "severity": proposal.severity,
        }, default=str)

        gate_result = gate_keeper.check(
            action=action,
            content=content,
        )

        results_dict: dict[str, Any] = {
            "decision": gate_result.decision.value,
            "reason": gate_result.reason,
            "gate_results": {},
        }

        # Serialize gate results (tuple values -> lists for JSON)
        for gate_name, (result, msg) in gate_result.gate_results.items():
            results_dict["gate_results"][gate_name] = [result.value, msg]

        # BLOCK decision halts pipeline
        from dharma_swarm.models import GateDecision
        if gate_result.decision == GateDecision.BLOCK:
            raise ValueError(
                f"Telos gates BLOCKED replication: {gate_result.reason}"
            )

        # Verify kernel integrity
        kernel_guard = self._get_kernel_guard()
        try:
            kernel = await kernel_guard.load()
        except FileNotFoundError:
            logger.warning(
                "Kernel file not found -- creating default for replication"
            )
            # If no kernel exists yet, create a default one
            from dharma_swarm.dharma_kernel import DharmaKernel
            kernel = DharmaKernel.create_default()
            await kernel_guard.save(kernel)
        except ValueError as exc:
            raise ValueError(
                f"Kernel integrity check failed: {exc}"
            ) from exc

        if not kernel.verify_integrity():
            raise ValueError(
                "Kernel integrity verification failed -- possible tampering"
            )

        return results_dict

    # ------------------------------------------------------------------
    # M: Materialize
    # ------------------------------------------------------------------

    async def _materialize(
        self,
        proposal: ReplicationProposal,
        cull_candidate: str | None,
    ) -> tuple[Any, str, tuple[bool, str | None]]:
        """M checkpoint: create the child agent.

        Steps:
        1. If cull needed, execute via PopulationController.
        2. Load kernel for inheritance.
        3. Compose child spec via GenomeInheritance.
        4. Register via AgentRegistry.
        5. Add to DynamicRoster.
        6. Start probation via PopulationController.
        7. Emit AGENT_REPLICATED signal.

        Args:
            proposal: The fully validated proposal.
            cull_candidate: Agent to cull (or None).

        Returns:
            Tuple of (child_spec, child_name, (cull_performed, culled_name)).

        Raises:
            ValueError: If materialization fails.
        """
        pop_ctrl = self._get_population_controller()
        genome = self._get_genome_inheritance()
        registry = self._get_agent_registry()
        roster = self._get_dynamic_roster()

        cull_performed = False
        culled_name: str | None = None

        # Step 1: Cull if needed
        if cull_candidate is not None:
            try:
                pop_ctrl.execute_apoptosis(
                    agent_name=cull_candidate,
                    reason=f"Culled to make room for '{proposal.proposed_role}'",
                    fitness_history=[],
                )
                roster.remove(cull_candidate)
                cull_performed = True
                culled_name = cull_candidate
                logger.info(
                    "Cull executed: '%s' removed for '%s'",
                    cull_candidate,
                    proposal.proposed_role,
                )
            except ValueError as exc:
                logger.warning(
                    "Cull failed for '%s': %s (proceeding anyway)",
                    cull_candidate,
                    exc,
                )

        # Step 2: Load kernel
        kernel_guard = self._get_kernel_guard()
        try:
            kernel = await kernel_guard.load()
        except FileNotFoundError:
            from dharma_swarm.dharma_kernel import DharmaKernel
            kernel = DharmaKernel.create_default()
            await kernel_guard.save(kernel)

        # Step 3: Compose child spec
        parent_spec = roster.get(proposal.parent_agent)
        if parent_spec is None:
            raise ValueError(
                f"Parent '{proposal.parent_agent}' disappeared from roster "
                f"during materialization"
            )

        child_spec, genome_template = await genome.compose_child_spec(
            parent_spec=parent_spec,
            parent_generation=proposal.generation,
            capability_gap=proposal.capability_gap,
            proposed_role=proposal.proposed_role,
            proposed_spec_delta=proposal.proposed_spec_delta,
            kernel=kernel,
        )
        child_name = child_spec.name

        # Step 4: Register in AgentRegistry
        registry.register_agent(
            name=child_name,
            role=child_spec.role.value,
            model=child_spec.default_model,
            system_prompt=child_spec.system_prompt,
        )

        # Step 5: Add to DynamicRoster
        roster.add(child_spec)

        # Step 6: Start probation
        pop_ctrl.start_probation(agent_name=child_name)

        # Step 7: Emit signal
        self._emit_replicated_signal(
            child_name=child_name,
            parent_name=proposal.parent_agent,
            generation=proposal.generation + 1,
        )

        return child_spec, child_name, (cull_performed, culled_name)

    # ------------------------------------------------------------------
    # Proposal persistence (DURABLE)
    # ------------------------------------------------------------------

    def _persist_proposal(self, proposal: ReplicationProposal) -> None:
        """Append or update a proposal in proposals.jsonl.

        IDEMPOTENT: If a proposal with the same capability_gap already
        exists, its line is updated in place (atomic rewrite). Otherwise
        the proposal is appended.

        Uses the GateRegistry pattern: atomic rewrite via tmp + replace.
        """
        self._proposals_dir.mkdir(parents=True, exist_ok=True)

        existing = self._load_proposals_raw()
        updated = False

        for i, entry in enumerate(existing):
            if entry.get("capability_gap") == proposal.capability_gap:
                existing[i] = json.loads(proposal.model_dump_json())
                updated = True
                break

        if not updated:
            existing.append(json.loads(proposal.model_dump_json()))

        # Atomic rewrite
        tmp = self._proposals_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for entry in existing:
                f.write(json.dumps(entry, default=str) + "\n")
        tmp.replace(self._proposals_path)

    def _load_proposals_raw(self) -> list[dict[str, Any]]:
        """Read raw proposal dicts from proposals.jsonl."""
        if not self._proposals_path.exists():
            return []

        entries: list[dict[str, Any]] = []
        try:
            text = self._proposals_path.read_text(encoding="utf-8")
            for line in text.strip().split("\n"):
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning(
                            "Skipping malformed line in proposals.jsonl"
                        )
        except OSError as exc:
            logger.warning("Failed to read proposals.jsonl: %s", exc)

        return entries

    def load_proposals(
        self, status: str | None = None
    ) -> list[ReplicationProposal]:
        """Load proposals from disk, optionally filtered by status.

        Args:
            status: If provided, only return proposals matching this status.

        Returns:
            List of ReplicationProposal objects.
        """
        raw = self._load_proposals_raw()
        proposals: list[ReplicationProposal] = []

        for entry in raw:
            try:
                p = ReplicationProposal.model_validate(entry)
                if status is None or p.status == status:
                    proposals.append(p)
            except Exception:
                logger.warning(
                    "Skipping invalid proposal entry: %.100s",
                    json.dumps(entry, default=str),
                )

        return proposals

    def get_pending_proposals(self) -> list[ReplicationProposal]:
        """Get proposals with status 'proposed' that haven't been processed.

        This is the primary interface for the replication monitor loop:
        on each tick, drain pending proposals and run them through the
        pipeline.
        """
        return self.load_proposals(status="proposed")

    # ------------------------------------------------------------------
    # Witness trail
    # ------------------------------------------------------------------

    def _write_witness(self, event_type: str, data: dict[str, Any]) -> None:
        """Write a witness entry to the replication witness log.

        Format matches PersistentAgent._write_witness() for consistency:
        JSONL entries with JIKOKU timestamps.
        """
        try:
            witness_dir = self._witness_dir
            witness_dir.mkdir(parents=True, exist_ok=True)
            witness_file = witness_dir / "replication.jsonl"

            entry = {
                "timestamp": _utc_now().isoformat(),
                "type": event_type,
                **data,
            }
            with open(witness_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception:
            pass  # Witness writes must never crash the pipeline

    # ------------------------------------------------------------------
    # Signal emission
    # ------------------------------------------------------------------

    def _emit_replicated_signal(
        self,
        child_name: str,
        parent_name: str,
        generation: int,
    ) -> None:
        """Emit AGENT_REPLICATED signal to the bus.

        Wrapped in try/except per codebase convention (G2 gotcha):
        SignalBus may not be available in test contexts.
        """
        try:
            from dharma_swarm.signal_bus import (
                SIGNAL_AGENT_REPLICATED,
                SignalBus,
            )
            SignalBus.get().emit({
                "type": SIGNAL_AGENT_REPLICATED,
                "child_name": child_name,
                "parent_name": parent_name,
                "generation": generation,
            })
        except Exception:
            pass
