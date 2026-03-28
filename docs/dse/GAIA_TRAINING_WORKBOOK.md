# GAIA Training Workbook

Audience: first-time GAIA operators, ecological stewards, and technical reviewers.

Format: hands-on workbook that can be completed in 60-90 minutes.

Prerequisites:

- a local checkout of this repository
- `python3`
- the GAIA modules import cleanly in your environment

## Learning Goals

By the end of this workbook, a user should be able to:

1. explain what GAIA verifies and what it refuses to assume
2. run the full GAIA demo
3. record a minimal compute-to-restoration loop in a fresh ledger
4. understand 3-of-5 oracle verification
5. interpret drift, conservation, and chain-integrity signals

## Module 1: Orientation

Read [`../../gaia_ui.md`](../../gaia_ui.md) first.

Answer these questions before touching the code:

1. Why does GAIA separate claimed offsets from verified offsets?
2. Why does GAIA require distinct oracle types?
3. What does a positive net carbon position mean?
4. What is Goodhart drift in the GAIA context?

Expected answers:

- claims are not treated as truth until evidence exists
- distinct oracle types reduce single-channel fraud and blind spots
- the system is still net emitting on verified terms
- the system is optimizing for proxy impact instead of verified impact

## Module 2: Run The Demo

Run:

```bash
python3 scripts/gaia_demo.py
```

Capture the following outputs from your run:

- total compute CO2e
- total verified offset
- net carbon position
- number of agreeing oracles
- number of dissenting oracles
- chain integrity
- drift diagnosis

Checkpoint questions:

1. Why does the demo still show a conservation violation after verification?
2. Why is a dissenting oracle preserved instead of discarded?
3. What evidence suggests the ledger is auditable rather than just descriptive?

Expected reasoning:

- confidence-weighted verified offset is still lower than the total claim
- disagreement is useful information, not noise
- hash-chain integrity and typed units create a durable audit surface

## Module 3: Build A Minimal Ledger

Create a file called `tmp_gaia_training.py` outside the repository or work in a REPL.

Use this exercise skeleton:

```python
from pathlib import Path

from dharma_swarm.gaia_ledger import ComputeUnit, FundingUnit, GaiaLedger, LaborUnit, OffsetUnit

ledger = GaiaLedger(data_dir=Path(".gaia_training"))

ledger.record_compute(
    ComputeUnit(
        provider="pilot_lab",
        energy_mwh=4.0,
        carbon_intensity=0.4,
        workload_type="inference",
    )
)

ledger.record_funding(
    FundingUnit(
        amount_usd=5000.0,
        source="pilot_lab",
        destination="wetland_coop",
        purpose="wetland_restoration",
    )
)

ledger.record_labor(
    LaborUnit(
        worker_id="steward-01",
        project_id="wetland-pilot",
        hours=16.0,
        skill_type="monitoring",
        output_metric=12.0,
        output_unit="survey_plots",
        wage_rate=28.0,
    )
)

offset = OffsetUnit(
    project_id="wetland-pilot",
    co2e_tons=3.0,
    method="wetland_restoration",
)
ledger.record_offset(offset)

print(ledger.summary())
```

What you should see before verification:

- one compute unit
- one funding unit
- one labor unit
- one offset unit
- zero verified offset
- at least one conservation issue because the claim is not yet verified

## Module 4: Verify The Claim

Extend the previous exercise:

```python
from dharma_swarm.gaia_verification import OracleVerdict, verify_offset

session, coordination = verify_offset(
    ledger,
    offset.id,
    [
        OracleVerdict(
            oracle_type="satellite",
            target_id=offset.id,
            confidence=0.80,
            agrees_with_claim=True,
            evidence_summary="Canopy recovery visible in image stack.",
        ),
        OracleVerdict(
            oracle_type="iot_sensor",
            target_id=offset.id,
            confidence=0.78,
            agrees_with_claim=True,
            evidence_summary="Soil moisture and carbon moving in the expected direction.",
        ),
        OracleVerdict(
            oracle_type="community",
            target_id=offset.id,
            confidence=0.84,
            agrees_with_claim=True,
            evidence_summary="Local stewards confirm work completed and area improving.",
        ),
    ],
)

print(session.meets_threshold)
print(ledger.summary())
```

Checkpoint questions:

1. What changed in the ledger summary after verification?
2. Did the claim become fully trusted or confidence-weighted?
3. Why is that distinction important?

Expected answers:

- verification units were added and the offset can become verified
- trust is still confidence-weighted
- ecological claims should degrade gracefully under uncertainty rather than flip from zero to absolute certainty

## Module 5: Drift Drill

Create an intentionally bad ledger:

```python
from dharma_swarm.gaia_fitness import detect_goodhart_drift
from dharma_swarm.gaia_ledger import GaiaLedger, OffsetUnit

bad = GaiaLedger()
for i in range(5):
    bad.record_offset(OffsetUnit(project_id=f"claim-{i}", co2e_tons=100.0))

print(detect_goodhart_drift(bad))
```

What you should observe:

- `is_drifting` becomes `True`
- the diagnosis explicitly names Goodhart drift

Discussion prompt:

Why is it useful for GAIA to penalize overclaiming even if those claims might later be verified?

## Module 6: Persistence And Audit Trail

Save and reload your training ledger:

```python
path = ledger.save()
print(path)

reloaded = GaiaLedger(data_dir=Path(".gaia_training"))
reloaded.load()
print(reloaded.summary())
```

You have completed the module correctly if:

- the save path ends in `ledger.jsonl`
- the reloaded ledger retains the entries you recorded
- the chain still validates after reload

## Assessment

Mark each item complete only if you can demonstrate it live:

- I can explain the difference between claim, verification, and confidence.
- I can run the shipped GAIA demo.
- I can create a new ledger and record the four main operational units.
- I can verify an offset using three distinct oracle types.
- I can explain why GAIA might still show a violation after verification.
- I can detect and explain a Goodhart drift condition.
- I can save and reload a ledger from disk.

## What To Do Next

After completing this workbook:

1. review [`../../gaia_ui.md`](../../gaia_ui.md) again with your own notes
2. run the GAIA tests
3. complete the facilitator-led review in `GAIA_FACILITATOR_GUIDE.md`
