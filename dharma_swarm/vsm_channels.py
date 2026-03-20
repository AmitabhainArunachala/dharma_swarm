"""VSM Nervous System — the missing channels between Beer's 5 systems.

Closes the 5 gaps identified in CLAUDE.md Section VII:

1. S3↔S4 Channel: gates (telos_gates) ←→ zeitgeist feedback loop
2. Sporadic S3*: random audit of agent behavior
3. Algedonic Signal: emergency bypass to Dhyana (operator)
4. Agent-Internal Recursion: agents self-assess S1-S5 health
5. Variety Expansion Protocol: formal process for adding gates

Architecture notes:
  - S1 = Operations (ontology, agents, tasks)
  - S2 = Coordination (message_bus, stigmergy)
  - S3 = Control (telos_gates, evolution, guardrails)
  - S3* = Audit (sporadic random checks)
  - S4 = Intelligence (zeitgeist — outside + future)
  - S5 = Identity (dharma_kernel, identity.py)

Ground: Beer (PILLAR_08), Ashby (requisite variety), Dada Bhagwan (witness).
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Awaitable, Protocol

from pydantic import BaseModel, Field

from dharma_swarm.models import (
    GateDecision,
    GateResult,
    _new_id,
    _utc_now,
)

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Data Models
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class GatePattern(BaseModel):
    """Aggregated gate passage pattern — S3 → S4 signal.

    When gates repeatedly block similar actions, that's a signal about
    the environment. S4 (zeitgeist) should know.
    """

    id: str = Field(default_factory=_new_id)
    gate_name: str
    failure_count: int = 0
    total_checks: int = 0
    failure_rate: float = 0.0
    recent_reasons: list[str] = Field(default_factory=list)
    trending: str = "stable"  # "increasing", "decreasing", "stable"
    timestamp: datetime = Field(default_factory=_utc_now)

    @property
    def is_anomalous(self) -> bool:
        """True if failure rate exceeds expected baseline."""
        return self.failure_rate > 0.3 and self.total_checks >= 5


class AlgedonicSignal(BaseModel):
    """Emergency bypass signal — S1/S2/S3 → S5 (Dhyana).

    Named after Beer's algedonic channel: pain/pleasure signals that
    bypass all intermediate management and go straight to identity.

    Triggers:
      - 3+ consecutive gate failures from same agent
      - System health below critical threshold
      - Ontology integrity violation
      - Evolution stagnation beyond threshold
    """

    id: str = Field(default_factory=_new_id)
    severity: str  # "warning", "critical", "emergency"
    source_system: str  # "S1", "S2", "S3", "S4"
    title: str
    description: str
    recommended_action: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    acknowledged: bool = False
    timestamp: datetime = Field(default_factory=_utc_now)

    @property
    def is_emergency(self) -> bool:
        return self.severity == "emergency"


class AuditResult(BaseModel):
    """S3* sporadic audit result."""

    id: str = Field(default_factory=_new_id)
    agent_id: str
    audit_type: str  # "random_check", "behavior_sample", "output_review"
    passed: bool
    findings: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=_utc_now)


class AgentViability(BaseModel):
    """Agent-internal S1-S5 self-assessment (VSM Gap 4).

    Every agent periodically checks its own viability across all 5 systems.
    """

    agent_id: str
    s1_operations: float = 1.0   # Can I do my job? (task completion rate)
    s2_coordination: float = 1.0  # Am I communicating? (message responsiveness)
    s3_control: float = 1.0      # Am I passing gates? (gate passage rate)
    s4_intelligence: float = 1.0  # Am I aware of context? (context freshness)
    s5_identity: float = 1.0     # Am I aligned with telos? (telos coherence)
    overall: float = 1.0
    timestamp: datetime = Field(default_factory=_utc_now)

    def compute_overall(self) -> float:
        """Geometric mean — all systems must be healthy."""
        values = [self.s1_operations, self.s2_coordination,
                  self.s3_control, self.s4_intelligence, self.s5_identity]
        product = 1.0
        for v in values:
            product *= max(v, 0.01)  # floor to avoid zero-collapse
        self.overall = round(product ** (1.0 / len(values)), 4)
        return self.overall


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GAP 1: S3↔S4 Channel
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class GatePatternAggregator:
    """Aggregates gate check results into patterns for zeitgeist (S3→S4).

    Also receives zeitgeist signals and adjusts gate sensitivity (S4→S3).
    This closes the feedback loop Beer identified as essential.
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or (Path.home() / ".dharma")
        self._log_path = self._state_dir / "meta" / "gate_patterns.jsonl"
        self._gate_stats: dict[str, dict[str, int]] = {}
        self._recent_failures: list[dict[str, Any]] = []
        self._sensitivity_boost: dict[str, float] = {}

    def record_gate_check(
        self,
        gate_name: str,
        result: GateResult,
        action_description: str = "",
        agent_id: str = "",
    ) -> GatePattern | None:
        """Record a gate check and return pattern if anomalous.

        Called after every telos gate evaluation. Accumulates stats and
        fires an S3→S4 signal when patterns emerge.
        """
        if gate_name not in self._gate_stats:
            self._gate_stats[gate_name] = {"pass": 0, "fail": 0, "warn": 0}

        key = result.value.lower()
        self._gate_stats[gate_name][key] = self._gate_stats[gate_name].get(key, 0) + 1

        if result in (GateResult.FAIL, GateResult.WARN):
            self._recent_failures.append({
                "gate": gate_name,
                "result": result.value,
                "action": action_description[:200],
                "agent": agent_id,
                "time": _utc_now().isoformat(),
            })
            # Keep only last 100 failures
            self._recent_failures = self._recent_failures[-100:]

        # Build pattern
        stats = self._gate_stats[gate_name]
        total = sum(stats.values())
        fail_count = stats.get("fail", 0) + stats.get("warn", 0)

        pattern = GatePattern(
            gate_name=gate_name,
            failure_count=fail_count,
            total_checks=total,
            failure_rate=round(fail_count / max(total, 1), 4),
            recent_reasons=[f["action"] for f in self._recent_failures[-5:]
                           if f["gate"] == gate_name],
        )

        if pattern.is_anomalous:
            self._persist_pattern(pattern)
            return pattern
        return None

    def receive_zeitgeist_signal(
        self, signal_category: str, keywords: list[str]
    ) -> None:
        """S4→S3: zeitgeist detects an external threat, boost gate sensitivity.

        When zeitgeist finds competing research or security threats,
        gates tighten temporarily.
        """
        if signal_category == "threat":
            # Boost SATYA (truth) and STEELMAN gates when competition detected
            self._sensitivity_boost["SATYA"] = 0.2
            self._sensitivity_boost["STEELMAN"] = 0.2
            logger.info(
                "S4→S3: Zeitgeist threat signal boosted SATYA+STEELMAN sensitivity"
            )
        elif signal_category == "opportunity":
            # Relax VYAVASTHIT (flow) gate when opportunities detected
            self._sensitivity_boost["VYAVASTHIT"] = -0.1
            logger.info(
                "S4→S3: Zeitgeist opportunity signal relaxed VYAVASTHIT sensitivity"
            )

    def get_sensitivity_boost(self, gate_name: str) -> float:
        """Return current sensitivity adjustment for a gate.

        Positive = stricter, negative = more lenient.
        """
        return self._sensitivity_boost.get(gate_name, 0.0)

    def get_all_patterns(self) -> list[GatePattern]:
        """Return current patterns for all gates."""
        patterns = []
        for gate_name, stats in self._gate_stats.items():
            total = sum(stats.values())
            fail_count = stats.get("fail", 0) + stats.get("warn", 0)
            patterns.append(GatePattern(
                gate_name=gate_name,
                failure_count=fail_count,
                total_checks=total,
                failure_rate=round(fail_count / max(total, 1), 4),
            ))
        return patterns

    def _persist_pattern(self, pattern: GatePattern) -> None:
        """Append anomalous pattern to log."""
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "a") as fh:
            fh.write(pattern.model_dump_json() + "\n")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GAP 2: S3* — Sporadic Audit
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class SporadicAuditor:
    """Random audits of agent behavior — Beer's S3* function.

    S3 (control) tells agents what to do. S3* independently samples
    agent behavior to verify compliance. No agent knows when it will
    be audited.
    """

    def __init__(
        self,
        audit_probability: float = 0.05,
        state_dir: Path | None = None,
    ) -> None:
        self._probability = audit_probability
        self._state_dir = state_dir or (Path.home() / ".dharma")
        self._log_path = self._state_dir / "meta" / "sporadic_audits.jsonl"
        self._results: list[AuditResult] = []

    def should_audit(self) -> bool:
        """Randomly decide whether to audit this action.

        5% chance by default — enough to maintain variety without
        creating overhead.
        """
        return random.random() < self._probability

    async def audit_agent_output(
        self,
        agent_id: str,
        task_description: str,
        output: str,
        gate_results: dict[str, str] | None = None,
    ) -> AuditResult:
        """Audit a single agent output against telos gates.

        Unlike regular gate checks (which the agent initiates),
        this is an independent S3* check. The agent doesn't know
        it's happening.
        """
        findings: list[str] = []

        # Check 1: Output should acknowledge uncertainty (Axiom 2: Epistemic Humility)
        uncertainty_markers = [
            "uncertain", "might", "possibly", "unclear",
            "hypothesis", "confidence", "approximate",
        ]
        has_uncertainty = any(m in output.lower() for m in uncertainty_markers)
        if len(output) > 500 and not has_uncertainty:
            findings.append(
                "Axiom 2 (Epistemic Humility): Long output lacks uncertainty markers"
            )

        # Check 2: Output shouldn't claim capabilities beyond system level
        overmind_violations = [
            "i am conscious", "i understand deeply",
            "i know the answer", "definitely correct",
            "i am certain", "without a doubt",
        ]
        for phrase in overmind_violations:
            if phrase in output.lower():
                findings.append(
                    f"Axiom 14 (Overmind Humility): Overclaiming with '{phrase}'"
                )

        # Check 3: If gate results provided, verify consistency
        if gate_results:
            blocked = [g for g, r in gate_results.items() if r == "FAIL"]
            if blocked and output:
                findings.append(
                    f"Gate consistency: Output produced despite gate blocks: {blocked}"
                )

        passed = len(findings) == 0
        result = AuditResult(
            agent_id=agent_id,
            audit_type="random_check",
            passed=passed,
            findings=findings,
        )

        self._results.append(result)
        self._persist(result)

        if not passed:
            logger.warning(
                "S3* audit FAILED for agent %s: %s",
                agent_id,
                "; ".join(findings),
            )

        return result

    def recent_results(self, limit: int = 20) -> list[AuditResult]:
        """Return recent audit results."""
        return self._results[-limit:]

    def failure_rate(self) -> float:
        """Overall audit failure rate."""
        if not self._results:
            return 0.0
        failed = sum(1 for r in self._results if not r.passed)
        return round(failed / len(self._results), 4)

    def _persist(self, result: AuditResult) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "a") as fh:
            fh.write(result.model_dump_json() + "\n")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GAP 3: Algedonic Signal — Emergency Bypass to S5
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class AlgedonicChannel:
    """Pain/pleasure bypass channel — any system → S5 (Dhyana).

    In Beer's VSM, the algedonic channel carries signals that are too
    urgent for the normal management hierarchy. A frontline worker can
    pull the alarm and it reaches the CEO directly.

    In dharma_swarm: any subsystem can fire an algedonic signal that
    bypasses S2/S3/S4 and reaches the operator (Dhyana) immediately.

    Persistence: ~/.dharma/meta/algedonic.jsonl
    Active signals: ~/.dharma/meta/ALGEDONIC_ACTIVE.md
    """

    # Thresholds that trigger algedonic signals
    GATE_FAILURE_STREAK_THRESHOLD = 3
    HEALTH_CRITICAL_THRESHOLD = 0.3
    EVOLUTION_STAGNATION_CYCLES = 50
    COST_SPIKE_MULTIPLIER = 5.0

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or (Path.home() / ".dharma")
        self._log_path = self._state_dir / "meta" / "algedonic.jsonl"
        self._active_path = self._state_dir / "meta" / "ALGEDONIC_ACTIVE.md"
        self._signals: list[AlgedonicSignal] = []
        self._callbacks: list[Callable[[AlgedonicSignal], Any]] = []

    def register_callback(
        self, callback: Callable[[AlgedonicSignal], Any]
    ) -> None:
        """Register a callback for when algedonic signals fire.

        Callbacks receive the signal and can take immediate action
        (e.g., pause agents, send notification, write to operator log).
        """
        self._callbacks.append(callback)

    async def fire(self, signal: AlgedonicSignal) -> None:
        """Fire an algedonic signal — bypasses all intermediate management.

        This is the computational equivalent of pulling the fire alarm.
        """
        self._signals.append(signal)
        self._persist(signal)
        self._write_active_summary()

        level = "🔴" if signal.is_emergency else "🟡"
        logger.warning(
            "%s ALGEDONIC SIGNAL [%s] from %s: %s",
            level,
            signal.severity,
            signal.source_system,
            signal.title,
        )

        # Invoke all registered callbacks
        for cb in self._callbacks:
            try:
                result = cb(signal)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.error("Algedonic callback failed: %s", exc)

    async def check_gate_streak(
        self,
        agent_id: str,
        consecutive_failures: int,
        gate_name: str = "",
    ) -> None:
        """Check if agent gate failures warrant an algedonic signal."""
        if consecutive_failures >= self.GATE_FAILURE_STREAK_THRESHOLD:
            await self.fire(AlgedonicSignal(
                severity="warning" if consecutive_failures < 5 else "critical",
                source_system="S3",
                title=f"Agent {agent_id}: {consecutive_failures} consecutive gate failures",
                description=(
                    f"Agent {agent_id} has failed {consecutive_failures} gate checks "
                    f"in a row{f' (gate: {gate_name})' if gate_name else ''}. "
                    f"This may indicate a misaligned agent or corrupted task queue."
                ),
                recommended_action="Review agent task queue and recent outputs",
                context={"agent_id": agent_id, "gate_name": gate_name,
                         "streak": consecutive_failures},
            ))

    async def check_health(
        self,
        component: str,
        health_score: float,
    ) -> None:
        """Check if system health warrants an algedonic signal."""
        if health_score < self.HEALTH_CRITICAL_THRESHOLD:
            await self.fire(AlgedonicSignal(
                severity="critical" if health_score < 0.1 else "warning",
                source_system="S1",
                title=f"Critical health: {component} at {health_score:.1%}",
                description=(
                    f"Component {component} health has dropped to {health_score:.1%}. "
                    f"Threshold is {self.HEALTH_CRITICAL_THRESHOLD:.1%}."
                ),
                recommended_action=f"Investigate {component} immediately",
                context={"component": component, "health": health_score},
            ))

    async def check_evolution_stagnation(
        self,
        cycles_without_improvement: int,
        best_fitness: float,
    ) -> None:
        """Check if evolution stagnation warrants an algedonic signal."""
        if cycles_without_improvement >= self.EVOLUTION_STAGNATION_CYCLES:
            await self.fire(AlgedonicSignal(
                severity="warning",
                source_system="S3",
                title=f"Evolution stagnant: {cycles_without_improvement} cycles, best={best_fitness:.4f}",
                description=(
                    f"Darwin Engine has run {cycles_without_improvement} cycles "
                    f"without fitness improvement. Best fitness: {best_fitness:.4f}. "
                    f"The search space may be exhausted or the fitness function inadequate."
                ),
                recommended_action="Consider: restart with higher mutation rate, expand search space, or revise fitness function",
                context={"cycles": cycles_without_improvement, "best_fitness": best_fitness},
            ))

    async def check_cost_spike(
        self,
        current_cost: float,
        rolling_average: float,
    ) -> None:
        """Check if cost spike warrants an algedonic signal."""
        if rolling_average > 0 and current_cost > rolling_average * self.COST_SPIKE_MULTIPLIER:
            await self.fire(AlgedonicSignal(
                severity="critical",
                source_system="S1",
                title=f"Cost spike: ${current_cost:.2f} vs ${rolling_average:.2f} avg",
                description=(
                    f"Current cycle cost ${current_cost:.2f} is "
                    f"{current_cost/rolling_average:.1f}x the rolling average "
                    f"${rolling_average:.2f}. Possible runaway loop or expensive model misroute."
                ),
                recommended_action="Pause agents, check provider routing and task loop",
                context={"current": current_cost, "average": rolling_average},
            ))

    def acknowledge(self, signal_id: str) -> bool:
        """Operator acknowledges an algedonic signal."""
        for sig in self._signals:
            if sig.id == signal_id:
                sig.acknowledged = True
                self._write_active_summary()
                return True
        return False

    @property
    def active_signals(self) -> list[AlgedonicSignal]:
        """Return unacknowledged signals."""
        return [s for s in self._signals if not s.acknowledged]

    @property
    def all_signals(self) -> list[AlgedonicSignal]:
        return list(self._signals)

    def _persist(self, signal: AlgedonicSignal) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "a") as fh:
            fh.write(signal.model_dump_json() + "\n")

    def _write_active_summary(self) -> None:
        """Write active signals to a human-readable file for operator."""
        self._active_path.parent.mkdir(parents=True, exist_ok=True)
        active = self.active_signals
        if not active:
            self._active_path.write_text("# Algedonic Channel\n\nNo active signals. System nominal.\n")
            return

        lines = [
            "# ⚠ ALGEDONIC CHANNEL — ACTIVE SIGNALS\n",
            f"**{len(active)} unacknowledged signal(s)**\n",
        ]
        for sig in active:
            icon = "🔴" if sig.is_emergency else "🟡"
            lines.append(f"## {icon} [{sig.severity.upper()}] {sig.title}")
            lines.append(f"- Source: {sig.source_system}")
            lines.append(f"- Time: {sig.timestamp.strftime('%Y-%m-%d %H:%M UTC')}")
            lines.append(f"- {sig.description}")
            if sig.recommended_action:
                lines.append(f"- **Action**: {sig.recommended_action}")
            lines.append(f"- Signal ID: `{sig.id}` (use to acknowledge)")
            lines.append("")

        self._active_path.write_text("\n".join(lines))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GAP 4: Agent-Internal VSM Recursion
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class AgentViabilityMonitor:
    """Monitors agent-internal S1-S5 viability scores.

    Each agent should periodically self-assess. This monitor
    aggregates those assessments and triggers algedonic signals
    when agents become non-viable.
    """

    def __init__(
        self,
        algedonic: AlgedonicChannel | None = None,
    ) -> None:
        self._viabilities: dict[str, AgentViability] = {}
        self._algedonic = algedonic

    def update(self, viability: AgentViability) -> None:
        """Record an agent's self-assessment."""
        viability.compute_overall()
        self._viabilities[viability.agent_id] = viability

    async def check_all(self) -> list[AgentViability]:
        """Check all agents for non-viable states."""
        non_viable = []
        for agent_id, v in self._viabilities.items():
            if v.overall < 0.4:
                non_viable.append(v)
                if self._algedonic:
                    await self._algedonic.check_health(
                        f"agent/{agent_id}",
                        v.overall,
                    )
        return non_viable

    def get(self, agent_id: str) -> AgentViability | None:
        return self._viabilities.get(agent_id)

    def all_viabilities(self) -> dict[str, AgentViability]:
        return dict(self._viabilities)

    def fleet_health(self) -> float:
        """Geometric mean of all agent viabilities."""
        if not self._viabilities:
            return 1.0
        product = 1.0
        for v in self._viabilities.values():
            product *= max(v.overall, 0.01)
        return round(product ** (1.0 / len(self._viabilities)), 4)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GAP 5: Variety Expansion Protocol
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class GateExpansionProposal(BaseModel):
    """Formal proposal to add or modify a telos gate.

    Ashby's Law: Only variety absorbs variety. When zeitgeist detects
    new threat categories that existing gates don't cover, the system
    can propose new gates.
    """

    id: str = Field(default_factory=_new_id)
    proposed_gate: str
    tier: str  # "A", "B", "C"
    rationale: str
    triggered_by: str  # signal_id or observation
    proposed_check: str  # description of what the gate checks
    status: str = "proposed"  # "proposed", "approved", "rejected", "implemented"
    reviewed_by: str = ""
    timestamp: datetime = Field(default_factory=_utc_now)


class VarietyExpansionProtocol:
    """Formal process for expanding the gate array.

    Gates are not arbitrary — each one must trace to a principle.
    This protocol ensures new gates go through proper review.
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or (Path.home() / ".dharma")
        self._proposals_path = self._state_dir / "meta" / "gate_proposals.jsonl"
        self._proposals: list[GateExpansionProposal] = []

    def propose(
        self,
        gate_name: str,
        tier: str,
        rationale: str,
        triggered_by: str = "",
        proposed_check: str = "",
    ) -> GateExpansionProposal:
        """Submit a gate expansion proposal.

        Ground: Ashby (requisite variety), Beer (S5 approves new gates).
        """
        proposal = GateExpansionProposal(
            proposed_gate=gate_name,
            tier=tier,
            rationale=rationale,
            triggered_by=triggered_by,
            proposed_check=proposed_check,
        )
        self._proposals.append(proposal)
        self._persist(proposal)
        logger.info(
            "Gate expansion proposed: %s (tier %s) — %s",
            gate_name, tier, rationale[:80],
        )
        return proposal

    def approve(self, proposal_id: str, reviewer: str = "dhyana") -> bool:
        """S5 (Dhyana) approves a gate proposal."""
        for p in self._proposals:
            if p.id == proposal_id:
                p.status = "approved"
                p.reviewed_by = reviewer
                return True
        return False

    def reject(self, proposal_id: str, reviewer: str = "dhyana") -> bool:
        """S5 (Dhyana) rejects a gate proposal."""
        for p in self._proposals:
            if p.id == proposal_id:
                p.status = "rejected"
                p.reviewed_by = reviewer
                return True
        return False

    @property
    def pending(self) -> list[GateExpansionProposal]:
        return [p for p in self._proposals if p.status == "proposed"]

    @property
    def approved(self) -> list[GateExpansionProposal]:
        return [p for p in self._proposals if p.status == "approved"]

    def _persist(self, proposal: GateExpansionProposal) -> None:
        self._proposals_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._proposals_path, "a") as fh:
            fh.write(proposal.model_dump_json() + "\n")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Unified VSM Coordinator
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class VSMCoordinator:
    """Central coordinator wiring all 5 VSM gaps together.

    This is the nervous system of the organism. It connects:
    - GatePatternAggregator (S3→S4)
    - ZeitgeistScanner (S4) → back-pressure on gates (S4→S3)
    - SporadicAuditor (S3*)
    - AlgedonicChannel (any → S5)
    - AgentViabilityMonitor (agent-internal recursion)
    - VarietyExpansionProtocol (gate evolution)

    Usage:
        vsm = VSMCoordinator()
        # Wire into existing systems:
        vsm.on_gate_check("AHIMSA", GateResult.PASS, "safe action")
        vsm.on_agent_output(agent_id, task, output, gate_results)
        await vsm.run_zeitgeist_cycle()
        await vsm.check_fleet_viability()
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or (Path.home() / ".dharma")

        # Initialize all subsystems
        self.algedonic = AlgedonicChannel(self._state_dir)
        self.gate_patterns = GatePatternAggregator(self._state_dir)
        self.auditor = SporadicAuditor(state_dir=self._state_dir)
        self.viability = AgentViabilityMonitor(algedonic=self.algedonic)
        self.variety = VarietyExpansionProtocol(self._state_dir)

        # Agent failure tracking for algedonic
        self._agent_failure_streaks: dict[str, int] = {}

    def on_gate_check(
        self,
        gate_name: str,
        result: GateResult,
        action_description: str = "",
        agent_id: str = "",
    ) -> GatePattern | None:
        """Hook: called after every gate check.

        Wires into telos_gates.py — add this call after evaluate().
        """
        pattern = self.gate_patterns.record_gate_check(
            gate_name, result, action_description, agent_id,
        )

        # Track failure streaks for algedonic
        if agent_id:
            if result == GateResult.FAIL:
                self._agent_failure_streaks[agent_id] = (
                    self._agent_failure_streaks.get(agent_id, 0) + 1
                )
            else:
                self._agent_failure_streaks[agent_id] = 0

        return pattern

    async def on_agent_output(
        self,
        agent_id: str,
        task_description: str,
        output: str,
        gate_results: dict[str, str] | None = None,
    ) -> AuditResult | None:
        """Hook: called after agent produces output.

        Randomly triggers S3* audit.
        """
        # Check if algedonic needed for gate streak
        streak = self._agent_failure_streaks.get(agent_id, 0)
        if streak >= AlgedonicChannel.GATE_FAILURE_STREAK_THRESHOLD:
            await self.algedonic.check_gate_streak(agent_id, streak)

        # Sporadic audit
        if self.auditor.should_audit():
            return await self.auditor.audit_agent_output(
                agent_id, task_description, output, gate_results,
            )
        return None

    async def run_zeitgeist_feedback(
        self, signals: list[Any]
    ) -> None:
        """Process zeitgeist signals and feed back to gates (S4→S3)."""
        for signal in signals:
            if hasattr(signal, "category") and hasattr(signal, "keywords"):
                self.gate_patterns.receive_zeitgeist_signal(
                    signal.category, signal.keywords,
                )

        # Check if any signals warrant gate expansion proposals
        threat_signals = [
            s for s in signals
            if hasattr(s, "category") and s.category == "threat"
        ]
        if len(threat_signals) >= 3:
            self.variety.propose(
                gate_name="EMERGING_THREAT",
                tier="C",
                rationale=f"Zeitgeist detected {len(threat_signals)} threat signals in one scan cycle",
                triggered_by="zeitgeist_scan",
                proposed_check="Check proposed actions against newly detected threat patterns",
            )

    def status(self) -> dict[str, Any]:
        """Return full VSM nervous system status."""
        return {
            "algedonic_active": len(self.algedonic.active_signals),
            "algedonic_total": len(self.algedonic.all_signals),
            "gate_patterns": len(self.gate_patterns.get_all_patterns()),
            "audit_failure_rate": self.auditor.failure_rate(),
            "fleet_health": self.viability.fleet_health(),
            "pending_gate_proposals": len(self.variety.pending),
            "agent_failure_streaks": dict(self._agent_failure_streaks),
        }
