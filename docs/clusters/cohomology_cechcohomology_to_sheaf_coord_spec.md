# Cohomology - Cechcohomology - To Sheaf Coordination

## Goal

Ground the repo's generic `CechCohomology` machinery in a reusable
`to_sheaf_coordination` bridge so verification-style pipelines can publish
local assessments and obtain `H^0` global truths or `H^1` productive
disagreements without reimplementing site construction each time.

## Design

- `LocalClaimAssessment` is the portable input shape for one agent's view of a
  shared proposition.
- `build_complete_overlap_site()` creates a fully overlapping `NoosphereSite`
  for one coordination session.
- `to_sheaf_coordination()` converts those assessments into `Discovery`
  sections and runs `CoordinationProtocol`.

## Key Invariant

The discovery `content` must represent only the proposition state, such as
`valid:true` or `valid:false`. Confidence, evidence hashes, and narrative
summaries stay in metadata and evidence fields.

That separation matters because `DiscoverySheaf.compatible()` glues sections
only when both `claim_key` and normalized `content` agree. If confidence is
embedded directly in the discovery text, two agreeing assessors with different
confidence scores cannot glue into `H^0`.

## Expected Behavior

- All assessors agree on the proposition:
  `to_sheaf_coordination()` yields one global truth with averaged confidence.
- At least one assessor disagrees:
  `to_sheaf_coordination()` yields an `H^1` obstruction and marks the session
  as not globally coherent.
- Empty sessions return `None`.

## Integration

`gaia_verification.VerificationOracle.to_sheaf_coordination()` should delegate
to this bridge by translating oracle verdicts into `LocalClaimAssessment`
instances. That keeps GAIA-specific session logic separate from the generic
sheaf/cohomology mapping.
