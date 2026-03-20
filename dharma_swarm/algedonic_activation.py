"""algedonic_activation.py — Pain Causes Change.

Wires algedonic (pain/pleasure) signals to real behavioral modification.
Not just logging — when the organism hurts, it modifies itself.

Five pain signals:
  1. failure_rate      — audit_failure_rate > 0.5 → routing recalibration
  2. omega_divergence  — fleet/coherence diverge by > 0.4 → rebalance priorities
  3. ontological_drift — anomalous gate patterns > 5 → enforce glossary
  4. self_model_gap    — organism beliefs diverge from metrics → recalibrate
  5. telos_drift       — low coherence with healthy fleet → gnani_checkpoint

Ground: Beer (algedonic channel in VSM is the only channel that bypasses all
        intermediate management levels — pain must reach the top immediately),
        Kahneman (pain is a stronger signal than equivalent gain).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AlgedonicAction — describes a behavioral change
# ---------------------------------------------------------------------------


class AlgedonicAction(BaseModel):
    """A behavioral change triggered by an algedonic pain signal."""

    signal_type: str  # failure_rate, omega_divergence, ontological_drift,
    #                    self_model_gap, telos_drift
    severity: str  # low, medium, high, critical
    description: str
    action: str  # What behavioral change to make
    metadata: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# AlgedonicActivation
# ---------------------------------------------------------------------------


class AlgedonicActivation:
    """Wires pain signals to real behavioral change.

    Called from organism.heartbeat() after pulse is computed.
    Each action is recorded in OrganismMemory with relationships
    to the triggering algedonic event.
    """

    def __init__(self, organism: Any) -> None:  # Any to avoid circular import
        self._organism = organism
        self._activation_log: list[dict] = []

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def evaluate(self, pulse: Any) -> list[AlgedonicAction]:
        """Evaluate all five pain signals against current pulse.

        Returns list of actions to take. Never-fatal: each checker
        is individually wrapped.
        """
        actions: list[AlgedonicAction] = []
        for checker in [
            self._check_failure_rate,
            self._check_omega_divergence,
            self._check_ontological_drift,
            self._check_self_model_gap,
            self._check_telos_drift,
        ]:
            try:
                action = checker(pulse)
                if action is not None:
                    actions.append(action)
            except Exception as exc:
                logger.debug("Algedonic checker %s failed (non-fatal): %s", checker.__name__, exc)
        return actions

    def apply(self, action: AlgedonicAction) -> None:
        """Apply a behavioral change and log it.

        Records to organism memory. Actual behavioral changes are
        applied by the organism's heartbeat loop based on action.action field.
        """
        try:
            self._activation_log.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "signal": action.signal_type,
                "severity": action.severity,
                "action": action.action,
                "description": action.description,
            })
        except Exception as exc:
            logger.debug("Algedonic log append failed (non-fatal): %s", exc)

        # Record to organism memory if available
        try:
            if self._organism is not None and hasattr(self._organism, "memory") and self._organism.memory is not None:
                self._organism.memory.record_event(
                    entity_type="algedonic_event",
                    description=action.description,
                    metadata={
                        "signal": action.signal_type,
                        "action": action.action,
                        "severity": action.severity,
                    },
                )
                logger.info(
                    "ALGEDONIC ACTIVATION [%s]: %s → %s",
                    action.severity,
                    action.signal_type,
                    action.action,
                )
        except Exception as exc:
            logger.debug("Algedonic memory record failed (non-fatal): %s", exc)

    @property
    def recent_activations(self) -> list[dict]:
        """Return up to 20 most recent activations."""
        return self._activation_log[-20:]

    # ------------------------------------------------------------------
    # Pain signal checkers
    # ------------------------------------------------------------------

    def _check_failure_rate(self, pulse: Any) -> AlgedonicAction | None:
        """audit_failure_rate > 0.5 → routing recalibration."""
        rate = getattr(pulse, "audit_failure_rate", 0.0)
        if rate > 0.5:
            return AlgedonicAction(
                signal_type="failure_rate",
                severity="high",
                description=f"Audit failure rate at {rate:.0%}",
                action="recalibrate_routing",
                metadata={"failure_rate": rate},
            )
        return None

    def _check_omega_divergence(self, pulse: Any) -> AlgedonicAction | None:
        """Check if sub-scores diverge by > 0.4.

        Uses fleet_health vs identity_coherence as proxy sub-scores.
        """
        fleet = getattr(pulse, "fleet_health", 1.0)
        coherence = getattr(pulse, "identity_coherence", 1.0)
        divergence = abs(fleet - coherence)
        if divergence > 0.4:
            lagging = "fleet_health" if fleet < coherence else "identity_coherence"
            return AlgedonicAction(
                signal_type="omega_divergence",
                severity="medium",
                description=f"Sub-score divergence: {divergence:.2f} — {lagging} is lagging",
                action="rebalance_priorities",
                metadata={"divergence": divergence, "lagging": lagging},
            )
        return None

    def _check_ontological_drift(self, pulse: Any) -> AlgedonicAction | None:
        """Check for semantic inconsistency across agents.

        Uses anomalous_gate_patterns as proxy for drift.
        """
        patterns = getattr(pulse, "anomalous_gate_patterns", 0)
        if patterns > 5:
            return AlgedonicAction(
                signal_type="ontological_drift",
                severity="medium",
                description=f"{patterns} anomalous gate patterns detected",
                action="enforce_glossary",
                metadata={"patterns": patterns},
            )
        return None

    def _check_self_model_gap(self, pulse: Any) -> AlgedonicAction | None:  # noqa: ARG002
        """Check if organism's self-model diverges from reality.

        Uses organism memory's self_model_accuracy() if available.
        """
        try:
            if (
                self._organism is not None
                and hasattr(self._organism, "memory")
                and self._organism.memory is not None
            ):
                accuracy = self._organism.memory.self_model_accuracy()
                if accuracy < 0.5:
                    return AlgedonicAction(
                        signal_type="self_model_gap",
                        severity="high",
                        description=(
                            f"Self-model accuracy at {accuracy:.0%} — "
                            "organism beliefs diverge from metrics"
                        ),
                        action="recalibrate_from_metrics",
                        metadata={"accuracy": accuracy},
                    )
        except Exception as exc:
            logger.debug("_check_self_model_gap failed (non-fatal): %s", exc)
        return None

    def _check_telos_drift(self, pulse: Any) -> AlgedonicAction | None:
        """Check for divergence from vision.

        Triggers when identity_coherence drops below 0.4
        AND fleet is otherwise healthy (local optimization diverging from telos).
        """
        coherence = getattr(pulse, "identity_coherence", 1.0)
        fleet = getattr(pulse, "fleet_health", 1.0)
        if coherence < 0.4 and fleet > 0.6:
            return AlgedonicAction(
                signal_type="telos_drift",
                severity="critical",
                description=(
                    f"Identity coherence {coherence:.2f} while fleet healthy "
                    f"({fleet:.2f}) — possible telos drift"
                ),
                action="gnani_checkpoint",
                metadata={"coherence": coherence, "fleet_health": fleet},
            )
        return None
