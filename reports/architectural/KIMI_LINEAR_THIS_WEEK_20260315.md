# Kimi Linear This Week

Date: 2026-03-15
Repo: `/Users/dhyana/dharma_swarm`
Status: active investigation

## What To Check Out This Week

Do not treat Kimi Linear or other `O(n log n)` / linear-ish backbones as a full runtime replacement.
Treat them as candidate sidecar workers for jobs where your system currently pays too much to read and compress long context.

The first question is not:

- "Should dharma_swarm switch architectures?"

The first question is:

- "Can a long-context sidecar produce better memory artifacts per dollar than our current stack?"

## Concrete Test Target

Candidate model:

- `moonshotai/Kimi-Linear-48B-A3B-Instruct`

Reference research branch:

- `/Users/dhyana/repos/log-linear-attention`

Practical first repo:

- `/Users/dhyana/repos/Kimi-Linear`

## The Jobs To Test

Run the sidecar only on these jobs first:

1. Repo digestion
2. Conversation condensation
3. Trace summarization
4. Contradiction hunt
5. Memory distillation

These jobs are defined by:

- `benchmarks/long_context_sidecar_suite.py`
- `dharma_swarm/long_context_sidecar_eval.py`

Generated packet for this week:

- `reports/architectural/kimi_linear_sidecar_manifest_20260315.json`

## Commands

Build the workload packet:

```bash
cd /Users/dhyana/dharma_swarm
python benchmarks/long_context_sidecar_suite.py \
  --candidate-model moonshotai/Kimi-Linear-48B-A3B-Instruct \
  --baseline-model current-premium-model \
  --format json \
  --output reports/architectural/kimi_linear_sidecar_manifest_20260315.json
```

Readable version:

```bash
cd /Users/dhyana/dharma_swarm
python benchmarks/long_context_sidecar_suite.py \
  --candidate-model moonshotai/Kimi-Linear-48B-A3B-Instruct \
  --baseline-model current-premium-model \
  --format markdown \
  --output reports/architectural/kimi_linear_sidecar_manifest_20260315.md
```

If you have the hardware and serving stack, the first deployment path to test is:

```bash
vllm serve moonshotai/Kimi-Linear-48B-A3B-Instruct \
  --port 8000 \
  --tensor-parallel-size 4 \
  --max-model-len 1048576 \
  --trust-remote-code
```

If you do not have the hardware ready, still use the packet and run the same jobs against any reachable long-context candidate endpoint.

## Success Condition

Promote the sidecar lane only if it clearly wins on at least one job:

- better memory shards
- better trace compression
- cheaper large-context digestion
- better contradiction finding
- materially smaller carry-forward packets with no loss of important state

## Kill Condition

Do not spend more time on this lane this week if:

- the setup cost is higher than the likely gain
- it does not beat the current stack on one real job
- the outputs are verbose but not reusable
- it cannot preserve evidence and carry-forward state

## Architectural Rule

Even if Kimi Linear looks good, keep the architecture:

- canonical memory plane in `event_memory.py`
- retrieval and semantic routing in `hybrid_retriever.py` and `semantic_memory_bridge.py`
- lattice-style memory routing as the higher-order organizer
- long-context models as sidecars until proven otherwise

This is a sidecar investigation, not a rewrite order.
