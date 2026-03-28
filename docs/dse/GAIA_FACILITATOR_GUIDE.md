# GAIA Facilitator Guide

Use this guide to run a structured GAIA onboarding session without drifting into platform mythology or unsupported claims.

## Session Intent

Train users on the auditable GAIA core that exists today:

- categorical ledger
- oracle verification
- ecological fitness and drift detection
- persistence and audit trail

Do not teach speculative surfaces as if they are shipped. In the current tracked repository, GAIA is a Python runtime and demo, not a production web product.

## Recommended Format

Duration: 75 minutes

Agenda:

1. 10 min: orientation
2. 15 min: live demo
3. 20 min: user exercise on a fresh ledger
4. 15 min: verification and drift drill
5. 15 min: review and assessment

## Instructor Setup

Before the session, confirm these commands work:

```bash
python3 scripts/gaia_demo.py
pytest tests/test_gaia.py tests/test_gaia_ledger.py tests/test_gaia_verification.py tests/test_gaia_fitness.py
```

Have these files open during the session:

- `gaia_ui.md`
- `docs/dse/GAIA_TRAINING_WORKBOOK.md`
- `dharma_swarm/gaia_ledger.py`
- `dharma_swarm/gaia_verification.py`
- `dharma_swarm/gaia_fitness.py`

## Core Teaching Points

### 1. Claims are not truth

GAIA distinguishes:

- recorded claim
- verified claim
- confidence-weighted verified impact

If the trainee collapses these three into one number, correct that immediately.

### 2. Disagreement is first-class

A dissenting oracle is not a bug. It is part of the epistemic surface. The point of GAIA is not unanimous storytelling. The point is auditable ecological truth under uncertainty.

### 3. Conservation violations are useful

Users may assume a violation means the system is broken. Teach the opposite:

- violations are evidence that the system is refusing to overclaim
- a healthy GAIA session can show a temporary violation while evidence accumulates

### 4. Drift detection is governance, not polish

Goodhart drift detection exists to prevent the platform from optimizing for offset volume or PR optics instead of verified ecological outcomes.

## Live Demo Script

Run:

```bash
python3 scripts/gaia_demo.py
```

Pause at these moments:

### After Step 3

Ask:

- Why is the offset still unverified?
- Why does the conservation check fail here?

Expected answer:

- the claim has been registered, but there are not yet enough oracle attestations
- GAIA is correctly refusing to treat an unverified claim as settled impact

### After Step 5

Ask:

- Why does one dissenting oracle remain visible?
- What does the 3-of-5 threshold buy us?

Expected answer:

- disagreement remains part of the record
- the threshold reduces single-channel fraud and brittle dependence on one verification source

### After Step 7

Ask:

- What would have to happen for drift to become `True`?

Expected answer:

- claims would need to accumulate faster than verification, dropping the verified-to-claimed ratio below the drift threshold

## Exercise Review Key

Use these expected outcomes for the workbook exercises.

### Workbook Module 3

Expected pre-verification state:

- one offset claim exists
- verified offset is still zero
- at least one conservation issue is likely present

### Workbook Module 4

Expected post-verification state:

- the offset is eligible to become verified
- verification units appear in the ledger
- verified impact remains confidence-weighted rather than absolute

### Workbook Module 5

Expected drift state:

- `is_drifting` is `True`
- diagnosis contains `GOODHART DRIFT DETECTED`

## Assessment Rubric

Mark each learner as `ready`, `needs support`, or `not yet`.

- `ready`: can run the demo, explain the claim/verification distinction, and interpret drift and conservation outputs correctly
- `needs support`: can run commands but confuses verified impact with raw claims or treats disagreement as failure
- `not yet`: cannot complete the workflow without step-by-step intervention or repeatedly overstates what the current platform ships

## Common Failure Modes

### Overclaiming the platform

Problem:

- trainee talks about a web dashboard, live project matching, or external integrations as if they already ship

Correction:

- bring them back to the current tracked runtime: ledger, verification, fitness, demo, tests

### Ignoring confidence weighting

Problem:

- trainee assumes `verified` means 100% certainty

Correction:

- show that GAIA multiplies verified offsets by confidence when calculating the verified total

### Treating violations as defects

Problem:

- trainee thinks the system should always show zero violations

Correction:

- explain that temporary violations are sometimes the right answer when evidence is incomplete

### Treating dissent as noise

Problem:

- trainee wants to hide or drop the dissenting oracle

Correction:

- explain that preserved disagreement is part of the anti-greenwashing design

## Completion Standard

The training is complete when a learner can do all of the following without guessing:

1. run the demo
2. create a new ledger
3. record compute, funding, labor, and offset data
4. verify an offset with three distinct oracle types
5. interpret `summary()`
6. interpret `detect_goodhart_drift()`
7. save and reload the ledger

## Follow-On Practice

If you want a second session, use one of these drills:

- add a dissenting oracle and explain the coordination result
- create a deliberately invalid claim and inspect the violation surface
- compare an unverified ledger to a verified ledger using the weighted fitness score
