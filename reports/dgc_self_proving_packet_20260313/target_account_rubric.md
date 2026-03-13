# Target Account Rubric

Date: 2026-03-13
Purpose: keep target selection disciplined and non-delusional

## Core score

Use:

`PartnerScore = 0.30 Pain + 0.20 Urgency + 0.20 CorpusDensity + 0.15 BuyingAuthority + 0.10 ProofLeverage + 0.05 TrustFit`

Each factor is scored `1-5`.

## Definitions

- `Pain`
  - how badly the account suffers from context loss, fragmented execution, or operator thrash
- `Urgency`
  - whether a decision or artifact is needed this month
- `CorpusDensity`
  - whether the account has enough repo/doc/note mass for DGC to outperform a generic chat tool
- `BuyingAuthority`
  - whether the contact can actually approve a paid diagnostic
- `ProofLeverage`
  - whether a successful engagement becomes a strong next case study
- `TrustFit`
  - whether the account can work with a frontier but honest managed system

## Reachability classification

Use one of:

- `self`
- `direct_warm`
- `warm_second_degree`
- `public_signal_cold`
- `inbound`
- `unverified`

Rules:

- only `self`, `direct_warm`, and `warm_second_degree` count toward a warm list
- `public_signal_cold` can count toward an active cold-start pipeline if public evidence and a concrete offer angle exist
- `unverified` does not count toward any active pipeline

## Evidence required for each target row

Every target entry must have:

- account name
- contact name or path to the person who can route it
- reachability status
- source evidence
  - email thread
  - notes file
  - intro source
  - existing collaboration
  - repo or project connection
  - public repo, launch page, hiring page, or engineering post
- trigger event or visible pain signal
- likely delivery channel
- one offer angle
- one next action

If any of those are missing, the row is incomplete.

## Offer selection score

For choosing which offer to lead with:

`OfferPriority = WinProbability x ProofValue x ACV / DeliveryRisk`

Interpretation:

- `Campaign X-Ray` should win when trust is still forming
- `Campaign Sprint` should win when the buyer already trusts the diagnostic
- `Campaign Desk` should follow success, not precede it

## Thresholds

- `4.2-5.0`
  - immediate outreach
- `3.6-4.1`
  - keep in active pipeline
- `3.0-3.5`
  - only pursue if relationship is unusually strong
- `<3.0`
  - ignore for now

Cold-start rule:

- do not send cold unless score is at least `4.0` and the public trigger is specific enough to personalize around

## Early-buyer filters

The first buyers should also satisfy these qualitative filters:

- fast procurement
- obvious pain
- dense corpus
- tolerance for managed delivery
- willingness to let DGC show the brittle parts honestly

## Anti-delusion rules

- No invented customer names.
- No warm labeling without source evidence.
- No scoring generic companies you have no path into and calling them pipeline.
- No placing competitors in the design-partner list just because they are famous.
- No cold outbound without a visible signal that makes the message relevant now.

## Recommended fields for a CSV or sheet

- `account_name`
- `segment`
- `contact_name`
- `reachability_status`
- `source_evidence`
- `trigger_event`
- `delivery_channel`
- `pain`
- `urgency`
- `corpus_density`
- `buying_authority`
- `proof_leverage`
- `trust_fit`
- `partner_score`
- `recommended_offer`
- `offer_angle`
- `next_action`
