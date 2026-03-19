"""CODE domain -- real cascade functions wired to elegance + metrics.

Phase functions compose with (don't replace) the existing evolution pipeline.
Generate reads real files, test runs ast.parse + pytest, score uses
EleganceScore and BehavioralSignature, mutate flags for next iteration.

All functions are sync (cascade.py handles async via _call()).
"""

from __future__ import annotations

import ast
import logging
import subprocess
from pathlib import Path
from typing import Any

from dharma_swarm.models import LoopDomain

logger = logging.getLogger(__name__)

# Project root -- used to resolve relative paths and find test files
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_domain(config: dict[str, Any] | None = None) -> LoopDomain:
    """Return the CODE domain configuration."""
    cfg = config or {}
    return LoopDomain(
        name="code",
        generate_fn="dharma_swarm.cascade_domains.code.generate",
        test_fn="dharma_swarm.cascade_domains.code.test",
        score_fn="dharma_swarm.cascade_domains.code.score",
        gate_fn="dharma_swarm.cascade_domains.common.telos_gate",
        mutate_fn="dharma_swarm.cascade_domains.code.mutate",
        select_fn="dharma_swarm.cascade_domains.common.default_select",
        eigenform_fn="dharma_swarm.cascade_domains.common.default_eigenform",
        max_iterations=cfg.get("max_iterations", 30),
        fitness_threshold=cfg.get("fitness_threshold", 0.6),
        mutation_rate=cfg.get("mutation_rate", 1.0),
        convergence_window=cfg.get("convergence_window", 8),
        eigenform_epsilon=cfg.get("eigenform_epsilon", 0.005),
    )


# ---------------------------------------------------------------------------
# GENERATE
# ---------------------------------------------------------------------------


def generate(seed: dict[str, Any] | None, context: dict[str, Any]) -> dict[str, Any]:
    """Generate a code artifact from seed or context.

    Resolution order for content:
      1. seed["content"] -- inline code string
      2. seed["path"]    -- read from filesystem
      3. context["path"] -- read from filesystem
      4. context["component"] -- bare component name, no file read
      5. FALLBACK: pick a random module from dharma_swarm/ to score

    Returns an artifact dict with: content, path, component, change_type, fitness.
    """
    content: str = ""
    path: str | None = None
    component: str = "unknown"
    change_type: str = "proposal"

    if seed:
        # Carry forward any existing metadata
        change_type = seed.get("change_type", change_type)
        component = seed.get("component", component)
        path = seed.get("path")

        if "content" in seed and seed["content"]:
            content = seed["content"]
        elif path:
            content = _read_file(path)
    else:
        path = context.get("path")
        component = context.get("component", component)

        if path:
            content = _read_file(path)

    # FALLBACK: if still no content, pick a real module to score
    if not content or not content.strip():
        path, content = _pick_random_module()
        if path:
            component = Path(path).stem
            change_type = "audit"

    # Derive component from path if still unknown
    if component == "unknown" and path:
        component = Path(path).stem

    return {
        "content": content,
        "path": path,
        "component": component,
        "change_type": change_type,
        "fitness": {},
    }


def _pick_random_module() -> tuple[str | None, str]:
    """Pick a random Python module from dharma_swarm/ to score.

    Returns (path, content). Falls back to ("", "") if nothing found.
    """
    import random

    pkg_dir = _PROJECT_ROOT / "dharma_swarm"
    candidates = [
        p for p in pkg_dir.glob("*.py")
        if p.stem != "__init__" and p.stat().st_size > 200
    ]
    if not candidates:
        return None, ""
    chosen = random.choice(candidates)
    try:
        return str(chosen), chosen.read_text(encoding="utf-8")
    except Exception:
        return None, ""


def _read_file(path: str) -> str:
    """Read a file, returning empty string on failure."""
    try:
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = _PROJECT_ROOT / resolved
        return resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return ""


# ---------------------------------------------------------------------------
# TEST
# ---------------------------------------------------------------------------


def test(artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Test a code artifact: syntax check via ast.parse, then pytest if available.

    Sets artifact["test_passed"], artifact["test_results"].
    """
    content = artifact.get("content", "")
    results: dict[str, Any] = {
        "syntax_valid": False,
        "pytest_ran": False,
        "pytest_passed": False,
        "pytest_exit_code": None,
        "pytest_output": "",
        "status": "fail",
    }

    # Step 1: AST syntax check
    if not content or not content.strip():
        results["status"] = "fail"
        results["error"] = "empty content"
        artifact["test_passed"] = False
        artifact["test_results"] = results
        return artifact

    try:
        ast.parse(content)
        results["syntax_valid"] = True
    except SyntaxError as exc:
        results["status"] = "fail"
        results["error"] = f"SyntaxError: {exc.msg} (line {exc.lineno})"
        artifact["test_passed"] = False
        artifact["test_results"] = results
        return artifact

    # Step 2: Find and run pytest for the file
    file_path = artifact.get("path")
    test_file = _find_test_file(file_path) if file_path else None

    if test_file and test_file.exists():
        results["pytest_ran"] = True
        try:
            proc = subprocess.run(
                ["python3", "-m", "pytest", str(test_file), "-q", "--tb=line", "-x"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(_PROJECT_ROOT),
            )
            results["pytest_exit_code"] = proc.returncode
            results["pytest_output"] = (proc.stdout + proc.stderr)[-2000:]
            results["pytest_passed"] = proc.returncode == 0

            if proc.returncode != 0:
                results["status"] = "fail"
                artifact["test_passed"] = False
                artifact["test_results"] = results
                return artifact

        except subprocess.TimeoutExpired:
            results["pytest_exit_code"] = -1
            results["pytest_output"] = "pytest timed out (30s)"
            results["status"] = "timeout"
            artifact["test_passed"] = False
            artifact["test_results"] = results
            return artifact
        except FileNotFoundError:
            # python3 not found -- skip pytest, rely on syntax check
            results["pytest_ran"] = False
            logger.debug("python3 not found, skipping pytest")

    # If we got here: syntax valid, and either no pytest or pytest passed
    results["status"] = "pass"
    artifact["test_passed"] = True
    artifact["test_results"] = results
    return artifact


def _find_test_file(file_path: str) -> Path | None:
    """Find the corresponding test file for a source file.

    Looks for tests/test_<stem>.py relative to project root.
    """
    try:
        source = Path(file_path)
        stem = source.stem
        # Standard convention: tests/test_<module>.py
        test_path = _PROJECT_ROOT / "tests" / f"test_{stem}.py"
        if test_path.exists():
            return test_path
        # Also check for tests in the same directory
        sibling = source.parent / f"test_{stem}.py"
        if sibling.exists():
            return sibling
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# SCORE
# ---------------------------------------------------------------------------


def score(artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Score a code artifact using elegance + behavioral metrics.

    Fitness components (weights sum to 1.0):
      - correctness (0.35): binary pass/fail from test phase
      - elegance    (0.30): AST-based code quality from elegance.py
      - behavioral  (0.20): swabhaav_ratio + entropy + mimicry penalty
      - test_detail (0.15): granular test quality (syntax + pytest)
    """
    content = artifact.get("content", "")
    test_passed = artifact.get("test_passed", False)
    test_results = artifact.get("test_results", {})

    # -- Correctness: binary from test phase --
    correctness = 1.0 if test_passed else 0.0

    # -- Elegance: from AST analysis --
    elegance_val = 0.0
    try:
        from dharma_swarm.elegance import evaluate_elegance

        elegance_score = evaluate_elegance(content)
        elegance_val = elegance_score.overall
    except Exception as exc:
        logger.warning("Elegance scoring failed: %s", exc)

    # -- Behavioral: from MetricsAnalyzer --
    behavioral_val = 0.5  # neutral default
    recognition_type = "NONE"
    swabhaav_ratio = 0.5
    entropy = 0.0
    complexity = 0.0
    try:
        from dharma_swarm.metrics import MetricsAnalyzer

        analyzer = MetricsAnalyzer()
        sig = analyzer.analyze(content)
        swabhaav_ratio = sig.swabhaav_ratio
        entropy = sig.entropy
        complexity = sig.complexity
        recognition_type = sig.recognition_type.value

        # Mimicry penalty: 0.5 if flagged as MIMICRY, else 0.0
        mimicry_penalty = 0.5 if recognition_type == "MIMICRY" else 0.0

        # Normalize entropy (already 0-1 from analyzer)
        normalized_entropy = entropy

        # Behavioral = weighted combination
        behavioral_val = (
            0.4 * swabhaav_ratio
            + 0.3 * normalized_entropy
            + 0.3 * (1.0 - mimicry_penalty)
        )
    except Exception as exc:
        logger.warning("Behavioral scoring failed: %s", exc)

    # -- Test detail: granular quality from test results --
    test_detail = 0.0
    if test_results.get("syntax_valid"):
        test_detail += 0.5
    if test_results.get("pytest_passed"):
        test_detail += 0.5
    elif not test_results.get("pytest_ran"):
        # No pytest available -- give partial credit for syntax alone
        test_detail += 0.25

    # -- Composite fitness score --
    composite = (
        0.35 * correctness
        + 0.30 * elegance_val
        + 0.20 * behavioral_val
        + 0.15 * test_detail
    )

    artifact["fitness"] = {
        "correctness": round(correctness, 4),
        "elegance": round(elegance_val, 4),
        "behavioral": round(behavioral_val, 4),
        "test_detail": round(test_detail, 4),
        "score": round(composite, 4),
        # Sub-metrics for introspection
        "swabhaav_ratio": round(swabhaav_ratio, 4),
        "entropy": round(entropy, 4),
        "complexity": round(complexity, 4),
        "recognition_type": recognition_type,
    }
    artifact["score"] = round(composite, 4)
    return artifact


# ---------------------------------------------------------------------------
# MUTATE
# ---------------------------------------------------------------------------


def mutate(
    artifact: dict[str, Any],
    context: dict[str, Any],
    mutation_rate: float = 0.1,
) -> dict[str, Any]:
    """Mutate a code artifact by picking a different file to score.

    At the current stage (no LLM rewriting), mutation means selecting a
    different module from the codebase. This gives the cascade real variation
    across iterations instead of scoring the same file repeatedly.
    """
    import random

    mutated = dict(artifact)
    mutated["metadata"] = mutated.get("metadata", {})
    mutated["metadata"]["mutated"] = True
    mutated["metadata"]["mutation_rate"] = mutation_rate
    mutated["metadata"]["generation"] = mutated["metadata"].get("generation", 0) + 1

    # With probability = mutation_rate, pick a different file
    if random.random() < mutation_rate:
        new_path, new_content = _pick_random_module()
        if new_path and new_path != mutated.get("path"):
            mutated["content"] = new_content
            mutated["path"] = new_path
            mutated["component"] = Path(new_path).stem
            mutated["change_type"] = "mutation"
            # Reset fitness so it gets re-scored
            mutated["fitness"] = {}
            mutated.pop("score", None)
            mutated.pop("test_passed", None)
            mutated.pop("test_results", None)

    return mutated
