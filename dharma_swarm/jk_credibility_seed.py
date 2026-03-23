"""
JK Credibility Seed — Semantic intelligence for the swarm.

This file encodes the findings from the Ruthless Critique (2026-03-21)
as structured data that agents can query during task planning.

When an agent is working on JK/welfare-tons tasks, it should read this
seed to understand:
1. What the credibility gaps are
2. What the competitive landscape looks like
3. What anti-patterns to avoid
4. What the priority order is

This is NOT a config file. It's operational intelligence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Credibility Gaps (ordered by severity)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CredibilityGap:
    id: str
    severity: str  # "critical", "high", "medium", "low"
    description: str
    evidence: str
    resolution: str
    phase: int  # which mission phase resolves this
    owner_team: str  # which sub-team owns this


CREDIBILITY_GAPS: tuple[CredibilityGap, ...] = (
    CredibilityGap(
        id="GAP-001",
        severity="critical",
        description="Internal contradiction: DBC proof (27,825 wt) vs Eden Kenya proof (588.5 wt) in same artifact pipeline",
        evidence="Worker artifact claims DBC at 27,825 wt-CO2e/yr but canonical file is Eden Kenya at 588.5 wt-CO2e/yr",
        resolution="Reconcile: determine which is canonical, archive the other, add provenance hashing",
        phase=0,
        owner_team="jk-truth",
    ),
    CredibilityGap(
        id="GAP-002",
        severity="critical",
        description="No public existence: zero GitHub repos, zero websites, zero blog posts, zero talks",
        evidence="118K lines of code and nobody outside knows it exists",
        resolution="Public GitHub repo + welfare-tons.org + README",
        phase=1,
        owner_team="jk-publish",
    ),
    CredibilityGap(
        id="GAP-003",
        severity="critical",
        description="Proof relies on non-public evidence: Eden payment records, payroll audit, FPIC package, Salesforce CRM, WhatsApp group",
        evidence="5+ citations in jk_welfare_ton_proof.md point to private/internal sources",
        resolution="Replace private citations with public sources or flag as UNVERIFIED",
        phase=0,
        owner_team="jk-truth",
    ),
    CredibilityGap(
        id="GAP-004",
        severity="high",
        description="Unverified citations: KFS Annual Report 2023 deforestation rate 3.8%/yr, MAFRI biodiversity survey 17 species",
        evidence="Could not verify from public web sources",
        resolution="Find public URL or DOI for each, or mark UNVERIFIED in proof",
        phase=0,
        owner_team="jk-truth",
    ),
    CredibilityGap(
        id="GAP-005",
        severity="high",
        description="No uncertainty quantification: all factors are single-point estimates",
        evidence="Proof uses exact values (C=130.24, E=4.485) without confidence intervals",
        resolution="Add Monte Carlo or at minimum sensitivity ranges for each factor",
        phase=2,
        owner_team="jk-critic",
    ),
    CredibilityGap(
        id="GAP-006",
        severity="high",
        description="Only 1 project scored: cannot demonstrate metric differentiates",
        evidence="Eden Kenya is the only proof. Need 20+ to show high-agency > low-agency",
        resolution="Score 20+ projects across diverse categories",
        phase=2,
        owner_team="jk-publish",
    ),
    CredibilityGap(
        id="GAP-007",
        severity="high",
        description="Formula weights are arbitrary: no derivation for why multiply, not add",
        evidence="W = C x E x A x B x V x P chosen without calibration study",
        resolution="Adversarial analysis + sensitivity analysis + recalibration proposal",
        phase=2,
        owner_team="jk-critic",
    ),
    CredibilityGap(
        id="GAP-008",
        severity="high",
        description="No external review: zero outside experts have evaluated the metric",
        evidence="Self-audit only. Proof says 'SUBMISSION READY' without peer review",
        resolution="Commission 3 paid external reviews",
        phase=3,
        owner_team="jk-market",
    ),
    CredibilityGap(
        id="GAP-009",
        severity="high",
        description="No demand validation: no buyer has said they would pay for welfare-ton scores",
        evidence="Demand is inferred from market trends, not from buyer conversations",
        resolution="10 buyer/registry/developer interviews",
        phase=3,
        owner_team="jk-market",
    ),
    CredibilityGap(
        id="GAP-010",
        severity="medium",
        description="No standards crosswalk: welfare-tons not mapped to GS, Verra, ICVCM",
        evidence="Grant mentions these exist but doesn't benchmark against them",
        resolution="Full crosswalk document for each major standard",
        phase=2,
        owner_team="jk-standards",
    ),
    CredibilityGap(
        id="GAP-011",
        severity="medium",
        description="No community voice: metric claims to measure welfare without community input",
        evidence="DBC/Eden proofs computed from desk research only",
        resolution="Community feedback protocol + at least 3 ground-truth validations",
        phase=5,
        owner_team="jk-field",
    ),
    CredibilityGap(
        id="GAP-012",
        severity="medium",
        description="Western-centric: all targets are US/EU funders, English-language registries",
        evidence="No scoring of Chinese CETS projects, Indian projects, SE Asian projects",
        resolution="Score projects in 3+ non-Western markets",
        phase=5,
        owner_team="jk-field",
    ),
    CredibilityGap(
        id="GAP-013",
        severity="medium",
        description="Grant framing is grandiose: $1.2M Google.org ask from solo researcher",
        evidence="No institutional affiliation, no publications, no prior grants",
        resolution="Defer Google.org. Submit Anthropic $35K first. Build track record.",
        phase=1,
        owner_team="jk-publish",
    ),
    CredibilityGap(
        id="GAP-014",
        severity="low",
        description="No academic co-author for preprint",
        evidence="Solo author = lower credibility with reviewers",
        resolution="Find ecological economics / environmental policy co-author",
        phase=3,
        owner_team="jk-publish",
    ),
)


# ---------------------------------------------------------------------------
# Competitive Landscape
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Competitor:
    name: str
    what_they_do: str
    funding: str
    our_advantage: str
    our_disadvantage: str
    threat_level: str  # "direct", "adjacent", "background"


COMPETITORS: tuple[Competitor, ...] = (
    Competitor(
        name="Sylvera",
        what_they_do="Carbon credit ratings using satellite + ML",
        funding="$96M raised",
        our_advantage="They don't score workforce impact at all",
        our_disadvantage="They have customers, team, brand, and data pipeline",
        threat_level="adjacent",
    ),
    Competitor(
        name="BeZero Carbon",
        what_they_do="Carbon credit ratings with 8-factor framework",
        funding="$50M+ raised",
        our_advantage="No employment/agency factors in their framework",
        our_disadvantage="Institutional credibility, corporate clients",
        threat_level="adjacent",
    ),
    Competitor(
        name="Calyx Global",
        what_they_do="Carbon credit ratings backed by Moody's",
        funding="Moody's-backed",
        our_advantage="No social/workforce dimension",
        our_disadvantage="Moody's brand, regulatory relationships",
        threat_level="adjacent",
    ),
    Competitor(
        name="Carbonmark",
        what_they_do="Digital carbon credit marketplace",
        funding="Funded",
        our_advantage="Marketplace, not ratings — different layer",
        our_disadvantage="They have the infrastructure we'd build on top of",
        threat_level="background",
    ),
    Competitor(
        name="Gold Standard SDG Impact Tool",
        what_they_do="SDG reporting for carbon projects",
        funding="NGO (established)",
        our_advantage="Their tool reports SDGs, doesn't create a tradeable unit",
        our_disadvantage="They ARE the standard — we need them, not compete",
        threat_level="direct",
    ),
    Competitor(
        name="Verra CCB Standards",
        what_they_do="Climate, Community & Biodiversity Standards for carbon projects",
        funding="NGO (established)",
        our_advantage="CCB is qualitative; welfare-tons is quantitative",
        our_disadvantage="CCB is already adopted by thousands of projects",
        threat_level="direct",
    ),
    Competitor(
        name="UNEP/ILO Decent Work in NBS",
        what_they_do="Framework for decent work in nature-based solutions (Dec 2024)",
        funding="UN system",
        our_advantage="Framework only, no measurement tool or tradeable unit",
        our_disadvantage="UN endorsement = instant credibility we don't have",
        threat_level="adjacent",
    ),
)


# ---------------------------------------------------------------------------
# Anti-Patterns (things the swarm must NOT do)
# ---------------------------------------------------------------------------

ANTI_PATTERNS: tuple[str, ...] = (
    "Do NOT call the system 'planetary palantir' to external audiences",
    "Do NOT submit Google.org $1.2M application before: publication + co-author + public tool + 20 scored projects",
    "Do NOT claim 'SUBMISSION READY' on any artifact that has unverified citations or gate failures",
    "Do NOT score projects from desk research only — at least 3 need ground-truth community input",
    "Do NOT let swarm agents generate contradictory proofs without truth-ledger reconciliation",
    "Do NOT build marketplace before diligence tool — matching without trust is theater",
    "Do NOT expand formula without adversarial stress-testing",
    "Do NOT write more architecture documents — write code, papers, and emails",
    "Do NOT confuse internal swarm sophistication with external credibility",
    "Do NOT present welfare-tons as a standard before it has external validation",
    "Do NOT apply for grants claiming capabilities that aren't publicly demonstrable",
)


# ---------------------------------------------------------------------------
# Priority Queue (what to do next, in order)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PriorityAction:
    rank: int
    action: str
    gate: str
    phase: int
    team: str
    deadline: Optional[str] = None  # ISO date if applicable
    blocked_by: Optional[str] = None


PRIORITY_QUEUE: tuple[PriorityAction, ...] = (
    PriorityAction(1, "Reconcile DBC vs Eden contradiction in proof files", "SATYA", 0, "jk-truth"),
    PriorityAction(2, "Audit all JK artifacts with credibility gates", "SATYA", 0, "jk-truth"),
    PriorityAction(3, "Submit Anthropic grant application (pick ONE draft)", "AHIMSA", 1, "jk-publish"),
    PriorityAction(4, "Create public welfare-tons GitHub repo", "AHIMSA", 1, "jk-publish"),
    PriorityAction(5, "Build welfare-tons.org static site with calculator", "AHIMSA", 1, "jk-publish"),
    PriorityAction(6, "Score 10 additional projects (diverse categories)", "TAPAS", 2, "jk-publish"),
    PriorityAction(7, "Write adversarial analysis: How to Game Welfare-Tons", "TAPAS", 2, "jk-critic"),
    PriorityAction(8, "Produce standards crosswalk (GS, Verra, ICVCM)", "DHARMA", 2, "jk-standards"),
    PriorityAction(9, "Write 10-page preprint for SSRN/arXiv", "AHIMSA", 3, "jk-publish"),
    PriorityAction(10, "Commission 3 paid external reviews", "SWARAJ", 3, "jk-market"),
    PriorityAction(11, "Run 10 buyer/registry/developer interviews", "SWARAJ", 3, "jk-market"),
    PriorityAction(12, "Find 1 academic co-author", "SWARAJ", 3, "jk-publish"),
    PriorityAction(13, "Build micro-SaaS: just-transition carbon diligence", "DHARMA", 4, "jk-publish"),
    PriorityAction(14, "Launch Welfare-Tons Weekly newsletter", "AHIMSA", 4, "jk-publish"),
    PriorityAction(15, "Score projects in China, India, SE Asia, Latin America", "SHAKTI", 5, "jk-field"),
    PriorityAction(16, "Design community feedback protocol", "AHIMSA", 5, "jk-field"),
)
