"""Apply unified diffs to files with rollback and test integration.

Parses standard unified diff format, backs up affected files before
modification, and provides atomic apply-and-test: changes are kept only
when the test suite passes, rolled back otherwise.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class ApplyResult(BaseModel):
    """Outcome of applying a unified diff."""

    success: bool
    files_changed: list[str] = []
    backup_paths: dict[str, str] = {}  # original -> backup
    error: str = ""


class ApplyTestResult(BaseModel):
    """Outcome of apply-then-test cycle."""

    applied: bool
    tests_passed: bool
    tests_output: str = ""
    files_changed: list[str] = []
    rolled_back: bool = False
    error: str = ""


# ---------------------------------------------------------------------------
# Internal diff representation
# ---------------------------------------------------------------------------


@dataclass
class Hunk:
    """A single hunk from a unified diff."""

    src_start: int
    src_count: int
    dst_start: int
    dst_count: int
    lines: list[str] = field(default_factory=list)


@dataclass
class FilePatch:
    """All hunks targeting a single file."""

    old_path: str  # "a/foo.py" or "/dev/null"
    new_path: str  # "b/foo.py" or "/dev/null"
    hunks: list[Hunk] = field(default_factory=list)
    is_new_file: bool = False

    @property
    def target_path(self) -> str:
        """Return the effective file path (strip leading a/ or b/)."""
        if self.new_path == "/dev/null":
            return _strip_prefix(self.old_path)
        return _strip_prefix(self.new_path)


_HUNK_RE = re.compile(
    r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@"
)


def _strip_prefix(path: str) -> str:
    """Remove leading ``a/`` or ``b/`` prefix from diff paths."""
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path


# ---------------------------------------------------------------------------
# Diff parser
# ---------------------------------------------------------------------------


def parse_unified_diff(diff_text: str) -> list[FilePatch]:
    """Parse a unified diff into a list of per-file patches.

    Handles:
    - Single and multi-file diffs
    - Multi-hunk patches
    - New file creation (old path ``/dev/null``)
    - Context, addition, and removal lines

    Args:
        diff_text: The full unified diff string.

    Returns:
        A list of ``FilePatch`` objects.

    Raises:
        ValueError: If the diff contains malformed hunk headers.
    """
    patches: list[FilePatch] = []
    current_patch: FilePatch | None = None
    current_hunk: Hunk | None = None
    lines = diff_text.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]

        # --- / +++ pair signals a new file patch
        if line.startswith("--- "):
            old_path = line[4:].strip()
            # Expect +++ on the next line
            if i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
                new_path = lines[i + 1][4:].strip()
                is_new = old_path == "/dev/null"
                current_patch = FilePatch(
                    old_path=old_path,
                    new_path=new_path,
                    is_new_file=is_new,
                )
                patches.append(current_patch)
                current_hunk = None
                i += 2
                continue

        # Hunk header
        m = _HUNK_RE.match(line)
        if m and current_patch is not None:
            current_hunk = Hunk(
                src_start=int(m.group(1)),
                src_count=int(m.group(2)) if m.group(2) is not None else 1,
                dst_start=int(m.group(3)),
                dst_count=int(m.group(4)) if m.group(4) is not None else 1,
            )
            current_patch.hunks.append(current_hunk)
            i += 1
            continue

        # Hunk body: context, add, or remove lines
        if current_hunk is not None and line[:1] in (" ", "+", "-"):
            current_hunk.lines.append(line)
            i += 1
            continue

        # Skip diff metadata lines (diff --git, index, etc.)
        i += 1

    return patches


# ---------------------------------------------------------------------------
# DiffApplier
# ---------------------------------------------------------------------------


class DiffApplier:
    """Applies unified diffs to files safely with rollback capability.

    Args:
        workspace: Root directory for resolving relative paths in the diff.
            Defaults to the current working directory.
    """

    def __init__(self, workspace: Path | None = None) -> None:
        self.workspace = (workspace or Path.cwd()).resolve()

    # -- public API ---------------------------------------------------------

    async def apply(
        self, diff_text: str, dry_run: bool = False
    ) -> ApplyResult:
        """Parse and apply a unified diff.

        1. Parse the diff to extract file paths and hunks.
        2. Back up affected files.
        3. Apply changes.
        4. Return ``ApplyResult`` with files changed and backup paths.

        If *dry_run* is ``True``, validates the diff without writing.

        Args:
            diff_text: Unified diff text.
            dry_run: When set, only validate -- do not modify files.

        Returns:
            An ``ApplyResult`` describing what was (or would be) changed.
        """
        stripped = diff_text.strip()
        if not stripped:
            return ApplyResult(success=True)

        try:
            patches = parse_unified_diff(stripped)
        except ValueError as exc:
            return ApplyResult(success=False, error=str(exc))

        if not patches:
            return ApplyResult(success=True)

        files_changed: list[str] = []
        backup_paths: dict[str, str] = {}

        for patch in patches:
            target = self.workspace / patch.target_path

            # Validate: if not a new file, the target must exist
            if not patch.is_new_file and not target.exists():
                return ApplyResult(
                    success=False,
                    error=f"Target file does not exist: {patch.target_path}",
                    files_changed=files_changed,
                    backup_paths=backup_paths,
                )

            if dry_run:
                files_changed.append(patch.target_path)
                continue

            # Back up existing file
            if target.exists():
                backup = target.with_suffix(target.suffix + ".bak")
                shutil.copy2(str(target), str(backup))
                backup_paths[str(target)] = str(backup)

            # Apply hunks
            try:
                self._apply_patch(target, patch)
            except Exception as exc:
                return ApplyResult(
                    success=False,
                    error=f"Failed applying patch to {patch.target_path}: {exc}",
                    files_changed=files_changed,
                    backup_paths=backup_paths,
                )

            files_changed.append(patch.target_path)

        return ApplyResult(
            success=True,
            files_changed=files_changed,
            backup_paths=backup_paths,
        )

    async def rollback(self, result: ApplyResult) -> None:
        """Restore files from backups recorded in *result*.

        Args:
            result: A previous ``ApplyResult`` whose backups should be restored.
        """
        for original, backup in result.backup_paths.items():
            backup_path = Path(backup)
            original_path = Path(original)
            if backup_path.exists():
                shutil.copy2(str(backup_path), str(original_path))
                backup_path.unlink()
                logger.debug("Rolled back %s from %s", original, backup)

    async def apply_and_test(
        self,
        diff_text: str,
        test_command: str = "python3 -m pytest tests/ -q --tb=short",
        timeout: float = 120.0,
    ) -> ApplyTestResult:
        """Apply a diff, run tests, and rollback on failure.

        1. Apply the diff.
        2. Run *test_command* via subprocess.
        3. If tests pass (exit code 0): keep changes, return success.
        4. If tests fail: rollback and return failure with test output.

        Args:
            diff_text: Unified diff text.
            test_command: Shell command to validate the change.
            timeout: Maximum seconds to wait for the test command.

        Returns:
            An ``ApplyTestResult`` describing the outcome.
        """
        apply_result = await self.apply(diff_text)
        if not apply_result.success:
            return ApplyTestResult(
                applied=False,
                tests_passed=False,
                error=apply_result.error,
            )

        if not apply_result.files_changed:
            return ApplyTestResult(
                applied=True,
                tests_passed=True,
                files_changed=[],
            )

        # Run tests
        try:
            proc = await asyncio.create_subprocess_shell(
                test_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace),
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                # Rollback on timeout
                await self.rollback(apply_result)
                return ApplyTestResult(
                    applied=True,
                    tests_passed=False,
                    tests_output="Test command timed out",
                    files_changed=apply_result.files_changed,
                    rolled_back=True,
                    error=f"Test command timed out after {timeout}s",
                )

            output = stdout_bytes.decode(errors="replace")
            err_output = stderr_bytes.decode(errors="replace")
            combined = (output + "\n" + err_output).strip()
            returncode = proc.returncode if proc.returncode is not None else -1

        except OSError as exc:
            await self.rollback(apply_result)
            return ApplyTestResult(
                applied=True,
                tests_passed=False,
                tests_output="",
                files_changed=apply_result.files_changed,
                rolled_back=True,
                error=f"Failed to run test command: {exc}",
            )

        if returncode == 0:
            # Tests passed -- clean up backups
            for backup in apply_result.backup_paths.values():
                Path(backup).unlink(missing_ok=True)
            return ApplyTestResult(
                applied=True,
                tests_passed=True,
                tests_output=combined,
                files_changed=apply_result.files_changed,
            )

        # Tests failed -- rollback
        await self.rollback(apply_result)
        return ApplyTestResult(
            applied=True,
            tests_passed=False,
            tests_output=combined,
            files_changed=apply_result.files_changed,
            rolled_back=True,
        )

    # -- internal -----------------------------------------------------------

    @staticmethod
    def _apply_patch(target: Path, patch: FilePatch) -> None:
        """Apply all hunks from *patch* to *target*.

        For new files, creates the file with added lines.
        For existing files, applies hunks in reverse order to preserve
        line number validity.
        """
        if patch.is_new_file:
            target.parent.mkdir(parents=True, exist_ok=True)
            content_lines: list[str] = []
            for hunk in patch.hunks:
                for line in hunk.lines:
                    if line.startswith("+"):
                        content_lines.append(line[1:])
                    elif line.startswith(" "):
                        content_lines.append(line[1:])
            target.write_text("\n".join(content_lines) + "\n" if content_lines else "", encoding="utf-8")
            return

        source_lines = target.read_text(encoding="utf-8").splitlines()

        # Apply hunks in reverse order so earlier hunks don't shift later ones
        for hunk in reversed(patch.hunks):
            new_lines: list[str] = []
            for line in hunk.lines:
                if line.startswith("+"):
                    new_lines.append(line[1:])
                elif line.startswith(" "):
                    new_lines.append(line[1:])
                # "-" lines are removed (not added to new_lines)

            start = hunk.src_start - 1  # diff is 1-indexed
            end = start + hunk.src_count
            source_lines[start:end] = new_lines

        target.write_text("\n".join(source_lines) + "\n", encoding="utf-8")
