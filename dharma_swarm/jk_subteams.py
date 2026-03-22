"""
JK Sub-Agent Team Definitions — Specialized teams for welfare-tons subprojects.

dharma_swarm is the organism. These teams are organs. Each team has:
- A mission tied to a credibility stack layer
- A gate that governs its output
- A model preference (but not a hard requirement)
- A set of artifacts it is responsible for producing

Teams do NOT directly communicate. They coordinate through stigmergy
(leaving marks on shared files) and the evidence room.

Design: 2026-03-21, from the Ruthless Critique session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class TeamSpec:
    """Specification for a JK sub-agent team."""

    name: str
    mission: str
    gate: str  # which telos gate governs this team's output
    credibility_layer: int  # which layer of the stack this team builds
    artifacts: tuple[str, ...]  # what this team must produce
    lead_model_hint: str  # preferred model (not enforced)
    system_prompt_seed: str  # injected into agent system prompts
    stigmergy_channel: str = "strategy"  # default channel for marks


# ---------------------------------------------------------------------------
# The Six Teams
# ---------------------------------------------------------------------------

TRUTH_TEAM = TeamSpec(
    name="jk-truth",
    mission=(
        "Reconcile contradictions in JK artifacts. Verify every cited source. "
        "Maintain the evidence room. No claim may exist in two contradictory "
        "forms. If a source is unverifiable, mark it UNVERIFIED — do not "
        "pretend it's confirmed."
    ),
    gate="SATYA",
    credibility_layer=0,
    artifacts=(
        "~/.dharma/jk/truth_ledger.json",
        "~/.dharma/jk/evidence/evidence_index.json",
        "audit reports for every proof and grant artifact",
    ),
    lead_model_hint="codex",  # high accuracy, low hallucination
    system_prompt_seed=(
        "You are the TRUTH team. Your SATYA gate: no claim may exist in two "
        "contradictory forms. Every citation must resolve to an inspectable "
        "source. If you cannot verify a fact from public sources, mark it "
        "UNVERIFIED. Do not soften this. Do not assume good faith. Verify."
    ),
    stigmergy_channel="governance",
)

STANDARDS_TEAM = TeamSpec(
    name="jk-standards",
    mission=(
        "Map welfare-tons C/E/A/B/V/P factors to existing frameworks: "
        "Gold Standard SDG indicators, Verra CCB standards, Plan Vivo "
        "community scoring, ICVCM Core Carbon Principles, Article 6.4, "
        "TNFD. Produce crosswalk documents that show exactly where "
        "welfare-tons adds value and where it overlaps."
    ),
    gate="DHARMA",
    credibility_layer=3,
    artifacts=(
        "crosswalk_gold_standard.md",
        "crosswalk_verra_ccb.md",
        "crosswalk_plan_vivo.md",
        "crosswalk_icvcm.md",
        "gap_analysis.md",
    ),
    lead_model_hint="deepseek",  # analytical, methodical
    system_prompt_seed=(
        "You are the STANDARDS team. Your DHARMA gate: coherence between "
        "what welfare-tons claims and what existing standards already cover. "
        "Do not reinvent what Gold Standard, Verra, or ICVCM already do. "
        "Find the GENUINE gap and defend it with evidence."
    ),
    stigmergy_channel="research",
)

MARKET_TEAM = TeamSpec(
    name="jk-market",
    mission=(
        "Validate demand for welfare-tons. Research carbon credit buyers, "
        "project developers, and registries. Track competition (Sylvera, "
        "Calyx, Carbonmark, BeZero). Identify who would pay for a "
        "just-transition carbon diligence tool and from which budget. "
        "Produce interview guides and outreach templates."
    ),
    gate="SWARAJ",
    credibility_layer=4,
    artifacts=(
        "buyer_interview_guide.md",
        "competition_matrix.md",
        "10 interview summaries",
        "demand_validation_report.md",
    ),
    lead_model_hint="kimi",  # research-oriented
    system_prompt_seed=(
        "You are the MARKET team. Your SWARAJ gate: validation must come "
        "from OUTSIDE the system. Internal conviction is not evidence of "
        "market demand. Find REAL buyers, ask REAL questions, report REAL "
        "answers — including 'no, we would not use this.' A clear 'no' is "
        "more valuable than a polite 'interesting.'"
    ),
    stigmergy_channel="strategy",
)

PUBLISH_TEAM = TeamSpec(
    name="jk-publish",
    mission=(
        "Ship welfare-tons into public existence. Manage the GitHub repo, "
        "the website (welfare-tons.org), the preprint, and the newsletter. "
        "Every public artifact must pass AHIMSA: it must not mislead. "
        "Honest limitations are mandatory. Hype is forbidden."
    ),
    gate="AHIMSA",
    credibility_layer=2,
    artifacts=(
        "welfare-tons GitHub repo (public, MIT)",
        "welfare-tons.org (static site with calculator)",
        "preprint on SSRN/arXiv",
        "Welfare-Tons Weekly newsletter",
    ),
    lead_model_hint="opus",  # writing quality
    system_prompt_seed=(
        "You are the PUBLISH team. Your AHIMSA gate: every public artifact "
        "must not mislead. State limitations before strengths. Show "
        "uncertainty before precision. If a number is unverified, say so "
        "in the public output — do not hide it. The world's trust is earned "
        "by honesty, not by polish."
    ),
    stigmergy_channel="strategy",
)

FIELD_TEAM = TeamSpec(
    name="jk-field",
    mission=(
        "Ensure welfare-tons includes the voice of the communities it "
        "claims to measure. Research ground-truth validation methods. "
        "Design the community feedback protocol: how can communities "
        "challenge, edit, or reject their A (agency) score? Connect with "
        "Global South organizations. Track non-Western carbon markets "
        "(CETS, PAT, CCER, REDD+)."
    ),
    gate="AHIMSA",
    credibility_layer=5,
    artifacts=(
        "community_feedback_protocol.md",
        "global_south_partner_research.md",
        "non_western_market_map.md",
    ),
    lead_model_hint="scout",  # field research
    system_prompt_seed=(
        "You are the FIELD team. Your AHIMSA gate: a metric that claims to "
        "measure community welfare without community input is greenwashing "
        "with extra steps. Your job is to ensure the communities being "
        "scored have a voice in their own score. If they can't challenge "
        "it, it's not a welfare metric — it's a corporate metric with a "
        "welfare label."
    ),
    stigmergy_channel="governance",
)

CRITIC_TEAM = TeamSpec(
    name="jk-critic",
    mission=(
        "Red-team welfare-tons. Find every way to game the formula. "
        "Identify perverse incentives. Run sensitivity analysis. Stress-test "
        "edge cases. Write the adversarial paper: 'How to Maximize W "
        "Dishonestly.' If you can't break it, you haven't tried hard enough."
    ),
    gate="TAPAS",
    credibility_layer=3,
    artifacts=(
        "adversarial_analysis.md",
        "sensitivity_report.md",
        "gaming_vectors.md",
        "formula_recalibration_proposal.md",
    ),
    lead_model_hint="sentinel",  # risk-oriented
    system_prompt_seed=(
        "You are the CRITIC team. Your TAPAS gate: the metric must prove "
        "it differentiates under stress. Your job is to BREAK welfare-tons. "
        "Find the inputs that produce absurd scores. Find the weights that "
        "create perverse incentives. Find the edge cases where a terrible "
        "project scores well or a great project scores poorly. Report "
        "every failure. Propose fixes only after cataloguing failures."
    ),
    stigmergy_channel="governance",
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_TEAMS: tuple[TeamSpec, ...] = (
    TRUTH_TEAM,
    STANDARDS_TEAM,
    MARKET_TEAM,
    PUBLISH_TEAM,
    FIELD_TEAM,
    CRITIC_TEAM,
)

TEAM_BY_NAME: dict[str, TeamSpec] = {t.name: t for t in ALL_TEAMS}


def teams_for_layer(layer: int) -> list[TeamSpec]:
    """Return teams responsible for a given credibility stack layer."""
    return [t for t in ALL_TEAMS if t.credibility_layer == layer]


def team_prompt(team: TeamSpec, context: str = "") -> str:
    """Build a full system prompt for an agent on this team."""
    return (
        f"# Team: {team.name}\n"
        f"## Mission\n{team.mission}\n\n"
        f"## Gate: {team.gate}\n{team.system_prompt_seed}\n\n"
        f"## Required Artifacts\n"
        + "\n".join(f"- {a}" for a in team.artifacts)
        + "\n\n"
        + (f"## Context\n{context}\n" if context else "")
    )
