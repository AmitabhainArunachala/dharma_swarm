# Planetary Reciprocity Commons Seed

This directory is the prepared seed for a future `planetary-reciprocity-commons`
repository.

It exists so the reciprocity / GAIA domain can evolve out of DGC without losing
the native orchestration connection.

## Intended Split

- `dharma_swarm` remains the cognition and orchestration layer
- `planetary-reciprocity-commons` becomes the domain repo for:
  - AI Reciprocity Ledger
  - GAIA verification and reporting
  - governance and public docs
  - APIs, pilots, and dashboards

## What Should Move Here First

- `dharma_swarm/ai_reciprocity_ledger.py`
- `dharma_swarm/gaia_ledger.py`
- `dharma_swarm/gaia_verification.py`
- `dharma_swarm/gaia_fitness.py`
- related tests and docs listed in
  `docs/reports/JAGAT_KALYAN_EXPORT_MANIFEST_2026-03-11.yaml`

## What Should Stay In DGC

- `thinkodynamic_director` orchestration
- Jagat Kalyan skills
- DGC integration client
- swarm workflows that call into this future service

## Native Link Back To DGC

The stable seam is:

- `dharma_swarm/integrations/reciprocity_commons.py`

That client is the contract DGC should keep even after the rest moves out.

## First Goal For The New Repo

Stand up a minimal service exposing:

- `POST /activities`
- `POST /obligations`
- `POST /projects`
- `POST /outcomes`
- `GET /ledger/summary`
- `GET /health`

## Repo Naming

- public repo: `planetary-reciprocity-commons`
- internal codename: `jagat-kalyan-protocol`
- execution engine: `gaia`
