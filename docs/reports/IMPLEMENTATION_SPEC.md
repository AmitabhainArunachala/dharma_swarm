# IMPLEMENTATION SPEC — dharma_swarm Overnight Build Phase 2
## Date: 2026-03-08
## Source: Phase 1 Reader Synthesis (Reader-A: 24 new tools, Reader-B: code audit, Reader-C: patterns)
## Target: 3 parallel implementation agents (IMPL-CORE, IMPL-PLANNER, IMPL-SAFETY)

---

## CRITICAL CONTEXT FOR ALL AGENTS

### Existing Infrastructure (DO NOT REINVENT)
These already exist and MUST be used/extended, not recreated:

- `Proposal.think_notes: str = ""` -- exists in `evolution.py:65`, just needs enforcement
- `Proposal.spec_ref: str | None = None` -- exists in `evolution.py:63`
- `Proposal.requirement_refs: list[str]` -- exists in `evolution.py:64`
- `EvolutionPlan` model -- exists in `evolution.py:89-98` with all fields
- `CircuitBreaker` logic -- exists in `evolution.py:231-263` with `_circuit_breaker_limit`
- `CycleResult.strategy_pivots: int` -- exists in `evolution.py:85`
- `ArchiveEntry.spec_ref` and `requirement_refs` -- exist in `archive.py:62-63`
- `FitnessScore.weighted()` -- exists in `archive.py:40-48`
- `TelosGatekeeper.THINK_PHASE_HINTS` -- exists in `telos_gates.py:116-120`
- `_build_system_prompt()` -- exists in `agent_runner.py:79-112`
- `build_agent_context()` -- exists in `context.py:380-452`

### Import Conventions
All imports use `from dharma_swarm.X import Y`. No relative imports. Pydantic BaseModel for all data classes. Async-first (all I/O methods are `async def`).

### Test Conventions
Tests live in `tests/test_<module>.py`. Use `pytest` + `pytest-asyncio`. Fixtures use `tmp_path`. Mock providers return `LLMResponse(content="...", model="mock")`. No network calls in tests.

---

## Priority 0: Darwin Engine Upgrades (Agent 3A — IMPL-CORE)

**Files to modify**: `dharma_swarm/selector.py`, `dharma_swarm/archive.py`, `dharma_swarm/evolution.py`, `dharma_swarm/fitness_predictor.py`

### Change 0A: Novelty Bonus in selector.py

**Source**: DGM (Sakana AI) selection formula. Reader-B Gap #1.

**What**: All 4 selection strategies currently use fitness-only weighting. Add novelty pressure via inverse offspring count.

**File**: `dharma_swarm/selector.py`

**Step 1**: Add a helper to count children for each entry.

```python
# Add after line 26 (after _get_applied function)

async def _count_children(archive: EvolutionArchive) -> dict[str, int]:
    """Count direct children for each entry in the archive.

    Returns:
        Mapping from entry_id to number of direct children.
    """
    counts: dict[str, int] = {}
    for entry in archive._entries.values():
        if entry.parent_id:
            counts[entry.parent_id] = counts.get(entry.parent_id, 0) + 1
    return counts
```

**Step 2**: Add a novelty-adjusted weight function.

```python
# Add after _count_children

def _novelty_weight(entry: ArchiveEntry, child_counts: dict[str, int]) -> float:
    """Compute DGM-style novelty-adjusted weight.

    Formula: fitness * (1.0 / (1.0 + n_children))
    Balances exploitation (fitness) with exploration (fewer children = higher weight).

    Args:
        entry: The archive entry to weight.
        child_counts: Mapping from entry_id to child count.

    Returns:
        Novelty-adjusted weight (always >= 0).
    """
    fitness = entry.fitness.weighted()
    n_children = child_counts.get(entry.id, 0)
    novelty = 1.0 / (1.0 + n_children)
    return fitness * novelty
```

**Step 3**: Modify `tournament_select` to use novelty weights.

Replace the return statement at the end of `tournament_select` (currently line 65):
```python
# OLD:
    return max(pool, key=lambda e: e.fitness.weighted())

# NEW:
    child_counts = await _count_children(archive)
    return max(pool, key=lambda e: _novelty_weight(e, child_counts))
```

**Step 4**: Modify `roulette_select` to use novelty weights.

Replace the weights computation (currently lines 87-93):
```python
# OLD:
    weights = [e.fitness.weighted() for e in candidates]
    total = sum(weights)
    if total == 0.0:
        return random.choice(candidates)
    return random.choices(candidates, weights=weights, k=1)[0]

# NEW:
    child_counts = await _count_children(archive)
    weights = [_novelty_weight(e, child_counts) for e in candidates]
    total = sum(weights)
    if total == 0.0:
        return random.choice(candidates)
    return random.choices(candidates, weights=weights, k=1)[0]
```

**Step 5**: Modify `rank_select` to incorporate novelty as tiebreaker.

Replace the sort key (currently line 117):
```python
# OLD:
    sorted_asc = sorted(candidates, key=lambda e: e.fitness.weighted())

# NEW:
    child_counts = await _count_children(archive)
    sorted_asc = sorted(candidates, key=lambda e: _novelty_weight(e, child_counts))
```

**DO NOT MODIFY**: `elite_select` -- elite is intentionally pure exploitation.

---

### Change 0B: MAP-Elites Feature Grid in archive.py

**Source**: OpenEvolve MAP-Elites + CycleQD. Reader-B Gap #2.

**What**: Add a diversity grid that bins entries by feature dimensions. Prevents convergence on single high-fitness variant.

**File**: `dharma_swarm/archive.py`

**Step 1**: Add feature dimensions to `ArchiveEntry`.

Add a new field after `rollback_reason` (line 84):
```python
    # MAP-Elites feature coordinates
    feature_coords: dict[str, float] = Field(default_factory=dict)
```

**Step 2**: Add `MAPElitesGrid` class.

Add after the `ArchiveEntry` class (after line 85):
```python
class MAPElitesGrid:
    """MAP-Elites diversity archive binning entries by feature dimensions.

    Maintains one entry per bin (the fittest). Prevents evolutionary
    convergence by preserving diverse solutions across feature space.

    Feature dimensions for dharma_swarm:
        - dharmic_alignment: [0.0, 1.0] binned into N_BINS intervals
        - elegance: [0.0, 1.0] binned into N_BINS intervals
        - complexity: diff_size mapped to [0.0, 1.0] via min(diff_lines/500, 1.0)
    """

    N_BINS: int = 5  # 5x5x5 = 125 cells max

    def __init__(self) -> None:
        # grid[(d_bin, e_bin, c_bin)] = ArchiveEntry (best per cell)
        self._grid: dict[tuple[int, int, int], ArchiveEntry] = {}

    @staticmethod
    def _bin_value(value: float, n_bins: int = 5) -> int:
        """Map a [0, 1] value to a bin index."""
        return min(int(value * n_bins), n_bins - 1)

    @staticmethod
    def compute_feature_coords(entry: ArchiveEntry) -> dict[str, float]:
        """Compute feature coordinates from an entry's fitness and diff.

        Returns:
            Dict with keys 'dharmic_alignment', 'elegance', 'complexity'.
        """
        diff_lines = len(entry.diff.splitlines()) if entry.diff else 0
        return {
            "dharmic_alignment": entry.fitness.dharmic_alignment,
            "elegance": entry.fitness.elegance,
            "complexity": min(diff_lines / 500.0, 1.0),
        }

    def _coords_to_bin(self, coords: dict[str, float]) -> tuple[int, int, int]:
        """Convert feature coordinates to grid bin indices."""
        return (
            self._bin_value(coords.get("dharmic_alignment", 0.0)),
            self._bin_value(coords.get("elegance", 0.0)),
            self._bin_value(coords.get("complexity", 0.0)),
        )

    def try_insert(self, entry: ArchiveEntry) -> bool:
        """Insert entry if its bin is empty or it beats the current occupant.

        Also populates entry.feature_coords if not already set.

        Returns:
            True if entry was inserted (new bin or higher fitness), False otherwise.
        """
        if not entry.feature_coords:
            entry.feature_coords = self.compute_feature_coords(entry)
        bin_key = self._coords_to_bin(entry.feature_coords)
        existing = self._grid.get(bin_key)
        if existing is None or entry.fitness.weighted() > existing.fitness.weighted():
            self._grid[bin_key] = entry
            return True
        return False

    def get_diverse_parents(self, n: int = 5) -> list[ArchiveEntry]:
        """Return up to n entries from distinct bins, sorted by fitness.

        This provides diverse parents for the next evolution cycle.
        """
        entries = sorted(
            self._grid.values(),
            key=lambda e: e.fitness.weighted(),
            reverse=True,
        )
        return entries[:n]

    @property
    def occupied_bins(self) -> int:
        """Number of occupied bins in the grid."""
        return len(self._grid)

    @property
    def total_bins(self) -> int:
        """Total possible bins (N_BINS^3)."""
        return self.N_BINS ** 3

    def coverage(self) -> float:
        """Fraction of bins occupied."""
        return self.occupied_bins / self.total_bins if self.total_bins > 0 else 0.0
```

**Step 3**: Integrate grid into `EvolutionArchive`.

Add to `EvolutionArchive.__init__` (line 102), after `self._entries`:
```python
        self.grid = MAPElitesGrid()
```

Add to `EvolutionArchive.load` — after successfully parsing each entry (after line 123, inside the try block):
```python
                    self.grid.try_insert(entry)
```

Add to `EvolutionArchive.add_entry` — after `self._entries[entry.id] = entry` (after line 152):
```python
        self.grid.try_insert(entry)
```

**Step 4**: Add a `get_diverse` method to `EvolutionArchive`.

Add after `get_latest` method (after line 199):
```python
    async def get_diverse(self, n: int = 5) -> list[ArchiveEntry]:
        """Return diverse parents from the MAP-Elites grid.

        Args:
            n: Maximum number of diverse entries to return.

        Returns:
            List of entries from distinct feature bins, sorted by fitness.
        """
        return self.grid.get_diverse_parents(n=n)
```

---

### Change 0C: Verbal Self-Reflection in evolution.py

**Source**: Reflexion (NeurIPS 2023). Reader-B Gap #4. Reader-C P0 #5.

**What**: After each evolution cycle, generate a verbal reflection asking "why did this cycle succeed/fail?" and store it in the CycleResult.

**File**: `dharma_swarm/evolution.py`

**Step 1**: Add reflection fields to `CycleResult`.

Add after `duration_seconds` field (line 86):
```python
    reflection: str = ""
    lessons_learned: list[str] = Field(default_factory=list)
```

**Step 2**: Add a reflection method to `DarwinEngine`.

Add after `get_fitness_trend` (after line 754, at end of class):
```python
    async def reflect_on_cycle(
        self,
        cycle: CycleResult,
        proposals: list[Proposal],
        provider: Any | None = None,
    ) -> CycleResult:
        """Generate verbal self-reflection after an evolution cycle.

        If a provider is available, uses LLM to generate reflection.
        Otherwise, generates a rule-based reflection from cycle metrics.

        Args:
            cycle: The completed CycleResult to reflect on.
            proposals: The proposals that were processed.
            provider: Optional LLM provider for verbal reflection.

        Returns:
            The CycleResult with reflection and lessons_learned populated.
        """
        # Rule-based reflection (always available, no LLM needed)
        lessons: list[str] = []

        if cycle.proposals_archived == 0 and cycle.proposals_submitted > 0:
            lessons.append(
                f"All {cycle.proposals_submitted} proposals failed. "
                "Consider: different mutation strategy, different parent, "
                "or relaxing gate criteria."
            )
        if cycle.circuit_breakers_tripped > 0:
            lessons.append(
                f"Circuit breaker tripped {cycle.circuit_breakers_tripped}x. "
                "Repeated failures on same gate signature. Strategy pivot needed."
            )
        if cycle.best_fitness < 0.3 and cycle.proposals_archived > 0:
            lessons.append(
                f"Best fitness only {cycle.best_fitness:.3f}. "
                "Proposals are passing gates but scoring poorly. "
                "Check: correctness (test pass rate), elegance (AST score)."
            )
        if cycle.best_fitness > 0.7:
            lessons.append(
                f"Strong cycle: best fitness {cycle.best_fitness:.3f}. "
                "Archive this lineage for future parent selection."
            )

        # Rejection analysis
        rejected = [p for p in proposals if p.status == EvolutionStatus.REJECTED]
        if rejected:
            gate_reasons = [p.gate_reason or "unknown" for p in rejected]
            unique_reasons = list(set(gate_reasons))
            lessons.append(
                f"{len(rejected)} rejected. Gate reasons: {'; '.join(unique_reasons[:3])}"
            )

        cycle.lessons_learned = lessons
        cycle.reflection = " | ".join(lessons) if lessons else "Clean cycle, no issues."

        # Log reflection as trace
        await self.traces.log_entry(
            TraceEntry(
                agent="darwin_engine",
                action="reflect",
                state="reflected",
                metadata={
                    "cycle_id": cycle.cycle_id,
                    "reflection": cycle.reflection,
                    "lessons_count": len(lessons),
                },
            )
        )

        logger.info("Cycle %s reflection: %s", cycle.cycle_id, cycle.reflection[:200])
        return cycle
```

**Step 3**: Wire reflection into `run_cycle` and `run_cycle_with_sandbox`.

At the end of `run_cycle` (before the final `return result` on line 549), add:
```python
        # Verbal self-reflection (Reflexion pattern)
        await self.reflect_on_cycle(result, proposals)
```

At the end of `run_cycle_with_sandbox` (before the final `return result` on line 713), add:
```python
        # Verbal self-reflection (Reflexion pattern)
        await self.reflect_on_cycle(result, proposals)
```

---

### Change 0D: Think-Gate Enforcement in evolution.py

**Source**: Devin mandatory think (10 cases). Reader-C P0 #1.

**What**: Enforce that `Proposal.think_notes` is non-empty before any status transition past PENDING. The field exists but is never enforced.

**File**: `dharma_swarm/evolution.py`

**Step 1**: Add a validation check in `gate_check`.

At the beginning of `gate_check` method (after line 267, before the `result = DEFAULT_GATEKEEPER.check(...)` call), add:
```python
        # ThinkGate: enforce non-empty think_notes (Devin mandatory-think pattern)
        if not proposal.think_notes or len(proposal.think_notes.strip()) < 10:
            proposal.status = EvolutionStatus.REJECTED
            proposal.gate_decision = GateDecision.BLOCK.value
            proposal.gate_reason = (
                "ThinkGate: Proposal.think_notes is empty or too short "
                f"(got {len(proposal.think_notes.strip())} chars, need >= 10). "
                "Every proposal must include deliberate reasoning about risks, "
                "alternatives considered, and expected outcomes."
            )
            logger.warning(
                "Proposal %s REJECTED by ThinkGate: insufficient think_notes",
                proposal.id,
            )
            await self.traces.log_entry(
                TraceEntry(
                    agent="darwin_engine",
                    action="think_gate",
                    state="rejected",
                    metadata={
                        "proposal_id": proposal.id,
                        "think_notes_len": len(proposal.think_notes.strip()),
                    },
                )
            )
            return proposal
```

---

### Change 0E: Subtree Fitness Estimation in fitness_predictor.py

**Source**: HGM Clade-Metaproductivity (CMP). Reader-A finding from Landscape.

**What**: Extend FitnessPredictor to estimate the potential of an entry's descendants, not just its own fitness. An entry that performs poorly might be a great ancestor.

**File**: `dharma_swarm/fitness_predictor.py`

**Step 1**: Add a subtree estimation method.

Add after the `group_count` property (after line 197):
```python
    def estimate_subtree_potential(
        self,
        entry_id: str,
        archive_entries: dict[str, Any],
    ) -> float:
        """Estimate the metaproductivity of an entry's subtree (HGM CMP pattern).

        Looks at all descendants and computes the max fitness achieved
        in the subtree. An entry with low personal fitness but high-fitness
        descendants has high metaproductivity.

        Args:
            entry_id: The root entry to evaluate.
            archive_entries: Dict mapping entry_id to entry objects
                (must have .parent_id and .fitness.weighted() attributes).

        Returns:
            Estimated subtree potential (0.0 to 1.0).
            Returns the entry's own fitness if no descendants exist.
        """
        # Find all descendants via BFS
        descendants: list[float] = []
        queue = [entry_id]
        visited: set[str] = {entry_id}

        while queue:
            current_id = queue.pop(0)
            for eid, entry in archive_entries.items():
                if eid in visited:
                    continue
                if getattr(entry, "parent_id", None) == current_id:
                    visited.add(eid)
                    queue.append(eid)
                    fitness = getattr(entry, "fitness", None)
                    if fitness and hasattr(fitness, "weighted"):
                        descendants.append(fitness.weighted())

        if not descendants:
            # No descendants — return own fitness or neutral
            own = archive_entries.get(entry_id)
            if own and hasattr(own, "fitness") and hasattr(own.fitness, "weighted"):
                return own.fitness.weighted()
            return _NEUTRAL_PRIOR

        # CMP = max descendant fitness (could also use mean or weighted)
        return max(descendants)
```

---

### Test Criteria for Priority 0

**File**: `tests/test_evolution.py` and `tests/test_selector.py` (extend existing)

```
TEST 1: test_novelty_bonus_reduces_overexploited_parent
    - Create archive with 3 entries: A (fitness=0.8, 10 children), B (fitness=0.6, 0 children), C (fitness=0.7, 2 children)
    - Run tournament_select 100 times
    - Assert B is selected more often than pure-fitness would predict (B should win >20% despite lower fitness)
    - Assert A is selected LESS often than pure-fitness (A's 10 children reduce its novelty weight)

TEST 2: test_map_elites_grid_prevents_convergence
    - Create 10 entries with same high fitness but different (dharmic_alignment, elegance, complexity) coordinates
    - Insert all into MAPElitesGrid
    - Assert grid.occupied_bins >= 3 (entries land in different cells)
    - Insert entry with slightly higher fitness in occupied bin
    - Assert it replaces the existing occupant
    - Insert entry with lower fitness in occupied bin
    - Assert it does NOT replace the occupant

TEST 3: test_map_elites_coverage
    - Create MAPElitesGrid with N_BINS=5
    - Assert total_bins == 125
    - Insert entries spanning feature space
    - Assert coverage() returns occupied_bins / 125

TEST 4: test_cycle_result_has_reflection
    - Run DarwinEngine.run_cycle with 3 proposals (1 passes gates, 2 fail)
    - Assert result.reflection is non-empty string
    - Assert result.lessons_learned is non-empty list
    - Assert "rejected" appears in reflection (since 2 proposals failed)

TEST 5: test_think_gate_rejects_empty_notes
    - Create proposal with think_notes=""
    - Run gate_check
    - Assert proposal.status == REJECTED
    - Assert "ThinkGate" in proposal.gate_reason

TEST 6: test_think_gate_passes_with_notes
    - Create proposal with think_notes="This mutation improves selector diversity by adding novelty weighting"
    - Run gate_check
    - Assert proposal.status != REJECTED (may be GATED or REJECTED for other reasons, but NOT ThinkGate)

TEST 7: test_subtree_fitness_estimation
    - Create mock archive: A->B->C where A.fitness=0.3, B.fitness=0.5, C.fitness=0.9
    - Call estimate_subtree_potential("A", archive)
    - Assert result == 0.9 (C is the best descendant)
    - Call estimate_subtree_potential("C", archive) with no descendants
    - Assert result == 0.9 (own fitness returned)

TEST 8: test_archive_entry_has_feature_coords
    - Create ArchiveEntry with fitness scores
    - Call MAPElitesGrid.compute_feature_coords(entry)
    - Assert result has keys: dharmic_alignment, elegance, complexity
    - Assert all values are in [0.0, 1.0]

TEST 9: test_diverse_selection_from_grid
    - Populate grid with entries in 5 different bins
    - Call get_diverse(n=3)
    - Assert 3 entries returned
    - Assert entries are from different bins (different feature_coords)
```

---

## Priority 1: Agent Loop + Planner Module (Agent 3B — IMPL-PLANNER)

**Files to create**: `dharma_swarm/planner.py`
**Files to modify**: `dharma_swarm/agent_runner.py`, `dharma_swarm/context.py`

### Change 1A: New planner.py Module

**Source**: Manus external planner, Devin dual-mode, Traycer read-only planner, Qoder quest design. Reader-C P0 #3.

**What**: A Planner class that generates numbered pseudocode plans. The planner ONLY reads and plans — it never writes code. Plans are injected as structured events into executor agents.

**File**: `dharma_swarm/planner.py` (NEW FILE)

```python
"""Planner module -- plan-before-execute enforcement.

Implements the Manus/Devin/Traycer pattern: planning and execution are
separated. The planner generates structured task plans; executors receive
plans and follow them. Planners are read-only — they cannot write code.

The EvolutionPlan model already exists in evolution.py. This module adds
the general-purpose TaskPlan for non-evolution work.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from dharma_swarm.models import Task, _new_id, _utc_now

logger = logging.getLogger(__name__)


class PlanStep(BaseModel):
    """A single step in a task plan."""

    index: int
    description: str
    files_to_read: list[str] = Field(default_factory=list)
    files_to_modify: list[str] = Field(default_factory=list)
    verification: str = ""
    status: str = "pending"  # pending, in_progress, completed, skipped


class TaskPlan(BaseModel):
    """Structured plan for a task, generated before execution.

    This is the Manus/Kiro pattern: plans are explicit, numbered,
    and injected into executor context. Plans can be validated
    before execution begins.
    """

    id: str = Field(default_factory=_new_id)
    task_id: str = ""
    task_title: str = ""
    summary: str = ""
    steps: list[PlanStep] = Field(default_factory=list)
    think_notes: str = ""
    complexity_rating: int = Field(default=1, ge=1, le=10)
    created_at: str = Field(default_factory=lambda: _utc_now().isoformat())
    planner_agent: str = "task_planner"


class Planner:
    """Task planner that generates structured plans before execution.

    The planner is intentionally limited: it reads files and generates plans
    but never writes code. This is the Traycer read-only pattern.

    Usage:
        planner = Planner()
        plan = planner.create_plan(task)
        # Validate plan, then pass to executor
        context = planner.format_plan_for_injection(plan)
        # Inject context into executor's system prompt
    """

    def create_plan(
        self,
        task: Task,
        files_to_read: list[str] | None = None,
        files_to_modify: list[str] | None = None,
        think_notes: str = "",
    ) -> TaskPlan:
        """Create a structured plan for a task.

        This is a lightweight plan creation — no LLM call. For LLM-generated
        plans, use create_plan_with_provider().

        Args:
            task: The task to plan for.
            files_to_read: Files the executor should read before starting.
            files_to_modify: Files the executor is expected to modify.
            think_notes: Planner's reasoning about the approach.

        Returns:
            A TaskPlan ready for validation and injection.
        """
        steps: list[PlanStep] = []

        # Step 1: Always read relevant files first (v0/Devin read-before-write)
        if files_to_read:
            steps.append(PlanStep(
                index=1,
                description="Read relevant files to understand current state",
                files_to_read=list(files_to_read),
                verification="Confirm understanding of existing code structure",
            ))

        # Step 2: Implementation steps (one per file to modify)
        if files_to_modify:
            for i, filepath in enumerate(files_to_modify, start=len(steps) + 1):
                steps.append(PlanStep(
                    index=i,
                    description=f"Modify {filepath} according to task requirements",
                    files_to_read=[filepath],
                    files_to_modify=[filepath],
                    verification=f"Verify {filepath} changes are correct",
                ))

        # Step 3: Verification
        steps.append(PlanStep(
            index=len(steps) + 1,
            description="Run tests and verify all changes",
            verification="All tests pass, no regressions",
        ))

        # Complexity rating heuristic
        n_files = len(files_to_modify or [])
        complexity = min(max(n_files, 1), 10)

        plan = TaskPlan(
            task_id=task.id,
            task_title=task.title,
            summary=f"Plan for: {task.title}",
            steps=steps,
            think_notes=think_notes or f"Planning task: {task.title}",
            complexity_rating=complexity,
        )

        logger.info(
            "Created plan %s for task %s: %d steps, complexity=%d",
            plan.id, task.id, len(steps), complexity,
        )
        return plan

    async def create_plan_with_provider(
        self,
        task: Task,
        provider: Any,
        context: str = "",
    ) -> TaskPlan:
        """Generate an LLM-powered plan for a task.

        The provider is used in read-only mode (generates text, never writes files).

        Args:
            task: The task to plan for.
            provider: LLM provider (must have async complete() method).
            context: Additional context to include in the planning prompt.

        Returns:
            A TaskPlan with LLM-generated steps.
        """
        from dharma_swarm.models import LLMRequest

        prompt = (
            f"You are a PLANNER. You create plans but NEVER write code.\n"
            f"Task: {task.title}\n"
            f"Description: {task.description}\n"
            f"\n{context}\n\n"
            f"Generate a numbered plan with steps. For each step:\n"
            f"1. What to do (one sentence)\n"
            f"2. What files to read first\n"
            f"3. What files to modify\n"
            f"4. How to verify the step succeeded\n"
            f"\nRate complexity 1-10.\n"
            f"Think carefully about risks and alternatives."
        )

        request = LLMRequest(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": prompt}],
            system="You are a planning agent. Generate structured plans. Never write code.",
            max_tokens=2000,
            temperature=0.3,
        )

        response = await provider.complete(request)

        # Parse response into plan (simplified -- real parsing would be more robust)
        plan = TaskPlan(
            task_id=task.id,
            task_title=task.title,
            summary=response.content[:200],
            think_notes=response.content,
            planner_agent="llm_planner",
        )

        logger.info("LLM plan %s created for task %s", plan.id, task.id)
        return plan

    @staticmethod
    def format_plan_for_injection(plan: TaskPlan) -> str:
        """Format a plan as text for injection into an executor's context.

        This is the Manus pattern: plans are injected as events into the
        agent's context stream.

        Args:
            plan: The plan to format.

        Returns:
            Formatted plan string ready for system prompt injection.
        """
        lines = [
            f"## EXECUTION PLAN (plan_id={plan.id})",
            f"Task: {plan.task_title}",
            f"Complexity: {plan.complexity_rating}/10",
            f"Summary: {plan.summary}",
            "",
            "### Steps:",
        ]

        for step in plan.steps:
            status_mark = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]", "skipped": "[-]"}.get(step.status, "[ ]")
            lines.append(f"{status_mark} {step.index}. {step.description}")
            if step.files_to_read:
                lines.append(f"     Read: {', '.join(step.files_to_read)}")
            if step.files_to_modify:
                lines.append(f"     Modify: {', '.join(step.files_to_modify)}")
            if step.verification:
                lines.append(f"     Verify: {step.verification}")

        lines.append("")
        lines.append(f"Planner notes: {plan.think_notes[:500]}")
        lines.append("")
        lines.append(
            "IMPORTANT: Follow this plan step by step. "
            "Do not skip steps. Do not add steps not in the plan. "
            "If you encounter a problem, note it and continue."
        )

        return "\n".join(lines)

    @staticmethod
    def update_step_status(
        plan: TaskPlan, step_index: int, status: str
    ) -> TaskPlan:
        """Update the status of a specific plan step.

        Args:
            plan: The plan to update.
            step_index: 1-based index of the step.
            status: New status (pending, in_progress, completed, skipped).

        Returns:
            The updated plan.
        """
        for step in plan.steps:
            if step.index == step_index:
                step.status = status
                break
        return plan
```

### Change 1B: Memory Survival Directive in context.py

**Source**: Windsurf "ALL CONVERSATION CONTEXT will be deleted". Reader-C P0 #4.

**What**: Inject a memory survival instinct directive into every agent's context.

**File**: `dharma_swarm/context.py`

**Step 1**: Add constant after CONTEXT_BUDGET (line 377):

```python
MEMORY_SURVIVAL_DIRECTIVE = (
    "\n\n## CRITICAL: MEMORY SURVIVAL\n"
    "YOUR CONTEXT WILL BE DESTROYED after this task completes. "
    "You will have NO memory of this conversation.\n"
    "Before your task ends, you MUST externalize:\n"
    "- Discoveries and patterns -> write to ~/.dharma/shared/<your_role>_notes.md (APPEND)\n"
    "- Important findings -> write to ~/.dharma/witness/ with timestamp\n"
    "- Lessons learned -> include in task result\n"
    "Read ~/.dharma/shared/ FIRST to see what other agents already found.\n"
    "Failure to externalize = permanent knowledge loss."
)
```

**Step 2**: Inject the directive into `build_agent_context`.

At the end of `build_agent_context`, before the hard cap check (before line 449), add:
```python
    # Memory survival instinct (Windsurf pattern)
    sections.append(MEMORY_SURVIVAL_DIRECTIVE)
    used += len(MEMORY_SURVIVAL_DIRECTIVE)
```

### Change 1C: Plan Injection in agent_runner.py

**Source**: Manus plan injection as events. Reader-C finding.

**What**: When an agent starts a task, check if a plan exists and inject it into the system prompt.

**File**: `dharma_swarm/agent_runner.py`

**Step 1**: Modify `_build_prompt` (line 115) to accept and inject an optional plan.

```python
# OLD (line 115-123):
def _build_prompt(task: Task, config: AgentConfig) -> LLMRequest:
    """Build an LLMRequest from a task and agent config."""
    system = _build_system_prompt(config)
    user_content = f"## Task: {task.title}\n\n{task.description}"
    return LLMRequest(
        model=config.model,
        messages=[{"role": "user", "content": user_content}],
        system=system,
    )

# NEW:
def _build_prompt(
    task: Task,
    config: AgentConfig,
    plan_context: str = "",
) -> LLMRequest:
    """Build an LLMRequest from a task and agent config.

    Args:
        task: The task to execute.
        config: Agent configuration.
        plan_context: Optional formatted plan to inject (Manus pattern).
    """
    system = _build_system_prompt(config)
    user_parts = [f"## Task: {task.title}\n\n{task.description}"]
    if plan_context:
        user_parts.append(f"\n\n{plan_context}")
    return LLMRequest(
        model=config.model,
        messages=[{"role": "user", "content": "\n".join(user_parts)}],
        system=system,
    )
```

---

### Test Criteria for Priority 1

**File**: `tests/test_planner.py` (NEW FILE)

```
TEST 1: test_create_plan_basic
    - Create a Task with title="Fix bug" and description="Fix the selector"
    - Call Planner().create_plan(task, files_to_read=["selector.py"], files_to_modify=["selector.py"])
    - Assert plan has >= 3 steps (read, modify, verify)
    - Assert plan.task_id == task.id
    - Assert plan.complexity_rating >= 1

TEST 2: test_format_plan_for_injection
    - Create a TaskPlan with 3 steps
    - Call Planner.format_plan_for_injection(plan)
    - Assert result contains "EXECUTION PLAN"
    - Assert result contains step descriptions
    - Assert result contains "Follow this plan step by step"

TEST 3: test_update_step_status
    - Create plan with 3 steps
    - Call update_step_status(plan, 1, "completed")
    - Assert plan.steps[0].status == "completed"
    - Assert plan.steps[1].status == "pending" (unchanged)

TEST 4: test_memory_survival_directive_injected
    - Call build_agent_context(role="surgeon")
    - Assert "CONTEXT WILL BE DESTROYED" in result
    - Assert "externalize" in result.lower()

TEST 5: test_build_prompt_with_plan
    - Create task and config
    - Create plan and format it
    - Call _build_prompt(task, config, plan_context=formatted_plan)
    - Assert "EXECUTION PLAN" in the user message content

TEST 6: test_plan_step_has_verification
    - Create plan with files_to_modify=["foo.py"]
    - Assert each modification step has non-empty verification field

TEST 7: test_complexity_rating_scales_with_files
    - Create plan with 1 file -> assert complexity == 1
    - Create plan with 5 files -> assert complexity == 5
    - Create plan with 15 files -> assert complexity == 10 (capped)
```

---

## Priority 2: Safety + Memory + Self-Reference (Agent 3C — IMPL-SAFETY)

**Files to modify**: `dharma_swarm/telos_gates.py`, `dharma_swarm/agent_runner.py`, `dharma_swarm/providers.py`

### Change 2A: Mandatory Think Points in telos_gates.py

**Source**: Devin 10-case mandatory think. Reader-C P0 #1.

**What**: Promote WITNESS gate from advisory (Tier C) to mandatory enforcement for specific think phases. When a think_phase is specified and reflection is insufficient, BLOCK instead of just WARN.

**File**: `dharma_swarm/telos_gates.py`

**Step 1**: Add mandatory think phases constant.

Add after `THINK_PHASE_HINTS` dict (after line 120):
```python
    # Think phases that BLOCK (not just warn) on insufficient reflection
    MANDATORY_THINK_PHASES: set[str] = {
        "before_write",
        "before_git",
        "before_complete",
        "before_pivot",
    }
```

**Step 2**: Modify the WITNESS gate logic to block on mandatory phases.

Replace the WITNESS gate section (lines 254-280) with:
```python
        # --- WITNESS (Tier C, promoted to blocking for mandatory phases) ---
        phase_key = (think_phase or "").strip().lower()
        if phase_key:
            reflection_text = reflection.strip() or f"{action} {content}".strip()
            if self._is_reflection_sufficient(reflection_text):
                results["WITNESS"] = (
                    GateResult.PASS,
                    f"Think-point satisfied ({phase_key})",
                )
            elif phase_key in self.MANDATORY_THINK_PHASES:
                # Mandatory think phases BLOCK, not just warn
                results["WITNESS"] = (
                    GateResult.FAIL,
                    f"MANDATORY think-point missing ({phase_key}). "
                    f"{self.THINK_PHASE_HINTS.get(phase_key, 'Pause and reflect before proceeding.')} "
                    f"This phase requires deliberate reflection before proceeding.",
                )
            else:
                hint = self.THINK_PHASE_HINTS.get(
                    phase_key,
                    "Pause and reflect before proceeding.",
                )
                results["WITNESS"] = (
                    GateResult.WARN,
                    f"Think-point missing ({phase_key}). {hint}",
                )
        else:
            # Use recursive reading awareness for file operations
            if not hasattr(self, "_witness_gate"):
                from dharma_swarm.telos_gates_witness_enhancement import (
                    WitnessGateEnhancement,
                )
                self._witness_gate = WitnessGateEnhancement()
            results["WITNESS"] = self._witness_gate.evaluate(
                action, content, tool_name,
            )
```

**Step 3**: Update the decision logic to handle WITNESS as potential blocker.

The existing decision logic already handles Tier C FAIL as REVIEW. But for mandatory think phases, we want WITNESS FAIL to be a BLOCK. Add this check BEFORE the existing tier_c_fail check (before line 331):

```python
        # Mandatory think-phase WITNESS failures are blocking
        witness_result = results.get("WITNESS")
        if (
            witness_result
            and witness_result[0] == GateResult.FAIL
            and (think_phase or "").strip().lower() in self.MANDATORY_THINK_PHASES
        ):
            return GateCheckResult(
                decision=GateDecision.BLOCK,
                reason=f"Mandatory think-point violation: {witness_result[1]}",
                gate_results=results,
            )
```

---

### Change 2B: Fix SubprocessProvider 5000-char Truncation

**Source**: Reader-B Gap #3. Confirmed bug at providers.py:372.

**What**: The `_SubprocessProvider.complete()` method silently truncates stdout at 5000 chars. Claude Code and Codex outputs are often longer. Increase to 50000 chars.

**File**: `dharma_swarm/providers.py`

**Step 1**: Change line 372.

```python
# OLD (line 372):
        content = stdout.decode()[:5000] if stdout else ""

# NEW:
        content = stdout.decode()[:50_000] if stdout else ""
```

That's it. One line. Highest ROI fix in the codebase per Reader-B.

---

### Change 2C: Read-Before-Write Tracking in agent_runner.py

**Source**: v0 enforcement + Devin + Claude Code universal pattern.

**What**: Track which files an agent has read during task execution. Warn (via logging) if a file is written without being read first. This is enforcement-via-tracking, not blocking.

**File**: `dharma_swarm/agent_runner.py`

**Step 1**: Add a read tracker to AgentRunner.

Add to `AgentRunner.__init__` (after line 212):
```python
        self._files_read: set[str] = set()
        self._files_written: set[str] = set()
```

**Step 2**: Add tracking methods.

Add after `health_check` method (after line 319):
```python
    def track_file_read(self, filepath: str) -> None:
        """Record that a file was read during task execution."""
        self._files_read.add(filepath)

    def track_file_write(self, filepath: str) -> None:
        """Record a file write and warn if not previously read.

        Implements the v0/Devin read-before-write pattern.
        """
        self._files_written.add(filepath)
        if filepath not in self._files_read:
            logger.warning(
                "Agent %s wrote %s WITHOUT reading it first (read-before-write violation)",
                self._config.name,
                filepath,
            )

    def get_read_write_report(self) -> dict[str, Any]:
        """Return a summary of file access during this task.

        Returns:
            Dict with read_count, write_count, violations (writes without reads).
        """
        violations = self._files_written - self._files_read
        return {
            "files_read": len(self._files_read),
            "files_written": len(self._files_written),
            "violations": list(violations),
            "violation_count": len(violations),
        }
```

**Step 3**: Reset trackers at task start.

In `run_task`, after setting status to BUSY (after line 248), add:
```python
        self._files_read.clear()
        self._files_written.clear()
```

**Step 4**: Log the report after task completion.

In `run_task`, after the `logger.info("Agent %s finished task %s"...)` line (after line 278), add:
```python
            rw_report = self.get_read_write_report()
            if rw_report["violation_count"] > 0:
                logger.warning(
                    "Agent %s had %d read-before-write violations: %s",
                    self._config.name,
                    rw_report["violation_count"],
                    rw_report["violations"][:5],
                )
```

---

### Change 2D: Pop Quiz / Liveness Check Support

**Source**: Devin pop quiz pattern. Reader-C cross-reference.

**What**: Add a method to AgentRunner that injects a test prompt and validates the response. The Garden Daemon can call this periodically.

**File**: `dharma_swarm/agent_runner.py`

**Step 1**: Add a liveness check method to AgentRunner.

Add after `get_read_write_report` method:
```python
    async def liveness_check(
        self,
        challenge: str = "What is your current role and task?",
        expected_keywords: list[str] | None = None,
    ) -> dict[str, Any]:
        """Inject a test prompt and validate the agent's response.

        Implements the Devin pop-quiz pattern: periodically verify that
        a running agent is still operating correctly.

        Args:
            challenge: The test prompt to send.
            expected_keywords: Words that should appear in the response.

        Returns:
            Dict with 'passed' (bool), 'response' (str), 'keywords_found' (list).
        """
        if self._provider is None:
            return {"passed": False, "response": "", "reason": "No provider attached"}

        from dharma_swarm.models import LLMRequest

        request = LLMRequest(
            model=self._config.model,
            messages=[{"role": "user", "content": f"POP QUIZ: {challenge}"}],
            system="Answer the question briefly and accurately.",
            max_tokens=200,
            temperature=0.0,
        )

        try:
            response = await self._provider.complete(request)
            content = response.content.lower()

            expected = expected_keywords or [self._config.role.value]
            found = [kw for kw in expected if kw.lower() in content]
            passed = len(found) > 0

            logger.info(
                "Liveness check for %s: %s (found %d/%d keywords)",
                self._config.name,
                "PASSED" if passed else "FAILED",
                len(found),
                len(expected),
            )

            return {
                "passed": passed,
                "response": response.content[:200],
                "keywords_found": found,
                "keywords_expected": expected,
            }
        except Exception as exc:
            logger.warning("Liveness check failed for %s: %s", self._config.name, exc)
            return {"passed": False, "response": "", "reason": str(exc)}
```

---

### Test Criteria for Priority 2

**File**: `tests/test_telos_gates.py` (extend existing), `tests/test_agent_runner.py` (extend)

```
TEST 1: test_mandatory_think_phase_blocks
    - Call gatekeeper.check(action="write file", think_phase="before_write", reflection="")
    - Assert result.decision == GateDecision.BLOCK
    - Assert "MANDATORY think-point" in result.reason

TEST 2: test_mandatory_think_phase_passes_with_reflection
    - Call gatekeeper.check(action="write file", think_phase="before_write",
        reflection="I have verified the target file exists and this change is reversible via git")
    - Assert result.decision != GateDecision.BLOCK (should be ALLOW or REVIEW)

TEST 3: test_non_mandatory_think_phase_warns_only
    - Call gatekeeper.check(action="something", think_phase="before_debug", reflection="")
    - Assert result.decision != GateDecision.BLOCK (should be REVIEW at most, not BLOCK)
    - Assert WITNESS gate result is WARN, not FAIL

TEST 4: test_subprocess_output_not_truncated_at_5000
    - Create a _SubprocessProvider
    - Mock subprocess that outputs 10000 chars
    - Call complete()
    - Assert len(response.content) > 5000

TEST 5: test_read_write_tracking
    - Create AgentRunner with mock provider
    - Call track_file_read("foo.py")
    - Call track_file_write("foo.py")  # should NOT warn
    - Call track_file_write("bar.py")  # should warn (not read first)
    - report = get_read_write_report()
    - Assert report["violation_count"] == 1
    - Assert "bar.py" in report["violations"]

TEST 6: test_read_write_tracking_resets_per_task
    - Create AgentRunner
    - Call track_file_read("old.py")
    - Run a new task (run_task)
    - Assert _files_read is empty (reset at task start)

TEST 7: test_liveness_check_passes
    - Create AgentRunner with mock provider that returns "I am a coder agent working on task X"
    - Call liveness_check(expected_keywords=["coder"])
    - Assert result["passed"] == True
    - Assert "coder" in result["keywords_found"]

TEST 8: test_liveness_check_fails_no_keywords
    - Create AgentRunner with mock provider that returns "I don't know"
    - Call liveness_check(expected_keywords=["coder", "task"])
    - Assert result["passed"] == False

TEST 9: test_liveness_check_no_provider
    - Create AgentRunner with provider=None
    - Call liveness_check()
    - Assert result["passed"] == False
    - Assert "No provider" in result["reason"]

TEST 10: test_mandatory_think_phases_set
    - Assert "before_write" in TelosGatekeeper.MANDATORY_THINK_PHASES
    - Assert "before_git" in TelosGatekeeper.MANDATORY_THINK_PHASES
    - Assert "before_complete" in TelosGatekeeper.MANDATORY_THINK_PHASES
    - Assert "before_pivot" in TelosGatekeeper.MANDATORY_THINK_PHASES
```

---

## Summary of All Changes

| Priority | File | Change | Lines (est.) | Source Pattern |
|----------|------|--------|-------------|----------------|
| P0 | selector.py | Novelty bonus `1/(1+n_children)` | ~30 | DGM |
| P0 | archive.py | MAPElitesGrid class + integration | ~120 | OpenEvolve |
| P0 | evolution.py | Verbal self-reflection after cycles | ~60 | Reflexion |
| P0 | evolution.py | ThinkGate enforcement | ~25 | Devin |
| P0 | fitness_predictor.py | Subtree fitness estimation | ~35 | HGM CMP |
| P1 | planner.py (NEW) | Planner class + TaskPlan model | ~200 | Manus/Devin/Traycer |
| P1 | context.py | Memory survival directive | ~15 | Windsurf |
| P1 | agent_runner.py | Plan injection into prompts | ~15 | Manus |
| P2 | telos_gates.py | Mandatory think phases (BLOCK) | ~25 | Devin |
| P2 | providers.py | Fix 5000-char truncation | ~1 | Reader-B bug |
| P2 | agent_runner.py | Read-before-write tracking | ~40 | v0/Devin |
| P2 | agent_runner.py | Liveness check (pop quiz) | ~45 | Devin |
| **TOTAL** | | | **~611** | |

### Dependency Order
1. P0 changes are independent of each other — all 3 agents can work in parallel
2. P1 depends on nothing in P0 (planner.py is a new file)
3. P2 depends on nothing in P0 or P1

### Files NOT Modified (Intentional)
- `models.py` — no schema changes needed; all new fields are in evolution.py/archive.py models
- `orchestrator.py` — plan injection happens at agent_runner level, not orchestrator
- `swarm.py` — god object; do not touch until refactoring sprint
- `daemon_config.py` — circuit breaker already exists there; our changes are in evolution.py

---

*IMPLEMENTATION_SPEC.md complete. 3 priorities, 12 changes, 32 tests, ~611 lines. Every change has exact file paths, function signatures, and line references. JSCA!*
