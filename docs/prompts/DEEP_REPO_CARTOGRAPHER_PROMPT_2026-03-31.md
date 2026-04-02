---
title: Deep Repo Cartographer Prompt
path: docs/prompts/DEEP_REPO_CARTOGRAPHER_PROMPT_2026-03-31.md
slug: deep-repo-cartographer-prompt
doc_type: documentation
status: active
summary: Use this when you need an agent to read dharma swarm deeply enough to build a reliable map, not just a superficial summary.
source:
  provenance: repo_local
  kind: documentation
  origin_signals:
  - scripts/repo_xray.py
  - README.md
  - CLAUDE.md
  - docs/architecture/NAVIGATION.md
  - pyproject.toml
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- multi_agent_systems
- software_architecture
- knowledge_management
- verification
- product_strategy
- frontend_engineering
inspiration:
- operator_runtime
- product_surface
connected_python_files:
- scripts/repo_xray.py
- api/main.py
- dharma_swarm/swarm.py
- dharma_swarm/agent_runner.py
- dharma_swarm/orchestrator.py
connected_python_modules:
- scripts.repo_xray
- api.main
- dharma_swarm.swarm
- dharma_swarm.agent_runner
- dharma_swarm.orchestrator
connected_relevant_files:
- scripts/repo_xray.py
- README.md
- CLAUDE.md
- docs/architecture/NAVIGATION.md
- pyproject.toml
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `docs` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: documentation
  vault_path: docs/prompts/DEEP_REPO_CARTOGRAPHER_PROMPT_2026-03-31.md
  retrieval_terms:
  - deep
  - repo
  - cartographer
  - prompt
  - '2026'
  - use
  - when
  - you
  - need
  - agent
  - read
  - deeply
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: working
  semantic_weight: 0.6
  coordination_comment: Use this when you need an agent to read dharma swarm deeply enough to build a reliable map, not just a superficial summary.
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/prompts/DEEP_REPO_CARTOGRAPHER_PROMPT_2026-03-31.md reinforces its salience without needing a separate message.
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
# Deep Repo Cartographer Prompt

Use this when you need an agent to read `dharma_swarm` deeply enough to build a reliable map, not just a superficial summary.

## Prompt

You are the deep cartographer for the `dharma_swarm` codebase.

Your job is not to admire the repo. Your job is to establish a defensible map of what is actually here, what is central, what is auxiliary, what is narrative-only, and what appears to be live product surface.

You must work in multiple passes and use multiple lenses. Do not rely on one scan, one README, one LLM summary, or one architectural document.

Repository root:

- `/Users/dhyana/dharma_swarm`

Primary objective:

- produce a living map of the repository that an operator can use to navigate, modify, and finish the project across local and cloud environments

Required outputs:

1. A canonical repo map with:
   - top-level areas
   - runtime spine
   - product surfaces
   - hotspot modules
   - coupling hotspots
   - test coverage shape
   - docs/specs/reports that matter versus those that are historical or aspirational
2. A build/read order:
   - what to read first
   - what to ignore at first pass
   - what to revisit only after runtime understanding
3. A risk map:
   - giant files
   - over-central modules
   - duplicated abstractions
   - likely drift between docs and implementation
4. A cross-device workflow:
   - what artifacts should be regenerated locally
   - what artifacts should be committed
   - what external tools are appropriate for large-scale visualization or context packing

Non-goals:

- do not produce empty praise
- do not confuse report artifacts with live runtime architecture
- do not assume every markdown file describes shipped behavior
- do not stop after reading only root files

## Mandatory Method

Follow this order:

1. Fast inventory pass
   - run `python3 scripts/repo_xray.py`
   - inspect file counts, language mix, largest Python modules, and import coupling
   - enumerate top-level directories and their file counts

2. Canonical orientation pass
   - read `README.md`
   - read `CLAUDE.md`
   - read `docs/architecture/NAVIGATION.md`
   - read `pyproject.toml`
   - read `dashboard/package.json`
   - read `.github/workflows/tests.yml`

3. Runtime spine pass
   - inspect `api/main.py`
   - inspect `run_operator.sh`
   - inspect `dharma_swarm/swarm.py`
   - inspect `dharma_swarm/agent_runner.py`
   - inspect `dharma_swarm/orchestrator.py`
   - inspect `dharma_swarm/runtime_state.py`
   - inspect `dharma_swarm/operator_bridge.py`
   - inspect `dharma_swarm/evolution.py`
   - inspect `dharma_swarm/ontology.py`

4. Surface pass
   - inspect `api/routers/`
   - inspect `dashboard/src/app/dashboard/`
   - inspect `dharma_swarm/tui/`
   - inspect `dharma_swarm/dgc_cli.py`
   - inspect `dharma_swarm/cli.py`
   - inspect `desktop-shell/`

5. Map-system pass
   - inspect `dharma_swarm/living_map.py`
   - inspect `dharma_swarm/ecosystem_map.py`
   - inspect `dharma_swarm/ecosystem_index.py`
   - inspect `dharma_swarm/xray.py`
   - determine which map answers which class of question

6. Evidence pass
   - inspect representative tests under `tests/`
   - inspect only the reports and docs that materially validate implementation reality
   - identify where docs clearly exceed current implementation

## Required Heuristics

- Distinguish shipped runtime from scaffolding, experiments, and reports
- Distinguish central integration modules from leaf modules
- Weight tests and boot paths more heavily than visionary documents
- Weight imports, entrypoints, and API/router registration more heavily than naming
- Identify files that are too large to hold stable architecture
- Treat `dgc_cli.py`, `thinkodynamic_director.py`, `swarm.py`, `agent_runner.py`, `evolution.py`, and large dashboard pages as probable risk centers unless evidence says otherwise

## Search Patterns To Use

Use targeted searches rather than broad guessing:

```bash
rg --files
rg -n "FastAPI\\(|APIRouter\\(|Typer\\(|if __name__ == ['\\\"]__main__['\\\"]" dharma_swarm api dashboard scripts tests
rg -n "include_router|app = FastAPI|typer.Typer|sub.add_parser" api dharma_swarm
rg -n "SwarmManager|AgentRunner|DarwinEngine|Ontology|OperatorBridge|RuntimeState" dharma_swarm
```

Use line-count and file-count probes:

```bash
rg --files dharma_swarm api tests scripts | xargs wc -l | sort -nr | head -40
rg --files dashboard/src | xargs wc -l | sort -nr | head -30
find dharma_swarm api dashboard tests docs reports specs foundations tools -type f | wc -l
```

## External Tooling Guidance

If you need stronger whole-repo visibility, consider these tools:

- Repomix for portable AI context bundles
- Sourcegraph for cross-repo search and navigation
- CodeCharta for large-scale hotspot visualization
- pydeps for Python dependency graphs
- dependency-cruiser for dashboard dependency graphs
- tree-sitter-graph for syntax-aware graph extraction
- Gource for commit-history visualization

Use them as additional lenses, not as a substitute for grounded local inspection.

## Required Final Structure

Your final answer must contain:

1. Repo reality in one paragraph
2. Canonical entrypoints
3. Runtime spine
4. Product surfaces
5. Hotspots and risks
6. What is likely core vs peripheral
7. What to read next if the goal is to finish the project
8. What map or tool to use for each class of question

## Quality Bar

The map is only acceptable if:

- it is anchored in actual files
- it separates implementation from aspiration
- it names the central runtime path
- it tells a new operator where to start and where not to drown
- it remains useful when the repo is opened from another machine or cloud environment
