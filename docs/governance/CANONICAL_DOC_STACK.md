# CANONICAL DOC STACK

**Date**: 2026-04-04
**Purpose**: Define the minimal root-adjacent file stack for repo integrity.

---

## Hierarchy (Read Order)

```
TIER 1 — MANDATORY FIRST-READ (agents MUST ingest before any action)
├── CLAUDE.md                          → Agent operating instructions (OWNER of: behavioral rules, architecture, build commands)
├── docs/governance/SOVEREIGN_MANIFEST.md → Repo ground truth (OWNER of: axioms, domain map, invariants, locks)
│
TIER 2 — DOMAIN REFERENCE (read when working in that domain)
├── docs/architecture/NAVIGATION.md    → Module-level map (OWNER of: which file does what, layer assignments)
├── docs/architecture/MODEL_ROUTING_CANON.md → Routing truth (OWNER of: provider selection, model hierarchy)
├── specs/DGC_TERMINAL_ARCHITECTURE_v1.1.md → Terminal protocol (OWNER of: Bun↔Python JSON stdio contract)
│
TIER 3 — FOUNDATIONAL (read for deep context, rarely changes)
├── foundations/INDEX.md               → 10-pillar intellectual genome entry point
├── specs/Dharma_Constitution_v0.md    → Constitutional rules
├── specs/KERNEL_CORE_SPEC.md          → Kernel immutability spec
│
TIER 4 — OPERATIONAL REFERENCE (read when operating the system)
├── README.md                          → Repo overview, quick-start
├── docs/governance/REPO_GOVERNANCE_AUDIT.md → Audit findings, contradictions, stale doc log
│
TIER 5 — ARCHIVE (do not read unless investigating history)
├── docs/archive/*                     → Correctly quarantined old docs
├── LIVING_LAYERS.md                   → Demote to archive (stale, overlaps NAVIGATION.md)
├── program.md                         → Demote to archive (overlaps README)
├── PRODUCT_SURFACE.md                 → Demote to archive or merge into SOVEREIGN_MANIFEST
```

---

## File Ownership Rules

| Kind of Truth | Canonical File | All Others Must Defer |
|---------------|---------------|----------------------|
| Agent behavior rules | `CLAUDE.md` | — |
| Repo axioms & domain map | `SOVEREIGN_MANIFEST.md` | — |
| Module-level what-does-what | `NAVIGATION.md` | — |
| Model/provider routing | `MODEL_ROUTING_CANON.md` | model_routing.py files must not contradict |
| Terminal protocol | `specs/DGC_TERMINAL_ARCHITECTURE_v1.1.md` | v1.0 is deprecated |
| Constitutional axioms | `specs/Dharma_Constitution_v0.md` | — |
| Kernel spec | `specs/KERNEL_CORE_SPEC.md` | — |
| Contradictions & staleness | `REPO_GOVERNANCE_AUDIT.md` | — |

---

## Deprecation / Merge Decisions

### DEPRECATE (move to docs/archive/)
| File | Reason |
|------|--------|
| `LIVING_LAYERS.md` | Overlaps NAVIGATION.md, stale line counts, bloated frontmatter |
| `program.md` | Overlaps README.md |
| `PRODUCT_SURFACE.md` | Content belongs in SOVEREIGN_MANIFEST or README |
| `specs/DGC_TERMINAL_ARCHITECTURE.md` (v1.0) | Superseded by v1.1 |
| `specs/SOVEREIGN_BUILD_PHASE_MASTER_SPEC_2026-03-19.md` | Stale build plan |
| `specs/ONTOLOGY_PHASE2_*.md` | Stale migration spec |
| `docs/architecture/DHARMA_SWARM_THREE_PLANE_ARCHITECTURE_2026-03-16.md` | Pre-TUI, stale |
| `docs/architecture/JIKOKU_SAMAYA_*.md` (4 files) | Merge into 1 or archive |
| `docs/architecture/SWARMLENS_MASTER_SPEC.md` | Replaced by Bun TUI |

### RETAIN AND UPDATE
| File | Action Needed |
|------|--------------|
| `CLAUDE.md` | Fix stale numbers (514 modules, 8571 collected tests, swarm.py 3119 lines, 18 providers not 9). Add pointer to SOVEREIGN_MANIFEST.md. |
| `docs/architecture/NAVIGATION.md` | Fix stale numbers, add bridge/adapter/orchestrator maps |
| `docs/architecture/MODEL_ROUTING_CANON.md` | Acknowledge 3 routing files, define which is canonical |
| `README.md` | Strip excessive Codex frontmatter, keep concise |

### CREATED BY GOVERNANCE AUDIT (2026-04-04)
| File | Purpose | Status |
|------|---------|--------|
| `docs/governance/SOVEREIGN_MANIFEST.md` | Repo ground truth for all agents | **EXISTS** — rewritten with filesystem-verified numbers |
| `docs/governance/REPO_GOVERNANCE_AUDIT.md` | Audit findings and contradiction log | **EXISTS** — updated with re-audit corrections |
| `docs/governance/CANONICAL_DOC_STACK.md` | This file — doc hierarchy | **EXISTS** |

---

## Frontmatter Policy

The Codex (GPT-5) frontmatter injection added 80+ lines of YAML to every markdown file. Policy going forward:

1. **Root governance docs** (Tier 1-2): NO frontmatter. Plain markdown. Maximum clarity.
2. **Architecture docs** (Tier 2-3): Minimal frontmatter (title, date, status only — 5 lines max).
3. **Archive docs**: Leave existing frontmatter in place (it's archived, doesn't matter).
4. **New docs**: No frontmatter unless the doc is consumed by a machine-readable pipeline.

---

## Anti-Doc-Maze Rules

1. **Maximum governance docs at root or docs/governance/**: 5 files
2. **Maximum architecture docs**: 10 files (current: 20 — cut in half)
3. **Any new doc must identify which existing doc it replaces or subordinates to**
4. **No doc may claim "single source of truth" for something another doc also covers**
5. **Stale docs must be archived within 2 weeks of becoming stale**
