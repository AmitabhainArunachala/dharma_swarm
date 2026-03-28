# Provider Matrix Harness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a first-class `dgc provider-matrix` harness that runs a fixed prompt corpus across a curated provider/model matrix, keeps `Codex + Opus` as sovereign lanes, and writes operator-facing leaderboard artifacts.

**Architecture:** Add a new `dharma_swarm/provider_matrix.py` module that derives target lanes from `model_hierarchy.py`, probes them through `runtime_provider.py`, scores structured responses against a fixed corpus, and emits machine + human-readable summaries. Wire a new `provider-matrix` CLI command in `dgc_cli.py`, document the operator workflow, and keep tests focused on target selection, budget enforcement, result scoring, artifact writing, and CLI dispatch.

**Tech Stack:** Python 3.14, pytest, existing runtime provider factories, canonical model hierarchy, Markdown/JSON artifact generation.

---

### Task 1: Add failing tests for the matrix harness core

**Files:**
- Create: `tests/test_provider_matrix.py`
- Test: `tests/test_provider_matrix.py`

**Step 1: Write the failing test**

```python
def test_build_default_matrix_targets_preserves_sovereign_lanes():
    targets = build_default_matrix_targets(profile="live25", env={})
    assert targets[0].provider is ProviderType.CODEX
    assert targets[1].provider in {ProviderType.CLAUDE_CODE, ProviderType.ANTHROPIC}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_provider_matrix.py -q`
Expected: FAIL because the module and helpers do not exist yet.

**Step 3: Write minimal implementation**

```python
def build_default_matrix_targets(...):
    return []
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_provider_matrix.py -q`
Expected: PASS after the harness module is implemented.

**Step 5: Commit**

```bash
git add tests/test_provider_matrix.py dharma_swarm/provider_matrix.py
git commit -m "feat: add provider matrix harness core"
```

### Task 2: Add failing tests for CLI wiring

**Files:**
- Modify: `tests/test_dgc_cli.py`
- Modify: `dharma_swarm/dgc_cli.py`

**Step 1: Write the failing test**

```python
def test_dgc_cli_provider_matrix_dispatch():
    ...
    assert kwargs["profile"] == "live25"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_dgc_cli.py -q -k provider_matrix`
Expected: FAIL because the parser/dispatcher do not know `provider-matrix`.

**Step 3: Write minimal implementation**

```python
def cmd_provider_matrix(...):
    ...
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_dgc_cli.py -q -k provider_matrix`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_dgc_cli.py dharma_swarm/dgc_cli.py
git commit -m "feat: wire provider matrix CLI"
```

### Task 3: Implement artifacts and docs

**Files:**
- Modify: `dharma_swarm/provider_matrix.py`
- Add: `docs/PROVIDER_MATRIX_HARNESS.md`

**Step 1: Write the failing test**

```python
def test_run_provider_matrix_writes_leaderboard_artifacts(tmp_path):
    payload = run_provider_matrix(...)
    assert Path(payload["artifacts"]["json_path"]).exists()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_provider_matrix.py -q`
Expected: FAIL because artifact generation is not implemented yet.

**Step 3: Write minimal implementation**

```python
def _write_artifacts(...):
    ...
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_provider_matrix.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add dharma_swarm/provider_matrix.py docs/PROVIDER_MATRIX_HARNESS.md
git commit -m "docs: add provider matrix operator guide"
```
