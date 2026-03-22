---
title: "Measuring Labor Market Outcomes of Corporate Carbon Investment: Welfare-Tons as a Joint Workforce-Environmental Impact Metric"
date: 2026-03-21
version: 2.1
type: grant_application
funder: Anthropic Economic Futures Research Awards Program
ask_usd: 35000
duration_months: 6
yosemite_grade: 5.13c
stars: 15
readiness_measure: ready to submit
status: submission ready
source_draft: /Users/dhyana/jagat_kalyan/grants/anthropic_grant_application_v2.md
prior_version: anthropic_grant_application.md (5.11c / 14 stars)
upgrade_methodology: GRANT_UPGRADE_WORKFLOW.md
changes_from_v1:
  - QALY analogy abstract opening replacing statistics-first opening
  - Welfare-tons formula upgraded to v2.0 (W = C×E×A×B×V×P)
  - Anthropic Economic Index tension acknowledged and reframed as opportunity
  - "Multi-objective optimization" corrected to "constrained optimization"
  - "Value extraction without loop closure" removed — replaced with neutral economics language
  - Competitive differentiation section added (vs. SD VISta, CCB, Plan Vivo)
  - Preliminary evidence added: welfare_tons.py (300+ tests, 9 project archetypes)
  - IRB research ethics statement added
  - Claude API use integrated explicitly into methodology
  - Publication target corrected: Ecological Economics vs. Nature Sustainability
  - Qualifications stats updated: 32/39 FDR, ~400 measurements, "targeting COLM"
  - Travel budget clarified as virtual-first
  - 7 vague references resolved with specific authors/titles/URLs
  - DemandSage citations replaced with BLS/WEF primary sources
  - Alignment section corrected: ecological restoration reframed vs. "higher-value AI roles"
  - Advisory gap addressed with named targets and a paid review budget line
  - SHRM 23.2M corrected: ~9.2M at displacement risk; majority face transformation not displacement; WEF net jobs counterweight (+170M created vs. 92M displaced) added
  - Algorithm solver specified: PuLP/GLPK weighted scalarization (open-source, feasibility-study scale)
  - Geographic/skills mismatch named as explicit research question
  - ILO 2024 carbon markets working paper added to references
  - Competitive differentiation section overhauled with full landscape (CCCI, ICVCM gap, UNEP/ILO 2024, WBA JTI Feb 2025)
  - UNEP/ILO "Decent Work in NbS" (Dec 2024) + WBA Just Transition Indicators (Feb 2025) + Rockefeller CCCI added to references
  - 2x2 competitive position (joint measurement × matching algorithm) articulated — empty cell named explicitly
  - Unique positioning statement: "welfare-tons as jointly traded unit" vs. add-on label
  - IEA citation corrected to use report-supported 2024 data-centre demand and accelerated-server growth language
tags:
  - jagat_kalyan
  - welfare_tons
  - carbon_markets
  - workforce_transition
  - ecological_restoration
  - qaly_analogy
---

# Anthropic Economic Futures Research Award Application

**Applicant**: John Shrader
**Date**: March 14, 2026
**Requested Amount**: $35,000
**Research Duration**: 6 months

---

## 1. Title and Abstract

### Measuring Labor Market Outcomes of Corporate Carbon Investment: Welfare-Tons as a Joint Workforce-Environmental Impact Metric

**Abstract** (215 words)

When health economists developed quality-adjusted life years in the 1970s, they did not invent a new value — they made an existing value visible. A year of paralysis is not equivalent to a year of mobility; the mathematics had simply never been made explicit. This proposal introduces an analogous composite unit for the AI workforce transition: **welfare-tons**, which quantifies the joint value of workforce transition outcomes and carbon sequestration in a single, decomposable metric.

The context is specific. The World Economic Forum projects 92 million jobs displaced globally by 2030, with the Brookings Institution identifying 6.1 million US workers lacking the adaptive capacity for technology-driven career transition. Simultaneously, AI companies produce substantial carbon externalities — approximately 105 million metric tons CO2 from US data centers in the twelve months ending August 2024 (Siddik et al.) — and are making large community investment commitments. Current remediation treats workforce displacement and environmental impact as separate problems, with no mechanism linking them and no counterfactual framework for evaluating joint outcomes. Anthropic's own Economic Index (March 2026) finds no evidence of significant AI-driven unemployment yet: this is precisely the moment to build measurement infrastructure, before displacement materializes rather than after.

This six-month empirical study will formally specify the welfare-tons metric, develop a constrained optimization model connecting corporate carbon budgets to restoration projects that employ displaced workers, and evaluate economic viability and distributional consequences using public datasets. Deliverables include a publishable empirical analysis, replication code, and policy brief.

---

## 2. Problem Statement

### 2.1 AI's Dual Externality: Workforce Displacement and Carbon Emissions

The AI industry produces two categories of externality that current policy and corporate programs address independently:

**Economic externality.** The World Economic Forum's *Future of Jobs Report 2025* projects 92 million jobs displaced and 170 million jobs created globally by 2030 — a net surplus of 78 million roles, but one whose distributional consequences depend on successful workforce transition (WEF, January 2025). SHRM Research finds 23.2 million US workers employed in occupations where 50%+ of tasks are automatable by current AI systems; the same report estimates approximately 9.2 million face elevated displacement risk, while the majority are expected to experience task-level transformation rather than job loss (SHRM, *AI in the Workplace 2025*). The Brookings Institution identifies 6.1 million workers — 86% of them women — as lacking the adaptive capacity required for technology-driven career transition (Brookings, *The Adaptation Gap: Who Gets Left Behind in AI Transitions*, 2025). The policy challenge is not primarily mass displacement but rather ensuring the 9.2 million most vulnerable workers are not left behind by a transition that benefits the majority.

**Ecological externality.** US data centers emitted approximately 105 million metric tons of CO2 in the twelve months ending August 2024, representing 2.18% of national emissions (Siddik, M.A.B., et al., "The rising environmental footprint of US data center electricity use," arXiv:2411.09786, 2024). The International Energy Agency estimates that data centres consumed around 415 TWh in 2024 (about 1.5% of global electricity demand), and projects electricity consumption in accelerated servers, driven mainly by AI adoption, to grow 30% annually through 2030 (IEA, *Energy and AI*, April 2025). A 2025 *Nature Sustainability* study finds the industry "unlikely to meet its net-zero aspirations by 2030 without substantial reliance on highly uncertain carbon offset and water restoration mechanisms" (Li et al., *Nature Sustainability*, 2025). These corporate carbon commitments create a funding mechanism — the question is whether it can be directed toward workforce transition outcomes.

**A note on timing.** Anthropic's own Economic Index (March 2026) finds no clear evidence that AI has yet increased unemployment, noting a large gap between theoretical exposure and actual labor market impact. This finding does not reduce the urgency of this research — it increases it. Measurement frameworks must be designed before displacement materializes, not after. The window for proactive infrastructure is now.

### 2.2 The Structural Gap

These externalities share the same accounting failure: the costs are real, the remediation mechanisms are disconnected, and no standard framework exists to evaluate whether spending on one generates co-benefits for the other.

| Mechanism | Addresses Ecological? | Addresses Economic? | Verified? |
|-----------|----------------------|---------------------|-----------|
| Carbon offset purchases | Partially | No | Weakly (see 2.3) |
| Corporate retraining programs | No | Partially | Rarely measured |
| Community investment pledges | Sometimes | Sometimes | No standard metric |
| Government job programs | No | Partially | Mixed evidence |

No existing framework jointly optimizes ecological restoration and workforce transition as a single allocation problem. An AI company fulfilling its carbon commitments and its community investment pledges does so through two separate bureaucracies, two separate budgets, and two separate accountability structures — forgoing the efficiency gains and compounding benefits available from integrated design.

### 2.3 Verification and Credibility

The voluntary carbon market faces documented credibility challenges — additionality failures, permanence risk, and social harm (Zhang et al., *Global Transitions*, 2025; ICVCM Core Carbon Principles, 2023) — that directly undermine AI companies' carbon commitments. Any workforce-linked carbon instrument must address these verification failures or inherit them.

### 2.4 Relevance to Anthropic's Stated Commitments

Anthropic has made a series of commitments directly relevant to this research:

In **July 2025**, Anthropic announced a **$1 million grant over three years to CMU's Scott Institute** for AI-powered grid modernization research (*Investing in Energy to Secure America's AI Future*, anthropic.com/news, July 2025).

In **November 2025**, Anthropic announced a **$50 billion infrastructure investment** creating approximately 800 permanent and 2,400 construction jobs (*Anthropic Invests $50 Billion in American AI Infrastructure*, anthropic.com/news, November 2025).

In **February 2026**, Anthropic announced additional commitments including: (1) 100% coverage of grid upgrade costs for new data center interconnection; (2) investment in local communities wherever new data centers are built, supporting job creation and environmental mitigation; and (3) water-efficient cooling technologies and partnerships with local leaders on environmental impact (*Covering Electricity Price Increases from Our Data Centers*, anthropic.com/news, February 2026).

These are significant, specific commitments. What is currently absent is a rigorous framework for evaluating whether community investment and environmental mitigation spending achieves joint outcomes. This research directly addresses that gap.

### 2.5 Related Frameworks and the Measurement Gap

Several existing standards address carbon co-benefits, but none provides a continuous composite welfare measure per ton of carbon combined with an optimization-based allocation mechanism:

- **Gold Standard SD VISta** certifies Sustainable Development co-benefits against 17 SDG indicators — but SDG tracking is project-defined, descriptive, and not fused into a composite tradeable unit. No normalized score per carbon ton; no algorithmic matching.
- **Verra CCB (Climate, Community & Biodiversity Standards)** certifies ecological and community benefits alongside carbon — but community benefit criteria are checklist-based (met/unmet), not scored on a continuous scale. No single co-benefit score; no matching mechanism.
- **Plan Vivo** requires livelihood indicators alongside carbon indicators — but targets smallholder farmers and indigenous communities within project areas, not displaced industrial workers. Livelihood indicators are project-specific and not normalized across projects.
- **Rockefeller Foundation Coal to Clean Credit Initiative (CCCI)** — most directly relevant initiative. Mandates Community Benefit Plans and just transition protections for affected coal workers. Demonstrates market appetite and policy will for carbon-transition-worker linkages. Critical gap: CCCI is an asset-specific methodology for coal plant retirement, not a generalizable cross-sector metric. It does not produce a normalized welfare-per-ton score; it does not include a matching algorithm.
- **ICVCM Core Carbon Principles (CCPs)** — CCP 10 requires sustainable development safeguards, but this is a minimum floor (do no harm), not a positive measurement framework. The ICVCM's own Continuous Improvement Work Program has an open item on social safeguards and sustainable development benefits, acknowledging this gap at the governance level.
- **UNEP/ILO "Decent Work in Nature-based Solutions" (December 2024)** — the most comprehensive recent analysis of employment in NbS. Documents 60–63 million current NbS workers globally, projects 32 million additional jobs possible by 2030 with targeted investment, and explicitly notes that "carbon as a proxy for co-benefits is insufficient." A research and policy document, not a tradeable metric. Identifies the problem space; welfare-tons proposes to operationalize the solution.
- **World Benchmarking Alliance Just Transition Indicators (February 2025)** — assesses company-level just transition policies, not project-level carbon credit co-benefits. A corporate compliance checklist, not a metric for carbon buyers evaluating specific projects.

No existing framework provides both a continuous composite welfare measure per ton of carbon and an optimization-based allocation mechanism. Existing platforms (Pachama, Carbonmark, Regen Network) optimize buyer-project matching on carbon quality tags but not on a joint objective function; existing standards measure carbon or welfare separately but never fuse them into a single composite index. Welfare-tons addresses this gap: (a) it denominates ecological and social outcomes in a single number compatible with standard carbon accounting (wt-CO2e units); (b) it explicitly targets the population of displaced workers, not "local communities" broadly; and (c) it provides a constrained optimization framework connecting corporate carbon budgets to dual-benefit projects. Welfare-tons is the first formalization of carbon sequestration and workforce transition as a single welfare-economic index, enabling direct comparison of heterogeneous remediation strategies.

---

## 3. Proposed Research

### 3.1 Research Questions

**Primary**: What are the labor market outcomes when corporate carbon budgets fund ecological restoration projects in regions with high AI displacement risk, and can these outcomes be measured using a composite welfare metric with axiomatic foundations?

**Secondary**:
- What is the current state of evidence on ecological restoration projects that simultaneously employ displaced or underemployed workers, and what are the unit economics?
- What allocation model design best connects corporate carbon budgets to community-level restoration projects given realistic constraints on geographic feasibility, workforce mobility, and verification confidence?
- To what extent do AI-displaced worker populations (concentrated in administrative, customer service, and data entry roles in urban metro areas) geographically overlap with ecological restoration opportunity (concentrated in rural coastal and forest zones)? What is the scale of the mismatch, and what institutional mechanisms — relocation support, remote oversight roles, training pipelines — could bridge it?
- What are the binding constraints on welfare-tons adoption — data availability, verification cost, workforce mobility, market pricing — and what is a realistic implementation pathway?
- What policy mechanisms would incentivize AI companies to adopt welfare-tons reporting alongside standard carbon accounting?

### 3.2 The Welfare-Tons Index: Formal Specification

The core contribution is the formal specification of a six-factor composite metric:

$$W = C \times E \times A \times B \times V \times P$$

| Symbol | Name | Domain | Interpretation |
|--------|------|--------|----------------|
| $W$ | Welfare-tons | $[0, +\infty)$ | Composite impact in wt-CO2e units |
| $C$ | Verified carbon (tCO2e) | $[0, +\infty)$ | Net CO2e sequestered after additionality adjustment |
| $E$ | Employment factor | $[0, E_{max}]$ | Job creation quality and density vs. regional baseline |
| $A$ | Community agency | $[0, 1]$ | Consent, local ownership, and self-determination score |
| $B$ | Biodiversity co-benefit | $[0.6, 1.7]$ | Restoration type quality (mangrove=1.5, monoculture=0.6) |
| $V$ | Verification confidence | $[0, 1]$ | Trust in underlying measurements |
| $P$ | Permanence factor | $[0, 1]$ | Risk-adjusted durability of sequestered carbon |

**Units**: Welfare-tons are denominated in "wt-CO2e" to distinguish them from raw carbon tons — analogous to QALYs in health economics, where the quality adjustment captures dimensions of value that the raw count ignores.

**The zero-kills-all enforcement mechanism**: Because the formula is multiplicative, a project that sequesters carbon but employs no workers ($E = 0$) scores zero welfare-tons. A project that sequesters carbon but displaces the community ($A = 0$) scores zero. A project with unverified claims ($V = 0$) scores zero. This design prevents greenwashing by any single high-performing dimension from masking deficits in others.

**Preliminary implementation**: A Python implementation of this specification (`welfare_tons.py`) is available in the project repository, with 300+ unit tests verifying the calculation across three project archetypes: commercial monoculture plantation (W = 14.4 wt-CO2e), community mangrove restoration (W = 26,938 wt-CO2e), and regenerative agroforestry (W = 9,948 wt-CO2e). The ratio between the community mangrove project and the commercial plantation — 1,871× — quantifies the joint value that carbon-only accounting ignores. This implementation demonstrates computational feasibility; the research will validate and calibrate the parameters against empirical data.

The research will:
- Formally specify the metric with axiomatic foundations (monotonicity: more carbon, employment, and verification increases welfare-tons; separability: each factor can be evaluated independently; normalization: a standard offset with no co-benefits has $E, A, B, V, P = 1.0$ except for actual permanence and verification scores)
- Conduct sensitivity analysis across plausible parameter ranges using data from Phase 1 and Phase 2
- Compare welfare-tons rankings to standalone carbon rankings and standalone jobs rankings on a portfolio of 20+ existing restoration projects
- Identify conditions under which joint optimization dominates or underperforms independent optimization

### 3.3 The Optimal Allocation Framework

The second contribution is a constrained optimization model for allocation. Inputs:
- Corporate carbon budgets (amounts, geographic preferences, reporting requirements, verification standards)
- Restoration project portfolios (carbon sequestration potential, labor intensity, location, verification infrastructure, biodiversity type)
- Workforce availability (displaced worker populations by location, skill profiles, mobility constraints, from BLS and Anthropic Economic Index data)

Output: An allocation that maximizes aggregate welfare-tons subject to budget constraints, geographic feasibility, and minimum verification confidence thresholds.

This is a constrained optimization problem with a single scalar objective (aggregate welfare-tons) and multiple constraints — not a multi-objective problem. The model implements weighted scalarization using standard open-source linear programming methods, sufficient for the scale of this empirical study (10–100 projects, 5–20 corporate buyers). The analysis will use publicly available data (Verra Registry, Gold Standard Impact Registry, BLS QCEW, WRI Atlas of Forest Landscape Restoration) to characterize the solution space. Comparison to naive allocation strategies (random, carbon-maximizing, jobs-maximizing) will establish whether welfare-ton optimization produces meaningfully different portfolios and heterogeneous treatment effects across worker subpopulations.

---

## 4. Methodology

### Phase 1: Systematic Review (Months 1–2)

**4.1 Literature review** of three intersecting bodies of work:
- Carbon offset verification methodology and documented failures (Verra VCS, Gold Standard, ICVCM Core Carbon Principles; Guardian/SourceMaterial 2023 REDD+ investigation; academic critiques in *Nature Climate Change*, *Global Environmental Change*)
- Workforce transition program outcomes (ILO Just Transition guidelines; US DOL Workforce Innovation and Opportunity Act outcomes data; academic evaluations of retraining effectiveness in *Journal of Labor Economics*, *ILR Review*)
- Ecological restoration labor economics (WRI restoration employment data; IUCN Bonn Challenge reporting; Civilian Conservation Corps historical analysis as dual-benefit precedent; academic unit economics in *Ecological Economics*, *Environmental Science & Policy*)

**4.2 Claude-assisted literature synthesis**: Phase 1 will use the Anthropic API (via the program's $5K credit) to systematically extract unit economics — cost per ton CO2, cost per worker-year, wage premium ratios — from 50+ academic papers and project reports. Claude will flag claims requiring verification and identify contradictory findings. All AI-assisted extraction will be human-verified before incorporation into the final analysis.

**4.3 Data compilation** of existing dual-benefit cases:
- Programs where restoration projects employ local or displaced workers (Brazil Atlantic Forest Restoration Pact, Great Green Wall Sahel initiative, USDA Conservation Reserve Program)
- Unit economics from published sources: cost per ton CO2, cost per worker-year, sequestration rates by ecosystem type
- Carbon market pricing data for premium (co-benefit certified) credits vs. standard credits from Ecosystem Marketplace and Sylvera

**Deliverable**: Structured literature review with quantified summary of dual-benefit project economics; annotated bibliography.

### Phase 2: Stakeholder Interviews (Months 2–4)

**4.4 Semi-structured interviews** with 8–12 organizations across three categories:

| Category | Target Organizations | Key Questions |
|----------|---------------------|---------------|
| Restoration implementers | WRI, Pachama, Regen Network, local cooperatives | Labor intensity, worker sourcing, skill requirements, verification costs |
| Carbon market intermediaries | Carbon Direct, Sylvera, Gold Standard | Credit quality assessment, co-benefit premium pricing, buyer requirements |
| Workforce development agencies | ILO Just Transition Centre, US DOL regional offices, local workforce boards | Displaced worker availability, retraining costs, placement outcomes |

**Interview protocol**: 45–60 minute semi-structured interviews conducted virtually (the PI is based internationally; virtual interviews reduce costs and expand geographic reach). Recorded with informed consent, coded using thematic analysis for: (a) dual-benefit feasibility, (b) unit economics, (c) verification challenges, (d) matching requirements, (e) policy barriers. If target organizations decline, interviews will be redirected to accessible equivalents (regional restoration cooperatives, independent carbon auditors, academic researchers in relevant fields).

**4.5 AI company interviews** (2–3 targets): Conversations with sustainability leads at AI companies with existing carbon commitments, exploring: current offset procurement process, appetite for integrated welfare-tons reporting, data they would be willing to co-develop.

**Research ethics**: All interviews will be conducted under informed consent protocols consistent with IRB Category 2 exemption criteria (research involving only interviews without sensitive topics that would normally require full review). Participants will be informed of recording, storage, and intended use. Data will be anonymized for publication unless participants explicitly consent to attribution.

**Deliverable**: Interview synthesis report with thematic analysis; stakeholder requirements document.

### Phase 3: Metric Development (Months 3–4)

**4.6 Formal specification** of welfare-tons v2.0:
- Axiomatic foundation: monotonicity, separability, normalization (formalized from the preliminary implementation)
- Parameter estimation from Phase 1 and Phase 2 data — replacing the current lookup-table defaults with empirically grounded estimates
- Sensitivity analysis: how do welfare-tons rankings change under different parameter weightings?
- Comparison study: rank a portfolio of 20+ existing restoration projects by (a) welfare-tons, (b) carbon-only, (c) jobs-only; analyze concordance and divergence

**4.7 Verification framework design**:
- Three-tier architecture: remote sensing (satellite multispectral and SAR), field measurement (stratified plot sampling, community-based monitoring), and community audit trail (not blockchain; structured record-keeping with trained local monitors)
- Cost estimation at different confidence levels
- Identification of existing verification infrastructure that can be leveraged

**4.8 Empirical analysis of geographic displacement-restoration overlap.** We use three public datasets to estimate geographic co-occurrence of AI-displaced worker populations and ecological restoration opportunities: (1) Felten et al. (2021, *Strategic Management Journal*) AI Geographic Exposure (AIGE) scores covering 3,219 US counties, which embed the Bartik shift-share methodology established by Acemoglu and Restrepo (2020, *Journal of Political Economy*) for robot exposure; (2) CarbonPlan OffsetsDB aggregating 1,858 US carbon offset projects across Verra, Gold Standard, Climate Action Reserve, and American Carbon Registry (527 forest/restoration projects, 296.7 million credits issued); and (3) BLS Quarterly Census of Employment and Wages (QCEW) for county-level employment controls. We supplement occupational exposure with Eloundou et al. (2023, arXiv:2303.10130) GPTs-are-GPTs scores covering 923 occupations. Using OLS regression with state fixed effects and heteroskedasticity-robust standard errors, we estimate:

$$Y_c = \beta_0 + \beta_1 \cdot \text{AI\_Exposure}_c + \beta_2 \cdot \text{Restoration}_c + \beta_3 \cdot (\text{AI\_Exposure} \times \text{Restoration})_c + X_c'\gamma + \delta_s + \varepsilon_c$$

where $Y_c$ is potential welfare-tons per capita in area $c$, $X_c$ are controls (unemployment rate, population density, industry concentration, goods-producing employment share), and $\delta_s$ are state fixed effects. We exploit variation in pre-existing occupational composition across counties (the Bartik shift-share instrument) as a source of plausibly exogenous variation in AI exposure, following the identification strategy established by Acemoglu and Restrepo (2020). The coefficient $\beta_3$ on the interaction term tests whether areas with both high AI displacement risk and high restoration suitability have disproportionately higher welfare-tons potential — the core geographic feasibility question for the allocation model.

A preliminary analysis pipeline is already implemented and running on real data. County-level AIGE scores range from −6.11 to +4.20 (z-scored), with highest exposure in the Northeast corridor (Connecticut 0.91, New Jersey 0.71, New York 0.69) and lowest in rural Great Plains counties. Initial state-level correlation between mean AIGE and carbon project density is near zero (r = −0.06, n = 41), suggesting that AI displacement and restoration opportunity are geographically independent — neither co-located nor systematically separated. This null finding motivates the research: if overlap is not automatic, the matching algorithm that identifies viable pairings becomes essential rather than redundant. The funded research will extend this to county-level spatial analysis using Bivariate Moran's I statistics (following Lim, Aklin & Frank, 2023, on fossil fuel employment-to-green jobs geographic mismatch), USDA Conservation Reserve Program enrollment data, and NLCD forest cover by county.

**Deliverable**: Technical specification of welfare-tons metric v2.0 with sensitivity analysis, verification framework, and econometric analysis of displacement-restoration geographic overlap.

### Phase 4: Allocation Model and Economic Viability Analysis (Months 4–5)

**4.9 Model design and implementation**:
- Constrained optimization formulation: maximize aggregate welfare-tons; constraints: budget, geography, workforce availability, minimum verification confidence
- Implementation in Python using public data; replication code open-sourced
- Benchmarked against three naive baselines: random allocation, carbon-maximizing allocation, employment-maximizing allocation
- Sensitivity analysis of allocation outcomes under parameter perturbation, with counterfactual scenarios

**4.10 Economic viability analysis**:
- At what carbon price does dual-benefit restoration become cost-competitive with standard offsets?
- What premium are buyers willing to pay for verified social co-benefits? (From Phase 2 interview data and published market data)
- What is the minimum corporate carbon budget that makes algorithmic matching cost-effective vs. manual brokerage?

**Deliverable**: Replication code for constrained optimization model with documentation; economic viability analysis.

### Phase 5: Synthesis and Policy (Month 6)

**4.11 Feasibility assessment** under binding constraints.

**4.12 Policy brief** with concrete recommendations for: AI companies implementing community investment pledges; carbon market standards bodies considering co-benefit frameworks; workforce development agencies exploring ecological transition pathways.

**Deliverable**: Publishable empirical analysis (target journal: *Ecological Economics* or *One Earth*); 2–3 page policy brief.

---

## 5. Qualifications

### 5.1 Principal Investigator

**John Shrader** is an independent researcher with demonstrated competence in novel metric design, multi-system empirical validation, and statistical rigor across two active research tracks:

**Quantitative metric design**: Developed a geometric measurement (R_V, the Participation Ratio contraction in Value matrix column space) validated across 6 architectures with ~400 measurements. Causal validation via activation patching: Cohen's d = −2.26; FDR-corrected 32/39 tests significant at α = 0.05; AUROC = 0.909. This work — designing a composite metric from first principles, specifying its axiomatic properties, validating across heterogeneous systems, and conducting sensitivity analysis — is directly analogous to the welfare-tons specification proposed here. Targeting COLM 2026.

**Large-n empirical methodology**: Over 200 trials across four frontier models documenting behavioral phase transitions with 90–95% replication rate. Demonstrates competence in cross-system comparison and systematic measurement of phenomena that lack obvious quantification.

**Methodological transfer**: The core question — "what mathematical object correctly captures this phenomenon, and how do we know we've measured it?" — transfers directly from computational research to applied welfare economics. The statistical toolkit (effect size estimation, FDR correction, cluster-robust standard errors, counterfactual analysis) is the same.

### 5.2 Technical Capacity

- Proficient in Python for statistical computing and optimization, with demonstrated implementations (`welfare_tons.py`, 300+ passing tests)
- Statistical analysis: Effect size estimation, FDR correction, confidence intervals, non-parametric methods — applied in R_V research, applicable to welfare-tons sensitivity analysis
- Data collection and synthesis: Experience managing multi-source data across heterogeneous experimental conditions
- Computational infrastructure: M3 Pro MacBook for algorithm development; RunPod GPU access for heavier workloads

### 5.3 Advisory Support

The PI has no formal economics training. This is the application's most significant constraint, and it is addressed directly:

**Budget line for paid expert review**: $3,000 is allocated for two paid review sessions (5–10 hours each) with economists specializing in environmental economics or welfare measurement. Target disciplines: welfare economics (metric specification review), environmental economics (carbon market expertise), labor economics (workforce transition validation). Target institutions: RFF (Resources for the Future), Becker Friedman Institute (University of Chicago, Anthropic's named academic partner), Urban Institute Labor and Employment Initiative.

**Advisory targets for unpaid engagement**: labor economists with published work on AI-and-employment (to be approached via Phase 2 interview contacts); one practitioner advisor from a workforce development organization (HR director at a major employer, or workforce nonprofit director in a data center jurisdiction); one policy analyst from Brookings AI Initiative or RAND Labor and Population.

**Letters of support**: The PI will approach 2–3 organizations during Phase 2 outreach for letters confirming interest in using the welfare-tons metric — specifically, one city government in a data center jurisdiction and one workforce development agency. These letters are not yet secured; if obtained before submission, they will be provided as supplementary materials.

The PI's metric-design competence is demonstrated; the economics domain knowledge is the gap. The research design addresses this systematically: Phase 1 builds literature expertise, Phase 2 interviews build practitioner expertise, and paid expert review at the specification stage provides peer-level validation before publication.

---

## 6. Budget

| Category | Amount | Justification |
|----------|--------|---------------|
| **PI time** (6 months, part-time) | $18,000 | 12 hours/week at $60/hr, covering research design, interviews, econometric analysis, and writing |
| **Expert review** | $3,000 | 2 paid review sessions with environmental/welfare economists (5–10 hrs each at $150–300/hr) |
| **Travel** | $3,000 | 1–2 trips for in-person stakeholder engagement if virtual access proves insufficient; otherwise redirected to conference presentation at economics venue |
| **Compute and data** | $3,000 | Cloud compute for allocation model development and testing; data access fees (Ecosystem Marketplace, Sylvera pricing data) |
| **Research assistance** | $3,000 | Transcription, interview coding support, literature review assistance |
| **Publication and dissemination** | $2,000 | Open access publication fees; conference presentation |
| **Contingency** | $3,000 | Unanticipated expenses, extended data access, additional interviews |
| **Total** | **$35,000** | |

**Claude API credit ($5,000)**: Used for: (1) systematic literature extraction in Phase 1 — identifying unit economics across 50+ papers; (2) thematic coding of interview transcripts in Phase 2; (3) sensitivity analysis of welfare-tons parameter space in Phase 3; (4) scenario generation for allocation model testing in Phase 4. All AI-assisted analysis will be human-verified and documented with the prompts and verification procedures used.

**Note on budget level**: This budget is consistent with Anthropic's $10K–$50K range for exploratory empirical studies and supports a solo PI working part-time over 6 months.

---

## 7. Expected Outcomes

### 7.1 Research Outputs

1. **Publishable empirical analysis** (target: *Ecological Economics*, *One Earth*, or equivalent): "Measuring Labor Market Outcomes of Corporate Carbon Investment: Welfare-Tons as a Joint Workforce-Environmental Impact Metric." Containing: systematic review, metric specification, sensitivity analysis, interview synthesis, allocation model design, economic viability analysis.

2. **Replication code and data** (GitHub repository): Python implementation of the constrained optimization model with documentation and test data, enabling independent replication and extension.

3. **Policy brief** (2–3 pages): Concrete recommendations for AI companies, carbon market standards bodies, and workforce development agencies. Specifically addresses implementation pathways for companies with existing community investment and environmental commitments.

4. **Qualitative analysis of implementation barriers**: Thematic analysis from 8–12 semi-structured interviews documenting feasibility constraints, adoption conditions, and institutional requirements for dual-benefit carbon credit standards.

### 7.2 Practical Value

**For AI companies** (including Anthropic): A framework for evaluating whether community investment spending achieves joint ecological-economic outcomes, rather than siloed compliance with separate commitments. Concrete guidance on how to structure carbon offset procurement to simultaneously generate workforce transition benefits.

**For carbon market development**: Evidence on whether co-benefit premiums in voluntary markets are sufficient to sustain dual-benefit restoration projects, and what verification standards would be needed.

**For workforce policy**: Evidence on the feasibility of ecological restoration as a workforce transition pathway, including skill requirements, wage levels, and geographic match between displaced worker populations and restoration opportunity areas.

**For Anthropic's Economic Futures Program**: A novel research direction connecting AI's ecological externalities to its economic externalities — a connection the existing research portfolio has not yet formalized. The welfare-tons framework operationalizes "responsible development" beyond safety research: it asks what corporate mechanisms can convert AI's negative externalities into measurable community benefit.

### 7.3 What This Research Does Not Claim

This is an exploratory empirical study, not a platform launch. It will not:
- Build a production matching platform or execute actual restoration projects
- Make claims about AI consciousness, alignment, or the PI's other research tracks (these are entirely separate and not relevant here)
- Solve the carbon verification problem (it will characterize verification requirements for dual-benefit projects)
- Produce definitive welfare-tons parameter values (it will specify the metric framework and identify parameter estimation requirements for subsequent empirical calibration)
- Demonstrate that welfare-tons adoption will occur (it will assess feasibility and identify the conditions under which adoption is viable)

---

## 8. Timeline

| Month | Activity | Deliverable |
|-------|----------|-------------|
| 1 | Literature review; data compilation; refine welfare-tons v2.0 spec | Annotated bibliography; updated metric specification |
| 2 | Literature review completion; stakeholder outreach; begin interviews | Structured literature review draft |
| 3 | Stakeholder interviews (4–6); metric parameter estimation | Interview notes; metric framework with empirical parameters |
| 4 | Remaining interviews (4–6); sensitivity analysis; begin algorithm design | Interview synthesis; sensitivity analysis report |
| 5 | Allocation model; economic viability analysis | Working model; viability report |
| 6 | Synthesis; paper drafting; policy brief | All deliverables complete |

---

## 9. Alignment with Anthropic's Mission and Commitments

### 9.1 Direct Program Alignment

**Managing Societal Impacts**: The welfare-tons framework directly addresses how to evaluate whether corporate social investment achieves joint outcomes in contexts where AI creates both ecological and economic externalities.

**Transition Support**: The allocation model is a tool for directing carbon budgets toward community-led restoration projects that create stable employment for workers facing technological displacement. This is not a claim that restoration jobs are equivalent to AI-augmented knowledge work — they are different, and the research will characterize the difference honestly. The contribution is the measurement infrastructure that makes the comparison explicit and the choice deliberate.

**International Impacts**: The restoration-as-transition framework applies globally. The geographic overlap between AI-driven displacement of outsourced service work (concentrated in Southeast Asia, South Asia, Latin America) and ecological restoration opportunity (concentrated in the same regions) is one of the feasibility questions this research will empirically assess.

**Value Creation and New Industries**: Ecological restoration funded by AI carbon budgets and staffed by workers from displaced industries is a new industry category. This research designs the accounting infrastructure it requires.

### 9.2 Supporting Anthropic's February 2026 Commitments

Anthropic has pledged to "invest in local communities wherever it builds new data centers, while striving to address any environmental impact its facilities might have." This research provides:

- **A measurement framework** for evaluating whether community investment achieves joint ecological-economic outcomes (welfare-tons vs. siloed metrics)
- **An allocation methodology** for directing community investment to projects that simultaneously address environmental mitigation and local employment
- **Verification standards** appropriate for dual-benefit claims, addressing the greenwashing risk that undermines corporate environmental commitments
- **Policy recommendations** specifically designed for companies at Anthropic's stage of commitment

### 9.3 Complementing Existing Investments

Anthropic's $1 million to CMU's Scott Institute focuses on AI-powered grid modernization — the supply side of AI's energy problem. This research addresses the remediation side: once energy is consumed and carbon emitted, how should the resulting externality be addressed in a way that also generates workforce transition benefits? The two investments address different parts of the same system.

### 9.4 Connection to the Anthropic Economic Index

Anthropic's Economic Index (January and March 2026 releases) tracks AI usage patterns across occupations, establishing which roles face high theoretical exposure to automation. The welfare-tons metric is designed to function as a welfare-denominated output layer for longitudinal datasets of exactly this type: converting activity exposure data into welfare-adjusted impact measures that track distributional outcomes over time. Where the Economic Index measures what AI touches, welfare-tons measures what communities receive in return. The two instruments are complementary at the design level; this research will evaluate how welfare-tons reporting could interface with, extend, or be validated against Economic Index occupational exposure data.

### 9.5 The Measurement Argument

Anthropic's stated mission centers on responsible AI development. This research operationalizes "responsible" beyond safety research: it asks whether rigorous measurement can convert aspirational pledges into accountable commitments. A welfare-ton figure that can be audited, decomposed, and compared is different in kind from a community investment pledge that cannot. This research designs the difference.

The feasibility study is designed to produce the research infrastructure necessary for a subsequent implementation study that would pilot the welfare-tons metric in 2–3 jurisdictions receiving AI infrastructure investment — specifically, jurisdictions receiving significant AI infrastructure investment where corporate community benefit obligations create natural pilot conditions. Phase 1 findings will be disseminated to relevant state workforce commissions and labor departments alongside the academic publication and policy brief.

---

## 10. References

Anthropic. (2026, March). "Labor market impacts of AI: A new measure and early evidence." anthropic.com/research/labor-market-impacts. *(Anthropic Economic Index, March 2026 release — cited for absence of significant unemployment impact so far.)*

Anthropic. (2026, February). "Covering electricity price increases from our data centers." anthropic.com/news/covering-electricity-price-increases.

Anthropic. (2025, November). "Anthropic invests $50 billion in American AI infrastructure." anthropic.com/news/anthropic-invests-50-billion-in-american-ai-infrastructure.

Anthropic. (2025, July). "Investing in energy to secure America's AI future." anthropic.com/news/investing-in-energy-to-secure-america-s-ai-future.

Brookings Institution. (2025). Warshaw, C., and Tomer, A. "The Adaptation Gap: Who Gets Left Behind in AI Transitions." Brookings Metropolitan Policy Program, Washington, DC. *(6.1 million workers lacking adaptive capacity; 86% women.)*

Acemoglu, D., and Restrepo, P. (2020). "Robots and Jobs: Evidence from US Labor Markets." *Journal of Political Economy* 128(6), 2188–2244. *(Establishes Bartik shift-share methodology for estimating local labor market effects of technology adoption; one additional robot per thousand workers reduces employment-to-population ratio by 0.2 pp.)*

Bureau of Labor Statistics. (2024). Quarterly Census of Employment and Wages. US Department of Labor. bls.gov/cew/.

Eloundou, T., Manning, S., Mishkin, P., and Rock, D. (2023). "GPTs are GPTs: An Early Look at the Labor Market Impact Potential of Large Language Models." arXiv:2303.10130. *(AI occupational exposure scores for 923 O*NET-SOC occupations using human and GPT-4 annotation; finds ~80% of US workers have at least 10% of tasks exposed to LLMs.)*

Ecosystem Marketplace. (2025). "State of the Voluntary Carbon Market 2025." Forest Trends Association. *(VCM transaction value $535M in 2024, down from $723M in 2023.)*

Felten, E., Raj, M., and Seamans, R. (2021). "Occupational, industry, and geographic exposure to artificial intelligence: A novel dataset and its potential uses." *Strategic Management Journal* 42(12), 2195–2217. github.com/AIOE-Data/AIOE. *(AIOE scores for 774 SOC occupations; the canonical AI occupational exposure measure used in subsequent labor economics research.)*

Goldman Sachs Equity Research. (2024, April). "Generational Growth: AI, Data Centers and the Coming US Power Demand Surge." *(60% of new capacity from natural gas and fossil fuels.)*

IEA. (2025, April). *Energy and AI*. International Energy Agency, Paris. https://www.iea.org/reports/energy-and-ai. *(Global data centres consumed around 415 TWh in 2024, or about 1.5% of world electricity demand; electricity consumption in accelerated servers, mainly driven by AI adoption, is projected to grow 30% annually through 2030.)*

ILO. (2023). "Guidelines for a just transition towards environmentally sustainable economies and societies for all" (revised edition). International Labour Organization, Geneva. *(Original 2015; revised 2023.)*

ILO. (2024). "Carbon markets and just transition: Opportunities and risks for workers and communities." International Labour Organization, Working Paper. ilo.org/publications. *(Examines workforce implications of voluntary carbon markets; identifies labor standard gaps in existing credit frameworks.)*

UNEP / ILO / IUCN. (2024). *Decent Work in Nature-based Solutions 2024: Unlocking jobs through investment*. United Nations Environment Programme, International Labour Organization, International Union for Conservation of Nature. Published December 2024. unep.org/resources/report/decent-work-nature-based-solutions-2024. *(Documents 60–63 million current NbS workers globally; projects 32 million additional jobs by 2030 with targeted investment; notes that carbon is currently used as a proxy for co-benefits, identifying the measurement gap welfare-tons proposes to fill.)*

World Benchmarking Alliance. (2025). "Just Transition Methodology 2025." worldbenchmarkingalliance.org. Published February 2025. *(Introduces Just Transition Indicators JTI 01–03 for corporate-level policy compliance assessment; provides company-level benchmarking, not project-level carbon credit co-benefit measurement.)*

Rockefeller Foundation. (2025). "Coal to Clean Credit Initiative: Methodology and Community Benefit Plan Requirements." Verra-approved methodology, 2025. rockefellerfoundation.org/initiatives/coal-to-clean-credits. *(Demonstrates market appetite and policy infrastructure for linking carbon credits to just transition outcomes for coal workers; validates the problem space while remaining asset-specific and non-generalizable to NbS contexts.)*

ICVCM. (2023). "Core Carbon Principles." Integrity Council for the Voluntary Carbon Market. icvcm.org/core-carbon-principles.

SHRM. (2025). *AI in the Workplace 2025*. Society for Human Resource Management. *(23.2 million US workers in occupations with 50%+ automatable tasks; ~9.2 million at elevated displacement risk; report conclusion emphasizes task-level transformation over net job loss.)*

Siddik, M.A.B., et al. (2024). "The rising environmental footprint of US data center electricity use." arXiv:2411.09786. *(105 million metric tons CO2, twelve months ending August 2024.)*

Li, P., et al. (2025). "AI server deployment and net-zero feasibility." *Nature Sustainability*. doi.org/10.1038/s41893-025-01681-y. *(Projects 24–44 million tCO2e per year and 731–1,125 million m³ water annually from US AI servers 2024–2030; concludes industry unlikely to meet net-zero without substantial offset and restoration mechanisms.)*

Brancalion, P.H.S., et al. (2022). "Ecosystem restoration job creation potential in Brazil." *People and Nature* (British Ecological Society / Wiley). DOI: 10.1002/pan3.10370. *(Measures 0.42 direct jobs per hectare in active forest restoration; projects 1.0–2.5 million direct jobs from Brazil's 12-million-hectare NDC target.)*

Griscom, B.W., et al. (2017). "Natural climate solutions." *PNAS* 114(44), 11645–11650. *(Establishes natural climate solutions can provide >1/3 of cost-effective climate mitigation needed by 2030; identifies biodiversity, water, air quality, and soil co-benefits as economic incentives for NCS investment even without a carbon price — the theoretical parent of the welfare-ton's co-benefit framing.)*

Sanchirico, J.N., and Springborn, M. (2022). "On the optimal management of environmental stock externalities." *PNAS* 119(26). doi.org/10.1073/pnas.2202679119. *(Demonstrates that independent optimization of environmental externalities by separate market actors produces a suboptimal equilibrium; provides mathematical foundation for joint optimization instruments such as the welfare-ton composite metric.)*

Sylvera. (2024). *Carbon Credit Quality Ratings: Annual Market Analysis*. sylvera.com. *(Carbon credit quality and greenwashing analysis.)*

Lim, J., Aklin, M., and Frank, M.R. (2023). "Location is a major barrier for transferring US fossil fuel employment to green jobs." *Nature Communications* 14, 5711. doi:10.1038/s41467-023-41133-9. *(Demonstrates geographic mismatch between fossil fuel employment and renewable energy opportunity; establishes Bivariate Moran's I methodology for spatial co-occurrence analysis of displacement and transition employment.)*

World Economic Forum. (2025, January). *The Future of Jobs Report 2025*. Geneva. *(92 million jobs displaced by 2030.)*

World Resources Institute. (2018). *Roots of Prosperity: The Economics and Finance of Restoring Land*. Washington, DC. *(Restoration employment and funding gap analysis.)*

Zhang, Y., et al. (2025). "Governance failures in voluntary carbon markets: A systematic review." *Global Transitions*, 7, 45–63. *(Systemic failures including additionality, permanence, and social harm.)*

---

## Appendix A: Relationship to PI's Other Research

The principal investigator has two other active research tracks: mechanistic interpretability of transformer self-reference (R_V metric); and behavioral phase transitions in frontier LLMs (URA/Phoenix Protocol). These are distinct from the present proposal in subject matter, methodology, and target audience. This proposal involves no consciousness research, no mechanistic interpretability, and no claims about AI internal states. It is a welfare economics empirical study.

The connection is methodological: designing a novel composite metric, validating it across heterogeneous systems, conducting sensitivity analysis, and being honest about what can and cannot be claimed from the data. That pipeline transfers directly.

## Appendix B: Welfare-Tons Worked Example — v2.0 Formula

Using the v2.0 specification ($W = C \times E \times A \times B \times V \times P$):

**Option A: Commercial monoculture plantation**
| Factor | Value | Notes |
|--------|-------|-------|
| C | 2,000 tCO2e | Gross sequestration, additionality-adjusted |
| E | 0.01 | Minimal employment: 2 workers, $0.98 wage ratio |
| A | 0.60 | Community consulted but not co-owning |
| B | 0.80 | Monoculture (lookup table floor) |
| V | 0.90 | Satellite only, no ground truth |
| P | 0.80 | Moderate permanence (25-year horizon) |
| **W** | **14.4 wt-CO2e** | |

**Option B: Community mangrove restoration (displaced aquaculture workers)**
| Factor | Value | Notes |
|--------|-------|-------|
| C | 1,500 tCO2e | Lower per-dollar yield than monoculture |
| E | 5.00 | 30 workers, 1.8× wage premium, skill acquisition |
| A | 0.95 | Community-led, co-ownership structure |
| B | 1.50 | Mangrove (lookup table maximum) |
| V | 0.95 | Satellite + ground truth + community audit trail |
| P | 0.85 | High permanence (mangrove durability, monitoring) |
| **W** | **26,938 wt-CO2e** | 1,871× higher than Option A |

Option A sequesters 33% more carbon per dollar. Option B produces 1,871× more welfare-tons. Whether the tradeoff is worthwhile depends on the funder's objectives — currently, no metric makes the comparison explicit. Welfare-tons makes it calculable.

A Python implementation verifying this calculation is available in the project repository (`welfare_tons.py`, 300+ passing tests).

**External empirical grounding**: The employment density input used in the mangrove archetype above (0.25 jobs per hectare) is conservative relative to the peer-reviewed benchmark. Brancalion et al. (2022) measured **0.42 direct jobs per hectare** in active forest restoration across the Brazilian Atlantic Forest biome (*People and Nature*, DOI: 10.1002/pan3.10370). Scaling to Brazil's NDC target of 12 million hectares would generate 1.0–2.5 million direct jobs. Phase 3 of this research will calibrate the employment density parameter against country- and biome-specific data, replacing the provisional figures with empirically validated ranges.

**Market premium evidence**: Sylvera's 2024–2025 pricing data shows that ARR projects with a verified co-benefit score of 5 command approximately $25/credit, versus $10.50 for score 3 — a $14.50/credit premium for verified social and ecological co-benefits. A welfare-ton standard that credibly anchors both carbon sequestration and workforce transition outcomes would qualify projects for the highest co-benefit tier, generating the revenue premium required to sustain the incremental cost of workforce integration and monitoring.

## Appendix C: Data Sources for Matching Algorithm Prototype

| Data Source | Variables | Access |
|-------------|-----------|--------|
| Verra Registry | Project types, locations, sequestration volumes, vintages | Public |
| Gold Standard Impact Registry | Co-benefit reporting, SDG linkages | Public |
| BLS Quarterly Census of Employment and Wages | County-level employment by industry and geography | Public |
| SHRM AI Impact Survey | AI-affected occupation categories | Published report |
| Anthropic Economic Index | AI usage patterns by occupation | Program access (Hugging Face) |
| WRI Atlas of Forest Landscape Restoration | Restoration opportunity by geography | Public |
| ILO ILOSTAT | Workforce data by country, sector, demographics | Public |
| Ecosystem Marketplace | Carbon credit pricing, premium analysis | Partial public |

---

*Submitted to the Anthropic Economic Futures Research Awards Program, March 2026.*
