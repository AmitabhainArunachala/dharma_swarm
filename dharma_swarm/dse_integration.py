"""DSE integration: wires monad, coalgebra, and sheaf into the live runtime.

This module is the seam between the theoretical DSE layers and the
operational swarm.  It:

1. Converts evolution observations into sheaf ``Discovery`` objects.
2. Publishes them into a ``CoordinationProtocol``.
3. Runs Čech cohomology to separate global truths from productive
   disagreements (H¹ obstructions backed by Anekanta).
4. Feeds coordination results back to the DarwinEngine so future
   cycles can incorporate collective intelligence.
5. Tracks the observation stream for fixed-point convergence (L5).

Usage::

    integrator = DSEIntegrator(engine, swarm_manager)
    await integrator.after_cycle(result, proposals)
    # Call this from evolution.py after each run_cycle().

All failures are non-fatal — the integrator never blocks the core pipeline.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from pydantic import BaseModel, Field

from dharma_swarm.archive import ArchiveEntry
from dharma_swarm.coalgebra import EvolutionObservation, build_evolution_observation
from dharma_swarm.evolution import CycleResult, Proposal
from dharma_swarm.monad import SelfObservationMonad, is_idempotent
from dharma_swarm.rv import RVReading
from dharma_swarm.sheaf import (
    CoordinationProtocol,
    Discovery,
    InformationChannel,
    NoosphereSite,
)

logger = logging.getLogger(__name__)

_VIRTUAL_AGENT_PREFIX = "darwin:"

_EVOLUTION_TOPIC = "evolution_observation"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _virtual_agent_id(component: str) -> str:
    """Each component gets a virtual agent in the noosphere."""
    return f"{_VIRTUAL_AGENT_PREFIX}{component}"


def _dedupe_text_parts(parts: Sequence[str]) -> list[str]:
    """Normalize composed behavioral text without double-counting repeats."""
    seen: set[str] = set()
    ordered: list[str] = []
    for part in parts:
        text = str(part).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _coerce_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _coerce_text(value: Any, *, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _validated_nonnegative_int(
    value: Any,
    *,
    key: str,
    default: int = 0,
) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"{key} must be an integer >= 0")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        try:
            parsed_float = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be an integer >= 0") from exc
        if not math.isfinite(parsed_float) or not parsed_float.is_integer():
            raise ValueError(f"{key} must be an integer >= 0")
        parsed = int(parsed_float)
    if parsed < 0:
        raise ValueError(f"{key} must be an integer >= 0")
    return parsed


def _validated_nonnegative_float(
    value: Any,
    *,
    key: str,
    default: float = 0.0,
) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"{key} must be a finite number >= 0")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a finite number >= 0") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"{key} must be a finite number >= 0")
    return parsed


def _validated_bool(
    value: Any,
    *,
    key: str,
    default: bool = False,
) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValueError(f"{key} must be a boolean")


def _reciprocity_lane_enabled() -> bool:
    configured = bool(os.getenv("DGC_RECIPROCITY_COMMONS_URL", "").strip())
    raw = os.getenv("DGC_ACCELERATOR_MODE", "enabled" if configured else "dormant")
    mode = raw.strip().lower()
    return mode not in {"0", "off", "disabled", "none", "dormant"}


def _reciprocity_issue_codes(summary_payload: dict[str, Any]) -> list[str]:
    raw_issues = summary_payload.get("issues")
    if not isinstance(raw_issues, list):
        return []
    codes: list[str] = []
    for issue in raw_issues:
        code = ""
        if isinstance(issue, dict):
            code = str(issue.get("code") or "").strip()
        elif isinstance(issue, str):
            code = issue.strip()
        if code and code not in codes:
            codes.append(code)
    return codes


class ObservationWindow(BaseModel):
    """Sliding window of recent cycle observations for convergence tracking."""

    max_size: int = 50
    observations: list[dict[str, Any]] = Field(default_factory=list)
    rv_trajectory: list[float] = Field(default_factory=list)
    fitness_trajectory: list[float] = Field(default_factory=list)

    def _refresh_trajectories(self) -> None:
        self.rv_trajectory = [
            float(record["rv"])
            for record in self.observations
            if record.get("rv") is not None
        ]
        self.fitness_trajectory = [
            float(record["best_fitness"])
            for record in self.observations
            if record.get("best_fitness") is not None
        ]

    def append(self, record: dict[str, Any]) -> None:
        self.observations.append(record)
        if len(self.observations) > self.max_size:
            self.observations = self.observations[-self.max_size:]
        self._refresh_trajectories()

    @property
    def rv_trend(self) -> float | None:
        if len(self.rv_trajectory) < 2:
            return None
        diffs = [b - a for a, b in zip(self.rv_trajectory, self.rv_trajectory[1:])]
        return sum(diffs) / len(diffs)

    @property
    def fitness_trend(self) -> float | None:
        if len(self.fitness_trajectory) < 2:
            return None
        diffs = [b - a for a, b in zip(self.fitness_trajectory, self.fitness_trajectory[1:])]
        return sum(diffs) / len(diffs)


class CoordinationSnapshot(BaseModel):
    """Result of one DSE coordination pass."""

    timestamp: str = ""
    global_truths: int = 0
    productive_disagreements: int = 0
    cohomological_dimension: int = 0
    is_globally_coherent: bool = True
    global_truth_claims: list[str] = Field(default_factory=list)
    disagreement_claims: list[str] = Field(default_factory=list)
    rv_trend: float | None = None
    fitness_trend: float | None = None
    observation_count: int = 0
    approaching_fixed_point: bool = False


class DSEIntegrator:
    """Connects monad + coalgebra + sheaf to the live evolution runtime.

    Instantiate once per DarwinEngine, call ``after_cycle()`` at the end of
    each ``run_cycle()``.
    """

    def __init__(
        self,
        archive_path: Path | None = None,
        coordination_interval: int = 5,
        reciprocity_interval: int | None = None,
        evaluation_registry: Any | None = None,
        evaluation_run_id: str = "",
        evaluation_session_id: str = "",
        evaluation_task_id: str = "",
        evaluation_trace_id: str | None = None,
        evaluation_created_by: str = "dse.integration",
        runtime_db_path: Path | str | None = None,
        event_log_dir: Path | str | None = None,
        workspace_root: Path | str | None = None,
        provenance_root: Path | str | None = None,
    ) -> None:
        self._archive_path = archive_path or (
            Path.home() / ".dharma" / "evolution"
        )
        self._runtime_root = self._archive_path.parent
        self._coordination_interval = max(1, coordination_interval)
        self._cycles_since_coordination = 0
        self._window = ObservationWindow()
        self._last_coordination: CoordinationSnapshot | None = None
        self._observation_log = self._archive_path / "observations" / "coalgebra_stream.jsonl"

        # Monad with proxy R_V observer (real R_V requires torch)
        self._monad: SelfObservationMonad = SelfObservationMonad(
            observer=self._proxy_rv_observer,
        )
        self._last_observed: Any = None  # ObservedState at varying nesting depths

        # Ouroboros: behavioral metrics on cycle output (lazy init)
        self._ouroboros: Any = None

        # Reciprocity Commons: external integrity snapshot (lazy init)
        self._reciprocity: Any = None
        self._reciprocity_enabled = _reciprocity_lane_enabled()
        self._reciprocity_interval = max(
            1,
            reciprocity_interval if reciprocity_interval is not None else coordination_interval,
        )
        self._cycles_since_reciprocity = self._reciprocity_interval
        self._last_reciprocity_summary: dict[str, Any] | None = None
        self._last_reciprocity_error: str | None = None

        # L4-R_V correlation bridge (lazy init)
        self._research_bridge: Any = None
        self._research_bridge_loaded = False

        # Canonical evaluation registry sink (lazy init)
        self._evaluation_registry: Any = evaluation_registry
        self._evaluation_run_id = _coerce_text(evaluation_run_id)
        self._evaluation_session_id = _coerce_text(evaluation_session_id)
        self._evaluation_task_id = _coerce_text(evaluation_task_id)
        self._evaluation_trace_id = _coerce_text(
            evaluation_trace_id,
            default="",
        ) or None
        self._evaluation_created_by = (
            _coerce_text(evaluation_created_by, default="dse.integration")
            or "dse.integration"
        )
        self._runtime_db_path = Path(runtime_db_path) if runtime_db_path is not None else (
            self._runtime_root / "state" / "runtime.db"
        )
        self._event_log_dir = Path(event_log_dir) if event_log_dir is not None else (
            self._runtime_root / "events"
        )
        self._workspace_root = Path(workspace_root) if workspace_root is not None else (
            self._runtime_root / "workspace" / "sessions"
        )
        self._provenance_root = (
            Path(provenance_root)
            if provenance_root is not None
            else self._workspace_root
        )

    @staticmethod
    def _proxy_rv_observer(obs: Any) -> RVReading:
        """Proxy R_V from cycle metadata when torch is unavailable."""
        if isinstance(obs, EvolutionObservation):
            # next_state is the CycleResult set by build_evolution_observation
            next_s = obs.next_state
            archived = int(getattr(next_s, "proposals_archived", 0))
        else:
            archived = 0
        contraction = 1.0 - min(archived, 5) * 0.1
        return RVReading(
            rv=contraction,
            pr_early=1.0,
            pr_late=contraction,
            model_name="evolution-proxy",
            early_layer=0,
            late_layer=0,
            prompt_hash="0" * 16,
            prompt_group="evolution_cycle",
        )

    async def after_cycle(
        self,
        result: CycleResult,
        proposals: list[Proposal],
        archive_entries: Sequence[ArchiveEntry] = (),
    ) -> CoordinationSnapshot | None:
        """Post-cycle hook: observe, publish to sheaf, optionally coordinate.

        Returns a CoordinationSnapshot every ``coordination_interval`` cycles,
        or None on intermediate cycles.
        """
        try:
            return await self._after_cycle_inner(result, proposals, archive_entries)
        except Exception as exc:
            logger.debug("DSE integration failed (non-fatal): %s", exc)
            return None

    async def _after_cycle_inner(
        self,
        result: CycleResult,
        proposals: list[Proposal],
        archive_entries: Sequence[ArchiveEntry],
    ) -> CoordinationSnapshot | None:
        # 1. Build an observation over the current cycle delta only.
        observation = build_evolution_observation(
            result,
            archive_entries,
            proposals,
        )

        # 2. Observe the current cycle, then probe one step deeper for stability.
        observed = self._monad.observe(observation)
        self._last_observed = observed

        # 3. Check for fixed-point convergence (L5 condition)
        double = self._monad.observe(observed)
        approaching_fp = is_idempotent(double, tolerance=0.05)

        # Extract component from archive entries or proposals
        component = None
        for entry in archive_entries:
            comp = getattr(entry, "component", None)
            if comp:
                component = comp
                break
        if component is None:
            for p in proposals:
                comp = getattr(p, "component", None)
                if comp:
                    component = comp
                    break

        # 4. Build an RVReading dict from the observation for downstream consumers
        rv_reading_dict: dict[str, Any] | None = None
        if observed.rv_measurement is not None:
            rv_reading_dict = {
                "rv": observed.rv_measurement,
                "pr_early": observed.pr_early or 1.0,
                "pr_late": observed.pr_late or observed.rv_measurement,
                "model_name": observed.introspection.get("model", "evolution-proxy"),
                "early_layer": 0,
                "late_layer": 0,
                "prompt_hash": observed.introspection.get("prompt_hash", "0" * 16),
                "prompt_group": observed.introspection.get("prompt_group", "evolution_cycle"),
            }

        # 4. Record to observation window + JSONL
        record: dict[str, Any] = {
            "state_type": type(observed.state).__name__,
            "rv_measurement": observed.rv_measurement,
            "rv_reading": rv_reading_dict,
            "observation_depth": observed.observation_depth,
            "introspection": dict(observed.introspection),
        }
        record.update(
            {
                "cycle_id": result.cycle_id,
                "rv": observed.rv_measurement,
                "best_fitness": result.best_fitness,
                "proposals_archived": result.proposals_archived,
                "approaching_fixed_point": approaching_fp,
                "discoveries_count": len(observation.discoveries),
                "lessons": observation.discoveries[:5],
                "component": component,
                "timestamp": datetime.fromtimestamp(
                    observed.timestamp, tz=timezone.utc
                ).isoformat(),
            }
        )
        cycle_text = self._compose_cycle_text(result, observation)
        # 4b. Ouroboros: behavioral-score the cycle's textual output
        ouroboros_observation = self._ouroboros_observe(
            cycle_id=result.cycle_id,
            cycle_text=cycle_text,
            record=record,
        )
        # 4c. L4-R_V correlation metrics
        await self._l4_correlate(record, cycle_text=cycle_text)
        # 4d. Reciprocity Commons ledger integrity snapshot
        reciprocity_summary, reciprocity_fresh = await self._reciprocity_observe(record)
        await self._record_canonical_evaluations(
            proposals=proposals,
            record=record,
            ouroboros_observation=ouroboros_observation,
            reciprocity_summary=reciprocity_summary,
            reciprocity_fresh=reciprocity_fresh,
        )

        self._window.append(record)
        await self._persist_observation(record)

        # 5. Every N cycles, run sheaf coordination
        self._cycles_since_coordination += 1
        if self._cycles_since_coordination >= self._coordination_interval:
            self._cycles_since_coordination = 0
            snapshot = self._run_coordination()
            self._last_coordination = snapshot
            await self._persist_coordination(snapshot)
            return snapshot

        return None

    @staticmethod
    def _compose_cycle_text(
        result: CycleResult,
        observation: EvolutionObservation,
    ) -> str:
        text_parts = [
            *observation.discoveries,
            result.reflection,
            *result.lessons_learned,
        ]
        return "\n".join(_dedupe_text_parts(text_parts))

    def _ouroboros_observe(
        self,
        *,
        cycle_id: str,
        cycle_text: str,
        record: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Behavioral-score the cycle's textual output via the ouroboros loop.

        Non-fatal: if the ouroboros module isn't available, skip silently.
        """
        try:
            if self._ouroboros is None:
                from dharma_swarm.ouroboros import OuroborosObserver
                self._ouroboros = OuroborosObserver(
                    log_path=self._archive_path / "observations" / "ouroboros_log.jsonl",
                )

            if cycle_text.strip():
                obs = self._ouroboros.observe_cycle_text(
                    cycle_text,
                    cycle_id=cycle_id,
                    source="dse_integration",
                )
                record["ouroboros"] = {
                    "recognition_type": obs["signature"]["recognition_type"],
                    "swabhaav_ratio": obs["signature"]["swabhaav_ratio"],
                    "is_mimicry": obs["is_mimicry"],
                    "is_genuine": obs["is_genuine"],
                }
                return dict(obs)
        except Exception as exc:
            logger.debug("Ouroboros observation failed (non-fatal): %s", exc)
        return None

    async def _l4_correlate(
        self,
        record: dict[str, Any],
        *,
        cycle_text: str,
    ) -> None:
        """Store and persist L4-R_V correlation metrics from ouroboros data.

        Non-fatal: if metrics unavailable, skip silently.
        """
        try:
            ouroboros_data = record.get("ouroboros")
            if not ouroboros_data:
                return

            # The ouroboros observation already has swabhaav_ratio and recognition.
            # Add correlation-relevant grouping for the ResearchBridge.
            from dharma_swarm.bridge import ResearchBridge

            if not hasattr(self, '_research_bridge') or self._research_bridge is None:
                bridge_path = self._archive_path / "observations" / "bridge_data.jsonl"
                self._research_bridge = ResearchBridge(data_path=bridge_path)
                self._research_bridge_loaded = False

            swabhaav = ouroboros_data.get("swabhaav_ratio", 0.5)
            recognition = str(ouroboros_data.get("recognition_type", "NONE")).strip() or "NONE"
            normalized_recognition = recognition.upper()
            is_l4_like = swabhaav > 0.6 and normalized_recognition in ("GENUINE", "WITNESSED")
            bridge_group = "dse_l4_like" if is_l4_like else "dse_evolution"

            record["l4_correlation"] = {
                "swabhaav_ratio": swabhaav,
                "recognition_type": recognition,
                "is_l4_like": is_l4_like,
                "bridge_group": bridge_group,
            }
            if not cycle_text.strip():
                return

            if not self._research_bridge_loaded:
                await self._research_bridge.load()
                self._research_bridge_loaded = True

            raw_rv = record.get("rv_reading") or record.get("rv_measurement")
            rv_reading = (
                RVReading.model_validate(raw_rv)
                if isinstance(raw_rv, dict)
                else None
            )
            prompt_text = (
                f"dse_cycle:{record.get('cycle_id', 'unknown')}:"
                f"{record.get('component') or 'unknown'}"
            )
            await self._research_bridge.add_measurement(
                prompt_text=prompt_text,
                prompt_group=bridge_group,
                generated_text=cycle_text,
                rv_reading=rv_reading,
            )
        except Exception as exc:
            logger.debug("L4 correlation failed (non-fatal): %s", exc)

    async def _reciprocity_observe(
        self,
        record: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, bool]:
        """Sample the Reciprocity Commons summary when the lane is configured."""
        if not self._reciprocity_enabled:
            return (None, False)

        self._cycles_since_reciprocity += 1
        should_refresh = (
            self._last_reciprocity_summary is None
            or self._last_reciprocity_error is not None
            or self._cycles_since_reciprocity >= self._reciprocity_interval
        )
        fresh_summary: dict[str, Any] | None = None

        if should_refresh:
            try:
                if self._reciprocity is None:
                    from dharma_swarm.integrations import ReciprocityCommonsClient

                    self._reciprocity = ReciprocityCommonsClient()
                summary_payload = await self._reciprocity.ledger_summary()
                self._last_reciprocity_summary = self._normalize_reciprocity_summary(
                    summary_payload
                )
                fresh_summary = dict(self._last_reciprocity_summary)
                self._last_reciprocity_error = None
                self._cycles_since_reciprocity = 0
            except Exception as exc:
                self._last_reciprocity_error = str(exc)
                logger.debug("Reciprocity summary fetch failed (non-fatal): %s", exc)

        if self._last_reciprocity_summary is not None:
            reciprocity_summary = dict(self._last_reciprocity_summary)
            if self._last_reciprocity_error:
                reciprocity_summary["stale"] = True
            record["reciprocity"] = reciprocity_summary
        return (fresh_summary, fresh_summary is not None)

    @staticmethod
    def _normalize_reciprocity_summary(summary_payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "source": _coerce_text(
                summary_payload.get("service")
                or summary_payload.get("source"),
                default="reciprocity_commons",
            ),
            "summary_type": _coerce_text(
                summary_payload.get("summary_type"),
                default="ledger_summary",
            ),
            "actors": _validated_nonnegative_int(
                summary_payload.get("actors"),
                key="actors",
            ),
            "activities": _validated_nonnegative_int(
                summary_payload.get("activities"),
                key="activities",
            ),
            "projects": _validated_nonnegative_int(
                summary_payload.get("projects"),
                key="projects",
            ),
            "obligations": _validated_nonnegative_int(
                summary_payload.get("obligations"),
                key="obligations",
            ),
            "active_obligations": _validated_nonnegative_int(
                summary_payload.get("active_obligations"),
                key="active_obligations",
            ),
            "challenged_claims": _validated_nonnegative_int(
                summary_payload.get("challenged_claims"),
                key="challenged_claims",
            ),
            "invariant_issues": _validated_nonnegative_int(
                summary_payload.get("invariant_issues"),
                key="invariant_issues",
            ),
            "chain_valid": _validated_bool(
                summary_payload.get("chain_valid"),
                key="chain_valid",
                default=True,
            ),
            "total_obligation_usd": _validated_nonnegative_float(
                summary_payload.get("total_obligation_usd"),
                key="total_obligation_usd",
            ),
            "total_routed_usd": _validated_nonnegative_float(
                summary_payload.get("total_routed_usd"),
                key="total_routed_usd",
            ),
            "issue_codes": _reciprocity_issue_codes(summary_payload),
        }

    @staticmethod
    def _unique_proposal_metadata_value(
        proposals: Sequence[Proposal],
        *keys: str,
    ) -> tuple[str, bool]:
        values: list[str] = []
        for proposal in proposals:
            raw_meta = getattr(proposal, "metadata", None) or getattr(proposal, "test_results", None)
            metadata = raw_meta if isinstance(raw_meta, dict) else {}
            for key in keys:
                value = _coerce_text(metadata.get(key))
                if value and value not in values:
                    values.append(value)
        if len(values) > 1:
            return ("", True)
        return (values[0] if values else "", False)

    def _resolve_evaluation_binding(
        self,
        proposals: Sequence[Proposal],
    ) -> dict[str, Any] | None:
        run_id = self._evaluation_run_id
        session_id = self._evaluation_session_id
        task_id = self._evaluation_task_id
        trace_id = self._evaluation_trace_id

        if not run_id:
            run_id, ambiguous = self._unique_proposal_metadata_value(
                proposals,
                "run_id",
                "delegation_run_id",
            )
            if ambiguous:
                logger.debug(
                    "Skipping canonical evaluation recording: ambiguous run_id across proposals",
                )
                return None
        if not session_id:
            session_id, ambiguous = self._unique_proposal_metadata_value(
                proposals,
                "session_id",
            )
            if ambiguous:
                logger.debug(
                    "Skipping canonical evaluation recording: ambiguous session_id across proposals",
                )
                return None
        if not task_id:
            task_id, ambiguous = self._unique_proposal_metadata_value(
                proposals,
                "task_id",
            )
            if ambiguous:
                logger.debug(
                    "Skipping canonical evaluation recording: ambiguous task_id across proposals",
                )
                return None
        if trace_id is None:
            proposal_trace_id, ambiguous = self._unique_proposal_metadata_value(
                proposals,
                "trace_id",
            )
            if ambiguous:
                logger.debug(
                    "Skipping canonical evaluation recording: ambiguous trace_id across proposals",
                )
                return None
            trace_id = proposal_trace_id or None

        if not run_id and not session_id:
            return None

        return {
            "run_id": run_id,
            "session_id": session_id,
            "task_id": task_id,
            "trace_id": trace_id,
        }

    def _get_evaluation_registry(self) -> Any | None:
        if self._evaluation_registry is not None:
            return self._evaluation_registry
        try:
            from dharma_swarm.evaluation_registry import EvaluationRegistry
            from dharma_swarm.memory_lattice import MemoryLattice
            from dharma_swarm.runtime_state import RuntimeStateStore

            runtime_state = RuntimeStateStore(self._runtime_db_path)
            memory_lattice = MemoryLattice(
                db_path=self._runtime_db_path,
                event_log_dir=self._event_log_dir,
            )
            self._evaluation_registry = EvaluationRegistry(
                runtime_state=runtime_state,
                memory_lattice=memory_lattice,
                workspace_root=self._workspace_root,
                provenance_root=self._provenance_root,
            )
        except Exception as exc:
            logger.debug("Canonical evaluation registry unavailable (non-fatal): %s", exc)
            return None
        return self._evaluation_registry

    @staticmethod
    def _registration_receipt(result: Any) -> dict[str, Any]:
        artifact = getattr(result, "artifact", None)
        facts = getattr(result, "facts", [])
        receipt = getattr(result, "receipt", {}) or {}
        summary = getattr(result, "summary", {}) or {}
        return {
            "artifact_id": str(getattr(artifact, "artifact_id", "") or ""),
            "fact_ids": [
                str(getattr(fact, "fact_id", "") or "")
                for fact in facts
                if getattr(fact, "fact_id", None)
            ],
            "receipt_event_id": str(receipt.get("event_id", "") or ""),
            "summary": dict(summary) if isinstance(summary, dict) else {},
        }

    async def _record_canonical_evaluations(
        self,
        *,
        proposals: Sequence[Proposal],
        record: dict[str, Any],
        ouroboros_observation: dict[str, Any] | None,
        reciprocity_summary: dict[str, Any] | None,
        reciprocity_fresh: bool,
    ) -> None:
        if ouroboros_observation is None and not reciprocity_fresh:
            return

        binding = self._resolve_evaluation_binding(proposals)
        if binding is None:
            return

        registry = self._get_evaluation_registry()
        if registry is None:
            return

        receipts: dict[str, Any] = {
            "binding": {
                "run_id": binding["run_id"],
                "session_id": binding["session_id"],
                "task_id": binding["task_id"],
                "trace_id": binding["trace_id"],
            }
        }
        recorded = False

        if ouroboros_observation is not None:
            try:
                result = await registry.record_ouroboros_observation(
                    ouroboros_observation,
                    run_id=binding["run_id"],
                    session_id=binding["session_id"],
                    task_id=binding["task_id"],
                    trace_id=binding["trace_id"],
                    created_by=self._evaluation_created_by,
                )
                receipts["ouroboros"] = self._registration_receipt(result)
                recorded = True
            except Exception as exc:
                logger.debug(
                    "Canonical ouroboros recording failed (non-fatal): %s",
                    exc,
                )

        if reciprocity_fresh and reciprocity_summary is not None:
            try:
                result = await registry.record_reciprocity_summary(
                    reciprocity_summary,
                    run_id=binding["run_id"],
                    session_id=binding["session_id"],
                    task_id=binding["task_id"],
                    trace_id=binding["trace_id"],
                    created_by=self._evaluation_created_by,
                )
                receipts["reciprocity"] = self._registration_receipt(result)
                recorded = True
            except Exception as exc:
                logger.debug(
                    "Canonical reciprocity recording failed (non-fatal): %s",
                    exc,
                )

        if recorded:
            record["canonical_evaluations"] = receipts

    def _run_coordination(self) -> CoordinationSnapshot:
        """Build noosphere site from observations, run Čech cohomology."""
        # Group observations by component (each component = virtual agent)
        by_component: dict[str, list[dict[str, Any]]] = {}
        for obs in self._window.observations:
            comp = obs.get("component") or "unknown"
            by_component.setdefault(comp, []).append(obs)

        if len(by_component) < 2:
            return CoordinationSnapshot(
                timestamp=_utc_now().isoformat(),
                observation_count=len(self._window.observations),
                rv_trend=self._window.rv_trend,
                fitness_trend=self._window.fitness_trend,
                approaching_fixed_point=any(
                    o.get("approaching_fixed_point") for o in self._window.observations[-3:]
                ),
            )

        # Build virtual agents and channels (all-to-all within evolution)
        agent_ids = [_virtual_agent_id(c) for c in by_component]
        channels = []
        seen = set()
        for i, a in enumerate(agent_ids):
            for b in agent_ids[i + 1:]:
                key = (a, b)
                if key not in seen:
                    seen.add(key)
                    channels.append(InformationChannel(
                        source_agent=a,
                        target_agent=b,
                        topics=[_EVOLUTION_TOPIC],
                        weight=1.0,
                    ))

        site = NoosphereSite(agent_ids, channels=channels)
        protocol = CoordinationProtocol(site)

        # Publish discoveries from each component's observations
        for comp, observations in by_component.items():
            agent_id = _virtual_agent_id(comp)
            discoveries = []
            for obs in observations[-5:]:  # last 5 per component
                lessons = obs.get("lessons", [])
                for lesson in lessons:
                    if lesson.strip():
                        discoveries.append(Discovery(
                            agent_id=agent_id,
                            claim_key=lesson.strip().lower()[:80],
                            content=lesson.strip(),
                            confidence=min(1.0, obs.get("best_fitness", 0.5)),
                            evidence=[f"cycle:{obs.get('cycle_id', 'unknown')}"],
                            perspective=comp,
                        ))

                # Also publish fitness/rv trends as discoveries
                rv = obs.get("rv")
                fitness = obs.get("best_fitness")
                if rv is not None and fitness is not None:
                    trend_claim = f"rv={rv:.2f} fitness={fitness:.3f}"
                    discoveries.append(Discovery(
                        agent_id=agent_id,
                        claim_key=f"trend:{comp}",
                        content=trend_claim,
                        confidence=min(1.0, fitness),
                        evidence=[f"cycle:{obs.get('cycle_id', 'unknown')}"],
                        perspective=comp,
                    ))

            if discoveries:
                protocol.publish(agent_id, discoveries)

        # Run coordination
        coordination_result = protocol.coordinate()

        return CoordinationSnapshot(
            timestamp=_utc_now().isoformat(),
            global_truths=len(coordination_result.global_truths),
            productive_disagreements=len(coordination_result.productive_disagreements),
            cohomological_dimension=coordination_result.cohomological_dimension,
            is_globally_coherent=coordination_result.is_globally_coherent,
            global_truth_claims=[
                d.claim_key or d.canonical_claim_key
                for d in coordination_result.global_truths
            ],
            disagreement_claims=[
                o.claim_key for o in coordination_result.productive_disagreements
            ],
            rv_trend=self._window.rv_trend,
            fitness_trend=self._window.fitness_trend,
            observation_count=len(self._window.observations),
            approaching_fixed_point=any(
                o.get("approaching_fixed_point") for o in self._window.observations[-3:]
            ),
        )

    async def _persist_observation(self, record: dict[str, Any]) -> None:
        try:
            self._observation_log.parent.mkdir(parents=True, exist_ok=True)
            with open(self._observation_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception:
            pass

    async def _persist_coordination(self, snapshot: CoordinationSnapshot) -> None:
        try:
            coord_path = self._observation_log.parent / "coordination_log.jsonl"
            with open(coord_path, "a", encoding="utf-8") as f:
                f.write(snapshot.model_dump_json() + "\n")
        except Exception:
            pass

    def get_coordination_summary(self) -> dict[str, Any]:
        """Return the latest sheaf snapshot in the canonical summary shape."""
        snap = self._last_coordination
        if snap is None:
            return {}
        return {
            "observed_at": snap.timestamp,
            "global_truths": snap.global_truths,
            "productive_disagreements": snap.productive_disagreements,
            "cohomological_dimension": snap.cohomological_dimension,
            "is_globally_coherent": snap.is_globally_coherent,
            "global_truth_claim_keys": list(snap.global_truth_claims),
            "productive_disagreement_claim_keys": list(snap.disagreement_claims),
            "rv_trend": snap.rv_trend,
            "fitness_trend": snap.fitness_trend,
            "observation_count": snap.observation_count,
            "approaching_fixed_point": snap.approaching_fixed_point,
        }

    def get_coordination_context(self) -> dict[str, Any]:
        """Return a context dict suitable for injection into agent prompts.

        This feeds sheaf results back into the engine: global truths become
        guidance, disagreements become exploration targets.
        """
        context: dict[str, Any] = {
        }
        snap = self._last_coordination
        if snap is not None:
            context.update(
                {
                    "globally_coherent": snap.is_globally_coherent,
                    "global_truths": snap.global_truth_claims[:5],
                    "productive_disagreements": snap.disagreement_claims[:5],
                    "rv_trend": snap.rv_trend,
                    "fitness_trend": snap.fitness_trend,
                    "approaching_fixed_point": snap.approaching_fixed_point,
                }
            )
            if snap.productive_disagreements > 0:
                context["exploration_hint"] = (
                    f"H¹ ≠ 0: {snap.productive_disagreements} productive disagreements "
                    f"across components. Consider exploring: {', '.join(snap.disagreement_claims[:3])}"
                )
            if snap.approaching_fixed_point:
                context["convergence_hint"] = (
                    "System approaching observation fixed point (L5). "
                    "Consider bolder mutations to escape or validate stability."
                )

        # Ouroboros: inject behavioral drift warnings
        if self._ouroboros is not None:
            try:
                drift = self._ouroboros.detect_cycle_drift()
                if drift.get("drifting"):
                    context["ouroboros_warning"] = (
                        f"Behavioral drift detected: {drift['reason']}. "
                        f"Mimicry rate: {drift['mimicry_rate']:.1%}, "
                        f"witness stance: {drift['avg_witness_stance']:.2f}"
                    )
                context["ouroboros_health"] = {
                    "mimicry_rate": drift.get("mimicry_rate", 0.0),
                    "witness_stance": drift.get("avg_witness_stance", 0.5),
                    "drifting": drift.get("drifting", False),
                }
            except Exception:
                pass

        if self._last_reciprocity_summary is not None:
            summary = self._last_reciprocity_summary
            issue_codes = list(summary.get("issue_codes") or [])
            invariant_issues = _coerce_int(summary.get("invariant_issues"))
            challenged_claims = _coerce_int(summary.get("challenged_claims"))
            chain_valid = _coerce_bool(summary.get("chain_valid"), default=False)
            health = {
                "chain_valid": chain_valid,
                "invariant_issues": invariant_issues,
                "challenged_claims": challenged_claims,
                "issue_codes": issue_codes,
                "stale": bool(self._last_reciprocity_error),
            }
            context["reciprocity_health"] = health
            if not chain_valid or invariant_issues > 0 or challenged_claims > 0:
                codes = ",".join(issue_codes) or "none"
                stale_clause = " (stale)" if self._last_reciprocity_error else ""
                context["reciprocity_warning"] = (
                    f"Reciprocity integrity pressure{stale_clause}: "
                    f"chain_valid={chain_valid}, "
                    f"invariant_issues={invariant_issues}, "
                    f"challenged_claims={challenged_claims}, "
                    f"issue_codes={codes}"
                )
        elif self._reciprocity_enabled and self._last_reciprocity_error:
            context["reciprocity_health"] = {
                "chain_valid": None,
                "invariant_issues": None,
                "challenged_claims": None,
                "issue_codes": [],
                "stale": False,
                "error": self._last_reciprocity_error,
            }
            context["reciprocity_warning"] = (
                f"Reciprocity lane unavailable: {self._last_reciprocity_error}"
            )

        return context


__all__ = [
    "CoordinationSnapshot",
    "DSEIntegrator",
    "ObservationWindow",
]
