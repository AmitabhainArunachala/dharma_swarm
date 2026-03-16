"""Telic Seam — Write-through layer connecting orchestrator to ontology.

Phase A of the Strangler Fig migration: every orchestrator dispatch and
agent completion also writes ontology objects. Nothing changes about how
the orchestrator works — this is additive only.

The metabolic loop:
  need appears in ontology → action proposed → gates evaluate →
  orchestrator claims lease → agent executes → outcome recorded →
  value measured → fitness updated → routing changes → projections refresh

This module provides the first three arrows and the outcome recording.

Usage::

    from dharma_swarm.telic_seam import TelicSeam

    seam = TelicSeam()  # or TelicSeam(registry=..., lineage=...)

    # On dispatch:
    proposal_id = seam.record_dispatch(task, agent_id, topology="dispatch")
    seam.record_gate_decision(proposal_id, gate_result)

    # On completion:
    seam.record_outcome(proposal_id, task, agent_id, success=True, result="...")

    # On failure:
    seam.record_outcome(proposal_id, task, agent_id, success=False, error="...")
"""

from __future__ import annotations

import logging
from typing import Any

from dharma_swarm.lineage import LineageEdge, LineageGraph
from dharma_swarm.models import GateCheckResult, GateDecision, Task
from dharma_swarm.ontology import OntologyRegistry

logger = logging.getLogger(__name__)


class TelicSeam:
    """Write-through seam between orchestrator/agent_runner and ontology.

    Thread-safe for single-writer patterns. All methods are best-effort:
    ontology recording failures never block orchestration.
    """

    def __init__(
        self,
        registry: OntologyRegistry | None = None,
        lineage: LineageGraph | None = None,
    ) -> None:
        self._registry = registry or OntologyRegistry.create_dharma_registry()
        self._lineage = lineage or LineageGraph()
        self._proposal_map: dict[str, str] = {}  # task_id -> proposal obj_id

    @property
    def registry(self) -> OntologyRegistry:
        return self._registry

    @property
    def lineage(self) -> LineageGraph:
        return self._lineage

    def record_dispatch(
        self,
        task: Task,
        agent_id: str,
        topology: str = "dispatch",
    ) -> str | None:
        """Record an ActionProposal when the orchestrator dispatches a task.

        Returns the proposal object ID, or None if recording failed.
        """
        try:
            obj, errors = self._registry.create_object(
                "ActionProposal",
                properties={
                    "task_id": task.id,
                    "agent_id": agent_id,
                    "action_type": topology if topology in (
                        "dispatch", "fan_out", "pipeline", "evolution", "manual"
                    ) else "dispatch",
                    "title": task.title,
                    "description": task.description[:500] if task.description else "",
                    "status": "proposed",
                    "priority": task.priority.value,
                },
                created_by="orchestrator",
            )
            if obj is None:
                logger.debug("ActionProposal creation failed: %s", errors)
                return None

            self._proposal_map[task.id] = obj.id
            return obj.id

        except Exception as exc:
            logger.debug("TelicSeam.record_dispatch failed: %s", exc)
            return None

    def record_gate_decision(
        self,
        proposal_id: str | None,
        gate_result: GateCheckResult,
        witness_reroutes: int = 0,
    ) -> str | None:
        """Record a GateDecisionRecord linked to the ActionProposal.

        Returns the gate decision object ID, or None if recording failed.
        """
        if proposal_id is None:
            return None
        try:
            # Serialize gate_results to a dict of strings
            serialized_gates: dict[str, Any] = {}
            for gate_name, (result, reason) in gate_result.gate_results.items():
                serialized_gates[gate_name] = {
                    "result": result.value if hasattr(result, "value") else str(result),
                    "reason": reason,
                }

            obj, errors = self._registry.create_object(
                "GateDecisionRecord",
                properties={
                    "proposal_id": proposal_id,
                    "decision": gate_result.decision.value,
                    "reason": gate_result.reason,
                    "gate_results": serialized_gates,
                    "witness_reroutes": witness_reroutes,
                },
                created_by="telos_gatekeeper",
            )
            if obj is None:
                logger.debug("GateDecisionRecord creation failed: %s", errors)
                return None

            # Link gate decision to proposal
            self._registry.create_link(
                "has_gate_decision",
                source_id=proposal_id,
                target_id=obj.id,
                created_by="telic_seam",
            )

            # Update proposal status based on decision
            new_status = {
                GateDecision.ALLOW: "approved",
                GateDecision.BLOCK: "rejected",
                GateDecision.REVIEW: "gated",
            }.get(gate_result.decision, "gated")

            self._registry.update_object(
                proposal_id,
                {"status": new_status},
                updated_by="telic_seam",
            )

            return obj.id

        except Exception as exc:
            logger.debug("TelicSeam.record_gate_decision failed: %s", exc)
            return None

    def record_outcome(
        self,
        task: Task,
        agent_id: str,
        *,
        success: bool,
        result_summary: str = "",
        error: str = "",
        duration_ms: float = 0.0,
        fitness_score: float = 0.0,
    ) -> str | None:
        """Record an Outcome when agent completes (or fails) a task.

        Also records a lineage edge connecting task inputs to outputs.
        Returns the outcome object ID, or None if recording failed.
        """
        proposal_id = self._proposal_map.get(task.id)
        try:
            obj, errors = self._registry.create_object(
                "Outcome",
                properties={
                    "proposal_id": proposal_id or "",
                    "task_id": task.id,
                    "agent_id": agent_id,
                    "success": success,
                    "result_summary": result_summary[:500] if result_summary else "",
                    "error": error[:500] if error else "",
                    "duration_ms": duration_ms,
                    "fitness_score": fitness_score,
                },
                created_by=agent_id,
            )
            if obj is None:
                logger.debug("Outcome creation failed: %s", errors)
                return None

            # Link outcome to proposal if we have one
            if proposal_id:
                self._registry.create_link(
                    "has_outcome",
                    source_id=proposal_id,
                    target_id=obj.id,
                    created_by="telic_seam",
                )
                # Update proposal status
                self._registry.update_object(
                    proposal_id,
                    {"status": "completed" if success else "failed"},
                    updated_by="telic_seam",
                )

            # Record lineage edge
            input_artifacts = [task.id]
            if task.depends_on:
                input_artifacts.extend(task.depends_on)
            output_artifacts = [f"outcome:{obj.id}"]

            self._lineage.record(LineageEdge(
                task_id=task.id,
                input_artifacts=input_artifacts,
                output_artifacts=output_artifacts,
                agent=agent_id,
                operation="task_execution",
                metadata={
                    "success": success,
                    "proposal_id": proposal_id or "",
                    "outcome_id": obj.id,
                },
            ))

            return obj.id

        except Exception as exc:
            logger.debug("TelicSeam.record_outcome failed: %s", exc)
            return None

    def record_value_event(
        self,
        outcome_id: str,
        task: Task,
        agent_id: str,
        *,
        result_text: str = "",
        success: bool = True,
        duration_ms: float = 0.0,
        cell_id: str = "",
    ) -> str | None:
        """Record a ValueEvent measuring the value an Outcome produced.

        Idempotent: only one ValueEvent per outcome_id.
        Returns the value_event_id, or None if recording failed.
        """
        try:
            # Idempotency check
            for ve in self._registry.get_objects_by_type("ValueEvent"):
                if ve.properties.get("outcome_id") == outcome_id:
                    return ve.id

            # Compute behavioral_signal
            behavioral_signal = 0.5
            try:
                from dharma_swarm.metrics import MetricsAnalyzer
                behavioral_signal = MetricsAnalyzer().analyze(result_text).swabhaav_ratio
            except Exception:
                pass

            success_value = 1.0 if success else 0.0
            duration_efficiency = min(1.0, 10000.0 / max(duration_ms, 1.0))
            composite_value = (
                0.4 * behavioral_signal + 0.4 * success_value + 0.2 * duration_efficiency
            )
            task_type = ""
            if task and hasattr(task, "metadata") and isinstance(task.metadata, dict):
                task_type = task.metadata.get("task_type", "general")
            else:
                task_type = "general"

            obj, errors = self._registry.create_object(
                "ValueEvent",
                properties={
                    "outcome_id": outcome_id,
                    "agent_id": agent_id,
                    "cell_id": cell_id,
                    "task_id": task.id if task else "",
                    "task_type": task_type,
                    "behavioral_signal": behavioral_signal,
                    "success_value": success_value,
                    "duration_efficiency": duration_efficiency,
                    "composite_value": composite_value,
                    "scoring_method": "metrics_v1",
                },
                created_by=agent_id,
            )
            if obj is None:
                logger.debug("ValueEvent creation failed: %s", errors)
                return None

            # Link to outcome
            self._registry.create_link(
                "has_value_event",
                source_id=outcome_id,
                target_id=obj.id,
                created_by="telic_seam",
            )

            return obj.id

        except Exception as exc:
            logger.debug("TelicSeam.record_value_event failed: %s", exc)
            return None

    def record_contribution(
        self,
        value_event_id: str,
        agent_id: str,
        *,
        credit_share: float = 1.0,
        composite_value: float = 0.0,
        cell_id: str = "",
        task_type: str = "",
    ) -> str | None:
        """Record a Contribution assigning credit from a ValueEvent to an agent.

        Idempotent: one Contribution per (value_event_id, agent_id).
        Returns the contribution_id, or None if recording failed.
        """
        try:
            # Idempotency check
            for c in self._registry.get_objects_by_type("Contribution"):
                if (c.properties.get("value_event_id") == value_event_id
                        and c.properties.get("agent_id") == agent_id):
                    return c.id

            attributed_value = composite_value * credit_share

            obj, errors = self._registry.create_object(
                "Contribution",
                properties={
                    "value_event_id": value_event_id,
                    "agent_id": agent_id,
                    "cell_id": cell_id,
                    "task_type": task_type,
                    "credit_share": credit_share,
                    "attributed_value": attributed_value,
                },
                created_by=agent_id,
            )
            if obj is None:
                logger.debug("Contribution creation failed: %s", errors)
                return None

            # Link to value event
            self._registry.create_link(
                "has_contribution",
                source_id=value_event_id,
                target_id=obj.id,
                created_by="telic_seam",
            )

            return obj.id

        except Exception as exc:
            logger.debug("TelicSeam.record_contribution failed: %s", exc)
            return None

    def get_proposal_for_task(self, task_id: str) -> str | None:
        """Look up the ActionProposal ID for a task."""
        return self._proposal_map.get(task_id)

    def stats(self) -> dict[str, Any]:
        """Summary statistics for the metabolic loop."""
        ontology_stats = self._registry.stats()
        lineage_stats = self._lineage.stats()
        by_type = ontology_stats.get("objects_by_type", {})
        return {
            "proposals": by_type.get("ActionProposal", 0),
            "gate_decisions": by_type.get("GateDecisionRecord", 0),
            "outcomes": by_type.get("Outcome", 0),
            "value_events": by_type.get("ValueEvent", 0),
            "contributions": by_type.get("Contribution", 0),
            "venture_cells": by_type.get("VentureCell", 0),
            "lineage_edges": lineage_stats.get("total_edges", 0),
            "total_ontology_objects": ontology_stats.get("total_objects", 0),
            "registered_types": ontology_stats.get("registered_types", 0),
        }


# Module-level singleton — lazy init
_SEAM: TelicSeam | None = None


def get_seam() -> TelicSeam:
    """Get or create the module-level TelicSeam singleton."""
    global _SEAM
    if _SEAM is None:
        _SEAM = TelicSeam()
    return _SEAM


def reset_seam() -> None:
    """Reset the singleton (for testing)."""
    global _SEAM
    _SEAM = None
