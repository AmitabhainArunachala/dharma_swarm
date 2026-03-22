# Dharma Swarm Audit And Merge Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Audit the current `dharma_swarm` codebase, merge the active checkpoint working tree onto fresh `origin/main`, and publish a verified integration branch to GitHub.

**Architecture:** Work from a clean worktree based on `origin/main`, preserve the user's active dirty checkout untouched, import the checkpoint working tree with explicit exclusions for generated artifacts, then run an audit/verification pass to separate pre-existing failures from merge regressions before pushing.

**Tech Stack:** Git worktrees, Python 3.11, pytest, FastAPI, Next.js dashboard, shell rsync/git tooling.

---

### Task 1: Capture The Remote Baseline

**Files:**
- Create: `docs/plans/2026-03-22-dharma-swarm-audit-merge.md`
- Modify: none
- Test: baseline `pytest` run from repo root

**Step 1: Verify clean starting branch**

Run: `git status --short --branch`
Expected: clean `audit/merge-2026-03-22` tracking `origin/main`

**Step 2: Run baseline test suite on untouched `origin/main`**

Run: `python3 -m pytest -q`
Expected: pass or a documented baseline failure list

**Step 3: Record baseline risks**

Run: `git log --oneline --decorate main..origin/main`
Expected: note remote commits not yet merged into local `main`

### Task 2: Import The Checkpoint Working Tree Safely

**Files:**
- Modify: broad repo import into clean worktree
- Test: `git status --short`, targeted diff inspection

**Step 1: Copy the active checkpoint working tree into the audit worktree**

Run: `rsync -az --delete --exclude '.git' --exclude '.worktrees' --exclude '__pycache__' --exclude 'dashboard/test-results' --exclude 'desktop-shell/src-tauri/target' /Users/dhyana/dharma_swarm/ /Users/dhyana/dharma_swarm/.worktrees/audit-merge-20260322/`
Expected: working tree matches checkpoint content without generated artifacts

**Step 2: Inspect imported diff against `origin/main`**

Run: `git status --short`
Expected: staged/untracked delta reflects actual code and docs changes, not build output

**Step 3: Audit obvious hygiene failures**

Run: `git status --porcelain=v1 --untracked-files=all | sed -n '1,200p'`
Expected: no vendored build trees or transient files intended for commit

### Task 3: Resolve Blocking Merge Regressions

**Files:**
- Modify: touched Python modules, API routes, dashboard files, and `.gitignore` if generated files leak in
- Test: focused pytest selections for changed subsystems

**Step 1: Identify failing tests after import**

Run: `python3 -m pytest -q`
Expected: failing tests point to merge conflicts or stale assumptions

**Step 2: Fix the minimum blocking issues**

Run: targeted edit loop on the failing modules and tests
Expected: merge branch converges without rewriting unrelated behavior

**Step 3: Re-run focused suites around touched areas**

Run: `python3 -m pytest -q tests/test_api.py tests/test_context.py tests/test_providers.py tests/test_sleep_cycle.py`
Expected: touched backend areas pass or produce a narrowed remaining issue list

### Task 4: Verify The Merged Branch

**Files:**
- Modify: only files required by audit fixes
- Test: full repo verification

**Step 1: Run full test suite again**

Run: `python3 -m pytest -q`
Expected: clean pass or explicitly documented residual failures

**Step 2: Review final diff**

Run: `git diff --stat origin/main...HEAD`
Expected: branch contains intended merged content only

**Step 3: Summarize audit findings**

Run: capture blocking, high, and medium findings from code/test audit
Expected: concise audit report suitable for PR description

### Task 5: Publish To GitHub

**Files:**
- Modify: git history only
- Test: remote branch visibility

**Step 1: Commit the merged work**

Run: `git add -A && git commit -m "audit: merge checkpoint updates onto origin/main"`
Expected: single integration commit or a small coherent commit set

**Step 2: Push the audit branch**

Run: `git push -u origin audit/merge-2026-03-22`
Expected: GitHub branch published successfully

**Step 3: Open or report PR details**

Run: `gh pr create --base main --head audit/merge-2026-03-22 --title "Audit and merge checkpoint updates" --body "<summary>"`
Expected: PR URL or equivalent branch handoff details
