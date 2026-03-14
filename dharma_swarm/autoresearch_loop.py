"""AutoResearch Loop -- Karpathy-style self-improvement for dharma_swarm.

Points the Darwin Engine at dharma_swarm's own modules.

IMMUTABLE (eval function, cannot be modified):
  - tests/ (2327 tests -- the fitness function)
  - models.py (schema contract)
  - telos_gates.py (ethical constraints)

MUTABLE (genome, can be evolved):
  - providers.py, context.py, orchestrator.py, agent_runner.py, etc.
  - Any module not in IMMUTABLE set

DIRECTION (human intent):
  - CLAUDE.md, .FOCUS file
  - Priorities from Dhyana

THE LOOP:
  1. Select a module to improve (round-robin or priority-weighted)
  2. Read current module + its test results
  3. Propose improvement via Darwin Engine
  4. Gate check (telos)
  5. Run tests (2327 must still pass)
  6. Score elegance + fitness
  7. If fitness > threshold: keep. Otherwise: revert.
  8. Log to evolution archive with lineage.
  9. Sleep, repeat.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from dharma_swarm.archive import ArchiveEntry, EvolutionArchive, FitnessScore
from dharma_swarm.elegance import evaluate_elegance
from dharma_swarm.evolution import DarwinEngine, EvolutionStatus, Proposal
from dharma_swarm.models import LLMRequest, LLMResponse, ProviderType, _new_id, _utc_now
from dharma_swarm.traces import TraceEntry, TraceStore

logger = logging.getLogger(__name__)

HOME = Path.home()
DHARMA_SWARM_SRC = HOME / "dharma_swarm" / "dharma_swarm"
DHARMA_SWARM_ROOT = HOME / "dharma_swarm"

# Files that MUST NOT be modified by the loop
IMMUTABLE_FILES: frozenset[str] = frozenset({
    "models.py",
    "telos_gates.py",
    "__init__.py",
    "autoresearch_loop.py",  # the loop cannot modify itself
})

# Directories within dharma_swarm/ whose files are also immutable
IMMUTABLE_DIRS: frozenset[str] = frozenset({
    "hooks",
})

# Maximum source file size (lines) before we penalize fitness
_MAX_SANE_LINES: int = 800


def get_mutable_modules() -> list[Path]:
    """Return list of Python modules that can be evolved.

    Scans DHARMA_SWARM_SRC for .py files, excluding anything in
    IMMUTABLE_FILES or IMMUTABLE_DIRS. Results are sorted by name
    for deterministic round-robin ordering.
    """
    if not DHARMA_SWARM_SRC.is_dir():
        return []

    mutable: list[Path] = []
    for py_file in sorted(DHARMA_SWARM_SRC.rglob("*.py")):
        # Skip immutable filenames
        if py_file.name in IMMUTABLE_FILES:
            continue
        # Skip files inside immutable directories
        try:
            relative = py_file.relative_to(DHARMA_SWARM_SRC)
        except ValueError:
            continue
        if any(part in IMMUTABLE_DIRS for part in relative.parts):
            continue
        # Skip empty or near-empty stub files
        try:
            if py_file.stat().st_size < 50:
                continue
        except OSError:
            continue
        mutable.append(py_file)

    return mutable


class LoopConfig(BaseModel):
    """Configuration for the AutoResearch loop."""

    fitness_threshold: float = 0.6
    max_iterations: int = 10
    sleep_between_sec: float = 30.0
    test_timeout_sec: float = 300.0
    target_modules: list[str] = Field(default_factory=list)  # empty = all mutable
    dry_run: bool = False


class IterationResult(BaseModel):
    """Result of a single loop iteration."""

    iteration: int
    module: str
    proposal_id: str = ""
    description: str = ""
    fitness: float = 0.0
    accepted: bool = False
    test_passed: bool = False
    error: str = ""
    duration_sec: float = 0.0


class AutoResearchLoop:
    """Karpathy-style self-improvement loop for dharma_swarm.

    Each iteration selects a mutable module, measures its current fitness
    (test pass rate + elegance + size sanity), and logs the result to the
    evolution archive. The Darwin Engine integration for actual proposal
    generation requires an LLM provider; this class provides the
    measurement, gating, and logging framework that wraps it.

    Usage::

        loop = AutoResearchLoop(LoopConfig(max_iterations=5, dry_run=True))
        results = await loop.run()
        print(loop.report())
    """

    def __init__(self, config: LoopConfig | None = None) -> None:
        self.config = config or LoopConfig()
        self._iteration: int = 0
        self._results: list[IterationResult] = []
        self._mutable: list[Path] = []
        self._archive = EvolutionArchive()
        self._traces = TraceStore()
        self._backup: tuple[Path, str] | None = None

    # ------------------------------------------------------------------
    # Fuzzy text replacement
    # ------------------------------------------------------------------

    @staticmethod
    def _fuzzy_replace(source: str, find: str, replace: str) -> str | None:
        """Replace *find* in *source* with *replace*, using fuzzy matching.

        Tries in order:
          1. Exact substring match
          2. Right-stripped lines match
          3. Sliding window over source lines looking for best match

        Returns the modified source, or None if no match found.
        """
        # 1. Exact match
        if find in source:
            return source.replace(find, replace, 1)

        # Normalize both sides
        find_lines = [line.rstrip() for line in find.splitlines()]
        source_lines = [line.rstrip() for line in source.splitlines()]

        # 2. Stripped match
        find_joined = "\n".join(find_lines)
        source_joined = "\n".join(source_lines)
        if find_joined in source_joined:
            result = source_joined.replace(find_joined, replace.rstrip("\n"), 1)
            return result

        # 3. Sliding window: find best contiguous match
        find_count = len(find_lines)
        if find_count == 0 or find_count > len(source_lines):
            return None

        best_score = 0.0
        best_start = -1

        for start in range(len(source_lines) - find_count + 1):
            window = source_lines[start : start + find_count]
            # Score: fraction of lines that match (stripped)
            matches = sum(
                1 for a, b in zip(window, find_lines) if a.strip() == b.strip()
            )
            score = matches / find_count
            if score > best_score:
                best_score = score
                best_start = start

        # Require >= 80% line match
        if best_score >= 0.8 and best_start >= 0:
            # Reconstruct with original lines outside the window
            replace_lines = replace.rstrip("\n").splitlines()
            result_lines = (
                source_lines[:best_start]
                + replace_lines
                + source_lines[best_start + find_count :]
            )
            return "\n".join(result_lines)

        return None

    # ------------------------------------------------------------------
    # Module selection
    # ------------------------------------------------------------------

    def _resolve_mutable(self) -> list[Path]:
        """Build or return cached list of mutable modules, filtered by config."""
        if not self._mutable:
            all_mutable = get_mutable_modules()
            if self.config.target_modules:
                targets = set(self.config.target_modules)
                self._mutable = [
                    p for p in all_mutable if p.name in targets or p.stem in targets
                ]
            else:
                self._mutable = all_mutable
        return self._mutable

    def _select_module(self) -> Path:
        """Select next module to improve via round-robin.

        Raises:
            RuntimeError: If no mutable modules are available.
        """
        modules = self._resolve_mutable()
        if not modules:
            raise RuntimeError(
                "No mutable modules found. Check DHARMA_SWARM_SRC path "
                f"({DHARMA_SWARM_SRC}) and target_modules config."
            )
        idx = self._iteration % len(modules)
        return modules[idx]

    # ------------------------------------------------------------------
    # Context reading
    # ------------------------------------------------------------------

    def _read_module_context(self, module_path: Path) -> str:
        """Read the module source code and any related test file.

        Returns a formatted context string containing the source and, if
        found, the corresponding test file contents.
        """
        parts: list[str] = []

        # Read the module source
        try:
            source = module_path.read_text(encoding="utf-8")
            parts.append(f"=== {module_path.name} ({len(source.splitlines())} lines) ===")
            parts.append(source)
        except OSError as exc:
            parts.append(f"=== ERROR reading {module_path.name}: {exc} ===")
            return "\n".join(parts)

        # Look for corresponding test file
        test_name = f"test_{module_path.stem}.py"
        test_path = DHARMA_SWARM_ROOT / "tests" / test_name
        if test_path.is_file():
            try:
                test_source = test_path.read_text(encoding="utf-8")
                parts.append(f"\n=== {test_name} ({len(test_source.splitlines())} lines) ===")
                parts.append(test_source)
            except OSError:
                parts.append(f"\n=== Could not read {test_name} ===")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Test execution
    # ------------------------------------------------------------------

    def _run_tests(self) -> tuple[bool, str]:
        """Run the test suite via subprocess.

        Executes ``python -m pytest tests/ -x -q --timeout=60`` from the
        dharma_swarm root directory. Respects ``self.config.test_timeout_sec``
        for the overall subprocess timeout.

        Returns:
            Tuple of (all_passed, output_summary). The summary is truncated
            to the last 40 lines to keep logs manageable.
        """
        cmd = [
            "python", "-m", "pytest",
            "tests/",
            "-x",           # stop on first failure
            "-q",           # quiet output
            "--timeout=60", # per-test timeout
            "--tb=short",   # short tracebacks
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=str(DHARMA_SWARM_ROOT),
                capture_output=True,
                text=True,
                timeout=self.config.test_timeout_sec,
            )
            output = result.stdout + result.stderr
            # Truncate to last 40 lines for summary
            lines = output.strip().splitlines()
            summary = "\n".join(lines[-40:]) if len(lines) > 40 else output.strip()
            return result.returncode == 0, summary

        except subprocess.TimeoutExpired:
            return False, f"Test suite timed out after {self.config.test_timeout_sec}s"
        except FileNotFoundError:
            return False, "pytest not found -- is the virtual environment active?"
        except OSError as exc:
            return False, f"Failed to run tests: {exc}"

    # ------------------------------------------------------------------
    # Fitness computation
    # ------------------------------------------------------------------

    def _compute_fitness(self, module_path: Path, test_passed: bool) -> float:
        """Compute fitness score for the current state of a module.

        Combines three signals with fixed weights:
          - test_pass_rate (0.5): 1.0 if all tests pass, 0.0 otherwise
          - elegance (0.3): AST-based code quality from evaluate_elegance()
          - size_sanity (0.2): penalizes files over _MAX_SANE_LINES

        Returns:
            A float in [0.0, 1.0].
        """
        test_score = 1.0 if test_passed else 0.0

        # Elegance scoring
        elegance_score = 0.0
        try:
            source = module_path.read_text(encoding="utf-8")
            elegance = evaluate_elegance(source)
            elegance_score = elegance.overall
        except OSError:
            logger.warning("Could not read %s for elegance scoring", module_path)
        except Exception as exc:
            logger.warning("Elegance evaluation failed for %s: %s", module_path.name, exc)

        # Size sanity: linear penalty for files exceeding _MAX_SANE_LINES
        size_score = 1.0
        try:
            line_count = len(module_path.read_text(encoding="utf-8").splitlines())
            if line_count > _MAX_SANE_LINES:
                # Score drops linearly, hitting 0.0 at 2x the limit
                size_score = max(0.0, 1.0 - (line_count - _MAX_SANE_LINES) / _MAX_SANE_LINES)
        except OSError:
            size_score = 0.5  # unknown size gets neutral score

        fitness = (0.5 * test_score) + (0.3 * elegance_score) + (0.2 * size_score)
        return round(fitness, 4)

    # ------------------------------------------------------------------
    # Iteration
    # ------------------------------------------------------------------

    async def _propose_improvement(self, module_path: Path, context: str, fitness: float) -> str | None:
        """Ask an LLM to propose an improvement diff for the module.

        Returns a unified diff string, or None if no provider is available
        or the LLM declines to propose changes.
        """
        try:
            from dharma_swarm.providers import create_default_router
        except Exception:
            return None

        router = create_default_router()

        system_prompt = (
            "You are an expert Python developer improving modules in the dharma_swarm project.\n"
            "You will be given a module's source code and its test file.\n"
            "Propose ONE small, focused improvement: a bug fix, performance gain, or clarity improvement.\n"
            "Do NOT change function signatures or public APIs.\n"
            "Do NOT add unnecessary comments, docstrings, or type annotations.\n"
            "Do NOT rewrite the whole file — only change the specific lines that need improvement.\n\n"
            "Output format:\n"
            "DESCRIPTION: one-line summary of the change\n"
            "FIND:\n```\nexact lines to replace (copy-paste from source)\n```\n"
            "REPLACE:\n```\nimproved lines\n```\n\n"
            "If the module is already clean, respond with exactly: NO_CHANGE"
        )

        user_prompt = (
            f"Module: {module_path.name}\n"
            f"Current fitness: {fitness:.4f}\n\n"
            f"{context}\n\n"
            f"Propose one improvement using FIND/REPLACE format, or NO_CHANGE if none needed."
        )

        # Truncate context to fit in a reasonable token budget
        if len(user_prompt) > 12000:
            user_prompt = user_prompt[:12000] + "\n... (truncated)"

        request = LLMRequest(
            model="meta-llama/llama-3.3-70b-instruct",
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt,
            max_tokens=2048,
            temperature=0.3,
        )

        try:
            # Try OpenRouter free tier first, then paid
            for provider_type in (ProviderType.OPENROUTER_FREE, ProviderType.OPENROUTER):
                provider = router._providers.get(provider_type)
                if provider is None:
                    continue
                try:
                    response: LLMResponse = await provider.complete(request)
                    content = response.content.strip()
                    if "NO_CHANGE" in content[:50]:
                        logger.info("LLM declined to propose changes for %s", module_path.name)
                        return None
                    if "FIND:" in content and "REPLACE:" in content:
                        return content
                    logger.debug("LLM response not in FIND/REPLACE format for %s", module_path.name)
                    return None
                except Exception as exc:
                    logger.debug("Provider %s failed: %s", provider_type, exc)
                    continue
        except Exception as exc:
            logger.debug("Proposal generation failed: %s", exc)

        return None

    async def _apply_diff(self, module_path: Path, llm_response: str) -> bool:
        """Parse FIND/REPLACE from LLM response and apply to module.

        Returns True on success.
        """
        import re

        try:
            source = module_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Cannot read %s: %s", module_path.name, exc)
            return False

        # Extract FIND and REPLACE blocks from fenced code blocks
        find_match = re.search(r"FIND:\s*```[^\n]*\n(.*?)```", llm_response, re.DOTALL)
        replace_match = re.search(r"REPLACE:\s*```[^\n]*\n(.*?)```", llm_response, re.DOTALL)

        if not find_match or not replace_match:
            logger.warning("Could not parse FIND/REPLACE blocks from LLM response")
            return False

        find_text = find_match.group(1)
        replace_text = replace_match.group(1)

        # Strip trailing newline from both (code blocks often add one)
        find_text = find_text.rstrip("\n")
        replace_text = replace_text.rstrip("\n")

        new_source = self._fuzzy_replace(source, find_text, replace_text)
        if new_source is None:
            logger.warning(
                "FIND block not found in %s (tried exact, stripped, and fuzzy)",
                module_path.name,
            )
            return False

        # Safety: don't apply if replacement is identical or empties the file
        if new_source == source:
            logger.info("FIND/REPLACE produced identical source for %s", module_path.name)
            return False
        if len(new_source.strip()) < 10:
            logger.warning("Replacement would empty %s — refusing", module_path.name)
            return False

        # Write the modified source
        try:
            # Backup original
            self._backup = (module_path, source)
            module_path.write_text(new_source, encoding="utf-8")
            logger.info("Applied FIND/REPLACE to %s", module_path.name)
            return True
        except OSError as exc:
            logger.warning("Failed to write %s: %s", module_path.name, exc)
            return False

    async def _revert_module(self, module_path: Path) -> None:
        """Revert the module to its pre-modification state."""
        if self._backup and self._backup[0] == module_path:
            try:
                module_path.write_text(self._backup[1], encoding="utf-8")
                self._backup = None
                return
            except OSError:
                pass
        # Fallback: git checkout
        try:
            subprocess.run(
                ["git", "checkout", "HEAD", "--", str(module_path)],
                cwd=str(DHARMA_SWARM_ROOT),
                capture_output=True,
                timeout=10,
            )
        except Exception as exc:
            logger.error("Failed to revert %s: %s", module_path.name, exc)

    async def run_iteration(self) -> IterationResult:
        """Run a single iteration of the AutoResearch loop.

        Steps:
          1. Select module (round-robin through mutable set)
          2. Read module context (source + tests)
          3. Run tests to establish baseline fitness
          4. Propose improvement via LLM (if not dry_run)
          5. Apply diff, re-test, compare fitness
          6. Keep if improved, revert if not
          7. Log to trace store and archive
        """
        start = time.monotonic()
        self._iteration += 1
        iteration_num = self._iteration

        result = IterationResult(iteration=iteration_num, module="")

        try:
            # 1. Select module
            module_path = self._select_module()
            result.module = module_path.name
            logger.info(
                "Iteration %d: selected %s", iteration_num, module_path.name
            )

            # 2. Read context
            context = self._read_module_context(module_path)

            # 3. Baseline fitness
            if self.config.dry_run:
                baseline_passed = True
            else:
                baseline_passed, _ = await asyncio.to_thread(self._run_tests)
            baseline_fitness = self._compute_fitness(module_path, baseline_passed)

            result.test_passed = baseline_passed
            result.fitness = baseline_fitness

            # 4. Propose improvement via LLM
            diff_text: str | None = None
            if not self.config.dry_run:
                diff_text = await self._propose_improvement(
                    module_path, context, baseline_fitness
                )

            if diff_text is None:
                # No proposal — log baseline measurement only
                result.description = (
                    f"Baseline: {module_path.name} fitness={baseline_fitness:.4f}, "
                    f"no improvement proposed"
                )
                result.accepted = baseline_fitness >= self.config.fitness_threshold
            else:
                # 5. Apply diff and re-test
                result.proposal_id = _new_id()
                applied = await self._apply_diff(module_path, diff_text)

                if applied:
                    # 6. Re-test after applying diff
                    new_passed, test_summary = await asyncio.to_thread(self._run_tests)
                    new_fitness = self._compute_fitness(module_path, new_passed)

                    if new_passed and new_fitness > baseline_fitness:
                        # KEEP — improvement accepted
                        result.fitness = new_fitness
                        result.test_passed = True
                        result.accepted = True
                        result.description = (
                            f"IMPROVED {module_path.name}: "
                            f"{baseline_fitness:.4f} -> {new_fitness:.4f}"
                        )
                        logger.info(
                            "Iteration %d: ACCEPTED improvement for %s "
                            "(%.4f -> %.4f)",
                            iteration_num, module_path.name,
                            baseline_fitness, new_fitness,
                        )

                        # Archive the improvement
                        try:
                            entry = ArchiveEntry(
                                component=module_path.name,
                                change_type="mutation",
                                description=result.description,
                                fitness=FitnessScore(
                                    correctness=1.0 if new_passed else 0.0,
                                    elegance=new_fitness,
                                ),
                            )
                            await self._archive.add_entry(entry)
                        except Exception:
                            pass
                    else:
                        # REVERT — tests failed or fitness decreased
                        await self._revert_module(module_path)
                        result.fitness = baseline_fitness
                        result.test_passed = baseline_passed
                        result.accepted = False
                        reason = "tests failed" if not new_passed else "fitness decreased"
                        result.description = (
                            f"REVERTED {module_path.name}: {reason} "
                            f"(baseline={baseline_fitness:.4f}, "
                            f"proposed={new_fitness:.4f})"
                        )
                        logger.info(
                            "Iteration %d: REVERTED %s (%s)",
                            iteration_num, module_path.name, reason,
                        )
                else:
                    result.description = (
                        f"Diff failed to apply to {module_path.name}"
                    )
                    result.accepted = False

            # 7. Log trace
            try:
                await self._traces.init()
                trace = TraceEntry(
                    agent="autoresearch_loop",
                    action="iteration_complete",
                    metadata={
                        "iteration": iteration_num,
                        "module": module_path.name,
                        "fitness": result.fitness,
                        "test_passed": result.test_passed,
                        "accepted": result.accepted,
                        "had_proposal": diff_text is not None,
                    },
                )
                await self._traces.log_entry(trace)
            except Exception as exc:
                logger.debug("Trace logging failed (non-fatal): %s", exc)

        except RuntimeError as exc:
            result.error = str(exc)
            logger.error("Iteration %d failed: %s", iteration_num, exc)
        except Exception as exc:
            result.error = f"Unexpected error: {exc}"
            logger.error("Iteration %d unexpected error: %s", iteration_num, exc)

        result.duration_sec = round(time.monotonic() - start, 2)
        self._results.append(result)
        return result

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self) -> list[IterationResult]:
        """Run the full AutoResearch loop for max_iterations.

        Each iteration: select module -> measure fitness -> log result.
        Sleeps between iterations (configurable). Returns all results.
        """
        logger.info(
            "AutoResearch loop starting: max_iterations=%d, threshold=%.2f, dry_run=%s",
            self.config.max_iterations,
            self.config.fitness_threshold,
            self.config.dry_run,
        )

        for i in range(self.config.max_iterations):
            result = await self.run_iteration()

            logger.info(
                "Iteration %d/%d: %s fitness=%.4f accepted=%s (%.1fs)",
                result.iteration,
                self.config.max_iterations,
                result.module,
                result.fitness,
                result.accepted,
                result.duration_sec,
            )

            # Sleep between iterations (skip after the last one)
            if i < self.config.max_iterations - 1 and self.config.sleep_between_sec > 0:
                await asyncio.sleep(self.config.sleep_between_sec)

        logger.info("AutoResearch loop complete: %d iterations", len(self._results))
        return self._results

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def report(self) -> str:
        """Generate a human-readable report of loop results.

        Shows: total iterations, modules touched, accepted/rejected counts,
        average fitness, per-module breakdown, and any errors encountered.
        """
        if not self._results:
            return "AutoResearch Loop: no iterations run."

        total = len(self._results)
        accepted = sum(1 for r in self._results if r.accepted)
        rejected = total - accepted
        errors = [r for r in self._results if r.error]
        test_failures = sum(1 for r in self._results if not r.test_passed and not r.error)

        fitnesses = [r.fitness for r in self._results if not r.error]
        avg_fitness = sum(fitnesses) / len(fitnesses) if fitnesses else 0.0
        min_fitness = min(fitnesses) if fitnesses else 0.0
        max_fitness = max(fitnesses) if fitnesses else 0.0

        # Per-module stats
        module_fitness: dict[str, list[float]] = {}
        for r in self._results:
            if not r.error:
                module_fitness.setdefault(r.module, []).append(r.fitness)

        lines: list[str] = [
            "=" * 60,
            "AUTORESEARCH LOOP REPORT",
            "=" * 60,
            f"Iterations:      {total}",
            f"Accepted:        {accepted} (>= {self.config.fitness_threshold:.2f} threshold)",
            f"Rejected:        {rejected}",
            f"Test failures:   {test_failures}",
            f"Errors:          {len(errors)}",
            f"Avg fitness:     {avg_fitness:.4f}",
            f"Min fitness:     {min_fitness:.4f}",
            f"Max fitness:     {max_fitness:.4f}",
            f"Dry run:         {self.config.dry_run}",
            "",
            "--- Per-Module Breakdown ---",
        ]

        for module_name in sorted(module_fitness):
            scores = module_fitness[module_name]
            avg = sum(scores) / len(scores)
            lines.append(f"  {module_name:<35s}  avg={avg:.4f}  n={len(scores)}")

        if errors:
            lines.append("")
            lines.append("--- Errors ---")
            for r in errors:
                lines.append(f"  Iteration {r.iteration}: {r.error}")

        lines.append("=" * 60)
        return "\n".join(lines)
