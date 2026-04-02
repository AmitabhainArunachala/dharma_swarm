---
title: DHARMA Prompt Index
path: docs/prompts/README.md
slug: dharma-prompt-index
doc_type: readme
status: active
summary: Index of reusable prompt artifacts that were moved out of repo root during the documentation cleanup.
source:
  provenance: repo_local
  kind: readme
  origin_signals:
  - docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md
  - docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE3.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- knowledge_management
- operations
- software_architecture
inspiration:
- operator_runtime
- research_synthesis
connected_relevant_files:
- docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md
  - docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE3.md
improvement:
  room_for_improvement:
  - Split active prompt packs from historical prompt packs as needed.
  - Add narrower topical indexes if this directory grows much larger.
  next_review_at: '2026-04-01T23:59:00+09:00'
pkm:
  note_class: readme
  vault_path: docs/prompts/README.md
  retrieval_terms:
  - prompts
  - prompt
  - index
  - operators
  evergreen_potential: medium
stigmergy:
  meaning: This file gives prompt artifacts a dedicated home instead of leaving them in repo root.
  state: active
  semantic_weight: 0.8
  coordination_comment: Use this directory for reusable prompt artifacts, not product or runtime truth.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-01T23:59:00+09:00'
  curated_by_model: Codex (GPT-5)
  schema_version: pkm-phd-stigmergy-v1
---
# DHARMA Prompt Index

This directory holds reusable prompt artifacts. These are not product truth, runtime truth, or architecture canon.

## Current Prompt Pack

- [DEEP_REPO_CARTOGRAPHER_PROMPT_2026-03-31.md](/Users/dhyana/dharma_swarm/docs/prompts/DEEP_REPO_CARTOGRAPHER_PROMPT_2026-03-31.md)
- [DGC_SUBAGENT_GAUNTLET_PROMPT.md](/Users/dhyana/dharma_swarm/docs/prompts/DGC_SUBAGENT_GAUNTLET_PROMPT.md)
- [DHARMIC_SINGULARITY_PROMPT_v2.md](/Users/dhyana/dharma_swarm/docs/prompts/DHARMIC_SINGULARITY_PROMPT_v2.md)
- [ROUTER_EVOLUTION_SUBSTRATE_PROMPT.md](/Users/dhyana/dharma_swarm/docs/prompts/ROUTER_EVOLUTION_SUBSTRATE_PROMPT.md)
- [MEGA_PROMPT_STRANGE_LOOP.md](/Users/dhyana/dharma_swarm/docs/prompts/MEGA_PROMPT_STRANGE_LOOP.md)
- [MEGA_PROMPT_v2.md](/Users/dhyana/dharma_swarm/docs/prompts/MEGA_PROMPT_v2.md)
- [MEGA_PROMPT_v3.md](/Users/dhyana/dharma_swarm/docs/prompts/MEGA_PROMPT_v3.md)
- [MEGA_PROMPT_v4.md](/Users/dhyana/dharma_swarm/docs/prompts/MEGA_PROMPT_v4.md)
- [STRANGE_LOOP_COMPLETE_PROMPT.md](/Users/dhyana/dharma_swarm/docs/prompts/STRANGE_LOOP_COMPLETE_PROMPT.md)
- [STRANGE_LOOP_COMPLETE_PROMPT_v2.md](/Users/dhyana/dharma_swarm/docs/prompts/STRANGE_LOOP_COMPLETE_PROMPT_v2.md)
- [ORTHOGONAL_UPGRADE_PROMPT.md](/Users/dhyana/dharma_swarm/docs/prompts/ORTHOGONAL_UPGRADE_PROMPT.md)
- [PALANTIR_UPGRADE_PROMPT.md](/Users/dhyana/dharma_swarm/docs/prompts/PALANTIR_UPGRADE_PROMPT.md)
- [STRATEGIC_PROMPT.md](/Users/dhyana/dharma_swarm/docs/prompts/STRATEGIC_PROMPT.md)

## Rules

- Put reusable prompts here, not in repo root.
- Do not treat prompt files as canonical architecture or product truth.
- If a prompt becomes historically important but no longer active, move it into an archive subtree rather than returning it to root.
