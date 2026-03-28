# Honors Checkpoint Design

**Date:** 2026-03-28

**Goal:** turn high-value analytical task completion into a defended artifact instead of a pretty string.

## Problem

The current phase-2 lane blocks obvious junk, but it still accepts elegant unsupported synthesis. The runner checks semantic form, not whether the answer can defend itself under evidence, auditability, and system-effect pressure.

That means a task can still be marked complete even when it does not clearly list the files it used, the tests it relied on, the context it drew from, or the concrete repairs it recommends.

## Design

The first phase-3 slice adds one canonical checkpoint with three layers:

1. `CompletionContract`
   Each serious task may declare an honors contract in task metadata. The contract says what the answer must contain: stakeholders, required sections, evidence references, minimum file references, minimum test references, minimum fix proposals, and whether system-level effects are required.

2. `DefensePacket`
   After the model returns a candidate answer, the runner extracts a machine-readable defense packet from the final text. This packet records things like referenced files, tests, evidence paths, context terms, stakeholder mentions, fix proposals, residual risks, and system effects, plus supported-claim vs unsupported-claim heuristics.

3. `JudgePack`
   The runner scores the completion on four gates:
   - responsiveness
   - grounding
   - auditability
   - causal awareness

   The judge pack stores per-gate pass/fail, a final score, and explicit failure reasons.

The accepted checkpoint is persisted back onto `task.metadata`, and the orchestrator refuses to mark the task `COMPLETED` unless the checkpoint verdict passes.

## Data Flow

1. Task enters with `completion_contract` metadata.
2. Prompt builder injects the contract into the task prompt so the model knows the rubric.
3. Runner gets a completion, runs the existing semantic gate, then runs the honors checkpoint.
4. If the honors checkpoint fails and repair budget remains, the runner asks for a repair against the failed gates.
5. If the checkpoint passes, runner stores the full packet on the task metadata.
6. Orchestrator verifies the stored checkpoint before stamping completion.

## Error Handling

- No contract: preserve current behavior.
- Contract present but no checkpoint packet: fail closed.
- Contract present and checkpoint fails: raise a completion error and let the existing retry/failure machinery handle it.
- Orchestrator sees a failed or missing checkpoint on a supposedly successful task: convert the task to failed instead of completed.

## Testing

Focused tests should cover:

- contract parsing and normalization from task metadata
- prompt injection of the honors contract
- runner repair on semantically fine but contract-failing output
- defense packet persistence on accepted output
- orchestrator rejection when the runner returns a string without a passing judge pack
