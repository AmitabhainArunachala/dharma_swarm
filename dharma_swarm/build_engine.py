"""Build Engine — autonomous code improvement via Hermes Agent.

Connects the Foreman's CompoundingQueue to actual code execution:
    PULL TASK → BUILD PROMPT → SPAWN AGENT → VALIDATE → COMMIT/ROLLBACK

Safety: git stash before, rollback if tests fail, time budgets,
dry-run default, never auto-pushes.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────

HERMES_DIR = Path(__file__).resolve().parent.parent / "external" / "hermes-agent"
DEFAULT_MODEL = os.getenv("BUILD_ENGINE_MODEL", "anthropic/claude-sonnet-4-20250514")
MAX_TASK_MINUTES = 10
MAX_CYCLE_MINUTES = 60
MAX_AGENT_ITERATIONS = 30


# ── Models ───────────────────────────────────────────────────────────


@dataclass
class BuildTask:
    """A concrete code improvement task pulled from the queue."""

    queue_item_id: str
    initiative_id: str
    task: str
    project_name: str
    project_path: str
    dimension: str = ""
    targets: list[str] = field(default_factory=list)
    acceptance_criteria: str = ""
    test_command: str | None = None
    priority: float = 0.5


@dataclass
class BuildResult:
    """Outcome of a single build task execution."""

    task: BuildTask
    success: bool
    dry_run: bool = True
    agent_output: str = ""
    tests_passed: bool | None = None
    files_changed: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    error: str | None = None
    committed: bool = False
    quality_before: float | None = None
    quality_after: float | None = None
    quality_delta: float | None = None


# ── Hermes Agent Integration ─────────────────────────────────────────


def _hermes_available() -> bool:
    """Check if Hermes Agent can be imported and has an API key."""
    if not HERMES_DIR.is_dir():
        return False
    if not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("OPENROUTER_API_KEY"):
        return False
    return True


def _spawn_agent(
    prompt: str,
    system_prompt: str,
    project_path: str,
    model: str | None = None,
) -> str:
    """Spawn a Hermes AIAgent and run the task. Returns agent output.

    Args:
        model: Override the default model (e.g. for free-tier custodian agents).
    """
    original_path = list(sys.path)
    hermes_str = str(HERMES_DIR)
    try:
        if hermes_str not in sys.path:
            sys.path.insert(0, hermes_str)
        from run_agent import AIAgent

        agent = AIAgent(
            model=model or DEFAULT_MODEL,
            max_iterations=MAX_AGENT_ITERATIONS,
            enabled_toolsets=["terminal", "file"],
            quiet_mode=True,
            skip_memory=True,
            skip_context_files=True,
        )

        # Set working directory for agent's terminal operations
        original_cwd = os.getcwd()
        try:
            os.chdir(project_path)
            result = agent.run_conversation(
                prompt,
                system_message=system_prompt,
            )
            if isinstance(result, dict):
                return result.get("final_response", str(result))
            return str(result)
        finally:
            os.chdir(original_cwd)
    finally:
        sys.path[:] = original_path


# ── Prompt Builder ───────────────────────────────────────────────────


def build_prompt(task: BuildTask) -> tuple[str, str]:
    """Build system prompt and user prompt for a build task.

    Returns (system_prompt, user_prompt).
    """
    system_prompt = f"""You are a focused code improvement agent working on the project '{task.project_name}'.
Your working directory is: {task.project_path}

RULES:
- Only modify files within this project directory.
- Write clean, well-tested code.
- After making changes, run the test suite to verify.
- If tests fail, fix the issues or revert your changes.
- Do NOT create new dependencies without strong justification.
- Do NOT modify CI/CD configs, deployment files, or security-sensitive files.
- Be precise and minimal — fix exactly what's asked, nothing more.

TEST COMMAND: {task.test_command or 'python3 -m pytest'}
"""

    targets_str = ""
    if task.targets:
        targets_str = "\n\nTARGET FILES:\n" + "\n".join(f"- {t}" for t in task.targets)

    user_prompt = f"""TASK: {task.task}

DIMENSION: {task.dimension}
ACCEPTANCE CRITERIA: {task.acceptance_criteria}{targets_str}

Execute this task now. Write the code, then run the tests to verify."""

    return system_prompt, user_prompt


# ── Git Safety ───────────────────────────────────────────────────────


def _git_stash(project_path: str) -> bool:
    """Stash any uncommitted changes. Returns True if stash was created."""
    try:
        result = subprocess.run(
            ["git", "stash", "push", "-m", "build-engine-safety-stash"],
            capture_output=True, text=True, cwd=project_path, timeout=30,
        )
        # "No local changes to save" means nothing was stashed
        return "No local changes" not in result.stdout
    except (subprocess.TimeoutExpired, OSError):
        return False


def _git_stash_pop(project_path: str) -> None:
    """Pop the safety stash."""
    try:
        subprocess.run(
            ["git", "stash", "pop"],
            capture_output=True, text=True, cwd=project_path, timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass


def _git_diff_files(project_path: str) -> list[str]:
    """Get list of changed files."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True, text=True, cwd=project_path, timeout=30,
        )
        unstaged = result.stdout.strip().splitlines() if result.stdout.strip() else []
        result2 = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, cwd=project_path, timeout=30,
        )
        staged = result2.stdout.strip().splitlines() if result2.stdout.strip() else []
        return list(set(unstaged + staged))
    except (subprocess.TimeoutExpired, OSError):
        return []


def _git_reset_hard(project_path: str) -> None:
    """Hard reset to discard all changes (rollback)."""
    try:
        subprocess.run(
            ["git", "checkout", "."],
            capture_output=True, text=True, cwd=project_path, timeout=30,
        )
        subprocess.run(
            ["git", "clean", "-fd"],
            capture_output=True, text=True, cwd=project_path, timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass


def _git_commit(project_path: str, message: str) -> bool:
    """Stage all changes and commit. Returns True on success."""
    try:
        subprocess.run(
            ["git", "add", "-A"],
            capture_output=True, text=True, cwd=project_path, timeout=30,
        )
        result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True, text=True, cwd=project_path, timeout=30,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


# ── Validation ───────────────────────────────────────────────────────


def validate_result(project_path: str, test_command: str | None = None) -> bool:
    """Run project tests. Returns True if they pass."""
    cmd = test_command or "python3 -m pytest"
    try:
        result = subprocess.run(
            cmd.split(),
            capture_output=True, text=True,
            cwd=project_path, timeout=300,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


# ── Task Execution ───────────────────────────────────────────────────


def execute_task(task: BuildTask, dry_run: bool = True) -> BuildResult:
    """Execute a single build task.

    Args:
        task: The build task to execute.
        dry_run: If True, show what would be done without executing.

    Returns:
        BuildResult with outcome details.
    """
    start = time.monotonic()

    # Dry run: just report what would happen
    if dry_run:
        system_prompt, user_prompt = build_prompt(task)
        return BuildResult(
            task=task,
            success=True,
            dry_run=True,
            agent_output=f"[DRY RUN] Would execute:\n\nSystem: {system_prompt[:200]}...\n\nTask: {user_prompt}",
            duration_seconds=round(time.monotonic() - start, 2),
        )

    # Check Hermes availability
    if not _hermes_available():
        return BuildResult(
            task=task,
            success=False,
            dry_run=False,
            error="Hermes Agent not available (missing API key or hermes-agent directory)",
            duration_seconds=round(time.monotonic() - start, 2),
        )

    project_path = task.project_path

    # Safety: stash existing changes
    had_stash = _git_stash(project_path)

    try:
        # Build prompt
        system_prompt, user_prompt = build_prompt(task)

        # Spawn agent
        logger.info("Build engine: executing task for %s — %s", task.project_name, task.dimension)
        agent_output = _spawn_agent(user_prompt, system_prompt, project_path)

        # Check what changed
        files_changed = _git_diff_files(project_path)

        # Validate: run tests
        tests_passed = validate_result(project_path, task.test_command)

        if tests_passed and files_changed:
            # Commit the improvements
            commit_msg = (
                f"forge({task.project_name}): improve {task.dimension}\n\n"
                f"{task.task[:200]}\n\n"
                f"Co-Authored-By: Oz <oz-agent@warp.dev>"
            )
            committed = _git_commit(project_path, commit_msg)

            # Re-score quality after commit (close the feedback loop)
            quality_before = None
            quality_after = None
            quality_delta = None
            try:
                from dharma_swarm.foreman import (
                    load_projects,
                    score_all_dimensions,
                    record_snapshot,
                    save_projects,
                )
                for proj in load_projects():
                    if proj.name == task.project_name:
                        quality_before = proj.last_score
                        new_dims = score_all_dimensions(proj, skip_tests=False)
                        quality_after = round(sum(new_dims.values()) / len(new_dims), 3) if new_dims else None
                        if quality_before is not None and quality_after is not None:
                            quality_delta = round(quality_after - quality_before, 3)
                        # Update project with new scores
                        proj.dimensions = new_dims
                        proj.last_score = quality_after
                        proj.last_grade = (
                            "A" if (quality_after or 0) >= 0.8 else
                            "B" if (quality_after or 0) >= 0.6 else
                            "C" if (quality_after or 0) >= 0.4 else
                            "D" if (quality_after or 0) >= 0.2 else "F"
                        )
                        all_projs = load_projects()
                        for i, ep in enumerate(all_projs):
                            if ep.path == proj.path:
                                all_projs[i] = proj
                                break
                        save_projects(all_projs)
                        record_snapshot([proj])
                        logger.info(
                            "Build engine: quality re-score %s: %.3f → %.3f (Δ%+.3f)",
                            task.project_name,
                            quality_before or 0,
                            quality_after or 0,
                            quality_delta or 0,
                        )
                        break
            except Exception as e:
                logger.warning("Build engine: quality re-score failed: %s", e)

            return BuildResult(
                task=task,
                success=True,
                dry_run=False,
                agent_output=agent_output,
                tests_passed=True,
                files_changed=files_changed,
                committed=committed,
                duration_seconds=round(time.monotonic() - start, 2),
                quality_before=quality_before,
                quality_after=quality_after,
                quality_delta=quality_delta,
            )
        elif not tests_passed:
            # Rollback: tests failed
            logger.warning("Build engine: tests failed for %s, rolling back", task.project_name)
            _git_reset_hard(project_path)
            return BuildResult(
                task=task,
                success=False,
                dry_run=False,
                agent_output=agent_output,
                tests_passed=False,
                files_changed=[],
                duration_seconds=round(time.monotonic() - start, 2),
                error="Tests failed after agent execution — changes rolled back",
            )
        else:
            # No changes made
            return BuildResult(
                task=task,
                success=True,
                dry_run=False,
                agent_output=agent_output,
                tests_passed=tests_passed,
                files_changed=[],
                duration_seconds=round(time.monotonic() - start, 2),
            )

    except Exception as e:
        # Safety: rollback on any error
        _git_reset_hard(project_path)
        return BuildResult(
            task=task,
            success=False,
            dry_run=False,
            error=f"Build engine error: {e}",
            duration_seconds=round(time.monotonic() - start, 2),
        )
    finally:
        # Restore stashed changes if we stashed them
        if had_stash:
            _git_stash_pop(project_path)


# ── Build Cycle ──────────────────────────────────────────────────────


def run_build_cycle(
    max_tasks: int = 3,
    max_minutes: float = MAX_CYCLE_MINUTES,
    dry_run: bool = True,
    project_filter: str | None = None,
) -> list[BuildResult]:
    """Pull tasks from the queue and execute them.

    Args:
        max_tasks: Maximum number of tasks to execute.
        max_minutes: Time budget for the entire cycle.
        dry_run: If True, show what would be done.
        project_filter: Only execute tasks for this project.

    Returns:
        List of BuildResult objects.
    """
    from dharma_swarm.foreman import load_projects, get_active_projects
    from dharma_swarm.iteration_depth import CompoundingQueue, IterationLedger

    queue = CompoundingQueue()
    queue.load()
    pending = queue.get_pending()

    if not pending:
        logger.info("Build cycle: no pending tasks in queue")
        return []

    # Map initiative IDs to projects
    ledger = IterationLedger()
    ledger.load()
    projects = {p.name: p for p in get_active_projects()}

    # Build tasks from queue items
    tasks: list[BuildTask] = []
    for item in pending:
        # Find which project this belongs to
        initiative = ledger.get(item.initiative_id)
        if not initiative:
            continue
        project_name = initiative.project
        if project_filter and project_name != project_filter:
            continue
        project = projects.get(project_name)
        if not project:
            continue

        tasks.append(BuildTask(
            queue_item_id=item.id,
            initiative_id=item.initiative_id,
            task=item.task,
            project_name=project_name,
            project_path=project.path,
            test_command=project.test_command,
            priority=item.priority,
        ))

    if not tasks:
        logger.info("Build cycle: no tasks matched filters")
        return []

    # Execute within time budget
    results: list[BuildResult] = []
    cycle_start = time.monotonic()

    for task in tasks[:max_tasks]:
        elapsed = (time.monotonic() - cycle_start) / 60
        if elapsed >= max_minutes:
            logger.info("Build cycle: time budget exhausted (%.1f min)", elapsed)
            break

        result = execute_task(task, dry_run=dry_run)
        results.append(result)

        # Mark completed in queue if successful (and not dry run)
        if result.success and not dry_run:
            queue.complete(task.queue_item_id)

            # Record iteration in ledger
            if result.files_changed:
                ledger.record_iteration(
                    initiative_id=task.initiative_id,
                    action=f"Build engine: {task.dimension} — {len(result.files_changed)} files changed",
                    evidence=f"files: {', '.join(result.files_changed[:5])}",
                    reviewer="build-engine",
                )

    return results


# ── Cron Integration ─────────────────────────────────────────────────


def build_run_fn(job: dict[str, Any]) -> tuple[bool, str, str | None]:
    """Cron tick run_fn: runs a build cycle.

    Signature matches tick(run_fn=...) → (success, output, error).
    """
    dry_run = job.get("prompt", "").strip().lower() != "live"
    try:
        results = run_build_cycle(dry_run=dry_run)
        lines = [f"# Build Engine — {'DRY RUN' if dry_run else 'LIVE'}", ""]
        for r in results:
            status = "✅" if r.success else "❌"
            lines.append(f"{status} **{r.task.project_name}** / {r.task.dimension}")
            lines.append(f"  Task: {r.task.task[:100]}")
            if r.files_changed:
                lines.append(f"  Changed: {', '.join(r.files_changed[:5])}")
            if r.committed:
                lines.append(f"  Committed: yes")
            if r.error:
                lines.append(f"  Error: {r.error}")
            lines.append(f"  Duration: {r.duration_seconds}s")
            lines.append("")

        if not results:
            lines.append("No tasks in queue.")

        output = "\n".join(lines)
        return True, output, None
    except Exception as e:
        logger.error("Build cycle failed: %s", e)
        return False, f"Build cycle failed: {e}", str(e)
