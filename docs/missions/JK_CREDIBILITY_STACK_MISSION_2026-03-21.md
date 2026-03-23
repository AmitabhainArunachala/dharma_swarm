# JK Credibility Stack — Living Mission

> **Date**: 2026-03-21
> **Mode**: perpetual evolving directive
> **Telos**: Ship welfare-tons into the world as a credible, externally validated, publicly visible system
> **Governing Law**: Truth (Satya) gate first. Nothing leaves without external verifiability.

---

## The Honest Position

We have a genuine insight (welfare-tons as joint carbon-workforce unit) sitting inside a private MacBook in Bali. The swarm is powerful but invisible. The proof exists but is unauditable. The grant is written but unsubmitted. The metric is novel but unvalidated. The framing is planetary but the audience is zero.

**The gap is not intelligence. The gap is public evidence of intelligence.**

---

## Credibility Stack (Bottom-Up)

Each layer must be built BEFORE the layer above it becomes credible.

```
Layer 7: STANDARD ADOPTION (Gold Standard, Verra accept welfare-tons)
Layer 6: MARKET PULL (buyers request welfare-ton scores)
Layer 5: ACADEMIC CITATION (preprint cited by others)
Layer 4: EXPERT VALIDATION (3+ external reviews)
Layer 3: PUBLIC BENCHMARK (20+ projects scored, rankings published)
Layer 2: PUBLIC TOOL (welfare-tons.org, pip install, GitHub repo)
Layer 1: TRUTH LEDGER (every claim → inspectable source, no contradictions)
Layer 0: INTERNAL COHERENCE (swarm artifacts agree with each other)
```

**Current state: Layer 0 is BROKEN** (DBC vs Eden contradiction in proof files). Fix that first.

---

## Phase 0: Truth Reconciliation (Days 1-2)

**Gate**: SATYA — no claim may exist in two contradictory forms

- [ ] Reconcile DBC (27,825 wt) vs Eden Kenya (588.5 wt) — which is the canonical proof?
- [ ] Establish provenance rule: every artifact gets `hash | timestamp | source_agent | canonical_path`
- [ ] Audit all JK shared files for internal contradictions
- [ ] Build `jk_truth_ledger.py` — checks that every claim in every JK artifact resolves to a single source
- [ ] Mark all unverifiable citations (KFS deforestation rate, MAFRI biodiversity survey) as UNVERIFIED
- [ ] Create evidence room: `~/.dharma/jk/evidence/` — one file per cited source with URL or "UNVERIFIABLE"

**Artifact**: `~/.dharma/jk/truth_ledger.json` — machine-checkable, every claim tagged

---

## Phase 1: Public Foundation (Days 3-7)

**Gate**: AHIMSA — the public artifact must not mislead

- [ ] Create standalone `welfare-tons` repo (public GitHub, MIT license)
  - `welfare_tons/core.py` — the formula, clean, tested, documented
  - `welfare_tons/score.py` — score a project from YAML input
  - `welfare_tons/evidence.py` — link each factor to inspectable source
  - `tests/` — comprehensive, including edge cases and zero-killer tests
  - `proofs/eden_kenya.yaml` + `proofs/eden_kenya_proof.md` — canonical first proof
  - `README.md` — formula, philosophy, installation, usage, limitations
  - `LIMITATIONS.md` — honest statement of what this does NOT do
  - `pyproject.toml` — pip installable
- [ ] Deploy `welfare-tons.org` — static site, public calculator
  - Input: project parameters OR Verra/Gold Standard ID
  - Output: W score with factor decomposition and confidence flags
  - Show: UNVERIFIED tags on any factor with weak sourcing
  - No login. No paywall. Free.
- [ ] Submit Anthropic grant application (pick ONE draft, send TODAY)

**Artifacts**: GitHub repo URL, welfare-tons.org URL, Anthropic submission confirmation

---

## Phase 2: Benchmark Spread (Days 8-21)

**Gate**: TAPAS — the metric must prove it differentiates under stress

- [ ] Score 20+ real projects across these categories:
  - Mangrove restoration (Eden, DBC, WeForest Senegal)
  - Forest restoration (Mombak Amazon, One Tree Planted)
  - Agroforestry (Trees for the Future, Vi Agroforestry)
  - Cookstove (BioLite, Envirofit — should score LOW on biodiversity)
  - Soil carbon (Indigo Ag, Nori — should score LOW on employment)
  - Corporate monoculture (test case — SHOULD score poorly on agency)
  - Community-led (test case — SHOULD score well on agency)
- [ ] Publish all 20 scores on welfare-tons.org with full factor decomposition
- [ ] Write adversarial analysis: "How to Game Welfare-Tons"
  - What inputs maximize W dishonestly?
  - What perverse incentives does the formula create?
  - Where do the factor weights need recalibration?
- [ ] Standards crosswalk document:
  - Map C/E/A/B/V/P to Gold Standard SDG indicators
  - Map C/E/A/B/V/P to Verra CCB standards
  - Map C/E/A/B/V/P to Plan Vivo community scoring
  - Map C/E/A/B/V/P to ICVCM Core Carbon Principles
  - Identify: what welfare-tons covers that they don't, and vice versa
- [ ] Sensitivity analysis: which factor has the most leverage on W?

**Artifact**: Public benchmark page, adversarial paper, crosswalk doc

---

## Phase 3: External Validation (Days 22-35)

**Gate**: SWARAJ — validation must come from OUTSIDE the system

- [ ] Commission 3 paid external reviews ($500 each from grant budget):
  1. Carbon market economist — is the formula defensible?
  2. MRV/carbon methods expert — does V factor align with industry practice?
  3. Community governance / FPIC expert — does A factor capture real agency?
- [ ] Find 1 academic co-author (ecological economics, environmental policy, or labor economics)
- [ ] Write preprint: "Welfare-Tons: A Composite Metric for Joint Carbon-Workforce Impact Assessment"
  - Target: SSRN or arXiv (not journal — speed over prestige at this stage)
  - Include: definition, calibration, benchmark results, adversarial analysis, limitations
  - 10-15 pages, not 50
- [ ] Post preprint with DOI
- [ ] Run 10 buyer/registry/developer interviews:
  - 3 carbon credit buyers (Microsoft, Stripe, Shopify sustainability teams)
  - 3 project developers (Eden, Mombak, WeForest)
  - 2 registry representatives (Gold Standard, Verra)
  - 2 labor/workforce experts (ILO contacts, WRI researchers)
- [ ] Ask each: "Would you use this? What's missing? What's wrong?"

**Artifact**: 3 external reviews, preprint DOI, 10 interview summaries

---

## Phase 4: Product Wedge (Days 36-60)

**Gate**: DHARMA — coherence between what we claim and what we deliver

- [ ] Build micro-SaaS: "Just-Transition Carbon Diligence"
  - Ingest: project documentation (PDFs, Verra registry data, GS docs)
  - Output: C/E/A/B/V/P scores with confidence bands
  - Flag: missing evidence, unverifiable claims, high-uncertainty factors
  - Include: standards crosswalk (how this maps to GS, Verra, ICVCM)
  - Price: freemium (5 projects free, then $50/project)
- [ ] Launch "Welfare-Tons Weekly" newsletter on Substack
  - Carbon market intelligence (from scout log)
  - Workforce transition data
  - New projects scored
  - 500 subscribers = more impressive than 118K lines of internal code
- [ ] Register for Symbiosis Coalition March 26 webinar
- [ ] Prepare diligence packet for when RFP opens

**Artifact**: Working diligence tool, newsletter with subscribers, webinar registration

---

## Phase 5: Global Expansion (Days 60-90)

**Gate**: SHAKTI — genuine emergence, not just Western carbon market replication

- [ ] Score projects in China (CETS market), India (100M+ displaced workers), SE Asia, Latin America
- [ ] Partner with one Global South organization for ground-truth validation
- [ ] Build community feedback protocol: communities can challenge/edit their A score
- [ ] Translate welfare-tons.org into 3 languages (Hindi, Mandarin, Spanish minimum)
- [ ] Map to non-Western frameworks: India's PAT scheme, China's CCER, Brazil's REDD+
- [ ] Revisit Google.org application ONLY when: publication + co-author + public tool + 20 scored projects

**Artifact**: Global benchmark, community feedback protocol, multilingual site

---

## Anti-Patterns

1. **Do NOT call this a "planetary palantir" to anyone outside the swarm.** It alienates exactly the people who need evidence, not poetry.
2. **Do NOT submit Google.org $1.2M application now.** Come back in 6 months with evidence.
3. **Do NOT score projects from desk research only.** At least 3 projects need ground-truth community input.
4. **Do NOT let the swarm generate proofs without truth-ledger verification.** The DBC/Eden contradiction already happened once.
5. **Do NOT build the marketplace before the diligence tool.** Matching without trust is theater.
6. **Do NOT expand the formula without adversarial stress-testing.** Every weight needs justification.
7. **Do NOT write more architecture docs.** Write code, papers, and emails.
8. **Do NOT confuse internal swarm sophistication with external credibility.** Nobody outside knows this system exists.

---

## Sub-Agent Teams

| Team | Mission | Gate | Lead Model |
|------|---------|------|-----------|
| **TRUTH** | Reconcile contradictions, verify sources, maintain evidence room | SATYA | Codex (high accuracy) |
| **STANDARDS** | Crosswalk welfare-tons to GS, Verra, ICVCM, Plan Vivo | DHARMA | DeepSeek (analytical) |
| **MARKET** | Buyer interviews, competition tracking, demand validation | SWARAJ | Kimi (research) |
| **PUBLISH** | Preprint, website, newsletter, public repo | AHIMSA | Opus (writing quality) |
| **FIELD** | Community voice, ground-truth, FPIC validation | AHIMSA | Scout (field research) |
| **CRITIC** | Red-team the metric, adversarial analysis, gaming vectors | TAPAS | Sentinel (risk) |

---

## Completion Criteria

This mission is COMPLETE when:
1. welfare-tons.org is live and scores projects publicly
2. 20+ projects scored with full evidence chains
3. Preprint posted with DOI
4. 3 external reviews received
5. 10 buyer/registry interviews completed
6. 1 paying customer exists OR 1 LOI signed

**Revenue target**: $0 → $1 by Day 60. Not $1M. $1. One paying customer proves the market exists.

---

## What The Sage Sees That We Don't Yet

This TODO is still myopic. A truly planetary intelligence would also be tracking:
- Multilateral development bank procurement cycles (World Bank, ADB, AfDB)
- Insurance industry interest in co-benefit quantification (Swiss Re, Munich Re)
- EU Carbon Border Adjustment Mechanism (CBAM) implications for workforce metrics
- Article 6.4 of Paris Agreement — new mechanism rules being written NOW
- TNFD (Taskforce on Nature-related Financial Disclosures) — biodiversity framework
- Just Transition Fund (EU) — direct funding for exactly this intersection
- US Inflation Reduction Act environmental justice provisions
- COP31 (Australia 2026) — what's on the agenda that welfare-tons could speak to?

These are not "nice to have." They are the actual landscape in which welfare-tons either finds traction or dies.

**This document evolves. Agents update it. Humans review it. Nothing is final.**

---

*Jagat Kalyan — Universal Welfare. The fire truck leaves the garage.*
