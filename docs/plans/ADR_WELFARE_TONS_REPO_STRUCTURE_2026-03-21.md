# ADR: Where Welfare-Tons Code Lives

> **Date**: 2026-03-21
> **Status**: DECIDED
> **Decision**: Standalone repo for the public library + website; dharma_swarm orchestrates work on it

---

## Context

The Ruthless Critique established that welfare-tons needs public existence: a GitHub repo, a pip-installable package, a website, and a preprint. The question is where this code lives relative to dharma_swarm.

## Options Considered

### A: Module inside dharma_swarm
- **Pro**: No context switching, tests in same suite, agents already have access
- **Con**: dharma_swarm is 118K lines of private code. Making welfare-tons public means either open-sourcing the whole swarm (premature) or extracting a module (messy). Also, dharma_swarm is an AGENT — it does work. Welfare-tons is a PRODUCT — it is the work.

### B: Standalone repo (CHOSEN)
- **Pro**: Clean public face. MIT license. pip-installable. Anyone can use it without seeing swarm internals. Forces the code to stand on its own without relying on swarm infrastructure.
- **Con**: Two repos to maintain. Agents need to clone/read the external repo to work on it.

### C: Monorepo with separate package
- **Pro**: One repo, separate packages
- **Con**: Still forces the public and private code into the same repo. GitHub visibility is all-or-nothing.

## Decision

**Option B: Standalone repo.**

```
~/jagat_kalyan/welfare-tons/     # Standalone public repo
├── welfare_tons/
│   ├── __init__.py
│   ├── core.py                  # W = C × E × A × B × V × P
│   ├── score.py                 # Score a project from YAML
│   ├── evidence.py              # Link factors to inspectable sources
│   ├── sensitivity.py           # Monte Carlo / sensitivity analysis
│   └── crosswalk.py             # Map to GS, Verra, ICVCM, Plan Vivo
├── proofs/
│   ├── eden_kenya.yaml          # Canonical first proof
│   ├── eden_kenya_proof.md      # Generated proof document
│   └── ...                      # More scored projects
├── site/                        # welfare-tons.org (static, maybe Astro/11ty)
│   ├── index.html
│   ├── calculator/
│   └── benchmark/               # Public benchmark page
├── paper/                       # Preprint source
│   └── welfare_tons_preprint.tex
├── tests/
├── pyproject.toml
├── README.md
├── LIMITATIONS.md
├── LICENSE                      # MIT
└── CLAUDE.md                    # So swarm agents know how to work here
```

## How dharma_swarm Works ON welfare-tons

1. **dharma_swarm contains the intelligence** — credibility gates, sub-team definitions, semantic seeds, mission docs
2. **welfare-tons repo contains the product** — the formula, the proofs, the website, the paper
3. **Agents dispatched by dharma_swarm clone/read welfare-tons repo** to do their work
4. **The evidence room** (`~/.dharma/jk/evidence/`) is shared state accessible to both
5. **Stigmergy marks** reference both repos — agents leave marks on welfare-tons files too

```
dharma_swarm (the organism)
    ├── jk_credibility_gates.py    # HOW to evaluate
    ├── jk_subteams.py             # WHO does what
    ├── jk_credibility_seed.py     # WHAT we know about gaps
    ├── jk_stigmergy_seeds.py      # SIGNALS for agents
    └── jagat_kalyan.py            # WHY (world intelligence)
         │
         │  dispatches agents to work on ──→
         │
welfare-tons (the product)
    ├── welfare_tons/core.py       # THE formula
    ├── proofs/                    # THE evidence
    ├── site/                      # THE public face
    └── paper/                     # THE preprint
```

## Consequences

- welfare-tons repo can be public from day 1
- dharma_swarm remains private (for now)
- Agents need `~/jagat_kalyan/welfare-tons/` path in their working context
- Tests for welfare-tons are separate from dharma_swarm's 4300+ tests
- CI/CD for welfare-tons is separate (GitHub Actions, not swarm-internal)

## What to Build First

1. `welfare_tons/core.py` — the formula, extracted from the proof
2. `welfare_tons/score.py` — YAML → W score
3. `proofs/eden_kenya.yaml` — the canonical first proof
4. `tests/` — edge cases, zero-killers, sensitivity
5. `README.md` — formula, philosophy, limitations, usage
6. `pyproject.toml` — pip installable
7. Push to GitHub public

Everything else (website, paper, crosswalk) can follow iteratively.
