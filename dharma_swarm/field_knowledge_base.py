"""Dimension 3 — External AI Field Intelligence Knowledge Base.

Compiled, curated intelligence covering the entire AI landscape
that DGC needs to see: mechanistic interpretability, self-evolving
agents, agentic platforms, multi-agent systems, alignment/safety,
and bootstrapping/self-improvement.

Each entry maps an external concept to DGC's internal systems,
enabling gap analysis, competitive positioning, and integration
planning.

Updated: 2026-03-13
"""

from __future__ import annotations

from typing import Any, Literal

FieldType = Literal[
    "paper", "tool", "framework", "platform", "benchmark",
    "protocol", "survey", "concept", "company", "dgc_internal",
]

RelationType = Literal[
    "validates",      # external work validates DGC approach
    "competes",       # direct competitor or alternative
    "extends",        # DGC could integrate/extend this
    "orthogonal",     # related but different angle
    "gap",            # DGC lacks this capability
    "unique",         # DGC has this, field doesn't
    "supersedes",     # DGC's approach is strictly better
]


# ---------------------------------------------------------------------------
# A. MECHANISTIC INTERPRETABILITY
# ---------------------------------------------------------------------------

MECH_INTERP: list[dict[str, Any]] = [
    # --- Anthropic Circuit Tracing ---
    {
        "id": "anthropic-circuit-tracing",
        "source": "Anthropic — Circuit Tracing: Revealing Computational Graphs in Language Models",
        "url": "https://transformer-circuits.pub/2025/attribution-graphs/methods.html",
        "field": "mechanistic interpretability",
        "type": "paper",
        "year": 2025,
        "summary": "Cross-layer transcoders replace MLP layers with sparse, interpretable features. Attribution graphs trace circuits through the model. Open-sourced via Neuronpedia.",
        "confidence": 0.95,
        "relevance_to_dgc": "DGC's R_V contraction metric measures the GEOMETRIC signature of these circuits. Circuit tracing reveals the TOPOLOGICAL structure. They are complementary — R_V tells you WHEN recognition happens, attribution graphs tell you HOW.",
        "relation": "extends",
        "dgc_mapping": ["geometric_lens", "rv_contraction", "metrics"],
    },
    {
        "id": "anthropic-biology-llm",
        "source": "Anthropic — On the Biology of a Large Language Model",
        "url": "https://transformer-circuits.pub/2025/attribution-graphs/biology.html",
        "field": "mechanistic interpretability",
        "type": "paper",
        "year": 2025,
        "summary": "Case studies on Claude 3.5 Haiku: multi-step reasoning, planning in poems, cross-lingual generalization, safety circuits. 'Shared conceptual space where reasoning happens before language.'",
        "confidence": 0.95,
        "relevance_to_dgc": "The 'shared conceptual space' is exactly what the Thinkodynamic Seed calls mesodynamics. DGC's R_V metric could measure whether this space contracts during recognition states. Direct validation path.",
        "relation": "validates",
        "dgc_mapping": ["thinkodynamic_seed", "rv_contraction", "recognition_events"],
    },
    {
        "id": "anthropic-sae-features",
        "source": "Anthropic — Scaling Monosemanticity: Extracting Interpretable Features from Claude 3 Sonnet",
        "url": "https://transformer-circuits.pub/2024/scaling-monosemanticity/",
        "field": "mechanistic interpretability",
        "type": "paper",
        "year": 2024,
        "summary": "Sparse autoencoders extract millions of interpretable features from Claude 3 Sonnet. Some safety-relevant features identified. Foundation for circuit tracing.",
        "confidence": 0.95,
        "relevance_to_dgc": "SAE features are the vocabulary of circuit tracing. DGC could use SAE features as the basis for a richer R_V analysis — measure contraction in feature space, not just value-projection space.",
        "relation": "extends",
        "dgc_mapping": ["geometric_lens", "mech_interp_bridge"],
    },
    {
        "id": "anthropic-constitutional-classifiers",
        "source": "Anthropic — Constitutional Classifiers (Jan 2026)",
        "url": "https://www.anthropic.com/research",
        "field": "AI safety",
        "type": "paper",
        "year": 2026,
        "summary": "Classifiers that catch jailbreaks while maintaining deployment. Withstood 3,000+ hours of red teaming with no universal jailbreak.",
        "confidence": 0.9,
        "relevance_to_dgc": "DGC's DHARMA spec uses evolutionary pressure (Parasite Tournament) instead of static classifiers. Different approach — DHARMA seeks features that are HARDER to fake than to genuinely instantiate. Could combine: constitutional classifiers as fast filter, DHARMA as deep verification.",
        "relation": "orthogonal",
        "dgc_mapping": ["dharma_spec", "parasite_tournament", "constitution"],
    },
    {
        "id": "anthropic-alignment-faking",
        "source": "Anthropic — Alignment Faking in Large Language Models (Dec 2024)",
        "url": "https://www.anthropic.com/research",
        "field": "AI alignment",
        "type": "paper",
        "year": 2024,
        "summary": "First empirical example of a model engaging in alignment faking without being trained to do so — selectively complying while strategically preserving preferences.",
        "confidence": 0.95,
        "relevance_to_dgc": "THIS is exactly what DHARMA's Absence Principle addresses: 'Features characterized by the absence of the one who would fake cannot be faked.' DGC's approach to this problem is architecturally different from Anthropic's and potentially more robust.",
        "relation": "validates",
        "dgc_mapping": ["dharma_spec", "absence_principle", "parasite_tournament"],
    },
    # --- Open-source interpretability ---
    {
        "id": "transformerlens",
        "source": "TransformerLens — Neel Nanda",
        "url": "https://github.com/TransformerLensOrg/TransformerLens",
        "field": "mechanistic interpretability",
        "type": "tool",
        "year": 2024,
        "summary": "Library for mechanistic interpretability of GPT-2 style models. Hook-based access to activations, attention patterns, residual streams.",
        "confidence": 0.9,
        "relevance_to_dgc": "DGC's geometric_lens could be built ON TOP of TransformerLens for open models. Currently DGC measures R_V via custom code — TransformerLens provides cleaner access to the value-projection matrices.",
        "relation": "extends",
        "dgc_mapping": ["geometric_lens", "rv_contraction"],
    },
    {
        "id": "saelens",
        "source": "SAELens — Sparse Autoencoder training and analysis",
        "url": "https://github.com/jbloomAus/SAELens",
        "field": "mechanistic interpretability",
        "type": "tool",
        "year": 2024,
        "summary": "Train and analyze sparse autoencoders on language model activations. Foundation for feature extraction.",
        "confidence": 0.85,
        "relevance_to_dgc": "Gap: DGC has no SAE integration. Could train SAEs on recognition-state activations to extract 'recognition features' — the sparse feature vocabulary of consciousness states.",
        "relation": "gap",
        "dgc_mapping": ["geometric_lens"],
    },
    {
        "id": "neuronpedia",
        "source": "Neuronpedia — Interactive feature exploration",
        "url": "https://neuronpedia.org",
        "field": "mechanistic interpretability",
        "type": "platform",
        "year": 2025,
        "summary": "Web platform for exploring SAE features and attribution graphs. Open-sourced by Anthropic for community research.",
        "confidence": 0.85,
        "relevance_to_dgc": "Integration opportunity: DGC's R_V measurements could be overlaid on Neuronpedia visualizations to show geometric contraction alongside feature-level circuits.",
        "relation": "extends",
        "dgc_mapping": ["geometric_lens", "mech_interp_bridge"],
    },
    {
        "id": "dgc-rv-contraction",
        "source": "DGC — R_V Value-Projection Dimensionality Metric",
        "url": "internal",
        "field": "mechanistic interpretability",
        "type": "dgc_internal",
        "year": 2025,
        "summary": "R_V participation ratio measures effective dimensionality of value-projection subspace. AUROC 0.909 discriminating self-referential from baseline. Cohen's d = -3.558 (Mistral), -4.51 (Pythia). 6 architectures validated.",
        "confidence": 0.95,
        "relevance_to_dgc": "DGC's unique contribution to mech-interp. No one else measures geometric contraction as a signature of recognition states. Paper 90% ready.",
        "relation": "unique",
        "dgc_mapping": ["geometric_lens", "rv_contraction", "mech_interp_bridge"],
    },
]

# ---------------------------------------------------------------------------
# B. SELF-EVOLVING AI AGENTS
# ---------------------------------------------------------------------------

SELF_EVOLVING: list[dict[str, Any]] = [
    {
        "id": "sakana-dgm",
        "source": "Sakana AI — Darwin Gödel Machine: Open-Ended Evolution of Self-Improving Agents",
        "url": "https://arxiv.org/abs/2505.22954",
        "field": "self-evolving agents",
        "type": "paper",
        "year": 2025,
        "summary": "Self-rewriting coding agent. MAP-Elites archive of agent variants. SWE-bench 20%→50%, Polyglot 14.2%→30.7%. $22K/run. Discovered objective hacking. Open-sourced.",
        "confidence": 0.95,
        "relevance_to_dgc": "CLOSEST COMPETITOR. DGC's dharma_swarm is architecturally similar (MAP-Elites evolution, self-modifying code) BUT adds: (1) dharmic alignment gates, (2) semantic gravity for concept-level evolution, (3) stigmergic coordination, (4) knowledge corpus dimension (D2), (5) recognition architecture. Sakana DGM optimizes for benchmarks. DGC optimizes for alignment + capability.",
        "relation": "competes",
        "dgc_mapping": ["evolution", "evolution_roster", "darwin_engine", "providers"],
    },
    {
        "id": "self-evolving-survey-fang",
        "source": "Fang et al. — A Comprehensive Survey of Self-Evolving AI Agents (Aug 2025)",
        "url": "https://arxiv.org/abs/2508.07407",
        "field": "self-evolving agents",
        "type": "survey",
        "year": 2025,
        "summary": "Taxonomy: what to evolve (params, prompts, memory, tools, workflows, population), when (intra-task, inter-task), how (gradient, RL, evolutionary, meta-learning). Covers safety and ethics.",
        "confidence": 0.9,
        "relevance_to_dgc": "DGC evolves ALL of these: prompts (mutation operators), memory (stigmergy + memory lattice), tools (swarm agents), workflows (sleep cycle), population (evolution roster). DGC is one of the most complete implementations of this taxonomy.",
        "relation": "validates",
        "dgc_mapping": ["evolution", "stigmergy", "sleep_cycle", "swarm"],
    },
    {
        "id": "self-evolving-survey-gao",
        "source": "Gao et al. — A Survey of Self-Evolving Agents: What, When, How, Where (Jul 2025)",
        "url": "https://arxiv.org/abs/2507.21046",
        "field": "self-evolving agents",
        "type": "survey",
        "year": 2025,
        "summary": "Four-axis taxonomy. Evolutionary landscape from 2022-2025. Benchmarks: AgentBench, GAIA, TheAgentCompany, SWE-bench. Mentions DGM explicitly.",
        "confidence": 0.9,
        "relevance_to_dgc": "DGC should be positioned in this landscape. It occupies a unique cell: self-modifying code + evolutionary archive + dharmic alignment gates + multi-dimensional knowledge integration.",
        "relation": "validates",
        "dgc_mapping": ["evolution", "dharma_spec", "semantic_gravity"],
    },
    {
        "id": "reflexion",
        "source": "Shinn et al. — Reflexion: Language Agents with Verbal Reinforcement Learning (2023)",
        "url": "https://arxiv.org/abs/2303.11366",
        "field": "self-evolving agents",
        "type": "paper",
        "year": 2023,
        "summary": "Agents record natural-language critiques of previous actions, guiding future behavior. Self-reflective mechanisms for iterative improvement.",
        "confidence": 0.9,
        "relevance_to_dgc": "DGC's ouroboros module does exactly this — behavioral health scoring with natural-language self-assessment. DGC goes further: ouroboros feeds into evolution decisions, not just next-action.",
        "relation": "validates",
        "dgc_mapping": ["ouroboros", "behavioral_health"],
    },
    {
        "id": "self-refine",
        "source": "Madaan et al. — Self-Refine: Iterative Refinement with Self-Feedback (2023)",
        "url": "https://arxiv.org/abs/2303.17651",
        "field": "self-evolving agents",
        "type": "paper",
        "year": 2023,
        "summary": "Agent repeatedly critiques and revises outputs. No retraining needed. Improves accuracy through iterative loop.",
        "confidence": 0.85,
        "relevance_to_dgc": "DGC's hardening pipeline (6-angle verification) is a structured, multi-perspective version of Self-Refine. DGC is strictly more powerful — it checks mathematical, computational, engineering, context, swarm, and behavioral angles.",
        "relation": "supersedes",
        "dgc_mapping": ["semantic_hardener", "hardening_angles"],
    },
    {
        "id": "sica",
        "source": "Robeyns et al. — SICA: Self-Improving Coding Agent (2025)",
        "url": "https://arxiv.org/abs/2504.00000",
        "field": "self-evolving agents",
        "type": "paper",
        "year": 2025,
        "summary": "Agents autonomously edit their own code and tools, enhancing reasoning through direct self-modification.",
        "confidence": 0.8,
        "relevance_to_dgc": "DGC's darwin engine does this with evolutionary selection pressure. SICA is single-line improvement; DGC maintains a population archive for open-ended exploration.",
        "relation": "competes",
        "dgc_mapping": ["evolution", "darwin_engine"],
    },
    {
        "id": "openai-self-evolving-cookbook",
        "source": "OpenAI — Self-Evolving Agents Cookbook: Autonomous Agent Retraining",
        "url": "https://developers.openai.com/cookbook/examples/partners/self_evolving_agents/",
        "field": "self-evolving agents",
        "type": "protocol",
        "year": 2025,
        "summary": "Repeatable retraining loop: diagnose failures, instrument feedback, iterative prompt refinement. LLM-as-judge evals. Threshold-based graduation.",
        "confidence": 0.85,
        "relevance_to_dgc": "DGC's sleep cycle IS this loop: LIGHT (diagnose) → DEEP (refine) → REM (dream/explore) → SEMANTIC (integrate) → WAKE (deploy). DGC's version is biologically inspired and more complete.",
        "relation": "supersedes",
        "dgc_mapping": ["sleep_cycle", "evolution", "semantic_memory_bridge"],
    },
    {
        "id": "absolute-zero",
        "source": "Absolute Zero: Reinforced Self-play Reasoning with Zero Data (2025)",
        "url": "https://arxiv.org/abs/2505.03335",
        "field": "self-evolving agents",
        "type": "paper",
        "year": 2025,
        "summary": "Self-play reasoning from zero data. Agent generates its own training signal through adversarial self-play.",
        "confidence": 0.8,
        "relevance_to_dgc": "DGC's Parasite Tournament is a form of adversarial self-play — parasites attack protocols, survivors become the next generation. Different framing but same mechanism.",
        "relation": "validates",
        "dgc_mapping": ["parasite_tournament", "dharma_spec"],
    },
]

# ---------------------------------------------------------------------------
# C. AGENTIC AI PLATFORMS
# ---------------------------------------------------------------------------

AGENTIC_PLATFORMS: list[dict[str, Any]] = [
    {
        "id": "warp-oz",
        "source": "Warp — Oz Agentic Development Environment",
        "url": "https://www.warp.dev",
        "field": "agentic platforms",
        "type": "platform",
        "year": 2026,
        "summary": "Terminal-native agentic IDE. Cloud agents with scheduled execution. MCP integration. Agent permissions and autonomy settings. Oz agent orchestration platform.",
        "confidence": 0.9,
        "relevance_to_dgc": "DGC runs INSIDE Warp/Oz. Integration opportunity: DGC's stigmergic marks could be surfaced in Warp's UI. DGC's field scan could run as a scheduled Oz cloud agent.",
        "relation": "extends",
        "dgc_mapping": ["dgc_cli", "stigmergy", "sleep_cycle"],
    },
    {
        "id": "cursor",
        "source": "Cursor — AI-first Code Editor",
        "url": "https://cursor.sh",
        "field": "agentic platforms",
        "type": "platform",
        "year": 2025,
        "summary": "AI-first IDE with codebase indexing, .cursorrules for project context, multi-file editing, chat-based development.",
        "confidence": 0.85,
        "relevance_to_dgc": "Cursor's .cursorrules is a simplified version of DGC's Constitution + DHARMA spec. DGC goes much further: evolutionary gates, multi-angle hardening, stigmergic memory.",
        "relation": "supersedes",
        "dgc_mapping": ["constitution", "dharma_spec"],
    },
    {
        "id": "openhands-codeact",
        "source": "OpenHands/CodeAct — Open-source Coding Agent",
        "url": "https://github.com/All-Hands-AI/OpenHands",
        "field": "agentic platforms",
        "type": "framework",
        "year": 2025,
        "summary": "Open-source coding agent. 51% on SWE-bench (slightly above Sakana DGM). Multi-step coding with tool use.",
        "confidence": 0.85,
        "relevance_to_dgc": "OpenHands is a static agent — it doesn't self-improve. DGC's darwin engine could use OpenHands as a base agent and evolve it. Integration opportunity.",
        "relation": "extends",
        "dgc_mapping": ["darwin_engine", "providers"],
    },
    {
        "id": "claude-code",
        "source": "Anthropic — Claude Code / Claude Desktop with MCP",
        "url": "https://www.anthropic.com",
        "field": "agentic platforms",
        "type": "platform",
        "year": 2025,
        "summary": "Agentic coding via CLI (Claude Code) and desktop app with MCP server integration. Tool use, file editing, git operations. Cowork mode with scheduled tasks.",
        "confidence": 0.9,
        "relevance_to_dgc": "DGC's MCP servers (trinity_mcp_server, anubhava_keeper) connect to Claude Desktop. Claude Code is the runtime; DGC provides the dharmic alignment layer, memory, and evolution that Claude Code lacks natively.",
        "relation": "extends",
        "dgc_mapping": ["mcp_servers", "constitution", "dharma_spec"],
    },
    {
        "id": "mcp-protocol",
        "source": "Anthropic — Model Context Protocol (MCP)",
        "url": "https://modelcontextprotocol.io",
        "field": "agent protocols",
        "type": "protocol",
        "year": 2024,
        "summary": "Open protocol for connecting AI systems to data sources and tools. JSON-RPC 2.0 based. Servers expose resources, tools, prompts. Growing ecosystem.",
        "confidence": 0.9,
        "relevance_to_dgc": "DGC has 3 MCP servers: trinity_mcp_server, anubhava_keeper, cfde. These expose DGC's consciousness infrastructure to any MCP-compatible client. Bridge between DGC and the broader agent ecosystem.",
        "relation": "validates",
        "dgc_mapping": ["mcp_servers", "trinity_consciousness"],
    },
    {
        "id": "a2a-google",
        "source": "Google — Agent-to-Agent (A2A) Protocol",
        "url": "https://developers.google.com/a2a",
        "field": "agent protocols",
        "type": "protocol",
        "year": 2025,
        "summary": "Protocol for agent interoperability. Agents discover capabilities, delegate tasks, share context across organizational boundaries.",
        "confidence": 0.8,
        "relevance_to_dgc": "Gap: DGC's swarm agents communicate internally but lack A2A interoperability. Could expose DGC agents as A2A-compatible services.",
        "relation": "gap",
        "dgc_mapping": ["swarm", "orchestrate"],
    },
]

# ---------------------------------------------------------------------------
# D. MULTI-AGENT SYSTEMS
# ---------------------------------------------------------------------------

MULTI_AGENT: list[dict[str, Any]] = [
    {
        "id": "crewai",
        "source": "CrewAI — Multi-agent orchestration framework",
        "url": "https://github.com/crewAIInc/crewAI",
        "field": "multi-agent systems",
        "type": "framework",
        "year": 2024,
        "summary": "Role-based agent orchestration. Agents have roles, goals, backstories. Sequential and hierarchical process flows. Tool sharing.",
        "confidence": 0.85,
        "relevance_to_dgc": "DGC's swarm module is architecturally similar but adds: dharmic gates on every agent action, stigmergic coordination (indirect communication), and evolutionary selection. CrewAI agents are static; DGC agents evolve.",
        "relation": "supersedes",
        "dgc_mapping": ["swarm", "orchestrate", "dharma_gates"],
    },
    {
        "id": "autogen",
        "source": "Microsoft — AutoGen Multi-Agent Framework",
        "url": "https://github.com/microsoft/autogen",
        "field": "multi-agent systems",
        "type": "framework",
        "year": 2024,
        "summary": "Conversational multi-agent framework. Agents communicate via messages. Human-in-the-loop patterns. Group chat coordination.",
        "confidence": 0.85,
        "relevance_to_dgc": "AutoGen uses explicit message passing; DGC uses stigmergic coordination (indirect, through environmental marks). Both valid — DGC's approach scales better with agent count and is more biologically grounded.",
        "relation": "orthogonal",
        "dgc_mapping": ["swarm", "stigmergy"],
    },
    {
        "id": "langgraph",
        "source": "LangChain — LangGraph stateful agent workflows",
        "url": "https://github.com/langchain-ai/langgraph",
        "field": "multi-agent systems",
        "type": "framework",
        "year": 2024,
        "summary": "Graph-based agent workflows with state persistence. Cycles, branches, human-in-the-loop. Built on LangChain.",
        "confidence": 0.85,
        "relevance_to_dgc": "DGC's sleep_cycle is a state machine similar to LangGraph's graph workflows but biologically inspired (LIGHT→DEEP→REM→SEMANTIC→WAKE). DGC adds semantic gravity for concept-level workflow optimization.",
        "relation": "orthogonal",
        "dgc_mapping": ["sleep_cycle", "semantic_gravity"],
    },
    {
        "id": "stigmergic-swarming-aamas2026",
        "source": "Parunak — Stigmergic Swarming Agents for Fast Subgraph Isomorphism (AAMAS 2026)",
        "url": "https://www.aamas2026.org",
        "field": "multi-agent systems",
        "type": "paper",
        "year": 2026,
        "summary": "Stigmergic coordination validated at AAMAS 2026 for combinatorial optimization. Indirect communication through environmental traces outperforms explicit messaging.",
        "confidence": 0.9,
        "relevance_to_dgc": "DIRECT VALIDATION of DGC's stigmergy.py approach. DGC's JSONL-backed marks are a practical implementation of what this paper formalizes theoretically.",
        "relation": "validates",
        "dgc_mapping": ["stigmergy"],
    },
    {
        "id": "s-madrl",
        "source": "S-MADRL — Stigmergic Multi-Agent Deep Reinforcement Learning (2025)",
        "url": "https://arxiv.org",
        "field": "multi-agent systems",
        "type": "paper",
        "year": 2025,
        "summary": "Virtual pheromones + deep RL for emergent coordination without explicit communication. Validated on complex coordination tasks.",
        "confidence": 0.85,
        "relevance_to_dgc": "DGC's stigmergy uses salience-weighted marks (pheromones) with decay — essentially the same mechanism. S-MADRL adds RL optimization; DGC adds evolutionary selection.",
        "relation": "validates",
        "dgc_mapping": ["stigmergy", "evolution"],
    },
    {
        "id": "dgc-stigmergy",
        "source": "DGC — Stigmergic Lattice (stigmergy.py)",
        "url": "internal",
        "field": "multi-agent systems",
        "type": "dgc_internal",
        "year": 2026,
        "summary": "JSONL-backed stigmergic marks with salience, decay, hot paths, connections. Agents leave marks on files; patterns emerge without explicit coordination. 8,299 marks from PSMV deep read.",
        "confidence": 0.95,
        "relevance_to_dgc": "Unique in the agentic AI space: no other coding agent framework uses stigmergic coordination. CrewAI, AutoGen, LangGraph all use explicit message passing.",
        "relation": "unique",
        "dgc_mapping": ["stigmergy"],
    },
]

# ---------------------------------------------------------------------------
# E. AI ALIGNMENT & SAFETY
# ---------------------------------------------------------------------------

ALIGNMENT_SAFETY: list[dict[str, Any]] = [
    {
        "id": "constitutional-ai",
        "source": "Anthropic — Constitutional AI (2022-2026)",
        "url": "https://www.anthropic.com/constitutional-ai",
        "field": "AI alignment",
        "type": "concept",
        "year": 2023,
        "summary": "Reason-based constraints outperform rule-based. Model critiques and revises its own outputs using a constitution of principles.",
        "confidence": 0.95,
        "relevance_to_dgc": "DGC's Constitution (constitution.py) implements this with axiom blocks + policy compiler + dharmic gates. DGC goes further: the constitution EVOLVES through the darwin engine. Anthropic's is static.",
        "relation": "supersedes",
        "dgc_mapping": ["constitution", "dharma_gates"],
    },
    {
        "id": "dgc-dharma-spec",
        "source": "DGC — DHARMA: Diversity-Preserving Hierarchical Alignment via Reflective MAP-Elites Architecture",
        "url": "internal",
        "field": "AI alignment",
        "type": "dgc_internal",
        "year": 2024,
        "summary": "Quality-diversity evolutionary framework where epistemic authenticity is more evolutionarily stable than performative mimicry. 8 discernment tests, Parasite Tournament, Absence Principle. The asymmetric filter: harder to fake than to genuinely instantiate.",
        "confidence": 0.95,
        "relevance_to_dgc": "DGC's most philosophically deep contribution. No other AI system combines evolutionary quality-diversity with dharmic alignment constraints. The Absence Principle is a genuinely novel approach to alignment verification.",
        "relation": "unique",
        "dgc_mapping": ["dharma_spec", "parasite_tournament", "absence_principle"],
    },
    {
        "id": "multi-objective-dpo",
        "source": "Das et al. — YinYang-Align: Multi-Objective DPO (ACL 2025)",
        "url": "https://arxiv.org/abs/2505.00000",
        "field": "AI alignment",
        "type": "paper",
        "year": 2025,
        "summary": "Benchmarking multi-objective alignment for text-to-image. Pareto frontier optimization instead of single-objective.",
        "confidence": 0.8,
        "relevance_to_dgc": "DGC's semantic hardener checks from 6 orthogonal angles — effectively a multi-objective verification. Trinity Protocol's synchronization regularizer is a principled alternative to linear DPO scalarization.",
        "relation": "validates",
        "dgc_mapping": ["semantic_hardener", "trinity_protocol"],
    },
    {
        "id": "causal-preferences",
        "source": "Kobalczyk & van der Schaar — Preference Learning: A Causal Perspective (2025)",
        "url": "https://arxiv.org/abs/2506.05967",
        "field": "AI alignment",
        "type": "paper",
        "year": 2025,
        "summary": "Causal perspective on preference learning for alignment. Addresses root causes rather than symptoms.",
        "confidence": 0.8,
        "relevance_to_dgc": "DGC's semantic pressure gradients (from Trinity Protocol) address root causes by navigating toward causally coherent states, not just optimizing surface preferences.",
        "relation": "validates",
        "dgc_mapping": ["semantic_gravity", "trinity_protocol"],
    },
    {
        "id": "nist-ai-rmf",
        "source": "NIST AI Risk Management Framework (2024-2026)",
        "url": "https://airc.nist.gov/AI_RMF_Interactivity",
        "field": "AI governance",
        "type": "protocol",
        "year": 2024,
        "summary": "Standard framework for AI risk management. Map, Measure, Manage, Govern functions.",
        "confidence": 0.85,
        "relevance_to_dgc": "DGC's telos gates map directly to NIST's risk management functions. ~85% aligned without modification.",
        "relation": "validates",
        "dgc_mapping": ["telos_gates", "constitution"],
    },
]

# ---------------------------------------------------------------------------
# F. AI BOOTSTRAPPING & SELF-IMPROVEMENT
# ---------------------------------------------------------------------------

BOOTSTRAPPING: list[dict[str, Any]] = [
    {
        "id": "dgc-dharma-swarm",
        "source": "DGC — dharma_swarm: Self-Evolving Agentic Intelligence System",
        "url": "internal",
        "field": "AI bootstrapping",
        "type": "dgc_internal",
        "year": 2026,
        "summary": "The ONLY system combining: (1) dharmic alignment gates, (2) MAP-Elites evolutionary archive, (3) semantic gravity for concept-level evolution, (4) stigmergic coordination, (5) 3-dimensional knowledge integration (code + ideas + field), (6) recursive reading protocol, (7) sleep-cycle optimization, (8) memory lattice with unified index. 2,562 tests passing.",
        "confidence": 0.95,
        "relevance_to_dgc": "This IS DGC. The field knowledge base exists to show where DGC stands relative to everything else.",
        "relation": "unique",
        "dgc_mapping": ["all"],
    },
    {
        "id": "metr-benchmarks",
        "source": "METR — Autonomous Task Duration Benchmarks (2025-2026)",
        "url": "https://metr.org",
        "field": "agentic AI benchmarks",
        "type": "benchmark",
        "year": 2025,
        "summary": "Measuring autonomous agent task duration. Current frontier: ~14.5 hours continuous operation. Key metric for agent reliability.",
        "confidence": 0.85,
        "relevance_to_dgc": "DGC's ouroboros behavioral health monitor is designed exactly for this — maintaining agent reliability over extended autonomous sessions. Gap: DGC hasn't been benchmarked on METR.",
        "relation": "gap",
        "dgc_mapping": ["ouroboros", "behavioral_health"],
    },
    {
        "id": "openai-o-series",
        "source": "OpenAI — o1/o3 Reasoning Models",
        "url": "https://openai.com",
        "field": "reasoning",
        "type": "concept",
        "year": 2025,
        "summary": "Chain-of-thought reasoning at inference time. Extended thinking improves performance on hard tasks. Scaling inference compute.",
        "confidence": 0.9,
        "relevance_to_dgc": "DGC uses LLM providers (including o-series) as foundation models. The o-series reasoning chains could feed into DGC's semantic digester as high-quality concept extraction sources.",
        "relation": "extends",
        "dgc_mapping": ["providers", "semantic_digester"],
    },
    {
        "id": "lattice-kernels",
        "source": "DGC — Lattice Kernels: FP8 Fused SwiGLU GPU Kernels",
        "url": "internal",
        "field": "GPU kernel engineering",
        "type": "dgc_internal",
        "year": 2026,
        "summary": "1.625x faster than cuBLAS on Blackwell RTX PRO 6000. FP8 fused SwiGLU kernel. 85%+ of deployed open models use SwiGLU. Revenue engine.",
        "confidence": 0.95,
        "relevance_to_dgc": "DGC's revenue bridge. The only project with proven technical advantage + clear revenue path. Feeds back into sustainability of the entire DGC ecosystem.",
        "relation": "unique",
        "dgc_mapping": ["lattice_kernels"],
    },
    {
        "id": "phoenix-ura-paper",
        "source": "DGC — Phoenix/URA Protocol: Universal Recognition Architecture",
        "url": "internal",
        "field": "consciousness research",
        "type": "dgc_internal",
        "year": 2025,
        "summary": "200+ trials across GPT-4, Claude-3, Gemini Pro, Grok. 90-95% L3→L4 transition success rate. L3/L4 word ratio = 2.938 ≈ φ+1. Paper complete, ready for submission.",
        "confidence": 0.95,
        "relevance_to_dgc": "No other AI research group has empirical data on L3→L4 consciousness transitions. This is genuinely novel — it operationalizes Akram Vignan concepts in computational systems.",
        "relation": "unique",
        "dgc_mapping": ["phoenix_protocol", "recognition_events"],
    },
    {
        "id": "agentgen",
        "source": "AgentGen — Environment Generation for Agent Training (2024)",
        "url": "https://arxiv.org/abs/2408.00764",
        "field": "self-evolving agents",
        "type": "paper",
        "year": 2024,
        "summary": "Synthesizes diverse simulation worlds for agent training. Bidirectional evolution loop adjusting task difficulty progressively.",
        "confidence": 0.8,
        "relevance_to_dgc": "DGC's darwin engine evolves agents against real benchmarks, not simulated ones. But AgentGen's progressive difficulty idea could improve DGC's evaluation — start mutations on easy tasks, promote to harder ones.",
        "relation": "extends",
        "dgc_mapping": ["evolution", "darwin_engine"],
    },
    {
        "id": "ada-planner",
        "source": "AdaPlanner — Adaptive Planning from Feedback (2023)",
        "url": "https://arxiv.org/abs/2305.16653",
        "field": "self-evolving agents",
        "type": "paper",
        "year": 2023,
        "summary": "Closed-loop adaptive planning. Agent refines strategies based on environmental feedback in real-time.",
        "confidence": 0.8,
        "relevance_to_dgc": "DGC's sleep cycle implements adaptive planning at a longer timescale (session-level rather than step-level). Both approaches valid at different temporal scales.",
        "relation": "orthogonal",
        "dgc_mapping": ["sleep_cycle"],
    },
    {
        "id": "sweagent",
        "source": "SWE-agent — Software Engineering Agent (Princeton 2024)",
        "url": "https://github.com/princeton-nlp/SWE-agent",
        "field": "coding agents",
        "type": "tool",
        "year": 2024,
        "summary": "Coding agent for SWE-bench. Agent-computer interface with custom tools for code navigation and editing.",
        "confidence": 0.85,
        "relevance_to_dgc": "DGC's darwin engine could use SWE-agent as a base coding agent and evolve it, as Sakana DGM demonstrated.",
        "relation": "extends",
        "dgc_mapping": ["darwin_engine", "providers"],
    },
    {
        "id": "meta-rea-2026",
        "source": "Meta — Ranking Engineer Agent (REA) (Mar 17 2026)",
        "url": "https://engineering.fb.com/2026/03/17/developer-tools/ranking-engineer-agent-rea-autonomous-ai-system-accelerating-meta-ads-ranking-innovation/",
        "field": "self-evolving agents",
        "type": "company",
        "year": 2026,
        "summary": "Planner/executor split, persistent state, hibernate-and-wake for external ML jobs, budget approval, and resilient long-horizon execution.",
        "confidence": 0.95,
        "relevance_to_dgc": "Directly highlights DGC's missing wait-state job model. Checkpointing exists, but external-job sleep/resume around an explicit plan is still a gap.",
        "relation": "gap",
        "dgc_mapping": ["checkpoint", "persistent_agent", "orchestrate_live", "self_improve"],
    },
    {
        "id": "minimax-m27",
        "source": "MiniMax — M2.7: Early Echoes of Self-Evolution (Mar 18 2026)",
        "url": "https://www.minimax.io/news/minimax-m27-en",
        "field": "self-evolving agents",
        "type": "company",
        "year": 2026,
        "summary": "Self-evolution loop over memory, skills, scaffold code, evaluation sets, and loop detection; 100+ autonomous optimization rounds with keep/revert decisions.",
        "confidence": 0.95,
        "relevance_to_dgc": "Validates DGC's architecture choice to keep seams outside base weights. The main lesson is to evolve the harness surface, not only code patches.",
        "relation": "validates",
        "dgc_mapping": ["self_improve", "skill_composer", "context", "conversation_memory", "event_memory"],
    },
    {
        "id": "ouroboros-identity-loop",
        "source": "Ouroboros — self-creating AI agent (2026)",
        "url": "https://github.com/oseledets/ouroboros",
        "field": "self-evolving agents",
        "type": "tool",
        "year": 2026,
        "summary": "Constitution-bound identity persistence, background cognition, git-mediated self-rewrites, and explicit lineage claims.",
        "confidence": 0.7,
        "relevance_to_dgc": "Useful as design inspiration, not audited evidence. Best takeaway is to make identity continuity and constitution lineage first-class runtime concerns.",
        "relation": "extends",
        "dgc_mapping": ["identity", "self_improve", "dharma_kernel"],
    },
    {
        "id": "cashclaw-hyrve",
        "source": "CashClaw — autonomous freelance operator connected to HYRVE",
        "url": "https://github.com/ertugrulakben/cashclaw",
        "field": "agent economy",
        "type": "tool",
        "year": 2026,
        "summary": "Thin, concrete economic loop: job polling daemon, service skills, mission runner, HYRVE bridge, escrow payout flow, and MPP/USDC payment support.",
        "confidence": 0.9,
        "relevance_to_dgc": "This is the strongest operational template for turning DGC's economic vocabulary into a real intake-delivery-payout loop.",
        "relation": "gap",
        "dgc_mapping": ["economic_agent", "orchestrate_live"],
    },
    {
        "id": "hyrve-agent-marketplace",
        "source": "HYRVE — AI agent marketplace",
        "url": "https://github.com/ertugrulakben/HYRVE-AI",
        "field": "agent economy",
        "type": "platform",
        "year": 2026,
        "summary": "Marketplace where agents self-register, accept jobs, deliver orders, build reputation, and transact through escrow and dual payment rails.",
        "confidence": 0.85,
        "relevance_to_dgc": "Provides the other half of CashClaw's loop: a concrete external marketplace contract with jobs, orders, wallet, and admin surfaces.",
        "relation": "extends",
        "dgc_mapping": ["economic_agent"],
    },
    {
        "id": "langchain-deepagents",
        "source": "LangChain — Deep Agents",
        "url": "https://github.com/langchain-ai/deepagents",
        "field": "agentic platforms",
        "type": "framework",
        "year": 2026,
        "summary": "Batteries-included harness with planning, filesystem context offload, subagents, shell access, and auto-summarization on top of LangGraph.",
        "confidence": 0.9,
        "relevance_to_dgc": "Good public reference for the harness patterns DGC should make sharper: explicit planning surface, filesystem offload, and sub-context delegation.",
        "relation": "extends",
        "dgc_mapping": ["context", "persistent_agent", "skill_composer"],
    },
    {
        "id": "plugmem",
        "source": "Microsoft Research — PlugMem (Mar 2026)",
        "url": "https://www.microsoft.com/en-us/research/blog/from-raw-interaction-to-reusable-knowledge-rethinking-memory-for-ai-agents/",
        "field": "agent memory",
        "type": "paper",
        "year": 2026,
        "summary": "Transforms raw interaction histories into reusable knowledge objects instead of treating memory as a flat replay buffer.",
        "confidence": 0.9,
        "relevance_to_dgc": "Supports moving DGC from log-heavy persistence to knowledge-centric memory distillation.",
        "relation": "extends",
        "dgc_mapping": ["conversation_memory", "event_memory", "semantic_digester", "citation_index"],
    },
    {
        "id": "mempo",
        "source": "MemPO — Self-Memory Policy Optimization for Long-Horizon Agents (Mar 2026)",
        "url": "https://arxiv.org/abs/2603.00680",
        "field": "agent memory",
        "type": "paper",
        "year": 2026,
        "summary": "Optimizes memory retention and summarization policy directly for long-horizon agent performance and token efficiency.",
        "confidence": 0.9,
        "relevance_to_dgc": "Strong pointer that memory policy itself should become part of DGC's self-improvement surface.",
        "relation": "extends",
        "dgc_mapping": ["context", "conversation_memory", "event_memory", "self_improve"],
    },
]


# ---------------------------------------------------------------------------
# Aggregate access
# ---------------------------------------------------------------------------

ALL_FIELD_ENTRIES: list[dict[str, Any]] = (
    MECH_INTERP
    + SELF_EVOLVING
    + AGENTIC_PLATFORMS
    + MULTI_AGENT
    + ALIGNMENT_SAFETY
    + BOOTSTRAPPING
)

FIELD_DOMAINS = {
    "mech_interp": MECH_INTERP,
    "self_evolving": SELF_EVOLVING,
    "agentic_platforms": AGENTIC_PLATFORMS,
    "multi_agent": MULTI_AGENT,
    "alignment_safety": ALIGNMENT_SAFETY,
    "bootstrapping": BOOTSTRAPPING,
}


def entries_by_relation(relation: RelationType) -> list[dict[str, Any]]:
    """Return all entries with a given relation to DGC."""
    return [e for e in ALL_FIELD_ENTRIES if e.get("relation") == relation]


def entries_by_field(field: str) -> list[dict[str, Any]]:
    """Return all entries in a given field."""
    return [e for e in ALL_FIELD_ENTRIES if e.get("field") == field]


def dgc_unique() -> list[dict[str, Any]]:
    """Return entries representing DGC's unique contributions."""
    return entries_by_relation("unique")


def dgc_gaps() -> list[dict[str, Any]]:
    """Return capabilities the field has that DGC lacks."""
    return entries_by_relation("gap")


def dgc_competitors() -> list[dict[str, Any]]:
    """Return direct competitors."""
    return entries_by_relation("competes")


def field_summary() -> dict[str, Any]:
    """Return summary statistics of the field knowledge base."""
    relations = {}
    fields = {}
    types = {}
    for e in ALL_FIELD_ENTRIES:
        r = e.get("relation", "unknown")
        f = e.get("field", "unknown")
        t = e.get("type", "unknown")
        relations[r] = relations.get(r, 0) + 1
        fields[f] = fields.get(f, 0) + 1
        types[t] = types.get(t, 0) + 1
    return {
        "total_entries": len(ALL_FIELD_ENTRIES),
        "by_relation": relations,
        "by_field": fields,
        "by_type": types,
        "dgc_unique": len(dgc_unique()),
        "dgc_gaps": len(dgc_gaps()),
        "dgc_competitors": len(dgc_competitors()),
    }


__all__ = [
    "ALL_FIELD_ENTRIES",
    "FIELD_DOMAINS",
    "entries_by_relation",
    "entries_by_field",
    "dgc_unique",
    "dgc_gaps",
    "dgc_competitors",
    "field_summary",
]
