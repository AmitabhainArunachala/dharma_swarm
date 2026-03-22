"""Custodians — autonomous code maintenance fleet.

Deploys specialized free-tier LLM agents to continuously debug, lint,
type-check, document, and test the dharma_swarm codebase.

Five roles, three tiers:
    Tier 3 (fast):     Linter
    Tier 2 (general):  Type Tightener, Doc Patcher, Dead Code Hunter
    Tier 1 (reasoning): Test Gap Closer

Safety: branch-per-run, py_compile + test validation, git reset on failure,
max files per role per cycle, stash/pop existing work.

Usage:
    dgc custodians run [--roles linter,doc_patcher] [--dry-run]
    dgc custodians status
    dgc custodians schedule
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────

DHARMA_SWARM_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = DHARMA_SWARM_ROOT / "dharma_swarm"
TESTS_DIR = DHARMA_SWARM_ROOT / "tests"
STATE_DIR = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma")) / "custodians"
HISTORY_FILE = STATE_DIR / "history.jsonl"
MAX_FILES_PER_ROLE = 5
MAX_AGENT_ITERATIONS = 20
TEST_COMMAND = "python3 -m pytest tests/ -x -q --tb=short"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_dirs() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


# ── Role Definitions ─────────────────────────────────────────────────


@dataclass(frozen=True)
class CustodianRole:
    """A specialized maintenance agent role."""

    name: str
    tier: int  # 1=reasoning, 2=general, 3=fast
    system_prompt: str
    user_prompt_template: str
    file_filter: str = "*.py"  # glob pattern for target files
    skip_patterns: tuple[str, ...] = ("__pycache__", ".pyc", "node_modules")
    max_files: int = MAX_FILES_PER_ROLE


ROLES: dict[str, CustodianRole] = {
    "linter": CustodianRole(
        name="linter",
        tier=3,
        system_prompt=(
            "You are a Python linter agent. Your ONLY job is to fix lint issues.\n"
            "Working directory: {project_path}\n\n"
            "RULES:\n"
            "- Run `python3 -m py_compile <file>` to check syntax before and after changes.\n"
            "- Remove unused imports (check that nothing breaks after removal).\n"
            "- Fix obvious formatting issues (trailing whitespace, missing newlines at EOF).\n"
            "- Do NOT change logic, rename things, or refactor.\n"
            "- Do NOT add new imports or dependencies.\n"
            "- If unsure whether an import is used, leave it.\n"
            "- After ALL changes, run: {test_command}\n"
        ),
        user_prompt_template=(
            "Fix lint issues in these files:\n{file_list}\n\n"
            "For each file: check syntax, remove clearly unused imports, "
            "fix formatting. Then run the test suite to verify nothing broke."
        ),
    ),
    "type_tightener": CustodianRole(
        name="type_tightener",
        tier=2,
        system_prompt=(
            "You are a Python type annotation agent. Your ONLY job is to add missing type hints.\n"
            "Working directory: {project_path}\n\n"
            "RULES:\n"
            "- Add return type annotations to public functions missing them.\n"
            "- Add parameter type annotations where types are obvious from usage.\n"
            "- Use `from __future__ import annotations` if not already present.\n"
            "- Do NOT change logic or behavior.\n"
            "- Do NOT add overly complex generic types — keep it simple.\n"
            "- Validate with `python3 -m py_compile <file>` after each change.\n"
            "- After ALL changes, run: {test_command}\n"
        ),
        user_prompt_template=(
            "Add missing type annotations to public functions in these files:\n{file_list}\n\n"
            "Focus on return types and obvious parameter types. "
            "Validate each file compiles, then run the test suite."
        ),
    ),
    "doc_patcher": CustodianRole(
        name="doc_patcher",
        tier=2,
        system_prompt=(
            "You are a Python documentation agent. Your ONLY job is to add missing docstrings.\n"
            "Working directory: {project_path}\n\n"
            "RULES:\n"
            "- Add docstrings to public classes and functions that lack them.\n"
            "- Keep docstrings concise — one line if simple, brief paragraph if complex.\n"
            "- Match the existing docstring style in the file.\n"
            "- Do NOT change code logic or behavior.\n"
            "- Do NOT document private methods (those starting with _) unless they're complex.\n"
            "- Validate with `python3 -m py_compile <file>` after changes.\n"
            "- After ALL changes, run: {test_command}\n"
        ),
        user_prompt_template=(
            "Add missing docstrings to public classes and functions in these files:\n{file_list}\n\n"
            "Keep docstrings concise and accurate. "
            "Validate each file compiles, then run the test suite."
        ),
    ),
    "test_gap_closer": CustodianRole(
        name="test_gap_closer",
        tier=1,
        system_prompt=(
            "You are a Python test writing agent. Your job is to write minimal smoke tests.\n"
            "Working directory: {project_path}\n\n"
            "RULES:\n"
            "- Write tests for modules that have NO existing test file.\n"
            "- Tests go in tests/test_<module_name>.py\n"
            "- Write 2-3 basic smoke tests per module: can it import, do key functions work.\n"
            "- Use pytest style. Use tmp_path for any file I/O.\n"
            "- Mock external dependencies (API calls, network, heavy imports).\n"
            "- Do NOT modify existing source code.\n"
            "- Run: {test_command} to verify tests pass.\n"
        ),
        user_prompt_template=(
            "These modules have no test coverage:\n{file_list}\n\n"
            "Write minimal smoke tests for each. Focus on: can it import, "
            "do key public functions accept correct args and return something. "
            "Run the tests to verify they pass."
        ),
        max_files=3,  # Fewer files — writing tests is expensive
    ),
    "dead_code_hunter": CustodianRole(
        name="dead_code_hunter",
        tier=2,
        system_prompt=(
            "You are a dead code removal agent. Your ONLY job is to find and remove dead code.\n"
            "Working directory: {project_path}\n\n"
            "RULES:\n"
            "- Remove functions/classes that are never called or imported anywhere.\n"
            "- Remove commented-out code blocks (>5 lines).\n"
            "- Remove imports that are not used in the file.\n"
            "- BEFORE removing anything, grep the entire project to confirm it's unused.\n"
            "- Be CONSERVATIVE — if there's any doubt, leave it.\n"
            "- Validate with `python3 -m py_compile <file>` after each change.\n"
            "- After ALL changes, run: {test_command}\n"
        ),
        user_prompt_template=(
            "Hunt for dead code in these files:\n{file_list}\n\n"
            "For each file: grep the project for usages of each function/class. "
            "Remove only what is provably unused. Validate after every removal."
        ),
        max_files=3,
    ),
}

# Map role names to their cron groups
CRON_GROUPS: dict[str, list[str]] = {
    "6h": ["linter", "doc_patcher"],
    "12h": ["type_tightener", "dead_code_hunter"],
    "daily": ["test_gap_closer"],
}

# ── Model Rotation ───────────────────────────────────────────────────
# Each role cycles through multiple candidate models across runs.
# Heavy reasoning roles get Tier 1 models; fast roles get Tier 3.

MODEL_ROTATION: dict[str, list[str]] = {
    "linter": [
        "microsoft/phi-4:free",
        "mistralai/mistral-small-3.1-24b-instruct:free",
    ],
    "type_tightener": [
        "qwen/qwen-2.5-72b-instruct:free",
        "google/gemini-2.0-flash-exp:free",
        "nousresearch/hermes-3-llama-3.1-405b:free",
    ],
    "doc_patcher": [
        "qwen/qwen-2.5-72b-instruct:free",
        "nousresearch/hermes-3-llama-3.1-405b:free",
        "google/gemini-2.0-flash-exp:free",
    ],
    "test_gap_closer": [
        "deepseek/deepseek-r1:free",
        "meta-llama/llama-3.3-70b-instruct:free",
    ],
    "dead_code_hunter": [
        "deepseek/deepseek-r1:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen-2.5-72b-instruct:free",
    ],
}


def _get_model_for_role(role_name: str) -> str:
    """Get the next model in the rotation for a role.

    Cycles through MODEL_ROTATION based on the number of previous runs.
    Falls back to tier-based selection if role is not in rotation.
    """
    candidates = MODEL_ROTATION.get(role_name)
    if not candidates:
        role = ROLES.get(role_name)
        return _get_model_for_tier(role.tier if role else 2)

    # Count previous runs for this role to determine rotation index
    history = load_history(role=role_name, limit=1000)
    run_count = len(history)
    return candidates[run_count % len(candidates)]


# ── File Selection ───────────────────────────────────────────────────


def _discover_py_files(directory: Path, exclude: tuple[str, ...] = ()) -> list[Path]:
    """Discover Python files, excluding patterns."""
    files: list[Path] = []
    for f in sorted(directory.rglob("*.py")):
        rel = str(f.relative_to(directory))
        if any(pat in rel for pat in exclude):
            continue
        if f.stat().st_size < 10:  # Skip empty/trivial files
            continue
        files.append(f)
    return files


def _load_last_touched() -> dict[str, str]:
    """Load {filepath: last_role_that_touched_it} from history."""
    if not HISTORY_FILE.exists():
        return {}
    touched: dict[str, str] = {}
    for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            for f in entry.get("files_changed", []):
                touched[f] = entry.get("role", "")
        except json.JSONDecodeError:
            continue
    return touched


def select_files(
    role: CustodianRole,
    project_dir: Path | None = None,
) -> list[Path]:
    """Select target files for a role, rotating to avoid re-touching."""
    pkg = project_dir or PACKAGE_DIR
    all_files = _discover_py_files(pkg, exclude=role.skip_patterns)

    if role.name == "test_gap_closer":
        # Find modules with no corresponding test file
        test_files = {f.name for f in TESTS_DIR.iterdir() if f.name.startswith("test_")} if TESTS_DIR.is_dir() else set()
        untested = []
        for f in all_files:
            test_name = f"test_{f.stem}.py"
            if test_name not in test_files and not f.name.startswith("test_"):
                untested.append(f)
        all_files = untested

    # Rotate: deprioritize files touched last cycle by this role
    last_touched = _load_last_touched()
    fresh = [f for f in all_files if last_touched.get(str(f)) != role.name]
    stale = [f for f in all_files if last_touched.get(str(f)) == role.name]

    candidates = fresh + stale  # Fresh files first
    return candidates[: role.max_files]


# ── Execution ────────────────────────────────────────────────────────


@dataclass
class CustodianResult:
    """Outcome of a single custodian role run."""

    role: str
    success: bool
    dry_run: bool = True
    model: str = ""
    files_targeted: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    agent_output: str = ""
    duration_seconds: float = 0.0
    error: str | None = None
    committed: bool = False


def _get_model_for_tier(tier: int) -> str:
    """Get the preferred free-fleet model for a tier."""
    from dharma_swarm.free_fleet import FREE_FLEET
    return FREE_FLEET.preferred_model(tier=tier)


def _validate_files(project_path: str, files: list[str]) -> bool:
    """Validate changed files compile cleanly."""
    for f in files:
        fpath = Path(project_path) / f
        if not fpath.exists() or fpath.suffix != ".py":
            continue
        try:
            result = subprocess.run(
                ["python3", "-m", "py_compile", str(fpath)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                logger.warning("py_compile failed for %s: %s", f, result.stderr)
                return False
        except (subprocess.TimeoutExpired, OSError):
            return False
    return True


def _run_tests(project_path: str, test_command: str | None = None) -> bool:
    """Run the project test suite. Returns True if tests pass."""
    cmd = test_command or TEST_COMMAND
    try:
        result = subprocess.run(
            cmd.split(),
            capture_output=True, text=True,
            cwd=project_path, timeout=300,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


# ── Auto-Merge ───────────────────────────────────────────────────────


def _git_merge_to_main(project_path: str, branch_name: str) -> bool:
    """Merge a custodian branch back to main. Returns True on success."""
    try:
        # Switch to main
        r = subprocess.run(
            ["git", "checkout", "main"],
            capture_output=True, text=True, cwd=project_path, timeout=30,
        )
        if r.returncode != 0:
            logger.warning("Failed to checkout main: %s", r.stderr)
            return False

        # Merge
        r = subprocess.run(
            ["git", "merge", branch_name, "--no-edit"],
            capture_output=True, text=True, cwd=project_path, timeout=60,
        )
        if r.returncode != 0:
            logger.warning("Merge conflict on %s, aborting", branch_name)
            subprocess.run(
                ["git", "merge", "--abort"],
                capture_output=True, text=True, cwd=project_path, timeout=30,
            )
            return False

        # Clean up branch
        subprocess.run(
            ["git", "branch", "-d", branch_name],
            capture_output=True, text=True, cwd=project_path, timeout=30,
        )
        logger.info("Merged %s to main and deleted branch", branch_name)
        return True
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("Auto-merge failed: %s", e)
        return False


# ── Ontological Lifecycle ────────────────────────────────────────────
# Each role tracks its own lifecycle: seed → growing → solid → shipped
# mirroring the plant ontological system in iteration_depth.py.

ROLE_LIFECYCLE_THRESHOLDS = {
    "growing": {"min_runs": 1},
    "solid": {"min_runs": 5, "min_success_rate": 0.7},
    "shipped": {"min_runs": 10, "min_success_rate": 0.85},
}


def _compute_role_lifecycle(role_name: str) -> dict[str, Any]:
    """Compute lifecycle status for a custodian role from history.

    Returns dict with: status, total_runs, successes, success_rate, files_healed.
    Status follows the plant ontology: seed → growing → solid → shipped.
    """
    history = load_history(role=role_name, limit=10000)
    real_runs = [h for h in history if not h.get("dry_run", True)]
    total = len(real_runs)
    successes = sum(1 for h in real_runs if h.get("success"))
    rate = successes / total if total > 0 else 0.0
    files_healed = sum(len(h.get("files_changed", [])) for h in real_runs)

    # Determine lifecycle status
    status = "seed"
    if total >= ROLE_LIFECYCLE_THRESHOLDS["shipped"]["min_runs"] and rate >= ROLE_LIFECYCLE_THRESHOLDS["shipped"]["min_success_rate"]:
        status = "shipped"
    elif total >= ROLE_LIFECYCLE_THRESHOLDS["solid"]["min_runs"] and rate >= ROLE_LIFECYCLE_THRESHOLDS["solid"]["min_success_rate"]:
        status = "solid"
    elif total >= ROLE_LIFECYCLE_THRESHOLDS["growing"]["min_runs"]:
        status = "growing"

    return {
        "role": role_name,
        "status": status,
        "total_runs": total,
        "successes": successes,
        "success_rate": round(rate, 3),
        "files_healed": files_healed,
    }


def _update_role_ontology(role_name: str) -> None:
    """Update the ontology registry with current role lifecycle state.

    Registers CustodianRole objects in the ontology and updates their
    status based on the plant lifecycle ratchet.
    Uses the shared singleton registry so updates persist and are visible
    to API, TUI, and other subsystems.
    """
    try:
        from dharma_swarm.ontology import OntologyObj
        from dharma_swarm.ontology_runtime import get_shared_registry, persist_shared_registry

        registry = get_shared_registry()

        lifecycle = _compute_role_lifecycle(role_name)
        role = ROLES.get(role_name)
        if not role:
            return

        obj_id = f"custodian-{role_name}"
        model = _get_model_for_role(role_name)

        properties = {
            "name": role_name,
            "tier": role.tier,
            "model": model,
            "status": lifecycle["status"],
            "total_runs": lifecycle["total_runs"],
            "success_rate": lifecycle["success_rate"],
            "files_healed": lifecycle["files_healed"],
        }

        obj, errors = registry.put_object(
            OntologyObj(
                id=obj_id,
                type_name="CustodianRole",
                properties=properties,
                created_by="custodians",
            ),
            updated_by="custodians",
        )
        if obj is None or errors:
            logger.debug("Ontology update skipped for %s: %s", role_name, errors)
            return

        persist_shared_registry(registry)
        logger.debug(
            "Ontology update: %s status=%s runs=%d rate=%.1f%%",
            role_name, lifecycle["status"],
            lifecycle["total_runs"], lifecycle["success_rate"] * 100,
        )
    except Exception as e:
        # Ontology update is best-effort — don't break the run
        logger.debug("Ontology update skipped: %s", e)


def _record_run(result: CustodianResult) -> None:
    """Append a run record to history."""
    _ensure_dirs()
    entry = {
        "timestamp": _utc_now().isoformat(),
        "role": result.role,
        "success": result.success,
        "dry_run": result.dry_run,
        "model": result.model,
        "files_targeted": result.files_targeted,
        "files_changed": result.files_changed,
        "duration_seconds": result.duration_seconds,
        "committed": result.committed,
        "error": result.error,
    }
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def run_role(
    role_name: str,
    dry_run: bool = True,
    project_path: str | None = None,
    test_command: str | None = None,
) -> CustodianResult:
    """Run a single custodian role.

    Args:
        role_name: One of the ROLES keys.
        dry_run: If True, show what would be done without executing.
        project_path: Override project root (default: dharma_swarm repo root).
        test_command: Override test command.

    Returns:
        CustodianResult with outcome details.
    """
    role = ROLES.get(role_name)
    if role is None:
        return CustodianResult(
            role=role_name, success=False,
            error=f"Unknown role: {role_name}. Valid: {', '.join(ROLES)}",
        )

    start = time.monotonic()
    proj = project_path or str(DHARMA_SWARM_ROOT)
    model = _get_model_for_role(role_name)
    test_cmd = test_command or TEST_COMMAND

    # Select target files
    files = select_files(role)
    if not files:
        return CustodianResult(
            role=role_name, success=True, dry_run=dry_run, model=model,
            duration_seconds=round(time.monotonic() - start, 2),
            error="No files to process",
        )

    file_list = "\n".join(f"- {f.relative_to(DHARMA_SWARM_ROOT)}" for f in files)
    target_names = [str(f.relative_to(DHARMA_SWARM_ROOT)) for f in files]

    # Build prompts
    sys_prompt = role.system_prompt.format(
        project_path=proj, test_command=test_cmd,
    )
    user_prompt = role.user_prompt_template.format(file_list=file_list)

    # Dry run
    if dry_run:
        return CustodianResult(
            role=role_name, success=True, dry_run=True, model=model,
            files_targeted=target_names,
            agent_output=f"[DRY RUN] Would run {role_name} on {len(files)} files with {model}",
            duration_seconds=round(time.monotonic() - start, 2),
        )

    # Live run — import git helpers from build engine
    from dharma_swarm.build_engine import (
        _git_stash, _git_stash_pop, _git_diff_files,
        _git_reset_hard, _git_commit, _hermes_available,
    )

    if not _hermes_available():
        return CustodianResult(
            role=role_name, success=False, dry_run=False, model=model,
            files_targeted=target_names,
            error="Hermes Agent not available (missing API key or hermes-agent directory)",
            duration_seconds=round(time.monotonic() - start, 2),
        )

    # Create custodian branch
    branch_name = f"custodians/{_utc_now().strftime('%Y-%m-%d-%H%M')}-{role_name}"
    try:
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            capture_output=True, text=True, cwd=proj, timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("Failed to create branch %s: %s", branch_name, e)

    had_stash = _git_stash(proj)

    try:
        # Spawn agent with free-tier model
        from dharma_swarm.build_engine import _spawn_agent
        agent_output = _spawn_agent(user_prompt, sys_prompt, proj, model=model)

        # Check what changed
        files_changed = _git_diff_files(proj)

        # Validate
        if files_changed:
            compile_ok = _validate_files(proj, files_changed)
            tests_ok = _run_tests(proj, test_cmd) if compile_ok else False

            if compile_ok and tests_ok:
                commit_msg = (
                    f"custodians({role_name}): maintenance pass\n\n"
                    f"Model: {model}\n"
                    f"Files: {', '.join(files_changed[:10])}\n\n"
                    f"Co-Authored-By: Oz <oz-agent@warp.dev>"
                )
                committed = _git_commit(proj, commit_msg)

                # Auto-merge to main if commit succeeded
                if committed:
                    merged = _git_merge_to_main(proj, branch_name)
                    if not merged:
                        logger.info(
                            "Branch %s not merged (conflict?) — left for manual review",
                            branch_name,
                        )
            else:
                logger.warning("Custodian %s: validation failed, rolling back", role_name)
                _git_reset_hard(proj)
                files_changed = []
                committed = False

                result = CustodianResult(
                    role=role_name, success=False, dry_run=False, model=model,
                    files_targeted=target_names,
                    files_changed=[],
                    agent_output=agent_output,
                    duration_seconds=round(time.monotonic() - start, 2),
                    error="Validation failed (compile or tests) — changes rolled back",
                    committed=False,
                )
                _record_run(result)
                return result
        else:
            committed = False

        result = CustodianResult(
            role=role_name, success=True, dry_run=False, model=model,
            files_targeted=target_names,
            files_changed=files_changed,
            agent_output=agent_output,
            duration_seconds=round(time.monotonic() - start, 2),
            committed=committed,
        )
        _record_run(result)
        _update_role_ontology(role_name)
        return result

    except Exception as e:
        _git_reset_hard(proj)
        result = CustodianResult(
            role=role_name, success=False, dry_run=False, model=model,
            files_targeted=target_names,
            error=f"Custodian error: {e}",
            duration_seconds=round(time.monotonic() - start, 2),
        )
        _record_run(result)
        return result
    finally:
        if had_stash:
            _git_stash_pop(proj)
        # Return to main branch
        try:
            subprocess.run(
                ["git", "checkout", "main"],
                capture_output=True, text=True, cwd=proj, timeout=30,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass


def run_custodian_cycle(
    roles: list[str] | None = None,
    dry_run: bool = True,
    test_command: str | None = None,
) -> list[CustodianResult]:
    """Run a full custodian cycle with the specified roles.

    Args:
        roles: List of role names to run. None = all roles.
        dry_run: If True, show what would be done.
        test_command: Override test command.

    Returns:
        List of CustodianResult objects.
    """
    role_names = roles or list(ROLES.keys())
    results: list[CustodianResult] = []

    for name in role_names:
        if name not in ROLES:
            logger.warning("Unknown custodian role: %s", name)
            continue
        result = run_role(name, dry_run=dry_run, test_command=test_command)
        results.append(result)

    return results


# ── Status & History ─────────────────────────────────────────────────


def load_history(role: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Load recent custodian run history."""
    if not HISTORY_FILE.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            if role is None or entry.get("role") == role:
                entries.append(entry)
        except json.JSONDecodeError:
            continue
    return entries[-limit:]


def format_status() -> str:
    """Format a human-readable custodian fleet status."""
    history = load_history(limit=50)
    if not history:
        return "No custodian runs recorded yet. Run `dgc custodians run` to start."

    lines = ["# Custodian Fleet — Status", ""]

    # Per-role summary
    role_stats: dict[str, dict[str, Any]] = {}
    for entry in history:
        rname = entry.get("role", "?")
        if rname not in role_stats:
            role_stats[rname] = {"runs": 0, "successes": 0, "files_changed": 0, "last": ""}
        role_stats[rname]["runs"] += 1
        if entry.get("success"):
            role_stats[rname]["successes"] += 1
        role_stats[rname]["files_changed"] += len(entry.get("files_changed", []))
        role_stats[rname]["last"] = entry.get("timestamp", "")

    lifecycle_icons = {"seed": "🌱", "growing": "🌿", "solid": "🪨", "shipped": "🚀"}

    for rname in ROLES:
        stats = role_stats.get(rname, {"runs": 0, "successes": 0, "files_changed": 0, "last": "never"})
        tier = ROLES[rname].tier
        model = _get_model_for_role(rname)
        lifecycle = _compute_role_lifecycle(rname)
        lc_icon = lifecycle_icons.get(lifecycle["status"], "?")
        rate = f"{stats['successes']}/{stats['runs']}" if stats["runs"] else "—"
        lines.append(
            f"  {lc_icon} {rname:20s}  tier={tier}  runs={rate}  "
            f"files_healed={lifecycle['files_healed']}  status={lifecycle['status']}"
        )
        lines.append(f"    model: {model}  (next in rotation)")

    # Recent runs
    lines.append("")
    lines.append("Recent runs:")
    for entry in history[-5:]:
        status = "✅" if entry.get("success") else "❌"
        dry = " [DRY]" if entry.get("dry_run") else ""
        lines.append(
            f"  {status} {entry.get('role', '?')}{dry}  "
            f"{len(entry.get('files_changed', []))} files  "
            f"{entry.get('duration_seconds', 0)}s  "
            f"{entry.get('timestamp', '')[:16]}"
        )

    return "\n".join(lines)


# ── Cron Integration ─────────────────────────────────────────────────


def custodians_run_fn(job: dict[str, Any]) -> tuple[bool, str, str | None]:
    """Cron tick run_fn: runs a custodian cycle.

    The job prompt determines which group to run:
      "6h"    → linter + doc_patcher
      "12h"   → type_tightener + dead_code_hunter
      "daily" → test_gap_closer
      "all"   → all roles
    """
    group = job.get("prompt", "6h").strip().lower()
    role_names = CRON_GROUPS.get(group, list(ROLES.keys()))

    try:
        results = run_custodian_cycle(roles=role_names, dry_run=False)
        lines = [f"# Custodian Fleet — {group} cycle", ""]
        for r in results:
            status = "✅" if r.success else "❌"
            lines.append(f"{status} **{r.role}** ({r.model})")
            if r.files_changed:
                lines.append(f"  Changed: {', '.join(r.files_changed[:5])}")
            if r.committed:
                lines.append("  Committed: yes")
            if r.error:
                lines.append(f"  Error: {r.error}")
            lines.append(f"  Duration: {r.duration_seconds}s")
            lines.append("")

        output = "\n".join(lines)
        all_ok = all(r.success for r in results)
        return all_ok, output, None
    except Exception as e:
        logger.error("Custodian cycle failed: %s", e)
        return False, f"Custodian cycle failed: {e}", str(e)


def create_custodian_cron_jobs() -> list[dict[str, Any]]:
    """Create the recurring custodian cron jobs."""
    from dharma_swarm.cron_scheduler import create_job, list_jobs

    existing = list_jobs()
    existing_names = {j.get("name", "") for j in existing}
    created: list[dict[str, Any]] = []

    schedules = [
        ("custodians-6h", "6h", "every 6h"),
        ("custodians-12h", "12h", "every 12h"),
        ("custodians-daily", "daily", "every 24h"),
    ]

    for name, prompt, schedule in schedules:
        if name in existing_names:
            logger.info("Custodian cron job '%s' already exists", name)
            continue
        job = create_job(prompt=prompt, schedule=schedule, name=name, handler="custodians_forge")
        created.append(job)
        logger.info("Created custodian cron job: %s (%s)", name, schedule)

    return created


def install_launchd_service() -> bool:
    """Install the cron daemon as a macOS launchd service.

    Copies the plist to ~/Library/LaunchAgents/ and loads it.
    Creates log directory. Returns True on success.
    """
    import platform
    import shutil

    if platform.system() != "Darwin":
        logger.info("Launchd is macOS-only; skipping service install")
        return False

    plist_src = DHARMA_SWARM_ROOT / "scripts" / "com.dharma.cron-daemon.plist"
    if not plist_src.exists():
        logger.warning("Plist template not found: %s", plist_src)
        return False

    # Ensure log directory
    log_dir = Path.home() / ".dharma" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Copy plist with absolute paths; launchd does not reliably expand "~".
    launch_agents = Path.home() / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True, exist_ok=True)
    dest = launch_agents / "com.dharma.cron-daemon.plist"
    plist_text = plist_src.read_text(encoding="utf-8")
    home_str = str(Path.home())
    plist_text = plist_text.replace(
        "<string>~/.dharma/logs/cron-daemon.stdout.log</string>",
        f"<string>{home_str}/.dharma/logs/cron-daemon.stdout.log</string>",
    )
    plist_text = plist_text.replace(
        "<string>~/.dharma/logs/cron-daemon.stderr.log</string>",
        f"<string>{home_str}/.dharma/logs/cron-daemon.stderr.log</string>",
    )
    plist_text = plist_text.replace(
        "<string>~</string>",
        f"<string>{home_str}</string>",
    )
    dest.write_text(plist_text, encoding="utf-8")

    # Load (unload first if already loaded)
    try:
        subprocess.run(
            ["launchctl", "unload", str(dest)],
            capture_output=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass

    try:
        result = subprocess.run(
            ["launchctl", "load", str(dest)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            logger.info("Launchd service installed and loaded: %s", dest)
            return True
        else:
            logger.warning("launchctl load failed: %s", result.stderr)
            return False
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("Failed to load launchd service: %s", e)
        return False
