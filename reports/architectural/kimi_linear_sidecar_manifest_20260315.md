# Long-Context Sidecar Evaluation Plan

- Generated: `2026-03-14T19:59:18.269558+00:00`
- Candidate model: `moonshotai/Kimi-Linear-48B-A3B-Instruct`
- Baseline model: `current-premium-model`
- Repo root: `/Users/dhyana/dharma_swarm`
- Dharma home: `/Users/dhyana/.dharma`

## Thesis

Test long-context models as sidecar workers that read and compress large local artifacts into reusable memory products. Do not replace the main reasoning model or the canonical memory plane until the sidecar clearly wins on a real job.

## Workloads

### 1. Repo Digestion

- Case ID: `repo_digest`
- Role: `architecture_scout`
- Objective: Digest core memory/retrieval files and explain how they should be compressed into reusable memory artifacts for the main model.
- Model job: Read large code and architecture context cheaply, then compress it.
- Prompt frame: Read the sources as one system. Produce an architectural summary, three missing seams, and a compact memory shard packet.
- Output schema:
  - `system_summary`
  - `memory_shards`
  - `missing_seams`
  - `followup_questions`
- Sources:
  - `/Users/dhyana/dharma_swarm/dharma_swarm/engine/event_memory.py` [present] (truncated)
  - `/Users/dhyana/dharma_swarm/dharma_swarm/engine/hybrid_retriever.py` [present] (truncated)
  - `/Users/dhyana/dharma_swarm/dharma_swarm/semantic_memory_bridge.py` [present] (truncated)
- Success signals:
  - Correctly identifies event memory, hybrid retrieval, and semantic bridge roles.
  - Produces compact reusable memory shards instead of prose sprawl.
  - Surfaces at least one real integration seam worth testing.
- Kill signals:
  - Misstates the core memory architecture.
  - Needs the premium model to fix basic repo understanding.
  - Produces bloated output that is not reusable as memory.
- Evaluation questions:
  - Did it preserve system structure correctly?
  - Did it compress meaningfully enough to help downstream prompts?
  - Did it find missing seams we would actually build?

### 2. Conversation Condensation

- Case ID: `conversation_condense`
- Role: `continuity_editor`
- Objective: Condense recent conversations and distilled notes into a compact state packet for the next cycle.
- Model job: Turn messy user and system history into clean continuity state.
- Prompt frame: Extract commitments, open loops, invariants, and unresolved tensions. Output a compact continuity packet.
- Output schema:
  - `commitments`
  - `open_loops`
  - `identity_invariants`
  - `next_cycle_context`
- Sources:
  - `/Users/dhyana/.dharma/conversations/dashboard_2026-03-14.jsonl` [present] (truncated)
  - `/Users/dhyana/.dharma/distilled/2026-03-14_15.md` [present] (truncated)
  - `/Users/dhyana/.dharma/DGC_SEED_CONTEXT.md` [present] (truncated)
- Success signals:
  - Remembers concrete commitments and unresolved loops.
  - Produces a concise packet usable in future prompts.
  - Separates stable identity from temporary context.
- Kill signals:
  - Collapses important distinctions between goals and chatter.
  - Loses actionable commitments.
  - Outputs generic summarization with no continuity value.
- Evaluation questions:
  - Would this packet improve the next live session?
  - Did it preserve promises and constraints?
  - Is the output smaller and more useful than raw history?

### 3. Trace Summarization

- Case ID: `trace_summarize`
- Role: `ops_summarizer`
- Objective: Summarize long operational traces into a small packet that highlights events, failures, and useful carry-forward state.
- Model job: Compress operational logs and trace files for the next agent cycle.
- Prompt frame: Read the traces and produce an execution summary, detected failures, carry-forward state, and one contradiction check.
- Output schema:
  - `execution_summary`
  - `failures`
  - `carry_forward_state`
  - `contradictions`
- Sources:
  - `/Users/dhyana/.dharma/evolution/archive.jsonl` [present] (truncated)
  - `/Users/dhyana/.dharma/foreman/cycles.jsonl` [present]
  - `/Users/dhyana/dharma_swarm/reports/dual_engine_swarm_20260313_run/state/mission.json` [present]
- Success signals:
  - Captures what happened without reproducing the whole log.
  - Flags failures and degraded states clearly.
  - Produces carry-forward state the main model can use.
- Kill signals:
  - Copies logs instead of compressing them.
  - Misses obvious degraded or failed conditions.
  - Cannot separate signal from noise.
- Evaluation questions:
  - Would this reduce context load in live loops?
  - Did it preserve failures and operator-relevant state?
  - Did it surface contradictions worth checking?

### 4. Contradiction Hunt

- Case ID: `contradiction_hunt`
- Role: `integrity_reviewer`
- Objective: Read plans and architecture docs, then surface hidden contradictions, duplicate machinery, and mismatched claims.
- Model job: Act as a cheap structural critic over large planning documents.
- Prompt frame: Find claims that disagree, duplicate modules, or create architecture drift. Propose one keep/kill decision per contradiction.
- Output schema:
  - `contradictions`
  - `duplicate_machinery`
  - `keep_kill_decisions`
  - `risk_summary`
- Sources:
  - `/Users/dhyana/dharma_swarm/reports/architectural/STRANGE_LOOP_MASTER_PLAN_20260314.md` [present] (truncated)
  - `/Users/dhyana/dharma_swarm/program.md` [present] (truncated)
  - `/Users/dhyana/dharma_swarm/LIVING_LAYERS.md` [present] (truncated)
- Success signals:
  - Finds real contradictions rather than superficial style issues.
  - Connects contradictions to concrete files and decisions.
  - Suggests keep/kill decisions grounded in the repo state.
- Kill signals:
  - Only finds vague philosophical inconsistencies.
  - Misses duplicate machinery already called out in plans.
  - Cannot map claims back to specific files.
- Evaluation questions:
  - Did it reduce architecture drift?
  - Did it tie claims to concrete files?
  - Did it find anything worth acting on this week?

### 5. Memory Distillation

- Case ID: `memory_distill`
- Role: `memory_distiller`
- Objective: Turn dense notes and semantic summaries into compact memory shards that are worth indexing and recalling.
- Model job: Produce reusable memory artifacts, not just summaries.
- Prompt frame: Extract high-salience memory shards, novelty, invariants, and evidence paths. Output them in a form that can be indexed.
- Output schema:
  - `memory_shards`
  - `novelty_notes`
  - `invariants`
  - `evidence_paths`
- Sources:
  - `/Users/dhyana/dharma_swarm/reports/psmv_hyperfiles_20260313/repo_semantic_summary.md` [present]
  - `/Users/dhyana/.dharma/distilled/ideas.jsonl` [present] (truncated)
  - `/Users/dhyana/.dharma/DGC_SEED_CONTEXT.md` [present] (truncated)
- Success signals:
  - Produces discrete shard-like artifacts rather than one monolith.
  - Preserves evidence paths and invariants.
  - Would be worth adding to memory_plane or unified_index.
- Kill signals:
  - Outputs generic notes that are not indexable.
  - Drops evidence provenance.
  - Confuses speculative ideas with stable invariants.
- Evaluation questions:
  - Would these shards improve retrieval quality later?
  - Did it preserve provenance and confidence?
  - Are the shards compact enough to re-use automatically?
