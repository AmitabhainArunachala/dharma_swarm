# DGC Hybrid Accelerator Blueprint (2026-03-10)

## North Star

DGC should become a sovereign, memory-native orchestration engine whose live control plane stays local, inspectable, and replayable while external accelerators improve retrieval, evaluation, and model choice without ever becoming the canonical source of truth. The winning shape is not a monolith and not a thin shell around third-party infra; it is a lean hybrid runtime with explicit claims, provenance, compiled context, typed artifacts, isolated workspaces, and optional accelerator lanes.

## Canonical Runtime Stack

Use one lean hybrid by default:

- `SQLite` for live structured truth.
- `JSONL` for append-only replay and audit.
- `filesystem` for actual workspaces and artifact payloads.
- `git` only for promoted outputs and operator-approved publication.
- `FTS5` in SQLite first; add semantic/vector indexing only as a derived layer.

Authority split:

- `runtime.db` is authoritative for tasks, sessions, claims, delegation, memory facts, artifact metadata, leases, and evaluation decisions.
- `events/*.jsonl` is authoritative for immutable event history and replay.
- `workspace/` and `artifacts/` are authoritative for file contents.
- NVIDIA RAG, Data Flywheel, and any vector store are accelerators only.

## Canonical Layout

Target layout under `~/.dharma`:

```text
.dharma/
  state/
    runtime.db
  events/
    runtime.jsonl
    task_lifecycle.jsonl
    tool_results.jsonl
    snapshots.jsonl
    flywheel_exports.jsonl
  workspace/
    agents/
      <agent_id>/
        <task_id>/
    shared/
      inbox/
      published/
      scratch/
  artifacts/
    <artifact_id>/
      payload
      manifest.json
```

Current seam note:

- Existing modules already persist pieces of this across `message_bus.py`, `session_ledger.py`, `operator_bridge.py`, `engine/event_memory.py`, and repo-local `workspace/` helpers.
- vNext should converge those seams around one runtime spine instead of multiplying stores.

## `runtime.db` Tables

Build the first canonical schema around these tables:

| Table | Purpose |
| --- | --- |
| `sessions` | operator/session identity, ownership, channel, status, continuity refs |
| `tasks` | queued work, priority, intent, parent-child lineage, trace IDs |
| `task_claims` | atomic claim, timeout, release, stale recovery |
| `delegation_runs` | dispatch -> ack -> heartbeat -> completion lifecycle |
| `heartbeats` | liveness for agents, runners, long tasks, autopilot loops |
| `artifacts` | artifact metadata, state, checksums, manifests, publication state |
| `artifact_links` | lineage between artifacts, tasks, sessions, and external jobs |
| `memory_facts` | durable promoted facts with provenance and validity windows |
| `memory_edges` | typed graph relationships between facts, artifacts, tasks, and sessions |
| `workspace_leases` | shared-zone write locks and lease ownership |
| `context_bundles` | auditable record of assembled context packages per run |
| `evaluation_runs` | local or flywheel evaluation jobs and score payloads |
| `provider_recommendations` | candidate route/model recommendations gated by policy |
| `operator_actions` | interrupts, approvals, cancellations, overrides, promotions |

Minimum object fields:

- `tasks`: `task_id`, `session_id`, `parent_task_id`, `trace_id`, `status`, `intent`, `priority`, `requested_by`, `assigned_agent`, `created_at`, `updated_at`, `deadline_at`
- `task_claims`: `claim_id`, `task_id`, `claimer_id`, `status`, `claimed_at`, `acknowledged_at`, `heartbeat_at`, `expires_at`, `released_at`, `failure_reason`
- `delegation_runs`: `run_id`, `task_id`, `parent_session_id`, `child_session_id`, `provider_policy_ref`, `status`, `queued_at`, `acknowledged_at`, `last_heartbeat_at`, `completed_at`
- `artifacts`: `artifact_id`, `task_id`, `session_id`, `kind`, `state`, `path`, `checksum`, `manifest_path`, `created_by`, `created_at`, `published_at`
- `memory_facts`: `fact_id`, `source_kind`, `source_ref`, `session_id`, `task_id`, `fact_type`, `subject`, `predicate`, `object_json`, `confidence`, `promotion_state`, `valid_from`, `valid_to`, `created_at`
- `evaluation_runs`: `eval_id`, `workload_id`, `source_artifact_id`, `backend`, `status`, `score_json`, `created_at`, `completed_at`
- `provider_recommendations`: `recommendation_id`, `eval_id`, `route_scope`, `provider`, `model`, `quality_score`, `latency_score`, `cost_score`, `decision`, `promoted_at`

## Canonical Module Map

Build now:

- `dharma_swarm/context_compiler.py`
  - compile bounded context bundles from session state, tasks, operator intent, memory, artifacts, workspace diffs, and policy
- `dharma_swarm/artifact_manifest.py`
  - write/read machine-readable artifact manifests with provenance, checksums, lineage, publish state
- `dharma_swarm/rag_ingest_bridge.py`
  - export only curated artifacts and promoted memory summaries into NVIDIA RAG ingestion
- `dharma_swarm/flywheel_exporter.py`
  - export provenanced workload records, traces, and gold artifacts into Data Flywheel jobs
- `dharma_swarm/evaluation_registry.py`
  - persist eval outcomes and provider recommendations back into canonical truth
- `dharma_swarm/workspace_leases.py`
  - formalize isolated work zones, shared-zone leases, and promotion rules around `file_lock.py`

Extend current seams:

- `dharma_swarm/message_bus.py`
  - become the canonical SQLite transport/query seam for the runtime spine
- `dharma_swarm/operator_bridge.py`
  - stay the precedent for queue/claim/ack/recovery semantics; extend into active runners
- `dharma_swarm/session_ledger.py`
  - continue as append-only audit fact emission into JSONL/runtime envelopes
- `dharma_swarm/runtime_contract.py`
  - standardize portable `EventEnvelope` / `ArtifactEnvelope` / `ContextBundleEnvelope`
- `dharma_swarm/provider_policy.py`
  - consume governed recommendations, not raw accelerator output
- `dharma_swarm/engine/provenance.py`
  - evolve from append-only session logs to artifact/task/session lineage blocks
- `dharma_swarm/engine/event_memory.py`
  - absorb temporal event recall and write-through memory indexing

Later:

- `dharma_swarm/memory_lattice.py`
  - only once the event + fact + retrieval seams are stable
- `dharma_swarm/operator_cockpit.py`
  - if the TUI surface needs a dedicated backing model

## Context Compiler Contract

`ContextCompiler` should produce a `ContextBundle` per run with:

- `bundle_id`
- `session_id`
- `task_id`
- `trace_id`
- `budget_tokens`
- `sections`
- `source_refs`
- `policy_refs`
- `generated_at`

Assembly order:

1. always-on operator/session identity
2. active task + success criteria
3. relevant recent turns and continuity snapshot
4. promoted memory facts
5. retrieved artifacts and cited event history
6. workspace diff summary
7. policy/governance constraints
8. optional accelerator retrieval enrichment

Rules:

- Prefer structured facts over prose summaries.
- Prefer cited artifacts over uncited memory.
- Drop low-value history before dropping active task state.
- Record the final assembled bundle into `context_bundles`.
- Never let RAG or vector recall override canonical local truth; they enrich it.

## Workspace Model

Default workspace rule:

- every agent writes inside an isolated work zone
- shared zones are explicit
- writable shared zones require a lease
- publication into `shared/published/` is an explicit promotion step

Target zones:

- `workspace/agents/<agent_id>/<task_id>/`
- `workspace/shared/inbox/`
- `workspace/shared/scratch/`
- `workspace/shared/published/`

Promotion contract:

1. artifact created in isolated workspace
2. manifest + checksum recorded
3. operator or policy marks artifact promotable
4. lease acquired for shared publication
5. promoted copy written to shared zone
6. optional git commit only after promotion

## NVIDIA + Data Flywheel Boundary

NVIDIA services attach as accelerator lanes around the sovereign spine:

- `NVIDIA NIM` = inference backend reachable through `providers.py`
- `NVIDIA RAG` = retrieval/ingest accelerator via `integrations/nvidia_rag.py`
- `Data Flywheel` = optimization/eval loop via `integrations/data_flywheel.py`

They do not own:

- task truth
- session truth
- claim state
- artifact authority
- durable memory truth
- provider routing decisions

They do accelerate:

- heavy retrieval and grounded answering
- ingest of curated published artifacts
- workload-based evaluation and model recommendation

## End-to-End Loop: `DGC -> RAG -> Flywheel -> Provider Policy`

1. DGC run starts.
   - `tasks`, `task_claims`, `delegation_runs` update in `runtime.db`
   - lifecycle envelope appended to `events/task_lifecycle.jsonl`

2. Agent works in isolated workspace.
   - partial outputs stay local
   - artifact manifest recorded when a useful artifact is produced

3. Artifact is promoted.
   - `artifacts` + `artifact_links` rows inserted
   - payload stored under `artifacts/<artifact_id>/`
   - provenance linked to task/session/agent/model

4. `rag_ingest_bridge.py` selects promotable knowledge.
   - include published docs, verified reports, promoted summaries, stable facts
   - exclude scratchpads, transient chatter, and unverified notes

5. `ContextCompiler` assembles local context first.
   - local memory/artifact/event recall is primary
   - NVIDIA RAG results may extend the bundle with citations

6. `flywheel_exporter.py` emits workload records.
   - include `workload_id`, provider/model path, inputs, outputs, eval signals, artifact refs, and outcome labels
   - append exported batch metadata to `events/flywheel_exports.jsonl`

7. `evaluation_registry.py` records flywheel returns.
   - store eval job status, scorecards, candidate routes, and promotion status

8. `provider_policy.py` can adopt a recommendation only through explicit policy.
   - accelerator output is advisory until promoted

## What Gets Indexed

RAG/semantic index by default:

- published documents
- promoted summaries
- verified research artifacts
- stable memory facts
- artifact manifests

Do not index by default:

- transient scratch work
- chain-of-thought-like notes
- noisy session chatter
- stale task debris

## First 5 Build Moves

1. Build `dharma_swarm/artifact_manifest.py`
   - make artifacts publishable, checksummed, and ingestable
2. Build `dharma_swarm/context_compiler.py`
   - compile context bundles from local truth first
3. Build `dharma_swarm/rag_ingest_bridge.py`
   - promote curated artifacts into the NVIDIA ingest lane
4. Build `dharma_swarm/flywheel_exporter.py`
   - export provenanced workload records to the flywheel lane
5. Build `dharma_swarm/evaluation_registry.py`
   - close the loop from eval output back to canonical provider policy

## Autonomous 5-Hour Loop

Existing proven harness:

```bash
cd /Users/dhyana/dharma_swarm
POLL_SECONDS=300 USE_CAFFEINATE=1 scripts/start_allout_tmux.sh 5
```

Why this lane:

- already emits heartbeat + logs + snapshots
- already runs mission preflight
- already probes NVIDIA RAG and Flywheel health
- already synthesizes per-cycle TODO files

Known local caveat:

- on this host, local NVIDIA RAG self-heal will remain blocked unless remote endpoints are wired or GPU-backed infra is available
- that does not block core DGC autonomy work; it limits accelerator validation during the loop
