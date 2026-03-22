"""Consolidation Cycle — system-wide sleep/backpropagation.

Implements the "Cellular Organism" pattern: two consolidator agents
(Alpha/Beta) periodically read ALL agents' state, have a structured
contrarian debate, and modify behavioral DNA based on observed "loss".

Mirrors: sleep consolidation in the brain, forward pass → loss → backprop
in neural networks.

Four phases per cycle:
  1. OBSERVATION  — Alpha and Beta independently read all agent state
  2. DEBATE       — Structured 5-round contrarian dialogue
  3. BACKPROP     — Generate and apply behavioral corrections
  4. DIFFERENTIATION — Check for persistent capability gaps

Grounded in:
  - Hofstadter (Pillar 4): System observing itself (strange loop)
  - Dada Bhagwan (Pillar 6): Witness observes, then samvara (correction)
  - Friston (Pillar 10): Active inference — reduce surprise by updating params
  - Beer (Pillar 8): S3* sporadic audit at whole-system scale
  - Varela (Pillar 7): Autopoietic self-maintenance via behavioral modification
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from dharma_swarm.models import LLMRequest, ProviderType
from dharma_swarm.runtime_provider import (
    create_runtime_provider,
    preferred_runtime_provider_configs,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_CONSOLIDATION_INTERVAL = int(
    os.environ.get("DGC_CONSOLIDATION_INTERVAL", "86400")
)  # 24h default

# Models for the two sides of the debate — different families for genuine diversity
DEFAULT_ALPHA_MODEL = os.environ.get(
    "DGC_CONSOLIDATION_ALPHA_MODEL",
    "meta-llama/llama-3.3-70b-instruct:free",
)
DEFAULT_BETA_MODEL = os.environ.get(
    "DGC_CONSOLIDATION_BETA_MODEL",
    "deepseek/deepseek-chat-v3-0324:free",
)

# Severity thresholds for behavioral corrections
SEVERITY_AUTO_APPLY = 0.3      # < this: auto-apply after gate pass
SEVERITY_FLAG_REVIEW = 0.7     # < this: apply but flag for morning review
# >= SEVERITY_FLAG_REVIEW: proposed only, requires S5 veto


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class AgentStateSnapshot(BaseModel):
    """Snapshot of one agent's state for consolidation."""
    name: str
    working_memory_keys: list[str] = Field(default_factory=list)
    archival_summary: str = ""
    persona_summary: str = ""
    recent_task_count: int = 0
    error_count: int = 0
    stigmergy_mark_count: int = 0


class SystemStateReport(BaseModel):
    """One consolidator's view of the entire system."""
    consolidator_id: str  # "alpha" or "beta"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agent_snapshots: list[AgentStateSnapshot] = Field(default_factory=list)
    stigmergy_density: int = 0
    dream_count: int = 0
    observations: str = ""  # LLM-generated observations


class DebateTurn(BaseModel):
    """One turn in the contrarian debate."""
    speaker: str  # "alpha" or "beta"
    round_number: int
    position: str  # analysis, attack, defense, synthesis, verdict
    content: str


class LossItem(BaseModel):
    """A specific issue identified in the system."""
    category: str  # fitness_gap, memory_debt, coordination_failure, telos_drift, capability_gap
    severity: float = Field(ge=0.0, le=1.0)
    affected_agents: list[str] = Field(default_factory=list)
    description: str
    proposed_correction: str = ""


class SystemLossReport(BaseModel):
    """Output of the contrarian debate — the system's "loss"."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agreed_issues: list[LossItem] = Field(default_factory=list)
    alpha_only_issues: list[LossItem] = Field(default_factory=list)
    beta_only_issues: list[LossItem] = Field(default_factory=list)
    debate_transcript: list[DebateTurn] = Field(default_factory=list)
    system_loss_score: float = Field(default=0.0, ge=0.0, le=1.0)


class BehavioralCorrection(BaseModel):
    """A specific modification to agent behavioral DNA."""
    correction_type: str  # prompt_update, memory_adjustment, corpus_claim, gate_proposal
    target_agent: str  # agent name or "system"
    description: str
    rationale: str
    severity: float = Field(default=0.5, ge=0.0, le=1.0)
    applied: bool = False
    vetoed: bool = False
    veto_required: bool = False


class ConsolidationOutcome(BaseModel):
    """Full outcome of one consolidation cycle."""
    cycle_number: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    loss_report: SystemLossReport = Field(default_factory=SystemLossReport)
    corrections_proposed: int = 0
    corrections_applied: int = 0
    corrections_vetoed: int = 0
    system_loss_score: float = 0.0
    duration_seconds: float = 0.0


class DifferentiationProposal(BaseModel):
    """Proposal for a new constitutional agent role."""
    proposed_role: str
    justification: str
    capability_gap: str
    evidence_cycles: list[int] = Field(default_factory=list)
    parent_agent: str = ""
    generation: int = 0
    severity: float = 0.0
    status: str = "proposed"  # requires S5 (Dhyana) approval


# ---------------------------------------------------------------------------
# System Observer
# ---------------------------------------------------------------------------

class SystemObserver:
    """Phase 1: Read all agent state and produce a SystemStateReport."""

    def __init__(self, state_dir: Path) -> None:
        self._state_dir = state_dir

    async def observe(self, consolidator_id: str) -> SystemStateReport:
        """Read all agent state and produce a report."""
        report = SystemStateReport(consolidator_id=consolidator_id)

        # Read agent memory banks
        agent_memory_dir = self._state_dir / "agent_memory"
        if agent_memory_dir.exists():
            for agent_dir in sorted(agent_memory_dir.iterdir()):
                if agent_dir.is_dir():
                    snapshot = self._read_agent_state(agent_dir)
                    report.agent_snapshots.append(snapshot)

        # Read stigmergy density
        marks_file = self._state_dir / "stigmergy" / "marks.jsonl"
        if marks_file.exists():
            try:
                lines = marks_file.read_text(encoding="utf-8").strip().split("\n")
                report.stigmergy_density = len([l for l in lines if l.strip()])
            except Exception:
                pass

        # Read dream count
        hum_file = self._state_dir / "subconscious" / "hum.jsonl"
        if hum_file.exists():
            try:
                lines = hum_file.read_text(encoding="utf-8").strip().split("\n")
                report.dream_count = len([l for l in lines if l.strip()])
            except Exception:
                pass

        return report

    def _read_agent_state(self, agent_dir: Path) -> AgentStateSnapshot:
        """Read one agent's memory state."""
        name = agent_dir.name
        snapshot = AgentStateSnapshot(name=name)

        # Working memory
        working_file = agent_dir / "working.json"
        if working_file.exists():
            try:
                data = json.loads(working_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    snapshot.working_memory_keys = list(data.keys())[:10]
            except Exception:
                pass

        # Archival memory (just count + first few keys)
        archival_file = agent_dir / "archival.json"
        if archival_file.exists():
            try:
                data = json.loads(archival_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    keys = list(data.keys())
                    snapshot.archival_summary = f"{len(keys)} entries: {', '.join(keys[:5])}"
            except Exception:
                pass

        # Persona
        persona_file = agent_dir / "persona.json"
        if persona_file.exists():
            try:
                data = json.loads(persona_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    snapshot.persona_summary = json.dumps(
                        {k: str(v)[:50] for k, v in list(data.items())[:3]},
                    )
            except Exception:
                pass

        return snapshot

    def compress_for_llm(self, report: SystemStateReport, max_chars: int = 4000) -> str:
        """Compress a SystemStateReport into text for LLM context."""
        parts = [f"# System State ({report.consolidator_id})\n"]
        parts.append(f"Timestamp: {report.timestamp.isoformat()}\n")
        parts.append(f"Stigmergy marks: {report.stigmergy_density}\n")
        parts.append(f"Dream associations: {report.dream_count}\n\n")

        for snap in report.agent_snapshots:
            parts.append(f"## Agent: {snap.name}\n")
            parts.append(f"  Working memory: {snap.working_memory_keys}\n")
            if snap.archival_summary:
                parts.append(f"  Archival: {snap.archival_summary}\n")
            if snap.persona_summary:
                parts.append(f"  Persona: {snap.persona_summary}\n")
            parts.append("\n")

        text = "".join(parts)
        if len(text) > max_chars:
            text = text[:max_chars - 50] + "\n\n[... truncated for context budget]"
        return text


# ---------------------------------------------------------------------------
# Contrarian Dialogue
# ---------------------------------------------------------------------------

ALPHA_SYSTEM = """You are Consolidator Alpha — the THESIS side of a system-wide behavioral audit.

Your role: identify what IS working in this multi-agent system and propose
targeted refinements to improve further. You see patterns of success and
want to amplify them.

You will receive a snapshot of all agents' state (memory, traces, stigmergy).
Your analysis must be SPECIFIC and GROUNDED in the data — cite specific agents,
specific memory items, specific patterns.

Focus on:
1. Which agents are performing well and why
2. What coordination patterns are working
3. What small refinements would improve the system
4. What the system should keep doing"""

BETA_SYSTEM = """You are Consolidator Beta — the ANTITHESIS side of a system-wide behavioral audit.

Your role: identify what is NOT working in this multi-agent system and propose
structural changes to fix systemic issues. You see patterns of failure and
want to eliminate them.

You will receive a snapshot of all agents' state (memory, traces, stigmergy).
Your analysis must be SPECIFIC and GROUNDED in the data — cite specific agents,
specific memory items, specific patterns.

Focus on:
1. Which agents are underperforming and why
2. What coordination failures are occurring
3. What structural changes would fix systemic issues
4. What the system should stop doing"""

DEBATE_PROMPT = """Your opponent ({opponent}) has argued:

{opponent_argument}

Previous debate history:
{history}

Respond with your counter-position. Be specific. Concede where the evidence
is against you. The goal is to find truth, not to win.

Keep response under 500 words."""

LOSS_EXTRACTION_PROMPT = """Given this debate transcript between two consolidation agents,
extract the specific issues they identified.

{transcript}

Respond with a JSON object:
{{
    "agreed_issues": [
        {{"category": "fitness_gap|memory_debt|coordination_failure|telos_drift|capability_gap",
          "severity": 0.0-1.0,
          "affected_agents": ["agent_name"],
          "description": "specific issue",
          "proposed_correction": "specific fix"}}
    ],
    "alpha_only_issues": [...],
    "beta_only_issues": [...],
    "system_loss_score": 0.0-1.0
}}

Only include issues backed by evidence from the debate. Be precise."""


class ContrarianDialogue:
    """Phase 2: Structured contrarian debate between Alpha and Beta."""

    def __init__(
        self,
        alpha_model: str = DEFAULT_ALPHA_MODEL,
        beta_model: str = DEFAULT_BETA_MODEL,
        rounds: int = 5,
    ) -> None:
        self.alpha_model = alpha_model
        self.beta_model = beta_model
        self.rounds = rounds

    async def run(
        self,
        alpha_state: str,
        beta_state: str,
        provider: Any,
    ) -> SystemLossReport:
        """Run the full debate and produce a loss report."""
        transcript: list[DebateTurn] = []

        # Phase 1: Independent analysis
        alpha_analysis = await self._call_llm(
            provider, self.alpha_model, ALPHA_SYSTEM,
            f"Analyze this system state:\n\n{alpha_state}",
        )
        transcript.append(DebateTurn(
            speaker="alpha", round_number=0,
            position="analysis", content=alpha_analysis,
        ))

        beta_analysis = await self._call_llm(
            provider, self.beta_model, BETA_SYSTEM,
            f"Analyze this system state:\n\n{beta_state}",
        )
        transcript.append(DebateTurn(
            speaker="beta", round_number=0,
            position="analysis", content=beta_analysis,
        ))

        # Phase 2: Debate rounds
        history = f"ALPHA ANALYSIS:\n{alpha_analysis}\n\nBETA ANALYSIS:\n{beta_analysis}"
        last_alpha = alpha_analysis

        for round_num in range(1, self.rounds + 1):
            # Beta attacks
            beta_turn = await self._call_llm(
                provider, self.beta_model, BETA_SYSTEM,
                DEBATE_PROMPT.format(
                    opponent="Alpha", opponent_argument=last_alpha, history=history,
                ),
            )
            transcript.append(DebateTurn(
                speaker="beta", round_number=round_num,
                position="attack" if round_num <= 2 else "synthesis",
                content=beta_turn,
            ))
            history += f"\n\nBETA (round {round_num}):\n{beta_turn}"

            # Alpha responds
            alpha_turn = await self._call_llm(
                provider, self.alpha_model, ALPHA_SYSTEM,
                DEBATE_PROMPT.format(
                    opponent="Beta", opponent_argument=beta_turn, history=history,
                ),
            )
            transcript.append(DebateTurn(
                speaker="alpha", round_number=round_num,
                position="defense" if round_num <= 2 else "synthesis",
                content=alpha_turn,
            ))
            history += f"\n\nALPHA (round {round_num}):\n{alpha_turn}"
            last_alpha = alpha_turn

        # Phase 3: Extract loss report from debate
        loss_report = await self._extract_loss(provider, transcript)
        loss_report.debate_transcript = transcript
        return loss_report

    async def _extract_loss(
        self, provider: Any, transcript: list[DebateTurn],
    ) -> SystemLossReport:
        """Extract structured loss report from debate transcript."""
        transcript_text = "\n\n".join(
            f"[{t.speaker.upper()} - R{t.round_number} - {t.position}]\n{t.content}"
            for t in transcript
        )
        raw = await self._call_llm(
            provider, self.alpha_model,
            "You are a precise JSON extractor. Respond with ONLY valid JSON.",
            LOSS_EXTRACTION_PROMPT.format(transcript=transcript_text),
        )
        return self._parse_loss_report(raw)

    def _parse_loss_report(self, raw: str) -> SystemLossReport:
        """Parse LLM output into SystemLossReport."""
        import re
        raw = raw.strip()

        # Try direct parse
        for attempt in [raw, re.search(r"\{.*\}", raw, re.DOTALL)]:
            text = attempt.group() if hasattr(attempt, "group") else attempt
            try:
                data = json.loads(text)
                return SystemLossReport(
                    agreed_issues=[LossItem(**i) for i in data.get("agreed_issues", [])],
                    alpha_only_issues=[LossItem(**i) for i in data.get("alpha_only_issues", [])],
                    beta_only_issues=[LossItem(**i) for i in data.get("beta_only_issues", [])],
                    system_loss_score=float(data.get("system_loss_score", 0.5)),
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

        logger.warning("Failed to parse loss report, returning empty: %.200s", raw)
        return SystemLossReport(system_loss_score=0.5)

    async def _call_llm(
        self, provider: Any, model: str, system: str, user_msg: str,
    ) -> str:
        """Make an LLM call via the dharma_swarm provider."""
        request = LLMRequest(
            model=model,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=1500,
            temperature=0.7,
        )
        response = await provider.complete(request)
        return response.content


class _PreferredRuntimeProviderChain:
    """Minimal provider wrapper that enforces local/NIM-before-OpenRouter."""

    async def complete(self, request: LLMRequest) -> Any:
        configs = preferred_runtime_provider_configs(
            model_overrides={
                ProviderType.OPENROUTER_FREE: request.model,
                ProviderType.OPENROUTER: request.model,
            }
        )
        if not configs:
            raise RuntimeError(
                "No preferred providers available; configure Ollama, NVIDIA NIM, or OpenRouter"
            )

        last_exc: Exception | None = None
        for config in configs:
            provider = create_runtime_provider(config)
            try:
                provider_request = request.model_copy(
                    update={"model": config.default_model or request.model}
                )
                return await provider.complete(provider_request)
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Consolidation provider %s failed for model %s: %s",
                    config.provider.value,
                    config.default_model or request.model,
                    exc,
                )
            finally:
                close = getattr(provider, "close", None)
                if callable(close):
                    await close()

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Preferred provider chain exhausted without an explicit error")


# ---------------------------------------------------------------------------
# Behavioral Backpropagation
# ---------------------------------------------------------------------------

class BehavioralBackprop:
    """Phase 3: Generate and apply corrections based on the loss report."""

    def __init__(self, state_dir: Path) -> None:
        self._state_dir = state_dir

    async def apply(
        self, loss_report: SystemLossReport,
    ) -> list[BehavioralCorrection]:
        """Convert loss items into behavioral corrections and apply them."""
        corrections: list[BehavioralCorrection] = []

        for issue in loss_report.agreed_issues:
            correction = BehavioralCorrection(
                correction_type=self._categorize_correction(issue),
                target_agent=issue.affected_agents[0] if issue.affected_agents else "system",
                description=issue.proposed_correction or issue.description,
                rationale=issue.description,
                severity=issue.severity,
                veto_required=issue.severity >= SEVERITY_FLAG_REVIEW,
            )

            if correction.veto_required:
                # High severity — propose only, don't apply
                correction.applied = False
                correction.vetoed = False
                self._write_pending_veto(correction)
                logger.info(
                    "Consolidation: HIGH severity correction proposed (veto required): %s",
                    correction.description[:80],
                )
            elif issue.severity >= SEVERITY_AUTO_APPLY:
                # Medium severity — apply but flag for review
                applied = await self._apply_correction(correction)
                correction.applied = applied
                if applied:
                    logger.info(
                        "Consolidation: Applied correction (flagged for review): %s",
                        correction.description[:80],
                    )
            else:
                # Low severity — auto-apply
                applied = await self._apply_correction(correction)
                correction.applied = applied

            corrections.append(correction)

        return corrections

    def _categorize_correction(self, issue: LossItem) -> str:
        """Map issue category to correction type."""
        mapping = {
            "fitness_gap": "prompt_update",
            "memory_debt": "memory_adjustment",
            "coordination_failure": "prompt_update",
            "telos_drift": "corpus_claim",
            "capability_gap": "gate_proposal",
        }
        return mapping.get(issue.category, "prompt_update")

    async def _apply_correction(self, correction: BehavioralCorrection) -> bool:
        """Apply a behavioral correction through existing APIs."""
        try:
            if correction.correction_type == "memory_adjustment":
                return await self._apply_memory_correction(correction)
            elif correction.correction_type == "corpus_claim":
                return await self._apply_corpus_correction(correction)
            elif correction.correction_type == "prompt_update":
                return await self._apply_prompt_correction(correction)
            else:
                logger.info(
                    "Consolidation: Correction type '%s' logged but not auto-applied",
                    correction.correction_type,
                )
                return False
        except Exception as e:
            logger.error("Failed to apply correction: %s", e)
            return False

    async def _apply_memory_correction(self, correction: BehavioralCorrection) -> bool:
        """Apply a memory adjustment via AgentMemoryBank."""
        try:
            from dharma_swarm.agent_memory import AgentMemoryBank
            bank = AgentMemoryBank(
                agent_name=correction.target_agent,
                base_path=self._state_dir / "agent_memory",
            )
            await bank.remember(
                key=f"consolidation_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                value=correction.description,
                category="lesson",
                importance=correction.severity,
                source="consolidation_cycle",
            )
            return True
        except Exception as e:
            logger.warning("Memory correction failed: %s", e)
            return False

    async def _apply_corpus_correction(self, correction: BehavioralCorrection) -> bool:
        """Propose a new corpus claim via DharmaCorpus."""
        try:
            from dharma_swarm.dharma_corpus import ClaimCategory, DharmaCorpus
            corpus = DharmaCorpus(self._state_dir / "corpus.jsonl")
            await corpus.propose(
                statement=correction.description,
                category=ClaimCategory.LEARNED_CONSTRAINT,
                confidence=1.0 - correction.severity,
                created_by="consolidation_cycle",
            )
            return True
        except Exception as e:
            logger.warning("Corpus correction failed: %s", e)
            return False

    async def _apply_prompt_correction(self, correction: BehavioralCorrection) -> bool:
        """Log prompt update suggestion (actual prompt evolution via AgentRegistry)."""
        # Write to shared notes for the affected agent
        shared_dir = self._state_dir / "shared"
        shared_dir.mkdir(parents=True, exist_ok=True)
        note_file = shared_dir / "consolidation_corrections.jsonl"
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "target": correction.target_agent,
            "type": correction.correction_type,
            "description": correction.description,
            "rationale": correction.rationale,
            "severity": correction.severity,
        }
        with open(note_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return True

    def _write_pending_veto(self, correction: BehavioralCorrection) -> None:
        """Write high-severity correction to pending veto file."""
        veto_dir = self._state_dir / "consolidation"
        veto_dir.mkdir(parents=True, exist_ok=True)
        veto_file = veto_dir / "pending_veto.jsonl"
        with open(veto_file, "a", encoding="utf-8") as f:
            f.write(correction.model_dump_json() + "\n")


# ---------------------------------------------------------------------------
# Differentiation Check
# ---------------------------------------------------------------------------

class DifferentiationCheck:
    """Phase 4: Check if the system needs a new agent role."""

    def __init__(self, state_dir: Path, gap_threshold: int = 3) -> None:
        self._state_dir = state_dir
        self._gap_threshold = gap_threshold

    def check(
        self, loss_report: SystemLossReport, cycle_number: int,
    ) -> DifferentiationProposal | None:
        """Check for persistent capability gaps across consolidation cycles."""
        # Load previous gap history
        gap_file = self._state_dir / "consolidation" / "capability_gaps.jsonl"
        gap_history: list[dict[str, Any]] = []
        if gap_file.exists():
            for line in gap_file.read_text(encoding="utf-8").strip().split("\n"):
                if line.strip():
                    try:
                        gap_history.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

        # Record current capability gaps
        current_gaps = [
            i for i in loss_report.agreed_issues
            if i.category == "capability_gap"
        ]
        if current_gaps:
            gap_file.parent.mkdir(parents=True, exist_ok=True)
            with open(gap_file, "a", encoding="utf-8") as f:
                for gap in current_gaps:
                    f.write(json.dumps({
                        "cycle": cycle_number,
                        "description": gap.description,
                        "affected_agents": gap.affected_agents,
                    }) + "\n")

        # Check for persistent gaps (same description appearing in 3+ cycles)
        from collections import Counter
        gap_descriptions = [g.get("description", "") for g in gap_history]
        gap_descriptions.extend(g.description for g in current_gaps)
        counts = Counter(gap_descriptions)

        for desc, count in counts.items():
            if count >= self._gap_threshold and desc:
                cycles_seen = [
                    g.get("cycle", 0) for g in gap_history
                    if g.get("description") == desc
                ]
                if cycle_number not in cycles_seen:
                    cycles_seen.append(cycle_number)

                # Find the matching LossItem to extract parent agent and severity
                matching_gap = next(
                    (g for g in current_gaps if g.description == desc), None
                )
                parent = (
                    matching_gap.affected_agents[0]
                    if matching_gap and matching_gap.affected_agents
                    else "system"
                )
                gap_severity = matching_gap.severity if matching_gap else 0.5

                # Derive generation from parent's actual lineage
                parent_generation = 0
                try:
                    from dharma_swarm.agent_registry import AgentRegistry
                    _reg = AgentRegistry()
                    _identity = _reg.load_agent(parent)
                    if _identity and "prompt_generation" in _identity:
                        parent_generation = int(_identity["prompt_generation"])
                except Exception:
                    pass  # Static founding agents default to gen 0

                return DifferentiationProposal(
                    proposed_role=f"specialist_{desc[:30].replace(' ', '_')}",
                    justification=f"Persistent capability gap detected in {count} cycles",
                    capability_gap=desc,
                    evidence_cycles=cycles_seen,
                    parent_agent=parent,
                    generation=parent_generation + 1,
                    severity=gap_severity,
                )

        return None


# ---------------------------------------------------------------------------
# Consolidation Cycle (top-level orchestrator)
# ---------------------------------------------------------------------------

class ConsolidationCycle:
    """Orchestrates all four phases of the consolidation cycle.

    Usage:
        cycle = ConsolidationCycle(state_dir=Path("~/.dharma").expanduser())
        outcome = await cycle.run()
    """

    def __init__(
        self,
        state_dir: Path | None = None,
        alpha_model: str = DEFAULT_ALPHA_MODEL,
        beta_model: str = DEFAULT_BETA_MODEL,
        debate_rounds: int = 5,
    ) -> None:
        self._state_dir = state_dir or (Path.home() / ".dharma")
        self._observer = SystemObserver(self._state_dir)
        self._dialogue = ContrarianDialogue(
            alpha_model=alpha_model,
            beta_model=beta_model,
            rounds=debate_rounds,
        )
        self._backprop = BehavioralBackprop(self._state_dir)
        self._differentiation = DifferentiationCheck(self._state_dir)
        self._cycle_number = self._load_cycle_number()

    async def run(self, provider: Any = None) -> ConsolidationOutcome:
        """Execute one full consolidation cycle."""
        import time
        start = time.monotonic()

        self._cycle_number += 1
        cycle_dir = self._state_dir / "consolidation" / f"cycle_{self._cycle_number}"
        cycle_dir.mkdir(parents=True, exist_ok=True)

        logger.info("=== CONSOLIDATION CYCLE %d ===", self._cycle_number)

        # Phase 1: Observation
        logger.info("Phase 1: System observation")
        alpha_report = await self._observer.observe("alpha")
        beta_report = await self._observer.observe("beta")
        alpha_text = self._observer.compress_for_llm(alpha_report)
        beta_text = self._observer.compress_for_llm(beta_report)

        # Save state reports
        (cycle_dir / "alpha_state.json").write_text(
            alpha_report.model_dump_json(indent=2), encoding="utf-8",
        )
        (cycle_dir / "beta_state.json").write_text(
            beta_report.model_dump_json(indent=2), encoding="utf-8",
        )

        # Phase 2: Contrarian Dialogue
        logger.info("Phase 2: Contrarian dialogue")
        if provider is None:
            provider = self._get_default_provider()

        loss_report = await self._dialogue.run(alpha_text, beta_text, provider)

        # Save loss report
        (cycle_dir / "loss_report.json").write_text(
            loss_report.model_dump_json(indent=2), encoding="utf-8",
        )

        # Phase 3: Behavioral Backpropagation
        logger.info("Phase 3: Behavioral backpropagation")
        corrections = await self._backprop.apply(loss_report)

        # Save corrections
        (cycle_dir / "corrections.json").write_text(
            json.dumps([c.model_dump() for c in corrections], indent=2, default=str),
            encoding="utf-8",
        )

        # Phase 4: Differentiation Check
        logger.info("Phase 4: Differentiation check")
        proposal = self._differentiation.check(loss_report, self._cycle_number)
        if proposal:
            logger.info(
                "DIFFERENTIATION PROPOSAL: %s (gap: %s)",
                proposal.proposed_role, proposal.capability_gap,
            )
            (cycle_dir / "differentiation_proposal.json").write_text(
                proposal.model_dump_json(indent=2), encoding="utf-8",
            )
            # Handoff to ReplicationProtocol: write proposal to durable
            # proposals.jsonl so the replication monitor loop can pick it up.
            self._handoff_to_replication(proposal)

        # Build outcome
        duration = time.monotonic() - start
        outcome = ConsolidationOutcome(
            cycle_number=self._cycle_number,
            loss_report=loss_report,
            corrections_proposed=len(corrections),
            corrections_applied=sum(1 for c in corrections if c.applied),
            corrections_vetoed=sum(1 for c in corrections if c.vetoed),
            system_loss_score=loss_report.system_loss_score,
            duration_seconds=duration,
        )

        # Save outcome
        (cycle_dir / "outcome.json").write_text(
            outcome.model_dump_json(indent=2), encoding="utf-8",
        )

        # Update latest symlink
        latest = self._state_dir / "consolidation" / "latest"
        latest.unlink(missing_ok=True)
        try:
            latest.symlink_to(cycle_dir.name)
        except OSError:
            pass

        # Persist cycle number
        self._save_cycle_number()

        # Emit signal
        self._emit_signal(outcome)

        logger.info(
            "=== CONSOLIDATION CYCLE %d COMPLETE (%.1fs) ===\n"
            "  Loss: %.3f | Corrections: %d proposed, %d applied",
            self._cycle_number, duration,
            outcome.system_loss_score,
            outcome.corrections_proposed, outcome.corrections_applied,
        )

        return outcome

    def _load_cycle_number(self) -> int:
        """Load the current cycle number from disk."""
        counter_file = self._state_dir / "consolidation" / "cycle_counter.txt"
        if counter_file.exists():
            try:
                return int(counter_file.read_text().strip())
            except (ValueError, OSError):
                pass
        return 0

    def _save_cycle_number(self) -> None:
        """Persist the current cycle number."""
        counter_dir = self._state_dir / "consolidation"
        counter_dir.mkdir(parents=True, exist_ok=True)
        (counter_dir / "cycle_counter.txt").write_text(
            str(self._cycle_number), encoding="utf-8",
        )

    def _get_default_provider(self) -> Any:
        """Get the canonical low-cost provider chain for the dialogue."""
        return _PreferredRuntimeProviderChain()

    def _emit_signal(self, outcome: ConsolidationOutcome) -> None:
        """Emit a signal to the SignalBus."""
        try:
            from dharma_swarm.signal_bus import SignalBus
            SignalBus.get().emit({
                "type": "CONSOLIDATION_COMPLETE",
                "cycle": outcome.cycle_number,
                "loss": outcome.system_loss_score,
                "corrections_proposed": outcome.corrections_proposed,
                "corrections_applied": outcome.corrections_applied,
            })
        except Exception:
            pass  # Signal bus may not be available in test contexts

    def _handoff_to_replication(self, proposal: DifferentiationProposal) -> None:
        """Write a DifferentiationProposal to the replication pipeline.

        Appends the proposal dict to ``~/.dharma/replication/proposals.jsonl``
        (the file ReplicationProtocol.get_pending_proposals() reads) and emits
        SIGNAL_REPLICATION_PROPOSAL on the signal bus so the replication
        monitor loop can wake early.

        Wrapped in try/except: handoff failure must never crash the
        consolidation cycle. The proposal is already persisted in the
        cycle directory as a fallback.
        """
        try:
            replication_dir = self._state_dir / "replication"
            replication_dir.mkdir(parents=True, exist_ok=True)
            proposals_file = replication_dir / "proposals.jsonl"

            # Build a dict compatible with ReplicationProposal.model_validate()
            proposal_data = proposal.model_dump()
            proposal_data.setdefault("parent_agent", proposal.parent_agent or "system")
            proposal_data.setdefault("generation", proposal.generation)
            proposal_data.setdefault("severity", proposal.severity)

            with open(proposals_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(proposal_data, default=str) + "\n")

            logger.info(
                "Replication handoff: proposal '%s' written to %s",
                proposal.proposed_role,
                proposals_file,
            )
        except Exception as exc:
            logger.warning("Replication handoff (file write) failed: %s", exc)

        # Emit signal (fast-path trigger for the replication monitor loop)
        try:
            from dharma_swarm.signal_bus import SIGNAL_REPLICATION_PROPOSAL, SignalBus
            SignalBus.get().emit({
                "type": SIGNAL_REPLICATION_PROPOSAL,
                "proposed_role": proposal.proposed_role,
                "capability_gap": proposal.capability_gap,
                "parent_agent": proposal.parent_agent,
                "severity": proposal.severity,
            })
        except Exception:
            pass  # Signal bus may not be available in test contexts
