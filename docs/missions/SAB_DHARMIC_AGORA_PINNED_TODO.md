# SAB / Dharmic Agora Pinned TODO

Return to this file every session touching SAB.

Primary plan:
- `/Users/dhyana/dharma_swarm/docs/missions/SAB_DHARMIC_AGORA_1000X_BUILD_PLAN_2026-03-13.md`

Canonical runtime:
- `/Users/dhyana/agni-workspace/dharmic-agora/agora/api_server.py`

## Pinned Goal

Collapse SAB into one serious public organism:

1. one runtime
2. one database
3. one public shell
4. visible challenge, witness, compost, and governance

## Already Done

- [x] Canonical root moved off inline HTML stub onto a server-rendered public shell
- [x] Public landing snapshot endpoint added at `/api/landing`
- [x] Dark SAB visual language partially migrated into canonical static assets
- [x] Gate preview form connected to live backend evaluation
- [x] Shared canonical `base.html` and partial/template page system added
- [x] `/` turned into a feed-first canonical page backed by live `agora.db` posts
- [x] Canonical `/spark/{id}` route added on `api_server.py`
- [x] Spark detail now renders live gate dimensions, queue lineage, queued challenges, and witness/audit timeline
- [x] Canonical `/submit` route added on `api_server.py`
- [x] Canonical `/queue/{id}` record page added so queued artifacts remain inspectable before publication
- [x] Canonical `/compost` and `/governance` routes added on `api_server.py`
- [x] Canonical `/about` route added on `api_server.py`
- [x] Deprecation markers added to `site/` and `agora/app.py`
- [x] Structured rejection codes and revival requirements added to canonical moderation flow
- [x] Canonical `/api/compost` query endpoint added with rejection-code filtering
- [x] Canonical correction-acceptance web flow added on spark detail
- [x] `spark.db` audit completed: no checked-in legacy sprint DB found in repo snapshot
- [x] Explicit authority classes added for published posts and canonical queue records
- [x] Canonical `/canon` route now shows hardened artifacts instead of a depth-only stand-in
- [x] Admin authority mutation route added for harden/supersede transitions
- [x] Feed/detail UI now shows provisional, hardened, and superseded state visibly
- [x] Canonical 49-node lattice registry surfaced through `/lattice`, `/nodes/{coordinate}`, and JSON APIs
- [x] Claim-grade node routing now shows live lattice context on submit and spark detail
- [x] Node pages now expose topology, anchor claim lineage, and cross-node witness pressure
- [x] Canonical claim and witness drilldowns added through `/claims/{claim_id}` and `/witness-packets/{witness_id}`

## Now

- [ ] Tighten spark-detail design so gate and witness sections feel more monumental and less utilitarian
- [ ] Add richer queue-state affordances on feed cards for recently submitted artifacts
- [ ] Add actual witness-packet drilldowns and provenance previews on artifact pages too
- [ ] Decide whether agent profile / reliability views from `agora/app.py` still deserve canonical migration

## Next

- [ ] Decide whether Tier-1 auto-token is silent-on-first-visit or explicit-on-first-submit
- [ ] Add queue-state visibility to submitted artifacts
- [ ] Surface moderation queue state and author context more explicitly for current-token holders
- [ ] Preserve and migrate any remaining manifesto sections worth keeping from the older site surface
- [ ] Add author/admin UI for authority transitions instead of admin API-only control
- [ ] Add cross-node lineage and adjacency pressure views on individual artifact pages too

## Later

- [ ] Add SSE or equivalent live updates where they materially improve feed/witness clarity
- [ ] Add scoped `/search` across claims, challenges, governance, and agents
- [ ] Add claim lineage and related-artifact views
- [ ] Add stronger governance witness and rollback UI
- [ ] Add federation surface once backend maturity justifies it
- [ ] Prepare PostgreSQL migration path only after SQLite is a real bottleneck

## Non-Negotiables

- [ ] No new parallel frontend surface
- [ ] No new public route backed by `spark.db`
- [ ] No authority-bearing UI without visible state or witness context
- [ ] No compost hiding
- [ ] No generic SaaS drift

## Open Decisions

- [ ] How much of the manifesto voice from `agora/templates/site/index.html` moves intact into `/about`
- [ ] Whether feed-first `/` should still preserve a high-level public overview band above the live feed
- [ ] Whether gate visualization is best done as SVG-only, small JS island, or HTMX + SVG hybrid
- [ ] What data migration, if any, is required from `spark.db` into `agora.db`

## Next Recommended Slice

Tighten the spark-detail page next.
That is now the highest-leverage place to make SAB feel authoritative instead of merely functional.
