"""Neural Consolidation Engine — Backpropagation for Agent Behavior.

Mirrors the biological pattern described by agentic AI architects:

1. **Forward pass**: Agents operate, produce outputs, leave stigmergy marks
2. **Loss computation**: Systematic observation of errors, drift, inefficiency
3. **Contrarian discussion**: Two LLM calls (advocate + critic) → gradient direction
4. **Backpropagation**: Modify behavioral "weights" (correction files read by agents)
5. **Cell division**: When agent scope exceeds capacity → propose differentiation

The contrarian discussion mirrors what happens in the human brain during sleep:
two consolidation processes observe the entire system, disagree with each other,
push toward optimization, then modify the "weight files" (markdown/config) that
determine agent behavior — exactly like observing loss and doing backprop to
adjust weights in a neural network.

Grounding:
- Dada Bhagwan (P3): Witness → Error → Pratikraman → Correction
- Varela (P4): Autopoietic self-maintenance through self-observation
- Friston (P6): Active inference = minimizing prediction error
- Beer (P8): S4 intelligence → S3 control loop
- Levin (P10): Cell division as multi-scale cognitive differentiation
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_CORRECTIONS_DIR = Path.home() / ".dharma" / "consolidation" / "corrections"
_REPORTS_DIR = Path.home() / ".dharma" / "consolidation" / "reports"
_MAX_TRACES = 50  # Recent traces to read per forward scan
_MAX_MARKS = 100  # Recent stigmergy marks to read
_MAX_CORRECTIONS = 10  # Max corrections per cycle
_CELL_DIVISION_VARIETY_THRESHOLD = 6  # Task domains before considering split
_CELL_DIVISION_FAILURE_THRESHOLD = 0.35  # Failure rate before considering split
_CORRECTION_TTL_HOURS = 48  # Corrections expire after this

# Domain inference keywords (shared between loss detection and cell division)
_DOMAIN_KEYWORDS: list[tuple[str, str]] = [
    ("test", "testing"),
    ("research", "research"),
    ("code", "engineering"),
    ("fix", "engineering"),
    ("evolve", "evolution"),
    ("review", "review"),
    ("audit", "governance"),
    ("design", "architecture"),
]


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SystemSnapshot:
    """Forward pass results — all observable agent state."""

    traces: list[dict] = field(default_factory=list)
    stigmergy_marks: list[dict] = field(default_factory=list)
    task_outcomes: list[dict] = field(default_factory=list)
    agent_states: dict[str, dict] = field(default_factory=dict)
    fitness_signals: list[dict] = field(default_factory=list)
    timestamp: str = ""

    @property
    def agent_names(self) -> list[str]:
        return list(self.agent_states.keys())

    @property
    def total_tasks(self) -> int:
        return len(self.task_outcomes)

    @property
    def failure_rate(self) -> float:
        if not self.task_outcomes:
            return 0.0
        failed = sum(1 for t in self.task_outcomes if t.get("success") is False)
        return failed / len(self.task_outcomes)


@dataclass
class LossSignal:
    """Computed error between actual and desired agent behavior."""

    category: str  # repeated_failure, telos_drift, mimicry, coordination_gap, scope_overload
    agent: str  # Which agent (or "*" for systemic)
    severity: float  # 0.0 - 1.0
    evidence: str  # What was observed
    correction_hint: str  # Suggested direction


@dataclass
class BehavioralCorrection:
    """A weight update — modification to agent behavioral configuration.

    Like adjusting a weight in a neural network after observing loss,
    this modifies the text that determines an agent's future behavior.
    """

    target_agent: str  # Which agent to correct (or "*" for all)
    correction: str  # Specific behavioral instruction
    evidence: str  # What advocate/critic observed
    confidence: float  # 0.0 - 1.0
    source: str  # "advocate", "critic", "synthesis"
    timestamp: str = ""


@dataclass
class CellDivisionProposal:
    """Proposal to split an agent into specialized sub-agents.

    Like a cell in a multicellular organism that has grown beyond
    the scope where a single set of instructions can manage it.
    """

    parent_agent: str
    proposed_children: list[dict] = field(default_factory=list)
    justification: str = ""
    variety_score: float = 0.0
    failure_rate: float = 0.0


@dataclass
class ConsolidationReport:
    """Full report from one consolidation cycle."""

    started_at: str = ""
    duration_seconds: float = 0.0
    snapshot_summary: dict = field(default_factory=dict)
    losses_found: int = 0
    corrections_applied: int = 0
    division_proposals: int = 0
    advocate_summary: str = ""
    critic_summary: str = ""
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Provider protocol (duck-typed to avoid circular imports)
# ---------------------------------------------------------------------------


@runtime_checkable
class CompletionProvider(Protocol):
    """Minimal interface for LLM completion."""

    async def complete(self, request: Any) -> Any: ...


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------


class NeuralConsolidator:
    """The backpropagation engine for agent behavior.

    Like neural network training:
    - forward_scan()  = forward pass (observe all activations)
    - compute_loss()  = loss function (measure error from telos)
    - contrarian_discuss() = gradient computation (direction of correction)
    - backpropagate() = weight update (modify behavioral files)
    - check_cell_division() = architecture search (should we add/split neurons?)
    """

    def __init__(
        self,
        provider: Optional[CompletionProvider] = None,
        base_path: Optional[Path] = None,
        corrections_dir: Optional[Path] = None,
        reports_dir: Optional[Path] = None,
    ) -> None:
        self._provider = provider
        self._base = base_path or Path.home() / ".dharma"
        self._corrections_dir = corrections_dir or _CORRECTIONS_DIR
        self._reports_dir = reports_dir or _REPORTS_DIR

    # -- Forward Pass -------------------------------------------------------

    async def forward_scan(self) -> SystemSnapshot:
        """Read all observable system state.

        Like reading all neuron activations after a forward pass through
        the network — we observe everything the agents produced.
        """
        snap = SystemSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # 1. Recent traces (agent actions)
        snap.traces = self._read_traces()

        # 2. Stigmergy marks (pheromone signals)
        snap.stigmergy_marks = self._read_stigmergy()

        # 3. Task outcomes (success/failure records)
        snap.task_outcomes = self._read_task_outcomes()
        if not snap.task_outcomes and snap.traces:
            snap.task_outcomes = self.traces_to_outcomes(snap.traces)
        # Bridge: if no dedicated cycle log exists, synthesise from traces
        if not snap.task_outcomes and snap.traces:
            snap.task_outcomes = self.traces_to_outcomes(snap.traces)

        # 4. Agent states (identity + performance)
        snap.agent_states = self._read_agent_states()

        # 5. Fitness signals (quality scores)
        snap.fitness_signals = self._read_fitness_signals()

        return snap

    def _read_traces(self) -> list[dict]:
        """Read recent agent traces from the trace store.

        Supports two layouts:
        - traces/*.jsonl  (original design — JSONL files)
        - traces/history/*.json  (live system — individual JSON per trace)
        """
        traces: list[dict] = []
        trace_path = self._base / "traces"
        if not trace_path.exists():
            return traces

        # Strategy 1: JSONL files in traces/ root
        jsonl_files = sorted(
            trace_path.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        for f in jsonl_files[:3]:
            try:
                for line in f.read_text().strip().split("\n")[-_MAX_TRACES:]:
                    if line.strip():
                        traces.append(json.loads(line))
            except Exception as exc:
                logger.debug("Trace read failed for %s: %s", f.name, exc)

        # Strategy 2: Individual JSON files in traces/history/
        if not traces:
            history_dir = trace_path / "history"
            if history_dir.exists():
                history_files = sorted(
                    history_dir.glob("*.json"),
                    key=lambda p: p.stat().st_mtime, reverse=True,
                )
                for f in history_files[:_MAX_TRACES]:
                    try:
                        traces.append(json.loads(f.read_text()))
                    except Exception as exc:
                        logger.debug("History trace read failed for %s: %s", f.name, exc)

        return traces[-_MAX_TRACES:]

    def _read_stigmergy(self) -> list[dict]:
        """Read recent stigmergy marks."""
        marks_path = self._base / "stigmergy" / "marks.jsonl"
        if not marks_path.exists():
            return []
        marks: list[dict] = []
        try:
            for line in marks_path.read_text().strip().split("\n")[-_MAX_MARKS:]:
                if line.strip():
                    marks.append(json.loads(line))
        except Exception as exc:
            logger.debug("Stigmergy read failed: %s", exc)
        return marks

    def _read_task_outcomes(self) -> list[dict]:
        """Read recent task outcomes from available sources.

        Tries (in order):
        1. cycles.jsonl (original design)
        2. thinkodynamic/cycles.jsonl
        3. pulse_log.jsonl (live daemon dispatch log)
        4. known agent roots/*/task_log.jsonl (live per-agent execution history)
        5. Synthesise from traces (fallback — convert trace actions to outcomes)
        """
        outcomes: list[dict] = []

        # Strategy 1-2: JSONL cycle logs
        for candidate in [
            self._base / "cycles.jsonl",
            self._base / "thinkodynamic" / "cycles.jsonl",
            self._base / "pulse_log.jsonl",
        ]:
            if candidate.exists():
                try:
                    lines = candidate.read_text().strip().split("\n")
                    for line in lines[-_MAX_TRACES:]:
                        if line.strip():
                            outcomes.append(json.loads(line))
                    if outcomes:
                        return outcomes
                except Exception as exc:
                    logger.debug("Cycle log read failed for %s: %s", candidate.name, exc)

        # Strategy 4: Per-agent task logs under known agent roots
        for agents_dir in self._agent_roots():
            for task_log in agents_dir.glob("*/task_log.jsonl"):
                agent_name = task_log.parent.name
                try:
                    lines = [line for line in task_log.read_text().splitlines() if line.strip()]
                    for line in lines[-_MAX_TRACES:]:
                        outcomes.append(self._normalize_task_outcome(
                            json.loads(line),
                            agent_name=agent_name,
                        ))
                except Exception as exc:
                    logger.debug("Task log read failed for %s: %s", task_log, exc)

        if outcomes:
            outcomes.sort(key=lambda item: str(item.get("timestamp", "")))
            return outcomes[-_MAX_TRACES:]

        # Strategy 5: Synthesise from traces already read by forward_scan
        # (caller can use traces_to_outcomes after forward_scan populates traces)
        return outcomes

    @staticmethod
    def traces_to_outcomes(traces: list[dict]) -> list[dict]:
        """Convert raw trace dicts into task_outcome format for loss computation.

        Bridge for systems that record individual traces but no aggregated
        cycles.jsonl. Maps trace fields → outcome fields so loss detectors work.
        """
        outcomes: list[dict] = []
        for t in traces:
            outcomes.append({
                "agent": t.get("agent", "unknown"),
                "title": t.get("action", "unknown"),
                "success": t.get("success", True) if "success" in t else True,
                "error": t.get("error", ""),
                "domain": t.get("action", "general"),
                "gate_decision": t.get("gate_decision"),
                "telos_score": t.get("telos_score"),
            })
        return outcomes

    @staticmethod
    def _normalize_task_outcome(record: dict[str, Any], *, agent_name: str) -> dict[str, Any]:
        """Normalize heterogeneous task logs into the task_outcome shape."""
        error = record.get("error")
        if record.get("success") is False and not error:
            error = record.get("response_preview") or "unspecified_failure"
        return {
            "agent": record.get("agent", agent_name),
            "title": record.get(
                "title",
                record.get(
                    "task_description",
                    record.get("task", record.get("action", "unknown")),
                ),
            ),
            "success": record.get("success"),
            "error": error,
            "timestamp": record.get("timestamp", ""),
            "domain": record.get("domain"),
            "gate_decision": record.get("gate_decision", record.get("gate_result")),
            "telos_score": record.get("telos_score"),
            "model": record.get("model"),
        }

    def _read_agent_states(self) -> dict[str, dict]:
        """Read per-agent identity snapshots."""
        states: dict[str, dict] = {}
        for agents_dir in self._agent_roots():
            for agent_dir in agents_dir.iterdir():
                if not agent_dir.is_dir():
                    continue
                name = agent_dir.name
                identity_path = agent_dir / "identity.json"
                if identity_path.exists():
                    try:
                        states[name] = json.loads(identity_path.read_text())
                    except Exception:
                        states[name] = {"name": name, "error": "identity_unreadable"}
                else:
                    states.setdefault(name, {"name": name})
        return states

    def _agent_roots(self) -> list[Path]:
        """Return known per-agent registry roots across live runtimes."""
        roots = [
            self._base / "ginko" / "agents",
            self._base / "agents",
            self._base / "agent_memory",
        ]
        return [root for root in roots if root.exists()]

    def _read_fitness_signals(self) -> list[dict]:
        """Read recent fitness/quality signals from logs."""
        signals: list[dict] = []
        log_dir = self._base / "logs" / "router"
        if not log_dir.exists():
            return signals
        # Read routing audit (contains quality scores)
        audit_path = log_dir / "routing_audit.jsonl"
        if audit_path.exists():
            try:
                lines = audit_path.read_text().strip().split("\n")
                for line in lines[-_MAX_TRACES:]:
                    if line.strip():
                        signals.append(json.loads(line))
            except Exception as exc:
                logger.debug("Fitness signal read failed: %s", exc)
        return signals

    # -- Loss Computation ---------------------------------------------------

    def compute_loss(self, snapshot: SystemSnapshot) -> list[LossSignal]:
        """Identify errors, drift, and inefficiency.

        Like computing the loss function after a forward pass — we
        measure how far the system's actual behavior is from its telos.
        """
        losses: list[LossSignal] = []

        losses.extend(self._detect_repeated_failures(snapshot))
        losses.extend(self._detect_mimicry(snapshot))
        losses.extend(self._detect_coordination_gaps(snapshot))
        losses.extend(self._detect_scope_overload(snapshot))
        losses.extend(self._detect_telos_drift(snapshot))

        # Sort by severity (highest first)
        losses.sort(key=lambda l: l.severity, reverse=True)
        return losses

    def _detect_repeated_failures(self, snap: SystemSnapshot) -> list[LossSignal]:
        """Detect the same type of error happening repeatedly."""
        losses: list[LossSignal] = []
        error_counts: dict[str, int] = {}

        for outcome in snap.task_outcomes:
            if outcome.get("success") is False or outcome.get("status") == "failed":
                error_type = outcome.get("error", outcome.get("failure_reason", "unknown"))
                # Normalize to first 60 chars
                key = str(error_type)[:60].lower()
                error_counts[key] = error_counts.get(key, 0) + 1

        for error_key, count in error_counts.items():
            if count >= 2:
                agent = "system"
                # Try to find which agent
                for outcome in snap.task_outcomes:
                    err = str(outcome.get("error", ""))[:60].lower()
                    if err == error_key:
                        agent = outcome.get("agent", outcome.get("assigned_to", "system"))
                        break
                losses.append(LossSignal(
                    category="repeated_failure",
                    agent=agent,
                    severity=min(1.0, count * 0.25),
                    evidence=f"Error '{error_key}' occurred {count} times",
                    correction_hint=f"Address root cause of: {error_key}",
                ))

        return losses

    def _detect_mimicry(self, snap: SystemSnapshot) -> list[LossSignal]:
        """Detect performative profundity — agents producing templated output."""
        losses: list[LossSignal] = []
        mimicry_phrases = [
            "i understand your concern",
            "great question",
            "absolutely",
            "that's a really important point",
            "let me help you with that",
            "i'd be happy to",
        ]

        for trace in snap.traces:
            text = str(trace.get("result", trace.get("output", ""))).lower()
            if not text or len(text) < 50:
                continue
            mimicry_count = sum(1 for phrase in mimicry_phrases if phrase in text)
            if mimicry_count >= 2:
                agent = trace.get("agent", trace.get("actor", "*"))
                losses.append(LossSignal(
                    category="mimicry",
                    agent=agent,
                    severity=min(1.0, mimicry_count * 0.2),
                    evidence=f"Agent '{agent}' used {mimicry_count} mimicry phrases in single output",
                    correction_hint="Produce genuine analysis, not performative acknowledgment",
                ))

        return losses

    def _detect_coordination_gaps(self, snap: SystemSnapshot) -> list[LossSignal]:
        """Detect agents working in isolation or at cross-purposes."""
        losses: list[LossSignal] = []

        # Check if any agent has marks that went unread (no access_count increment)
        unread_marks: dict[str, int] = {}
        for mark in snap.stigmergy_marks:
            if mark.get("access_count", 0) == 0 and mark.get("salience", 0) >= 0.6:
                agent = mark.get("agent", "unknown")
                unread_marks[agent] = unread_marks.get(agent, 0) + 1

        for agent, count in unread_marks.items():
            if count >= 3:
                losses.append(LossSignal(
                    category="coordination_gap",
                    agent=agent,
                    severity=min(1.0, count * 0.15),
                    evidence=f"Agent '{agent}' left {count} high-salience marks that went unread",
                    correction_hint="Other agents should scan stigmergy marks from this agent",
                ))

        return losses

    @staticmethod
    def _infer_domain(outcome: dict) -> str:
        """Infer task domain from metadata or title keywords."""
        domain = outcome.get("domain")
        if not domain:
            domain = outcome.get("thread") or "general"
        title = outcome.get("title", "").lower()
        for keyword, dom in _DOMAIN_KEYWORDS:
            if keyword in title:
                domain = dom
                break
        return domain

    def _detect_scope_overload(self, snap: SystemSnapshot) -> list[LossSignal]:
        """Detect agents handling too many different task domains."""
        losses: list[LossSignal] = []
        agent_domains: dict[str, set[str]] = {}

        for outcome in snap.task_outcomes:
            agent = outcome.get("agent", outcome.get("assigned_to"))
            if not agent:
                continue
            domain = self._infer_domain(outcome)
            agent_domains.setdefault(agent, set()).add(domain)

        for agent, domains in agent_domains.items():
            if len(domains) >= _CELL_DIVISION_VARIETY_THRESHOLD:
                losses.append(LossSignal(
                    category="scope_overload",
                    agent=agent,
                    severity=min(1.0, len(domains) * 0.12),
                    evidence=f"Agent '{agent}' spans {len(domains)} domains: {', '.join(sorted(domains))}",
                    correction_hint="Consider splitting this agent into specialized sub-agents",
                ))

        return losses

    def _detect_telos_drift(self, snap: SystemSnapshot) -> list[LossSignal]:
        """Detect actions that don't serve the 7-STAR telos vector.

        Algorithmic check: tasks with no telos scoring or gate results
        indicate the system is operating without governance oversight.
        """
        losses: list[LossSignal] = []
        ungated_count = 0

        for outcome in snap.task_outcomes:
            gate = outcome.get("gate_decision", outcome.get("gate_result"))
            telos = outcome.get("telos_score")
            if gate is None and telos is None:
                ungated_count += 1

        if ungated_count >= 3:
            losses.append(LossSignal(
                category="telos_drift",
                agent="*",
                severity=min(1.0, ungated_count * 0.1),
                evidence=f"{ungated_count} tasks ran without gate evaluation or telos scoring",
                correction_hint="Ensure all significant actions pass through telos gate checks",
            ))

        return losses

    # -- Contrarian Discussion (Gradient Computation) -----------------------

    async def contrarian_discuss(
        self,
        snapshot: SystemSnapshot,
        losses: list[LossSignal],
    ) -> list[BehavioralCorrection]:
        """Two LLM calls with opposing frames, synthesized into corrections.

        This mirrors what the architect described: two agents read the
        entire system state, disagree with each other, and produce
        specific modifications to behavioral files.

        Without a provider, falls back to algorithmic corrections from
        the loss signals directly.
        """
        if self._provider is None:
            return self._algorithmic_corrections(losses)

        # Build compact snapshot summary for LLM context
        summary = self._build_snapshot_summary(snapshot, losses)

        try:
            # 1. Advocate: what's working?
            advocate_response = await self._llm_call(
                system="You are the Advocate in a neural consolidation cycle for a "
                       "multi-agent AI system. Your role: identify what is WORKING WELL "
                       "and should be reinforced. Be specific — name agents, tasks, "
                       "patterns. Do not be generically positive.",
                prompt=f"System snapshot from the last cycle:\n\n{summary}\n\n"
                       f"Observed losses:\n{self._format_losses(losses)}\n\n"
                       "What is working well? What patterns should be reinforced? "
                       "What agents are performing effectively?",
            )

            # 2. Critic: what's broken?
            critic_response = await self._llm_call(
                system="You are the Critic in a neural consolidation cycle for a "
                       "multi-agent AI system. Your role: identify what is BROKEN. "
                       "What errors keep repeating? What beliefs are incorrect? "
                       "What coordination is failing? Be brutal and specific.",
                prompt=f"System snapshot from the last cycle:\n\n{summary}\n\n"
                       f"Observed losses:\n{self._format_losses(losses)}\n\n"
                       "What is broken? What keeps failing? What incorrect assumptions "
                       "are agents operating under?",
            )

            # 3. Synthesis: produce specific corrections
            synthesis_response = await self._llm_call(
                system="You are the Synthesizer. You received two analyses of the same "
                       "multi-agent system — one from an Advocate (what's working) and "
                       "one from a Critic (what's broken). Produce specific BEHAVIORAL "
                       "CORRECTIONS for each agent. Each correction must be: (1) a "
                       "concrete instruction, (2) justified by evidence, (3) rated "
                       "by confidence 0-1. Return valid JSON array.",
                prompt=f"ADVOCATE analysis:\n{advocate_response}\n\n"
                       f"CRITIC analysis:\n{critic_response}\n\n"
                       "Produce corrections as a JSON array:\n"
                       '[{"target_agent": "name or *", "correction": "specific instruction", '
                       '"evidence": "what was observed", "confidence": 0.0-1.0}]\n\n'
                       "Also note if any agent should DIVIDE into specialized sub-agents.",
            )

            corrections = self._parse_synthesis(
                synthesis_response, advocate_response, critic_response,
            )
            return corrections[:_MAX_CORRECTIONS]

        except Exception as exc:
            logger.warning("Contrarian discussion failed, using algorithmic fallback: %s", exc)
            return self._algorithmic_corrections(losses)

    async def _llm_call(self, system: str, prompt: str) -> str:
        """Make a single LLM call via the provider."""
        from dharma_swarm.models import LLMRequest

        request = LLMRequest(
            model="",  # Provider selects default
            messages=[{"role": "user", "content": prompt}],
            system=system,
            max_tokens=1500,
            temperature=0.7,
        )
        assert self._provider is not None
        response = await self._provider.complete(request)
        return response.content if hasattr(response, "content") else str(response)

    def _build_snapshot_summary(
        self, snap: SystemSnapshot, losses: list[LossSignal],
    ) -> str:
        """Build a compact text summary of system state for LLM context."""
        lines: list[str] = []

        lines.append(f"Timestamp: {snap.timestamp}")
        lines.append(f"Agents active: {len(snap.agent_states)}")
        lines.append(f"Tasks observed: {snap.total_tasks}")
        lines.append(f"Overall failure rate: {snap.failure_rate:.1%}")
        lines.append(f"Stigmergy marks: {len(snap.stigmergy_marks)}")
        lines.append(f"Losses detected: {len(losses)}")
        lines.append("")

        # Per-agent summary
        for name, state in snap.agent_states.items():
            completed = state.get("tasks_completed", 0)
            failed = state.get("tasks_failed", 0)
            quality = state.get("avg_quality", 0.0)
            lines.append(f"  {name}: completed={completed} failed={failed} quality={quality:.2f}")

        # Recent high-salience marks
        high_marks = [m for m in snap.stigmergy_marks if m.get("salience", 0) >= 0.7]
        if high_marks:
            lines.append("\nHigh-salience signals:")
            for mark in high_marks[-5:]:
                lines.append(f"  [{mark.get('agent', '?')}] {mark.get('observation', '')[:100]}")

        return "\n".join(lines)

    def _format_losses(self, losses: list[LossSignal]) -> str:
        """Format loss signals for LLM context."""
        if not losses:
            return "No significant losses detected."
        lines: list[str] = []
        for loss in losses:
            lines.append(
                f"- [{loss.category}] agent={loss.agent} severity={loss.severity:.2f}: "
                f"{loss.evidence}"
            )
        return "\n".join(lines)

    def _parse_synthesis(
        self,
        synthesis: str,
        advocate: str,  # noqa: ARG002 — kept for future enrichment
        critic: str,
    ) -> list[BehavioralCorrection]:
        """Parse the synthesizer's JSON output into corrections."""
        now = datetime.now(timezone.utc).isoformat()
        corrections: list[BehavioralCorrection] = []

        # Try to extract JSON from the response
        text = synthesis.strip()
        # Find JSON array in response
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            try:
                items = json.loads(text[start : end + 1])
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    corrections.append(BehavioralCorrection(
                        target_agent=item.get("target_agent", "*"),
                        correction=item.get("correction", ""),
                        evidence=item.get("evidence", ""),
                        confidence=float(item.get("confidence", 0.5)),
                        source="synthesis",
                        timestamp=now,
                    ))
            except json.JSONDecodeError:
                logger.warning("Failed to parse synthesis JSON, extracting manually")

        # If JSON parse failed, create corrections from advocate/critic text
        if not corrections:
            if critic:
                corrections.append(BehavioralCorrection(
                    target_agent="*",
                    correction=critic[:500],
                    evidence="Critic analysis (unparsed)",
                    confidence=0.5,
                    source="critic",
                    timestamp=now,
                ))

        return corrections

    def _algorithmic_corrections(self, losses: list[LossSignal]) -> list[BehavioralCorrection]:
        """Generate corrections directly from loss signals without LLM.

        This is the fallback when no provider is available — it converts
        each loss signal into a behavioral correction based on the
        correction_hint field.
        """
        now = datetime.now(timezone.utc).isoformat()
        corrections: list[BehavioralCorrection] = []

        for loss in losses:
            if loss.severity < 0.3:
                continue
            corrections.append(BehavioralCorrection(
                target_agent=loss.agent,
                correction=loss.correction_hint,
                evidence=loss.evidence,
                confidence=min(1.0, loss.severity * 0.8),
                source="algorithmic",
                timestamp=now,
            ))

        return corrections[:_MAX_CORRECTIONS]

    # -- Backpropagation (Weight Update) ------------------------------------

    async def backpropagate(
        self,
        corrections: list[BehavioralCorrection],
    ) -> dict[str, Any]:
        """Apply corrections to behavioral weights.

        Like adjusting weights after backprop — we write correction files
        that agent_runner reads and injects into future system prompts.
        This is the exact analog of "modifying the markdown files that
        tell agents how to behave."
        """
        self._corrections_dir.mkdir(parents=True, exist_ok=True)
        applied = 0
        agents_updated: set[str] = set()

        for correction in corrections:
            if correction.confidence < 0.3:
                continue

            target = correction.target_agent
            agents_to_update = (
                list(set(c.target_agent for c in corrections if c.target_agent != "*"))
                if target == "*"
                else [target]
            )
            # For wildcard, also write a global correction
            if target == "*":
                agents_to_update.append("_global")

            for agent_name in agents_to_update:
                path = self._corrections_dir / f"{agent_name}.md"
                self._append_correction(path, correction)
                agents_updated.add(agent_name)
                applied += 1

        # Expire old corrections
        expired = self._expire_old_corrections()

        return {
            "corrections_applied": applied,
            "agents_updated": sorted(agents_updated),
            "corrections_expired": expired,
        }

    def _append_correction(self, path: Path, correction: BehavioralCorrection) -> None:
        """Append a correction to an agent's correction file."""
        existing = path.read_text() if path.exists() else ""

        entry = (
            f"\n## Correction ({correction.timestamp})\n"
            f"**Source**: {correction.source} | **Confidence**: {correction.confidence:.2f}\n"
            f"**Evidence**: {correction.evidence}\n\n"
            f"{correction.correction}\n"
        )

        # Prepend header if file is new
        if not existing:
            header = (
                "# Behavioral Corrections\n\n"
                "These corrections were generated by the Neural Consolidation Engine\n"
                "during sleep-cycle contrarian discussion. They modify agent behavior\n"
                "like weight updates in a neural network.\n\n"
                "---\n"
            )
            existing = header

        path.write_text(existing + entry)

    def _expire_old_corrections(self) -> int:
        """Remove correction files older than TTL."""
        if not self._corrections_dir.exists():
            return 0
        expired = 0
        cutoff = time.time() - (_CORRECTION_TTL_HOURS * 3600)
        for path in self._corrections_dir.glob("*.md"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    expired += 1
            except Exception:
                pass
        return expired

    # -- Cell Division (Architecture Search) --------------------------------

    def check_cell_division(
        self, snapshot: SystemSnapshot,
    ) -> list[CellDivisionProposal]:
        """Evaluate if any agent should split into specialized sub-agents.

        Like a cell in a multicellular organism that has grown beyond
        the scope where one genome can effectively regulate — it needs
        to divide and differentiate.

        Criteria:
        - Task variety exceeds threshold (too many domains)
        - Failure rate trending up (overloaded)
        - Combined with absolute task volume
        """
        proposals: list[CellDivisionProposal] = []
        agent_tasks: dict[str, list[dict]] = {}

        for outcome in snapshot.task_outcomes:
            agent = outcome.get("agent", outcome.get("assigned_to"))
            if agent:
                agent_tasks.setdefault(agent, []).append(outcome)

        for agent, tasks in agent_tasks.items():
            # Compute task variety (number of distinct domains)
            domains: set[str] = set()
            for task in tasks:
                domain = self._infer_domain(task)
                domains.add(domain)

            variety_score = len(domains)

            # Compute failure rate for this agent
            failed = sum(1 for t in tasks if t.get("success") is False)
            agent_failure_rate = failed / len(tasks) if tasks else 0.0

            if (variety_score >= _CELL_DIVISION_VARIETY_THRESHOLD
                    or agent_failure_rate >= _CELL_DIVISION_FAILURE_THRESHOLD):

                # Propose children based on domain clustering
                children: list[dict] = []
                for domain in sorted(domains):
                    children.append({
                        "name": f"{agent}-{domain}",
                        "specialization": domain,
                        "task_count": sum(
                            1 for t in tasks
                            if domain in t.get("title", "").lower()
                            or t.get("domain") == domain
                        ),
                    })

                proposals.append(CellDivisionProposal(
                    parent_agent=agent,
                    proposed_children=children,
                    justification=(
                        f"Agent '{agent}' spans {variety_score} domains with "
                        f"{agent_failure_rate:.0%} failure rate across {len(tasks)} tasks. "
                        f"Domains: {', '.join(sorted(domains))}"
                    ),
                    variety_score=variety_score,
                    failure_rate=agent_failure_rate,
                ))

        return proposals

    # -- Full Consolidation Cycle -------------------------------------------

    async def consolidation_cycle(self) -> ConsolidationReport:
        """Run the full neural consolidation cycle.

        This is the complete backpropagation loop:
        1. Forward scan (read all state)
        2. Compute loss (identify errors)
        3. Contrarian discussion (advocate vs critic → gradient)
        4. Backpropagate (modify behavioral weights)
        5. Check cell division (architecture search)

        Returns a ConsolidationReport with all findings.
        """
        report = ConsolidationReport(
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        t0 = time.monotonic()

        # 1. Forward pass
        try:
            snapshot = await self.forward_scan()
            report.snapshot_summary = {
                "agents": len(snapshot.agent_states),
                "traces": len(snapshot.traces),
                "tasks": snapshot.total_tasks,
                "marks": len(snapshot.stigmergy_marks),
                "failure_rate": snapshot.failure_rate,
            }
        except Exception as exc:
            report.errors.append(f"forward_scan: {exc}")
            report.duration_seconds = time.monotonic() - t0
            return report

        # 2. Loss computation
        try:
            losses = self.compute_loss(snapshot)
            report.losses_found = len(losses)
        except Exception as exc:
            report.errors.append(f"compute_loss: {exc}")
            losses = []

        # 3. Contrarian discussion (requires losses to discuss)
        if losses:
            try:
                corrections = await self.contrarian_discuss(snapshot, losses)
            except Exception as exc:
                report.errors.append(f"contrarian_discuss: {exc}")
                corrections = []
        else:
            corrections = []
            logger.info("No losses detected — skipping contrarian discussion")

        # 4. Backpropagation
        if corrections:
            try:
                bp_result = await self.backpropagate(corrections)
                report.corrections_applied = bp_result["corrections_applied"]
            except Exception as exc:
                report.errors.append(f"backpropagate: {exc}")

        # 5. Cell division check
        try:
            proposals = self.check_cell_division(snapshot)
            report.division_proposals = len(proposals)
            if proposals:
                self._persist_division_proposals(proposals)
        except Exception as exc:
            report.errors.append(f"cell_division: {exc}")

        # Persist report
        report.duration_seconds = time.monotonic() - t0
        self._persist_report(report)

        logger.info(
            "Neural consolidation complete: %d losses, %d corrections, "
            "%d division proposals (%.1fs)",
            report.losses_found,
            report.corrections_applied,
            report.division_proposals,
            report.duration_seconds,
        )

        return report

    def _persist_report(self, report: ConsolidationReport) -> None:
        """Write consolidation report to disk."""
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        path = self._reports_dir / f"consolidation_{date_str}.json"
        try:
            import dataclasses
            path.write_text(json.dumps(dataclasses.asdict(report), indent=2, default=str))
        except Exception as exc:
            logger.warning("Failed to persist consolidation report: %s", exc)

    def _persist_division_proposals(self, proposals: list[CellDivisionProposal]) -> None:
        """Write cell division proposals to disk for operator review."""
        proposals_dir = self._base / "consolidation" / "division_proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        path = proposals_dir / f"proposals_{date_str}.json"
        try:
            import dataclasses
            path.write_text(json.dumps(
                [dataclasses.asdict(p) for p in proposals],
                indent=2, default=str,
            ))
        except Exception as exc:
            logger.warning("Failed to persist division proposals: %s", exc)


# ---------------------------------------------------------------------------
# Correction reader (used by agent_runner.py to inject corrections)
# ---------------------------------------------------------------------------


def load_behavioral_corrections(
    agent_name: str,
    corrections_dir: Optional[Path] = None,
) -> str:
    """Load behavioral corrections for an agent.

    Called by agent_runner._build_system_prompt() to inject corrections
    into the agent's system prompt — like loading updated weights before
    the next forward pass.

    Reads both agent-specific and global corrections.
    """
    cdir = corrections_dir or _CORRECTIONS_DIR
    if not cdir.exists():
        return ""

    parts: list[str] = []

    # Global corrections (apply to all agents)
    global_path = cdir / "_global.md"
    if global_path.exists():
        try:
            text = global_path.read_text().strip()
            if text:
                parts.append(text)
        except Exception:
            pass

    # Agent-specific corrections
    agent_path = cdir / f"{agent_name}.md"
    if agent_path.exists():
        try:
            text = agent_path.read_text().strip()
            if text:
                parts.append(text)
        except Exception:
            pass

    if not parts:
        return ""

    return (
        "\n\n## Neural Consolidation Corrections\n"
        "The following corrections were generated during sleep-cycle "
        "consolidation. Apply these behavioral adjustments:\n\n"
        + "\n\n".join(parts)
    )
