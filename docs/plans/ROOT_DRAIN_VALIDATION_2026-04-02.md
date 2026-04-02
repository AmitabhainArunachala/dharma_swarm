---
title: Root Drain Validation
path: docs/plans/ROOT_DRAIN_VALIDATION_2026-04-02.md
slug: root-drain-validation
doc_type: plan
status: active
summary: "Date: 2026-04-02 Scope: verify that the six-document root-drain stabilization slice is tracked, merge-safe, and only as broadly claimed as was actually checked."
source:
  provenance: repo_local
  kind: validation_note
  origin_signals:
  - README.md
  - CLAUDE.md
  - docs/README.md
  - program_ecosystem.md
  - scripts/seed_signal_map.py
  - reports/historical/GODEL_CLAW_V1_REPORT.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- software_architecture
- knowledge_management
- verification
- documentation
inspiration:
- repo_topology
- verification
connected_relevant_files:
- README.md
- CLAUDE.md
- docs/README.md
- program_ecosystem.md
- scripts/seed_signal_map.py
- docs/archive/AGENT_SWARM_SYNTHESIS.md
- docs/archive/MOONSHOT_COMPLETE.md
- docs/archive/PALANTIR_ONTOLOGY_GAP_ANALYSIS.md
- docs/archive/UNASSAILABLE_SYSTEM_BLUEPRINT.md
- docs/architecture/VERIFICATION_LANE.md
- reports/historical/GODEL_CLAW_V1_REPORT.md
improvement:
  room_for_improvement:
  - Keep the scope bound to explicitly verified path pairs and backlinks.
  - Add follow-up validation notes instead of expanding this file into repo-wide cleanup claims.
  next_review_at: '2026-04-03T00:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/ROOT_DRAIN_VALIDATION_2026-04-02.md
  retrieval_terms:
  - root
  - drain
  - validation
  - merge-safe
  - backlinks
  - retirement
  evergreen_potential: medium
stigmergy:
  meaning: This note records what was actually validated for the bounded root-drain slice and where validation stops.
  state: working
  semantic_weight: 0.82
  coordination_comment: Use this note as a scoped truth record, not as proof of repo-wide backlink cleanliness.
  trace_role: validation_trace
curation:
  last_frontmatter_refresh: '2026-04-02T00:00:00+09:00'
  curated_by_model: Codex (GPT-5)
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Root Drain Validation

Date: 2026-04-02
Repo: `dharma_swarm`
Scope: verify the current root-drain slice is merge-safe for the six path pairs actively being retired in this pass

This note records git reality for the current slice. It does not claim repo-wide backlink cleanup or root-drain completion.

## Merge-Safe Status

The six affected replacements now exist on disk and are tracked in git before their paired root paths are retired.

| Former root path | Replacement | On disk | Tracked in git | Current git state |
|------------------|-------------|---------|----------------|-------------------|
| `AGENT_SWARM_SYNTHESIS.md` | `docs/archive/AGENT_SWARM_SYNTHESIS.md` | yes | yes | staged rename |
| `MOONSHOT_COMPLETE.md` | `docs/archive/MOONSHOT_COMPLETE.md` | yes | yes | staged rename |
| `PALANTIR_ONTOLOGY_GAP_ANALYSIS.md` | `docs/archive/PALANTIR_ONTOLOGY_GAP_ANALYSIS.md` | yes | yes | staged rename |
| `UNASSAILABLE_SYSTEM_BLUEPRINT.md` | `docs/archive/UNASSAILABLE_SYSTEM_BLUEPRINT.md` | yes | yes | staged rename |
| `VERIFICATION_LANE.md` | `docs/architecture/VERIFICATION_LANE.md` | yes | yes | staged delete + add |
| `GODEL_CLAW_V1_REPORT.md` | `reports/historical/GODEL_CLAW_V1_REPORT.md` | yes | yes | staged rename |

## What Was Verified

- Each replacement file is present on disk and contains substantive document content, not a stub.
- The replacement files carry path frontmatter aligned with their current locations:
  - `docs/archive/AGENT_SWARM_SYNTHESIS.md`
  - `docs/archive/MOONSHOT_COMPLETE.md`
  - `docs/archive/PALANTIR_ONTOLOGY_GAP_ANALYSIS.md`
  - `docs/archive/UNASSAILABLE_SYSTEM_BLUEPRINT.md`
  - `docs/architecture/VERIFICATION_LANE.md`
  - `reports/historical/GODEL_CLAW_V1_REPORT.md`
- The root originals are no longer present in the working tree and their retirements are staged only after the replacements were added to git.

## Navigation And Backlink Reality

- `README.md` still points to `docs/dse/GAIA_UI.md`, which matches the current destination for `gaia_ui.md`.
- `CLAUDE.md` points to `docs/architecture/NAVIGATION.md`, which matches the current destination.
- `docs/README.md` points at architecture and archive surfaces rather than the drained root paths checked in this slice.
- Only two backlink-touch examples were directly verified in this pass:
  - `program_ecosystem.md` now references `docs/archive/AGENT_SWARM_SYNTHESIS.md`
  - `scripts/seed_signal_map.py` now references `reports/historical/GODEL_CLAW_V1_REPORT.md`
- This pass does not claim full backlink cleanup across the repo.

## Residual Issues

- Root-drain cleanup outside these six path pairs is not validated by this note.
- Some historical reports, prompts, and planning docs still mention former root paths. Those references may be acceptable archival record and are not automatically navigation bugs.
- Additional stale root-era references likely remain outside the touched set. They should be cleaned only by targeted follow-up verification, not inferred from this pass.
- `VERIFICATION_LANE.md` currently stages as delete plus add rather than rename detection. That is merge-safe, but the path pair should still be reviewed as a move, not as proof of content identity.

## Current Stop Point

This slice is merge-safe with respect to the six path pairs above because the replacement files are now tracked before the tracked root sources are retired.

It is not accurate to call the broader repo backlink-clean yet.
