# GAIA User Manual

Status: current tracked runtime manual for the GAIA surfaces that exist in this repository on March 27, 2026.

GAIA is the ecological accountability slice inside `dharma_swarm`. In the current tracked tree, the user-facing surface is Python-first:

- `dharma_swarm/gaia_ledger.py`
- `dharma_swarm/gaia_verification.py`
- `dharma_swarm/gaia_fitness.py`
- `dharma_swarm/gaia_platform.py`
- `scripts/gaia_demo.py`

This manual documents those runnable surfaces. The tracked repository now ships a terminal dashboard in `dharma_swarm/gaia_platform.py`; it still does not include a production web product for GAIA.

## What GAIA Does

GAIA closes one auditable loop:

1. measure AI compute and carbon intensity
2. record funding and labor for restoration work
3. register ecological offset claims
4. verify those claims with independent oracles
5. detect drift between claimed impact and verified impact
6. preserve the full trail in a hash-chained ledger

The core design is intentionally strict:

- five unit types: compute, offset, funding, labor, verification
- 3-of-5 oracle verification before an offset is treated as verified
- conservation-law checks to catch overclaiming and double counting
- self-observation metrics to detect Goodhart drift

## Who This Manual Is For

Use this manual if you are any of the following:

- an operator running a pilot accountability loop
- a verifier reviewing restoration evidence
- a technical steward integrating GAIA into a restoration workflow
- a trainer onboarding a new GAIA user

## Quick Start

Render the shipped terminal dashboard:

```bash
python3 -m dharma_swarm.gaia_platform dashboard --model anthropic_claude_ops
```

That command stages a small audited pilot under the chosen data directory, writes a pilot report, and prints:

- the current model/operator profile
- the top approved restoration recommendations
- the staged pilot ledger summary
- the saved audit report path

Generate a richer pilot report with monitoring checkpoints and structured user
feedback:

```bash
python3 -m dharma_swarm.gaia_platform pilot-report \
  --model anthropic_claude_ops \
  --project-id bayou-lafourche-mangroves \
  --feedback-file docs/dse/gaia_pilot_feedback_sample.json
```

That command stages the same auditable pilot chain, then writes:

- `pilot_report.json` with ledger, verification, monitoring, and feedback data
- `pilot_report.md` with an operator-readable summary
- both artifacts under the selected GAIA pilot directory

Run the full end-to-end demo:

```bash
python3 scripts/gaia_demo.py
```

That script walks through the complete GAIA loop:

- compute footprint recording
- project funding
- labor accounting
- offset registration
- 3-of-5 verification
- conservation audit
- Goodhart drift detection
- self-observation and fitness scoring

On the current codebase, the demo completes successfully and prints a full audit trail with:

- total compute CO2e
- total verified offset
- net carbon position
- worker count and labor hours
- chain integrity status
- drift diagnosis

## Mental Model

### The five units

- `ComputeUnit`: measured AI workload energy plus carbon intensity
- `OffsetUnit`: claimed or verified sequestration for a restoration project
- `FundingUnit`: money flowing into the work
- `LaborUnit`: person-hours, skills, and output tied to a project
- `VerificationUnit`: an oracle attestation about a target claim

### The five conservation laws

GAIA checks five invariants:

1. no creation ex nihilo
2. no double counting
3. additionality
4. temporal coherence
5. compositional integrity

If an offset is claimed before enough evidence exists, GAIA will show a conservation violation instead of silently accepting the claim.

### Verification rule

Offsets become verified when at least three distinct oracle types agree. The current oracle set is:

- `satellite`
- `iot_sensor`
- `human_auditor`
- `community`
- `statistical_model`

## First Session

### 1. Start a ledger

```python
from pathlib import Path

from dharma_swarm.gaia_ledger import GaiaLedger

ledger = GaiaLedger(data_dir=Path(".gaia_session"))
```

If you do not provide `data_dir`, GAIA uses:

```text
~/.dharma/gaia_ledger
```

### 2. Record compute

```python
from dharma_swarm.gaia_ledger import ComputeUnit

compute = ComputeUnit(
    provider="anthropic",
    energy_mwh=12.0,
    carbon_intensity=0.35,
    workload_type="inference",
    metadata={"model": "claude_ops_batch"},
)
ledger.record_compute(compute)
```

`ComputeUnit.co2e_tons` is derived automatically from `energy_mwh * carbon_intensity`.

### 3. Register a restoration claim

```python
from dharma_swarm.gaia_ledger import FundingUnit, LaborUnit, OffsetUnit

ledger.record_funding(
    FundingUnit(
        amount_usd=25000.0,
        source="pilot_buyer",
        destination="bayou_restoration_coop",
        purpose="mangrove_restoration",
    )
)

ledger.record_labor(
    LaborUnit(
        worker_id="worker-001",
        project_id="bayou-lafourche-mangroves",
        hours=40.0,
        skill_type="planting",
        location="Lafourche Parish, LA",
        output_metric=500.0,
        output_unit="seedlings",
        wage_rate=30.0,
    )
)

offset = OffsetUnit(
    project_id="bayou-lafourche-mangroves",
    co2e_tons=120.0,
    method="mangrove_restoration",
)
ledger.record_offset(offset)
```

At this stage the offset is only a claim. It is not yet verified.

### 4. Verify the claim

```python
from dharma_swarm.gaia_verification import OracleVerdict, verify_offset

verdicts = [
    OracleVerdict(
        oracle_type="satellite",
        target_id=offset.id,
        confidence=0.86,
        evidence_summary="Canopy growth visible in multispectral imagery.",
        agrees_with_claim=True,
    ),
    OracleVerdict(
        oracle_type="iot_sensor",
        target_id=offset.id,
        confidence=0.82,
        evidence_summary="Ground sensors show improved soil carbon.",
        agrees_with_claim=True,
    ),
    OracleVerdict(
        oracle_type="human_auditor",
        target_id=offset.id,
        confidence=0.90,
        evidence_summary="Field audit confirms restoration activity.",
        agrees_with_claim=True,
    ),
]

session, coordination = verify_offset(ledger, offset.id, verdicts)
```

If three distinct oracle types agree, GAIA records verification units and marks the offset as verified.

### 5. Review health and integrity

```python
from dharma_swarm.gaia_fitness import EcologicalFitness, detect_goodhart_drift

summary = ledger.summary()
fitness = EcologicalFitness().weighted_score(ledger)
drift = detect_goodhart_drift(ledger)
```

The most important outputs are:

- `summary["chain_valid"]`
- `summary["conservation_violations"]`
- `summary["total_compute_co2e"]`
- `summary["total_verified_offset"]`
- `summary["net_carbon_position"]`
- `drift["is_drifting"]`
- `drift["diagnosis"]`

### 6. Save and reopen the ledger

```python
path = ledger.save()
print(path)
```

This writes `ledger.jsonl` inside the ledger directory. To reopen it later:

```python
ledger = GaiaLedger(data_dir=Path(".gaia_session"))
ledger.load()
```

## Reading The Output

### `ledger.summary()`

`summary()` returns a single dictionary with counts and health metrics, including:

- entries
- chain validity
- unit counts
- total compute CO2e
- total verified offset
- net carbon position
- total labor hours
- total funding
- worker count
- conservation violation list

Interpretation:

- positive `net_carbon_position` means the system is still emitting more than it has credibly offset
- zero or negative `net_carbon_position` means the ledger is at or beyond net-zero on verified terms
- nonzero `conservation_violations` means a human should inspect the claim path before relying on it

### Goodhart drift report

`detect_goodhart_drift()` exists to answer a simple question:

Is the system producing offset volume faster than it is producing verified ecological truth?

If drift is detected, the report says so directly:

```text
GOODHART DRIFT DETECTED: High offset claims with low verification.
```

If coverage is adequate, the current code reports:

```text
No drift detected. Verification coverage adequate.
```

### Self-observation

GAIA also computes a self-referential fitness reading through `gaia_observer_function()` and `observe_ledger()`. Lower self-referential fitness is healthier in the current implementation because it means the ledger's internal model is contracting around verified rather than merely claimed impact.

## Example: The Demo Scenario

The shipped demo uses a Louisiana mangrove restoration example and currently produces this shape of outcome:

- 50,000 MWh training workload plus 8,760 MWh inference workload
- $2.5M funding to a coastal restoration cooperative
- 5 workers and 800 labor hours
- 25,000 claimed tons CO2e
- 4 agreeing oracles and 1 dissenting oracle
- verified offset below the full claim because confidence weighting still applies

This is intentional. GAIA is designed to preserve disagreement and confidence weighting rather than flatten them into a single marketing-friendly number.

## Common Tasks

### Run the end-to-end example

```bash
python3 scripts/gaia_demo.py
```

### Run the GAIA test suite

```bash
pytest tests/test_gaia.py tests/test_gaia_ledger.py tests/test_gaia_verification.py tests/test_gaia_fitness.py
```

### Inspect the current working assumptions

Read these files:

- `dharma_swarm/gaia_ledger.py`
- `dharma_swarm/gaia_verification.py`
- `dharma_swarm/gaia_fitness.py`
- `scripts/gaia_demo.py`

## Troubleshooting

### The offset never becomes verified

Check for one of these:

- fewer than three agreeing oracle types
- duplicate oracle submissions of the same type
- low-confidence or dissenting verdicts

### The chain is invalid

`summary()["chain_valid"]` should be `True`. If it is not, treat the ledger as tampered or corrupted and reload from a known-good source.

### The net carbon position stays positive

That means verified offsets are still below measured compute emissions. GAIA is behaving correctly. Either increase real restoration output or reduce compute demand.

### Goodhart drift is detected

This usually means you have registered claims faster than you have verified them. Stop issuing impact claims until verification coverage improves.

### Conservation violations remain after verification

A verified offset can still leave a violation if the weighted verified total is still below the claimed total. This is expected when confidence weighting is conservative.

## Current Boundaries

Be explicit about what the current tracked runtime does not yet provide:

- no GAIA web dashboard in the tracked tree
- no registry integrations for live satellite or sensor vendors
- no multi-tenant user management layer

This manual is therefore a runtime manual for the auditable GAIA core plus the shipped terminal platform surface, not a promise about future web product layers.

## Next Documents

For onboarding and workshops, continue with:

- `docs/dse/GAIA_TRAINING_WORKBOOK.md`
- `docs/dse/GAIA_FACILITATOR_GUIDE.md`
