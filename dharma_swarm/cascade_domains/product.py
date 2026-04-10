"""PRODUCT domain — real cascade functions wired to foreman + elegance + metrics.

Scores product artifacts (projects, directories, individual files) on five
quality dimensions from foreman.py plus structural and behavioral analysis.
Generates concrete improvement tasks for the weakest dimension.

All functions are sync (cascade.py handles async via _call()).
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

from dharma_swarm.models import LoopDomain

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_domain(config: dict[str, Any] | None = None) -> LoopDomain:
    """Return the PRODUCT domain configuration."""
    cfg = config or {}
    return LoopDomain(
        name="product",
        generate_fn="dharma_swarm.cascade_domains.product.generate",
        test_fn="dharma_swarm.cascade_domains.product.test",
        score_fn="dharma_swarm.cascade_domains.product.score",
        gate_fn="dharma_swarm.cascade_domains.common.telos_gate",
        mutate_fn="dharma_swarm.cascade_domains.common.default_mutate",
        select_fn="dharma_swarm.cascade_domains.common.default_select",
        max_iterations=cfg.get("max_iterations", 20),
        fitness_threshold=cfg.get("fitness_threshold", 0.5),
    )


# ---------------------------------------------------------------------------
# GENERATE
# ---------------------------------------------------------------------------


def generate(seed: dict[str, Any] | None, context: dict[str, Any]) -> dict[str, Any]:
    """Generate a product artifact from seed or context.

    Supports two modes:
      1. Project mode: seed["project_path"] -> reads project directory, scores via foreman
      2. File mode:    seed["path"] -> reads a single file for product quality assessment

    Returns an artifact dict with: content, project_path, dimensions, fitness.
    """
    project_path: str | None = None
    content: str = ""
    dimensions: list[str] = ["usability", "reliability", "value", "documented", "tested"]

    if seed:
        project_path = seed.get("project_path") or seed.get("path")
        if seed.get("content"):
            content = seed["content"]
        elif project_path:
            content = _read_product_content(project_path)
        dimensions = seed.get("dimensions", dimensions)
    else:
        project_path = context.get("project_path") or context.get("path")
        if project_path:
            content = _read_product_content(project_path)

    return {
        "content": content,
        "project_path": project_path,
        "dimensions": dimensions,
        "fitness": {},
    }


def _read_product_content(path_str: str) -> str:
    """Read product content — either a single file or project summary."""
    try:
        p = Path(path_str)
        if not p.is_absolute():
            p = _PROJECT_ROOT / p

        if p.is_file():
            return p.read_text(encoding="utf-8")[:50000]

        if p.is_dir():
            # Collect a summary of the project: README + top-level Python files
            parts: list[str] = []
            readme = None
            for name in ("README.md", "README.rst", "README.txt", "README"):
                candidate = p / name
                if candidate.exists():
                    readme = candidate
                    break
            if readme:
                parts.append(readme.read_text(encoding="utf-8")[:5000])

            # Collect top-level Python files (up to 10)
            py_files = sorted(p.glob("*.py"))[:10]
            for pf in py_files:
                try:
                    parts.append(f"--- {pf.name} ---\n{pf.read_text(encoding='utf-8')[:3000]}")
                except (OSError, UnicodeDecodeError):
                    pass

            return "\n\n".join(parts) if parts else ""

        return ""
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Could not read product at %s: %s", path_str, exc)
        return ""


# ---------------------------------------------------------------------------
# TEST
# ---------------------------------------------------------------------------


def test(artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Test a product artifact: syntax check for Python, structure check for projects."""
    content = artifact.get("content", "")
    project_path = artifact.get("project_path")
    results: dict[str, Any] = {
        "has_content": bool(content and content.strip()),
        "has_readme": False,
        "syntax_valid": True,
        "test_suite_found": False,
        "status": "pass" if content else "fail",
    }

    if project_path:
        p = Path(project_path)
        if not p.is_absolute():
            p = _PROJECT_ROOT / p

        if p.is_dir():
            # Check for README
            for name in ("README.md", "README.rst", "README.txt"):
                if (p / name).exists():
                    results["has_readme"] = True
                    break

            # Check for test directory or test files
            tests_dir = p / "tests"
            if tests_dir.is_dir() and any(tests_dir.glob("test_*.py")):
                results["test_suite_found"] = True
            elif any(p.glob("test_*.py")):
                results["test_suite_found"] = True

            # Syntax check all Python files (excluding noise dirs)
            _skip_dirs = {".venv", "venv", "__pycache__", ".mypy_cache",
                          ".pytest_cache", "node_modules", ".tox", ".eggs"}
            py_files = [
                f for f in p.rglob("*.py")
                if not any(part in _skip_dirs for part in f.parts)
            ]
            syntax_errors = 0
            for pf in py_files[:50]:  # cap at 50 files
                try:
                    ast.parse(pf.read_text(encoding="utf-8"))
                except SyntaxError:
                    syntax_errors += 1
                except (OSError, UnicodeDecodeError):
                    pass
            results["syntax_valid"] = syntax_errors == 0
            results["syntax_errors"] = syntax_errors

        elif p.is_file() and p.suffix == ".py":
            try:
                ast.parse(content)
            except SyntaxError:
                results["syntax_valid"] = False

    if not results["has_content"]:
        results["status"] = "fail"
    elif not results["syntax_valid"]:
        results["status"] = "fail"

    artifact["test_passed"] = results["status"] == "pass"
    artifact["test_results"] = results
    return artifact


# ---------------------------------------------------------------------------
# SCORE
# ---------------------------------------------------------------------------


def score(artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Score a product artifact on five dimensions.

    Fitness components (weights sum to 1.0):
      - foreman_quality (0.30): foreman's 5-dimension scoring if project registered
      - elegance       (0.20): AST-based code quality from elegance.py
      - behavioral     (0.15): swabhaav_ratio + entropy + mimicry penalty
      - completeness   (0.20): README + tests + docs coverage
      - test_quality   (0.15): syntax valid + test suite present
    """
    content = artifact.get("content", "")
    project_path = artifact.get("project_path")
    test_results = artifact.get("test_results", {})

    # -- Foreman quality: project-level scoring --
    foreman_quality = 0.5  # neutral default
    foreman_dims: dict[str, float] = {}
    try:
        from dharma_swarm.foreman import ProjectEntry, score_all_dimensions

        if project_path:
            p = Path(project_path)
            if not p.is_absolute():
                p = _PROJECT_ROOT / p
            if p.is_dir():
                cache = context.setdefault("_product_foreman_cache", {})
                cache_key = str(p.resolve())
                cached_dims = cache.get(cache_key)
                if isinstance(cached_dims, dict):
                    foreman_dims = dict(cached_dims)
                else:
                    entry = ProjectEntry(
                        name=p.name,
                        path=str(p),
                        test_command=f"python3 -m pytest {p / 'tests'} -q --tb=line -x" if (p / "tests").is_dir() else None,
                    )
                    foreman_dims = score_all_dimensions(entry, skip_tests=True)
                    cache[cache_key] = dict(foreman_dims)
                foreman_quality = sum(foreman_dims.values()) / max(1, len(foreman_dims))
    except Exception as exc:
        logger.debug("Foreman scoring unavailable: %s", exc)

    # -- Elegance: AST-based code quality --
    elegance_val = 0.0
    try:
        from dharma_swarm.elegance import evaluate_elegance

        if content.strip():
            # Score the content if it looks like Python
            try:
                ast.parse(content[:20000])
                es = evaluate_elegance(content[:20000])
                elegance_val = es.overall
            except SyntaxError:
                # Not Python code — score based on length and structure
                lines = content.strip().split("\n")
                elegance_val = min(1.0, len(lines) / 100) * 0.5  # basic length credit
    except Exception as exc:
        logger.debug("Elegance scoring failed: %s", exc)

    # -- Behavioral: from MetricsAnalyzer --
    behavioral_val = 0.5
    try:
        from dharma_swarm.metrics import MetricsAnalyzer

        sig = MetricsAnalyzer().analyze(content[:10000])
        mimicry_penalty = 0.5 if sig.recognition_type.value == "MIMICRY" else 0.0
        behavioral_val = (
            0.4 * sig.swabhaav_ratio
            + 0.3 * sig.entropy
            + 0.3 * (1.0 - mimicry_penalty)
        )
    except Exception as exc:
        logger.debug("Behavioral scoring failed: %s", exc)

    # -- Completeness: structural quality --
    completeness = 0.0
    if test_results.get("has_content"):
        completeness += 0.3
    if test_results.get("has_readme"):
        completeness += 0.3
    if test_results.get("test_suite_found"):
        completeness += 0.25
    if test_results.get("syntax_valid", True):
        completeness += 0.15

    # -- Test quality --
    test_quality = 0.0
    if test_results.get("syntax_valid", True):
        test_quality += 0.5
    if test_results.get("test_suite_found"):
        test_quality += 0.5
    elif test_results.get("has_content"):
        test_quality += 0.2  # partial credit for having content at all

    # -- Composite --
    composite = (
        0.30 * foreman_quality
        + 0.20 * elegance_val
        + 0.15 * behavioral_val
        + 0.20 * completeness
        + 0.15 * test_quality
    )

    artifact["fitness"] = {
        "foreman_quality": round(foreman_quality, 4),
        "foreman_dimensions": foreman_dims,
        "elegance": round(elegance_val, 4),
        "behavioral": round(behavioral_val, 4),
        "completeness": round(completeness, 4),
        "test_quality": round(test_quality, 4),
        "score": round(composite, 4),
    }
    artifact["score"] = round(composite, 4)
    return artifact
