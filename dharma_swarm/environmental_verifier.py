"""Environmental verifier — ground truth over self-assessment.

Agents cannot reliably fix their own failures (Principle #3). This module
provides EXTERNAL verification: did the file change? did the test pass?
did the state change as predicted?

Tiered verification (consequence-proportional):
  - Read-only: no verification needed
  - Reversible writes: Layer 1 (deterministic checks)
  - Irreversible writes: Layer 1 + Layer 2 (semantic checks)
  - External/high-stakes: Layer 1 + Layer 2 + Layer 3 (adversarial)

Grounded in: SYNTHESIS.md P0 #5, Principle #3
Sources: Anthropic effective agents, Devin lessons, SWE-bench top systems
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_FILE_MUTATION_VERBS = {"write", "edit", "create", "update", "append", "rewrite"}


class VerificationTier(str, Enum):
    """How deeply to verify, based on blast radius."""
    NONE = "none"           # Read-only, no verification
    DETERMINISTIC = "L1"    # Schema, format, file existence
    SEMANTIC = "L2"         # LLM-based meaning check
    ADVERSARIAL = "L3"      # Red team / cross-review


class BlastRadius(str, Enum):
    """How much damage can this action cause."""
    READ_ONLY = "read_only"
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"
    EXTERNAL = "external"


class VerificationStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


@dataclass
class VerificationCheck:
    """A single verification check result."""
    name: str
    tier: VerificationTier
    status: VerificationStatus
    message: str = ""
    expected: Any = None
    actual: Any = None


@dataclass
class VerificationResult:
    """Complete verification result for an action."""
    action_id: str = ""
    timestamp: str = ""
    tier: VerificationTier = VerificationTier.NONE
    checks: list[VerificationCheck] = field(default_factory=list)
    overall: VerificationStatus = VerificationStatus.SKIP
    prediction_error: float = 0.0  # |expected - actual| for precision updating

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    @property
    def passed(self) -> bool:
        return self.overall == VerificationStatus.PASS

    @property
    def failed_checks(self) -> list[VerificationCheck]:
        return [c for c in self.checks if c.status == VerificationStatus.FAIL]


def classify_blast_radius(
    action_type: str,
    target: str = "",  # noqa: ARG001
    is_external: bool = False,
) -> BlastRadius:
    """Classify action blast radius for verification tier selection.

    Args:
        action_type: The type of action (read, write, delete, api_call, etc.)
        target: The target path or resource
        is_external: Whether this affects external systems
    """
    if is_external:
        return BlastRadius.EXTERNAL

    read_actions = {"read", "scan", "search", "query", "list", "check"}
    if action_type.lower() in read_actions:
        return BlastRadius.READ_ONLY

    # Destructive patterns
    destructive_patterns = {"delete", "drop", "truncate", "rm", "force", "reset"}
    if any(p in action_type.lower() for p in destructive_patterns):
        return BlastRadius.IRREVERSIBLE

    # Everything else is reversible (file writes, edits, etc.)
    return BlastRadius.REVERSIBLE


def select_tier(blast_radius: BlastRadius) -> VerificationTier:
    """Select verification tier based on blast radius."""
    return {
        BlastRadius.READ_ONLY: VerificationTier.NONE,
        BlastRadius.REVERSIBLE: VerificationTier.DETERMINISTIC,
        BlastRadius.IRREVERSIBLE: VerificationTier.SEMANTIC,
        BlastRadius.EXTERNAL: VerificationTier.ADVERSARIAL,
    }[blast_radius]


# ---------------------------------------------------------------------------
# Layer 1: Deterministic checks
# ---------------------------------------------------------------------------

def check_file_exists(path: str) -> VerificationCheck:
    """Verify a file exists."""
    exists = Path(path).exists()
    return VerificationCheck(
        name="file_exists",
        tier=VerificationTier.DETERMINISTIC,
        status=VerificationStatus.PASS if exists else VerificationStatus.FAIL,
        message=f"{'Exists' if exists else 'Missing'}: {path}",
        expected=True,
        actual=exists,
    )


def check_file_changed(path: str, previous_mtime: float) -> VerificationCheck:
    """Verify a file was modified after a given timestamp."""
    p = Path(path)
    if not p.exists():
        return VerificationCheck(
            name="file_changed",
            tier=VerificationTier.DETERMINISTIC,
            status=VerificationStatus.FAIL,
            message=f"File does not exist: {path}",
            expected="modified",
            actual="missing",
        )

    current_mtime = p.stat().st_mtime
    changed = current_mtime > previous_mtime
    return VerificationCheck(
        name="file_changed",
        tier=VerificationTier.DETERMINISTIC,
        status=VerificationStatus.PASS if changed else VerificationStatus.FAIL,
        message=f"{'Modified' if changed else 'Unchanged'}: {path}",
        expected="modified",
        actual="modified" if changed else "unchanged",
    )


def check_file_not_empty(path: str) -> VerificationCheck:
    """Verify a file is not empty."""
    p = Path(path)
    if not p.exists():
        return VerificationCheck(
            name="file_not_empty",
            tier=VerificationTier.DETERMINISTIC,
            status=VerificationStatus.FAIL,
            message=f"File does not exist: {path}",
        )

    size = p.stat().st_size
    return VerificationCheck(
        name="file_not_empty",
        tier=VerificationTier.DETERMINISTIC,
        status=VerificationStatus.PASS if size > 0 else VerificationStatus.FAIL,
        message=f"Size: {size} bytes",
        expected=">0",
        actual=size,
    )


def check_valid_json(path: str) -> VerificationCheck:
    """Verify a file contains valid JSON."""
    p = Path(path)
    if not p.exists():
        return VerificationCheck(
            name="valid_json",
            tier=VerificationTier.DETERMINISTIC,
            status=VerificationStatus.FAIL,
            message=f"File does not exist: {path}",
        )

    try:
        json.loads(p.read_text())
        return VerificationCheck(
            name="valid_json",
            tier=VerificationTier.DETERMINISTIC,
            status=VerificationStatus.PASS,
            message="Valid JSON",
        )
    except json.JSONDecodeError as e:
        return VerificationCheck(
            name="valid_json",
            tier=VerificationTier.DETERMINISTIC,
            status=VerificationStatus.FAIL,
            message=f"Invalid JSON: {e}",
        )


def check_valid_python(path: str) -> VerificationCheck:
    """Verify a file contains valid Python syntax."""
    p = Path(path)
    if not p.exists():
        return VerificationCheck(
            name="valid_python",
            tier=VerificationTier.DETERMINISTIC,
            status=VerificationStatus.FAIL,
            message=f"File does not exist: {path}",
        )

    try:
        compile(p.read_text(), path, "exec")
        return VerificationCheck(
            name="valid_python",
            tier=VerificationTier.DETERMINISTIC,
            status=VerificationStatus.PASS,
            message="Valid Python syntax",
        )
    except SyntaxError as e:
        return VerificationCheck(
            name="valid_python",
            tier=VerificationTier.DETERMINISTIC,
            status=VerificationStatus.FAIL,
            message=f"Syntax error: {e}",
        )


async def check_tests_pass(
    test_path: str,
    cwd: str | None = None,
    timeout: int = 120,
) -> VerificationCheck:
    """Run pytest on a specific test file/pattern and check if it passes."""
    cmd = ["python3", "-m", "pytest", test_path, "-q", "--tb=short", "-x"]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, _stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )

        passed = proc.returncode == 0
        output = stdout.decode()[:500]

        return VerificationCheck(
            name="tests_pass",
            tier=VerificationTier.DETERMINISTIC,
            status=VerificationStatus.PASS if passed else VerificationStatus.FAIL,
            message=output if passed else f"Tests failed (rc={proc.returncode}): {output}",
            expected="exit 0",
            actual=f"exit {proc.returncode}",
        )
    except asyncio.TimeoutError:
        return VerificationCheck(
            name="tests_pass",
            tier=VerificationTier.DETERMINISTIC,
            status=VerificationStatus.ERROR,
            message=f"Timeout after {timeout}s: {test_path}",
        )
    except Exception as e:
        return VerificationCheck(
            name="tests_pass",
            tier=VerificationTier.DETERMINISTIC,
            status=VerificationStatus.ERROR,
            message=f"Error running tests: {e}",
        )


def check_process_alive(pid: int) -> VerificationCheck:
    """Verify a process is running."""
    try:
        os.kill(pid, 0)
        return VerificationCheck(
            name="process_alive",
            tier=VerificationTier.DETERMINISTIC,
            status=VerificationStatus.PASS,
            message=f"PID {pid} is alive",
        )
    except ProcessLookupError:
        return VerificationCheck(
            name="process_alive",
            tier=VerificationTier.DETERMINISTIC,
            status=VerificationStatus.FAIL,
            message=f"PID {pid} is dead",
            expected="alive",
            actual="dead",
        )
    except PermissionError:
        return VerificationCheck(
            name="process_alive",
            tier=VerificationTier.DETERMINISTIC,
            status=VerificationStatus.PASS,
            message=f"PID {pid} exists (permission denied)",
        )


def _is_auto_verified_file_action(action_type: str, target: str) -> bool:
    """Return True when a generic file-mutation action should trigger file checks."""
    if not target:
        return False

    path = Path(target)
    if path.exists() and path.is_dir():
        return False

    action = action_type.lower()
    if action in {"write", "edit", "create"}:
        return True

    tokens = {token for token in re.split(r"[^a-z0-9]+", action) if token}
    return "file" in tokens and bool(tokens & _FILE_MUTATION_VERBS)


def _append_check_if_missing(
    checks: list[VerificationCheck],
    existing_names: set[str],
    check: VerificationCheck,
) -> None:
    """Append a check once by name.

    Explicit expectations win. Auto-generated target checks should fill gaps
    rather than creating duplicate entries with the same semantic meaning.
    """
    if check.name in existing_names:
        return
    checks.append(check)
    existing_names.add(check.name)


# ---------------------------------------------------------------------------
# Composite verifier
# ---------------------------------------------------------------------------

async def verify_action(
    action_id: str,
    action_type: str,
    target: str = "",
    expectations: dict[str, Any] | None = None,
    is_external: bool = False,
    test_path: str | None = None,
    test_cwd: str | None = None,
) -> VerificationResult:
    """Run verification appropriate to the action's blast radius.

    Args:
        action_id: Unique identifier for the action
        action_type: What kind of action (write, delete, api_call, etc.)
        target: Target path or resource
        expectations: Dict of expected outcomes (file_exists, file_changed_after, etc.)
        is_external: Whether this affects external systems
        test_path: Optional test file to run
        test_cwd: Working directory for tests

    Returns:
        VerificationResult with all check results
    """
    expectations = expectations or {}
    blast = classify_blast_radius(action_type, target, is_external)
    tier = select_tier(blast)

    result = VerificationResult(
        action_id=action_id,
        tier=tier,
    )

    if tier == VerificationTier.NONE:
        result.overall = VerificationStatus.SKIP
        return result

    # Layer 1: Deterministic checks
    checks: list[VerificationCheck] = []
    existing_names: set[str] = set()

    if "file_exists" in expectations:
        _append_check_if_missing(
            checks, existing_names, check_file_exists(expectations["file_exists"])
        )

    if "file_changed_after" in expectations and target:
        _append_check_if_missing(
            checks, existing_names, check_file_changed(target, expectations["file_changed_after"])
        )

    if "file_not_empty" in expectations:
        _append_check_if_missing(
            checks, existing_names, check_file_not_empty(expectations["file_not_empty"])
        )

    if "valid_json" in expectations:
        _append_check_if_missing(
            checks, existing_names, check_valid_json(expectations["valid_json"])
        )

    if "valid_python" in expectations:
        _append_check_if_missing(
            checks, existing_names, check_valid_python(expectations["valid_python"])
        )

    if "process_alive" in expectations:
        _append_check_if_missing(
            checks, existing_names, check_process_alive(expectations["process_alive"])
        )

    # Auto-check: generic file mutations should still validate the target file
    # even when callers provide only partial expectations (for example,
    # file_changed_after without syntax validation).
    if _is_auto_verified_file_action(action_type, target):
        if "file_exists" not in expectations:
            _append_check_if_missing(checks, existing_names, check_file_exists(target))
        if "file_not_empty" not in expectations:
            _append_check_if_missing(checks, existing_names, check_file_not_empty(target))
        if target.endswith(".py"):
            if "valid_python" not in expectations:
                _append_check_if_missing(
                    checks, existing_names, check_valid_python(target)
                )
        elif target.endswith(".json"):
            if "valid_json" not in expectations:
                _append_check_if_missing(
                    checks, existing_names, check_valid_json(target)
                )

    # Run tests if specified
    if test_path:
        test_check = await check_tests_pass(test_path, cwd=test_cwd)
        checks.append(test_check)

    result.checks = checks

    # Compute overall
    if not checks:
        result.overall = VerificationStatus.SKIP
    elif any(c.status == VerificationStatus.FAIL for c in checks):
        result.overall = VerificationStatus.FAIL
    elif any(c.status == VerificationStatus.ERROR for c in checks):
        result.overall = VerificationStatus.ERROR
    else:
        result.overall = VerificationStatus.PASS

    # Compute prediction error (for precision updating)
    total = len(checks)
    failed = len([c for c in checks if c.status in (VerificationStatus.FAIL, VerificationStatus.ERROR)])
    result.prediction_error = failed / total if total > 0 else 0.0

    return result
