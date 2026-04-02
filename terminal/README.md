---
title: Dharma Terminal
path: terminal/README.md
slug: dharma-terminal
doc_type: readme
status: reference
summary: This package is the replacement seam for the current Python dgc terminal UI.
source:
  provenance: repo_local
  kind: readme
  origin_signals:
  - dharma_swarm/dgc_cli.py
  - dharma_swarm/tui_launcher.py
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- software_architecture
- product_strategy
- frontend_engineering
- operations
inspiration:
- operator_runtime
connected_python_files:
- dharma_swarm/dgc_cli.py
- dharma_swarm/tui_launcher.py
- dharma_swarm/terminal_bridge.py
connected_python_modules:
- dharma_swarm.dgc_cli
- dharma_swarm.tui_launcher
- dharma_swarm.terminal_bridge
connected_relevant_files:
- dharma_swarm/dgc_cli.py
- dharma_swarm/tui_launcher.py
- dharma_swarm/terminal_bridge.py
- terminal/README.md
improvement:
  room_for_improvement:
  - Keep entry points and commands aligned with the current runtime.
  - Add sharper cross-links into the most active specs, tests, and dashboards.
  - Make shipped behavior vs. exploratory material explicit.
  - Review whether this file should stay in `terminal` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: readme
  vault_path: terminal/README.md
  retrieval_terms:
  - terminal
  - package
  - replacement
  - seam
  - current
  - python
  - dgc
  evergreen_potential: high
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: canonical
  semantic_weight: 0.9
  coordination_comment: This package is the replacement seam for the current Python dgc terminal UI.
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising terminal/README.md reinforces its salience without needing a separate message.
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
# Dharma Terminal

This package is the replacement seam for the current Python `dgc` terminal UI.

## Why it exists

The current operator terminal surface is split across:

- a large Python CLI in `dharma_swarm/dgc_cli.py`
- a Textual TUI in `dharma_swarm/tui/`
- legacy fallback launch behavior in `dharma_swarm/tui_launcher.py`

That seam is hard to keep clean. This package moves the terminal presentation
layer to Bun + React + Ink while keeping Python as the runtime and provider
adapter core.

## Architecture

- `src/index.tsx`: Ink entrypoint
- Python bridge: `python3 -m dharma_swarm.terminal_bridge stdio`
- Protocol: line-delimited JSON over stdio

The bridge exposes:

- handshake/provider discovery
- slash-command execution through `SystemCommandHandler`
- streamed provider events through the existing Python adapter layer

## Intended usage

```bash
cd terminal
bun install
bun run src/index.tsx
```

## Current status

This is the new seam scaffold, not yet a complete replacement for all DGC TUI
features. The point is to establish a clean operator shell boundary first.
