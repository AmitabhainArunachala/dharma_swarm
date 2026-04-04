---
title: 'Repo X-Ray: dharma_swarm'
path: reports/historical/xray_report.md
slug: repo-x-ray-dharma-swarm
doc_type: note
status: active
summary: 'Repo X-Ray: dharma swarm Generated 2026-03-14T02:02:51 UTC'
source:
  provenance: repo_local
  kind: note
  origin_signals:
  - dharma_swarm/xray.py
  - dharma_swarm/tui_legacy.py
  - dharma_swarm/thinkodynamic_director.py
  - dharma_swarm/dgc_cli.py
  - dharma_swarm/evolution.py
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- multi_agent_systems
- software_architecture
- research_methodology
- verification
- frontend_engineering
- operations
inspiration:
- operator_runtime
- research_synthesis
connected_python_files:
- dharma_swarm/xray.py
- dharma_swarm/tui_legacy.py
- dharma_swarm/thinkodynamic_director.py
- dharma_swarm/dgc_cli.py
- dharma_swarm/evolution.py
connected_python_modules:
- dharma_swarm.xray
- dharma_swarm.tui_legacy
- dharma_swarm.thinkodynamic_director
- dharma_swarm.dgc_cli
- dharma_swarm.evolution
connected_relevant_files:
- dharma_swarm/xray.py
- dharma_swarm/tui_legacy.py
- dharma_swarm/thinkodynamic_director.py
- dharma_swarm/dgc_cli.py
- dharma_swarm/evolution.py
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `.` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: note
  vault_path: reports/historical/xray_report.md
  retrieval_terms:
  - xray
  - repo
  - ray
  - generated
  - '2026'
  - 14t02
  - utc
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: active
  semantic_weight: 0.6
  coordination_comment: 'Repo X-Ray: dharma swarm Generated 2026-03-14T02:02:51 UTC'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising reports/historical/xray_report.md reinforces its salience without needing a separate message.
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
# Repo X-Ray: dharma_swarm
*Generated 2026-03-14T02:02:51 UTC*

## Overview
- **Path**: `/Users/dhyana/dharma_swarm`
- **Files analyzed**: 472
- **Total lines**: 198,412 (169,636 non-blank)
- **Languages**: docs: 889 files (0 lines) | config: 639 files (0 lines) | python: 464 files (197,109 lines) | javascript: 6 files (1,048 lines) | typescript: 2 files (255 lines)

## Architecture
### Top Modules
- **dharma_swarm**: 220 files, 96,127 lines, 607 classes, 3260 functions — Contains 0 classes, 11 functions
- **external**: 155 files, 79,560 lines, 130 classes, 1887 functions — Contains 1 classes, 15 functions
- **.worktrees**: 90 files, 21,485 lines, 198 classes, 816 functions — Contains 0 classes, 1 functions
- **.claude**: 5 files, 706 lines, 0 classes, 0 functions
- **(root)**: 1 files, 351 lines, 0 classes, 4 functions — Contains 0 classes, 4 functions
- **hooks**: 1 files, 183 lines, 0 classes, 2 functions — Contains 0 classes, 2 functions

### Module Connections
- `.worktrees` → `dharma_swarm`

## Code Quality Signals
**Overall Grade: C** (score: 0.40)

- **Test ratio**: 0% (2 test files)
- **Docstring coverage**: 72%
- **Naming conventions**: 100%
- **Type annotation rate**: 73%
- **Avg complexity per file**: 55.2

## Complexity Hotspots
Functions with the highest cyclomatic complexity:

- `run` in `external/hermes-agent/cli.py:3788` — complexity=157, 939 lines
- `_handle_message` in `external/hermes-agent/gateway/run.py:867` — complexity=131, 692 lines
- `_run_agent` in `external/hermes-agent/gateway/run.py:3019` — complexity=128, 588 lines
- `setup_model_provider` in `external/hermes-agent/hermes_cli/setup.py:634` — complexity=127, 703 lines
- `run_doctor` in `external/hermes-agent/hermes_cli/doctor.py:97` — complexity=124, 639 lines
- `process_command` in `external/hermes-agent/cli.py:2648` — complexity=91, 318 lines
- `analyze_repo` in `dharma_swarm/xray.py:424` — complexity=87, 312 lines
- `_session_browse_picker` in `external/hermes-agent/hermes_cli/main.py:128` — complexity=83, 271 lines
- `_handle_command` in `dharma_swarm/tui_legacy.py:807` — complexity=78, 278 lines
- `_handle_command` in `.worktrees/self-optimize/dharma_swarm/tui_legacy.py:829` — complexity=77, 277 lines

## Largest Files
- `dharma_swarm/thinkodynamic_director.py` — 4,920 lines (complexity=805)
- `dharma_swarm/dgc_cli.py` — 4,783 lines (complexity=627)
- `external/hermes-agent/cli.py` — 4,290 lines (complexity=858)
- `external/hermes-agent/gateway/run.py` — 3,360 lines (complexity=733)
- `external/hermes-agent/hermes_cli/main.py` — 2,766 lines (complexity=462)
- `dharma_swarm/evolution.py` — 2,392 lines (complexity=260)
- `dharma_swarm/tui/app.py` — 2,310 lines (complexity=529)

## External Dependencies
140 external packages: `@docusaurus/plugin-content-docs, @docusaurus/preset-classic, @docusaurus/types, PIL, adapters, agent, aiofiles, aiohttp, aiosqlite, anthropic, app, artifacts, atroposlib, backports, base, browser_tool, btw, child_process, chunker, clarify_tool`
*...and 120 more*

## Internal Coupling
Files with the most internal imports:

- `dharma_swarm/dgc_cli.py` imports 58 internal modules
- `dharma_swarm/swarm.py` imports 36 internal modules
- `dharma_swarm/evolution.py` imports 25 internal modules
- `.worktrees/self-optimize/dharma_swarm/swarm.py` imports 20 internal modules
- `dharma_swarm/tui/app.py` imports 13 internal modules
- `.worktrees/self-optimize/dharma_swarm/dgc_cli.py` imports 12 internal modules
- `dharma_swarm/pulse.py` imports 12 internal modules

## Risk Flags
- 🟡 **testing**: Low test ratio: 0% (test files / source files). Target: >50%.
- 🟡 **size**: Large file (997 lines). Consider splitting. (`.worktrees/self-optimize/dharma_swarm/evolution.py`)
- 🟡 **size**: Large file (1020 lines). Consider splitting. (`.worktrees/self-optimize/dharma_swarm/dgc_cli.py`)
- 🟡 **size**: Large file (1553 lines). Consider splitting. (`.worktrees/self-optimize/dharma_swarm/tui_legacy.py`)
- 🟡 **size**: Large file (738 lines). Consider splitting. (`.worktrees/self-optimize/dharma_swarm/tui/app.py`)
- 🟡 **size**: Large file (1082 lines). Consider splitting. (`external/hermes-agent/batch_runner.py`)
- 🟡 **size**: Large file (591 lines). Consider splitting. (`external/hermes-agent/mini_swe_runner.py`)
- 🟡 **size**: Large file (4290 lines). Consider splitting. (`external/hermes-agent/cli.py`)
- 🟡 **size**: Large file (1222 lines). Consider splitting. (`external/hermes-agent/trajectory_compressor.py`)
- 🟡 **size**: Large file (698 lines). Consider splitting. (`external/hermes-agent/hermes_state.py`)
- 🟡 **size**: Large file (828 lines). Consider splitting. (`external/hermes-agent/honcho_integration/session.py`)
- 🟡 **size**: Large file (666 lines). Consider splitting. (`external/hermes-agent/honcho_integration/cli.py`)
- 🟡 **size**: Large file (745 lines). Consider splitting. (`external/hermes-agent/tools/process_registry.py`)
- 🟡 **size**: Large file (1051 lines). Consider splitting. (`external/hermes-agent/tools/web_tools.py`)
- 🟡 **size**: Large file (1232 lines). Consider splitting. (`external/hermes-agent/tools/skills_hub.py`)

## Recommended Next Steps
1. Add tests for complex untested modules: garden_daemon.py, hooks/telos_gate.py, .worktrees/self-optimize/hooks/telos_gate.py
2. Refactor `run` in `external/hermes-agent/cli.py` (complexity=157). Extract helper functions.
3. Split large files: .worktrees/self-optimize/dharma_swarm/evolution.py, .worktrees/self-optimize/dharma_swarm/dgc_cli.py, .worktrees/self-optimize/dharma_swarm/tui_legacy.py (997+ lines each).
