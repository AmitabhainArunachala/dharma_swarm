---
title: Substrate Directory Cartography
path: docs/plans/2026-04-03-substrate-directory-cartography.md
slug: substrate-directory-cartography
doc_type: plan
status: active
summary: Maps the actual content shapes inside foundations, lodestones, and mode_pack so substrate cleanup decisions can be based on directory reality rather than abstract policy alone.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - foundations/INDEX.md
  - lodestones/README.md
  - mode_pack/README.md
  - filesystem scan on 2026-04-03
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- knowledge_management
- documentation
- software_architecture
- operations
- verification
inspiration:
- repo_topology
- canonical_truth
connected_relevant_files:
- docs/plans/2026-04-03-substrate-graduation-candidates.md
- docs/plans/2026-04-02-substrate-layer-policy.md
- foundations/INDEX.md
- lodestones/README.md
- mode_pack/README.md
- docs/plans/2026-04-02-root-and-substrate-classification-map.md
improvement:
  room_for_improvement:
  - Add per-file graduation candidates only after the directory-level shapes are accepted.
  - Recheck this map if the substrate directories grow materially.
  - Add examples of files that clearly should stay versus files that may mature outward.
  next_review_at: '2026-04-04T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-03-substrate-directory-cartography.md
  retrieval_terms:
  - substrate
  - cartography
  - foundations
  - lodestones
  - mode_pack
  - directory map
  evergreen_potential: high
stigmergy:
  meaning: This file turns the substrate policy into a concrete map of what each substrate directory currently contains.
  state: active
  semantic_weight: 0.84
  coordination_comment: Use this note before proposing any file-level substrate moves.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-03T02:00:00+09:00'
  curated_by_model: Codex (GPT-5)
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Substrate Directory Cartography

## Purpose

The substrate policy already says `foundations/`, `lodestones/`, and `mode_pack/` are different layers.

This note maps what is actually inside them so later cleanup can decide by real content shape instead of intuition.

## `foundations/`

### Current content shape

The directory currently clusters around:

- pillar canon
  - `PILLAR_01_LEVIN.md`
  - `PILLAR_02_KAUFFMAN.md`
  - `PILLAR_03_JANTSCH.md`
  - `PILLAR_05_DEACON.md`
  - `PILLAR_06_FRISTON.md`
  - `PILLAR_07_HOFSTADTER.md`
  - `PILLAR_08_AUROBINDO.md`
  - `PILLAR_09_DADA_BHAGWAN.md`
  - `PILLAR_10_VARELA.md`
  - `PILLAR_11_BEER.md`
- synthesis and canon-bridging notes
  - `FOUNDATIONS_SYNTHESIS.md`
  - `META_SYNTHESIS.md`
  - `SYNTHESIS_DEACON_FRISTON.md`
  - `THINKODYNAMIC_BRIDGE.md`
- conceptual reference surfaces
  - `GLOSSARY.md`
  - `EMPIRICAL_CLAIMS_REGISTRY.md`
  - `SAMAYA_PROTOCOL.md`
  - `ECONOMIC_VISION.md`
  - `SACRED_GEOMETRY.md`
- transmissions / higher-churn substrate notes
  - `transmissions/`

### Read

`foundations/` is mostly coherent as conceptual canon already.

The main internal distinction is:

- durable pillar-level canon
- synthesis and bridge notes
- higher-churn transmission material

That suggests indexing and internal subtyping are more urgent than relocation.

## `lodestones/`

### Current content shape

The directory already has meaningful internal structure:

- `seeds/`
  - generative orienting fragments
- `reframes/`
  - perspective shifts and conceptual rewrites
- `bridges/`
  - connection surfaces between ideas and directions
- `grounding/`
  - research-backed support material
- `pillars_expanded/`
  - expanded readings that rhyme with foundations but are less canonical
- `CONSCIOUS_INFRASTRUCTURE.md`
  - broad orienting note

### Read

`lodestones/` is not random residue.

It functions as an orienting layer with a good native grammar:

- seed
- reframe
- bridge
- grounding

The main risk is not disorder.
The main risk is authority drift, especially where `grounding/` and `pillars_expanded/` start to impersonate `foundations/`.

## `mode_pack/`

### Current content shape

The directory is structurally different from the other two:

- `contracts/mode_pack.v1.json`
  - machine-readable contract surface
- `claude/`
  - operator mode directories such as:
    - `ceo-review`
    - `eng-review`
    - `incident-commander`
    - `qa`
    - `retro`
    - `browse`
    - `ship`

### Read

`mode_pack/` is not prose substrate.

It is an operational workflow/contract surface with:

- one explicit machine-readable contract
- one human/operator mode hierarchy

It should be treated closer to runtime support or operator contract than to `foundations/` or `lodestones/`.

## Main Boundary Tensions

The current overlaps are:

1. `foundations/` vs `lodestones/`
   - expanded pillars, bridge notes, and grounding notes can blur conceptual canon versus orienting interpretation

2. `lodestones/` vs `mode_pack/`
   - almost no current content overlap
   - the main danger is treating both as “misc support material” when they are not the same

3. `foundations/` vs live architecture/spec truth
   - bridge notes like `THINKODYNAMIC_BRIDGE.md` and protocol-like notes such as `SAMAYA_PROTOCOL.md` may eventually need graduation review

## Current Best Cleanup Posture

Based on current directory shape:

- `foundations/`
  - keep in place
  - strengthen internal indexing and canon-vs-transmission distinction
- `lodestones/`
  - keep in place
  - preserve its seed/reframe/bridge/grounding grammar
  - watch for authority drift into foundations/specs
- `mode_pack/`
  - keep in place
  - treat as operational contract surface, not substrate prose

## Recommended Next Move

The next safe substrate move is not relocation.

It is one bounded classification pass that labels:

1. likely stay-put canonical substrate files in `foundations/`
2. likely stay-put orienting files in `lodestones/`
3. possible graduation candidates from either directory
4. `mode_pack/` as explicitly non-prose operational contract

Candidate map:

- [2026-04-03-substrate-graduation-candidates.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-substrate-graduation-candidates.md)

## Control Entry Points

- [substrate-layer-policy.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-substrate-layer-policy.md)
- [root-and-substrate-classification-map.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-root-and-substrate-classification-map.md)
- [foundations/INDEX.md](/Users/dhyana/dharma_swarm/foundations/INDEX.md)
- [lodestones/README.md](/Users/dhyana/dharma_swarm/lodestones/README.md)
- [mode_pack/README.md](/Users/dhyana/dharma_swarm/mode_pack/README.md)
