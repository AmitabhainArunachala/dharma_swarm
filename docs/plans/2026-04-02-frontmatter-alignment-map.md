---
title: Frontmatter Alignment Map
path: docs/plans/2026-04-02-frontmatter-alignment-map.md
slug: frontmatter-alignment-map
doc_type: plan
status: active
summary: "Date: 2026-04-02 Purpose: place the YAML frontmatter system into the repo cleanup program and identify where metadata and filing structure align or drift."
source:
  provenance: repo_local
  kind: plan
  origin_signals:
  - scripts/normalize_markdown_frontmatter.rb
  - docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md
  - docs/plans/2026-04-02-current-meta-topology-of-dharma-swarm.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
---
# Frontmatter Alignment Map

Date: 2026-04-02
Scope: prose-layer metadata system and its fit with the ongoing cleanup program

## Thesis

The frontmatter pass is real and substantial.

It is not the whole filing system, but it is already acting like a semantic nervous system for the prose layer.

The cleanup program should not ignore it.
It should use it.

## What Exists

There is a repo-level normalization script:

- `scripts/normalize_markdown_frontmatter.rb`

It injects or normalizes metadata such as:

- `title`
- `path`
- `slug`
- `doc_type`
- `status`
- `summary`
- `source`
- `disciplines`
- `inspiration`
- `connected_*`
- `improvement`
- `pkm`
- `stigmergy`
- `curation`
- `schema_version: pkm-phd-stigmergy-v1`

This is not casual YAML.
It is a repo-wide metadata framework.

## Coverage Snapshot

Markdown coverage by domain:

- `docs`: `256` total, `230` with frontmatter, `89.8%`
- `reports`: `118` total, `117` with frontmatter, `99.2%`
- `foundations`: `25` total, `25` with frontmatter, `100%`
- `lodestones`: `14` total, `14` with frontmatter, `100%`
- `specs`: `22` total, `22` with frontmatter, `100%`
- `spec-forge`: `17` total, `17` with frontmatter, `100%`
- `research`: `4` total, `4` with frontmatter, `100%`
- `spinouts`: `1` total, `1` with frontmatter, `100%`
- `dharma_swarm` markdown: `10` total, `10` with frontmatter, `100%`

Repo-wide markdown count observed:

- total markdown files: `1856`
- markdown files with frontmatter detected: `796`

Interpretation:

- coverage is not universal across the entire repo
- but it is extremely strong across the main prose domains that matter for cleanup

## Where It Fits In The Big Picture

The cleanup program is organizing the filing system by authority and class.

The frontmatter layer is already trying to describe those classes in machine-readable form.

So the two efforts should converge:

- cleanup decides where a file belongs and what authority it should have
- frontmatter describes what the file is, how it connects, and what state it is in

That means frontmatter is:

- not a side project
- not enough by itself
- highly relevant infrastructure for the cleanup phase

## What It Does Well

The frontmatter layer already gives us:

- document self-description
- path and vault identity
- status hints
- type hints
- provenance
- connected-code and connected-doc signals
- archival and stigmergic semantics

This is very useful during cleanup because it helps answer:

- what does this file think it is?
- does that match where it lives?
- is its status aligned with its role?
- what might break if it moves?

## What It Does Not Solve By Itself

Frontmatter does not automatically solve:

- canon vs non-canon precedence
- whether a file should stay top-level
- whether a historical file is too visible
- whether a generated family is too coupled to move
- which doc tranches are safe next seams

That is why the topology and cleanup work still matters.

## Current Drift Patterns

The main drift is not missing frontmatter everywhere.
It is mismatch between metadata and filing reality in some important top-level docs.

Examples of top-level `docs/*.md` still lacking frontmatter:

- `docs/plans/2026-04-02-current-meta-topology-of-dharma-swarm.md`
- `DHARMA_COMMAND_NORTH_STAR_SPEC_2026-04-01.md`
- `DHARMA_COMMAND_POWER_BUILD_LOOP_SPEC_2026-04-01.md`
- `DHARMA_COMMAND_WORLD_CLASS_PRODUCT_SPEC_2026-04-01.md`
- `GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md`
- `HOT_PATH_INTEGRATION_PROTOCOL_2026-04-01.md`
- `OVERNIGHT_AGENT_SUPERVISOR_ARCHITECTURE_2026-04-01.md`
- `docs/plans/REPO_HYGIENE_TRIAGE_2026-04-01.md`
- `REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md`
- `REPO_RECLASSIFICATION_MATRIX_2026-04-01.md`
- several terminal-specific top-level docs

Interpretation:

- the frontmatter pass is strongest in the older, broader prose substrate
- some of the newer high-level cleanup and command docs still sit outside that semantic layer

## Working Rule For Ongoing Cleanup

While cleanup continues:

1. use frontmatter as evidence, not absolute truth
2. when moving files, update `path` and `vault_path`
3. when status and role disagree, fix the metadata
4. do not treat lack of frontmatter as a reason not to classify a file
5. do not let frontmatter override runtime or operator truth

## Best Next Metadata Move

Do not run a massive repo-wide frontmatter wave right now.

Instead:

- keep updating metadata opportunistically inside each cleanup tranche
- after a few more authority tranches, run a targeted alignment pass on the highest-value top-level docs that still lack frontmatter

Best future candidates:

- `docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md`
- `docs/REPO_RECLASSIFICATION_MATRIX_2026-04-01.md`
- `docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md`
- `docs/DHARMA_COMMAND_NORTH_STAR_SPEC_2026-04-01.md`
- `docs/DHARMA_COMMAND_WORLD_CLASS_PRODUCT_SPEC_2026-04-01.md`

## Bottom Line

The frontmatter layer belongs inside the cleanup trajectory.

It is best understood as:

- the prose layer's semantic metadata system
- already strong across the main non-code domains
- helpful for safe moves and authority classification
- still partial at the newest top-level doctrine layer

So the correct approach is:

- keep cleaning the filing system
- keep updating frontmatter inside those moves
- later align the remaining top-level doctrine docs into the same metadata system
