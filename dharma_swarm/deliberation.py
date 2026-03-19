"""S3-S4-S5 Deliberation Triangle — the missing VSM wiring.

Beer's VSM requires bidirectional communication:
  S4 (zeitgeist) sends intelligence → S3 (telos_gates)
  S3 (telos_gates) sends operational patterns → S4 (zeitgeist)
  S5 (identity) arbitrates when S3 and S4 disagree

This module implements all three channels plus the triangle protocol
that uses them together for slow-path deliberation.

Grounded in: SYNTHESIS.md Sprint 3, Principles #8 (S3-S4-S5 triangle)
Sources: Beer VSM, Conant-Ashby Good Regulator, dharma_swarm identity.py
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Message types for inter-system communication
# ---------------------------------------------------------------------------

class MessageDirection(str, Enum):
    S4_TO_S3 = "s4_to_s3"  # Intelligence → Control
    S3_TO_S4 = "s3_to_s4"  # Operational patterns → Intelligence
    S5_ARBITRATION = "s5_arbitration"  # Identity → Resolution


class IntelligenceType(str, Enum):
    """S4 → S3: Types of intelligence reports."""
    THREAT = "threat"               # External competitive/security threat
    OPPORTUNITY = "opportunity"     # Window of action
    METHODOLOGY = "methodology"     # New technique relevant to work
    CONSTRAINT_CHANGE = "constraint_change"  # Environment shifted


class OperationalPattern(str, Enum):
    """S3 → S4: Types of operational patterns."""
    GATE_FAILURE_SPIKE = "gate_failure_spike"  # Many actions being blocked
    CONSTRAINT_TENSION = "constraint_tension"  # Gates blocking useful work
    NOVEL_ACTION_TYPE = "novel_action_type"    # Unknown action patterns appearing
    BUDGET_PRESSURE = "budget_pressure"        # Cost constraints tightening


@dataclass
class S4Message:
    """Intelligence report from zeitgeist (S4) to telos gates (S3).

    "Here's what's happening in the environment that should affect
    how you evaluate actions."
    """
    intelligence_type: IntelligenceType
    title: str
    description: str = ""
    relevance: float = 0.5  # [0,1]
    keywords: list[str] = field(default_factory=list)
    recommended_gate_adjustment: str = ""  # e.g., "tighten SATYA", "relax REVERSIBILITY"
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class S3Message:
    """Operational pattern report from telos gates (S3) to zeitgeist (S4).

    "Here's what's happening operationally that should inform your
    environmental scanning priorities."
    """
    pattern_type: OperationalPattern
    description: str = ""
    gate_name: str = ""
    failure_rate: float = 0.0  # [0,1] — recent gate failure rate
    blocked_action_types: list[str] = field(default_factory=list)
    recommended_scan_focus: str = ""  # e.g., "scan for security threats"
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# S3-S4 Bidirectional Channel
# ---------------------------------------------------------------------------

class S3S4Channel:
    """Bidirectional communication channel between S3 (control) and S4 (intelligence).

    The channel buffers messages and provides query methods so each
    system can read what the other has sent.

    Usage::

        channel = S3S4Channel()

        # S4 sends intelligence to S3
        channel.send_intelligence(S4Message(
            intelligence_type=IntelligenceType.THREAT,
            title="Competing R_V paper on arxiv",
            relevance=0.9,
        ))

        # S3 reads pending intelligence
        threats = channel.pending_intelligence(IntelligenceType.THREAT)

        # S3 sends operational patterns to S4
        channel.send_pattern(S3Message(
            pattern_type=OperationalPattern.GATE_FAILURE_SPIKE,
            gate_name="REVERSIBILITY",
            failure_rate=0.4,
        ))

        # S4 reads patterns to adjust scanning
        patterns = channel.pending_patterns()
    """

    def __init__(self, persist_dir: Path | None = None) -> None:
        self._intelligence_buffer: list[S4Message] = []
        self._pattern_buffer: list[S3Message] = []
        self._persist_dir = persist_dir or (Path.home() / ".dharma" / "deliberation")

    def send_intelligence(self, msg: S4Message) -> None:
        """S4 sends intelligence report to S3."""
        self._intelligence_buffer.append(msg)
        self._persist("s4_to_s3", msg.__dict__)
        logger.debug("S4→S3: %s — %s", msg.intelligence_type.value, msg.title)

    def send_pattern(self, msg: S3Message) -> None:
        """S3 sends operational pattern to S4."""
        self._pattern_buffer.append(msg)
        self._persist("s3_to_s4", msg.__dict__)
        logger.debug("S3→S4: %s — %s", msg.pattern_type.value, msg.description)

    def pending_intelligence(
        self, filter_type: IntelligenceType | None = None
    ) -> list[S4Message]:
        """Read pending intelligence messages (S4 → S3 direction)."""
        if filter_type:
            return [m for m in self._intelligence_buffer if m.intelligence_type == filter_type]
        return list(self._intelligence_buffer)

    def pending_patterns(
        self, filter_type: OperationalPattern | None = None
    ) -> list[S3Message]:
        """Read pending operational patterns (S3 → S4 direction)."""
        if filter_type:
            return [m for m in self._pattern_buffer if m.pattern_type == filter_type]
        return list(self._pattern_buffer)

    def drain_intelligence(self) -> list[S4Message]:
        """Read and clear all pending intelligence messages."""
        msgs = list(self._intelligence_buffer)
        self._intelligence_buffer.clear()
        return msgs

    def drain_patterns(self) -> list[S3Message]:
        """Read and clear all pending pattern messages."""
        msgs = list(self._pattern_buffer)
        self._pattern_buffer.clear()
        return msgs

    def _persist(self, direction: str, data: dict[str, Any]) -> None:
        """Append message to JSONL log for audit trail."""
        try:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            log_file = self._persist_dir / f"{direction}.jsonl"
            with open(log_file, "a") as f:
                f.write(json.dumps(data, default=str) + "\n")
        except Exception:
            pass  # Channel must never block


# ---------------------------------------------------------------------------
# S5 Arbitration Protocol
# ---------------------------------------------------------------------------

class DisagreementType(str, Enum):
    """Types of S3-S4 disagreement."""
    S3_BLOCKS_S4_WANTS = "s3_blocks_s4_wants"  # Gates block, but intelligence says opportunity
    S3_ALLOWS_S4_WARNS = "s3_allows_s4_warns"  # Gates allow, but intelligence says threat
    BOTH_UNCERTAIN = "both_uncertain"           # Neither system has clear signal


@dataclass
class ArbitrationRequest:
    """Request for S5 to resolve an S3-S4 disagreement."""
    disagreement_type: DisagreementType
    action_description: str
    s3_position: str  # "block" or "allow"
    s3_reason: str
    s4_position: str  # "opportunity" or "threat" or "neutral"
    s4_reason: str
    telos_context: str = ""  # What's the telos-relevant context?


@dataclass
class ArbitrationResult:
    """S5's resolution of an S3-S4 disagreement."""
    decision: str  # "proceed", "block", "defer", "modify"
    reason: str
    tcs_at_decision: float = 0.5  # TCS at time of arbitration
    identity_regime: str = "stable"
    conditions: list[str] = field(default_factory=list)  # Conditions for proceeding
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class S5Arbitrator:
    """S5 identity-based arbitration for S3-S4 disagreements.

    When S3 (control) and S4 (intelligence) disagree about an action,
    S5 (identity) breaks the tie based on telos alignment and identity
    coherence.

    The arbitration is NOT a simple tiebreaker. It uses identity context:
    - What regime is the system in? (stable → more permissive, drifting → more conservative)
    - What's the telos alignment? (aligned → favor action, misaligned → favor block)
    - What's the TCS? (high → trust the system, low → be cautious)
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or (Path.home() / ".dharma")

    def arbitrate(self, request: ArbitrationRequest) -> ArbitrationResult:
        """Resolve an S3-S4 disagreement.

        The arbitration logic:

        1. If identity is CRITICAL → always side with S3 (conservative)
        2. If S3 blocks + S4 sees opportunity:
           - If telos-aligned → proceed with conditions
           - If not telos-aligned → block
        3. If S3 allows + S4 warns threat:
           - If threat is high-relevance → block
           - If threat is low-relevance → proceed with monitoring
        4. If both uncertain → defer (gather more information)
        """
        tcs = self._get_current_tcs()
        regime = self._get_regime(tcs)

        # Rule 1: Critical identity → always conservative
        if regime == "critical":
            return ArbitrationResult(
                decision="block",
                reason=f"Identity in CRITICAL regime (TCS={tcs:.3f}). Defaulting to conservative S3 position.",
                tcs_at_decision=tcs,
                identity_regime=regime,
            )

        # Rule 2: S3 blocks, S4 sees opportunity
        if request.disagreement_type == DisagreementType.S3_BLOCKS_S4_WANTS:
            if regime == "stable" and tcs > 0.6:
                # System is healthy → trust S4's intelligence
                return ArbitrationResult(
                    decision="proceed",
                    reason=f"S4 intelligence overrides S3 block. System stable (TCS={tcs:.3f}). {request.s4_reason}",
                    tcs_at_decision=tcs,
                    identity_regime=regime,
                    conditions=[
                        "Monitor outcome closely",
                        "Revert if prediction error > 0.5",
                        "Record as experience for fast path learning",
                    ],
                )
            elif regime == "drifting":
                # System drifting → side with S3 conservatism
                return ArbitrationResult(
                    decision="block",
                    reason=f"Identity drifting (TCS={tcs:.3f}). Siding with S3 control. {request.s3_reason}",
                    tcs_at_decision=tcs,
                    identity_regime=regime,
                )
            else:
                # Moderate TCS → proceed with extra conditions
                return ArbitrationResult(
                    decision="modify",
                    reason=f"Moderate TCS ({tcs:.3f}). Proceed with safeguards.",
                    tcs_at_decision=tcs,
                    identity_regime=regime,
                    conditions=[
                        "Reduce blast radius to minimum viable",
                        "Checkpoint before execution",
                        "Auto-revert on any gate failure",
                    ],
                )

        # Rule 3: S3 allows, S4 warns threat
        if request.disagreement_type == DisagreementType.S3_ALLOWS_S4_WARNS:
            if regime == "stable" and tcs > 0.7:
                # System very healthy → proceed but with monitoring
                return ArbitrationResult(
                    decision="proceed",
                    reason=f"S3 allows and system strong (TCS={tcs:.3f}). Proceed with threat monitoring.",
                    tcs_at_decision=tcs,
                    identity_regime=regime,
                    conditions=[
                        f"Monitor for: {request.s4_reason}",
                        "Increase zeitgeist scan frequency temporarily",
                    ],
                )
            else:
                # Not confident → block
                return ArbitrationResult(
                    decision="block",
                    reason=f"S4 threat warning with moderate TCS ({tcs:.3f}). {request.s4_reason}",
                    tcs_at_decision=tcs,
                    identity_regime=regime,
                )

        # Rule 4: Both uncertain → defer
        return ArbitrationResult(
            decision="defer",
            reason=f"Both S3 and S4 uncertain (TCS={tcs:.3f}). Deferring to information gathering.",
            tcs_at_decision=tcs,
            identity_regime=regime,
            conditions=["Run epistemic action first", "Gather more context before deciding"],
        )

    def _get_current_tcs(self) -> float:
        """Read current TCS from identity history."""
        history_path = self._state_dir / "meta" / "identity_history.jsonl"
        if not history_path.exists():
            return 0.5

        try:
            lines = history_path.read_text().strip().splitlines()
            if lines:
                last = json.loads(lines[-1])
                return float(last.get("tcs", 0.5))
        except Exception:
            pass
        return 0.5

    def _get_regime(self, tcs: float) -> str:
        """Classify identity regime from TCS."""
        if tcs < 0.25:
            return "critical"
        elif tcs < 0.4:
            return "drifting"
        return "stable"


# ---------------------------------------------------------------------------
# The Deliberation Triangle
# ---------------------------------------------------------------------------

@dataclass
class DeliberationInput:
    """Input to the full deliberation triangle."""
    action_type: str
    action_description: str
    target: str = ""
    content: str = ""
    domains: list[str] = field(default_factory=list)
    is_external: bool = False


@dataclass
class DeliberationOutput:
    """Output from the full deliberation triangle."""
    decision: str  # "allow", "block", "review", "defer"
    reason: str
    s3_result: dict[str, Any] = field(default_factory=dict)
    s4_signals: list[dict[str, Any]] = field(default_factory=list)
    s5_arbitration: dict[str, Any] | None = None
    used_arbitration: bool = False
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class DeliberationTriangle:
    """The full S3-S4-S5 deliberation protocol.

    This is the SLOW PATH from the complexity router. Used when an
    action is novel, cross-domain, or high-stakes.

    Protocol:
    1. S4 scans for relevant intelligence
    2. S3 runs gate checks (informed by S4 intelligence)
    3. If S3 and S4 agree → return result
    4. If S3 and S4 disagree → S5 arbitrates

    Usage::

        triangle = DeliberationTriangle(gatekeeper, scanner, channel, arbitrator)
        result = triangle.deliberate(DeliberationInput(
            action_type="deploy_to_production",
            action_description="Push v0.3.0 to AGNI",
        ))
    """

    def __init__(
        self,
        gatekeeper: Any = None,  # TelosGatekeeper — lazy to avoid circular
        scanner: Any = None,     # ZeitgeistScanner — lazy
        channel: S3S4Channel | None = None,
        arbitrator: S5Arbitrator | None = None,
    ) -> None:
        self._gatekeeper = gatekeeper
        self._scanner = scanner
        self.channel = channel or S3S4Channel()
        self.arbitrator = arbitrator or S5Arbitrator()

    def _get_gatekeeper(self) -> Any:
        if self._gatekeeper is None:
            from dharma_swarm.telos_gates import TelosGatekeeper
            self._gatekeeper = TelosGatekeeper()
        return self._gatekeeper

    def _get_scanner(self) -> Any:
        if self._scanner is None:
            from dharma_swarm.zeitgeist import ZeitgeistScanner
            self._scanner = ZeitgeistScanner()
        return self._scanner

    def deliberate(self, input: DeliberationInput) -> DeliberationOutput:
        """Run the full S3-S4-S5 deliberation protocol.

        Returns a DeliberationOutput with the combined decision.
        """
        # Step 1: Check S4 intelligence (from channel buffer)
        intelligence = self.channel.pending_intelligence()
        s4_position = "neutral"
        s4_reason = "No pending intelligence"
        action_terms = self._action_terms(input)

        # Check if any intelligence is relevant to this action
        relevant_intel = []
        for msg in intelligence:
            if self._message_is_relevant(msg, action_terms):
                relevant_intel.append(msg)

        if relevant_intel:
            # Aggregate S4 position from relevant intelligence
            threats = [m for m in relevant_intel if m.intelligence_type == IntelligenceType.THREAT]
            opportunities = [m for m in relevant_intel if m.intelligence_type == IntelligenceType.OPPORTUNITY]

            if threats and not opportunities:
                s4_position = "threat"
                s4_reason = "; ".join(m.title for m in threats[:3])
            elif opportunities and not threats:
                s4_position = "opportunity"
                s4_reason = "; ".join(m.title for m in opportunities[:3])
            else:
                s4_position = "mixed"
                s4_reason = f"{len(threats)} threats, {len(opportunities)} opportunities"

        # Step 2: Run S3 gate check
        gatekeeper = self._get_gatekeeper()
        s3_result = gatekeeper.check(
            action=input.action_description,
            content=input.content,
        )
        s3_position = s3_result.decision.value  # "allow", "block", "review"

        # Step 3: Check for agreement
        s3_s4_agree = self._check_agreement(s3_position, s4_position)

        if s3_s4_agree:
            # Agreement → return combined result
            return DeliberationOutput(
                decision=s3_position,
                reason=f"S3 ({s3_position}) and S4 ({s4_position}) agree. {s3_result.reason}",
                s3_result={"decision": s3_position, "reason": s3_result.reason},
                s4_signals=[{"position": s4_position, "reason": s4_reason}],
                used_arbitration=False,
            )

        # Step 4: Disagreement → S5 arbitrates
        disagreement_type = self._classify_disagreement(s3_position, s4_position)

        arbitration = self.arbitrator.arbitrate(ArbitrationRequest(
            disagreement_type=disagreement_type,
            action_description=input.action_description,
            s3_position=s3_position,
            s3_reason=s3_result.reason,
            s4_position=s4_position,
            s4_reason=s4_reason,
        ))

        # Map S5 decision to gate decision
        decision_map = {
            "proceed": "allow",
            "block": "block",
            "defer": "review",
            "modify": "review",
        }
        final_decision = decision_map.get(arbitration.decision, "review")

        # Report the disagreement back to the channel
        self.channel.send_pattern(S3Message(
            pattern_type=OperationalPattern.CONSTRAINT_TENSION,
            description=f"S3-S4 disagreement on: {input.action_description[:100]}",
            blocked_action_types=[input.action_type],
        ))

        return DeliberationOutput(
            decision=final_decision,
            reason=f"S5 arbitration: {arbitration.reason}",
            s3_result={"decision": s3_position, "reason": s3_result.reason},
            s4_signals=[{"position": s4_position, "reason": s4_reason}],
            s5_arbitration={
                "decision": arbitration.decision,
                "reason": arbitration.reason,
                "tcs": arbitration.tcs_at_decision,
                "regime": arbitration.identity_regime,
                "conditions": arbitration.conditions,
            },
            used_arbitration=True,
        )

    def _check_agreement(self, s3_position: str, s4_position: str) -> bool:
        """Check if S3 and S4 agree."""
        # Agreement cases:
        # S3 allows + S4 neutral/opportunity → agree (allow)
        # S3 blocks + S4 threat → agree (block)
        # S3 review + S4 neutral → agree (review)
        if s3_position == "allow" and s4_position in ("neutral", "opportunity"):
            return True
        if s3_position == "block" and s4_position == "threat":
            return True
        if s3_position == "review" and s4_position in ("neutral", "mixed"):
            return True
        return False

    def _action_terms(self, input: DeliberationInput) -> set[str]:
        """Extract normalized search terms for the action under review."""
        return self._normalize_terms(
            input.action_type,
            input.action_description,
            input.target,
            input.content,
            *input.domains,
        )

    def _message_is_relevant(self, msg: S4Message, action_terms: set[str]) -> bool:
        """Decide whether an intelligence message applies to this action.

        Threats, opportunities, and methodologies need a concrete lexical
        connection to the current action. Constraint changes can also apply
        globally when marked high-relevance.
        """
        intel_terms = self._normalize_terms(msg.title, msg.description, *msg.keywords)
        if intel_terms and action_terms & intel_terms:
            return True

        return (
            msg.intelligence_type == IntelligenceType.CONSTRAINT_CHANGE
            and msg.relevance > 0.7
        )

    def _normalize_terms(self, *parts: str) -> set[str]:
        """Normalize free-form text into lowercase alphanumeric terms."""
        terms: set[str] = set()
        for part in parts:
            if not part:
                continue
            normalized = part.lower().replace("_", " ").replace("-", " ")
            terms.update(re.findall(r"[a-z0-9]+", normalized))
        return terms

    def _classify_disagreement(
        self, s3_position: str, s4_position: str
    ) -> DisagreementType:
        """Classify the type of S3-S4 disagreement."""
        if s3_position == "block" and s4_position in ("opportunity", "neutral"):
            return DisagreementType.S3_BLOCKS_S4_WANTS
        if s3_position == "allow" and s4_position == "threat":
            return DisagreementType.S3_ALLOWS_S4_WARNS
        return DisagreementType.BOTH_UNCERTAIN
