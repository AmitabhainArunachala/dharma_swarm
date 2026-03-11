# Jagat Kalyan Spinout Plan

Date: 2026-03-11
Status: boundary plan
Decision: incubate inside DGC natively now, split into a dedicated repo once the
initiative becomes externally real

## Canonical Decision

Yes, this should eventually become a separate repo.

But not yet as a total extraction.

The right shape is:

- `DGC / dharma_swarm`
  - remains the cognition and orchestration layer
  - keeps idea generation, partner scanning, workflow decomposition, and thin
    service integrations

- `Planetary Reciprocity Commons`
  - becomes the dedicated domain repo
  - owns the ledger, governance, reporting, pilots, public docs, and external
    APIs

## Native Layer That Should Stay In DGC

Keep these concerns in DGC even after the split:

- Jagat Kalyan skill definitions
- `thinkodynamic_director` mission/archetype selection
- swarm-level research, synthesis, and delegation
- thin external integration client
- future workflow templates that call into the reciprocity system

This is the "native level" you want.

DGC should be able to think with and act through the reciprocity system without
owning the whole domain model forever.

## Domain Layer That Wants To Leave

These want to become their own repo when the project gains a separate roadmap
or collaborators:

- `dharma_swarm/ai_reciprocity_ledger.py`
- `dharma_swarm/gaia_ledger.py`
- `dharma_swarm/gaia_verification.py`
- `dharma_swarm/gaia_fitness.py`
- Jagat Kalyan / reciprocity docs, public brief, concept note, governance
  charter, schema
- future API, dashboard, registry adapters, and MRV-specific code

## Practical Trigger To Spin Out

Create the new repo when any two of these become true:

1. external collaborators need focused issues and PRs
2. the project needs its own README and roadmap
3. the ledger/API grows faster than DGC core
4. public-facing branding starts to matter
5. compliance, governance, or MRV work becomes substantial

## Proposed Boundary

### Stay In DGC

- `dharma_swarm/integrations/reciprocity_commons.py`
- Jagat Kalyan skills
- director task archetypes and orchestration logic
- thin adapters or export clients

### Move To New Repo

- reciprocity ledger implementation
- GAIA implementation
- verification engine
- governance package
- public docs and schemas
- service API and storage

### Duplicate Temporarily If Helpful

- pydantic contracts
- YAML/JSON schemas
- sample payloads

## Target Repo

Recommended repo name:

- `planetary-reciprocity-commons`

Internal codename can remain:

- `jagat-kalyan-protocol`

Execution engine / sub-brand:

- `gaia`

## Immediate Preparation Done Here

This repo now contains:

- a thin integration seam in `dharma_swarm/integrations/reciprocity_commons.py`
- a spinout manifest
- a seed repo directory under `spinouts/planetary_reciprocity_commons_seed/`

That gives you a clean next move without forcing a split tonight.

## Migration Sequence

1. keep incubating design and orchestration in DGC
2. prove one small pilot architecture and one service contract
3. create the new repo from the seed directory
4. move domain modules and docs there
5. leave DGC talking to it through the integration client

## One-Line Rule

DGC should remain the mind.
Planetary Reciprocity Commons should become the body.
