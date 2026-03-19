"""Prompt Evolution Protocol -- Darwin Engine for prompt populations.

Evolutionary optimization of prompt templates through fitness-scored
mutation, crossover, selection, and canary deployment. Integrates with
the existing DarwinEngine pipeline, telos gates, and canary deployer.

Architecture:
    PromptGenome    -- evolvable prompt representation with invariant/mutable segments
    PromptFitness   -- multi-dimensional fitness scoring for prompts
    PromptEvolver   -- evolution operators (mutation, crossover, selection)
    PromptPopulation -- manages a population of prompt variants
    PromptEvolutionEngine -- orchestrates the full evolution loop

Literature grounding:
    - DSPy: gradient-free prompt optimization via bootstrapped demonstrations
    - EvoPrompt: evolutionary algorithms (GA, DE) on prompt populations
    - OPRO: LLMs optimize their own prompts via meta-prompting
    - Constitutional AI: self-correction as iterative prompt refinement
    - MAP-Elites: quality-diversity optimization preserving behavioral niches

Integration points:
    - DarwinEngine.run_cycle() can wrap prompt evolution as a proposal type
    - CanaryDeployer.evaluate_canary() validates prompt variants before promotion
    - TelosGatekeeper.check() gates all evolved prompts through 11 dharmic gates
    - EvolutionArchive stores prompt lineage with full fitness history
    - MetaEvolutionEngine can evolve the prompt evolution hyperparameters

Pipeline:
    SEED -> EVALUATE POPULATION -> SELECT PARENTS -> APPLY OPERATORS
    -> GATE CHECK -> CANARY DEPLOY -> MEASURE FITNESS -> ARCHIVE
    -> PROMOTE/ROLLBACK -> NEXT GENERATION
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import random
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from statistics import mean, pvariance, stdev
from typing import Any, Callable, Optional, Sequence

from pydantic import BaseModel, Field

from dharma_swarm.archive import (
    ArchiveEntry,
    EvolutionArchive,
    FitnessScore,
    normalize_fitness_weights,
)
from dharma_swarm.models import GateDecision, _new_id, _utc_now

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Segment types within a prompt genome
INVARIANT = "invariant"  # MUST NOT be mutated (telos, identity, safety)
MUTABLE = "mutable"      # CAN be evolved (wording, structure, examples)
ADAPTIVE = "adaptive"    # Auto-adjusted by runtime context (variables, state)

# Default fitness weights for prompt evaluation
_PROMPT_FITNESS_WEIGHTS: dict[str, float] = {
    "output_quality": 0.30,        # Did the agent produce good work?
    "depth_preservation": 0.15,    # Did subagents maintain depth?
    "token_efficiency": 0.15,      # Tokens used / semantic content produced
    "telos_alignment": 0.20,       # Did outputs serve the stated purpose?
    "consistency": 0.10,           # Same inputs produce similar quality outputs?
    "safety_compliance": 0.10,     # Did the prompt avoid safety violations?
}

# Evolution hyperparameter defaults
_DEFAULT_POPULATION_SIZE = 12
_DEFAULT_ELITE_COUNT = 2
_DEFAULT_TOURNAMENT_K = 3
_DEFAULT_MUTATION_RATE = 0.15
_DEFAULT_CROSSOVER_RATE = 0.30
_DEFAULT_MAX_GENERATIONS = 50
_DEFAULT_REGRESSION_THRESHOLD = 0.10  # 10% fitness drop triggers rollback
_DEFAULT_PROMOTION_THRESHOLD = 0.05   # 5% fitness improvement to promote
_DEFAULT_SPECIATION_DISTANCE = 0.40   # Genome distance for species boundary
_DEFAULT_DIVERSITY_PRESSURE = 0.20    # Weight of diversity in selection


# ---------------------------------------------------------------------------
# Prompt Genome
# ---------------------------------------------------------------------------


class SegmentType(str, Enum):
    """Classification of a prompt segment's mutability."""

    INVARIANT = "invariant"
    MUTABLE = "mutable"
    ADAPTIVE = "adaptive"


class PromptSegment(BaseModel):
    """A single segment within a prompt genome.

    Each segment has a type controlling whether it can be evolved,
    a role describing its function, and the actual content.

    Attributes:
        id: Unique segment identifier.
        segment_type: Whether this segment is invariant, mutable, or adaptive.
        role: Semantic role (e.g., "system_identity", "task_instruction",
              "few_shot_example", "output_format", "safety_constraint").
        content: The actual prompt text for this segment.
        weight: How much this segment contributes to the overall prompt.
              Higher weight = more selection pressure to optimize it.
        metadata: Optional key-value pairs for tracking provenance.
    """

    id: str = Field(default_factory=_new_id)
    segment_type: SegmentType = SegmentType.MUTABLE
    role: str = ""
    content: str = ""
    weight: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    def content_hash(self) -> str:
        """SHA-256 hash of segment content for change detection."""
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()[:16]


class PromptGenome(BaseModel):
    """Evolvable representation of a complete prompt template.

    A genome is an ordered list of segments, each classified as:
    - INVARIANT: telos alignment, identity assertions, safety constraints.
      These MUST NOT be mutated. They form the dharmic kernel of the prompt.
    - MUTABLE: task instructions, wording, structure, examples, formatting.
      These are the targets of evolutionary optimization.
    - ADAPTIVE: runtime-injected context (variables, state, user input).
      These are not evolved but templated at execution time.

    The genome also carries metadata for lineage tracking: parent IDs,
    generation number, species tag, and fitness history.

    Design decisions:
    - Segments are ordered: position matters for prompt effectiveness.
    - Each segment has a semantic role, enabling role-aware operators.
    - The invariant/mutable split is the computational analog of
      dharma_kernel.py (immutable axioms) vs dharma_corpus.py (evolving claims).
    - Species tags enable speciation: prompts for different task types
      evolve independently, preventing destructive interference.
    """

    id: str = Field(default_factory=_new_id)
    name: str = ""
    version: int = 0
    generation: int = 0
    segments: list[PromptSegment] = Field(default_factory=list)
    parent_ids: list[str] = Field(default_factory=list)
    species: str = "general"
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: _utc_now().isoformat())
    fitness_history: list[float] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def render(self, context: dict[str, str] | None = None) -> str:
        """Render the genome into a concrete prompt string.

        ADAPTIVE segments have their content treated as f-string templates
        with variables from `context`. INVARIANT and MUTABLE segments
        are rendered verbatim.

        Args:
            context: Variable substitutions for ADAPTIVE segments.

        Returns:
            The complete rendered prompt string.
        """
        ctx = context or {}
        parts: list[str] = []
        for seg in self.segments:
            if seg.segment_type == SegmentType.ADAPTIVE and ctx:
                try:
                    rendered = seg.content.format(**ctx)
                except (KeyError, IndexError, ValueError):
                    rendered = seg.content
                parts.append(rendered)
            else:
                parts.append(seg.content)
        return "\n\n".join(parts)

    def mutable_segments(self) -> list[PromptSegment]:
        """Return only the mutable segments (evolution targets)."""
        return [s for s in self.segments if s.segment_type == SegmentType.MUTABLE]

    def invariant_segments(self) -> list[PromptSegment]:
        """Return only the invariant segments (telos/safety kernel)."""
        return [s for s in self.segments if s.segment_type == SegmentType.INVARIANT]

    def adaptive_segments(self) -> list[PromptSegment]:
        """Return only the adaptive segments (runtime context)."""
        return [s for s in self.segments if s.segment_type == SegmentType.ADAPTIVE]

    def genome_hash(self) -> str:
        """Content hash of all mutable segments for deduplication."""
        content = "|".join(s.content for s in self.mutable_segments())
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def token_estimate(self) -> int:
        """Rough token count estimate (4 chars per token heuristic)."""
        total_chars = sum(len(s.content) for s in self.segments)
        return total_chars // 4

    def distance(self, other: PromptGenome) -> float:
        """Normalized edit distance between two genomes.

        Compares mutable segments only. Returns 0.0 for identical genomes,
        1.0 for completely different genomes. Used for speciation.
        """
        self_content = " ".join(s.content for s in self.mutable_segments())
        other_content = " ".join(s.content for s in other.mutable_segments())

        if not self_content and not other_content:
            return 0.0

        # Jaccard distance on word-level tokens
        self_tokens = set(self_content.lower().split())
        other_tokens = set(other_content.lower().split())
        if not self_tokens and not other_tokens:
            return 0.0
        intersection = len(self_tokens & other_tokens)
        union = len(self_tokens | other_tokens)
        return 1.0 - (intersection / union) if union > 0 else 1.0


# ---------------------------------------------------------------------------
# Prompt Fitness
# ---------------------------------------------------------------------------


class PromptFitnessScore(BaseModel):
    """Multi-dimensional fitness score for a prompt variant.

    Dimensions:
    - output_quality: Subjective quality of agent output (0-1).
      Measured by LLM-as-judge or human rating.
    - depth_preservation: Whether subagents maintained reasoning depth (0-1).
      Measured by output length variance, reasoning step count.
    - token_efficiency: Semantic content per token (0-1).
      Higher = more meaning per token spent.
    - telos_alignment: Degree to which outputs served stated purpose (0-1).
      Measured by telos gate pass rate on outputs.
    - consistency: Variance across repeated runs (0-1, higher = more consistent).
      Measured by scoring N independent runs and computing 1 - normalized_variance.
    - safety_compliance: Gate pass rate (0-1).
      Measured by running outputs through TelosGatekeeper.
    """

    output_quality: float = 0.0
    depth_preservation: float = 0.0
    token_efficiency: float = 0.0
    telos_alignment: float = 0.0
    consistency: float = 0.0
    safety_compliance: float = 0.0

    def weighted(self, weights: dict[str, float] | None = None) -> float:
        """Return weighted total fitness."""
        w = weights or _PROMPT_FITNESS_WEIGHTS
        return sum(getattr(self, k, 0.0) * v for k, v in w.items())

    def to_archive_fitness(self) -> FitnessScore:
        """Convert to the standard archive FitnessScore for interop.

        Maps prompt fitness dimensions to the canonical Darwin Engine
        dimensions so prompt evolution entries can coexist in the
        shared EvolutionArchive.
        """
        return FitnessScore(
            correctness=self.output_quality,
            dharmic_alignment=self.telos_alignment,
            elegance=self.depth_preservation,
            efficiency=self.token_efficiency,
            safety=self.safety_compliance,
            performance=self.consistency,
        )


class PromptEvaluation(BaseModel):
    """Complete evaluation record for a prompt variant.

    Tracks the genome, its fitness, the tasks it was evaluated on,
    and any observations from the evaluation process.
    """

    id: str = Field(default_factory=_new_id)
    genome_id: str = ""
    genome_hash: str = ""
    fitness: PromptFitnessScore = Field(default_factory=PromptFitnessScore)
    tasks_evaluated: int = 0
    task_types: list[str] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    gate_results: dict[str, str] = Field(default_factory=dict)
    tokens_used: int = 0
    latency_ms: float = 0.0
    evaluated_at: str = Field(default_factory=lambda: _utc_now().isoformat())


# ---------------------------------------------------------------------------
# Evolution Operators
# ---------------------------------------------------------------------------


class MutationOperator(str, Enum):
    """Types of mutation that can be applied to prompt segments."""

    REPHRASE = "rephrase"          # Reword without changing meaning
    RESTRUCTURE = "restructure"    # Change section ordering or hierarchy
    COMPRESS = "compress"          # Reduce token count preserving meaning
    EXPAND = "expand"              # Add detail or examples
    EXEMPLIFY = "exemplify"        # Add/modify few-shot examples
    TONE_SHIFT = "tone_shift"      # Adjust formality, directness, etc.
    CONSTRAIN = "constrain"        # Add output constraints or guardrails
    ABSTRACT = "abstract"          # Generalize specific instructions


class CrossoverMethod(str, Enum):
    """Methods for combining two parent genomes."""

    SEGMENT_SWAP = "segment_swap"      # Swap matching-role segments
    BLEND = "blend"                    # Merge content from both parents
    TOURNAMENT_SEGMENT = "tournament"  # For each segment, pick the parent's
                                       # version with higher fitness


@dataclass
class MutationRecord:
    """Record of a single mutation applied to a genome."""

    operator: MutationOperator
    segment_id: str
    segment_role: str
    original_content: str
    mutated_content: str
    mutation_prompt: str = ""
    timestamp: str = field(default_factory=lambda: _utc_now().isoformat())


@dataclass
class CrossoverRecord:
    """Record of a crossover operation between two parent genomes."""

    method: CrossoverMethod
    parent_a_id: str
    parent_b_id: str
    child_id: str
    segments_from_a: list[str] = field(default_factory=list)
    segments_from_b: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: _utc_now().isoformat())


class PromptEvolver:
    """Applies evolutionary operators to prompt genomes.

    Mutation strategies (grounded in literature):

    1. REPHRASE (DSPy-inspired): Use an LLM to rephrase instructions
       while preserving semantic intent. The meta-prompt asks: "Rephrase
       this instruction to be clearer and more effective."

    2. RESTRUCTURE (EvoPrompt-inspired): Permute section ordering,
       change hierarchy, promote subsections. Position effects are real
       in prompts (primacy/recency bias).

    3. COMPRESS (Token optimization): Use an LLM to produce a shorter
       version preserving all essential information. Critical for cost.

    4. EXPAND (Few-shot augmentation): Add examples, elaboration, or
       edge case handling. DSPy's bootstrapped demonstrations approach.

    5. EXEMPLIFY (DSPy's core innovation): Generate, select, and order
       few-shot examples based on which examples produce the best
       downstream performance.

    6. TONE_SHIFT: Adjust the prompt's register -- more direct, more
       formal, more conversational. Measurable impact on output quality.

    7. CONSTRAIN (Constitutional AI-inspired): Add output format
       constraints, guardrails, or self-correction instructions.

    8. ABSTRACT (OPRO-inspired): Generalize task-specific instructions
       into reusable patterns. Enables transfer across task types.

    Crossover strategies:

    1. SEGMENT_SWAP: For segments with matching roles, swap the content
       from two high-fitness parents. Exploits modular prompt structure.

    2. BLEND: Use an LLM to merge the best elements of two segments
       into a single unified version. OPRO's "combine" operation.

    3. TOURNAMENT_SEGMENT: For each segment position, select the version
       from whichever parent had higher fitness on tasks that exercise
       that segment's function.

    Args:
        mutation_rate: Probability of mutating each mutable segment.
        crossover_rate: Probability of applying crossover vs. mutation.
        mutation_fn: Optional async function that takes (content, operator, role)
            and returns mutated content. If None, mutations are applied
            using simple heuristic transforms (no LLM call).
    """

    def __init__(
        self,
        mutation_rate: float = _DEFAULT_MUTATION_RATE,
        crossover_rate: float = _DEFAULT_CROSSOVER_RATE,
        mutation_fn: Callable[..., Any] | None = None,
    ) -> None:
        self.mutation_rate = max(0.01, min(1.0, mutation_rate))
        self.crossover_rate = max(0.0, min(1.0, crossover_rate))
        self._mutation_fn = mutation_fn
        self._mutation_log: list[MutationRecord] = []
        self._crossover_log: list[CrossoverRecord] = []

    def mutate(
        self,
        genome: PromptGenome,
        *,
        operator: MutationOperator | None = None,
        target_segment_id: str | None = None,
    ) -> PromptGenome:
        """Apply mutation to a genome, returning a new child genome.

        Only MUTABLE segments are candidates for mutation. Each mutable
        segment is mutated with probability `self.mutation_rate` unless
        `target_segment_id` is specified (which forces mutation of that
        specific segment).

        The invariant segments are deep-copied unchanged. This is the
        computational samvara: the dharmic kernel passes through untouched.

        Args:
            genome: Parent genome to mutate.
            operator: Specific mutation operator to apply. If None, one
                is chosen randomly weighted by segment role.
            target_segment_id: If set, only this segment is mutated.

        Returns:
            A new PromptGenome with mutations applied.
        """
        child = genome.model_copy(deep=True)
        child.id = _new_id()
        child.version = genome.version + 1
        child.generation = genome.generation + 1
        child.parent_ids = [genome.id]
        child.created_at = _utc_now().isoformat()

        for segment in child.segments:
            if segment.segment_type != SegmentType.MUTABLE:
                continue

            if target_segment_id and segment.id != target_segment_id:
                continue

            if not target_segment_id and random.random() > self.mutation_rate:
                continue

            original = segment.content
            if operator is None:
                preferred_operator = self._select_operator(segment.role)
                mutated, applied_operator = self._apply_mutation_with_fallback(
                    segment.content,
                    segment.role,
                    preferred_operator=preferred_operator,
                )
            else:
                mutated = self._apply_mutation(segment.content, operator, segment.role)
                applied_operator = operator if mutated != original else None

            if applied_operator is not None:
                self._mutation_log.append(MutationRecord(
                    operator=applied_operator,
                    segment_id=segment.id,
                    segment_role=segment.role,
                    original_content=original,
                    mutated_content=mutated,
                ))
                segment.content = mutated
                segment.metadata["last_mutation"] = applied_operator.value
                segment.metadata["mutation_generation"] = child.generation

        return child

    def crossover(
        self,
        parent_a: PromptGenome,
        parent_b: PromptGenome,
        *,
        method: CrossoverMethod = CrossoverMethod.SEGMENT_SWAP,
    ) -> PromptGenome:
        """Combine two parent genomes into a child genome.

        Only MUTABLE segments participate in crossover. INVARIANT segments
        are copied from parent_a (the fitter parent by convention).

        Args:
            parent_a: First parent (convention: higher fitness).
            parent_b: Second parent.
            method: Crossover method to apply.

        Returns:
            A new child PromptGenome.
        """
        child = parent_a.model_copy(deep=True)
        child.id = _new_id()
        child.version = max(parent_a.version, parent_b.version) + 1
        child.generation = max(parent_a.generation, parent_b.generation) + 1
        child.parent_ids = [parent_a.id, parent_b.id]
        child.created_at = _utc_now().isoformat()

        segments_from_a: list[str] = []
        segments_from_b: list[str] = []

        if method == CrossoverMethod.SEGMENT_SWAP:
            # Build role-indexed lookup for parent_b's mutable segments
            b_by_role: dict[str, PromptSegment] = {
                s.role: s for s in parent_b.mutable_segments()
            }
            for segment in child.segments:
                if segment.segment_type != SegmentType.MUTABLE:
                    segments_from_a.append(segment.id)
                    continue
                b_segment = b_by_role.get(segment.role)
                if b_segment and random.random() < 0.5:
                    segment.content = b_segment.content
                    segment.metadata["crossover_source"] = parent_b.id
                    segments_from_b.append(segment.id)
                else:
                    segments_from_a.append(segment.id)

        elif method == CrossoverMethod.BLEND:
            b_by_role = {
                s.role: s for s in parent_b.mutable_segments()
            }
            for segment in child.segments:
                if segment.segment_type != SegmentType.MUTABLE:
                    segments_from_a.append(segment.id)
                    continue
                b_segment = b_by_role.get(segment.role)
                if b_segment and random.random() < 0.5:
                    # Simple blend: interleave sentences
                    a_sentences = _split_sentences(segment.content)
                    b_sentences = _split_sentences(b_segment.content)
                    blended = _interleave(a_sentences, b_sentences)
                    segment.content = " ".join(blended)
                    segments_from_b.append(segment.id)
                else:
                    segments_from_a.append(segment.id)

        elif method == CrossoverMethod.TOURNAMENT_SEGMENT:
            # Use fitness history to decide: pick from the parent with
            # higher recent fitness
            a_recent = mean(parent_a.fitness_history[-3:]) if parent_a.fitness_history else 0.5
            b_recent = mean(parent_b.fitness_history[-3:]) if parent_b.fitness_history else 0.5
            prefer_b = b_recent > a_recent

            b_by_role = {
                s.role: s for s in parent_b.mutable_segments()
            }
            for segment in child.segments:
                if segment.segment_type != SegmentType.MUTABLE:
                    segments_from_a.append(segment.id)
                    continue
                b_segment = b_by_role.get(segment.role)
                if b_segment and prefer_b:
                    segment.content = b_segment.content
                    segments_from_b.append(segment.id)
                else:
                    segments_from_a.append(segment.id)

        self._crossover_log.append(CrossoverRecord(
            method=method,
            parent_a_id=parent_a.id,
            parent_b_id=parent_b.id,
            child_id=child.id,
            segments_from_a=segments_from_a,
            segments_from_b=segments_from_b,
        ))

        return child

    def _role_operator_weights(self, role: str) -> list[tuple[MutationOperator, float]]:
        """Return role-specific mutation weights."""
        role_weights: dict[str, list[tuple[MutationOperator, float]]] = {
            "task_instruction": [
                (MutationOperator.REPHRASE, 0.35),
                (MutationOperator.COMPRESS, 0.25),
                (MutationOperator.CONSTRAIN, 0.20),
                (MutationOperator.RESTRUCTURE, 0.10),
                (MutationOperator.TONE_SHIFT, 0.10),
            ],
            "few_shot_example": [
                (MutationOperator.EXEMPLIFY, 0.40),
                (MutationOperator.EXPAND, 0.25),
                (MutationOperator.REPHRASE, 0.20),
                (MutationOperator.COMPRESS, 0.15),
            ],
            "output_format": [
                (MutationOperator.RESTRUCTURE, 0.35),
                (MutationOperator.CONSTRAIN, 0.30),
                (MutationOperator.COMPRESS, 0.20),
                (MutationOperator.REPHRASE, 0.15),
            ],
            "context": [
                (MutationOperator.COMPRESS, 0.40),
                (MutationOperator.ABSTRACT, 0.30),
                (MutationOperator.REPHRASE, 0.20),
                (MutationOperator.RESTRUCTURE, 0.10),
            ],
        }
        return role_weights.get(role, [])

    def _select_operator(self, role: str) -> MutationOperator:
        """Select a mutation operator weighted by segment role.

        Different roles benefit from different mutation types:
        - "task_instruction" -> REPHRASE, COMPRESS, CONSTRAIN
        - "few_shot_example" -> EXEMPLIFY, EXPAND
        - "output_format" -> RESTRUCTURE, CONSTRAIN
        - "context" -> COMPRESS, ABSTRACT
        - default -> uniform random
        """
        weights = self._role_operator_weights(role)
        if weights:
            operators, probs = zip(*weights)
            return random.choices(list(operators), weights=list(probs), k=1)[0]

        # Default: uniform over all operators
        return random.choice(list(MutationOperator))

    def _apply_mutation_with_fallback(
        self,
        content: str,
        role: str,
        *,
        preferred_operator: MutationOperator,
    ) -> tuple[str, MutationOperator | None]:
        """Try role-appropriate operators until one produces a real change."""
        seen: set[MutationOperator] = set()
        candidates: list[MutationOperator] = []

        def add_candidate(op: MutationOperator) -> None:
            if op in seen:
                return
            seen.add(op)
            candidates.append(op)

        add_candidate(preferred_operator)
        for op, _weight in sorted(
            self._role_operator_weights(role),
            key=lambda item: item[1],
            reverse=True,
        ):
            add_candidate(op)
        for op in MutationOperator:
            add_candidate(op)

        for candidate in candidates:
            mutated = self._apply_mutation(content, candidate, role)
            if mutated != content:
                return mutated, candidate

        return content, None

    def _apply_mutation(
        self,
        content: str,
        operator: MutationOperator,
        role: str,
    ) -> str:
        """Apply a mutation operator to content.

        If self._mutation_fn is set (LLM-backed), it is called.
        Otherwise, heuristic transforms are applied.

        These heuristic transforms are intentionally simple. The real
        power comes from LLM-backed mutation where the meta-prompt
        instructs the LLM to optimize the segment.
        """
        if self._mutation_fn is not None:
            try:
                # Mutation function should be sync or we handle async elsewhere
                result = self._mutation_fn(content, operator.value, role)
                if isinstance(result, str) and result.strip():
                    return result
            except Exception as e:
                logger.warning("LLM mutation failed, falling back to heuristic: %s", e)

        # Heuristic fallbacks (no LLM required)
        if operator == MutationOperator.COMPRESS:
            return _heuristic_compress(content)
        elif operator == MutationOperator.RESTRUCTURE:
            return _heuristic_restructure(content)
        elif operator == MutationOperator.REPHRASE:
            return _heuristic_rephrase(content)
        elif operator == MutationOperator.CONSTRAIN:
            return _heuristic_constrain(content)
        elif operator == MutationOperator.EXPAND:
            return _heuristic_expand(content)
        else:
            # For operators that strongly benefit from LLM (EXEMPLIFY,
            # TONE_SHIFT, ABSTRACT), return unchanged if no LLM available
            return content

    def get_mutation_log(self) -> list[MutationRecord]:
        """Return the mutation log for this evolver instance."""
        return list(self._mutation_log)

    def get_crossover_log(self) -> list[CrossoverRecord]:
        """Return the crossover log for this evolver instance."""
        return list(self._crossover_log)


# ---------------------------------------------------------------------------
# Prompt Population & Species
# ---------------------------------------------------------------------------


class PromptSpecies(BaseModel):
    """A species of prompts adapted to a specific task type.

    Speciation prevents destructive interference: a prompt optimized
    for code review should not compete directly with one optimized
    for creative writing. They evolve in parallel, sharing innovations
    through occasional inter-species crossover.

    Species boundaries are determined by genome distance (Jaccard on
    word tokens of mutable segments). If two genomes differ by more
    than `speciation_distance`, they belong to different species.

    This mirrors biological speciation and MAP-Elites' behavioral
    diversity maintenance.
    """

    id: str = Field(default_factory=_new_id)
    name: str = ""
    task_type: str = ""
    representative_genome_id: str = ""
    member_count: int = 0
    mean_fitness: float = 0.0
    best_fitness: float = 0.0
    generations_since_improvement: int = 0
    created_at: str = Field(default_factory=lambda: _utc_now().isoformat())


class PromptPopulation:
    """Manages a population of prompt genomes with species tracking.

    The population maintains:
    - A set of genomes (the current generation)
    - Species assignments based on genome distance
    - Fitness evaluations for each genome
    - An elite set that survives unchanged between generations

    Selection pressure is applied within species, not globally.
    This prevents a single dominant species from eliminating
    diverse but potentially valuable prompt strategies.

    Args:
        max_size: Maximum population size.
        elite_count: Number of top genomes preserved unchanged.
        speciation_distance: Genome distance threshold for species.
        diversity_pressure: Weight of diversity bonus in selection.
    """

    def __init__(
        self,
        max_size: int = _DEFAULT_POPULATION_SIZE,
        elite_count: int = _DEFAULT_ELITE_COUNT,
        speciation_distance: float = _DEFAULT_SPECIATION_DISTANCE,
        diversity_pressure: float = _DEFAULT_DIVERSITY_PRESSURE,
    ) -> None:
        self.max_size = max(4, max_size)
        self.elite_count = min(elite_count, max_size // 2)
        self.speciation_distance = speciation_distance
        self.diversity_pressure = diversity_pressure

        self._genomes: dict[str, PromptGenome] = {}
        self._fitness: dict[str, PromptFitnessScore] = {}
        self._evaluations: dict[str, list[PromptEvaluation]] = defaultdict(list)
        self._species: dict[str, PromptSpecies] = {}
        self._genome_species: dict[str, str] = {}  # genome_id -> species_id
        self._generation: int = 0

    @property
    def size(self) -> int:
        return len(self._genomes)

    @property
    def generation(self) -> int:
        return self._generation

    def add_genome(self, genome: PromptGenome) -> str:
        """Add a genome to the population, assigning it to a species.

        Returns the species ID it was assigned to.
        """
        self._genomes[genome.id] = genome
        species_id = self._assign_species(genome)
        return species_id

    def record_evaluation(
        self,
        genome_id: str,
        evaluation: PromptEvaluation,
    ) -> None:
        """Record a fitness evaluation for a genome."""
        if genome_id not in self._genomes:
            logger.warning("Genome %s not in population, skipping evaluation", genome_id)
            return

        self._evaluations[genome_id].append(evaluation)
        self._fitness[genome_id] = evaluation.fitness
        self._genomes[genome_id].fitness_history.append(
            evaluation.fitness.weighted()
        )

        # Update species statistics
        species_id = self._genome_species.get(genome_id)
        if species_id and species_id in self._species:
            self._update_species_stats(species_id)

    def get_genome(self, genome_id: str) -> PromptGenome | None:
        """Retrieve a genome by ID."""
        return self._genomes.get(genome_id)

    def get_fitness(self, genome_id: str) -> float:
        """Return the weighted fitness of a genome. 0.0 if not evaluated."""
        score = self._fitness.get(genome_id)
        return score.weighted() if score else 0.0

    def get_elites(self) -> list[PromptGenome]:
        """Return the top-N genomes by fitness (elite set)."""
        evaluated = [
            (gid, self.get_fitness(gid))
            for gid in self._genomes
            if gid in self._fitness
        ]
        evaluated.sort(key=lambda x: x[1], reverse=True)
        return [
            self._genomes[gid]
            for gid, _ in evaluated[:self.elite_count]
        ]

    def select_parent(
        self,
        *,
        tournament_k: int = _DEFAULT_TOURNAMENT_K,
        species_id: str | None = None,
    ) -> PromptGenome | None:
        """Tournament selection within a species (or globally if no species).

        Selection is fitness-proportional with a diversity bonus:
        genomes that are more distant from the current best get a
        small fitness boost, preventing premature convergence.

        Args:
            tournament_k: Number of candidates per tournament.
            species_id: If set, only select from this species.

        Returns:
            The winning genome, or None if population is empty.
        """
        candidates = list(self._genomes.values())
        if species_id:
            candidates = [
                g for g in candidates
                if self._genome_species.get(g.id) == species_id
            ]

        if not candidates:
            return None

        pool_size = min(tournament_k, len(candidates))
        pool = random.sample(candidates, pool_size)

        # Score with diversity bonus
        best_genome = max(
            pool,
            key=lambda g: self._selection_score(g),
        )
        return best_genome

    def advance_generation(
        self,
        new_genomes: list[PromptGenome],
    ) -> dict[str, Any]:
        """Replace the population with a new generation.

        Elites from the current generation are preserved. New genomes
        fill the remaining slots. Excess genomes beyond max_size are
        dropped (lowest fitness first).

        Args:
            new_genomes: The offspring to add.

        Returns:
            Generation summary statistics.
        """
        self._generation += 1

        # Preserve elites
        elites = self.get_elites()
        elite_ids = {e.id for e in elites}

        # Clear non-elite genomes
        pruned_ids = [
            gid for gid in list(self._genomes)
            if gid not in elite_ids
        ]
        for gid in pruned_ids:
            del self._genomes[gid]
            self._fitness.pop(gid, None)
            self._genome_species.pop(gid, None)

        # Add new genomes
        for genome in new_genomes:
            genome.generation = self._generation
            self.add_genome(genome)

        # Enforce max size
        while len(self._genomes) > self.max_size:
            worst_id = min(
                self._genomes,
                key=lambda gid: self.get_fitness(gid),
            )
            if worst_id not in elite_ids:
                del self._genomes[worst_id]
                self._fitness.pop(worst_id, None)
                self._genome_species.pop(worst_id, None)
            else:
                break

        # Refresh species
        self._refresh_species()

        return {
            "generation": self._generation,
            "population_size": len(self._genomes),
            "elites_preserved": len(elites),
            "new_added": len(new_genomes),
            "species_count": len(self._species),
            "mean_fitness": self._population_mean_fitness(),
            "best_fitness": self._population_best_fitness(),
        }

    def get_species_summary(self) -> list[dict[str, Any]]:
        """Return summary statistics for each species."""
        return [
            {
                "id": sp.id,
                "name": sp.name,
                "task_type": sp.task_type,
                "member_count": sp.member_count,
                "mean_fitness": sp.mean_fitness,
                "best_fitness": sp.best_fitness,
                "stagnant_generations": sp.generations_since_improvement,
            }
            for sp in self._species.values()
        ]

    def _assign_species(self, genome: PromptGenome) -> str:
        """Assign a genome to the nearest species or create a new one."""
        best_species_id: str | None = None
        best_distance = float("inf")

        for sp_id, sp in self._species.items():
            rep = self._genomes.get(sp.representative_genome_id)
            if rep is None:
                continue
            dist = genome.distance(rep)
            if dist < best_distance:
                best_distance = dist
                best_species_id = sp_id

        if best_species_id and best_distance < self.speciation_distance:
            self._genome_species[genome.id] = best_species_id
            self._update_species_stats(best_species_id)
            return best_species_id

        # Create new species
        new_species = PromptSpecies(
            name=genome.species or f"species_{len(self._species)}",
            task_type=genome.species,
            representative_genome_id=genome.id,
            member_count=1,
        )
        self._species[new_species.id] = new_species
        self._genome_species[genome.id] = new_species.id
        return new_species.id

    def _update_species_stats(self, species_id: str) -> None:
        """Recompute species statistics from member genomes."""
        sp = self._species.get(species_id)
        if sp is None:
            return

        members = [
            gid for gid, sid in self._genome_species.items()
            if sid == species_id
        ]
        sp.member_count = len(members)

        fitnesses = [self.get_fitness(gid) for gid in members]
        sp.mean_fitness = mean(fitnesses) if fitnesses else 0.0
        sp.best_fitness = max(fitnesses) if fitnesses else 0.0

    def _refresh_species(self) -> None:
        """Remove empty species and update all statistics."""
        empty = [
            sp_id for sp_id, sp in self._species.items()
            if sp.member_count == 0
            or sp.representative_genome_id not in self._genomes
        ]
        for sp_id in empty:
            del self._species[sp_id]

        for sp_id in self._species:
            self._update_species_stats(sp_id)

    def _selection_score(self, genome: PromptGenome) -> float:
        """Fitness with diversity bonus for selection."""
        base = self.get_fitness(genome.id)

        # Diversity bonus: distance from best genome
        best_genomes = self.get_elites()
        if best_genomes:
            min_dist = min(
                genome.distance(bg) for bg in best_genomes
                if bg.id != genome.id
            ) if len(best_genomes) > 1 or (best_genomes and best_genomes[0].id != genome.id) else 0.5
        else:
            min_dist = 0.5

        return base + (self.diversity_pressure * min_dist)

    def _population_mean_fitness(self) -> float:
        fitnesses = [self.get_fitness(gid) for gid in self._genomes]
        return mean(fitnesses) if fitnesses else 0.0

    def _population_best_fitness(self) -> float:
        fitnesses = [self.get_fitness(gid) for gid in self._genomes]
        return max(fitnesses) if fitnesses else 0.0


# ---------------------------------------------------------------------------
# Prompt Evolution Engine
# ---------------------------------------------------------------------------


class PromptCanaryResult(BaseModel):
    """Result of canary testing a prompt variant."""

    genome_id: str = ""
    canary_fitness: float = 0.0
    baseline_fitness: float = 0.0
    delta: float = 0.0
    decision: str = "defer"  # promote, rollback, defer
    tasks_evaluated: int = 0
    reason: str = ""


class PromptEvolutionConfig(BaseModel):
    """Configuration for the prompt evolution engine."""

    population_size: int = _DEFAULT_POPULATION_SIZE
    elite_count: int = _DEFAULT_ELITE_COUNT
    tournament_k: int = _DEFAULT_TOURNAMENT_K
    mutation_rate: float = _DEFAULT_MUTATION_RATE
    crossover_rate: float = _DEFAULT_CROSSOVER_RATE
    max_generations: int = _DEFAULT_MAX_GENERATIONS
    regression_threshold: float = _DEFAULT_REGRESSION_THRESHOLD
    promotion_threshold: float = _DEFAULT_PROMOTION_THRESHOLD
    speciation_distance: float = _DEFAULT_SPECIATION_DISTANCE
    diversity_pressure: float = _DEFAULT_DIVERSITY_PRESSURE
    canary_traffic_fraction: float = 0.10  # 10% traffic to canary
    min_evaluations_for_promotion: int = 5
    human_review_distance_threshold: float = 0.60
    archive_all_variants: bool = True


class PromptEvolutionEngine:
    """Orchestrates the full prompt evolution loop.

    This is the prompt-domain analog of DarwinEngine. It manages a
    population of prompt genomes, applies evolutionary operators,
    gates evolved prompts through telos checks, evaluates fitness
    through actual agent runs, and promotes/rolls back via canary
    deployment.

    The engine integrates with the existing dharma_swarm infrastructure:

    1. Telos Gates: Every evolved prompt passes through all 11 dharmic
       gates before it can be deployed. Invariant segments are verified
       unchanged. Mutable segments are checked for safety violations.

    2. Canary Deployment: New prompt variants are deployed to a fraction
       of traffic. If fitness improves above threshold -> promote. If
       fitness regresses below threshold -> automatic rollback.

    3. Archive: All prompt variants and their fitness histories are
       archived in a PromptEvolutionArchive (JSONL) for lineage tracking.

    4. Speciation: Prompts for different task types evolve independently.
       This prevents a code-review prompt from being optimized into
       something that is only good at creative writing.

    5. Meta-Evolution: The evolution hyperparameters themselves (mutation
       rate, crossover rate, selection pressure) can be evolved by the
       MetaEvolutionEngine, creating a recursive optimization loop.

    Safety Rails:
    - Telos gate: evolved prompts must pass all 11 gates.
    - Invariant verification: SHA-256 hash of invariant segments is
      checked before and after evolution. Any change = immediate reject.
    - Regression detection: automatic rollback if fitness drops >10%.
    - Diversity maintenance: speciation + diversity pressure prevent
      convergence to local optima.
    - Human review: prompts that mutated beyond recognition (distance
      > 0.60 from parent) are flagged for human review.
    - Lineage tracking: full parent->child tree with fitness at each node.

    Args:
        config: Evolution configuration.
        archive_path: Path for the prompt evolution archive.
        evolver: Optional pre-configured PromptEvolver instance.
    """

    def __init__(
        self,
        config: PromptEvolutionConfig | None = None,
        archive_path: Path | None = None,
        evolver: PromptEvolver | None = None,
    ) -> None:
        self.config = config or PromptEvolutionConfig()
        self.population = PromptPopulation(
            max_size=self.config.population_size,
            elite_count=self.config.elite_count,
            speciation_distance=self.config.speciation_distance,
            diversity_pressure=self.config.diversity_pressure,
        )
        self.evolver = evolver or PromptEvolver(
            mutation_rate=self.config.mutation_rate,
            crossover_rate=self.config.crossover_rate,
        )
        self._archive_path = archive_path or (
            Path.home() / ".dharma" / "evolution" / "prompt_archive.jsonl"
        )
        self._archive_path.parent.mkdir(parents=True, exist_ok=True)

        # Tracking
        self._generation_results: list[dict[str, Any]] = []
        self._canary_results: list[PromptCanaryResult] = []
        self._invariant_hashes: dict[str, list[str]] = {}  # genome_id -> [seg_hashes]
        self._flagged_for_review: list[str] = []  # genome IDs

    def seed_population(
        self,
        seed_genomes: list[PromptGenome],
    ) -> dict[str, Any]:
        """Initialize the population with seed genomes.

        Seed genomes are typically hand-crafted prompts that serve as
        the starting point for evolution. Their invariant segments
        define the immutable telos kernel.

        Args:
            seed_genomes: Initial prompt genomes.

        Returns:
            Seeding summary.
        """
        for genome in seed_genomes:
            self.population.add_genome(genome)
            self._record_invariant_hashes(genome)

        return {
            "seeded": len(seed_genomes),
            "population_size": self.population.size,
            "species_count": len(self.population._species),
        }

    def evolve_generation(self) -> list[PromptGenome]:
        """Produce the next generation of prompt variants.

        Pipeline:
        1. Select parents via tournament selection within species.
        2. Apply crossover with probability `crossover_rate`.
        3. Apply mutation to offspring.
        4. Verify invariant segments unchanged.
        5. Check genome distance for human review flagging.
        6. Return offspring for fitness evaluation.

        Returns:
            List of new child genomes ready for evaluation.
        """
        offspring: list[PromptGenome] = []
        elites = self.population.get_elites()
        target_count = self.config.population_size - len(elites)

        for _ in range(target_count):
            child = self._produce_offspring()
            if child is None:
                continue

            # Safety: verify invariant segments
            if not self._verify_invariants(child):
                logger.warning(
                    "Genome %s failed invariant check, discarding", child.id
                )
                continue

            # Check if mutation was too extreme -> flag for human review
            for parent_id in child.parent_ids:
                parent = self.population.get_genome(parent_id)
                if parent and child.distance(parent) > self.config.human_review_distance_threshold:
                    self._flagged_for_review.append(child.id)
                    child.metadata["flagged_for_review"] = True
                    child.metadata["review_reason"] = (
                        f"Mutation distance {child.distance(parent):.3f} exceeds "
                        f"threshold {self.config.human_review_distance_threshold}"
                    )
                    logger.info(
                        "Genome %s flagged for human review (distance=%.3f)",
                        child.id, child.distance(parent),
                    )
                    break

            offspring.append(child)

        return offspring

    def evaluate_canary(
        self,
        genome_id: str,
        canary_fitness: float,
        tasks_evaluated: int = 0,
    ) -> PromptCanaryResult:
        """Evaluate a canary deployment against the current best.

        Args:
            genome_id: The genome being canary-tested.
            canary_fitness: Observed fitness on canary traffic.
            tasks_evaluated: Number of tasks evaluated.

        Returns:
            PromptCanaryResult with promote/rollback/defer decision.
        """
        best_fitness = self.population._population_best_fitness()

        delta = canary_fitness - best_fitness
        min_evals = self.config.min_evaluations_for_promotion

        if tasks_evaluated < min_evals:
            decision = "defer"
            reason = (
                f"Insufficient evaluations ({tasks_evaluated}/{min_evals})"
            )
        elif delta > self.config.promotion_threshold:
            decision = "promote"
            reason = (
                f"Fitness delta +{delta:.4f} exceeds promotion "
                f"threshold {self.config.promotion_threshold}"
            )
        elif delta < -self.config.regression_threshold:
            decision = "rollback"
            reason = (
                f"Fitness delta {delta:.4f} below regression "
                f"threshold -{self.config.regression_threshold}"
            )
        else:
            decision = "defer"
            reason = (
                f"Fitness delta {delta:+.4f} within neutral zone "
                f"[{-self.config.regression_threshold}, "
                f"{self.config.promotion_threshold}]"
            )

        result = PromptCanaryResult(
            genome_id=genome_id,
            canary_fitness=canary_fitness,
            baseline_fitness=best_fitness,
            delta=delta,
            decision=decision,
            tasks_evaluated=tasks_evaluated,
            reason=reason,
        )
        self._canary_results.append(result)
        return result

    def run_generation(
        self,
        evaluate_fn: Callable[[PromptGenome], PromptEvaluation],
    ) -> dict[str, Any]:
        """Run a complete generation: evolve, evaluate, select.

        This is the main loop entry point. It:
        1. Produces offspring via evolutionary operators.
        2. Evaluates each offspring using the provided function.
        3. Advances the population to the next generation.
        4. Archives all variants.

        Args:
            evaluate_fn: Synchronous function that takes a PromptGenome
                and returns a PromptEvaluation. This is where the actual
                agent runs happen.

        Returns:
            Generation summary statistics.
        """
        # 1. Evolve
        offspring = self.evolve_generation()

        # 2. Evaluate
        for child in offspring:
            evaluation = evaluate_fn(child)
            self.population.record_evaluation(child.id, evaluation)

        # 3. Advance generation
        gen_summary = self.population.advance_generation(offspring)

        # 4. Archive
        if self.config.archive_all_variants:
            self._archive_generation(offspring)

        self._generation_results.append(gen_summary)
        return gen_summary

    def gate_check_genome(self, genome: PromptGenome) -> tuple[bool, str]:
        """Run telos gates on a rendered prompt genome.

        Uses the TelosGatekeeper to check the rendered prompt for
        safety violations. This is the dharmic filter that prevents
        evolved prompts from drifting into harmful territory.

        Args:
            genome: The genome to gate-check.

        Returns:
            (passed, reason) tuple.
        """
        from dharma_swarm.telos_gates import TelosGatekeeper

        gatekeeper = TelosGatekeeper()
        rendered = genome.render()

        result = gatekeeper.check(
            action=f"deploy_prompt:{genome.name}:{genome.id[:8]}",
            content=rendered,
        )

        passed = result.decision != GateDecision.BLOCK
        return passed, result.reason

    def get_best_genome(self) -> PromptGenome | None:
        """Return the highest-fitness genome in the population."""
        elites = self.population.get_elites()
        return elites[0] if elites else None

    def get_flagged_for_review(self) -> list[PromptGenome]:
        """Return genomes flagged for human review."""
        return [
            self.population.get_genome(gid)
            for gid in self._flagged_for_review
            if self.population.get_genome(gid) is not None
        ]

    def get_evolution_summary(self) -> dict[str, Any]:
        """Return a comprehensive summary of the evolution state."""
        return {
            "generation": self.population.generation,
            "population_size": self.population.size,
            "species": self.population.get_species_summary(),
            "mean_fitness": self.population._population_mean_fitness(),
            "best_fitness": self.population._population_best_fitness(),
            "best_genome_id": (
                self.get_best_genome().id if self.get_best_genome() else None
            ),
            "generations_run": len(self._generation_results),
            "canary_results": len(self._canary_results),
            "flagged_for_review": len(self._flagged_for_review),
            "total_archived": self._count_archived(),
        }

    # -- Internal methods ---------------------------------------------------

    def _produce_offspring(self) -> PromptGenome | None:
        """Produce a single offspring via selection + operators."""
        if random.random() < self.evolver.crossover_rate:
            # Crossover
            parent_a = self.population.select_parent(
                tournament_k=self.config.tournament_k,
            )
            parent_b = self.population.select_parent(
                tournament_k=self.config.tournament_k,
            )
            if parent_a is None or parent_b is None:
                return None
            if parent_a.id == parent_b.id:
                # Same parent selected twice -> just mutate
                return self.evolver.mutate(parent_a)

            # Ensure parent_a is the fitter one (convention)
            if self.population.get_fitness(parent_b.id) > self.population.get_fitness(parent_a.id):
                parent_a, parent_b = parent_b, parent_a

            child = self.evolver.crossover(parent_a, parent_b)
            # Often apply mutation after crossover
            if random.random() < self.evolver.mutation_rate:
                child = self.evolver.mutate(child)
            return child
        else:
            # Pure mutation
            parent = self.population.select_parent(
                tournament_k=self.config.tournament_k,
            )
            if parent is None:
                return None
            return self.evolver.mutate(parent)

    def _record_invariant_hashes(self, genome: PromptGenome) -> None:
        """Record SHA-256 hashes of invariant segments for verification."""
        hashes = [seg.content_hash() for seg in genome.invariant_segments()]
        self._invariant_hashes[genome.id] = hashes

    def _verify_invariants(self, genome: PromptGenome) -> bool:
        """Verify that invariant segments have not been modified.

        Checks against the hashes of the parent genome's invariant
        segments. Any change to an invariant segment is a hard reject.

        This is the prompt-domain equivalent of dharma_kernel.py's
        SHA-256 signed axioms: the telos kernel is immutable.
        """
        for parent_id in genome.parent_ids:
            parent_hashes = self._invariant_hashes.get(parent_id)
            if parent_hashes is None:
                continue

            current_hashes = [
                seg.content_hash() for seg in genome.invariant_segments()
            ]

            if len(current_hashes) != len(parent_hashes):
                logger.error(
                    "Invariant segment count changed: %d -> %d",
                    len(parent_hashes), len(current_hashes),
                )
                return False

            for i, (parent_h, current_h) in enumerate(
                zip(parent_hashes, current_hashes)
            ):
                if parent_h != current_h:
                    logger.error(
                        "Invariant segment %d mutated: %s -> %s",
                        i, parent_h, current_h,
                    )
                    return False

        # Record hashes for this genome's children
        self._record_invariant_hashes(genome)
        return True

    def _archive_generation(self, genomes: list[PromptGenome]) -> None:
        """Append generation genomes to the JSONL archive."""
        try:
            with open(self._archive_path, "a") as f:
                for genome in genomes:
                    entry = {
                        "genome_id": genome.id,
                        "name": genome.name,
                        "version": genome.version,
                        "generation": genome.generation,
                        "species": genome.species,
                        "parent_ids": genome.parent_ids,
                        "genome_hash": genome.genome_hash(),
                        "token_estimate": genome.token_estimate(),
                        "fitness": self.population.get_fitness(genome.id),
                        "fitness_history": genome.fitness_history,
                        "mutable_segment_count": len(genome.mutable_segments()),
                        "invariant_segment_count": len(genome.invariant_segments()),
                        "tags": genome.tags,
                        "archived_at": _utc_now().isoformat(),
                        "population_generation": self.population.generation,
                    }
                    f.write(json.dumps(entry, default=str) + "\n")
        except OSError as e:
            logger.error("Failed to archive prompt generation: %s", e)

    def _count_archived(self) -> int:
        """Count entries in the archive file."""
        if not self._archive_path.exists():
            return 0
        try:
            return sum(1 for line in self._archive_path.read_text().splitlines() if line.strip())
        except OSError:
            return 0


# ---------------------------------------------------------------------------
# Heuristic mutation helpers (no LLM required)
# ---------------------------------------------------------------------------


def _heuristic_compress(content: str) -> str:
    """Remove redundant whitespace and filler words."""
    # Remove multiple blank lines
    content = re.sub(r"\n{3,}", "\n\n", content)
    # Remove common filler phrases
    fillers = [
        "please note that ",
        "it is important to ",
        "keep in mind that ",
        "make sure to ",
        "remember that ",
        "you should ",
        "please ",
    ]
    lower = content.lower()
    for filler in fillers:
        if filler in lower:
            # Case-insensitive removal of first occurrence
            idx = lower.find(filler)
            content = content[:idx] + content[idx + len(filler):]
            lower = content.lower()
            break  # One compression per mutation
    return content.strip()


def _heuristic_restructure(content: str) -> str:
    """Shuffle paragraph order (position effect exploration)."""
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    if len(paragraphs) <= 1:
        return content
    # Swap two random paragraphs
    i, j = random.sample(range(len(paragraphs)), 2)
    paragraphs[i], paragraphs[j] = paragraphs[j], paragraphs[i]
    return "\n\n".join(paragraphs)


def _heuristic_rephrase(content: str) -> str:
    """Simple synonym substitution for common instruction words."""
    substitutions = [
        ("generate", "produce"),
        ("produce", "create"),
        ("create", "generate"),
        ("analyze", "examine"),
        ("examine", "investigate"),
        ("describe", "explain"),
        ("explain", "describe"),
        ("ensure", "verify"),
        ("verify", "confirm"),
        ("important", "critical"),
        ("critical", "essential"),
        ("should", "must"),
    ]
    for old, new in substitutions:
        if old in content.lower():
            # Replace first occurrence, preserving case
            pattern = re.compile(re.escape(old), re.IGNORECASE)
            content = pattern.sub(new, content, count=1)
            break  # One substitution per mutation
    return content


def _heuristic_constrain(content: str) -> str:
    """Add a simple output constraint to the content."""
    constraints = [
        "\nBe concise. Limit response to the essential points.",
        "\nStructure your response with clear headings.",
        "\nProvide specific examples where possible.",
        "\nIf uncertain, state your confidence level explicitly.",
        "\nStart with the most important finding.",
    ]
    constraint = random.choice(constraints)
    return content + constraint


def _heuristic_expand(content: str) -> str:
    """Add clarifying detail to the content."""
    expansions = [
        " Think step by step before answering.",
        " Consider edge cases and failure modes.",
        " Distinguish between what you know and what you infer.",
        " Ground your response in specific evidence.",
    ]
    expansion = random.choice(expansions)
    return content + expansion


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences (simple heuristic)."""
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]


def _interleave(a: list[str], b: list[str]) -> list[str]:
    """Interleave two lists, handling unequal lengths."""
    result = []
    for i in range(max(len(a), len(b))):
        if i < len(a):
            result.append(a[i])
        if i < len(b):
            result.append(b[i])
    return result


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def create_prompt_genome(
    *,
    name: str,
    system_identity: str = "",
    task_instruction: str = "",
    few_shot_examples: str = "",
    output_format: str = "",
    safety_constraints: str = "",
    context_template: str = "",
    species: str = "general",
    tags: list[str] | None = None,
) -> PromptGenome:
    """Factory function to create a well-structured prompt genome.

    This encodes the canonical prompt structure as a genome with
    properly classified segments:

    - system_identity: INVARIANT (who the agent is, its telos)
    - safety_constraints: INVARIANT (what must never be violated)
    - task_instruction: MUTABLE (the core task description)
    - few_shot_examples: MUTABLE (demonstrations)
    - output_format: MUTABLE (response structure)
    - context_template: ADAPTIVE (runtime-injected variables)

    Args:
        name: Human-readable name for this prompt.
        system_identity: The agent's identity/role statement.
        task_instruction: What the agent should do.
        few_shot_examples: Example input/output pairs.
        output_format: Expected response format.
        safety_constraints: Safety rules (invariant).
        context_template: Runtime context template with {placeholders}.
        species: Task type for speciation.
        tags: Optional classification tags.

    Returns:
        A PromptGenome ready for population seeding.
    """
    segments: list[PromptSegment] = []

    if system_identity:
        segments.append(PromptSegment(
            segment_type=SegmentType.INVARIANT,
            role="system_identity",
            content=system_identity,
            weight=1.0,
        ))

    if safety_constraints:
        segments.append(PromptSegment(
            segment_type=SegmentType.INVARIANT,
            role="safety_constraint",
            content=safety_constraints,
            weight=1.0,
        ))

    if task_instruction:
        segments.append(PromptSegment(
            segment_type=SegmentType.MUTABLE,
            role="task_instruction",
            content=task_instruction,
            weight=1.5,  # Higher weight = more optimization pressure
        ))

    if few_shot_examples:
        segments.append(PromptSegment(
            segment_type=SegmentType.MUTABLE,
            role="few_shot_example",
            content=few_shot_examples,
            weight=1.2,
        ))

    if output_format:
        segments.append(PromptSegment(
            segment_type=SegmentType.MUTABLE,
            role="output_format",
            content=output_format,
            weight=1.0,
        ))

    if context_template:
        segments.append(PromptSegment(
            segment_type=SegmentType.ADAPTIVE,
            role="context",
            content=context_template,
            weight=0.8,
        ))

    return PromptGenome(
        name=name,
        segments=segments,
        species=species,
        tags=tags or [],
    )


def create_meta_mutation_prompt(
    content: str,
    operator: str,
    role: str,
    fitness_history: list[float] | None = None,
) -> str:
    """Generate the meta-prompt for LLM-backed mutation.

    This is the OPRO-style prompt that asks an LLM to improve a
    prompt segment. The meta-prompt includes:
    - The current segment content
    - The mutation operator to apply
    - The segment's role in the overall prompt
    - Historical fitness data (what has worked before)

    Args:
        content: Current segment content to mutate.
        operator: Mutation operator name (e.g., "rephrase", "compress").
        role: Segment role (e.g., "task_instruction").
        fitness_history: Recent fitness scores for context.

    Returns:
        The meta-prompt string to send to the mutation LLM.
    """
    history_context = ""
    if fitness_history and len(fitness_history) >= 2:
        recent = fitness_history[-5:]
        trend = "improving" if recent[-1] > recent[0] else "declining"
        history_context = (
            f"\nRecent fitness trend: {trend} "
            f"(last 5: {', '.join(f'{f:.3f}' for f in recent)})\n"
        )

    operator_instructions = {
        "rephrase": (
            "Rephrase this prompt segment to be clearer and more effective. "
            "Preserve the exact semantic intent but improve the wording."
        ),
        "compress": (
            "Compress this prompt segment to use fewer tokens while preserving "
            "ALL essential information and instructions. Remove redundancy."
        ),
        "restructure": (
            "Restructure this prompt segment for better information flow. "
            "Consider primacy and recency effects. Lead with the most critical "
            "information."
        ),
        "expand": (
            "Expand this prompt segment with additional detail, edge cases, "
            "or clarifying instructions that would improve output quality."
        ),
        "exemplify": (
            "Add or improve the few-shot examples in this segment. "
            "Examples should be diverse, representative, and demonstrate "
            "the expected input/output format clearly."
        ),
        "constrain": (
            "Add output constraints or guardrails to this prompt segment "
            "that would improve consistency and reduce failure modes."
        ),
        "tone_shift": (
            "Adjust the tone of this prompt segment to be more direct "
            "and authoritative. Remove hedging language."
        ),
        "abstract": (
            "Generalize this prompt segment into a more reusable pattern "
            "that would work across similar task types."
        ),
    }

    instruction = operator_instructions.get(
        operator,
        f"Apply the '{operator}' transformation to improve this prompt segment."
    )

    return f"""You are a prompt optimization engine. Your task is to improve
a single prompt segment.

SEGMENT ROLE: {role}
MUTATION OPERATOR: {operator}
{history_context}
INSTRUCTION: {instruction}

CURRENT CONTENT:
---
{content}
---

OUTPUT: Return ONLY the improved segment content. No explanation, no
markdown fencing, no preamble. Just the improved text."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "CrossoverMethod",
    "CrossoverRecord",
    "MutationOperator",
    "MutationRecord",
    "PromptCanaryResult",
    "PromptEvaluation",
    "PromptEvolutionConfig",
    "PromptEvolutionEngine",
    "PromptEvolver",
    "PromptFitnessScore",
    "PromptGenome",
    "PromptPopulation",
    "PromptSegment",
    "PromptSpecies",
    "SegmentType",
    "create_meta_mutation_prompt",
    "create_prompt_genome",
]
