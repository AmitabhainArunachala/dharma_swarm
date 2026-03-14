"""Foreman — Focused Quality Forge.

Not a portfolio manager. A tireless quality hammer for a small set of projects.
Each cycle: SCAN → FIND WEAKEST → IMPROVE → VALIDATE → RECORD.

One dimension per cycle per project. 200 iterations of that = diamond.

Storage: ~/.dharma/foreman/projects.json, ~/.dharma/foreman/cycles.jsonl
"""

from __future__ import annotations

import ast
import json
import logging
import os
import shlex
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────

DHARMA_DIR = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma"))
FOREMAN_DIR = DHARMA_DIR / "foreman"
PROJECTS_FILE = FOREMAN_DIR / "projects.json"
CYCLES_FILE = FOREMAN_DIR / "cycles.jsonl"
HISTORY_FILE = FOREMAN_DIR / "history.jsonl"

QUALITY_DIMENSIONS = [
    "has_tests",
    "tests_pass",
    "error_handling",
    "documented",
    "edge_cases_covered",
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _ensure_dirs() -> None:
    FOREMAN_DIR.mkdir(parents=True, exist_ok=True)


# ── Project Registry ─────────────────────────────────────────────────


class ProjectEntry(BaseModel):
    """A project tracked by the Foreman."""

    name: str
    path: str
    test_command: str | None = None
    exclude: list[str] = Field(default_factory=list)
    active: bool = True
    last_scan: str | None = None
    last_grade: str | None = None
    last_score: float | None = None
    dimensions: dict[str, float | None] = Field(default_factory=dict)


def load_projects() -> list[ProjectEntry]:
    """Load the project registry."""
    _ensure_dirs()
    if not PROJECTS_FILE.exists():
        return []
    try:
        with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [ProjectEntry(**p) for p in data.get("projects", [])]
    except (json.JSONDecodeError, IOError):
        return []


def save_projects(projects: list[ProjectEntry]) -> None:
    """Atomically save the project registry."""
    _ensure_dirs()
    fd, tmp_path = tempfile.mkstemp(
        dir=str(FOREMAN_DIR), suffix=".tmp", prefix=".proj_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "projects": [p.model_dump() for p in projects],
                    "updated_at": _utc_now().isoformat(),
                },
                f,
                indent=2,
            )
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, PROJECTS_FILE)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def record_snapshot(projects: list[ProjectEntry]) -> None:
    """Append a snapshot of project scores to HISTORY_FILE."""
    _ensure_dirs()
    ts = _utc_now().isoformat()
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        for proj in projects:
            f.write(
                json.dumps({
                    "ts": ts,
                    "path": str(proj.path),
                    "name": proj.name,
                    "last_score": proj.last_score,
                    "last_grade": proj.last_grade,
                }) + "\n"
            )


def add_project(
    path: str,
    name: str | None = None,
    test_command: str | None = None,
    exclude: list[str] | None = None,
) -> ProjectEntry:
    """Register a project in the forge."""
    resolved = Path(path).resolve()
    if not resolved.is_dir():
        raise ValueError(f"Not a directory: {resolved}")

    projects = load_projects()
    # Deduplicate by path
    projects = [p for p in projects if p.path != str(resolved)]

    entry = ProjectEntry(
        name=name or resolved.name,
        path=str(resolved),
        test_command=test_command,
        exclude=exclude or [],
    )
    projects.append(entry)
    save_projects(projects)
    return entry


def get_active_projects() -> list[ProjectEntry]:
    """Return only active projects."""
    return [p for p in load_projects() if p.active]


# ── Quality Dimension Scoring ────────────────────────────────────────


def _score_has_tests(repo_path: Path, exclude: set[str]) -> float:
    """test_files / source_files, capped at 1.0."""
    from dharma_swarm.xray import discover_files, PYTHON_EXTS

    files = discover_files(repo_path, exclude_patterns=exclude)
    py_files = [f for f in files if f.suffix in PYTHON_EXTS]
    if not py_files:
        return 0.0
    test_files = [f for f in py_files if "test" in f.name.lower()]
    src_files = [f for f in py_files if "test" not in f.name.lower()]
    if not src_files:
        return 1.0 if test_files else 0.0
    return min(1.0, len(test_files) / len(src_files))


def _score_tests_pass(project: ProjectEntry) -> float:
    """1.0 if test suite exits 0, 0.0 otherwise. None if no test command."""
    if not project.test_command:
        return 0.0
    try:
        argv = shlex.split(project.test_command)
        if not argv:
            return 0.0
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=project.path,
        )
        return 1.0 if result.returncode == 0 else 0.0
    except (ValueError, subprocess.TimeoutExpired, OSError):
        return 0.0


def _score_error_handling(repo_path: Path, exclude: set[str]) -> float:
    """Fraction of source files that have try/except or raise statements."""
    from dharma_swarm.xray import discover_files, PYTHON_EXTS

    files = discover_files(repo_path, exclude_patterns=exclude)
    py_src = [
        f for f in files
        if f.suffix in PYTHON_EXTS and "test" not in f.name.lower()
    ]
    if not py_src:
        return 1.0

    has_handling = 0
    for path in py_src:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Try, ast.Raise)):
                    has_handling += 1
                    break
        except (OSError, SyntaxError):
            pass

    return round(has_handling / len(py_src), 3)


def _score_documented(repo_path: Path, exclude: set[str]) -> float:
    """Average docstring coverage across source files."""
    from dharma_swarm.xray import discover_files, PYTHON_EXTS

    files = discover_files(repo_path, exclude_patterns=exclude)
    py_src = [
        f for f in files
        if f.suffix in PYTHON_EXTS and "test" not in f.name.lower()
    ]
    if not py_src:
        return 1.0

    ratios: list[float] = []
    for path in py_src:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
            total = 0
            with_doc = 0
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    total += 1
                    if ast.get_docstring(node):
                        with_doc += 1
            if total > 0:
                ratios.append(with_doc / total)
        except (OSError, SyntaxError):
            pass

    return round(sum(ratios) / len(ratios), 3) if ratios else 0.0


def _score_edge_cases(repo_path: Path, exclude: set[str]) -> float:
    """Estimate: how many public functions have matching test functions?"""
    from dharma_swarm.xray import discover_files, PYTHON_EXTS

    files = discover_files(repo_path, exclude_patterns=exclude)
    py_files = [f for f in files if f.suffix in PYTHON_EXTS]

    # Collect public function names from source files
    public_fns: set[str] = set()
    for path in py_files:
        if "test" in path.name.lower():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not node.name.startswith("_"):
                        public_fns.add(node.name)
        except (OSError, SyntaxError):
            pass

    if not public_fns:
        return 1.0

    # Collect test function names
    test_targets: set[str] = set()
    for path in py_files:
        if "test" not in path.name.lower():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # test_foobar → foobar
                    name = node.name
                    if name.startswith("test_"):
                        name = name[5:]
                    test_targets.add(name)
        except (OSError, SyntaxError):
            pass

    covered = sum(1 for fn in public_fns if fn in test_targets)
    return round(covered / len(public_fns), 3)


def score_all_dimensions(
    project: ProjectEntry,
    *,
    skip_tests: bool = False,
) -> dict[str, float]:
    """Score all 5 quality dimensions for a project."""
    repo = Path(project.path)
    exclude = set(project.exclude) if project.exclude else set()
    cached_tests_pass = project.dimensions.get("tests_pass", 0.0) if project.dimensions else 0.0

    return {
        "has_tests": _score_has_tests(repo, exclude),
        "tests_pass": float(cached_tests_pass or 0.0) if skip_tests else _score_tests_pass(project),
        "error_handling": _score_error_handling(repo, exclude),
        "documented": _score_documented(repo, exclude),
        "edge_cases_covered": _score_edge_cases(repo, exclude),
    }


def find_weakest_dimension(dimensions: dict[str, float]) -> str:
    """Return the dimension name with the lowest score."""
    return min(dimensions, key=lambda k: dimensions[k])


# ── Task Generation ──────────────────────────────────────────────────


def generate_task(
    project: ProjectEntry,
    weakest: str,
    dimensions: dict[str, float],
) -> dict[str, Any]:
    """Generate a concrete improvement task for the weakest dimension.

    Returns a dict with: dimension, score, task, acceptance_criteria, priority.
    """
    score = dimensions[weakest]
    repo = Path(project.path)
    name = project.name

    if weakest == "has_tests":
        # Find source files without corresponding test files
        from dharma_swarm.xray import discover_files, PYTHON_EXTS
        exclude = set(project.exclude) if project.exclude else set()
        files = discover_files(repo, exclude_patterns=exclude)
        py_src = [
            f.relative_to(repo)
            for f in files
            if f.suffix in PYTHON_EXTS and "test" not in f.name.lower()
        ]
        untested = [str(f) for f in py_src[:5]]
        return {
            "dimension": "has_tests",
            "score": score,
            "task": f"Write tests for untested source files in {name}: {', '.join(untested[:3])}",
            "acceptance_criteria": f"Each file has a corresponding test_*.py. Target: test ratio ≥ {score + 0.2:.1f}",
            "priority": 1.0 - score,
            "targets": untested,
        }

    elif weakest == "tests_pass":
        return {
            "dimension": "tests_pass",
            "score": score,
            "task": f"Fix failing tests in {name}. Run: {project.test_command or 'pytest'}",
            "acceptance_criteria": "Test suite exits with code 0. All tests green.",
            "priority": 1.0,  # Broken tests are always top priority
        }

    elif weakest == "error_handling":
        from dharma_swarm.xray import discover_files, PYTHON_EXTS
        exclude = set(project.exclude) if project.exclude else set()
        files = discover_files(repo, exclude_patterns=exclude)
        # Find source files WITHOUT any try/except/raise
        unhandled: list[str] = []
        for path in files:
            if path.suffix not in PYTHON_EXTS or "test" in path.name.lower():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(content)
                has_eh = any(
                    isinstance(n, (ast.Try, ast.Raise)) for n in ast.walk(tree)
                )
                if not has_eh:
                    unhandled.append(str(path.relative_to(repo)))
            except (OSError, SyntaxError):
                pass
        targets = unhandled[:5]
        return {
            "dimension": "error_handling",
            "score": score,
            "task": f"Add input validation and error handling to: {', '.join(targets[:3])}",
            "acceptance_criteria": "Each file has appropriate try/except for I/O, ValueError for bad inputs, and helpful error messages.",
            "priority": 0.9 - score,
            "targets": targets,
        }

    elif weakest == "documented":
        from dharma_swarm.xray import discover_files, PYTHON_EXTS
        exclude = set(project.exclude) if project.exclude else set()
        files = discover_files(repo, exclude_patterns=exclude)
        undocumented: list[str] = []
        for path in files:
            if path.suffix not in PYTHON_EXTS or "test" in path.name.lower():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not node.name.startswith("_") and not ast.get_docstring(node):
                            undocumented.append(
                                f"{path.relative_to(repo)}:{node.name}"
                            )
            except (OSError, SyntaxError):
                pass
        targets = undocumented[:10]
        return {
            "dimension": "documented",
            "score": score,
            "task": f"Add docstrings (Args/Returns/Raises) to undocumented public functions in {name}",
            "acceptance_criteria": f"Docstring coverage ≥ {min(1.0, score + 0.2):.0%}",
            "priority": 0.7 - score,
            "targets": targets,
        }

    else:  # edge_cases_covered
        return {
            "dimension": "edge_cases_covered",
            "score": score,
            "task": f"Add edge-case tests for public functions in {name}: empty inputs, wrong types, boundary values",
            "acceptance_criteria": f"Edge case coverage ≥ {min(1.0, score + 0.15):.0%}. Each public function has at least one negative test.",
            "priority": 0.8 - score,
        }


# ── Forge Cycle ──────────────────────────────────────────────────────


class CycleReport(BaseModel):
    """Result of a single forge cycle."""

    cycle_id: str = Field(default_factory=_new_id)
    timestamp: str = Field(default_factory=lambda: _utc_now().isoformat())
    duration_seconds: float = 0.0
    level: str = "observe"
    per_project: list[dict[str, Any]] = Field(default_factory=list)
    queue_depth: int = 0


def run_cycle(
    level: str = "observe",
    project_filter: str | None = None,
    skip_tests: bool = False,
) -> CycleReport:
    """Run a single forge cycle across all active projects.

    Args:
        level: 'observe' (report only), 'advise' (queue tasks), 'build' (auto-fix).
        project_filter: If set, only run on this project name.
        skip_tests: If True, skip running test suites (faster).
    """
    import time

    start = time.monotonic()
    projects = get_active_projects()
    if project_filter:
        projects = [p for p in projects if p.name == project_filter]

    report = CycleReport(level=level)

    for project in projects:
        repo = Path(project.path)
        if not repo.is_dir():
            logger.warning("Project %s path missing: %s", project.name, project.path)
            continue

        # SCAN: score all dimensions
        dims = score_all_dimensions(project, skip_tests=skip_tests)

        # Compute grade
        avg_score = sum(dims.values()) / len(dims) if dims else 0.0
        grade = (
            "A" if avg_score >= 0.8 else
            "B" if avg_score >= 0.6 else
            "C" if avg_score >= 0.4 else
            "D" if avg_score >= 0.2 else "F"
        )

        # FIND WEAKEST
        weakest = find_weakest_dimension(dims)

        # IMPROVE: generate task
        task = generate_task(project, weakest, dims)

        project_result: dict[str, Any] = {
            "name": project.name,
            "grade": grade,
            "avg_quality": round(avg_score, 3),
            "dimensions": dims,
            "weakest_dimension": weakest,
            "task": task,
        }

        # If advise or build, queue the task
        if level in ("advise", "build"):
            from dharma_swarm.iteration_depth import (
                CompoundingQueue,
                IterationLedger,
            )

            ledger = IterationLedger()
            ledger.load()

            # Find or create initiative for this project
            initiative = None
            for init in ledger.get_active():
                if init.project == project.name:
                    initiative = init
                    break

            if initiative is None:
                initiative = ledger.create(
                    title=f"{project.name} Quality Forge",
                    description=f"Foreman-tracked quality improvement for {project.name}",
                    tags=["foreman", project.name],
                )
                # Set the project field
                initiative.project = project.name
                ledger.save()

            # Queue task
            queue = CompoundingQueue()
            queue.load()
            pending_for_initiative = [
                item for item in queue.get_for_initiative(initiative.id)
                if not item.completed
            ]
            already_pending = any(item.task == task["task"] for item in pending_for_initiative)
            if not already_pending:
                queue.add(
                    initiative_id=initiative.id,
                    task=task["task"],
                    priority=task["priority"],
                )

            # Record iteration
            ledger.record_iteration(
                initiative_id=initiative.id,
                action=f"Forge cycle: {weakest}={dims[weakest]:.2f}",
                evidence=json.dumps(dims),
                quality_updates={
                    "has_tests": dims["has_tests"],
                    "tests_pass": dims["tests_pass"],
                    "error_handling": dims["error_handling"],
                    "documented": dims["documented"],
                    "edge_cases_covered": dims["edge_cases_covered"],
                },
                reviewer="foreman",
            )

            project_result["queued"] = not already_pending
            project_result["queue_status"] = "already_pending" if already_pending else "queued"
            report.queue_depth = len(queue.get_pending())

        # Update project registry with latest scores
        project.last_scan = _utc_now().isoformat()
        project.last_grade = grade
        project.last_score = avg_score
        project.dimensions = dims

        report.per_project.append(project_result)

    # Save updated project scores
    all_projects = load_projects()
    for updated in projects:
        for i, existing in enumerate(all_projects):
            if existing.path == updated.path:
                all_projects[i] = updated
                break
    save_projects(all_projects)

    report.duration_seconds = round(time.monotonic() - start, 2)

    # Persist cycle report
    _ensure_dirs()
    with open(CYCLES_FILE, "a", encoding="utf-8") as f:
        f.write(report.model_dump_json() + "\n")

    return report


# ── Display ──────────────────────────────────────────────────────────


def format_status(projects: list[ProjectEntry] | None = None) -> str:
    """Format a human-readable status of all tracked projects."""
    if projects is None:
        projects = load_projects()

    if not projects:
        return "No projects registered. Use `dgc foreman add <path>` to add one."

    lines = ["# Foreman Quality Forge — Status", ""]
    for p in projects:
        status = "🔥" if p.active else "⏸️"
        grade = p.last_grade or "?"
        score = f"{p.last_score:.2f}" if p.last_score is not None else "—"
        lines.append(f"{status} **{p.name}** [{grade}] (quality={score})")

        if p.dimensions:
            dims = p.dimensions
            weakest = min(dims, key=lambda k: dims.get(k, 0) or 0)
            for dim_name in QUALITY_DIMENSIONS:
                val = dims.get(dim_name)
                marker = " ← WEAKEST" if dim_name == weakest else ""
                val_str = f"{val:.2f}" if val is not None else "—"
                bar = "█" * int((val or 0) * 10) + "░" * (10 - int((val or 0) * 10))
                lines.append(f"  {dim_name:22s} {bar} {val_str}{marker}")
        lines.append("")

    return "\n".join(lines)


# ── Cron Integration ─────────────────────────────────────────────────


def foreman_run_fn(job: dict[str, Any]) -> tuple[bool, str, str | None]:
    """Cron tick run_fn: runs a forge cycle.

    Signature matches tick(run_fn=...) → (success, output, error).
    """
    level = job.get("prompt", "advise").strip().lower()
    if level not in ("observe", "advise", "build"):
        level = "advise"
    try:
        report = run_cycle(level=level, skip_tests=(level == "observe"))
        output = format_status()
        output += f"\n---\nCycle {report.cycle_id}: {report.duration_seconds}s, {len(report.per_project)} projects scanned.\n"
        for p in report.per_project:
            output += f"  {p['name']}: {p['grade']} (weakest: {p['weakest_dimension']}={p['dimensions'][p['weakest_dimension']]:.2f})\n"
            output += f"  → {p['task']['task']}\n"
        return True, output, None
    except Exception as e:
        logger.error("Foreman cycle failed: %s", e)
        return False, f"Foreman cycle failed: {e}", str(e)


def create_foreman_cron_job(
    every: str = "every 4h",
    level: str = "advise",
) -> dict[str, Any]:
    """Create the recurring foreman cron job."""
    from dharma_swarm.cron_scheduler import create_job, list_jobs

    # Check if foreman job already exists
    existing = list_jobs()
    for job in existing:
        if job.get("name", "").startswith("foreman"):
            logger.info("Foreman cron job already exists: %s", job["id"])
            return job

    return create_job(
        prompt=level,
        schedule=every,
        name=f"foreman-forge-{level}",
    )
