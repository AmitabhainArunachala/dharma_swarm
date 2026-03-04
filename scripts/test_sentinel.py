#!/usr/bin/env python3
"""
Watches for file changes in dharma_swarm and runs regression guard.
Designed to be launched as a background process during overnight builds.

Launch:
    nohup python3 ~/dharma_swarm/scripts/test_sentinel.py > ~/.dharma/logs/sentinel.log 2>&1 &
    echo $! > ~/.dharma/sentinel.pid
"""

import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

WATCH_DIR = Path.home() / "dharma_swarm" / "dharma_swarm"
TESTS_DIR = Path.home() / "dharma_swarm" / "tests"
STATE_FILE = Path.home() / ".dharma" / "sentinel_state.json"
ALERT_DIR = Path.home() / ".dharma" / "alerts"
STOP_FILE = Path.home() / ".dharma" / "STOP_BUILD"
POLL_INTERVAL = 30  # seconds
BASELINE = 203


def get_mtime_hash():
    """Get hash of all .py mtimes under watch dirs."""
    mtimes = []
    for d in [WATCH_DIR, TESTS_DIR]:
        if not d.exists():
            continue
        for f in d.rglob("*.py"):
            try:
                mtimes.append(f"{f}:{f.stat().st_mtime}")
            except OSError:
                pass
    return hash(tuple(sorted(mtimes)))


def run_tests():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line", "-x"],
        capture_output=True,
        text=True,
        cwd=str(Path.home() / "dharma_swarm"),
        timeout=600,
    )
    return result


def parse_passed(output):
    for line in (output or "").split("\n"):
        m = re.search(r"(\d+) passed", line)
        if m:
            return int(m.group(1))
    return 0


def alert(severity, message, details=None):
    ALERT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    alert_data = {
        "timestamp": datetime.now().isoformat(),
        "severity": severity,
        "message": message,
        "details": details or {},
    }
    alert_file = ALERT_DIR / f"test_{severity}_{ts}.json"
    alert_file.write_text(json.dumps(alert_data, indent=2))
    print(f"[ALERT-{severity.upper()}] {message}")


def main():
    print(f"[SENTINEL] Watching {WATCH_DIR}")
    print(f"[SENTINEL] Baseline: {BASELINE} tests")
    print(f"[SENTINEL] Poll interval: {POLL_INTERVAL}s")

    last_hash = None
    consecutive_failures = 0

    while True:
        if STOP_FILE.exists():
            print("[SENTINEL] STOP_BUILD detected. Halting.")
            break

        current_hash = get_mtime_hash()

        if current_hash != last_hash:
            last_hash = current_hash
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[SENTINEL] Change detected at {ts}. Running tests...")

            result = run_tests()
            passed = parse_passed(result.stdout + result.stderr)

            state = {
                "timestamp": datetime.now().isoformat(),
                "passed": passed,
                "baseline": BASELINE,
                "regression": passed < BASELINE,
                "consecutive_failures": consecutive_failures,
            }
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(state, indent=2))

            if passed < BASELINE:
                consecutive_failures += 1
                alert(
                    "critical",
                    f"REGRESSION: {passed}/{BASELINE} tests passed",
                    {
                        "stdout": result.stdout[-1000:],
                        "stderr": result.stderr[-500:],
                    },
                )

                if consecutive_failures >= 3:
                    alert(
                        "emergency",
                        f"3 consecutive regressions. STOPPING BUILD.",
                        {"consecutive_failures": consecutive_failures},
                    )
                    STOP_FILE.write_text(
                        f"Test regression at {datetime.now().isoformat()}"
                    )
                    break
            else:
                if consecutive_failures > 0:
                    alert("info", f"Regression resolved. {passed} tests passing.")
                consecutive_failures = 0
                print(f"[SENTINEL] OK: {passed} tests passed")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
