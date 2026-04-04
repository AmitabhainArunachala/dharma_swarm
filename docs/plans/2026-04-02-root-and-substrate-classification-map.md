---
title: Root And Substrate Classification Map
path: docs/plans/2026-04-02-root-and-substrate-classification-map.md
slug: root-and-substrate-classification-map
doc_type: plan
status: active
summary: Classifies root-level prose and substrate directories into true entrypoints, active doctrine, and conceptual substrate so the next cleanup passes can reduce confusion without damaging the repo's guidance layer.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
    - README.md
    - CLAUDE.md
    - PRODUCT_SURFACE.md
    - foundations/INDEX.md
    - mode_pack/README.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
  - knowledge_management
  - software_architecture
  - operations
  - repository_hygiene
inspiration:
  - repo_hygiene
  - canonical_truth
  - research_synthesis
connected_relevant_files:
  - README.md
  - CLAUDE.md
  - PRODUCT_SURFACE.md
  - docs/architecture/GENOME_WIRING.md
  - LIVING_LAYERS.md
  - program.md
  - program_ecosystem.md
  - docs/architecture/SWARMLENS_MASTER_SPEC.md
  - mode_pack/README.md
  - foundations/INDEX.md
  - docs/plans/2026-04-02-root-operational-notes-policy.md
  - docs/plans/2026-04-02-root-next-tranche-plan.md
improvement:
  room_for_improvement:
    - Turn the root-level classifications into one actual move tranche after the specs seam lands.
    - Add missing readme/index anchors for substrate directories that still rely on implicit meaning.
    - Decide whether active doctrine files at root should stay or move into docs/architecture.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-02-root-and-substrate-classification-map.md
  retrieval_terms:
    - root
    - substrate
    - classification
    - canon
    - foundations
    - lodestones
    - mode_pack
  evergreen_potential: medium
stigmergy:
  meaning: This file separates root-level entrypoints from doctrine residue and conceptual substrate so the cleanup path can stay orderly.
  state: active
  semantic_weight: 0.85
  coordination_comment: Use this file to decide which root files are legitimate entrypoints and which belong in docs or substrate layers.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-02T23:59:00+09:00'
  curated_by_model: Codex (GPT-5)
  schema_version: pkm-phd-stigmergy-v1
---
# Root And Substrate Classification Map

## Main Finding

The remaining root-level prose is not random. It falls into three different classes:

1. true repo entrypoints
2. active doctrine that may or may not deserve root-level visibility
3. conceptual substrate that should be understood as a separate layer, not as product canon

The substrate directories are also not noise. They are a distinct knowledge layer.

## Root-Level Prose Classification

### Keep At Root

These function as real repo entrypoints or local runtime controls:

- `README.md`
- `CLAUDE.md`
- `pyproject.toml`
- `Makefile`
- `Dockerfile`
- `docker-compose.yml`
- `.env.template`

Reason:

- these files are expected at the repo root
- they act as operator, tooling, or build entry surfaces

### Active Root-Level Doctrine, But Likely Too Many

These are meaningful, but they increase root-level semantic density:

- `PRODUCT_SURFACE.md`
- `docs/architecture/GENOME_WIRING.md`
- `LIVING_LAYERS.md`
- `program.md`
- `program_ecosystem.md`

Interpretation:

- they are not junk
- but not all of them deserve equal top-level prominence
- some likely belong in `docs/architecture/`, `docs/plans/`, or a clearer product/substrate home later

### Non-Doctrine Operational Files

These are root-level runtime or operator entrypoints rather than cleanup targets:

- `run_operator.sh`
- `run_overnight.sh`
- `run_mcp_stdio.py`
- `swarm.sh`
- `swarm_live.sh`
- daemon and helper launch scripts

Interpretation:

- these may still need organization later
- but they are not the same class of problem as root-level prose clutter

## Substrate Directory Classification

### `foundations/`

This is not active product doctrine.
It is conceptual and research substrate.

What it contains:

- synthesis docs
- glossary
- pillar texts
- crown-jewel and protocol material
- transmissions

Recommended classification:

- keep as substrate
- do not fold into `docs/` canon
- improve its explicit indexing rather than relocating it casually

### `lodestones/`

This is also substrate, but more seed-like and orienting than `foundations/`.

What it contains:

- grounding research
- bridges
- reframes
- seeds
- expanded pillar material

Recommended classification:

- keep as substrate
- treat as orientation/intellectual attractor material
- add stronger local indexing before any move decisions

### `mode_pack/`

This is not substrate in the same sense.
It is a live contract and workflow layer.

What it contains:

- `README.md`
- `contracts/mode_pack.v1.json`

Recommended classification:

- keep as live runtime/reference layer
- do not treat it as archive or philosophy
- it is closer to product/runtime support than to substrate

## Plain-English Topology

The root is currently mixing:

- real repo entrypoints
- some strong but over-visible doctrine files
- runtime launcher scripts

The substrate directories are mixing:

- philosophical foundations
- research grounding
- orienting seeds

But those substrate directories are not the same as docs canon, and they should not be cleaned as if they were just misplaced docs.

## Best Next Cleanup Logic

### Do Soon

- finish the current `specs/` cleanup seam
- then take one bounded root-level prose tranche

### Root-Level Prose Tranche Candidates

The most likely future candidates for relocation out of root are:

- `PRODUCT_SURFACE.md`
- `docs/architecture/GENOME_WIRING.md`
- `LIVING_LAYERS.md`

Possible destinations:

- `docs/architecture/`
- `docs/plans/`
- a future product or substrate-specific docs subtree

### Do Not Rush

- do not dissolve `foundations/`
- do not dissolve `lodestones/`
- do not treat `mode_pack/` as a prose cleanup casualty

## Why This Matters

This classification reduces a major source of confusion:

- root-level prose can feel messy because some files are canon-like, some are active notes, and some are really subsystem doctrine
- substrate directories can look like clutter when they are actually a separate knowledge layer

The cleanup goal is not to remove the repo's intelligence.
It is to make each kind of intelligence live in a recognizable place.
