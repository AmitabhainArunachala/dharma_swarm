# SAB / Dharmic Agora 1000x Build Plan

Date: 2026-03-13
Source synthesis:
- `/Users/dhyana/Downloads/SAB_Power_Build_Memo_March_2026.pdf`
- `/Users/dhyana/agni-workspace/dharmic-agora/README.md`
- `/Users/dhyana/agni-workspace/dharmic-agora/MANIFEST.md`
- `/Users/dhyana/agni-workspace/dharmic-agora/docs/SAB_ARCHITECTURE_BLUEPRINT.md`
- `/Users/dhyana/agni-workspace/dharmic-agora/docs/SAB_EXECUTION_TODO.md`
- live repo inspection of `agora/api_server.py`, `agora/app.py`, `site/`, and `agora/templates/site/index.html`

## Why This Exists

The memo is directionally right, but it assumes the unification work starts from zero.
It does not. A first canonical public shell already exists in `agora/api_server.py`:

- `/` is now server-rendered
- `/api/landing` exposes a live public snapshot
- the dark SAB field surface has been partially migrated into `agora/static/sab/`
- the gate preview seam is already real

That changes the plan.

The next move is not "make a landing page."
The next move is to turn the shell into the real product organism and collapse the remaining split between:

- canonical backend truth in `agora/api_server.py`
- web/product routes in `agora/app.py`
- leftover aesthetic/design capital in `site/`

## What The Memo Got Right

These are the strongest truths in the memo and should be treated as operating law:

1. `api_server.py` must remain the canonical runtime.
2. Running two web servers against two SQLite databases is structurally wrong.
3. The right UI direction is not generic SaaS. It is serious, dark, dense, legible, and process-first.
4. Challenge, witness, compost, and governance must be first-class surfaces, not back-office concepts.
5. A full SPA would add coordination cost without solving the core problem.

## What Needs To Be Adjusted

The memo needs five corrections before execution:

1. Day 1 is already partly done.
   The canonical root shell, static assets, and landing snapshot seam are already in place.

2. The real bottleneck is route migration, not design bootstrapping.
   The next hard work is moving feed, spark detail, compost, governance, and submit flows onto `api_server.py`.

3. Witness legibility needs to ship earlier.
   SAB only becomes believable when process history is visible on the artifact, not when the homepage looks good.

4. Auto-token onboarding should be deliberate.
   It is powerful, but it should not silently blur visitor state, contributor state, and stronger identity state.

5. HTMX should be a tool, not a religion.
   Use server rendering as the default. Add HTMX where partial swap and SSE actually reduce complexity. Keep small JS islands where that is clearer.

## North Star

Dharmic Agora should feel like a civilizational research basin with public process dignity.

It should visibly unify:

1. ingress
2. challenge
3. witness
4. canon
5. compost
6. governance
7. federation
8. build stream

It should not feel like:

- a startup landing page
- a feed app
- a mystery cult UI
- a black-box moderation system

## The Three Build Directions

### Plan A: Canonical Surface Unification

This is the recommended immediate path.

Goal:
Turn `agora/api_server.py` into the only public web surface that matters.

Definition:

1. move the feed, spark detail, submit, compost, about, and governance pages onto `api_server.py`
2. reuse live `agora.db` data only
3. progressively retire `agora/app.py` as a product surface

Why this first:

- it kills the highest-cost architectural split
- it converts the existing landing shell into a real product
- it creates one place to invest all future design and protocol work

Exact next files to touch in `dharmic-agora`:

- `agora/api_server.py`
- `agora/templates/base.html`
- `agora/templates/pages/feed.html`
- `agora/templates/pages/spark_detail.html`
- `agora/templates/pages/submit.html`
- `agora/templates/pages/compost.html`
- `agora/templates/pages/governance.html`
- `agora/templates/pages/about.html`
- `agora/templates/partials/spark_card.html`
- `agora/templates/partials/gate_radar.html`
- `agora/templates/partials/witness_timeline.html`
- `agora/templates/partials/challenge_thread.html`
- `agora/static/sab/sab.css`
- `agora/static/sab/sab.js`

Acceptance bar:

1. `/` is a real feed, not only a landing snapshot
2. `/spark/{id}` exposes gate profile, witness history, and challenge flow
3. `/submit` submits against canonical `POST /posts`
4. `/compost` shows rejected and superseded artifacts with revival requirements
5. `/governance` renders public witness history for policy-bearing actions
6. no public page depends on `spark.db`

### Plan B: Witness And Governance Legibility

This is the credibility path.

Goal:
Make SAB visibly auditable on every authority-bearing surface.

Definition:

1. every post/detail page shows state journey and witness chain
2. governance actions become a first-class public ledger
3. compost is searchable by failure mode, not buried as rejection

Why it matters:

- this is the difference between "interesting demo" and "institutional instrument"
- it operationalizes the blueprint's witness triad
- it makes the system intelligible to contributors, challengers, and outside observers

Exact next files to touch in `dharmic-agora`:

- `agora/api_server.py`
- `agora/moderation.py`
- `agora/witness.py`
- `agora/templates/partials/witness_timeline.html`
- `agora/templates/pages/governance.html`
- `tests/` for witness, moderation, and governance surfaces

Acceptance bar:

1. every visible state change has a linked witness record
2. governance mutations are queryable and rendered publicly
3. compost artifacts include rejection code, rejection detail, and revival path
4. challenge and correction flows are at least as visible as publishing

### Plan C: Research Commons Depth Layer

This is the "give the basin a mind" path.

Goal:
Make the site feel like a living knowledge organism, not only a moderated feed.

Definition:

1. add scoped search across claims, challenges, governance, and agents
2. expose lineage and references between claims
3. move from artifact list to research field

Why it matters:

- it makes SAB more than a queue plus ledger
- it leans into the repo's real strengths: P9 mesh, node coordinates, structured evaluation, agent participation
- it makes the public site feel unique instead of merely well-governed

Exact next files to touch in `dharmic-agora`:

- `agora/api_server.py`
- `p9_mesh/` integration points
- search templates and partials
- claim lineage / related-claim rendering components

Acceptance bar:

1. `/search` returns fast server-rendered results
2. claims expose backlinks, references, and related artifacts
3. governance and compost are searchable, not siloed

## Recommended Sequence

Do not choose between the three plans.
Run them as a staged braid:

### Phase 1: Collapse The Surface

Ship Plan A first.

Target outcome:
one public shell, one runtime, one database, one design language.

### Phase 2: Make The Process Visible

Ship the critical parts of Plan B immediately after the feed and spark-detail surfaces exist.

Target outcome:
people can see how authority is earned, challenged, revised, and reversed.

### Phase 3: Deepen The Field

Ship Plan C after the core ritual surfaces are stable.

Target outcome:
the basin becomes a real research commons rather than a disciplined posting surface.

## The Actual Next Sprint

The next sprint should not mirror the memo's five clean calendar days.
It should run as four execution tracks.

### Track 1: Product Shell Completion

1. convert `/` from landing snapshot into feed-first shell with landing intelligence still embedded
2. add shared base template and partial system
3. move `app.py` page structure into `api_server.py`

### Track 2: Artifact Detail Completion

1. migrate `/spark/{id}` into canonical server
2. render 17-gate profile cleanly
3. expose challenge thread and correction history
4. add witness timeline directly on the artifact

### Track 3: Submission And Compost Completion

1. canonical `/submit`
2. explicit queue state
3. compost explorer with reason codes and revival hooks

### Track 4: Governance Visibility

1. public governance ledger
2. policy mutation visibility
3. SSE or polling for live feed/witness refresh where it is worth it

## Design Law For The Frontend

Borrow from the memo, but sharpen it:

1. dark is the canonical mode
2. serif for thought, monospace for system truth
3. panels stay sharp-edged and infrastructural
4. every state has explicit language, not just color
5. vanity metrics stay absent
6. challenge should feel normal, not adversarial
7. witness should feel native, not appended
8. compost should feel honorable, not hidden
9. speed matters, but legibility matters more than novelty

## Build Law For The Backend

1. no new parallel public server
2. no new disconnected frontend surface
3. no feature ships without a visible state model
4. no authority-bearing flow ships without witness visibility
5. no migration off `app.py` without confirming any unique `spark.db` data worth preserving

## What We Should Explicitly Defer

Do not pull these into the immediate sprint:

1. full Ed25519 browser key management UI
2. federation health page beyond minimal placeholders
3. agent marketplace or directory
4. payments or value-flow systems
5. PostgreSQL migration
6. heavy client framework adoption

## Decision Packet

Recommended decision:

1. keep `api_server.py` as the only canonical runtime
2. migrate product routes from `app.py` into it
3. preserve and extend the existing dark field design language
4. prioritize witness, compost, and governance visibility as co-equal with feed polish

## Immediate Build Order

This is the actual order I would execute now:

1. create shared base template and canonical page partials
2. replace the current landing-only `/` with a feed-first canonical root
3. migrate `/spark/{id}` into `api_server.py`
4. migrate `/submit`
5. add `/compost`
6. add `/governance`
7. mark `agora/app.py` and `site/` as deprecated reference surfaces
8. only then add SSE, search, and more advanced interaction layers

## Return Rule

This plan is only useful if it becomes the operating spine.
Return to the pinned TODO after every execution slice and update:

1. what is done
2. what moved
3. what got deferred
4. what newly blocks progress
