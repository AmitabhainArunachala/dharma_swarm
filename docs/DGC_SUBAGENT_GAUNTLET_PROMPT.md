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

