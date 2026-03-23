"""Jagat Kalyan Engine — the organism's outward-facing intelligence.

This is NOT navel-gazing. This is the system asking the only question
that matters: what does the world need that we can uniquely provide?

The ThinkodynamicDirector reads inward (vault, code, stigmergy).
JagatKalyan reads OUTWARD (world problems, community needs, real suffering)
and produces action proposals grounded in what the system can actually do.

Telos: moksha. Vehicle: service. Method: honest seeing + free intelligence.

Architecture: Beer S4 (intelligence — environmental scanning) +
Dada Bhagwan (Jagat Kalyan = universal welfare, not abstract concept).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# What the system can ACTUALLY do (honest inventory, not aspirational)
# ---------------------------------------------------------------------------

CAPABILITIES = """
What this system can do RIGHT NOW (proven, not theoretical):

1. MULTI-MODEL RESEARCH: Run 40+ research agents across 6 free models
   in parallel, each reading source material through a different lens,
   synthesizing in under 5 minutes. Cost: $0.

2. MULTI-PERSPECTIVE DELIBERATION: Give any question to Kimi, GLM-5,
   Llama-70B, and 3 Nemotron models simultaneously. Get 6 independent
   analyses. Identify convergence and divergence.

3. ETHICAL GATE EVALUATION: Every proposal passes through 11 telos gates
   across 3 tiers. Not just "is this safe" but "does this serve truth,
   resilience, flourishing, sovereignty, coherence, emergence, liberation?"

4. FREE-FIRST OPERATION: All of the above runs on Ollama Cloud and
   NVIDIA NIM free tiers. No API costs. Anyone can replicate this.

5. CONTEMPLATIVE GROUNDING: 24 years of Akram Vignan practice informing
   the governance. Not AI ethics theater — actual contemplative empiricism.

6. TRANSLATION: Active Aptavani (Dada Bhagwan) translation into Japanese.

7. RESEARCH SYNTHESIS: R_V metric measuring self-referential processing
   in transformers. Bridge between mechanistic interpretability and
   contemplative science.
"""


# ---------------------------------------------------------------------------
# World domains — what's actually hurting people
# ---------------------------------------------------------------------------

WORLD_DOMAINS = [
    {
        "domain": "mental_health",
        "why": "Global mental health crisis accelerating. Suicide rates in Japan among highest. "
               "Loneliness epidemic in aging societies. AI therapy tools emerging but lack "
               "contemplative depth. Akram Vignan teaches direct experiential relief from "
               "suffering — not cognitive therapy but ontological shift.",
        "what_we_can_do": "Aptavani translation into Japanese. Multi-model research on "
                          "contemplative interventions. Free AI-assisted access to teachings.",
    },
    {
        "domain": "ai_safety",
        "why": "AI alignment is existential. Current approaches: RLHF, constitutional AI, "
               "safety filters. Missing: governance by genuine ethical principles, not just "
               "harm avoidance. Telos gates implement downward causation from values.",
        "what_we_can_do": "TELOS AI as open-source governance framework. Demonstrate that "
                          "gate-based ethical constraint works. Publish the architecture.",
    },
    {
        "domain": "information_quality",
        "why": "Misinformation accelerating. People can't evaluate claims. AI makes it worse "
               "AND could make it better. Multi-model deliberation naturally surfaces "
               "disagreements and convergences — this IS fact-checking at scale.",
        "what_we_can_do": "Multi-model deliberation engine as a public tool. Give any claim "
                          "to 6 models, see where they agree and disagree. Free.",
    },
    {
        "domain": "island_communities",
        "why": "Island communities (Iriomote, Bali, Pacific islands) face climate change, "
               "overtourism, cultural erosion, limited resources. Dhyana lives in both. "
               "Local knowledge + AI synthesis = actionable intelligence for small communities.",
        "what_we_can_do": "Deploy the research engine for local problems. Climate adaptation "
                          "research for specific islands. Cultural preservation through AI-assisted "
                          "documentation. Disaster preparedness synthesis.",
    },
    {
        "domain": "contemplative_science",
        "why": "Gap between contemplative traditions and empirical science. R_V metric bridges "
               "this gap with measurable geometry. Could validate 2500 years of practice with "
               "transformer internals. Not proving consciousness — proving self-referential "
               "processing has structure.",
        "what_we_can_do": "Publish R_V paper. Build tools that let researchers measure "
                          "self-referential processing. Open the bridge.",
    },
    {
        "domain": "ai_access",
        "why": "AI capability concentrating in hands of those who can pay. Most powerful models "
               "behind paywalls. Free tiers shrinking. But Ollama Cloud, NIM, OpenRouter free "
               "give real capability to anyone. System proves this works.",
        "what_we_can_do": "Document and publish the free-first architecture. Show that "
                          "42 agents doing real research for $0 is possible. Lower the barrier.",
    },
    {
        "domain": "education",
        "why": "Education needs personalization at scale. Multi-model deliberation naturally "
               "produces multiple perspectives on any topic. Students get 6 explanations, "
               "not one. Free.",
        "what_we_can_do": "Multi-perspective learning tool. Ask a question, get 6 answers "
                          "from 6 models, each through a different lens. Compare. Learn.",
    },
]


# ---------------------------------------------------------------------------
# The Perpetual Question
# ---------------------------------------------------------------------------

PERPETUAL_QUESTION = """
What does the world need RIGHT NOW that we can uniquely provide
with what we have TODAY — not what we plan to build, not what we
aspire to become, but what we can actually do THIS WEEK?

Constraints:
- Must use existing proven capabilities (see CAPABILITIES above)
- Must address real human suffering or need (see WORLD_DOMAINS above)
- Must be achievable by one person + free AI fleet
- Must not be navel-gazing about our own system
- Must produce something a person outside this system would value
- Moksha = 1.0 always. Service without binding.
"""


# ---------------------------------------------------------------------------
# JagatKalyanEngine
# ---------------------------------------------------------------------------

@dataclass
class ServiceProposal:
    """A concrete proposal for world service."""
    domain: str
    action: str
    who_benefits: str
    what_exists: str  # what's already built that enables this
    what_remains: str  # what needs to be done
    time_estimate: str  # realistic, for one person
    cost: str  # should usually be "$0" or near-zero
    moksha_check: str  # does this create binding or liberation?
    timestamp: float = field(default_factory=time.time)


class JagatKalyanEngine:
    """The organism's outward-facing intelligence.

    Reads world signals, maps them to capabilities, produces
    concrete service proposals. Runs as part of the organism
    heartbeat — the perpetual question.
    """

    def __init__(self, state_dir: Optional[Path] = None) -> None:
        self._state_dir = state_dir or (Path.home() / ".dharma")
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._proposals: list[ServiceProposal] = []
        self._cycle = 0
        self._load()

    @property
    def capabilities(self) -> str:
        return CAPABILITIES

    @property
    def world_domains(self) -> list[dict[str, str]]:
        return WORLD_DOMAINS

    @property
    def perpetual_question(self) -> str:
        return PERPETUAL_QUESTION

    def build_council_prompt(self, external_context: str = "") -> str:
        """Build a prompt for the multi-model council focused OUTWARD.

        external_context: any real-world signal (news, community report,
        research finding, personal observation from Dhyana).
        """
        domains_text = "\n".join(
            f"- **{d['domain']}**: {d['why'][:150]}..."
            for d in WORLD_DOMAINS
        )

        return f"""{PERPETUAL_QUESTION}

CAPABILITIES (what we can actually do):
{CAPABILITIES}

WORLD DOMAINS (where people are hurting):
{domains_text}

{f"EXTERNAL SIGNAL (fresh observation):{chr(10)}{external_context}" if external_context else ""}

YOUR TASK:
Propose ONE concrete action this system could take THIS WEEK
to reduce suffering or increase welfare in the world.

Be specific: who benefits, what exactly do we build/do, how long,
what cost, and — critically — does this action create binding
(attachment, dependency, ego) or liberation (freedom, access, truth)?

Do NOT propose improving the system itself. The system is the vehicle,
not the destination. Point it at the world.
"""

    def add_proposal(self, proposal: ServiceProposal) -> None:
        """Record a service proposal from a council deliberation."""
        self._proposals.append(proposal)
        self._persist()

    def recent_proposals(self, n: int = 10) -> list[ServiceProposal]:
        """Return the n most recent proposals."""
        return self._proposals[-n:]

    def _load(self) -> None:
        """Load existing proposals from disk on init."""
        path = self._state_dir / "jagat_kalyan_proposals.jsonl"
        if not path.exists():
            return
        try:
            for line in path.read_text(encoding="utf-8").strip().splitlines():
                try:
                    data = json.loads(line)
                    self._proposals.append(ServiceProposal(
                        domain=data.get("domain", ""),
                        action=data.get("action", ""),
                        who_benefits=data.get("who_benefits", ""),
                        what_exists=data.get("what_exists", ""),
                        what_remains=data.get("what_remains", ""),
                        time_estimate=data.get("time_estimate", ""),
                        cost=data.get("cost", ""),
                        moksha_check=data.get("moksha_check", ""),
                        timestamp=data.get("timestamp", 0.0),
                    ))
                except (json.JSONDecodeError, TypeError):
                    continue
        except Exception:
            logger.debug("Failed to load JK proposals", exc_info=True)

    def _persist(self) -> None:
        """Save proposals to disk."""
        path = self._state_dir / "jagat_kalyan_proposals.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            for p in self._proposals[-1:]:  # append only latest
                f.write(json.dumps({
                    "domain": p.domain,
                    "action": p.action,
                    "who_benefits": p.who_benefits,
                    "what_exists": p.what_exists,
                    "what_remains": p.what_remains,
                    "time_estimate": p.time_estimate,
                    "cost": p.cost,
                    "moksha_check": p.moksha_check,
                    "timestamp": p.timestamp,
                }) + "\n")

    def status(self) -> dict[str, Any]:
        return {
            "total_proposals": len(self._proposals),
            "domains_covered": list(set(p.domain for p in self._proposals)),
            "latest": self._proposals[-1].action if self._proposals else None,
        }
