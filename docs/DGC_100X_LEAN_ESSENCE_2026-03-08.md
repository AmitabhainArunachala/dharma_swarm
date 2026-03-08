# DGC 100x Lean Essence Blueprint (2026-03-08)

## 0) What DGC Itself Is Signaling Right Now

Snapshot from `python -m dharma_swarm.dgc_cli mission-status --json`:

- Core mission spine is healthy: `6/6` checks pass
  - planner/executor separation
  - circuit breaker
  - traceability fields
  - think-points
  - memory survival instinct
  - TUI plan-mode contract
- `tracked_wiring` is weak: `0/8` mission-critical files are local-only (not tracked in git)
- Accelerator lane is blocked:
  - NVIDIA RAG health blocked
  - ingest health blocked
  - flywheel URL returning `404`

Interpretation:
- The cognitive spine is mostly present.
- Operational reliability and reproducibility are not yet at the same level.
- The biggest risk is not missing ideas; it is drift + unverifiable wiring.

---

## 1) Keep / Cut / Add (Lean, not bloated)

### KEEP (high leverage patterns already aligned)

1. Planner -> Executor separation as hard contract
- Already present in `dharma_swarm/planner.py` and mission check.
- Keep strict role split: planners never write code; executors never rewrite plan semantics.

2. Reflective reroute instead of dead-stop
- Already in `check_with_reflective_reroute()` and wired into orchestrator/pulse/task transitions.
- Keep this as default recovery path for think-point failures.

3. Circuit breaker behavior
- Keep the “no same-failure infinite retries” rule.
- This is anti-chaos and anti-token-burn.

4. Memory survival instinct
- Keep forced externalization to shared artifacts (`~/.dharma/shared` + notes + marks).

5. Sparse parallelism
- Keep read-heavy multi-agent parallelism.
- Keep write-heavy work mostly serialized through a single edit authority.

### CUT (or demote)

1. Unbounded YOLO loops with no external stop conditions
- Replace with bounded cycles + checkpointed goals + kill criteria.

2. Report inflation without closure
- Demote “new report generation” unless it closes a tracked issue.
- Rule: no new report unless it updates a KPI, a failing test, or a tracked task.

3. Duplicate architecture tracks with ambiguous ownership
- Merge to one spine backlog: no parallel architecture docs that diverge from code.

4. Metrics without verified provenance
- Drop or mark all metrics that cannot be traced to commands/tests/artifacts.

### ADD (highest ROI imports from frontier systems)

1. AGENTS layering discipline (Codex pattern)
- Global + repo + nested override precedence, byte cap, deterministic merge.
- DGC action: use AGENTS-style instruction inheritance explicitly in TUI/session bootstrap.

2. Explicit sandbox/approval profiles (Codex + Claude pattern)
- Promote named modes:
  - `readonly_audit`
  - `workspace_auto`
  - `strict_external`
  - `yolo_local_container`
- Never run “yolo” without profile + workspace boundary + audit trail.

3. Hooks as policy enforcement plane (Claude pattern)
- PreTool/PostTool hook equivalents for DGC commands.
- Enforce: redaction, dangerous command checks, traceability fields, checkpoint heartbeat.

4. Ledger-based orchestration loop (Magentic-One pattern)
- Add two explicit ledgers:
  - `task_ledger` (plan + assumptions + success criteria)
  - `progress_ledger` (step evidence + failure signatures + pivots)
- Replan trigger when progress stalls for N iterations.

5. Edit->lint/test->verify->record loop (Aider pattern)
- For every write path, enforce post-edit validation before task completion.
- Persist diff, test results, and rollback hints with the task artifact.

6. Runtime isolation as first-class (OpenHands/SWE-agent pattern)
- Standardize heavy autonomous runs inside explicit isolated runtime (container/remote sandbox), not mixed host context.

---

## 2) 14-Day Execution Plan (mapped to current DGC modules)

## Days 1-2: Mission Control Hardening

Targets:
- `dharma_swarm/dgc_cli.py`
- `scripts/mission_preflight.sh`
- `scripts/start_caffeine*_tmux.sh`

Deliverables:
- Preflight becomes mandatory in automation modes (`MISSION_BLOCK_ON_FAIL=1` default for unattended runs).
- Fail fast if `tracked_wiring` misses mission-critical files.
- Clear one-command health output with severity classes (`OK/WARN/BLOCKED/FAIL`).

Success criteria:
- Unattended runs cannot start when spine is inconsistent.

## Days 3-4: Ledger Layer

Targets:
- `dharma_swarm/orchestrator.py`
- `dharma_swarm/task_board.py`
- `dharma_swarm/message_bus.py`

Deliverables:
- Add `task_ledger.jsonl` + `progress_ledger.jsonl` per session.
- Log every pivot with failure signature and pivot reason.
- Auto-replan trigger after repeated signature threshold.

Success criteria:
- Every completed task has reconstructable decision history.

## Days 5-6: Hook Plane + Policy Profiles

Targets:
- `hooks/telos_gate.py`
- `dharma_swarm/telos_gates.py`
- `config/*.toml` (new profile definitions)

Deliverables:
- Pre-action policy hook: enforce mode, boundary, traceability refs.
- Post-action hook: enforce evidence capture and artifact linking.
- Canonical profiles: `readonly_audit`, `workspace_auto`, `strict_external`, `yolo_local_container`.

Success criteria:
- Every action can be traced to an explicit profile and policy decision.

## Days 7-8: Write Authority and Parallel Discipline

Targets:
- `dharma_swarm/orchestrator.py`
- `dharma_swarm/agent_runner.py`
- `dharma_swarm/startup_crew.py`

Deliverables:
- Enforce single write-authority agent per mutable workspace segment.
- Keep parallel subagents read-heavy by default.
- Add merge gate for conflicting proposals.

Success criteria:
- Parallel runs no longer create race-condition patch conflicts.

## Days 9-10: Quality Flywheel

Targets:
- `dharma_swarm/evolution.py`
- `dharma_swarm/archive.py`
- tests for adversarial gates + workflow regressions

Deliverables:
- Mandatory post-edit quality loop: lint/test/targeted stress before archive.
- Archive entries must include: spec_ref, requirement_refs, verification evidence.
- Add fail-closed behavior for missing evidence.

Success criteria:
- No proposal archives without verifiable proof chain.

## Days 11-12: Accelerator Lane Recovery (NVIDIA + data flywheel)

Targets:
- `dharma_swarm/integrations/nvidia_rag.py`
- `dharma_swarm/integrations/data_flywheel.py`
- `scripts/start_caffeine_nvidia_tmux.sh`
- `docs/NVIDIA_INFRA_SELF_HEAL.md`

Deliverables:
- Fix endpoint contracts and health probes (explicit expected paths/response schema).
- Distinguish infra states: `not_configured`, `unreachable`, `misconfigured`, `healthy`.
- Add fallback route when NVIDIA lane unavailable.

Success criteria:
- Mission status shows deterministic accelerator state with actionable diagnostics.

## Days 13-14: Gauntlet + Freeze

Targets:
- `docs/DGC_SUBAGENT_GAUNTLET_PROMPT.md`
- `scripts/*gauntlet*` or equivalent runner
- `tests/tui/test_app_plan_mode.py`, `tests/test_orchestrator.py`, `tests/test_telos_gates.py`

Deliverables:
- Run full-system gauntlet with standardized scorecard.
- Freeze and tag stable profile set.
- Publish operator runbook for daily/overnight use.

Success criteria:
- One reproducible run demonstrates safety + throughput + memory persistence.

---

## 3) Anti-Bloat Operating Contract

These are mandatory guardrails to keep DGC sharp.

1. One new abstraction in, one old abstraction out
- If a layer is added, remove or collapse overlap.

2. No feature without a kill-switch
- Every autonomous component must be disable-able at runtime.

3. No metric without source pointer
- Every KPI must map to command output, test run, or log artifact.

4. No parallel writes without ownership model
- Parallel research yes, parallel mutation only via controlled merge.

5. No report-only cycles
- Each cycle must close at least one tracked task or failing check.

6. No new provider mode without profile + tests
- Provider additions require explicit security/approval profile and smoke tests.

7. No hidden magic
- Every “self-evolving” step must emit: input, decision, evidence, output.

---

## 4) What To Run First (Operator sequence)

```bash
cd ~/dharma_swarm

# 1) Hard truth snapshot
python3 -m dharma_swarm.dgc_cli mission-status --json

# 2) Strict preflight
MISSION_STRICT_CORE=1 MISSION_REQUIRE_TRACKED=1 MISSION_BLOCK_ON_FAIL=1 scripts/mission_preflight.sh

# 3) Core regression slice
pytest -q tests/test_telos_gates.py tests/tui/test_app_plan_mode.py tests/test_orchestrator.py

# 4) Only then start autonomous lane
scripts/start_caffeine_tmux.sh 04:00
```

---

## 5) Source signals used for this blueprint

- OpenAI Codex docs: Sandboxing, Multi-agents, AGENTS.md, Agent approvals/security
- OpenAI Codex GitHub README
- Anthropic Claude Code docs: Security, IAM/permissions modes, Hooks
- Microsoft AutoGen docs: Magentic-One architecture (Task Ledger + Progress Ledger + replan)
- Aider docs: lint/test loop, git-integrated safe iteration
- OpenHands docs: runtime isolation patterns
- SWE-agent docs: benchmarking/evaluation discipline and trajectory inspection
- Internal DGC artifacts:
  - `specs/DGC_TERMINAL_ARCHITECTURE_v1.1.md`
  - `AGENT_PROMPT_SYNTHESIS.md`
  - `docs/NVIDIA_INFRA_SELF_HEAL.md`
  - `~/.dharma/shared/gap_closure_1772884910/*`
  - `~/.dharma/shared/olympus_gauntlet_1772893368/reports/*`

