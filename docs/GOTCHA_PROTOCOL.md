---
title: Gotcha Protocol
path: docs/GOTCHA_PROTOCOL.md
slug: gotcha-protocol
doc_type: documentation
status: active
summary: A self-healing feedback system for dharma swarm. Gotchas are known pitfalls, anti-patterns, and footguns specific to this codebase that have burned us at least once. They exist so we never burn the same way twice.
source:
  provenance: repo_local
  kind: documentation
  origin_signals:
  - docs/GOTCHA_PROTOCOL.md
  - docs/plans/SPRINT_GOTCHAS.md
  - tools/feedback_collector.py
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- swarm_intelligence
- multi_agent_systems
- software_architecture
- verification
- frontend_engineering
- machine_learning
inspiration:
- stigmergy
- verification
connected_python_files:
- tools/feedback_collector.py
connected_python_modules:
- tools.feedback_collector
connected_relevant_files:
- docs/plans/SPRINT_GOTCHAS.md
- tools/feedback_collector.py
- docs/plans/ALLOUT_6H_MODE.md
- docs/plans/ALL_NIGHT_BUILD_CONCLAVE_2026-03-20.md
- docs/ASCII_STUDIO_SETUP.md
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `docs` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: documentation
  vault_path: docs/GOTCHA_PROTOCOL.md
  retrieval_terms:
  - gotcha
  - protocol
  - self
  - healing
  - feedback
  - system
  - gotchas
  - are
  - known
  - pitfalls
  - anti
  - patterns
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: working
  semantic_weight: 0.6
  coordination_comment: A self-healing feedback system for dharma swarm. Gotchas are known pitfalls, anti-patterns, and footguns specific to this codebase that have burned us at least once. They exist so we never burn the same way twice.
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/GOTCHA_PROTOCOL.md reinforces its salience without needing a separate message.
    marker_based:
      what_it_is: The frontmatter is an explicit annotation layer on top of the document.
      semantic_mark: Semantic weight, improvement prompts, related files, and provenance comments tell later agents how to use this document.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-01T00:43:19+09:00'
  curated_by_model: Codex (GPT-5)
  source_model_in_file: 
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Gotcha Protocol

A self-healing feedback system for dharma_swarm. Gotchas are known pitfalls,
anti-patterns, and footguns specific to this codebase that have burned us at
least once. They exist so we never burn the same way twice.

## What Is a Gotcha

A gotcha is a sharp edge that looks harmless until you cut yourself on it.
Wrong import path, frozen dataclass you tried to mutate, env var that silently
changes behavior, docstring that lies about the implementation. Every codebase
accumulates them. The difference is whether you write them down.

## Where Gotchas Live

Each skill file (`~/.claude/skills/*/SKILL.md`) has a `## Gotchas` section at
the bottom. Skill-level gotchas are scoped to that skill's domain.

System-wide gotchas live in two places:

- **This file** (`docs/GOTCHA_PROTOCOL.md`) -- the protocol and core examples
- **`docs/plans/SPRINT_GOTCHAS.md`** -- rolling log of errors encountered during
  development sprints, auto-populated by `tools/feedback_collector.py`

## Gotcha Format

Every gotcha entry follows the same four-field structure:

```
**Trigger**: What action or assumption caused the error
**Symptom**: What actually happened (error message, wrong behavior, silent failure)
**Fix**: How to resolve it when you hit it
**Prevention**: How to never hit it again
```

No prose. No hedging. Four fields, each one sentence.

## The Self-Healing Rule

**If you make a mistake executing a skill, immediately append to ## Gotchas
before continuing.**

This is not optional. This is not "when you have time." The gotcha gets written
while the pain is fresh, before you move on to the next thing. The system heals
itself only if every wound leaves a scar in the right place.

The sequence is:

1. Error occurs
2. Diagnose and fix the immediate problem
3. Write the gotcha entry (trigger/symptom/fix/prevention)
4. Append it to the relevant `## Gotchas` section
5. Now continue with your work

If you skip step 3, you will hit the same error again. Guaranteed.

## How to Add a New Gotcha

### To a skill file

Open the SKILL.md, find `## Gotchas` (create it if missing), append:

```markdown
---

**Trigger**: [what you did]
**Symptom**: [what went wrong]
**Fix**: [how to resolve]
**Prevention**: [how to avoid]
```

### To the sprint log

Run the feedback collector to auto-detect patterns:

```bash
python3 tools/feedback_collector.py --since 7 --output docs/plans/SPRINT_GOTCHAS.md
```

Or append manually to `docs/plans/SPRINT_GOTCHAS.md` using the same format.

### To this protocol document

Only add gotchas here if they are system-wide and fundamental -- things that
affect every developer and every agent working in this codebase.

## Core Gotchas (dharma_swarm)

These are the known system-wide sharp edges. Read them before writing any code.

---

**Trigger**: Running `claude -p` from inside a Claude Code session
**Symptom**: Subprocess hangs or fails silently because `CLAUDECODE` env var is set
**Fix**: Unset `CLAUDECODE` and `CLAUDE_CODE_ENTRYPOINT` before spawning subprocess
**Prevention**: Always unset these env vars in any code that shells out to `claude`

---

**Trigger**: Trying to mutate an `AgentSpec` instance after creation
**Symptom**: `FrozenInstanceError` -- AgentSpec is a frozen dataclass
**Fix**: Create a new AgentSpec with the desired changes using `dataclasses.replace()`
**Prevention**: Treat AgentSpec as immutable; use `replace()` for modifications

---

**Trigger**: Expecting `SignalBus` events to survive a process restart
**Symptom**: Events dispatched before restart are silently lost
**Fix**: Re-emit critical events on startup, or use stigmergy marks for durability
**Prevention**: SignalBus is in-process only. For durable signals, use StigmergyStore

---

**Trigger**: Calling `.dict()` on a Pydantic v2 model
**Symptom**: `DeprecationWarning` or `AttributeError` depending on Pydantic version
**Fix**: Use `.model_dump()` instead of `.dict()`
**Prevention**: This codebase uses Pydantic v2. Always use `model_dump()`, `model_validate()`, `model_json_schema()`

---

**Trigger**: Trusting the docstring in `orchestrate_live.py` about loop count
**Symptom**: You wire 7 loops but there are actually 10, missing 3 critical subsystems
**Fix**: Count the actual `asyncio.create_task()` calls in the function body
**Prevention**: When the docstring and the code disagree, the code is right. Always verify

---

**Trigger**: Running full test suite without `-x` flag during development
**Symptom**: 6-minute wait before seeing a failure that happened in the first 30 seconds
**Fix**: Use `python3 -m pytest tests/ -q --tb=short -x` to stop on first failure
**Prevention**: Always use `-x` during development. Full suite is for CI/pre-commit only

---

**Trigger**: Importing from `dharma_swarm` using relative paths from wrong directory
**Symptom**: `ModuleNotFoundError` or importing a stale cached version
**Fix**: Run from project root, or ensure package is pip-installed (`pip install -e .`)
**Prevention**: The package is pip-installed. Use absolute imports (`from dharma_swarm.X import Y`)

---

**Trigger**: Assuming `~/.dharma/` directories exist on first run
**Symptom**: `FileNotFoundError` when writing to state directories
**Fix**: Create the directory with `os.makedirs(path, exist_ok=True)`
**Prevention**: Always use `exist_ok=True` when writing to any `~/.dharma/` path

---

## Automated Collection

The `tools/feedback_collector.py` script scans conversation logs for recurring
error patterns and proposes gotcha entries automatically. Run it periodically:

```bash
# Scan last 7 days of logs
python3 tools/feedback_collector.py --since 7

# Write results to sprint log
python3 tools/feedback_collector.py --since 7 --output docs/plans/SPRINT_GOTCHAS.md
```

The collector detects:

- ImportError / ModuleNotFoundError patterns
- TypeError / ValueError patterns
- "not found" / "does not exist" file path issues
- Repeated tool calls to the same file (circular exploration)
- API connection failures
- Permission and environment variable issues

Each detected pattern is formatted as a gotcha entry ready for review.

## Philosophy

Gotchas are not documentation. Documentation tells you how things should work.
Gotchas tell you how things actually break. Both are necessary. Neither
substitutes for the other.

A codebase with zero gotchas is not a codebase with zero problems. It is a
codebase that has not learned from its problems yet.
