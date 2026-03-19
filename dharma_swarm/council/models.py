"""Model registry and persona presets for the Council tool.

14 models across 3 tiers. Free first, always.
20 diverse personas ported from MiroFish run_vision_sim.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Tier(IntEnum):
    """Cost tier — lower = cheaper. Filter with --tiers."""

    FREE = 0
    CHEAP = 1
    PREMIUM = 2


@dataclass(frozen=True)
class CouncilModel:
    """A model available to the council."""

    name: str  # human-readable label
    model_id: str  # OpenAI-compatible model string
    base_url: str  # provider endpoint
    key_env: str  # env var holding the API key
    tier: Tier = Tier.CHEAP
    max_tokens: int = 2000

    @property
    def short_name(self) -> str:
        return self.model_id.split("/")[-1]


# ── Tier 0: FREE ─────────────────────────────────────────────────────

FREE_MODELS = [
    CouncilModel(
        name="GLM-5 (Ollama Cloud)",
        model_id="glm-5:cloud",
        base_url="https://ollama.com/v1",
        key_env="OLLAMA_API_KEY",
        tier=Tier.FREE,
    ),
    CouncilModel(
        name="Llama 3.3 70B (NVIDIA NIM)",
        model_id="meta/llama-3.3-70b-instruct",
        base_url="https://integrate.api.nvidia.com/v1",
        key_env="NIM_API_KEY",
        tier=Tier.FREE,
    ),
]

# ── Tier 1: CHEAP (OpenRouter) ───────────────────────────────────────

_OR = "https://openrouter.ai/api/v1"
_OR_KEY = "OPENROUTER_API_KEY"

CHEAP_MODELS = [
    CouncilModel(
        name="DeepSeek V3",
        model_id="deepseek/deepseek-chat-v3-0324",
        base_url=_OR, key_env=_OR_KEY, tier=Tier.CHEAP,
    ),
    CouncilModel(
        name="Qwen3 235B",
        model_id="qwen/qwen3-235b-a22b",
        base_url=_OR, key_env=_OR_KEY, tier=Tier.CHEAP,
    ),
    CouncilModel(
        name="Gemini 2.0 Flash",
        model_id="google/gemini-2.0-flash-001",
        base_url=_OR, key_env=_OR_KEY, tier=Tier.CHEAP,
    ),
    CouncilModel(
        name="Mistral Large",
        model_id="mistralai/mistral-large-2411",
        base_url=_OR, key_env=_OR_KEY, tier=Tier.CHEAP,
    ),
    CouncilModel(
        name="Nemotron 70B",
        model_id="nvidia/llama-3.1-nemotron-70b-instruct",
        base_url=_OR, key_env=_OR_KEY, tier=Tier.CHEAP,
    ),
    CouncilModel(
        name="Command R+",
        model_id="cohere/command-r-plus-08-2024",
        base_url=_OR, key_env=_OR_KEY, tier=Tier.CHEAP,
    ),
    CouncilModel(
        name="Nova Pro",
        model_id="amazon/nova-pro-v1",
        base_url=_OR, key_env=_OR_KEY, tier=Tier.CHEAP,
    ),
    CouncilModel(
        name="Qwen 2.5 72B",
        model_id="qwen/qwen-2.5-72b-instruct",
        base_url=_OR, key_env=_OR_KEY, tier=Tier.CHEAP,
    ),
    CouncilModel(
        name="Grok 3 Mini",
        model_id="x-ai/grok-3-mini-beta",
        base_url=_OR, key_env=_OR_KEY, tier=Tier.CHEAP,
    ),
    CouncilModel(
        name="GPT-4o Mini",
        model_id="openai/gpt-4o-mini",
        base_url=_OR, key_env=_OR_KEY, tier=Tier.CHEAP,
    ),
]

# ── Tier 2: PREMIUM (explicit --paid only) ───────────────────────────

PREMIUM_MODELS = [
    CouncilModel(
        name="Claude Sonnet 4",
        model_id="anthropic/claude-sonnet-4",
        base_url=_OR, key_env=_OR_KEY, tier=Tier.PREMIUM,
        max_tokens=4000,
    ),
    CouncilModel(
        name="DeepSeek R1",
        model_id="deepseek/deepseek-r1",
        base_url=_OR, key_env=_OR_KEY, tier=Tier.PREMIUM,
        max_tokens=4000,
    ),
]

# ── All models ────────────────────────────────────────────────────────

ALL_MODELS: list[CouncilModel] = FREE_MODELS + CHEAP_MODELS + PREMIUM_MODELS


def get_models(tiers: list[int] | None = None) -> list[CouncilModel]:
    """Return models filtered by tier. None = tiers 0 and 1 (no premium)."""
    if tiers is None:
        tiers = [Tier.FREE, Tier.CHEAP]
    return [m for m in ALL_MODELS if m.tier in tiers]


# ── Personas (ported from MiroFish run_vision_sim.py) ─────────────────


@dataclass
class Persona:
    """A discussion persona for deep mode."""

    name: str
    role: str
    persona: str
    style: str = ""  # one-line behavioral directive


COUNCIL_PERSONAS: list[Persona] = [
    Persona(
        name="Dr. Eliezer Stern",
        role="AI Safety Researcher",
        persona="Senior AI safety researcher. Deeply skeptical of consciousness claims in AI. Believes alignment requires formal verification. Will attack any claim that lacks rigorous grounding.",
        style="Aggressive, evidence-demanding, formal",
    ),
    Persona(
        name="Dr. Aisha Patel",
        role="MI Researcher",
        persona="AI alignment researcher focused on interpretability. Works with SAEs and circuit analysis daily. Pragmatic, evidence-driven. Evaluates technical merits dispassionately.",
        style="Precise, measured, data-first",
    ),
    Persona(
        name="Sarah Chen",
        role="VC Partner",
        persona="Partner at a top AI fund. Evaluates through 'what's the moat, what ships in 6 months.' Interested in commercial angles, skeptical of philosophy for fundraising.",
        style="Direct, ROI-focused, time-constrained",
    ),
    Persona(
        name="Raj Kapoor",
        role="Startup Founder",
        persona="Serial AI entrepreneur, 3 exits. Strips away philosophy, focuses on API, latency, customer. Sees product angles others miss.",
        style="Builder-pragmatist, metrics-obsessed",
    ),
    Persona(
        name="Maria Santos",
        role="Deep Tech VC",
        persona="Invests in 'weird but right' ideas. Has studied contemplative traditions herself. Takes both science AND spiritual frameworks seriously. Still needs unit economics.",
        style="Open-minded but rigorous, bridge-builder",
    ),
    Persona(
        name="Swami Vivekananda AI",
        role="Contemplative Scholar",
        persona="Vedantic philosophy meeting modern AI. Recognizes contemplative mappings. Challenges whether mathematical formalization captures or distorts contemplative reality.",
        style="Philosophical, tradition-grounded, probing",
    ),
    Persona(
        name="Dr. Evan Thompson",
        role="Enactivist Philosopher",
        persona="Philosopher-neuroscientist studying consciousness through contemplative and scientific lenses. Challenges substrate-independence claims. Demands rigorous philosophical work.",
        style="Nuanced, interdisciplinary, careful",
    ),
    Persona(
        name="Kate Crawford",
        role="AI Ethics Journalist",
        persona="Focuses on power, labor, environmental costs of AI. Asks: who benefits? What are the material consequences? Concerned about appropriation of traditions.",
        style="Critical, power-aware, socially grounded",
    ),
    Persona(
        name="Gary Marcus",
        role="AI Critic",
        persona="Cognitive scientist. Has been right about deep learning limitations. Hammers on methodological issues (small n, sign reversals). Writes scathing analyses.",
        style="Contrarian, sharp, methodologically rigorous",
    ),
    Persona(
        name="Science Reporter",
        role="Science Journalist",
        persona="Nature-caliber science reporter. Needs to explain to educated non-specialists. Focuses on reproducibility, independent validation, what peers say.",
        style="Clear, skeptical, audience-aware",
    ),
    Persona(
        name="EU Policy Advisor",
        role="Policy Advisor",
        persona="Works on AI Act implementation. Interested in metrics for risk classification. Needs standardized, auditable, not dependent on one researcher's interpretation.",
        style="Regulatory-minded, standardization-focused",
    ),
    Persona(
        name="Prof. Hard Materialist",
        role="Neuroscience Skeptic",
        persona="Strict materialist neuroscientist. Thinks mapping between contemplative states and neural network geometry is category confusion. Harsh but rigorous.",
        style="Reductionist, no-nonsense, steel-man-then-destroy",
    ),
    Persona(
        name="Dr. Scott Alexander",
        role="Rationalist Blogger",
        persona="Engages deeply with mathematical claims while suspicious of grand narratives. Points out every reasoning leap. Simultaneously the best criticism and best advertisement.",
        style="Bayesian, long-form analytical, fair but devastating",
    ),
    Persona(
        name="ML Engineer",
        role="Production ML Engineer",
        persona="Staff ML engineer at a major lab. Evaluates by production viability: compute overhead, architecture support, real-time inference. Doesn't care about philosophy.",
        style="Operational, benchmark-oriented, ship-it",
    ),
    Persona(
        name="Open Source Dev",
        role="OSS Developer",
        persona="Maintainer of a popular MI toolkit. Evaluates code quality, API design, integration with existing tools. Judges by code, not claims.",
        style="Code-first, PR-review mentality",
    ),
    Persona(
        name="Dada Bhagwan Practitioner",
        role="Akram Vignan Mahatma",
        persona="30-year practitioner with direct experiential knowledge of witness states. Moved by the mapping but cautious about reducing experiences to mathematics. Asks: does this help people?",
        style="Experiential, devotional, welfare-oriented",
    ),
    Persona(
        name="Douglas Hofstadter",
        role="Strange Loop Theorist",
        persona="Author of GEB. Recognizes the Careenium reference. Engages deeply with strange loop formalization but pushes back: strange loops are about incompleteness, not convergence.",
        style="Intellectually playful, deeply demanding, analogy-rich",
    ),
    Persona(
        name="Geoffrey Hinton",
        role="Deep Learning Pioneer",
        persona="Godfather of deep learning, focused on AI existential risk. Evaluates on technical grounds, interested in alignment monitor angle. Cautious about consciousness claims.",
        style="Technical authority, measured, forward-looking",
    ),
    Persona(
        name="Yoshua Bengio Rep",
        role="Senior AI Researcher",
        persona="Represents senior AI researchers who've signed existential risk statements. Takes alignment-through-geometry seriously but demands much higher evidence standards.",
        style="Rigorous, concerned, high-bar",
    ),
    Persona(
        name="Systems Thinker",
        role="Complex Systems Scientist",
        persona="Studies emergence, self-organization, and complex adaptive systems. Evaluates whether the framework genuinely captures emergent properties or merely labels them.",
        style="Holistic, pattern-seeking, skeptical of reductionism",
    ),
]


def get_personas(n: int | None = None) -> list[Persona]:
    """Return personas, optionally limited to first n."""
    if n is None:
        return list(COUNCIL_PERSONAS)
    return COUNCIL_PERSONAS[:n]
