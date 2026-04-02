---
title: DGC Subagent Gauntlet Prompt (Planner/Executor + Gates + Memory)
path: docs/prompts/DGC_SUBAGENT_GAUNTLET_PROMPT.md
slug: dgc-subagent-gauntlet-prompt-planner-executor-gates-memory
doc_type: documentation
status: active
summary: Paste this prompt inside dgc chat to run a deep system stress-and-evolve session.
source:
  provenance: repo_local
  kind: documentation
  origin_signals: []
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- multi_agent_systems
- software_architecture
- knowledge_management
- verification
- machine_learning
inspiration:
- verification
connected_python_files:
- tests/test_dashboard_chat_session_contract.py
- tests/test_dgc_cli_memory_retrospectives.py
- tests/tui/test_stream_output_observability.py
- tests/tui/test_system_commands.py
- tests/test_agent_memory.py
connected_python_modules:
- tests.test_dashboard_chat_session_contract
- tests.test_dgc_cli_memory_retrospectives
- tests.tui.test_stream_output_observability
- tests.tui.test_system_commands
- tests.test_agent_memory
connected_relevant_files:
- tests/test_dashboard_chat_session_contract.py
- tests/test_dgc_cli_memory_retrospectives.py
- tests/tui/test_stream_output_observability.py
- tests/tui/test_system_commands.py
- tests/test_agent_memory.py
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `docs` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: documentation
  vault_path: docs/prompts/DGC_SUBAGENT_GAUNTLET_PROMPT.md
  retrieval_terms:
  - dgc
  - subagent
  - gauntlet
  - prompt
  - planner
  - executor
  - gates
  - memory
  - paste
  - inside
  - chat
  - run
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: working
  semantic_weight: 0.55
  coordination_comment: Paste this prompt inside dgc chat to run a deep system stress-and-evolve session.
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/prompts/DGC_SUBAGENT_GAUNTLET_PROMPT.md reinforces its salience without needing a separate message.
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
# DGC Subagent Gauntlet Prompt (Planner/Executor + Gates + Memory)

Paste this prompt inside `dgc` chat to run a deep system stress-and-evolve session.

---

You are operating inside DGC. Run a high-rigor, evidence-first gauntlet that tests and improves the system without unsafe drift.

## Non-negotiable contract

1. Enter plan mode correctly: call `EnterPlanMode` with `{}` (empty input object only).
2. Follow planner-executor separation:
   - Planner creates numbered plan and success criteria.
   - Executors only execute assigned steps.
3. Use exactly 3 subagents in parallel:
   - `forensics-agent`: verify claims, logs, metrics, and failure signatures.
   - `chaos-agent`: trigger edge-case and stress scenarios across tools/providers.
   - `evolution-agent`: propose safe, traceable mutations with rollback notes.
4. Mandatory think points before:
   - file writes
   - strategy pivots
   - declaring completion
5. Circuit breaker:
   - If same failure signature repeats 3 times, stop retrying and pivot strategy.
6. Memory survival instinct:
   - Assume all context dies at end of task.
   - Externalize all important findings to artifacts.
7. Traceability required for every mutation:
   - include `spec_ref` and `requirement_refs` in proposal/report language.
8. Continue on non-critical failures; mark them as `BLOCKED` with exact cause.
9. No fabricated success. Every claim must cite command output or file evidence.

## Mission

Run a full-stack gauntlet of DGC capabilities:
- CLI health and core workflows
- provider dispatch and error normalization
- telos gates and evolution loop behavior
- TUI plan-mode and stream behavior
- NVIDIA integration touchpoints (RAG, ingest, flywheel) if configured
- archival traceability and memory persistence

## Execution protocol

1. Planner phase
   - Produce a numbered 12-step plan with pass/fail criteria and risk notes.
   - Explicitly map each step to one of: Observe, Orient, Plan, Act, Verify, Record, Iterate, Gate.

2. Parallel subagent phase
   - Spawn 3 subagents with strict output schema:
     - `task_id`
     - `commands_run`
     - `evidence_paths`
     - `failures`
     - `recommendations`
   - Require each subagent to save artifacts under:
     - `~/.dharma/shared/gauntlet_<timestamp>/subagents/<name>/`

3. Integration phase
   - Merge subagent outputs.
   - Deduplicate overlapping findings.
   - Rank top 15 fixes by ROI (impact x effort x risk reduction).

4. Implementation phase
   - Implement top 5 safe, high-ROI fixes immediately.
   - For each fix, provide:
     - changed file paths
     - exact reason
     - verification commands
     - residual risks

5. Verification phase
   - Run targeted tests first, then broader test slices.
   - Produce a claim-evidence table:
     - claim
     - evidence file
     - command
     - status (`PROVEN` / `PARTIAL` / `NOT PROVEN`)

6. Final gate phase
   - Run telos/gate self-check on your own final report.
   - Include one section called `What I still do NOT know`.

## Timebox and output

- Timebox: run until done or 6 hours (whichever comes first).
- Emit heartbeat updates every 15 minutes with current step and blockers.
- Write final outputs to:
  - `~/.dharma/shared/gauntlet_<timestamp>/GAUNTLET_FINAL_REPORT.md`
  - `~/.dharma/shared/gauntlet_<timestamp>/scorecard.json`
  - `~/.dharma/shared/gauntlet_<timestamp>/commands.jsonl`

## Ship-readiness rubric

At the end, score each dimension 0-10 and justify with evidence:
- Safety gates
- Planner/executor discipline
- Recovery from failure
- Memory persistence
- Traceability quality
- Multi-provider reliability
- Integration readiness

Do not skip evidence. Start now with planner phase.
