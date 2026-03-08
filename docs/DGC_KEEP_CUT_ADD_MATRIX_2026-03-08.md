# DGC Keep/Cut/Add Matrix (System-by-System)

Date: 2026-03-08
Scope: DGC vs Codex, Claude Code, Magentic-One, Aider, OpenHands, SWE-agent

## A) Keep (already good in DGC)

| Pattern | Why keep | Current DGC anchor |
|---|---|---|
| Planner-executor separation | Reduces plan drift and self-contradiction | `dharma_swarm/planner.py`, mission core check |
| Reflective reroute on think-point failure | Prevents brittle dead-stops while preserving safety | `dharma_swarm/telos_gates.py` |
| Circuit breaker | Stops infinite retries on same failure | `dharma_swarm/evolution.py`, swarm/pulse loops |
| Memory externalization | Survives context loss between sessions | `~/.dharma/shared`, notes persistence |
| Role-based crew bootstrap | Gives specialization while staying provider-open | `dharma_swarm/startup_crew.py` |

## B) Add (high ROI imports)

| Source system | Pattern to import | Why it matters | DGC implementation target | Priority |
|---|---|---|---|---|
| Codex | AGENTS hierarchical discovery + byte budget + fallback filenames | Deterministic instruction layering and less prompt drift | TUI/session bootstrap + `.dharma` instruction loader | P0 |
| Codex | Named sandbox/approval profiles (`read-only`, `workspace-write`, `danger-full-access`; `untrusted`, `on-request`, `never`) | Makes autonomy explicit and auditable | `dgc_cli`, automation launchers, `mission_preflight` | P0 |
| Codex | Rules/prefix-rule governance for escalations | Fine-grained command control without killing speed | Policy layer around escalation decisions | P1 |
| Codex | Multi-agent role config (`max_threads`, `max_depth`, per-role config) | Controlled parallelism and bounded nesting | `startup_crew.py`, orchestrator spawn policies | P1 |
| Claude Code | Hook lifecycle (PreToolUse/PostToolUse/PermissionRequest/Subagent events) | Real policy enforcement at execution boundaries | `hooks/telos_gate.py` + new DGC hook dispatcher | P0 |
| Claude Code | Decision-capable hooks (allow/deny with reason) | Hardens safety while preserving automation | integrate with telos decisions + audit logs | P0 |
| Magentic-One | Task Ledger + Progress Ledger + explicit outer/inner loop replan | Better long-horizon coherence | `orchestrator.py`, `task_board.py`, new ledgers | P0 |
| Aider | Automatic lint/test after edits + git-integrated rollback (`/undo` equivalent behavior) | Strong quality loop, lower regression risk | mutation/apply pathways in `agent_runner.py` and evolution archive pipeline | P1 |
| OpenHands | Runtime isolation first (container default, local runtime warning) | Safer unattended execution | night loops + NVIDIA lane + yolo mode routing | P1 |
| SWE-agent | Trajectory inspection and replay discipline | Debuggable autonomy and reproducible failures | add trajectory/trace artifacts + replay command wrappers | P1 |

## C) Cut / Do-not-import

| Anti-pattern | Why reject | Replacement |
|---|---|---|
| Unbounded all-night loops without hard objectives | Burns tokens, yields report spam | Bounded cycles + KPI gates + stop conditions |
| Parallel write agents on same area | Race conditions and merge chaos | single write authority + read-heavy satellites |
| “Mission complete” claims without evidence map | False confidence | mandatory claim->evidence table |
| New architecture docs that outpace code | strategic drift | code-first roadmap with tracked tasks |
| YOLO without profile declaration | hidden risk | required `autonomy profile` on every unattended run |

## D) 14-day merge map (module-level)

### P0 (Week 1)

1. Policy profiles and trust modes
- Files: `dharma_swarm/dgc_cli.py`, `scripts/mission_preflight.sh`, `scripts/start_caffeine*_tmux.sh`
- Outcome: unattended starts blocked unless profile + preflight pass.

2. Hook plane
- Files: `hooks/telos_gate.py`, `dharma_swarm/telos_gates.py`
- Outcome: before/after tool checks with explicit allow/deny outputs and logged reasons.

3. Ledger integration
- Files: `dharma_swarm/orchestrator.py`, `dharma_swarm/task_board.py`, `dharma_swarm/message_bus.py`
- Outcome: `task_ledger` + `progress_ledger` emitted every cycle.

### P1 (Week 2)

4. Parallel discipline and role caps
- Files: `dharma_swarm/startup_crew.py`, `dharma_swarm/orchestrator.py`
- Outcome: enforce `max_threads`, `max_depth`, write-authority constraints.

5. Quality flywheel hardening
- Files: `dharma_swarm/evolution.py`, `dharma_swarm/archive.py`, tests
- Outcome: no archive without lint/test/evidence fields.

6. Accelerator lane normalization
- Files: `dharma_swarm/integrations/nvidia_rag.py`, `dharma_swarm/integrations/data_flywheel.py`
- Outcome: precise health states and robust fallback behavior.

## E) Anti-bloat scoring gate (use before merging new feature)

Score each 0/1. Merge only if score >= 5/7.

1. Is there a measurable KPI this feature improves?
2. Is there a kill-switch at runtime?
3. Is there a failing test this change addresses or a new test proving value?
4. Does it reduce net complexity (or justify added complexity)?
5. Is ownership clear (single module owner + runbook entry)?
6. Does it preserve provider-agnostic operation?
7. Does it improve evidence traceability?

## F) Immediate truth from current state

- Mission core checks: `6/6` pass.
- Tracked wiring: `0/8` (critical local-only debt).
- Accelerator lane: blocked (RAG/ingest unreachable, flywheel path mismatch).
- Targeted regression slice run now: `60 passed` (`test_telos_gates`, `test_app_plan_mode`, `test_orchestrator`).

Interpretation:
- The core behavior model is present.
- Operational reproducibility is the current bottleneck.

