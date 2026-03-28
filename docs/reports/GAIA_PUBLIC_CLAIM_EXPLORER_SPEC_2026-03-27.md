# GAIA Public Claim Explorer Spec

Date: 2026-03-27
Status: validator draft
Scope: integrity-card, challenge-path, consent, and remediation workflow for public ecological claims in GAIA-ECO

## Purpose

Define the smallest credible public-claim surface that can sit on top of the current GAIA trust kernel without overclaiming what the repository already ships.

This spec is grounded in the current append-only GAIA ledger, the shipped 3-of-5 oracle verification flow, and prior governance artifacts. It is a design for the next build slice, not a claim that a production public explorer already exists.

## Hard Boundary

The explorer may publish:

- what claim is being made
- what evidence and audit path support it
- what disagreement, challenge, or reversal remains open

The explorer may not imply:

- that Aptavani itself is an ecological methodology
- that an unverified proxy is verified impact
- that consent is satisfied because an operator says it is
- that unresolved grievances are compatible with `high_integrity`

## Current Trust Anchors

The spec assumes and reuses these existing surfaces:

- [`dharma_swarm/gaia_ledger.py`](../../dharma_swarm/gaia_ledger.py): append-only audit log and conservation-law checks
- [`dharma_swarm/gaia_verification.py`](../../dharma_swarm/gaia_verification.py): 3-of-5 oracle verification across `satellite`, `iot_sensor`, `human_auditor`, `community`, and `statistical_model`
- [`dharma_swarm/gaia_fitness.py`](../../dharma_swarm/gaia_fitness.py): anti-greenwashing drift detection and ecological gate language
- [`dharma_swarm/claim_graph.py`](../../dharma_swarm/claim_graph.py): typed claim-to-evidence and contradiction substrate
- [`dharma_swarm/contradiction_registry.py`](../../dharma_swarm/contradiction_registry.py): explicit disagreement registry
- [`dharma_swarm/citation_index.py`](../../dharma_swarm/citation_index.py): typed source relationships

## Public Claim Invariant

No public ecological claim without:

- a claim statement with bounded scope
- a methodology reference
- a visible integrity class
- an evidence path
- an audit status
- a challenge path
- explicit consent status whenever communities, land access, local knowledge, or livelihood claims are implicated

If any item is missing, the surface may store the claim internally but may not publish it as a public integrity card.

## Integrity Card

### Required fields

| Field | Requirement | Why it exists |
| --- | --- | --- |
| `claim_id` | stable immutable identifier | allows challenge, citation, and reversal linkage |
| `project_id` | linked initiative or site | prevents orphan claims |
| `claim_statement` | one bounded sentence, no universal language | constrains marketing drift |
| `claim_type` | `activity`, `output`, `outcome`, `livelihood`, or `mixed` | determines evidence rules |
| `claim_scope` | geography, time window, and population or ecosystem scope | prevents false generalization |
| `integrity_class` | `experimental`, `emerging`, or `high_integrity` | public quality signal |
| `methodology_ref` | source or methodology identifier | makes the claim reproducible |
| `evidence_path` | list of evidence bundles with hashes and source types | auditability |
| `audit_status` | `pending`, `passed`, `qualified`, `failed`, or `challenged` | exposes review state |
| `challenge_status` | visible current challenge state | keeps disputes public |
| `consent_status` | `not_applicable`, `pending`, `documented`, `verified`, `disputed`, `withdrawn`, or `expired` | blocks soft claims of legitimacy |
| `grievance_status` | `none`, `open`, `material`, or `resolved` | unresolved harm must stay visible |
| `oracle_summary` | distinct oracle types and their verdict counts | ties to the current GAIA kernel |
| `reversal_status` | `none`, `watch`, `partial_reversal`, or `full_reversal` | prevents silent overwrite |
| `last_reviewed_at` | most recent governance review timestamp | freshness |
| `public_notes` | plain-language limitations and uncertainties | preserves dissent and caveats |

### Evidence lane badges

Every evidence item on the card should carry a Pramana-style lane badge:

| Badge | Meaning | Public use rule |
| --- | --- | --- |
| `[G]` | direct mechanistic or measurement evidence | may support quantified ecological outcome claims |
| `[B]` | observed field or human behavior evidence | may support operational and stewardship claims |
| `[P]` | proxy or heuristic signal | must never be displayed as verified impact |
| `[I]` | inference derived from other claims | must be labeled as interpretation |
| `[S]` | speculative or hypothesis content | must not appear as settled public outcome |

The card should summarize lane composition. A `high_integrity` ecological outcome claim cannot be supported only by `[P]`, `[I]`, or `[S]` evidence.

### Integrity classes

| Class | Minimum requirements | Public wording constraints |
| --- | --- | --- |
| `experimental` | methodology present; at least one evidence bundle; at least one audit record exists; challenge path open | may describe pilot activity or early signals, not verified impact |
| `emerging` | methodology present; at least two independent evidence bundles; at least one non-operator review or audit; no unresolved material challenge banner suppressed | may describe measured trends with uncertainty, not settled durable impact |
| `high_integrity` | methodology present; evidence path complete; audit `passed` or transparently `qualified`; no unresolved material challenge; no `material` grievance; consent `verified` when applicable; quantified ecological outcome claims satisfy current 3-of-5 oracle threshold | may describe verified impact only within the bounded scope on the card |

### Publication rules

1. A quantified ecological outcome claim cannot be `high_integrity` unless it satisfies the existing GAIA 3-of-5 oracle threshold.
2. A proxy-only claim can be `experimental` or `emerging`, never `high_integrity`.
3. Any open consent dispute or material grievance blocks `high_integrity`.
4. Any material challenge forces a visible banner and suspends promotional wording until resolved.
5. A reversal never deletes the prior card. It appends a new state and links backward.

### Card example

```json
{
  "claim_id": "claim_peatland_rewetting_2026_q2",
  "project_id": "site_tokachi_peat_01",
  "claim_statement": "Rewetting work restored hydrology across 42 hectares between April and June 2026.",
  "claim_type": "outcome",
  "integrity_class": "emerging",
  "audit_status": "qualified",
  "challenge_status": "open_review",
  "consent_status": "verified",
  "grievance_status": "none",
  "oracle_summary": {
    "agreeing": ["satellite", "community"],
    "dissenting": ["statistical_model"]
  },
  "public_notes": [
    "Hydrology evidence is stronger than biodiversity evidence in this review window.",
    "No durable carbon claim is published at this integrity class."
  ]
}
```

## Challenge Path

### Who may challenge

Standing should be broad. A challenge may be submitted by:

- local or Indigenous community members
- project workers or stewards
- auditors, researchers, or partner NGOs
- funders or buyers
- public observers with evidence of factual error, methodological weakness, or misrepresentation

Anonymous submission should be allowed for intake, but anonymous challenges should not automatically change a public card without corroborating evidence.

### Valid challenge grounds

- factual error
- misleading scope or wording
- missing or broken evidence path
- audit conflict of interest
- consent dispute
- open grievance or implementation harm
- conservation-law violation
- ecological reversal or underdelivery
- fabricated, altered, or unverifiable evidence

### Workflow states

| State | Meaning | Public visibility | Exit condition |
| --- | --- | --- | --- |
| `submitted` | intake created | visible count, reporter may be private | intake triage starts |
| `acknowledged` | challenge received and non-spam | visible on card | owner assigned |
| `needs_evidence` | challenge plausible but incomplete | visible with deadline | evidence supplied or expired |
| `open_review` | active review by challenge desk or council | visible banner | findings issued |
| `material_challenge` | evidence suggests claim may be unsafe or misleading | visible red banner; promotional use frozen | remediation plan approved |
| `dismissed` | challenge rejected with reason | visible with rationale | appeal window closes |
| `upheld` | challenge accepted | visible with findings | remediation or withdrawal begins |
| `resolved` | remediation finished and reviewed | visible with link to outcome | monitoring or closure complete |
| `appeal_open` | formal second review underway | visible | appeal decided |

### Default service levels

- acknowledge within 5 business days
- publish triage state within 10 business days
- reach initial finding within 30 calendar days unless the card explicitly states why more time is needed

The goal is credibility, not speed theater. If evidence is incomplete, the public state should say so rather than silently stall.

### Automatic suspension triggers

The explorer should immediately freeze promotional use and force either downgrade or `material_challenge` when any of the following occur:

- plausible evidence fabrication or tampering
- consent status becomes `disputed` or `withdrawn`
- grievance status becomes `material`
- an audit fails
- a conservation-law violation materially affects the claim
- a reversal changes the claim’s quantified outcome beyond the card’s disclosed uncertainty bounds

## Consent Workflow

### When consent is mandatory

Consent workflow is mandatory whenever a claim touches:

- land access or land-use intervention
- Indigenous or local communities
- local or traditional ecological knowledge
- livelihood, employment, or benefit-sharing claims
- community-sourced testimony presented as evidence

### Consent statuses

| Status | Meaning | Public effect |
| --- | --- | --- |
| `not_applicable` | no community-facing or land-rights surface identified | card may proceed if justified |
| `pending` | review not complete | blocks `high_integrity` |
| `documented` | operator has provided records | still not enough for `high_integrity` on sensitive claims |
| `verified` | records checked by community or independent reviewer | eligible for `high_integrity` if other gates pass |
| `disputed` | standing disagreement about legitimacy or scope | forces `material_challenge` |
| `withdrawn` | prior consent revoked | freezes public claim |
| `expired` | consent no longer valid for current scope or time window | blocks continued publication until refreshed |

### Required consent artifacts

At minimum, the system should store:

- decision-making body or representatives
- date, place, and language of the consent process
- scope of what was approved
- benefit-sharing or stewardship terms
- grievance route
- evidence bundle hash for minutes, recordings, or signed records
- privacy tier for sensitive attachments

For sensitive communities, the public card may display a redacted summary while the evidence path stores hashed protected records.

### Consent invariants

1. `unknown` is not a valid public consent status. The status must be explicit.
2. Operator-attested consent alone is insufficient for `high_integrity`.
3. Consent to intervention is not the same as consent to public storytelling or data publication.
4. An unresolved grievance blocks `high_integrity` even if a consent document exists.
5. Consent withdrawal does not erase history. It creates a new public state and freezes the affected claim.

## Remediation Workflow

### Remediation outcomes

Every upheld or material challenge must end in one or more explicit outcomes:

- `clarification`
- `numerical_correction`
- `methodology_correction`
- `integrity_downgrade`
- `claim_freeze`
- `claim_withdrawal`
- `claim_reissue`

### Workflow

| Step | Requirement |
| --- | --- |
| `case_opened` | remediation case linked to challenge and claim |
| `owner_assigned` | accountable operator or governance body named |
| `containment` | public wording frozen if the claim is materially unsafe |
| `repair_plan` | what will change, by when, and what evidence will prove repair |
| `verification` | new evidence, audit, or consent review executed |
| `decision` | council or challenge desk records pass, downgrade, withdraw, or reissue |
| `historical_append` | prior claim state remains visible and linked |

### Reinstatement rule

A downgraded or frozen ecological outcome claim may return to `high_integrity` only if:

- the original challenge is resolved
- required evidence is replaced or corrected
- consent and grievance status are again eligible
- a fresh review confirms the integrity class
- quantified outcome claims again satisfy the current 3-of-5 oracle threshold

## Unsupported Claim Patterns

The explorer should reject publication of claims that do any of the following:

- treat `[P]` proxy metrics as verified ecological outcomes
- claim durable restoration impact before any durable monitoring window exists
- infer biodiversity recovery from carbon signals alone
- claim community benefit from participant counts alone
- describe an initiative as community-consented when consent is only operator-attested
- use Aptavani or dharmic language as evidence that a project works
- generalize from one site or time window to all sites, all ecosystems, or all communities
- hide a reversal, dissenting oracle, or failed audit behind a refreshed summary card

## Blockers And Human Review Questions

1. Consent and grievance handling will require jurisdiction-specific legal review. This spec only defines platform state, not legal sufficiency.
2. The repository has no current typed model for consent, grievance, public challenge, or remediation records. Implementation requires new schemas rather than pure UI work.
3. Materiality thresholds for ecological reversal are methodology-dependent. Human councils need to set them before automation can freeze claims consistently.
4. The system still needs a decision on who can issue the final `high_integrity` designation: operator, audit desk, MRV council, or a multi-body quorum.
5. Anonymous challenge protection and public transparency pull in opposite directions. A redaction policy is required before launch.

## Recommended Implementation Boundary

Build next:

- typed models for `PublicClaimCard`, `ChallengeRecord`, `ConsentRecord`, and `RemediationCase`
- append-only event logging for status transitions
- integrity-class evaluator that reuses existing GAIA verification outcomes
- public serializer that emits redacted and full audit views

Do not build yet:

- irreversible auto-publishing
- automated legal sufficiency judgments
- automated dismissal of consent disputes
- marketing-friendly aggregate badges divorced from claim-level evidence

## Source Trail

- [`docs/reports/GAIA_ECO_CONCEPTUAL_FRAMEWORK_2026-03-27.md`](./GAIA_ECO_CONCEPTUAL_FRAMEWORK_2026-03-27.md)
- [`docs/reports/GAIA_ECO_ARCHITECTURE_2026-03-27.yaml`](./GAIA_ECO_ARCHITECTURE_2026-03-27.yaml)
- [`docs/reports/PLANETARY_RECIPROCITY_COMMONS_GOVERNANCE_CHARTER_2026-03-11.md`](./PLANETARY_RECIPROCITY_COMMONS_GOVERNANCE_CHARTER_2026-03-11.md)
- [`docs/reports/AI_RECIPROCITY_LEDGER_V0_SCHEMA_2026-03-11.yaml`](./AI_RECIPROCITY_LEDGER_V0_SCHEMA_2026-03-11.yaml)
