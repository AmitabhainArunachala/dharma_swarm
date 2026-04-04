#!/usr/bin/env python3
"""
morning_after.py — Morning-After Audit Runner for Dharmic Quant Build

Run this AFTER the 25-agent build completes:
  python3 ~/dharma_swarm/scripts/morning_after.py

Steps:
  1. Check worktree status — which agents completed?
  2. List worktree branches and their changes
  3. Run full audit on current state
  4. Apply safe fixes (install missing deps)
  5. Run ginko test suite
  6. Generate merge recommendation
  7. Print executive summary + next steps

Does NOT auto-merge. Gives you the information to merge safely.
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

DHARMA_SWARM = Path.home() / "dharma_swarm"
SRC = DHARMA_SWARM / "dharma_swarm"
TESTS = DHARMA_SWARM / "tests"
AUDIT_HOME = Path.home() / ".dharma" / "ginko" / "audit"


def run(cmd: list[str], cwd: str | None = None, timeout: int = 30) -> tuple[int, str]:
    """Run command, return (returncode, output)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"
    except Exception as e:
        return -1, str(e)


def banner(text: str):
    print(f"\n{'=' * 72}")
    print(f"  {text}")
    print(f"{'=' * 72}\n")


def section(text: str):
    print(f"\n--- {text} ---\n")


def main():
    start = time.time()
    banner(f"DHARMIC QUANT — MORNING AFTER AUDIT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # ── Step 1: Worktree Status ───────────────────────────────────
    section("STEP 1: WORKTREE STATUS")
    code, output = run(["git", "worktree", "list"], cwd=str(DHARMA_SWARM))
    worktrees = [l.strip() for l in output.split("\n") if l.strip()]
    print(f"  Active worktrees: {len(worktrees)}")
    for wt in worktrees:
        print(f"    {wt}")

    # Count agent worktrees (typically named with agent descriptions)
    agent_wts = [w for w in worktrees if "dharma_swarm" in w and w != worktrees[0]]
    print(f"\n  Agent worktrees: {len(agent_wts)}")
    if agent_wts:
        print("  These contain build output. Review diffs before merging.")

    # ── Step 2: Worktree Diffs ────────────────────────────────────
    section("STEP 2: WORKTREE CHANGES SUMMARY")
    for wt_line in agent_wts:
        wt_path = wt_line.split()[0]
        code, diff_stat = run(
            ["git", "diff", "--stat", "HEAD"],
            cwd=wt_path, timeout=10,
        )
        if diff_stat and diff_stat != "TIMEOUT":
            print(f"  {Path(wt_path).name}:")
            for line in diff_stat.split("\n")[-5:]:
                print(f"    {line}")
            print()

    # ── Step 3: File Manifest Check ───────────────────────────────
    section("STEP 3: BUILD OUTPUT — FILE CHECK")
    expected_new = [
        "ginko_agents.py", "agent_registry.py", "ginko_sec.py",
        "ginko_paper_trade.py", "ginko_report_gen.py", "ginko_live_test.py",
    ]
    expected_tests = [
        "test_ginko_data_integration.py", "test_ginko_sec.py",
        "test_ginko_paper_trade.py", "test_ginko_report_gen.py",
        "test_ginko_integration.py",
    ]
    expected_other = ["Dockerfile", "docker-compose.yml"]
    expected_docs = ["yc_w27_application.md", "substack_first_issue.md", "hn_launch_post.md"]

    created = 0
    missing = 0

    print("  Source modules:")
    for f in expected_new:
        path = SRC / f
        exists = path.exists()
        size = path.stat().st_size if exists else 0
        status = f"  OK ({size:,} bytes)" if exists else "  MISSING"
        print(f"    {'[+]' if exists else '[X]'} {f}{status}")
        created += exists
        missing += not exists

    print("\n  Test files:")
    for f in expected_tests:
        path = TESTS / f
        exists = path.exists()
        print(f"    {'[+]' if exists else '[X]'} {f}")
        created += exists
        missing += not exists

    print("\n  Infrastructure:")
    for f in expected_other:
        path = DHARMA_SWARM / f
        exists = path.exists()
        print(f"    {'[+]' if exists else '[X]'} {f}")
        created += exists
        missing += not exists

    print("\n  Documentation:")
    for f in expected_docs:
        path = DHARMA_SWARM / "docs" / f
        exists = path.exists()
        print(f"    {'[+]' if exists else '[X]'} docs/{f}")
        created += exists
        missing += not exists

    print(f"\n  TOTAL: {created} created, {missing} missing")

    # Check for files in worktrees that aren't merged yet
    if missing > 0 and agent_wts:
        print("\n  Checking worktrees for missing files...")
        for wt_line in agent_wts:
            wt_path = Path(wt_line.split()[0])
            for f in expected_new:
                candidate = wt_path / "dharma_swarm" / f
                if candidate.exists() and not (SRC / f).exists():
                    print(f"    FOUND in worktree: {f} at {wt_path.name}")

    # ── Step 4: Run Full Audit ────────────────────────────────────
    section("STEP 4: FULL AUDIT")
    try:
        # Import and run the audit engine
        sys.path.insert(0, str(DHARMA_SWARM))
        from dharma_swarm.ginko_audit import GinkoAuditor

        auditor = GinkoAuditor()
        report = auditor.build_report(mode="morning_after")
        path = auditor.save_report(report)
        print(auditor.format_terminal_report(report))
        print(f"\n  Report saved: {path}")
    except ImportError as e:
        print(f"  Could not import ginko_audit: {e}")
        print("  Running audit via subprocess...")
        code, output = run(
            ["python3", "-m", "dharma_swarm.ginko_audit"],
            cwd=str(DHARMA_SWARM), timeout=120,
        )
        print(output)
    except Exception as e:
        print(f"  Audit failed: {e}")

    # ── Step 5: Install Missing Deps ──────────────────────────────
    section("STEP 5: DEPENDENCY CHECK")
    deps_to_check = ["httpx", "fastapi", "uvicorn", "numpy", "pydantic"]
    for dep in deps_to_check:
        code, _ = run(["python3", "-c", f"import {dep}"])
        status = "installed" if code == 0 else "MISSING"
        print(f"  {dep}: {status}")
        if code != 0:
            print(f"    Installing {dep}...")
            run(["pip", "install", dep], timeout=60)

    # ── Step 6: Test Suite ────────────────────────────────────────
    section("STEP 6: GINKO TEST SUITE")
    import glob
    test_files = sorted(glob.glob(str(TESTS / "test_ginko_*.py")))
    print(f"  Found {len(test_files)} ginko test files")

    if test_files:
        code, output = run(
            ["python3", "-m", "pytest"] + test_files + ["-v", "--tb=short"],
            cwd=str(DHARMA_SWARM), timeout=180,
        )
        # Show last 30 lines
        lines = output.split("\n")
        for line in lines[-30:]:
            print(f"  {line}")
        print(f"\n  Exit code: {code} {'(PASS)' if code == 0 else '(FAIL)'}")

    # ── Step 7: Executive Summary ─────────────────────────────────
    elapsed = time.time() - start
    banner("EXECUTIVE SUMMARY")
    print(f"  Build files: {created}/{created + missing} created")
    print(f"  Worktrees: {len(agent_wts)} agent worktrees pending merge")
    print(f"  Audit time: {elapsed:.1f}s")
    print()
    print("  NEXT STEPS:")
    print("  1. Review worktree diffs: git -C <worktree> diff --stat")
    print("  2. Merge completed worktrees into trunk")
    print("  3. Run: python3 -m dharma_swarm.ginko_audit --fix")
    print("  4. Run: python3 -m pytest tests/test_ginko_*.py -v")
    print("  5. Run: python3 -m dharma_swarm.ginko_audit --enhancements")
    print("  6. Launch enhancement wave (see docs/plans/GINKO_ENHANCEMENT_WAVE.md)")
    print()
    print("  ENHANCEMENT WAVE LAUNCH:")
    print("  python3 -m dharma_swarm.ginko_audit --enhancements | head -50")
    print()


if __name__ == "__main__":
    main()
