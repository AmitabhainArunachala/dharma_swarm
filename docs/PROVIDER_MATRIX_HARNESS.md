# Provider Matrix Harness

The live provider/model matrix harness is wired into the CLI as:

```bash
dgc provider-matrix [options]
```

## What It Does

- Builds a curated target matrix from the canonical provider hierarchy.
- Keeps `Codex` and `Opus` sovereign at the top of the lane order.
- Expands delegated lanes across `GLM`, `Kimi`, `MiniMax`, `Qwen`, and other cheap/open providers.
- Runs a fixed deployment-oriented prompt corpus.
- Scores responses for uptime, schema compliance, and latency.
- Writes operator-facing JSON + Markdown leaderboard artifacts.

## Profiles

- `quick`
  Fast sanity check across the sovereign pair and a small delegated lane set.

- `live25`
  Broad live matrix with 25 curated provider/model lanes.
  The scheduler is prompt-major, so the default budget reaches delegated lanes before it spends on repeated sovereign passes.

## Default Corpus

`deployment`

This corpus asks every lane to produce compact JSON for:

- best deployment wedge
- sovereign/delegated handoff plan
- launch guardrail recommendation

## Budget Model

The harness uses synthetic cost units so it can stop before burning too much paid capacity:

- `free = 1`
- `cheap = 2`
- `paid = 5`

`--budget-units` is not a dollar estimator. It is a deterministic stop condition for mixed-lane sweeps.

## Recommended Runs

Quick local pass:

```bash
dgc provider-matrix --profile quick --max-prompts 1 --budget-units 12
```

Broad live sweep:

```bash
dgc provider-matrix --profile live25 --budget-units 40
```

Deep repeat pass after the broad sweep:

```bash
dgc provider-matrix --profile live25 --max-prompts 3 --budget-units 80
```

Machine-readable output:

```bash
dgc provider-matrix --profile live25 --json
```

Include lanes even when auth/binaries are missing:

```bash
dgc provider-matrix --profile live25 --include-unavailable
```

## Artifacts

By default each run writes:

- `~/.dharma/shared/provider_matrix_<RUN_ID>.json`
- `~/.dharma/shared/provider_matrix_<RUN_ID>.md`

Use `--artifact-dir PATH` to redirect output or `--no-artifacts` to suppress writes.

## Status Semantics

- `ok`: response matched the required JSON contract
- `schema_invalid`: provider answered, but did not follow the required schema
- `provider_error`: CLI/provider returned an error banner or access failure in-band
- `timeout`, `auth_failed`, `missing_config`, `unknown_model`, `unreachable`: runtime failures
