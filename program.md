# dharma_swarm autoresearch

Adapted from [karpathy/autoresearch](https://github.com/karpathy/autoresearch).
Instead of training a model and measuring val_bpb, you improve a living codebase
and measure **test pass rate + zero regressions**.

## Setup

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `mar14`).
   The branch `autoresearch/<tag>` must not already exist.
2. **Create the branch**: `git checkout -b autoresearch/<tag>` from current HEAD.
3. **Read context**: Read these files for orientation:
   - `CLAUDE.md` — system identity, architecture, rules.
   - `dharma_swarm/evolution.py` — Darwin Engine (the system you're improving).
   - `dharma_swarm/swarm.py` — SwarmManager (agent orchestration).
   - `dharma_swarm/dse_integration.py` — DSE integration (monad + sheaf).
   - `tests/` — the test suite that is your ground truth metric.
4. **Run baseline**: `python3 -m pytest tests/ -q --tb=no 2>&1 | tail -5`
   Record the baseline pass/fail count.
5. **Initialize results.tsv**: Create `results.tsv` with the header row.
6. **Confirm and go**.

## The Metric

Your single metric is the **test suite**:

```bash
python3 -m pytest tests/ -q --tb=line 2>&1 | tail -5
```

A change is **good** if:
- Tests passing >= baseline (zero regressions)
- Tests passing > previous best (new tests added that pass), OR
- Tests passing == previous AND code is simpler/cleaner (simplification win)

A change is **bad** if:
- Any previously-passing test now fails (regression)
- New tests fail
- Code crashes

## What You CAN Do

You modify files under `dharma_swarm/` and `tests/`. Everything is fair game:

- **Fix bugs** — find failing edge cases, harden error handling
- **Add tests** — increase coverage for under-tested modules
- **Refactor** — simplify complex functions, remove dead code
- **Optimize** — reduce unnecessary allocations, speed up hot paths
- **Improve types** — add type annotations, fix Pyright warnings
- **Wire disconnected modules** — find orphaned code and connect it

## What You CANNOT Do

- Modify files outside `dharma_swarm/` and `tests/` (no touching CLAUDE.md, hooks/, etc.)
- Delete tests to make the suite pass (that's cheating)
- Add external dependencies not already in pyproject.toml
- Break the public API of existing classes (SwarmManager, DarwinEngine, etc.)
- Touch `.dharma/` state files or running daemon state

## Priorities (Descending)

1. Fix actual bugs (tests that fail, edge cases that crash)
2. Add tests for untested code paths
3. Simplify complex code while maintaining behavior
4. Type safety improvements
5. Performance optimizations
6. Wire orphaned modules into the runtime

## Scope Guide

The codebase is ~83K lines across ~90 Python files. Focus areas by impact:

| Module | Lines | Tests | Priority |
|--------|-------|-------|----------|
| evolution.py | ~2000 | test_evolution.py | HIGH — the core engine |
| swarm.py | ~800 | test_swarm.py | HIGH — orchestration |
| dse_integration.py | ~380 | test_dse_integration.py | MEDIUM — new, needs hardening |
| monad.py | ~200 | test_monad_laws.py | MEDIUM — mathematical core |
| coalgebra.py | ~300 | test_coalgebra.py | MEDIUM — evolution stream |
| sheaf.py | ~460 | test_sheaf.py | MEDIUM — coordination layer |
| providers.py | ~600 | test_providers.py | HIGH — LLM integration |
| agent_runner.py | ~400 | test_agent_runner.py | HIGH — task execution |
| archive.py | ~220 | test_archive.py | LOW — stable |
| metrics.py | ~410 | test_metrics.py | LOW — stable |

## Output Format

After running the test suite, extract:
```bash
# Get pass/fail/skip counts
python3 -m pytest tests/ -q --tb=no 2>&1 | tail -3
```

## Logging Results

Log to `results.tsv` (tab-separated). Do NOT commit this file.

```
commit	tests_passed	tests_failed	status	description
```

1. git commit hash (short, 7 chars)
2. tests passed count
3. tests failed count
4. status: `keep`, `discard`, or `crash`
5. short description of what this experiment tried

Example:
```
commit	tests_passed	tests_failed	status	description
a1b2c3d	2203	12	keep	baseline
b2c3d4e	2210	12	keep	add 7 tests for dse_integration edge cases
c3d4e5f	2210	13	discard	refactor sheaf coordination (broke test_sheaf)
d4e5f6g	2215	10	keep	fix 2 pre-existing failures in test_swarm + add tests
```

## The Experiment Loop

LOOP FOREVER:

1. Look at the git state and previous results in `results.tsv`
2. Pick a target: scan for untested code, bugs, complexity, or orphaned modules
3. Make a focused change (one logical unit — don't mix concerns)
4. `git add` the changed files and `git commit`
5. Run the test suite: `python3 -m pytest tests/ -q --tb=line > run.log 2>&1`
6. Extract results: `tail -5 run.log`
7. If crashed: `tail -50 run.log`, attempt fix or skip
8. Record results in `results.tsv`
9. If tests_passed >= baseline AND tests_failed <= baseline: **keep** (advance branch)
10. If regression (tests_failed increased OR tests_passed decreased): `git reset --hard HEAD~1` (discard)

**Strategy evolution**: After every 10 experiments, review `results.tsv` to see what's
working. Shift focus toward what produces the most improvement. If you've been adding
tests for 10 rounds, try refactoring. If refactoring keeps failing, go back to tests.

**Timeout**: The test suite should finish in ~2 minutes. If it hangs for >5 minutes, kill
and treat as crash.

**NEVER STOP**: Once the loop begins, do NOT pause to ask the human. The human might be
asleep. You are autonomous. If you run out of obvious improvements, dig deeper — read
modules you haven't touched, look at test coverage gaps, find subtle bugs in error
handling, check for race conditions in async code, look for dead code to remove. The loop
runs until the human interrupts you, period.

At ~2 minutes per test run + ~3 minutes for analysis/coding, expect ~12 experiments/hour,
~100 experiments overnight.

## Current Baseline

As of March 14 2026: **3017 passed, 0 failed, 3 skipped** (~2 min runtime).
This is your floor. Never go below 3017 passing.

## Simplicity Criterion

All else being equal, simpler is better. A test that adds coverage is great. A refactor
that reduces line count while maintaining behavior is great. Adding complexity for marginal
improvement is not worth it.
