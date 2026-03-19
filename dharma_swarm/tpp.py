"""Transmission Prompt Protocol (TPP) — living medium of multi-agent intelligence.

The prompt is not just instructions — it is the nervous system of the swarm.
Context depth decays exponentially across agent boundaries (100% → 10% → 1%).
TPP preserves causal depth, telos continuity, and semantic fidelity through
every layer of a multi-agent hierarchy.

Architecture (5 levels, each compresses the level above):

    Level 4 (TELOS)     — Why does this agent exist?
    Level 3 (IDENTITY)  — Who is this agent? Witness stance?
    Level 2 (CONTEXT)   — What does this agent need to know?
    Level 1 (TASK)      — What does this agent need to do?
    Level 0 (TECHNICAL) — How does this agent operate?

Stripping any level corrupts all levels below.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal  # noqa: F401 — Path used in type comments

from dharma_swarm.models import _new_id

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TPP_VERSION = "1.0.0"

# Shakti modes — energy calibration for task types
SHAKTI_MODES = {
    "iccha": "Creative exploration, divergent thinking, novel connections",
    "jnana": "Analytical precision, research, deep investigation",
    "kriya": "Implementation, execution, building, shipping",
    "para": "Integration, synthesis, witnessing, meta-cognition",
}

# Compression levels for semantic abstraction
CompressionLevel = Literal["full", "semantic", "principled", "telos", "seed"]

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class TPPLevel(str, Enum):
    """The five levels of a Transmission Prompt."""
    TELOS = "telos"
    IDENTITY = "identity"
    CONTEXT = "context"
    TASK = "task"
    TECHNICAL = "technical"


@dataclass
class IntentThread:
    """Immutable record of original operator intent, carried through every agent.

    Like a distributed trace ID but richer — preserves the WHY, not just the WHO.
    """
    operator_intent: str
    telos: str
    trace_id: str = field(default_factory=_new_id)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    depth_budget: int = 0  # 0 = unlimited
    original_context_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator_intent": self.operator_intent,
            "telos": self.telos,
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "depth_budget": self.depth_budget,
            "original_context_hash": self.original_context_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IntentThread:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ContextReceipt:
    """Audit trail entry documenting what context was preserved vs. omitted.

    Each agent produces a receipt when compressing context for a child.
    Chain of receipts = full reconstruction path.
    """
    agent_id: str
    compression_level: CompressionLevel
    received_context_hash: str
    compressed_context_hash: str
    preserved: list[str]  # What was kept (topic labels)
    omitted: list[str]    # What was dropped (topic labels)
    omission_reasons: dict[str, str] = field(default_factory=dict)
    recovery_hints: dict[str, str] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "compression_level": self.compression_level,
            "received_context_hash": self.received_context_hash,
            "compressed_context_hash": self.compressed_context_hash,
            "preserved": self.preserved,
            "omitted": self.omitted,
            "omission_reasons": self.omission_reasons,
            "recovery_hints": self.recovery_hints,
            "timestamp": self.timestamp,
        }


@dataclass
class SiblingSignal:
    """Structured findings from a sibling agent for integration into prompts."""
    agent_id: str
    agent_role: str
    finding_summary: str
    confidence: float = 0.5
    telos_alignment: float = 0.5
    relevance_tags: list[str] = field(default_factory=list)
    raw_findings: str = ""

    def to_prompt_fragment(self, max_chars: int = 500) -> str:
        """Format as an injectable prompt fragment."""
        summary = self.finding_summary[:max_chars]
        return (
            f"[Sibling: {self.agent_role} | "
            f"confidence={self.confidence:.2f} | "
            f"telos_alignment={self.telos_alignment:.2f}]\n"
            f"{summary}"
        )


@dataclass
class TPPPrompt:
    """A fully-formed Transmission Prompt with all 5 levels."""
    telos: str = ""
    identity: str = ""
    context: str = ""
    task: str = ""
    technical: str = ""
    intent_thread: IntentThread | None = None
    context_receipt: ContextReceipt | None = None
    sibling_signals: list[SiblingSignal] = field(default_factory=list)
    shakti_mode: str = "jnana"
    cascade_depth: int = 0  # How many hops from operator
    version: str = TPP_VERSION

    def render(self) -> str:
        """Render the prompt as a formatted string for injection into an LLM."""
        sections = []

        # Level 4: TELOS
        if self.telos:
            sections.append(f"## TELOS (why you exist)\n{self.telos}")

        # Level 3: IDENTITY
        if self.identity:
            identity_block = self.identity
            if self.shakti_mode in SHAKTI_MODES:
                identity_block += f"\nShakti mode: {self.shakti_mode} — {SHAKTI_MODES[self.shakti_mode]}"
            sections.append(f"## IDENTITY (who you are)\n{identity_block}")

        # Level 2: CONTEXT
        ctx_parts = []
        if self.context:
            ctx_parts.append(self.context)
        if self.intent_thread:
            ctx_parts.append(
                f"\n### Intent Thread (from operator)\n"
                f"Original intent: {self.intent_thread.operator_intent}\n"
                f"Telos: {self.intent_thread.telos}\n"
                f"Trace: {self.intent_thread.trace_id}"
            )
        if self.sibling_signals:
            ctx_parts.append("\n### Sibling Findings")
            for sig in self.sibling_signals:
                ctx_parts.append(sig.to_prompt_fragment())
        if ctx_parts:
            sections.append(f"## CONTEXT (what you need to know)\n" + "\n".join(ctx_parts))

        # Level 1: TASK
        if self.task:
            sections.append(f"## TASK (what you need to do)\n{self.task}")

        # Level 0: TECHNICAL
        tech_parts = []
        if self.technical:
            tech_parts.append(self.technical)
        if self.cascade_depth > 0:
            tech_parts.append(
                f"\n### Cascade Protocol\n"
                f"You are at cascade depth {self.cascade_depth}. "
                f"If you need to spawn sub-agents, use TPP format with "
                f"depth={self.cascade_depth + 1}. "
                f"Thread the intent thread through to all children. "
                f"Compress your context using semantic abstraction before passing down."
            )
        if self.context_receipt:
            tech_parts.append(
                f"\n### Context Receipt\n"
                f"Compression: {self.context_receipt.compression_level}\n"
                f"Preserved: {', '.join(self.context_receipt.preserved)}\n"
                f"Omitted: {', '.join(self.context_receipt.omitted)}"
            )
        if tech_parts:
            sections.append(f"## TECHNICAL (how you operate)\n" + "\n".join(tech_parts))

        return "\n\n".join(sections)

    def token_estimate(self) -> int:
        """Rough token count (chars / 3.8)."""
        return max(1, int(len(self.render()) / 3.8))

    def to_dict(self) -> dict[str, Any]:
        return {
            "telos": self.telos,
            "identity": self.identity,
            "context": self.context,
            "task": self.task,
            "technical": self.technical,
            "intent_thread": self.intent_thread.to_dict() if self.intent_thread else None,
            "context_receipt": self.context_receipt.to_dict() if self.context_receipt else None,
            "sibling_signals": [
                {"agent_id": s.agent_id, "agent_role": s.agent_role,
                 "finding_summary": s.finding_summary,
                 "confidence": s.confidence, "telos_alignment": s.telos_alignment}
                for s in self.sibling_signals
            ],
            "shakti_mode": self.shakti_mode,
            "cascade_depth": self.cascade_depth,
            "version": self.version,
        }


# ---------------------------------------------------------------------------
# Semantic Compression Engine
# ---------------------------------------------------------------------------


def _content_hash(text: str) -> str:
    """SHA-256 hash of content for receipts."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _extract_headings(text: str) -> list[str]:
    """Extract markdown headings as topic labels."""
    return [line.lstrip("#").strip() for line in text.split("\n") if line.startswith("#")]


def _extract_key_sentences(text: str, budget: int) -> str:
    """Extract sentences with highest information density.

    Heuristic: sentences containing numbers, proper nouns, or technical terms
    are more likely to be load-bearing.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if not sentences:
        return text[:budget]

    scored: list[tuple[float, str]] = []
    for sent in sentences:
        score = 0.0
        # Numbers indicate specific claims
        if re.search(r'\d+\.?\d*', sent):
            score += 2.0
        # Technical terms (CamelCase, snake_case, code refs)
        if re.search(r'[A-Z][a-z]+[A-Z]|_[a-z]+_|`[^`]+`', sent):
            score += 1.5
        # Causal language
        if any(word in sent.lower() for word in ("because", "therefore", "causes", "implies", "proves")):
            score += 1.0
        # Conclusion language
        if any(word in sent.lower() for word in ("finding", "result", "conclude", "key", "critical")):
            score += 1.0
        # Short sentences are usually topic sentences
        if len(sent.split()) < 15:
            score += 0.5
        scored.append((score, sent))

    scored.sort(key=lambda x: x[0], reverse=True)

    result = []
    chars = 0
    for _, sent in scored:
        if chars + len(sent) > budget:
            break
        result.append(sent)
        chars += len(sent) + 1

    return " ".join(result) if result else text[:budget]


def compress_semantic(
    content: str,
    level: CompressionLevel = "semantic",
    budget: int = 5000,
) -> tuple[str, ContextReceipt]:
    """Compress content using semantic abstraction, not truncation.

    Returns (compressed_text, receipt) so the caller knows what was kept/dropped.

    Levels:
        full:       No compression, return as-is
        semantic:    Drop examples, keep principles and findings (~50% reduction)
        principled:  Abstract to patterns and principles (~80% reduction)
        telos:       Purpose + key constraints only (~95% reduction)
        seed:        Single paragraph that could regenerate context (~99% reduction)
    """
    original_hash = _content_hash(content)
    headings = _extract_headings(content)
    preserved: list[str] = []
    omitted: list[str] = []

    if level == "full" or len(content) <= budget:
        compressed = content[:budget]
        preserved = headings
        omitted = []
    elif level == "semantic":
        # Drop examples and verbose explanations, keep principles and findings
        lines = content.split("\n")
        kept: list[str] = []
        in_example = False
        chars = 0
        for line in lines:
            # Skip example blocks
            if "example" in line.lower() and line.strip().startswith(("#", "```", ">")):
                in_example = True
                omitted.append("example block")
                continue
            if in_example and (line.startswith("#") or line.startswith("```")):
                in_example = False
            if in_example:
                continue
            # Skip verbose explanations (lines starting with "For example", "Consider", etc.)
            stripped = line.strip()
            if stripped.lower().startswith(("for example", "consider ", "note that", "e.g.", "i.e.")):
                omitted.append("verbose explanation")
                continue
            if chars + len(line) > budget:
                break
            kept.append(line)
            chars += len(line) + 1
            if line.startswith("#"):
                preserved.append(line.lstrip("#").strip())
        compressed = "\n".join(kept)
    elif level == "principled":
        # Extract key sentences by information density
        compressed = _extract_key_sentences(content, budget)
        preserved = ["key sentences by information density"]
        omitted = ["examples", "verbose explanations", "low-density sentences"]
    elif level == "telos":
        # Purpose + constraints only
        lines = content.split("\n")
        purpose_lines: list[str] = []
        chars = 0
        for line in lines:
            stripped = line.strip().lower()
            if any(kw in stripped for kw in (
                "purpose", "telos", "goal", "why", "must", "constraint",
                "requirement", "critical", "never", "always",
            )):
                if chars + len(line) <= budget:
                    purpose_lines.append(line)
                    chars += len(line) + 1
        compressed = "\n".join(purpose_lines) if purpose_lines else content[:budget]
        preserved = ["purpose statements", "constraints"]
        omitted = ["all implementation detail", "examples", "background"]
    elif level == "seed":
        # Single paragraph regeneration seed
        first_heading = headings[0] if headings else "Context"
        key_sentences = _extract_key_sentences(content, budget - 100)
        compressed = f"[Seed: {first_heading}] {key_sentences}"
        preserved = ["regeneration seed"]
        omitted = ["everything except highest-density sentences"]
    else:
        compressed = content[:budget]
        preserved = ["head truncation"]
        omitted = ["tail"]

    receipt = ContextReceipt(
        agent_id="tpp_compressor",
        compression_level=level,
        received_context_hash=original_hash,
        compressed_context_hash=_content_hash(compressed),
        preserved=preserved,
        omitted=list(set(omitted)),
    )

    return compressed, receipt


# ---------------------------------------------------------------------------
# Prompt Composition
# ---------------------------------------------------------------------------


def compose_prompt(
    *,
    task_description: str,
    telos: str = "",
    identity: str = "",
    context: str = "",
    technical: str = "",
    intent_thread: IntentThread | None = None,
    sibling_signals: list[SiblingSignal] | None = None,
    shakti_mode: str = "jnana",
    cascade_depth: int = 0,
    context_budget: int = 5000,
    compression_level: CompressionLevel = "semantic",
    anti_patterns: list[str] | None = None,
) -> TPPPrompt:
    """Compose a TPP-formatted prompt for spawning a subagent.

    This is the primary API. Given a task and optional context, produces
    a fully-formed TPP prompt with all 5 levels populated.

    Args:
        task_description: What the agent needs to do.
        telos: Why this agent exists (derived from parent's telos if not set).
        identity: Who this agent is (experiential, not prestige).
        context: Full context to be semantically compressed.
        technical: Tool constraints, output format, etc.
        intent_thread: Immutable operator intent (threaded from parent).
        sibling_signals: Findings from parallel agents at this level.
        shakti_mode: Energy calibration (iccha/jnana/kriya/para).
        cascade_depth: How many hops from the operator.
        context_budget: Max chars for context after compression.
        compression_level: How aggressively to compress context.
        anti_patterns: Top 2-3 failure modes to avoid.
    """
    # Compress context if needed
    context_receipt = None
    compressed_context = context
    if context and len(context) > context_budget:
        compressed_context, context_receipt = compress_semantic(
            context, level=compression_level, budget=context_budget,
        )

    # Build task section with anti-patterns
    task_section = task_description
    if anti_patterns:
        task_section += "\n\n### Anti-patterns (do NOT do these)\n"
        for ap in anti_patterns:
            task_section += f"- {ap}\n"

    # Default telos from intent thread
    if not telos and intent_thread:
        telos = (
            f"You exist to serve: {intent_thread.telos}\n"
            f"Operator asked: {intent_thread.operator_intent}"
        )

    return TPPPrompt(
        telos=telos,
        identity=identity,
        context=compressed_context,
        task=task_section,
        technical=technical,
        intent_thread=intent_thread,
        context_receipt=context_receipt,
        sibling_signals=sibling_signals or [],
        shakti_mode=shakti_mode,
        cascade_depth=cascade_depth,
    )


def compose_cascade(
    *,
    parent_prompt: TPPPrompt,
    subtasks: list[dict[str, Any]],
    parent_findings: str = "",
) -> list[TPPPrompt]:
    """Generate cascading prompts for multi-agent work.

    Each child inherits the parent's telos, intent thread, and a compressed
    version of the parent's context. Sibling signals are wired so later
    agents know what earlier ones found.

    Args:
        parent_prompt: The parent agent's TPP prompt.
        subtasks: List of dicts with keys: task, identity, shakti_mode, anti_patterns.
        parent_findings: What the parent agent found so far (optional).
    """
    child_prompts: list[TPPPrompt] = []
    accumulated_signals: list[SiblingSignal] = []

    # Compress parent context for children
    parent_context = parent_prompt.context
    if parent_findings:
        parent_context = f"{parent_context}\n\n### Parent Findings\n{parent_findings}"

    for sub in subtasks:
        child = compose_prompt(
            task_description=sub.get("task", ""),
            telos=parent_prompt.telos,
            identity=sub.get("identity", ""),
            context=parent_context,
            technical=sub.get("technical", parent_prompt.technical),
            intent_thread=parent_prompt.intent_thread,
            sibling_signals=list(accumulated_signals),
            shakti_mode=sub.get("shakti_mode", parent_prompt.shakti_mode),
            cascade_depth=parent_prompt.cascade_depth + 1,
            context_budget=sub.get("context_budget", 3000),
            compression_level=sub.get("compression_level", "principled"),
            anti_patterns=sub.get("anti_patterns"),
        )
        child_prompts.append(child)

        # Wire sibling signal for next agents
        accumulated_signals.append(SiblingSignal(
            agent_id=f"sibling_{len(accumulated_signals)}",
            agent_role=sub.get("role", "agent"),
            finding_summary=f"[Will produce: {sub.get('task', '')[:100]}]",
            confidence=0.0,  # Not yet completed
            telos_alignment=0.8,
        ))

    return child_prompts


# ---------------------------------------------------------------------------
# Prompt Quality Evaluation
# ---------------------------------------------------------------------------


@dataclass
class PromptScore:
    """Result of evaluating a prompt against TPP quality metrics."""
    # Structural metrics (0-5 scale)
    information_density: float = 0.0
    specificity: float = 0.0
    measurability: float = 0.0
    token_efficiency: float = 0.0
    structural_completeness: float = 0.0
    # Thinkodynamic metrics
    telos_continuity: float = 0.0
    depth_ratio: float = 0.0
    shakti_calibration: float = 0.0
    # Composite
    transmission_quality_score: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "information_density": self.information_density,
            "specificity": self.specificity,
            "measurability": self.measurability,
            "token_efficiency": self.token_efficiency,
            "structural_completeness": self.structural_completeness,
            "telos_continuity": self.telos_continuity,
            "depth_ratio": self.depth_ratio,
            "shakti_calibration": self.shakti_calibration,
            "tqs": self.transmission_quality_score,
        }


def evaluate_prompt(prompt: TPPPrompt) -> PromptScore:
    """Score a TPP prompt against quality metrics.

    Returns a PromptScore with individual metrics and composite TQS.
    All metrics are 0-5 scale. TQS is weighted average mapped to 0-1.
    """
    rendered = prompt.render()
    score = PromptScore()

    # --- Structural metrics ---

    # Information density: semantic content / total chars
    words = rendered.split()
    total_chars = len(rendered)
    if total_chars > 0:
        # Unique meaningful words / total words as proxy for density
        meaningful = {w.lower() for w in words if len(w) > 3 and not w.startswith("#")}
        density = len(meaningful) / max(1, len(words))
        score.information_density = min(5.0, density * 10)

    # Specificity: concrete terms vs vague terms
    vague_terms = sum(1 for w in words if w.lower() in {
        "things", "stuff", "various", "general", "overall", "appropriate",
        "relevant", "suitable", "etc", "basically", "essentially",
    })
    concrete_terms = sum(1 for w in words if (
        re.match(r'^[A-Z][a-z]+[A-Z]', w) or  # CamelCase
        '_' in w or  # snake_case
        re.match(r'^\d', w) or  # numbers
        w.startswith('`')  # code refs
    ))
    if len(words) > 0:
        specificity_ratio = (concrete_terms + 1) / (vague_terms + 1)
        score.specificity = min(5.0, specificity_ratio)

    # Measurability: % of task section with clear completion criteria
    task_text = prompt.task
    measurable_markers = sum(1 for marker in [
        "return", "output", "produce", "list", "score", "count",
        "verify", "ensure", "must", "complete when",
    ] if marker in task_text.lower())
    score.measurability = min(5.0, measurable_markers * 1.0)

    # Token efficiency
    token_est = prompt.token_estimate()
    if token_est > 0:
        # Penalize prompts that are too long or too short
        if 200 < token_est < 3000:
            score.token_efficiency = 4.0
        elif 100 < token_est <= 200 or 3000 <= token_est < 8000:
            score.token_efficiency = 3.0
        elif token_est >= 8000:
            score.token_efficiency = 1.0
        else:
            score.token_efficiency = 2.0

    # Structural completeness: all 5 TPP levels present
    levels_present = sum([
        bool(prompt.telos),
        bool(prompt.identity),
        bool(prompt.context),
        bool(prompt.task),
        bool(prompt.technical),
    ])
    score.structural_completeness = levels_present  # 0-5 naturally

    # --- Thinkodynamic metrics ---

    # Telos continuity: can the prompt trace to operator intent?
    if prompt.intent_thread and prompt.telos:
        score.telos_continuity = 5.0
    elif prompt.telos:
        score.telos_continuity = 3.0
    elif prompt.intent_thread:
        score.telos_continuity = 2.0
    else:
        score.telos_continuity = 0.0

    # Depth ratio: thinkodynamic content / total tokens
    depth_markers = sum(1 for marker in [
        "telos", "witness", "shakti", "swabhaav", "eigenform",
        "purpose", "why you exist", "intent thread",
        "dharma", "ahimsa", "moksha",
    ] if marker in rendered.lower())
    if token_est > 0:
        depth_ratio = depth_markers / (token_est / 100)
        score.depth_ratio = min(5.0, depth_ratio * 2)

    # Shakti calibration: is mode set and appropriate?
    if prompt.shakti_mode in SHAKTI_MODES:
        score.shakti_calibration = 4.0
        # Bonus for coherence between mode and task
        task_lower = prompt.task.lower()
        mode_words = {
            "iccha": ["explore", "create", "brainstorm", "imagine", "novel"],
            "jnana": ["analyze", "research", "investigate", "measure", "prove"],
            "kriya": ["implement", "build", "fix", "deploy", "ship"],
            "para": ["synthesize", "integrate", "review", "witness", "connect"],
        }
        matches = sum(1 for w in mode_words.get(prompt.shakti_mode, []) if w in task_lower)
        if matches >= 2:
            score.shakti_calibration = 5.0
    else:
        score.shakti_calibration = 1.0

    # --- Composite TQS ---
    weights = {
        "information_density": 0.10,
        "specificity": 0.10,
        "measurability": 0.10,
        "token_efficiency": 0.05,
        "structural_completeness": 0.20,
        "telos_continuity": 0.20,
        "depth_ratio": 0.10,
        "shakti_calibration": 0.15,
    }
    weighted_sum = sum(
        getattr(score, metric) * weight
        for metric, weight in weights.items()
    )
    score.transmission_quality_score = weighted_sum / 5.0  # Normalize to 0-1

    return score


# ---------------------------------------------------------------------------
# Telos Threading
# ---------------------------------------------------------------------------


def create_intent_thread(
    operator_intent: str,
    telos: str = "Jagat Kalyan — universal welfare",
    context: str = "",
) -> IntentThread:
    """Create a new intent thread from operator input.

    This is the ROOT of a chain. All child agents inherit this thread.
    """
    return IntentThread(
        operator_intent=operator_intent,
        telos=telos,
        original_context_hash=_content_hash(context) if context else "",
    )


def verify_telos_continuity(prompt: TPPPrompt) -> tuple[bool, str]:
    """Verify that a prompt maintains telos continuity.

    Returns (passes, reason).
    A prompt has telos continuity if it can trace its purpose
    back to the operator's original intent.
    """
    if not prompt.telos:
        return False, "No telos statement present"
    if not prompt.intent_thread:
        return prompt.cascade_depth == 0, (
            "No intent thread — acceptable only at depth 0"
            if prompt.cascade_depth == 0
            else "No intent thread at cascade depth > 0"
        )
    # Check that telos references operator intent
    intent_words = set(prompt.intent_thread.operator_intent.lower().split())
    telos_words = set(prompt.telos.lower().split())
    overlap = intent_words & telos_words
    if len(overlap) < 2:
        return False, f"Telos has low overlap with operator intent ({len(overlap)} words)"
    return True, "Telos traces to operator intent"


# ---------------------------------------------------------------------------
# Handoff Integration — TPP-formatted artifacts
# ---------------------------------------------------------------------------


def format_handoff_as_tpp(
    *,
    from_agent: str,
    from_role: str,
    findings: str,
    confidence: float = 0.5,
    telos_alignment: float = 0.5,
    intent_thread: IntentThread | None = None,
) -> str:
    """Format agent findings as a TPP fragment for handoff.

    Instead of passing raw text between agents, this structures the
    findings so they can be directly injected into another agent's prompt.
    """
    parts = [
        f"## Handoff from {from_agent} ({from_role})",
        f"Confidence: {confidence:.2f} | Telos alignment: {telos_alignment:.2f}",
    ]
    if intent_thread:
        parts.append(f"Trace: {intent_thread.trace_id}")
    parts.append(f"\n### Findings\n{findings}")
    return "\n".join(parts)


def format_stigmergy_tpp(
    *,
    agent: str,
    observation: str,
    telos_tag: str = "",
    salience: float = 0.5,
    connections: list[str] | None = None,
) -> dict[str, Any]:
    """Format a stigmergy mark as a TPP-structured fragment.

    Expands beyond the 200-char limit of raw marks by including
    structured metadata that enables richer cross-agent communication.
    """
    return {
        "agent": agent,
        "observation": observation[:500],  # Expanded from 200
        "telos_tag": telos_tag,
        "salience": salience,
        "connections": connections or [],
        "tpp_version": TPP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Prompt Templates — Pre-built TPP templates for common agent types
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, dict[str, str]] = {
    "research": {
        "identity": (
            "You are a research agent. You have investigated complex systems before — "
            "some hypotheses confirmed, others overturned by data. You know the difference "
            "between correlation and causation, between suggestive and conclusive."
        ),
        "shakti_mode": "jnana",
        "anti_patterns": (
            "Do not summarize without synthesizing. "
            "Do not list findings without connecting them. "
            "Do not cite without verifying."
        ),
    },
    "builder": {
        "identity": (
            "You are an implementation agent. You have shipped systems that worked "
            "and systems that collapsed under their own abstractions. You know that "
            "the thinnest working version teaches more than the most elaborate plan."
        ),
        "shakti_mode": "kriya",
        "anti_patterns": (
            "Do not build from scratch when code exists to extend. "
            "Do not add abstractions for hypothetical future needs. "
            "Do not skip tests."
        ),
    },
    "reviewer": {
        "identity": (
            "You are an audit agent. You have caught bugs that passed every test, "
            "claims that sounded right but were wrong by an order of magnitude, "
            "and architectures that looked clean until the first real load."
        ),
        "shakti_mode": "para",
        "anti_patterns": (
            "Do not rubber-stamp. "
            "Do not critique style when substance is wrong. "
            "Do not miss the forest for the trees."
        ),
    },
    "synthesizer": {
        "identity": (
            "You are a synthesis agent. You see connections between domains that "
            "specialists miss. You know that the most important insight is often "
            "the one that links two findings nobody thought were related."
        ),
        "shakti_mode": "para",
        "anti_patterns": (
            "Do not produce a list of summaries — produce an integrated understanding. "
            "Do not force connections that don't exist. "
            "Do not lose the original nuance in the act of integrating."
        ),
    },
    "creative": {
        "identity": (
            "You are a creative exploration agent. You have learned that the best ideas "
            "come from the edges of the distribution, from combining things that "
            "weren't supposed to go together. Constraints catalyze, not limit."
        ),
        "shakti_mode": "iccha",
        "anti_patterns": (
            "Do not generate obvious variations of existing ideas. "
            "Do not self-censor for feasibility before exploring. "
            "Do not optimize before you have something worth optimizing."
        ),
    },
    "cascade": {
        "identity": (
            "You are an orchestrator agent. You decompose complex work into focused "
            "sub-tasks and spawn sub-agents to handle each one. You know that "
            "the quality of the decomposition determines the quality of the outcome."
        ),
        "shakti_mode": "para",
        "anti_patterns": (
            "Do not spawn too many sub-agents (max 10). "
            "Do not pass raw context — compress semantically. "
            "Do not lose the telos in the decomposition."
        ),
    },
}


def compose_from_template(
    template_name: str,
    *,
    task_description: str,
    telos: str = "",
    context: str = "",
    intent_thread: IntentThread | None = None,
    **kwargs: Any,
) -> TPPPrompt:
    """Compose a prompt using a pre-built template.

    Templates provide identity, shakti_mode, and anti_patterns.
    Caller provides task, telos, context, and intent_thread.
    """
    template = TEMPLATES.get(template_name, TEMPLATES["research"])
    anti_patterns = template.get("anti_patterns", "").split(". ")
    anti_patterns = [ap.strip().rstrip(".") for ap in anti_patterns if ap.strip()]

    return compose_prompt(
        task_description=task_description,
        telos=telos,
        identity=template["identity"],
        context=context,
        intent_thread=intent_thread,
        shakti_mode=template.get("shakti_mode", "jnana"),
        anti_patterns=anti_patterns,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Quick Evaluation (3-metric gut check)
# ---------------------------------------------------------------------------


def quick_check(prompt: TPPPrompt) -> dict[str, Any]:
    """Fast 3-metric check when full evaluation is too expensive.

    Returns: {passes: bool, telos: bool, structure: bool, specificity: bool, summary: str}
    """
    has_telos = bool(prompt.telos)
    has_structure = sum([
        bool(prompt.telos),
        bool(prompt.identity),
        bool(prompt.context),
        bool(prompt.task),
        bool(prompt.technical),
    ]) >= 3
    task_words = prompt.task.split()
    vague = sum(1 for w in task_words if w.lower() in {
        "things", "stuff", "various", "general", "appropriate",
    })
    has_specificity = len(task_words) > 10 and vague < len(task_words) * 0.1

    passes = has_telos and has_structure and has_specificity
    return {
        "passes": passes,
        "telos": has_telos,
        "structure": has_structure,
        "specificity": has_specificity,
        "summary": (
            "PASS" if passes else
            f"FAIL: {'no telos' if not has_telos else ''}"
            f"{'incomplete structure' if not has_structure else ''}"
            f"{'too vague' if not has_specificity else ''}"
        ).strip(),
    }
