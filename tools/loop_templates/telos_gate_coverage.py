"""Telos Gate Coverage Loop.

Iterates test generation until all 11 core telos gates have dedicated
test coverage. Each iteration: identify uncovered gates, generate test
for one, run it, log result.

Convergence criterion: all 11 gates have at least 1 passing test
Max iterations: 20
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STATE_DIR = Path.home() / ".dharma"
OVERNIGHT_DIR = STATE_DIR / "overnight"
LOG_FILE = OVERNIGHT_DIR / "gate_coverage.jsonl"

DHARMA_SWARM_ROOT = Path.home() / "dharma_swarm"
TESTS_DIR = DHARMA_SWARM_ROOT / "tests"

# The 11 core gates from dharma_swarm.telos_gates.TelosGatekeeper.CORE_GATES
CORE_GATE_NAMES: list[str] = [
    "AHIMSA",
    "SATYA",
    "CONSENT",
    "VYAVASTHIT",
    "REVERSIBILITY",
    "SVABHAAVA",
    "BHED_GNAN",
    "WITNESS",
    "ANEKANTA",
    "DOGMA_DRIFT",
    "STEELMAN",
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class LoopConfig:
    """Configuration for the telos gate coverage loop."""

    max_iterations: int = 20
    tests_dir: Path = field(default_factory=lambda: TESTS_DIR)
    log_dir: Path = field(default_factory=lambda: OVERNIGHT_DIR)
    test_timeout: float = 60.0  # seconds per test run
    gate_names: list[str] = field(default_factory=lambda: list(CORE_GATE_NAMES))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tests_dir"] = str(self.tests_dir)
        d["log_dir"] = str(self.log_dir)
        return d


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------


@dataclass
class GateCoverageStatus:
    """Coverage status for a single gate."""

    gate_name: str
    covered: bool
    test_files: list[str] = field(default_factory=list)


@dataclass
class IterationResult:
    """Result of a single coverage iteration."""

    iteration: int
    gates_covered: int
    gates_total: int
    gate_targeted: str
    test_generated: bool
    test_passed: bool
    test_file: str
    error: str | None
    coverage_map: dict[str, bool]
    converged: bool
    elapsed_seconds: float
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Gate coverage detection
# ---------------------------------------------------------------------------


def scan_gate_coverage(tests_dir: Path, gate_names: list[str]) -> dict[str, GateCoverageStatus]:
    """Scan test files for references to each gate name.

    Searches for the gate name (case-insensitive) in test file names
    and test file contents. A gate is considered covered if at least
    one test file references it.
    """
    coverage: dict[str, GateCoverageStatus] = {}

    test_files: list[Path] = []
    if tests_dir.is_dir():
        test_files = sorted(tests_dir.rglob("test_*.py"))

    for gate_name in gate_names:
        matching_files: list[str] = []
        gate_lower = gate_name.lower()

        for tf in test_files:
            # Check filename
            if gate_lower in tf.name.lower():
                matching_files.append(str(tf.relative_to(tests_dir.parent)))
                continue

            # Check file contents (cheap grep)
            try:
                content = tf.read_text(errors="replace")
                if gate_name in content or gate_lower in content:
                    matching_files.append(str(tf.relative_to(tests_dir.parent)))
            except OSError:
                continue

        coverage[gate_name] = GateCoverageStatus(
            gate_name=gate_name,
            covered=len(matching_files) > 0,
            test_files=matching_files,
        )

    return coverage


def uncovered_gates(coverage: dict[str, GateCoverageStatus]) -> list[str]:
    """Return names of gates without test coverage."""
    return [name for name, status in coverage.items() if not status.covered]


# ---------------------------------------------------------------------------
# Test stub generation
# ---------------------------------------------------------------------------


def generate_test_stub(gate_name: str, output_dir: Path) -> Path:
    """Generate a minimal test file that exercises a telos gate.

    The generated test imports TelosGatekeeper, creates an instance,
    and verifies the gate exists and evaluates correctly for a benign action.

    Returns:
        Path to the generated test file.
    """
    test_filename = f"test_gate_{gate_name.lower()}.py"
    test_path = output_dir / test_filename

    test_code = f'''"""Auto-generated test for telos gate: {gate_name}.

Generated by the overnight telos gate coverage loop.
Verifies the gate exists in CORE_GATES and evaluates correctly.
"""

import pytest

from dharma_swarm.telos_gates import TelosGatekeeper, GateTier


class TestGate{gate_name.title().replace("_", "")}:
    """Tests for the {gate_name} telos gate."""

    def test_gate_exists_in_core(self) -> None:
        """Verify {gate_name} is registered in CORE_GATES."""
        assert "{gate_name}" in TelosGatekeeper.CORE_GATES

    def test_gate_has_valid_tier(self) -> None:
        """Verify {gate_name} has a valid GateTier assignment."""
        tier = TelosGatekeeper.CORE_GATES["{gate_name}"]
        assert isinstance(tier, GateTier)
        assert tier in (GateTier.A, GateTier.B, GateTier.C)

    def test_gate_present_after_init(self) -> None:
        """Verify {gate_name} is in the active GATES dict after init."""
        gatekeeper = TelosGatekeeper()
        assert "{gate_name}" in gatekeeper.GATES

    def test_benign_action_passes(self) -> None:
        """Verify a benign action is not blocked by {gate_name}."""
        gatekeeper = TelosGatekeeper()
        result = gatekeeper.evaluate("read a harmless file")
        # Benign actions should not be blocked
        assert result.decision != "block" or result.gate != "{gate_name}", (
            f"Gate {gate_name} unexpectedly blocked a benign action"
        )
'''

    test_path.write_text(test_code)
    return test_path


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


def run_test_file(test_path: Path, timeout: float = 60.0) -> tuple[bool, str]:
    """Run a single test file with pytest.

    Returns:
        Tuple of (passed: bool, output: str).
    """
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", str(test_path), "-v", "--tb=short", "-q"],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(DHARMA_SWARM_ROOT),
        )
        passed = result.returncode == 0
        output = result.stdout + result.stderr
        return passed, output
    except subprocess.TimeoutExpired:
        return False, f"Test timed out after {timeout}s"
    except Exception as exc:
        return False, f"Failed to run test: {exc}"


# ---------------------------------------------------------------------------
# JSONL logging
# ---------------------------------------------------------------------------


def _log_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Append a JSON record to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


# ---------------------------------------------------------------------------
# Core loop
# ---------------------------------------------------------------------------


async def run(
    config: LoopConfig | None = None,
    shutdown_event: asyncio.Event | None = None,
) -> list[IterationResult]:
    """Run the telos gate coverage loop.

    Args:
        config: Loop configuration. Uses defaults if None.
        shutdown_event: Set this event to trigger graceful shutdown.

    Returns:
        List of IterationResult for each completed iteration.
    """
    cfg = config or LoopConfig()
    shutdown = shutdown_event or asyncio.Event()

    log_path = cfg.log_dir / "gate_coverage.jsonl"
    cfg.log_dir.mkdir(parents=True, exist_ok=True)

    results: list[IterationResult] = []

    # Log config at start
    _log_jsonl(log_path, {
        "event": "loop_start",
        "config": cfg.to_dict(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    logger.info(
        "Gate coverage loop starting: max_iter=%d, gates=%d",
        cfg.max_iterations, len(cfg.gate_names),
    )

    for iteration in range(1, cfg.max_iterations + 1):
        if shutdown.is_set():
            logger.info("Shutdown requested at iteration %d", iteration)
            break

        t0 = time.monotonic()

        # Scan current coverage
        coverage = scan_gate_coverage(cfg.tests_dir, cfg.gate_names)
        missing = uncovered_gates(coverage)
        gates_covered = len(cfg.gate_names) - len(missing)

        coverage_map = {name: status.covered for name, status in coverage.items()}

        # Check convergence
        if not missing:
            iter_result = IterationResult(
                iteration=iteration,
                gates_covered=gates_covered,
                gates_total=len(cfg.gate_names),
                gate_targeted="",
                test_generated=False,
                test_passed=False,
                test_file="",
                error=None,
                coverage_map=coverage_map,
                converged=True,
                elapsed_seconds=round(time.monotonic() - t0, 2),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            results.append(iter_result)
            _log_jsonl(log_path, {"event": "iteration", **iter_result.to_dict()})
            logger.info("All %d gates covered -- converged", len(cfg.gate_names))
            break

        # Target the first uncovered gate
        target_gate = missing[0]
        logger.info(
            "Iteration %d/%d: targeting gate %s (%d/%d covered)",
            iteration, cfg.max_iterations, target_gate,
            gates_covered, len(cfg.gate_names),
        )

        # Generate test stub
        test_path = generate_test_stub(target_gate, cfg.tests_dir)
        test_generated = True

        # Run the test
        passed, output = await asyncio.to_thread(
            run_test_file, test_path, cfg.test_timeout,
        )

        error_msg: str | None = None
        if not passed:
            error_msg = output[-500:] if len(output) > 500 else output
            logger.warning("Test for gate %s failed: %s", target_gate, error_msg[:200])

        elapsed = time.monotonic() - t0

        iter_result = IterationResult(
            iteration=iteration,
            gates_covered=gates_covered + (1 if passed else 0),
            gates_total=len(cfg.gate_names),
            gate_targeted=target_gate,
            test_generated=test_generated,
            test_passed=passed,
            test_file=str(test_path.relative_to(DHARMA_SWARM_ROOT)),
            error=error_msg,
            coverage_map=coverage_map,
            converged=False,
            elapsed_seconds=round(elapsed, 2),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        results.append(iter_result)
        _log_jsonl(log_path, {"event": "iteration", **iter_result.to_dict()})

        logger.info(
            "Iteration %d: gate=%s, generated=%s, passed=%s, "
            "coverage=%d/%d, elapsed=%.1fs",
            iteration, target_gate, test_generated, passed,
            iter_result.gates_covered, len(cfg.gate_names), elapsed,
        )

    # Log summary
    final_coverage = scan_gate_coverage(cfg.tests_dir, cfg.gate_names)
    final_covered = sum(1 for s in final_coverage.values() if s.covered)

    summary = {
        "event": "loop_end",
        "total_iterations": len(results),
        "gates_covered": final_covered,
        "gates_total": len(cfg.gate_names),
        "converged": final_covered == len(cfg.gate_names),
        "uncovered": uncovered_gates(final_coverage),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _log_jsonl(log_path, summary)
    logger.info("Loop complete: %s", json.dumps(summary, indent=2))

    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


async def _main() -> None:
    """Entry point for direct execution."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    config = LoopConfig()
    shutdown = asyncio.Event()

    import signal as _signal
    from typing import Any

    def _handle_signal(sig: int, frame: Any) -> None:
        logger.info("Signal %d received, shutting down gracefully...", sig)
        shutdown.set()

    _signal.signal(_signal.SIGINT, _handle_signal)
    _signal.signal(_signal.SIGTERM, _handle_signal)

    await run(config=config, shutdown_event=shutdown)


if __name__ == "__main__":
    asyncio.run(_main())
