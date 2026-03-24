"""Strange Loop — the organism's recursive self-modification engine.

The simplest possible strange loop:
  observe → diagnose → propose → evaluate → apply → measure → keep/revert

The organism watches itself, proposes changes to its own parameters,
tests them against reality, and keeps what works. The Gnani Field
evaluates proposals before application.

This is the seed of recursive self-improvement. It traverses the full
stack: the organism modifies its own config → which changes how it routes,
scales, and evaluates → which changes what it observes → which changes
what it proposes next.

Ground: Hofstadter (strange loops — self-reference that traverses levels),
        Darwin-Gödel Machine (self-modification with proof surrogates),
        Karpathy autoresearch (optimize-or-revert loop).
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _make_id() -> str:
    """Generate a short unique ID."""
    return uuid.uuid4().hex[:12]


@dataclass
class OrganismConfig:
    """Tunable parameters the organism can mutate about itself."""
    routing_bias: float = 0.0               # Bias toward higher-tier models (0.0-0.5)
    scaling_health_threshold: float = 0.3   # Fleet health below this triggers scaling
    scaling_consecutive_unhealthy: int = 3  # Consecutive unhealthy pulses before scaling
    algedonic_failure_threshold: float = 0.5  # Failure rate above this triggers pain
    algedonic_divergence_threshold: float = 0.4  # Omega divergence above this triggers pain
    algedonic_drift_threshold: float = 0.4  # Identity coherence below this triggers pain
    heartbeat_interval: float = 60.0        # Seconds between heartbeats
    stigmergy_salience_threshold: float = 0.8  # Salience above this harvests stigmergy
    evolution_gnani_stagnation: int = 5     # Stagnation cycles before Gnani checkpoint


@dataclass
class Mutation:
    """A proposed change to an organism parameter."""
    id: str
    parameter: str      # Name of the OrganismConfig field
    old_value: Any      # Value before mutation
    new_value: Any      # Proposed new value
    reason: str         # Why this mutation was proposed
    proposed_at: datetime
    applied_at: datetime | None = None
    reverted_at: datetime | None = None
    pre_metrics: dict = field(default_factory=dict)   # Metrics before application
    post_metrics: dict = field(default_factory=dict)  # Metrics after measurement
    gnani_verdict: bool | None = None                 # Did Gnani approve?
    kept: bool | None = None                          # Final decision

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "id": self.id,
            "parameter": self.parameter,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "reason": self.reason,
            "proposed_at": self.proposed_at.isoformat(),
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "reverted_at": self.reverted_at.isoformat() if self.reverted_at else None,
            "pre_metrics": self.pre_metrics,
            "post_metrics": self.post_metrics,
            "gnani_verdict": self.gnani_verdict,
            "kept": self.kept,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Mutation":
        """Reconstruct from a dict."""
        proposed_at = datetime.fromisoformat(d["proposed_at"])
        applied_at = datetime.fromisoformat(d["applied_at"]) if d.get("applied_at") else None
        reverted_at = datetime.fromisoformat(d["reverted_at"]) if d.get("reverted_at") else None
        return cls(
            id=d["id"],
            parameter=d["parameter"],
            old_value=d["old_value"],
            new_value=d["new_value"],
            reason=d["reason"],
            proposed_at=proposed_at,
            applied_at=applied_at,
            reverted_at=reverted_at,
            pre_metrics=d.get("pre_metrics", {}),
            post_metrics=d.get("post_metrics", {}),
            gnani_verdict=d.get("gnani_verdict"),
            kept=d.get("kept"),
        )


class StrangeLoop:
    """The organism's recursive self-modification engine.

    Call `tick()` from the organism heartbeat every N cycles.
    It will observe, diagnose, propose, evaluate, apply, and eventually
    measure and keep/revert.
    """

    def __init__(self, organism: Any, config: OrganismConfig | None = None) -> None:
        self._organism = organism
        self.config = config or OrganismConfig()
        self._mutations: list[Mutation] = []
        self._pending_mutation: Mutation | None = None  # Currently being tested
        self._measurement_countdown: int = 0  # Heartbeats until measurement
        self._tick_interval: int = 10  # Run strange loop every N heartbeats
        self._measurement_window: int = 5  # Measure for N heartbeats after applying
        self._load()

    def tick(self, cycle_number: int, pulse_history: list) -> str:
        """Main strange loop tick. Returns status string.

        States:
        - "idle": No pending mutation, checking if we should propose
        - "proposed": Mutation proposed and evaluated by Gnani
        - "testing": Mutation applied, measuring effects
        - "decided": Measurement complete, kept or reverted
        """
        # If there's a pending mutation being tested, check measurement
        if self._pending_mutation is not None:
            if self._measurement_countdown <= 0:
                return self._measure_and_decide(pulse_history)
            else:
                self._measurement_countdown -= 1
                return "testing"

        # Otherwise, try to propose a new mutation
        if cycle_number % self._tick_interval != 0:
            return "idle"

        return self._observe_diagnose_propose(pulse_history)

    def _observe_diagnose_propose(self, pulse_history: list) -> str:
        """Observe pulse history, diagnose problems, propose a mutation."""
        if len(pulse_history) < 5:
            return "idle"  # Not enough data

        recent = pulse_history[-10:]

        # Compute summary metrics
        avg_health = sum(p.fleet_health for p in recent) / len(recent)
        avg_coherence = sum(p.identity_coherence for p in recent) / len(recent)
        avg_failure = sum(p.audit_failure_rate for p in recent) / len(recent)
        unhealthy_ratio = sum(1 for p in recent if not p.is_healthy) / len(recent)

        # Diagnose: which parameter should change?
        proposal = None

        if avg_failure > self.config.algedonic_failure_threshold and self.config.routing_bias < 0.4:
            # High failure rate → increase routing bias (use smarter models)
            new_bias = min(self.config.routing_bias + 0.05, 0.5)
            proposal = Mutation(
                id=_make_id(),
                parameter="routing_bias",
                old_value=self.config.routing_bias,
                new_value=new_bias,
                reason=f"Avg failure rate {avg_failure:.2f} > threshold {self.config.algedonic_failure_threshold}",
                proposed_at=datetime.now(timezone.utc),
            )
        elif unhealthy_ratio > 0.5 and self.config.scaling_health_threshold > 0.2:
            # Frequently unhealthy → lower scaling threshold (trigger scaling sooner)
            new_threshold = max(self.config.scaling_health_threshold - 0.05, 0.15)
            proposal = Mutation(
                id=_make_id(),
                parameter="scaling_health_threshold",
                old_value=self.config.scaling_health_threshold,
                new_value=new_threshold,
                reason=f"Unhealthy ratio {unhealthy_ratio:.2f} — lower scaling threshold",
                proposed_at=datetime.now(timezone.utc),
            )
        elif avg_health > 0.8 and avg_failure < 0.1 and self.config.routing_bias > 0.05:
            # Very healthy, low failure → decrease routing bias (save cost)
            new_bias = max(self.config.routing_bias - 0.05, 0.0)
            proposal = Mutation(
                id=_make_id(),
                parameter="routing_bias",
                old_value=self.config.routing_bias,
                new_value=new_bias,
                reason=(
                    f"Healthy (avg_health={avg_health:.2f}, avg_failure={avg_failure:.2f})"
                    " — reduce routing bias to save cost"
                ),
                proposed_at=datetime.now(timezone.utc),
            )

        if proposal is None:
            return "idle"

        # Evaluate via Gnani checkpoint
        try:
            if hasattr(self._organism, 'attractor') and self._organism.attractor is not None:
                verdict = self._organism.attractor.gnani_checkpoint(
                    f"Self-mutation: change {proposal.parameter} from {proposal.old_value} "
                    f"to {proposal.new_value}. Reason: {proposal.reason}",
                    {
                        "parameter": proposal.parameter,
                        "old": proposal.old_value,
                        "new": proposal.new_value,
                    },
                )
                proposal.gnani_verdict = verdict.proceed
                if not verdict.proceed:
                    # Gnani says HOLD — record and skip
                    self._mutations.append(proposal)
                    self._record_to_memory(proposal, "gnani_held")
                    self._save()
                    return "held_by_gnani"
            else:
                proposal.gnani_verdict = True  # No Gnani → proceed
        except Exception:
            proposal.gnani_verdict = True  # Gnani error → proceed

        # Apply the mutation
        self._apply_mutation(proposal)
        proposal.applied_at = datetime.now(timezone.utc)
        proposal.pre_metrics = self._snapshot_metrics(pulse_history)
        self._pending_mutation = proposal
        self._measurement_countdown = self._measurement_window
        self._record_to_memory(proposal, "applied")
        self._save()

        return "proposed_and_applied"

    def _apply_mutation(self, mutation: Mutation) -> None:
        """Apply a mutation to the organism's config."""
        setattr(self.config, mutation.parameter, mutation.new_value)
        # Also apply to the actual organism subsystem
        self._sync_config_to_organism()

    def _revert_mutation(self, mutation: Mutation) -> None:
        """Revert a mutation."""
        setattr(self.config, mutation.parameter, mutation.old_value)
        mutation.reverted_at = datetime.now(timezone.utc)
        self._sync_config_to_organism()

    def _sync_config_to_organism(self) -> None:
        """Push current config values to the organism's subsystems."""
        try:
            org = self._organism
            if org is not None and hasattr(org, 'router') and org.router is not None:
                org.router._routing_bias = self.config.routing_bias
        except Exception:
            pass

    def _measure_and_decide(self, pulse_history: list) -> str:
        """Compare pre/post metrics and decide to keep or revert."""
        mutation = self._pending_mutation
        if mutation is None:
            return "idle"

        mutation.post_metrics = self._snapshot_metrics(pulse_history)

        # Compare: did the metric the mutation targeted improve?
        pre = mutation.pre_metrics
        post = mutation.post_metrics

        improved = False
        if mutation.parameter == "routing_bias":
            # Check if failure rate decreased
            improved = post.get("avg_failure", 1.0) < pre.get("avg_failure", 1.0)
            # Or if we were reducing bias and health stayed good
            if mutation.new_value < mutation.old_value:
                improved = post.get("avg_health", 0.0) > 0.6
        elif mutation.parameter == "scaling_health_threshold":
            improved = post.get("unhealthy_ratio", 1.0) < pre.get("unhealthy_ratio", 1.0)
        else:
            # Generic: overall health improved or stayed stable
            improved = post.get("avg_health", 0.0) >= pre.get("avg_health", 0.0)

        mutation.kept = improved

        if improved:
            logger.info(
                "STRANGE LOOP: KEEPING mutation %s (%s: %s → %s)",
                mutation.id[:8], mutation.parameter, mutation.old_value, mutation.new_value,
            )
        else:
            self._revert_mutation(mutation)
            logger.info(
                "STRANGE LOOP: REVERTING mutation %s (%s: %s → %s, back to %s)",
                mutation.id[:8], mutation.parameter, mutation.old_value,
                mutation.new_value, mutation.old_value,
            )

        self._mutations.append(mutation)
        self._pending_mutation = None
        self._record_to_memory(mutation, "kept" if improved else "reverted")
        self._save()

        return "kept" if improved else "reverted"

    def _snapshot_metrics(self, pulse_history: list) -> dict:
        """Compute summary metrics from recent pulse history."""
        recent = pulse_history[-self._measurement_window:] if pulse_history else []
        if not recent:
            return {}
        return {
            "avg_health": sum(p.fleet_health for p in recent) / len(recent),
            "avg_coherence": sum(p.identity_coherence for p in recent) / len(recent),
            "avg_failure": sum(p.audit_failure_rate for p in recent) / len(recent),
            "unhealthy_ratio": sum(1 for p in recent if not p.is_healthy) / len(recent),
        }

    def _record_to_memory(self, mutation: Mutation, event: str) -> None:
        """Record mutation event to organism memory."""
        try:
            if hasattr(self._organism, 'memory') and self._organism.memory is not None:
                self._organism.memory.record_event(
                    entity_type="mutation",
                    description=(
                        f"Strange loop {event}: {mutation.parameter} "
                        f"{mutation.old_value}→{mutation.new_value} ({mutation.reason})"
                    ),
                    metadata={
                        "mutation_id": mutation.id,
                        "parameter": mutation.parameter,
                        "old_value": mutation.old_value,
                        "new_value": mutation.new_value,
                        "event": event,
                        "gnani_verdict": mutation.gnani_verdict,
                        "kept": mutation.kept,
                    },
                )
        except Exception:
            pass

    def _get_mutations_path(self) -> Path | None:
        """Get the path for the mutations JSONL file."""
        try:
            org = self._organism
            if org is not None and hasattr(org, '_state_dir') and org._state_dir is not None:
                state_dir = Path(org._state_dir)
                mutations_dir = state_dir / "organism_memory"
                mutations_dir.mkdir(parents=True, exist_ok=True)
                return mutations_dir / "mutations.jsonl"
        except Exception:
            pass
        return None

    def _save(self) -> None:
        """Persist mutation history to disk."""
        path = self._get_mutations_path()
        if path is None:
            return
        try:
            lines = []
            for m in self._mutations:
                lines.append(json.dumps(m.to_dict()))
            # Also save pending mutation if any
            if self._pending_mutation is not None:
                d = self._pending_mutation.to_dict()
                d["_pending"] = True
                lines.append(json.dumps(d))
            path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        except Exception as exc:
            logger.debug("StrangeLoop save failed (non-fatal): %s", exc)

    def _load(self) -> None:
        """Load mutation history from disk."""
        path = self._get_mutations_path()
        if path is None or not path.exists():
            return
        try:
            self._mutations = []
            self._pending_mutation = None
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    is_pending = d.pop("_pending", False)
                    mutation = Mutation.from_dict(d)
                    if is_pending:
                        self._pending_mutation = mutation
                        # Restore countdown to 0 so it will be measured next tick
                        self._measurement_countdown = 0
                    else:
                        self._mutations.append(mutation)
                except Exception as exc:
                    logger.debug("StrangeLoop load: skipping malformed line: %s", exc)
        except Exception as exc:
            logger.debug("StrangeLoop load failed (non-fatal): %s", exc)

    @property
    def stats(self) -> dict:
        """Strange loop statistics."""
        total = len(self._mutations)
        kept = sum(1 for m in self._mutations if m.kept is True)
        reverted = sum(1 for m in self._mutations if m.kept is False)
        held = sum(1 for m in self._mutations if m.gnani_verdict is False)
        return {
            "total_mutations": total,
            "kept": kept,
            "reverted": reverted,
            "held_by_gnani": held,
            "pending": self._pending_mutation is not None,
            "current_config": {
                "routing_bias": self.config.routing_bias,
                "scaling_health_threshold": self.config.scaling_health_threshold,
                "algedonic_failure_threshold": self.config.algedonic_failure_threshold,
            },
        }
