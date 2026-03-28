# Offline Training Lane

## Scope

This lane is export-only.

It exists to package:

- trajectories
- grade cards
- reward signals

for later offline experimentation outside the live `dharma_swarm` runtime.

## Non-Goals

- no PPO execution
- no DPO execution
- no GRPO execution
- no LoRA execution
- no VERL launch path
- no live training scheduler inside the runtime

## Export Format

- `trajectories.jsonl`: ordered message or step records
- `grades.json`: serialized grade-card payload
- `rewards.json`: serialized reward-signal payload
- `manifest.json`: bundle metadata and member listing

## Invariant

The live runtime may emit offline bundles, but it must not start training jobs.
