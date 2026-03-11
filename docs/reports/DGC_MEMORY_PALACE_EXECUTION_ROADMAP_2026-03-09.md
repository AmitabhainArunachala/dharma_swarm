# DGC Memory Palace Execution Roadmap

Date: 2026-03-09  
Status: execution-grade architecture brief  
Canonical runtime: [`/Users/dhyana/dharma_swarm`](/Users/dhyana/dharma_swarm)  
Primary inputs: [`/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_HYPER_REVIEW_2026-03-09.md#L7`](/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_HYPER_REVIEW_2026-03-09.md#L7), [`/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_SCOUT_REPORT_2026-03-09.md#L9`](/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_SCOUT_REPORT_2026-03-09.md#L9), [`/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L433`](/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L433), [`/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L118`](/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L118), [`/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L732`](/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L732), [`/Users/dhyana/Downloads/dharma_swarm_memory_palace_research.pdf`](/Users/dhyana/Downloads/dharma_swarm_memory_palace_research.pdf)

## A. Bottom Line

- `OBSERVED`: canonical `dharma_swarm` already has real memory substrates, not a blank slate: five-layer strange-loop memory in [`/Users/dhyana/dharma_swarm/dharma_swarm/memory.py#L77`](/Users/dhyana/dharma_swarm/dharma_swarm/memory.py#L77), a self-editing per-agent memory bank in [`/Users/dhyana/dharma_swarm/dharma_swarm/agent_memory.py#L69`](/Users/dhyana/dharma_swarm/dharma_swarm/agent_memory.py#L69), and a pluggable knowledge-store interface in [`/Users/dhyana/dharma_swarm/dharma_swarm/engine/knowledge_store.py#L68`](/Users/dhyana/dharma_swarm/dharma_swarm/engine/knowledge_store.py#L68).
- `OBSERVED`: memory is already in the live runtime loop. `AgentRunner` injects working memory into prompts and writes task results and failures back into memory in [`/Users/dhyana/dharma_swarm/dharma_swarm/agent_runner.py#L308`](/Users/dhyana/dharma_swarm/dharma_swarm/agent_runner.py#L308) and [`/Users/dhyana/dharma_swarm/dharma_swarm/agent_runner.py#L338`](/Users/dhyana/dharma_swarm/dharma_swarm/agent_runner.py#L338). Consolidation already runs in the quiet-hours sleep cycle in [`/Users/dhyana/dharma_swarm/dharma_swarm/sleep_cycle.py#L87`](/Users/dhyana/dharma_swarm/dharma_swarm/sleep_cycle.py#L87).
- `OBSERVED`: the current ceiling is blocked by retrieval quality and memory unification. The HYPER review explicitly identifies the missing seams as event ingress and unified semantic retrieval in [`/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_HYPER_REVIEW_2026-03-09.md#L16`](/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_HYPER_REVIEW_2026-03-09.md#L16) and [`/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_HYPER_REVIEW_2026-03-09.md#L19`](/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_HYPER_REVIEW_2026-03-09.md#L19). The SCOUT report maps those same gaps to canonical attach points in [`/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_SCOUT_REPORT_2026-03-09.md#L13`](/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_SCOUT_REPORT_2026-03-09.md#L13) and [`/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_SCOUT_REPORT_2026-03-09.md#L21`](/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_SCOUT_REPORT_2026-03-09.md#L21).
- `OBSERVED`: the research brief’s strongest recommendation is not “add more memory tables.” It is a staged memory engine: hybrid retrieval first, then temporal memory, then feedback, then context scheduling, then graph expansion, then hierarchical compression. [`/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L433`](/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L433) [`/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L1423`](/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L1423) [`/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L158`](/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L158) [`/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L696`](/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L696)
- `INFERRED`: the right build order for a true Memory Palace is:
  1. canonical event spine plus unified index
  2. hybrid multilingual retrieval
  3. temporal metadata and query engine
  4. retrieval feedback and citation signals
  5. FSRS context scheduler
  6. graph expansion and query-time traversal
  7. CoD and RAPTOR summarization

## B. Architecture Law

- `OBSERVED`: `dharma_swarm` remains canonical. `dharmic-agora` remains the SAB runtime authority and must not be turned into the DGC memory substrate. [`/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_HYPER_REVIEW_2026-03-09.md#L12`](/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_HYPER_REVIEW_2026-03-09.md#L12)
- `OBSERVED`: do not import the legacy `canonical_memory.py` monolith or the `ops/bridge` file-queue transport. Both reports mark those as dangerous legacy surface. [`/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_SCOUT_REPORT_2026-03-09.md#L73`](/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_SCOUT_REPORT_2026-03-09.md#L73) [`/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_HYPER_REVIEW_2026-03-09.md#L75`](/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_HYPER_REVIEW_2026-03-09.md#L75)
- `OBSERVED`: memory should remain advisory-first. Runtime mutation stays behind the existing control plane: runtime contract in [`/Users/dhyana/dharma_swarm/dharma_swarm/runtime_contract.py#L17`](/Users/dhyana/dharma_swarm/dharma_swarm/runtime_contract.py#L17), orchestrator lifecycle in [`/Users/dhyana/dharma_swarm/dharma_swarm/orchestrator.py#L188`](/Users/dhyana/dharma_swarm/dharma_swarm/orchestrator.py#L188), provider routing in [`/Users/dhyana/dharma_swarm/dharma_swarm/provider_policy.py#L113`](/Users/dhyana/dharma_swarm/dharma_swarm/provider_policy.py#L113), and telos gates already embedded in runtime execution in [`/Users/dhyana/dharma_swarm/dharma_swarm/agent_runner.py#L284`](/Users/dhyana/dharma_swarm/dharma_swarm/agent_runner.py#L284).
- `INFERRED`: the Memory Palace should therefore be a memory plane, not a second orchestrator. It should enrich retrieval, context assembly, and planning; it should not become a parallel truth system that bypasses ledgers, gates, or SAB boundaries.

## C. Current Baseline

| Layer | Current canonical surface | What is already real | Limitation that blocks Memory Palace |
|---|---|---|---|
| Reflective memory | [`/Users/dhyana/dharma_swarm/dharma_swarm/memory.py#L77`](/Users/dhyana/dharma_swarm/dharma_swarm/memory.py#L77) | Five layers, SQLite persistence, evidence-biased quality scoring | No semantic retrieval, no cross-source ingestion, no temporal or graph reasoning |
| Agent local memory | [`/Users/dhyana/dharma_swarm/dharma_swarm/agent_memory.py#L69`](/Users/dhyana/dharma_swarm/dharma_swarm/agent_memory.py#L69) | Working, archival, persona tiers; consolidation; lessons; persistence | Search is keyword-only and per-agent, not canonical memory fabric |
| Knowledge store | [`/Users/dhyana/dharma_swarm/dharma_swarm/engine/knowledge_store.py#L68`](/Users/dhyana/dharma_swarm/dharma_swarm/engine/knowledge_store.py#L68) | Stable storage/search contract with local and Qdrant backends | Retrieval quality is bootstrap-grade: token overlap and deterministic hash embeddings in [`/Users/dhyana/dharma_swarm/dharma_swarm/engine/knowledge_store.py#L23`](/Users/dhyana/dharma_swarm/dharma_swarm/engine/knowledge_store.py#L23), [`/Users/dhyana/dharma_swarm/dharma_swarm/engine/knowledge_store.py#L43`](/Users/dhyana/dharma_swarm/dharma_swarm/engine/knowledge_store.py#L43), [`/Users/dhyana/dharma_swarm/dharma_swarm/engine/knowledge_store.py#L117`](/Users/dhyana/dharma_swarm/dharma_swarm/engine/knowledge_store.py#L117) |
| Runtime event surfaces | [`/Users/dhyana/dharma_swarm/dharma_swarm/runtime_contract.py#L17`](/Users/dhyana/dharma_swarm/dharma_swarm/runtime_contract.py#L17), [`/Users/dhyana/dharma_swarm/dharma_swarm/orchestrator.py#L188`](/Users/dhyana/dharma_swarm/dharma_swarm/orchestrator.py#L188), [`/Users/dhyana/dharma_swarm/dharma_swarm/message_bus.py#L186`](/Users/dhyana/dharma_swarm/dharma_swarm/message_bus.py#L186) | Validated envelopes, lifecycle events, publish/subscribe, artifacts | No canonical ingest-and-replay event spine yet |
| Context assembly | [`/Users/dhyana/dharma_swarm/dharma_swarm/context.py#L159`](/Users/dhyana/dharma_swarm/dharma_swarm/context.py#L159), [`/Users/dhyana/dharma_swarm/dharma_swarm/context.py#L243`](/Users/dhyana/dharma_swarm/dharma_swarm/context.py#L243) | Real context engine already exists | Mostly file-read based; no first-class retrieval policy or note scheduler |

## D. Phase Order

| Phase | Decision | Why now | Canonical attach point | Safe to delegate |
|---|---|---|---|---|
| 1. Event spine plus unified index | `BUILD NOW` | It creates one canonical memory substrate instead of three disconnected stores | `runtime_contract.py`, `orchestrator.py`, `message_bus.py`, `memory.py`, `engine/knowledge_store.py` | `partially` |
| 2. Hybrid retrieval | `BUILD NOW` | It is the first real leap in memory quality | `engine/knowledge_store.py`, `context.py`, `agent_runner.py` | `yes` |
| 3. Temporal engine | `BUILD NOW` | It is the missing difference between “search” and “memory” | retrieval layer plus note metadata loaders | `yes` |
| 4. Feedback and citation signals | `BUILD NOW` | It turns retrieval into a learning loop instead of static recall | `agent_runner.py`, `runtime_contract.py`, `monitor.py` | `partially` |
| 5. FSRS scheduler | `BUILD AFTER 1-4` | It needs retrieval and feedback data to matter | `context.py` plus retrieval ranking layer | `yes` |
| 6. Graph expansion | `BUILD AFTER 1-5` | It compounds retrieval quality but should not arrive before the index exists | new graph service fed by indexed notes | `partially` |
| 7. CoD plus RAPTOR summarization | `BUILD LAST` | Compression without measurement produces elegant rot | retrieval, feedback, and scheduler layers | `no` |

## E. Phase 1: Canonical Event Spine Plus Unified Index

- `OBSERVED`: both HYPER and SCOUT identify `event_spine.py` and `unified_indexer.py` as the memory seams legacy DGC still knows how to do better than canonical runtime. [`/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_HYPER_REVIEW_2026-03-09.md#L16`](/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_HYPER_REVIEW_2026-03-09.md#L16) [`/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_SCOUT_REPORT_2026-03-09.md#L13`](/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_SCOUT_REPORT_2026-03-09.md#L13) [`/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_SCOUT_REPORT_2026-03-09.md#L21`](/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_SCOUT_REPORT_2026-03-09.md#L21)
- `OBSERVED`: canonical runtime already has the needed ingress hooks. Runtime envelopes exist in [`/Users/dhyana/dharma_swarm/dharma_swarm/runtime_contract.py#L40`](/Users/dhyana/dharma_swarm/dharma_swarm/runtime_contract.py#L40), orchestrator lifecycle events already emit via the bus in [`/Users/dhyana/dharma_swarm/dharma_swarm/orchestrator.py#L188`](/Users/dhyana/dharma_swarm/dharma_swarm/orchestrator.py#L188), and the bus already carries typed artifacts in [`/Users/dhyana/dharma_swarm/dharma_swarm/message_bus.py#L256`](/Users/dhyana/dharma_swarm/dharma_swarm/message_bus.py#L256).

Target build:

- New storage service under `dharma_swarm/engine/` for canonical memory ingestion.
- One SQLite-backed event log with dedupe on `event_id` and replay by `session_id`, `trace_id`, and `event_type`.
- One canonical document/chunk index that stores:
  - note path
  - source type
  - chunk text
  - normalized metadata
  - source hash
  - last indexed commit or timestamp
- One incremental index-run ledger so indexing is replayable and restart-safe.

Do not do:

- Do not turn [`/Users/dhyana/dharma_swarm/dharma_swarm/message_bus.py#L94`](/Users/dhyana/dharma_swarm/dharma_swarm/message_bus.py#L94) into the long-term memory database.
- Do not duplicate reflective memory tables from [`/Users/dhyana/dharma_swarm/dharma_swarm/memory.py#L19`](/Users/dhyana/dharma_swarm/dharma_swarm/memory.py#L19) as a second SQLite island.
- Do not import legacy transport semantics that create side-channel state outside canonical runtime.

Acceptance gates:

1. Ingest and validate `RuntimeEnvelope` records from canonical contract. [`/Users/dhyana/dharma_swarm/dharma_swarm/runtime_contract.py#L53`](/Users/dhyana/dharma_swarm/dharma_swarm/runtime_contract.py#L53)
2. Replay a session’s event history deterministically by `session_id`.
3. Re-index without duplicating unchanged chunks.
4. Search across note chunks and runtime events through one retrieval facade.
5. Add canonical tests for dedupe, replay, and incremental sync.

Delegation:

- `SAFE`: storage schema, chunk persistence, replay tests.
- `UNSAFE`: final contract shape and cross-surface data model.

## F. Phase 2: Hybrid Multilingual Retrieval

- `OBSERVED`: the research recommendation is explicit: `BGE-M3 (int8) -> LanceDB -> SQLite FTS5 -> MiniLM reranker -> header-aware chunking -> multi-query retrieval`. [`/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L433`](/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L433)
- `OBSERVED`: current canonical retrieval is intentionally lightweight and contract-stable, but not remotely strong enough yet. [`/Users/dhyana/dharma_swarm/dharma_swarm/engine/knowledge_store.py#L85`](/Users/dhyana/dharma_swarm/dharma_swarm/engine/knowledge_store.py#L85) [`/Users/dhyana/dharma_swarm/dharma_swarm/engine/knowledge_store.py#L117`](/Users/dhyana/dharma_swarm/dharma_swarm/engine/knowledge_store.py#L117)

Target build:

- Preserve the `KnowledgeStore` contract in [`/Users/dhyana/dharma_swarm/dharma_swarm/engine/knowledge_store.py#L68`](/Users/dhyana/dharma_swarm/dharma_swarm/engine/knowledge_store.py#L68), but introduce a stronger backend and a separate retriever service.
- Add a hybrid retriever that performs:
  - dense search
  - BM25 or FTS search
  - metadata filtering
  - reciprocal rank fusion
  - optional reranking
- Route `context.py` memory reads through this retriever instead of only direct SQLite/file reads. [`/Users/dhyana/dharma_swarm/dharma_swarm/context.py#L243`](/Users/dhyana/dharma_swarm/dharma_swarm/context.py#L243)
- Expose retrieval as a first-class runtime tool for `AgentRunner`, not just as silent prompt stuffing. Current injection occurs in [`/Users/dhyana/dharma_swarm/dharma_swarm/agent_runner.py#L308`](/Users/dhyana/dharma_swarm/dharma_swarm/agent_runner.py#L308).

Acceptance gates:

1. Retrieval quality beats the current in-memory baseline on canonical tests.
2. Language coverage explicitly includes English, Japanese, and Sanskrit as required by the research brief. [`/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L447`](/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L447)
3. Results include ranked evidence metadata suitable for downstream feedback.
4. Backends remain swappable behind the existing `KnowledgeStore` surface.

Delegation:

- `SAFE`: backend implementation and benchmark harness.
- `UNSAFE`: changing the public `KnowledgeStore` contract without principal review.

## G. Phase 3: Temporal Metadata And Query Engine

- `OBSERVED`: the research treats git history and note metadata as first-class temporal memory, not archival trivia. [`/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L923`](/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L923) [`/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L1423`](/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L1423)
- `OBSERVED`: canonical runtime currently stores timestamps on memories and messages, but does not yet provide temporal ranking or supersession reasoning. [`/Users/dhyana/dharma_swarm/dharma_swarm/memory.py#L20`](/Users/dhyana/dharma_swarm/dharma_swarm/memory.py#L20) [`/Users/dhyana/dharma_swarm/dharma_swarm/message_bus.py#L27`](/Users/dhyana/dharma_swarm/dharma_swarm/message_bus.py#L27)

Target build:

- Define canonical note metadata fields for:
  - `created`
  - `epistemic_date`
  - `belief_expires`
  - `belief_confidence`
  - `belief_status`
  - `superseded_by`
  - `supersedes`
  - `last_retrieved`
  - `retrieval_count`
  - `decay_score`
- Build a temporal engine that can:
  - filter stale or superseded notes
  - bias retrieval toward current-valid knowledge
  - inspect note history through git
  - write access logs for later feedback and scheduling

Canonical attach points:

- retrieval ranking layer
- note indexing pipeline
- `context.py` assembly
- later, graph contradiction checks

Acceptance gates:

1. Retrieval can exclude stale or superseded notes by policy.
2. Notes with stronger confidence and fresher evidence rank higher when semantically tied.
3. Temporal query tests prove historical snapshot recall and supersession behavior.

Delegation:

- `SAFE`: metadata parser, git query layer, temporal ranking tests.

## H. Phase 4: Feedback Logging And Citation Signals

- `OBSERVED`: the strongest self-improvement recommendation in the research is instrumentation first, not model tuning. The report’s summary and verdict explicitly prioritize citation-based reranking boosts and feedback logging before Darwin-style modification. [`/Users/dhyana/Downloads/dharma_swarm_memory_palace_research.pdf`](/Users/dhyana/Downloads/dharma_swarm_memory_palace_research.pdf)
- `OBSERVED`: the runtime already has a place to record outcomes and observe drift: task execution in [`/Users/dhyana/dharma_swarm/dharma_swarm/agent_runner.py#L368`](/Users/dhyana/dharma_swarm/dharma_swarm/agent_runner.py#L368), runtime envelopes in [`/Users/dhyana/dharma_swarm/dharma_swarm/runtime_contract.py#L130`](/Users/dhyana/dharma_swarm/dharma_swarm/runtime_contract.py#L130), and health monitoring in [`/Users/dhyana/dharma_swarm/dharma_swarm/monitor.py#L116`](/Users/dhyana/dharma_swarm/dharma_swarm/monitor.py#L116).

Target build:

- Add a retrieval feedback log for every memory-assisted task:
  - query
  - retrieved item ids and ranks
  - chosen items actually injected
  - explicit citations detected in output
  - missing-evidence flag
  - outcome quality or failure signature
- Promote this feedback into canonical audit surfaces instead of private heuristics.
- Feed the monitor with retrieval-level health metrics later, but keep the monitor analytical, matching its current design in [`/Users/dhyana/dharma_swarm/dharma_swarm/monitor.py#L104`](/Users/dhyana/dharma_swarm/dharma_swarm/monitor.py#L104).

Acceptance gates:

1. Every retrieval-assisted completion can be traced back to ranked evidence.
2. Feedback data is queryable by note id, task id, and session id.
3. Retrieval metrics can show “retrieved but unused,” “used and cited,” and “missing.”
4. No training or retuning happens until this signal quality is verified.

Delegation:

- `SAFE`: logging plumbing and citation extraction.
- `UNSAFE`: closing the loop into automatic reweighting before metrics stabilize.

## I. Phase 5: FSRS Context Scheduler

- `OBSERVED`: the research explicitly reframes spaced repetition as context-budget management for agent memory, not human flashcards. [`/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L118`](/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L118)
- `OBSERVED`: the proposed priority function combines semantic similarity, recency, FSRS retrievability, and graph distance. [`/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L158`](/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L158)

Target build:

- Create a note scheduler layer that ranks candidate context items after retrieval, not before retrieval.
- Store per-note scheduler state separate from core notes, analogous to the existing per-agent memory bank state files in [`/Users/dhyana/dharma_swarm/dharma_swarm/agent_memory.py#L324`](/Users/dhyana/dharma_swarm/dharma_swarm/agent_memory.py#L324).
- Use feedback from Phase 4:
  - accurate and useful note -> longer resurfacing interval
  - outdated or misleading note -> shorter interval and stale flag

Critical rule:

- FSRS is not the retrieval engine.
- FSRS is the context-priority layer sitting on top of retrieval and temporal filtering.

Acceptance gates:

1. Scheduler state persists and evolves per note.
2. Context assembly can show why a note was selected.
3. Low-value repeated context stuffing drops measurably.

Delegation:

- `SAFE`: scheduler implementation once feedback schema is frozen.

## J. Phase 6: Graph Expansion And Query-Time Traversal

- `OBSERVED`: the research wants query-time entity expansion, subgraph injection, and contradiction detection. [`/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L761`](/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L761) [`/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L769`](/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L769)
- `OBSERVED`: the recommended production graph backend is Kuzu, with GLiNER extraction and optional LightRAG-style traversal. [`/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L771`](/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L771) [`/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L901`](/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L901)
- `OBSERVED`: canonical runtime already has one useful precursor: stigmergic marks capture file-path activity and explicit `connections` fields in [`/Users/dhyana/dharma_swarm/dharma_swarm/stigmergy.py#L30`](/Users/dhyana/dharma_swarm/dharma_swarm/stigmergy.py#L30). That is not a knowledge graph, but it is a coordination trace worth joining later.

Target build:

- Derive graph edges from:
  - note wikilinks
  - tags and metadata
  - entity extraction
  - later, contradiction and supersession relations
- Use graph traversal to expand candidate sets before final rerank.
- Join graph distance into the same ranking policy described in the FSRS phase.

Acceptance gates:

1. Graph lookups improve retrieval on multi-hop conceptual queries.
2. Contradiction checks can flag opposed claims about the same entities.
3. Graph never becomes the sole retrieval path; it remains a retrieval amplifier.

Delegation:

- `SAFE`: entity extraction pipeline and Kuzu storage.
- `UNSAFE`: graph-driven context injection policy before offline evaluation exists.

## K. Phase 7: CoD And RAPTOR Summarization

- `OBSERVED`: the research proposes an agent-native summarization ladder: L0 verbatim notes, L1 Chain-of-Density summaries, L2-L4 RAPTOR summaries. [`/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L696`](/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L696) [`/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L732`](/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L732) [`/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L861`](/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L861)
- `OBSERVED`: the same research also says summary quality should be measured by downstream task performance, with regeneration when summaries fail. [`/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L698`](/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L698) [`/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L714`](/Users/dhyana/Downloads/pkm_research_domains_4_6.md#L714)

Target build:

- Store L1 summaries as sidecars to indexed notes.
- Build L2-L4 only as batch artifacts after enough retrieval and feedback data exists.
- Version summaries in git or in an equally auditable artifact store.

Critical rule:

- Do not let summaries replace source notes for factual work.
- Summaries are compression layers, not authoritative truth.

Acceptance gates:

1. Every summary points back to source note ids.
2. Failed summaries are traceable and regenerable.
3. Retrieval can mix abstraction levels without losing provenance.

Delegation:

- `NOT YET`: keep summarization policy and quality control under principal review until Phases 1-4 are stable.

## L. What The Other Agent Can Build In Parallel

- `SAFE NOW`
  - `src/core/model_router.py` import into provider routing, because HYPER/SCOUT already classify it as high-ROI and narrow-scope. [`/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_HYPER_REVIEW_2026-03-09.md#L30`](/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_HYPER_REVIEW_2026-03-09.md#L30)
  - `session_event_bridge.py` and `continuity_harness.py`, because they improve ingress and replay integrity for the future event spine. [`/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_HYPER_REVIEW_2026-03-09.md#L28`](/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_HYPER_REVIEW_2026-03-09.md#L28)

- `SAFE AFTER THIS ROADMAP IS ACCEPTED`
  - unified index storage and tests
  - hybrid retriever implementation
  - temporal metadata parser and git query layer
  - retrieval feedback logger

- `HOLD BACK`
  - graph-driven policy
  - summary regeneration policy
  - any Darwin-style tuning of retrieval parameters

## M. Immediate 14-Day Build Packet

1. Freeze the canonical memory contracts:
   - event ingestion schema
   - indexed chunk schema
   - retrieval result schema
   - feedback log schema
2. Build Phase 1 storage and replay tests.
3. Replace bootstrap retrieval with a hybrid retriever behind the existing knowledge-store facade.
4. Add temporal metadata parsing and ranking.
5. Log retrieval evidence and citations for every memory-assisted task.

If those five land cleanly, `dharma_swarm` stops being “agents with some memory” and starts becoming a real Memory Palace substrate.

## N. Success Criteria

- `M1`: a task can retrieve relevant memory from notes, runtime events, and prior outputs through one canonical interface.
- `M2`: retrieval can explain why each memory item was selected and whether it later helped.
- `M3`: stale or superseded knowledge is demoted automatically by temporal policy.
- `M4`: context assembly is ranked, budgeted, and auditable rather than ad hoc.
- `M5`: summaries and graph expansion improve recall and reasoning without becoming hidden truth stores.

`INFERRED`: after Phases 1-4, the claim “this is a serious agentic memory engine” becomes credible. After Phases 5-7, the claim “this is the strongest Memory Palace we know how to build under current constraints” becomes defensible.
