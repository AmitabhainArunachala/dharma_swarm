# DGC Unified Operator Shell Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** converge the terminal operator experience into one transcript-first, intent-first `dgc` shell without rewriting the `dharma_swarm` engine.

**Architecture:** add a thin `operator_shell` layer above the existing runtime, then route both the interactive Textual client and the batch CLI through shared shell contracts. Keep the first slice focused on shell convergence, copy/paste quality, and local capability indexing. Do not rewrite `swarm.py`, `orchestrator.py`, `agent_runner.py`, or `providers.py` in this plan.

**Tech Stack:** Python 3.11+, Textual, pathlib/dataclasses, pytest, existing `dharma_swarm` CLI/TUI modules

---

### Task 0: Create a clean execution lane

**Files:**
- Create: `../dharma_swarm-operator-shell-worktree/` (git worktree)

**Step 1: Create a dedicated worktree**

Run:

```bash
git -C /Users/dhyana/dharma_swarm worktree add ../dharma_swarm-operator-shell-worktree -b feat/dgc-operator-shell
```

Expected: a fresh worktree with the new branch and without the current dirty-tree collisions.

**Step 2: Verify entrypoint files are present**

Run:

```bash
ls /Users/dhyana/dharma_swarm-operator-shell-worktree/dharma_swarm/{dgc_cli.py,cli.py}
```

Expected: both files exist.

**Step 3: Use the worktree for all further tasks**

All remaining commands in this plan should run from the worktree root.

### Task 1: Scaffold the operator shell contracts

**Files:**
- Create: `dharma_swarm/operator_shell/__init__.py`
- Create: `dharma_swarm/operator_shell/models.py`
- Create: `dharma_swarm/operator_shell/intent.py`
- Test: `tests/test_operator_shell_intent.py`

**Step 1: Write the failing tests**

Add tests for:

```python
from dharma_swarm.operator_shell.intent import classify_input


def test_classify_input_marks_slash_commands() -> None:
    result = classify_input("/status")
    assert result.kind == "command"
    assert result.command_name == "status"


def test_classify_input_marks_plain_language_inspection() -> None:
    result = classify_input("show me what's broken")
    assert result.kind == "intent"
    assert result.intent_family == "system_inspection"


def test_classify_input_marks_plan_requests() -> None:
    result = classify_input("plan this before doing anything")
    assert result.recommended_mode == "plan"
```

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_operator_shell_intent.py -q
```

Expected: FAIL because `dharma_swarm.operator_shell.intent` does not exist yet.

**Step 3: Write minimal implementation**

Create simple contracts:

```python
@dataclass(frozen=True, slots=True)
class ShellIntent:
    raw: str
    kind: str
    command_name: str | None = None
    intent_family: str | None = None
    recommended_mode: str | None = None
    transparency_note: str | None = None
```

Implement `classify_input()` with:

- slash-command detection
- plan-language detection
- basic inspection/debug/help heuristics
- safe fallback to conversational intent

**Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_operator_shell_intent.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add dharma_swarm/operator_shell/__init__.py dharma_swarm/operator_shell/models.py dharma_swarm/operator_shell/intent.py tests/test_operator_shell_intent.py
git commit -m "feat: scaffold operator shell intent contracts"
```

### Task 2: Extract a shared operator command registry

**Files:**
- Create: `dharma_swarm/operator_shell/commands.py`
- Modify: `dharma_swarm/tui/commands/system_commands.py`
- Modify: `dharma_swarm/tui/commands/palette.py`
- Modify: `dharma_swarm/dgc_cli.py`
- Test: `tests/test_operator_shell_commands.py`
- Test: `tests/tui/test_system_commands.py`
- Test: `tests/test_dgc_cli.py`

**Step 1: Write the failing tests**

Add tests for:

```python
from dharma_swarm.operator_shell.commands import command_by_name, slash_command_names


def test_command_registry_contains_status() -> None:
    cmd = command_by_name("status")
    assert cmd is not None
    assert cmd.batch_name == "status"
    assert cmd.slash_name == "status"


def test_command_registry_exposes_palette_entries() -> None:
    names = slash_command_names()
    assert "status" in names
    assert "health" in names
```

Also add a TUI regression verifying `/status` still resolves, and a CLI regression verifying `dgc dashboard` and `dgc status` still dispatch through the shared registry.

**Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_operator_shell_commands.py tests/tui/test_system_commands.py tests/test_dgc_cli.py -q
```

Expected: FAIL because the registry does not exist and current callers are hard-coded.

**Step 3: Write minimal implementation**

Create a registry contract:

```python
@dataclass(frozen=True, slots=True)
class ShellCommand:
    batch_name: str
    slash_name: str
    category: str
    description: str
    aliases: tuple[str, ...] = ()
```

Populate the first shared set:

- `status`
- `health`
- `runtime`
- `dashboard`
- `plan`
- `model`
- `swarm`
- `logs`
- `dharma`
- `stigmergy`
- `hum`

Refactor:

- `SystemCommandHandler` to import command metadata instead of owning the canonical list
- `DGCCommandProvider` to build palette entries from the same registry
- `dgc_cli.py` help text and lookup helpers to read the same names/aliases

**Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/test_operator_shell_commands.py tests/tui/test_system_commands.py tests/test_dgc_cli.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add dharma_swarm/operator_shell/commands.py dharma_swarm/tui/commands/system_commands.py dharma_swarm/tui/commands/palette.py dharma_swarm/dgc_cli.py tests/test_operator_shell_commands.py tests/tui/test_system_commands.py tests/test_dgc_cli.py
git commit -m "refactor: centralize dgc operator command registry"
```

### Task 3: Add a shell router for intent-first behavior

**Files:**
- Create: `dharma_swarm/operator_shell/router.py`
- Modify: `dharma_swarm/tui/app.py`
- Test: `tests/test_operator_shell_router.py`
- Test: `tests/tui/test_app_interactive_e2e.py`
- Test: `tests/tui/test_app_plan_mode.py`

**Step 1: Write the failing tests**

Add tests for:

```python
from dharma_swarm.operator_shell.router import resolve_shell_action


def test_router_maps_plain_language_to_status_action() -> None:
    action = resolve_shell_action("show me what's broken")
    assert action.kind == "command"
    assert action.command_name in {"status", "health"}


def test_router_maps_plan_language_to_mode_switch() -> None:
    action = resolve_shell_action("plan this before touching code")
    assert action.kind == "mode_switch"
    assert action.mode == "plan"
```

Add TUI regressions verifying:

- plain language intent can produce a visible transparency note
- plan-language input can switch into plan mode before execution

**Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_operator_shell_router.py tests/tui/test_app_interactive_e2e.py tests/tui/test_app_plan_mode.py -q
```

Expected: FAIL because the shell router does not exist yet.

**Step 3: Write minimal implementation**

Create a shell action contract:

```python
@dataclass(frozen=True, slots=True)
class ShellAction:
    kind: str
    command_name: str | None = None
    mode: str | None = None
    transparency_note: str | None = None
```

Implement `resolve_shell_action()` using:

- `classify_input()`
- command registry lookup
- small transparent heuristics for plan/help/inspection

Modify `DGCApp` submission flow so it:

- classifies input
- writes a small system note when it auto-resolves intent
- switches mode if needed
- routes to slash-command execution or provider submission

**Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/test_operator_shell_router.py tests/tui/test_app_interactive_e2e.py tests/tui/test_app_plan_mode.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add dharma_swarm/operator_shell/router.py dharma_swarm/tui/app.py tests/test_operator_shell_router.py tests/tui/test_app_interactive_e2e.py tests/tui/test_app_plan_mode.py
git commit -m "feat: add intent-first operator shell routing"
```

### Task 4: Build the local capability registry

**Files:**
- Create: `dharma_swarm/operator_shell/capabilities.py`
- Create: `dharma_swarm/operator_shell/capability_sources.py`
- Test: `tests/test_operator_shell_capabilities.py`

**Step 1: Write the failing tests**

Add tests for:

```python
from pathlib import Path

from dharma_swarm.operator_shell.capabilities import index_local_capabilities


def test_index_local_capabilities_detects_codex_skill(tmp_path: Path) -> None:
    skill = tmp_path / "skills" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# Demo", encoding="utf-8")
    result = index_local_capabilities(
        codex_skills_root=tmp_path / "skills",
        claude_skills_root=tmp_path / "missing",
    )
    assert any(item.kind == "skill" for item in result)


def test_index_local_capabilities_tracks_source_system() -> None:
    ...
```

Cover:

- Codex skills
- Claude skills
- Claude agents
- Claude commands
- Agni workspace skills
- trust/source metadata

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_operator_shell_capabilities.py -q
```

Expected: FAIL because the capability indexer does not exist.

**Step 3: Write minimal implementation**

Create:

```python
@dataclass(frozen=True, slots=True)
class CapabilityRecord:
    capability_id: str
    name: str
    kind: str
    source_system: str
    source_path: str
    summary: str
    trust_tier: str
    promotion_status: str = "indexed"
```

Implement first-pass local sources for:

- `~/.codex/skills`
- `~/.claude/skills`
- `~/.claude/agents`
- `~/.claude/commands`
- `~/agni-workspace/skills`
- `~/agni-workspace/scratch/obsidian-skills`

Keep it local-only in this phase. Do **not** add GitHub/social intake here.

**Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_operator_shell_capabilities.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add dharma_swarm/operator_shell/capabilities.py dharma_swarm/operator_shell/capability_sources.py tests/test_operator_shell_capabilities.py
git commit -m "feat: add local operator capability registry"
```

### Task 5: Make the transcript shell copy-first

**Files:**
- Modify: `dharma_swarm/tui/widgets/stream_output.py`
- Modify: `dharma_swarm/tui/widgets/prompt_input.py`
- Modify: `dharma_swarm/tui/app.py`
- Modify: `dharma_swarm/tui/theme/dharma_dark.tcss`
- Test: `tests/tui/test_app_interactive_e2e.py`
- Test: `tests/tui/test_stream_output_observability.py`

**Step 1: Write the failing tests**

Add tests for:

- copy-last still returns clean assistant text after intent-first routing
- transparency notes do not pollute copied assistant replies
- tool summaries stay compact by default
- prompt input keeps multiline ergonomics with plain Enter send

Minimal example:

```python
def test_transparency_note_not_in_last_reply(...):
    ...
    assert stream.get_last_reply() == "real assistant reply"
```

**Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/tui/test_app_interactive_e2e.py tests/tui/test_stream_output_observability.py -q
```

Expected: FAIL on the new expectations.

**Step 3: Write minimal implementation**

Adjust the transcript widgets so:

- shell guidance lines render as system text
- assistant reply tracking ignores guidance/system notes
- tool summaries stay compact unless expanded
- inline behavior remains the default path for supported terminals

Keep UI work narrowly focused on transcript ergonomics, not dashboard redesign.

**Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/tui/test_app_interactive_e2e.py tests/tui/test_stream_output_observability.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add dharma_swarm/tui/widgets/stream_output.py dharma_swarm/tui/widgets/prompt_input.py dharma_swarm/tui/app.py dharma_swarm/tui/theme/dharma_dark.tcss tests/tui/test_app_interactive_e2e.py tests/tui/test_stream_output_observability.py
git commit -m "feat: polish transcript-first dgc shell ergonomics"
```

### Task 6: Route batch CLI through the shell layer

**Files:**
- Modify: `dharma_swarm/dgc_cli.py`
- Modify: `dharma_swarm/cli.py`
- Create: `dharma_swarm/operator_shell/batch.py`
- Test: `tests/test_dgc_cli.py`

**Step 1: Write the failing tests**

Add regressions for:

- batch help text reflecting the shared registry
- `dgc` defaulting to interactive transcript shell
- `dharma-swarm` remaining compatible but clearly secondary
- command alias resolution matching the registry

**Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_dgc_cli.py -q
```

Expected: FAIL on the new CLI expectations.

**Step 3: Write minimal implementation**

Create a tiny batch adapter:

```python
def run_batch_command(name: str, args: list[str]) -> int:
    ...
```

Then refactor:

- `dgc_cli.py` to use the shell registry for command lookup and help generation
- `cli.py` to either delegate into shell-compatible operations or clearly mark compatibility-only behavior

Do not remove `cli.py` in this phase.

**Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/test_dgc_cli.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add dharma_swarm/dgc_cli.py dharma_swarm/cli.py dharma_swarm/operator_shell/batch.py tests/test_dgc_cli.py
git commit -m "refactor: route dgc batch commands through operator shell"
```

### Task 7: Demote legacy paths without breaking launch

**Files:**
- Modify: `dharma_swarm/tui_launcher.py`
- Modify: `dharma_swarm/dgc_cli.py`
- Test: `tests/test_dgc_cli.py`
- Test: `tests/test_tui.py`

**Step 1: Write the failing tests**

Add tests that verify:

- legacy TUI remains a fallback only
- user-facing copy identifies the new transcript shell as canonical
- `dgc ui` / `dgc dashboard` descriptions no longer imply multiple competing terminal products

**Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_dgc_cli.py tests/test_tui.py -q
```

Expected: FAIL on updated user-facing copy and fallback expectations.

**Step 3: Write minimal implementation**

Update launcher and help text so:

- the new transcript shell is explicitly canonical
- legacy is described as fallback/compatibility only
- operator surface help no longer reads as split-brain

Keep fallback behavior intact for this slice.

**Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/test_dgc_cli.py tests/test_tui.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add dharma_swarm/tui_launcher.py dharma_swarm/dgc_cli.py tests/test_dgc_cli.py tests/test_tui.py
git commit -m "chore: demote legacy dgc tui paths"
```

### Task 8: Run the focused verification bundle

**Files:**
- Test: `tests/test_operator_shell_intent.py`
- Test: `tests/test_operator_shell_commands.py`
- Test: `tests/test_operator_shell_router.py`
- Test: `tests/test_operator_shell_capabilities.py`
- Test: `tests/test_dgc_cli.py`
- Test: `tests/tui/test_system_commands.py`
- Test: `tests/tui/test_app_interactive_e2e.py`
- Test: `tests/tui/test_app_plan_mode.py`
- Test: `tests/tui/test_stream_output_observability.py`
- Test: `tests/test_tui.py`

**Step 1: Run the full focused suite**

Run:

```bash
pytest tests/test_operator_shell_intent.py tests/test_operator_shell_commands.py tests/test_operator_shell_router.py tests/test_operator_shell_capabilities.py tests/test_dgc_cli.py tests/tui/test_system_commands.py tests/tui/test_app_interactive_e2e.py tests/tui/test_app_plan_mode.py tests/tui/test_stream_output_observability.py tests/test_tui.py -q
```

Expected: PASS.

**Step 2: Run one interactive smoke**

Run:

```bash
python3 -m dharma_swarm.dgc_cli --tui
```

Expected: transcript-first shell launches cleanly, prompt accepts multiline input, and `Ctrl+P`/slash commands still work.

**Step 3: Summarize follow-on work**

Record that the next lane after this plan is:

- capability promotion rules
- trusted GitHub repo watcher in quarantine
- later: broader field/skill seeker

**Step 4: Commit**

```bash
git add .
git commit -m "feat: land unified dgc operator shell slice"
```
