# Thinkodynamic Live Canary Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build and run an unattended live canary that evaluates whether repeated thinkodynamic cycles materially improve the next cycle's mission state.

**Architecture:** Add a small operator-grade canary module that shells into the real `thinkodynamic_director`, reads the live task board and generated artifacts, scores each cycle for behavioral quality, and writes machine-readable reports under `~/.dharma/logs/thinkodynamic_canary`. Launch it via tmux with bounded delegation so it can run unattended without flooding the task board.

**Tech Stack:** Python 3, sqlite3, subprocess, tmux, existing `dharma_swarm` CLI/runtime scripts.

---

### Task 1: Add the canary module

**Files:**
- Create: `dharma_swarm/thinkodynamic_canary.py`
- Test: `tests/test_thinkodynamic_canary.py`

**Step 1: Write the failing test**

Add tests for queue saturation, stale review detection, generic workflow detection, and successful delegation.

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_thinkodynamic_canary.py`
Expected: FAIL because the module does not exist yet.

**Step 3: Write minimal implementation**

Implement a module that:
- runs `thinkodynamic_director`
- snapshots task-board state before/after
- scores behavioral issues from `latest.json` and the summary markdown
- writes report payloads

**Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_thinkodynamic_canary.py`
Expected: PASS

### Task 2: Add operator launch surfaces

**Files:**
- Create: `scripts/thinkodynamic_live_canary.py`
- Create: `scripts/start_thinkodynamic_live_canary_tmux.sh`
- Create: `scripts/status_thinkodynamic_live_canary_tmux.sh`

**Step 1: Write the launcher wrappers**

Add a Python wrapper plus tmux start/status helpers that mirror the existing operator scripts.

**Step 2: Run the launcher in a bounded way**

Run: `bash scripts/start_thinkodynamic_live_canary_tmux.sh 1`
Expected: tmux session starts and writes `~/.dharma/logs/thinkodynamic_canary/latest.*`

### Task 3: Verify against live state

**Files:**
- Use: `scripts/system_integration_probe.py`
- Use: `scripts/start_verification_lane.sh`

**Step 1: Run focused verification**

Run:
- `pytest -q tests/test_thinkodynamic_canary.py`
- `python3 scripts/system_integration_probe.py`

Expected:
- unit tests pass
- integration probe completes and surfaces real live degradations honestly

**Step 2: Launch unattended lanes**

Run:
- `bash scripts/start_verification_lane.sh 8`
- `bash scripts/start_thinkodynamic_live_canary_tmux.sh 8`

Expected:
- verification lane records operator/daemon drift
- canary records whether each live mission cycle actually delegates, updates tasks, and avoids stale review reuse
