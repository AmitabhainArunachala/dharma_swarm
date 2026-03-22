"""Universal Loop Engine — F(S) = S.

The cascade engine runs any domain through the universal pattern:
  GENERATE → TEST → SCORE → GATE → eigenform check → MUTATE → SELECT → repeat

Phase functions are resolved via importlib from string refs in LoopDomain.
Handles both sync and async callables.

The META domain evolves LoopDomain configs themselves — the strange loop
where the system's configuration is a candidate for its own optimization.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import time
from collections.abc import Callable
from typing import Any

from dharma_swarm.checkpoint import (
    CheckpointStore,
    InterruptDecision,
    InterruptGate,
    InterruptRequest,
    LoopCheckpoint,
)
from dharma_swarm.models import LoopDomain, LoopResult

logger = logging.getLogger(__name__)

# Module-level singletons — shared across all engine runs
_checkpoint_store = CheckpointStore()
_interrupt_gate = InterruptGate()


# ---------------------------------------------------------------------------
# Domain registry
# ---------------------------------------------------------------------------

_DOMAIN_MODULES: dict[str, str] = {
    "code": "dharma_swarm.cascade_domains.code",
    "product": "dharma_swarm.cascade_domains.product",
    "skill": "dharma_swarm.cascade_domains.skill",
    "research": "dharma_swarm.cascade_domains.research",
    "meta": "dharma_swarm.cascade_domains.meta",
}


def get_registered_domains() -> dict[str, LoopDomain]:
    """Load all registered domain configs."""
    domains: dict[str, LoopDomain] = {}
    for name, module_path in _DOMAIN_MODULES.items():
        try:
            mod = importlib.import_module(module_path)
            domains[name] = mod.get_domain()
        except Exception as e:
            logger.warning("Failed to load domain %s: %s", name, e)
    return domains


# ---------------------------------------------------------------------------
# Function resolution
# ---------------------------------------------------------------------------

def _resolve_fn(dotted_path: str) -> Callable[..., Any]:
    """Resolve a dotted import path to a callable.

    E.g. "dharma_swarm.cascade_domains.code.generate" →
         the generate function from code.py.
    """
    parts = dotted_path.rsplit(".", 1)
    if len(parts) != 2:
        raise ImportError(f"Invalid function path: {dotted_path!r}")
    module_path, fn_name = parts
    mod = importlib.import_module(module_path)
    fn = getattr(mod, fn_name)
    if not callable(fn):
        raise TypeError(f"{dotted_path} is not callable")
    return fn


async def _call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Call a function, handling both sync and async."""
    if inspect.iscoroutinefunction(fn):
        return await fn(*args, **kwargs)
    return fn(*args, **kwargs)


# ---------------------------------------------------------------------------
# LoopEngine
# ---------------------------------------------------------------------------

class LoopEngine:
    """Universal strange-loop engine.

    Runs a domain through GENERATE → TEST → SCORE → GATE → eigenform →
    MUTATE → SELECT until convergence, eigenform, or limits.

    Now with:
      - Checkpoint after every iteration (crash-safe resume)
      - InterruptGate at GATE phase (human-in-the-loop for Tier B/C)
    """

    def __init__(
        self,
        domain: LoopDomain,
        *,
        checkpoint_store: CheckpointStore | None = None,
        interrupt_gate: InterruptGate | None = None,
    ):
        self.domain = domain
        self._fns: dict[str, Callable[..., Any]] = {}
        self._store = checkpoint_store or _checkpoint_store
        self._gate = interrupt_gate or _interrupt_gate

    def _resolve_all(self) -> None:
        """Resolve all phase function references."""
        self._fns["generate"] = _resolve_fn(self.domain.generate_fn)
        self._fns["test"] = _resolve_fn(self.domain.test_fn)
        self._fns["score"] = _resolve_fn(self.domain.score_fn)
        self._fns["gate"] = _resolve_fn(self.domain.gate_fn)
        self._fns["mutate"] = _resolve_fn(self.domain.mutate_fn)
        self._fns["select"] = _resolve_fn(self.domain.select_fn)
        self._fns["eigenform"] = _resolve_fn(self.domain.eigenform_fn)

    async def run(
        self,
        seed: dict[str, Any] | None = None,
        *,
        context: dict[str, Any] | None = None,
        resume: bool = True,
    ) -> LoopResult:
        """Run the full loop until convergence or limits.

        If *resume* is True (default), checks for an existing checkpoint
        and resumes from the saved iteration. On crash/restart, no work
        is lost.
        """
        self._resolve_all()
        ctx = context or {}

        result = LoopResult(domain=self.domain.name)
        start = time.monotonic()

        current = seed
        previous: dict[str, Any] | None = None
        candidates: list[dict[str, Any]] = []
        best_score = 0.0
        start_iteration = 0

        # --- RESUME FROM CHECKPOINT ---
        if resume:
            cp = self._store.load(self.domain.name, result.cycle_id)
            if cp is None:
                # Also check for any checkpoint for this domain (latest)
                existing = self._store.list_checkpoints(self.domain.name)
                if existing and not existing[0].converged:
                    cp = existing[0]
                    result.cycle_id = cp.cycle_id

            if cp is not None and not cp.converged:
                logger.info(
                    "Resuming %s from checkpoint: iteration=%d, best=%.3f",
                    self.domain.name, cp.iteration, cp.best_score,
                )
                current = cp.current
                previous = cp.previous
                candidates = cp.candidates
                best_score = cp.best_score
                result.fitness_trajectory = cp.fitness_trajectory
                result.eigenform_trajectory = cp.eigenform_trajectory
                result.cycle_id = cp.cycle_id
                start_iteration = cp.iteration
                start = time.monotonic() - cp.elapsed_seconds

        for iteration in range(start_iteration, self.domain.max_iterations):
            elapsed = time.monotonic() - start
            if elapsed > self.domain.max_duration_seconds:
                result.converged = True
                result.convergence_reason = f"time limit ({self.domain.max_duration_seconds}s)"
                break

            # GENERATE
            artifact = await _call(self._fns["generate"], current, ctx)

            # TEST
            artifact = await _call(self._fns["test"], artifact, ctx)

            # SCORE
            artifact = await _call(self._fns["score"], artifact, ctx)
            score = artifact.get("score", 0.0)
            result.fitness_trajectory.append(score)
            if score > best_score:
                best_score = score

            # GATE (with interrupt support)
            gate_result = await _call(self._fns["gate"], artifact, ctx)
            gate_passed = gate_result.get("passed", True)
            gate_tier = gate_result.get("tier", "C")

            # Tier A/B gate failures trigger interrupt for operator review
            if not gate_passed and gate_tier in ("A", "B"):
                interrupt_req = InterruptRequest(
                    domain=self.domain.name,
                    cycle_id=result.cycle_id,
                    iteration=iteration,
                    phase="gate",
                    reason=f"Tier {gate_tier} gate blocked: {gate_result.get('reason', 'unknown')}",
                    artifact=artifact,
                    gate_results=gate_result,
                )
                response = await self._gate.interrupt(interrupt_req)

                if response.decision == InterruptDecision.REJECT:
                    result.interrupted = True
                    result.interrupt_reason = f"Operator rejected at iteration {iteration}: {response.reason}"
                    logger.info("Operator rejected: %s", response.reason)
                    break
                elif response.decision == InterruptDecision.MODIFY:
                    if response.modified_artifact:
                        artifact = response.modified_artifact
                        score = artifact.get("score", score)
                    # Fall through — operator modified, continue loop
                elif response.decision == InterruptDecision.APPROVE:
                    gate_passed = True  # Override gate

            if not gate_passed:
                logger.debug(
                    "Gate blocked iteration %d: %s",
                    iteration,
                    gate_result.get("reason", ""),
                )
                # Still checkpoint even on gate block
                self._save_checkpoint(
                    result, iteration, current, previous,
                    candidates, best_score, time.monotonic() - start,
                )
                continue

            # EIGENFORM CHECK
            if previous is not None:
                distance = await _call(
                    self._fns["eigenform"], artifact, previous
                )
                result.eigenform_trajectory.append(distance)
                if distance < self.domain.eigenform_epsilon:
                    result.eigenform_reached = True
                    result.converged = True
                    result.convergence_reason = (
                        f"eigenform (distance={distance:.4f} < "
                        f"epsilon={self.domain.eigenform_epsilon})"
                    )
                    result.iterations_completed = iteration + 1
                    result.best_fitness = best_score
                    result.duration_seconds = time.monotonic() - start
                    # Clean up checkpoint on successful convergence
                    self._store.delete(self.domain.name, result.cycle_id)
                    return result
            else:
                result.eigenform_trajectory.append(float("inf"))

            # Check fitness threshold convergence
            if score >= self.domain.fitness_threshold:
                window = self.domain.convergence_window
                if len(result.fitness_trajectory) >= window:
                    recent = result.fitness_trajectory[-window:]
                    variance = _variance(recent)
                    if variance < 0.001:
                        result.converged = True
                        result.convergence_reason = (
                            f"fitness plateau (var={variance:.6f})"
                        )
                        break

            # MUTATE
            mutation_rate = self._adjusted_mutation_rate(result.eigenform_trajectory)
            mutated = await _call(
                self._fns["mutate"], artifact, ctx, mutation_rate
            )
            candidates.append(artifact)
            if len(candidates) > 10:
                candidates = candidates[-10:]

            # SELECT
            previous = current
            current = await _call(self._fns["select"], candidates, ctx)

            # --- CHECKPOINT after every iteration ---
            self._save_checkpoint(
                result, iteration + 1, current, previous,
                candidates, best_score, time.monotonic() - start,
            )

        result.iterations_completed = min(
            len(result.fitness_trajectory), self.domain.max_iterations
        )
        result.best_fitness = best_score
        result.duration_seconds = time.monotonic() - start

        # Clean up checkpoint on completion
        if result.converged or result.interrupted:
            self._store.delete(self.domain.name, result.cycle_id)

        return result

    def _save_checkpoint(
        self,
        result: LoopResult,
        iteration: int,
        current: dict[str, Any] | None,
        previous: dict[str, Any] | None,
        candidates: list[dict[str, Any]],
        best_score: float,
        elapsed: float,
    ) -> None:
        """Save a checkpoint after an iteration. Fire-and-forget."""
        try:
            cp = LoopCheckpoint(
                domain=self.domain.name,
                cycle_id=result.cycle_id,
                iteration=iteration,
                current=current,
                previous=previous,
                candidates=candidates,
                best_score=best_score,
                fitness_trajectory=list(result.fitness_trajectory),
                eigenform_trajectory=list(result.eigenform_trajectory),
                elapsed_seconds=elapsed,
                converged=result.converged,
                interrupted=result.interrupted,
                interrupt_reason=result.interrupt_reason,
            )
            path = self._store.save(cp)
            logger.debug("Checkpoint saved: %s", path)
        except Exception as e:
            logger.warning("Failed to save checkpoint: %s", e)

    def _adjusted_mutation_rate(
        self, eigenform_trajectory: list[float]
    ) -> float:
        """Adjust mutation rate based on eigenform distance trend."""
        base = self.domain.mutation_rate
        if len(eigenform_trajectory) < 2:
            return base

        recent = eigenform_trajectory[-3:]
        avg_distance = sum(
            d for d in recent if d != float("inf")
        ) / max(1, sum(1 for d in recent if d != float("inf")))

        # Close to eigenform → reduce mutation
        if avg_distance < self.domain.eigenform_epsilon * 3:
            return base * 0.5
        # Far from eigenform → increase mutation
        if avg_distance > 1.0:
            return min(0.5, base * 1.5)
        return base


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def _variance(values: list[float]) -> float:
    """Population variance of a list of floats."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


def get_interrupt_gate() -> InterruptGate:
    """Return the module-level interrupt gate (for CLI/API to resolve interrupts)."""
    return _interrupt_gate


def get_checkpoint_store() -> CheckpointStore:
    """Return the module-level checkpoint store."""
    return _checkpoint_store


async def feedback_ascent(result: LoopResult) -> None:
    """Feed loop results back into the recognition seed — the strange loop.

    When a cascade domain completes, its results update the recognition seed
    so future agent context includes what the system learned. This is the
    ascent path: execution → synthesis → context → execution.

    Also emits a signal so other loops can feel the completion.
    """
    from pathlib import Path

    # 1. Emit signal to bus
    try:
        from dharma_swarm.signal_bus import SignalBus

        bus = SignalBus.get()
        bus.emit({
            "type": "CASCADE_COMPLETE",
            "domain": result.domain,
            "converged": result.converged,
            "best_fitness": result.best_fitness,
            "eigenform_reached": result.eigenform_reached,
            "iterations": result.iterations_completed,
        })
        if result.eigenform_reached:
            bus.emit({
                "type": "CASCADE_EIGENFORM_DISTANCE",
                "domain": result.domain,
                "distance": result.eigenform_trajectory[-1]
                if result.eigenform_trajectory else 0.0,
            })
    except Exception as e:
        logger.debug("Signal emission failed: %s", e)

    # 2. Append to cascade history for recognition engine to consume
    try:
        import json
        history_dir = Path.home() / ".dharma" / "meta"
        history_dir.mkdir(parents=True, exist_ok=True)
        history_file = history_dir / "cascade_history.jsonl"
        entry = {
            "domain": result.domain,
            "converged": result.converged,
            "best_fitness": result.best_fitness,
            "eigenform_reached": result.eigenform_reached,
            "iterations": result.iterations_completed,
            "duration": result.duration_seconds,
            "convergence_reason": result.convergence_reason,
            "timestamp": time.time(),
        }
        with open(history_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.debug("Cascade history write failed: %s", e)

    # 3. Write stigmergy mark for agent context (L8)
    try:
        from dharma_swarm.stigmergy import StigmergicMark, StigmergyStore

        store = StigmergyStore()
        status = "EIGENFORM" if result.eigenform_reached else ("CONVERGED" if result.converged else "INCOMPLETE")
        obs = f"cascade:{result.domain} fitness={result.best_fitness:.3f} {status} iter={result.iterations_completed}"
        # Deduplicate: skip if last mark for this domain has identical observation
        recent = await store.read_marks(file_path=f"cascade_domain_{result.domain}", limit=1)
        if recent and recent[0].observation == obs:
            logger.debug("Cascade mark deduplicated for domain %s", result.domain)
        else:
            mark = StigmergicMark(
                agent="cascade_engine",
                file_path=f"cascade_domain_{result.domain}",
                action="write",
                observation=obs,
                salience=0.7 if result.eigenform_reached else 0.5,
            )
            await store.leave_mark(mark)
    except Exception as e:
        logger.debug("Stigmergy mark failed: %s", e)


async def run_domain(
    domain_name: str,
    *,
    seed: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    resume: bool = True,
) -> LoopResult:
    """Convenience: load a domain by name and run it.

    If *resume* is True, resumes from the last checkpoint if one exists.
    Automatically calls feedback_ascent() on completion.
    """
    module_path = _DOMAIN_MODULES.get(domain_name)
    if not module_path:
        raise ValueError(
            f"Unknown domain: {domain_name!r}. "
            f"Available: {sorted(_DOMAIN_MODULES)}"
        )
    mod = importlib.import_module(module_path)
    domain = mod.get_domain(config)
    engine = LoopEngine(domain)
    result = await engine.run(seed, context=context, resume=resume)

    # Feed results back into the recognition seed (strange loop closure)
    await feedback_ascent(result)

    return result
