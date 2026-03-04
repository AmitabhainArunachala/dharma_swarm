#!/usr/bin/env python3
"""
Standalone regression guard. Returns exit code 0 if tests >= 202, else 1.
Writes machine-readable result to ~/.dharma/test_baseline.json.
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASELINE = 203
STATE_FILE = Path.home() / ".dharma" / "test_baseline.json"
DHARMA_SWARM = Path.home() / "dharma_swarm"


def run_tests():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line"],
        capture_output=True,
        text=True,
        cwd=str(DHARMA_SWARM),
        timeout=300,
    )
    return result


def parse_result(output):
    """Extract passed/failed counts from pytest output."""
    for line in output.strip().split("\n"):
        if "passed" in line:
            m = re.search(r"(\d+) passed", line)
            if m:
                passed = int(m.group(1))
                failed_m = re.search(r"(\d+) failed", line)
                failed = int(failed_m.group(1)) if failed_m else 0
                return passed, failed
    return 0, -1


def main():
    result = run_tests()
    passed, failed = parse_result(result.stdout + result.stderr)

    status = {
        "timestamp": datetime.now().isoformat(),
        "passed": passed,
        "failed": failed,
        "baseline": BASELINE,
        "regression": passed < BASELINE,
        "stdout_tail": result.stdout[-500:] if result.stdout else "",
        "stderr_tail": result.stderr[-500:] if result.stderr else "",
    }

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(status, indent=2))

    if passed < BASELINE:
        print(f"REGRESSION: {passed}/{BASELINE} tests passed")
        if failed > 0:
            print(f"  {failed} tests FAILED")
        print(result.stdout[-1000:])
        sys.exit(1)
    else:
        print(f"OK: {passed} tests passed (baseline: {BASELINE})")
        sys.exit(0)


if __name__ == "__main__":
    main()
