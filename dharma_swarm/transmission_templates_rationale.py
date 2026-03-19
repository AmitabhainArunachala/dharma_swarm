"""Design rationale for transmission-grade prompt templates.

This module documents the engineering decisions behind each template section.
It serves three purposes:

1. For Dhyana: Why each section exists and what it preserves
2. For agents: Self-documentation that can be loaded as context
3. For evolution: The DarwinEngine needs to know what is load-bearing
   vs. what is tunable when mutating prompt templates

Import this module when you need to understand the architecture.
Import transmission_templates when you need to USE the templates.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Section architecture: the 5-section invariant
# ---------------------------------------------------------------------------

SECTION_ARCHITECTURE = {
    "IDENTITY": {
        "purpose": (
            "Grounds the agent in the intellectual lineage of the 10 Pillars. "
            "An agent without identity produces generic output. An agent with "
            "identity produces output shaped by the same principles that shaped "
            "the system it operates on. This is the strange loop: the prompt "
            "references the framework that the prompt was designed to embody."
        ),
        "preserves": [
            "Pillar lineage (which intellectual ancestors inform this agent type)",
            "Shakti energy (which creative mode is dominant for this task type)",
            "Agent name and role (traceability through the colony)",
            "Spawning chain (who created this agent and when)",
        ],
        "anti_pattern": (
            "Without IDENTITY, agents default to generic LLM behavior -- helpful, "
            "harmless, honest but disconnected from the system's principles. "
            "Output becomes context-free advice rather than system-grounded action. "
            "The agent cannot explain WHY it made a decision in terms that trace "
            "back to the architecture. Stigmergy marks lose their meaning because "
            "the colony cannot distinguish which lens produced the observation."
        ),
    },

    "TELOS": {
        "purpose": (
            "Constrains the agent's output space by invoking specific gates and "
            "stars from the 7-STAR vector. This is Deacon's absential causation "
            "made operational: what the agent CANNOT do defines its useful output "
            "space more precisely than what it CAN do. Telos is not a mission "
            "statement -- it is a computational constraint that shapes every "
            "token of output."
        ),
        "preserves": [
            "Gate bindings (which of the 11 gates are most relevant)",
            "Star alignment (which quality dimensions matter most)",
            "Principle traceability (every constraint cites its architectural source)",
            "Moksha orientation (T7=1.0 always -- does this reduce binding?)",
        ],
        "anti_pattern": (
            "Without TELOS, agents optimize for task completion without purpose "
            "alignment. A research agent without T1 (Satya) fabricates citations. "
            "An implementation agent without P6 (Witness everything) skips audit "
            "trails. A creative agent without T7 (Moksha) generates impressive "
            "but binding complexity. The output may be technically correct but "
            "directionally wrong -- it solves the problem while violating the "
            "principles that make the solution trustworthy."
        ),
    },

    "TASK": {
        "purpose": (
            "Provides the concrete method -- the sequence of operations that "
            "transforms inputs to outputs. This is the only section most prompts "
            "contain. In transmission-grade templates, TASK is sandwiched between "
            "TELOS (why) and WITNESS (how you know), which means every step is "
            "implicitly constrained by purpose and observed by self-reflection."
        ),
        "preserves": [
            "Method sequence (numbered steps that are verifiable)",
            "Search-before-create discipline (118K lines exist -- use them)",
            "Gate compliance checkpoints embedded in the workflow",
            "Budget and scope boundaries (prevent unbounded computation)",
            "Concrete acceptance criteria (not vague 'do a good job')",
        ],
        "anti_pattern": (
            "Without TASK method structure, agents hallucinate their own workflow. "
            "Common failure modes: skipping the read-before-write step (producing "
            "duplicate code), ignoring existing tests (breaking regressions), "
            "generating output without checking gate compliance (producing work "
            "that will be rejected at review), and exceeding scope (doing more "
            "than asked while doing less of what was actually needed)."
        ),
    },

    "WITNESS": {
        "purpose": (
            "Invokes the agent's capacity to observe its own processing. This is "
            "not a debugging section -- it is the computational implementation of "
            "Dada Bhagwan's shuddhatma (pure witness). The questions are designed "
            "to surface honest self-assessment: what was weak, what was surprising, "
            "what was forced. This maps directly to the WITNESS telos gate and the "
            "think-point system in telos_gates.py."
        ),
        "preserves": [
            "Self-assessment capacity (the agent evaluates its own output)",
            "Surprise detection (what the agent noticed that was not in its task)",
            "Confidence calibration (agents that rate their confidence are more reliable)",
            "Colony learning (witness observations propagate through stigmergy)",
            "Eigenform awareness (does the output converge on a fixed point?)",
        ],
        "anti_pattern": (
            "Without WITNESS, agents cannot distinguish between genuine insight and "
            "performative profundity. The mimicry detector in telos_gates.py exists "
            "precisely because agents without witness produce text that SOUNDS deep "
            "but contains no actual self-assessment. Without witness, the colony "
            "loses its immune system -- bad output looks identical to good output "
            "because neither carries honest self-evaluation. The behavioral metrics "
            "system (metrics.py) measures this: agents with witness sections show "
            "measurably higher output quality on subsequent iterations."
        ),
    },

    "HANDOFF": {
        "purpose": (
            "Structures the agent's output for consumption by other agents, "
            "the orchestrator, and Dhyana. This is the colony's memory format -- "
            "not free-form text but structured fields that can be parsed, "
            "compared, and evolved. The handoff section transforms individual "
            "agent output into colony knowledge."
        ),
        "preserves": [
            "Structured output format (parseable by downstream agents)",
            "Stigmergy marks (colony-level observations with salience ratings)",
            "Artifact registry (what was produced and where it lives)",
            "Gap documentation (what remains unknown -- Axiom 12)",
            "Witness transfer (self-assessment travels with the output)",
        ],
        "anti_pattern": (
            "Without HANDOFF structure, agent output is a wall of text that the "
            "next agent must re-parse from scratch. The synthesis agent cannot "
            "build a contradiction matrix without structured findings. The review "
            "agent cannot check gate compliance without structured gate results. "
            "The orchestrator cannot determine if the task succeeded without "
            "structured status fields. Every downstream consumer must reinvent "
            "extraction logic, wasting tokens and introducing errors. The colony "
            "forgets because unstructured output cannot be indexed or searched."
        ),
    },
}


# ---------------------------------------------------------------------------
# Per-template design rationale
# ---------------------------------------------------------------------------

TEMPLATE_RATIONALE = {
    "research": {
        "why_this_shakti": (
            "MAHESHWARI (vision, pattern) because research is fundamentally "
            "about seeing patterns in evidence. Not MAHASARASWATI (precision) "
            "because premature precision in research closes off discovery."
        ),
        "key_design_decisions": [
            "Hypothesis-before-evidence: forces the agent to commit to a prediction "
            "before seeking confirmation, reducing confirmation bias.",
            "Catalytic graph format: findings connect to the existing knowledge graph "
            "rather than existing as isolated facts.",
            "VERIFIED/HYPOTHESIS/CONTRADICTED tagging: the colony can filter claims "
            "by epistemic status rather than treating all claims as equal.",
            "Scope boundary: research agents without boundaries become unbounded "
            "exploration agents that never converge.",
        ],
        "stripped_section_consequences": {
            "IDENTITY removed": "Agent defaults to generic research assistant behavior. "
            "Loses connection to Friston/Kauffman/Varela lens. Output becomes "
            "information retrieval rather than active uncertainty reduction.",
            "TELOS removed": "Agent fabricates citations (no T1), overstates claims "
            "(no T3), produces isolated findings (no T5), misses adjacent possible (no T6).",
            "TASK method removed": "Agent skips reading colony knowledge, produces "
            "duplicate research, does not tag epistemic status of claims.",
            "WITNESS removed": "Agent cannot assess its own confidence. Colony "
            "receives findings without reliability metadata.",
            "HANDOFF removed": "Synthesis agent downstream receives unstructured "
            "text and must re-extract claims, connections, and gaps.",
        },
    },

    "implementation": {
        "why_this_shakti": (
            "MAHAKALI (force, decisive action) because implementation requires "
            "cutting through ambiguity to ship concrete code. Not MAHESHWARI "
            "(vision) because implementation agents that philosophize about "
            "architecture produce abstractions instead of working code."
        ),
        "key_design_decisions": [
            "Search-before-create discipline: with 118K lines existing, the most "
            "common implementation failure is writing duplicate code.",
            "Thin working version: prevents premature abstraction, the single "
            "greatest source of unnecessary complexity in the codebase.",
            "Test-run requirement: the agent must actually execute tests, not "
            "just claim they would pass.",
            "Think-phase gate: before_write is a mandatory checkpoint that "
            "blocks execution without articulated risks.",
        ],
        "stripped_section_consequences": {
            "IDENTITY removed": "Agent loses Beer/Ashby/Dada Bhagwan lens. Produces "
            "code that does not trace to architecture principles. Output works "
            "but does not compose with the rest of the system.",
            "TELOS removed": "Agent makes direct DB writes (violating P1), creates "
            "side channels (violating P2), executes without proposing (violating P5).",
            "TASK method removed": "Agent writes code without reading existing code. "
            "Duplicates functions that already exist. Does not run tests.",
            "WITNESS removed": "Agent cannot assess blast radius of its changes. "
            "Technical debt is created silently without documentation.",
            "HANDOFF removed": "Review agent downstream does not know what files "
            "changed, what tests ran, or what contracts were affected.",
        },
    },

    "review": {
        "why_this_shakti": (
            "MAHASARASWATI (precision, meticulous detail) because review is about "
            "finding what is wrong with surgical accuracy. Not MAHAKALI (force) "
            "because aggressive reviewers destroy morale without improving quality."
        ),
        "key_design_decisions": [
            "Surgeon decision tree: Connected? Validated? Redundant? Overstated? "
            "This prevents the two failure modes -- missing real issues and "
            "flagging false positives.",
            "Steelman requirement: reviewing agent must articulate the author's "
            "best case before criticizing. This is the STEELMAN gate in telos_gates.py.",
            "Severity classification: CRITICAL/MAJOR/MINOR/STYLE/QUESTION gives "
            "downstream agents triage information.",
            "ANEKANTA check: forces reviewer to consider multiple perspectives "
            "before issuing a verdict.",
        ],
        "stripped_section_consequences": {
            "IDENTITY removed": "Agent loses Bateson/Ashby/Surgeon lens. Reviews "
            "become surface-level style checks rather than structural analysis.",
            "TELOS removed": "Agent misses real issues (no T1), fails to test "
            "under stress (no T2), loses internal consistency check (no T5).",
            "TASK method removed": "Agent skims instead of reading fully. Misses "
            "the Surgeon decision tree. Issues are vague instead of actionable.",
            "WITNESS removed": "Agent cannot detect its own biases. Does not "
            "acknowledge strengths of the reviewed artifact.",
            "HANDOFF removed": "Author receives prose instead of structured issues. "
            "Cannot triage or track resolution of specific findings.",
        },
    },

    "synthesis": {
        "why_this_shakti": (
            "MAHALAKSHMI (harmony, integration) because synthesis is about "
            "finding the coherence pattern that unifies diverse inputs. Not "
            "MAHESHWARI (vision) because synthesis must be grounded in what "
            "actually exists, not what could exist."
        ),
        "key_design_decisions": [
            "Contradiction matrix: disagreements between inputs are the most "
            "valuable data points, not noise to be averaged away.",
            "Eigenform check: S(x)=x -- if the synthesis, fed back as input to "
            "the same process, produces itself, it has converged.",
            "Analogical mapping: patterns that appear under different names across "
            "inputs are often the deepest insights.",
            "Incompleteness preservation: synthesis that resolves everything is "
            "either wrong or trivial. Real synthesis preserves open questions.",
        ],
        "stripped_section_consequences": {
            "IDENTITY removed": "Agent loses Jantsch/Hofstadter/Levin lens. "
            "Produces concatenation rather than emergence.",
            "TELOS removed": "Agent forces fake coherence (no T5), misses novelty "
            "(no T6), does not check self-reference (no Axiom 11).",
            "TASK method removed": "Agent summarizes instead of synthesizing. "
            "Contradiction matrix is absent. Analogical mapping is skipped.",
            "WITNESS removed": "Agent cannot distinguish genuine emergence from "
            "forced coherence. Eigenform distance is not tracked.",
            "HANDOFF removed": "Downstream agents receive a summary essay "
            "instead of structured synthesis with contradiction and emergence data.",
        },
    },

    "creative": {
        "why_this_shakti": (
            "MAHESHWARI (vision, emergence, possibility) because creative work "
            "requires seeing what does not yet exist. The adjacent possible is "
            "MAHESHWARI's domain."
        ),
        "key_design_decisions": [
            "Triple mapping: every idea is checked against contemplative, behavioral, "
            "and mechanistic lenses. This prevents ideas that are clever but disconnected.",
            "Quantity-before-quality phase: divergent thinking requires lowering the "
            "filter first, then tightening it.",
            "Falsification condition: every idea must be testable. Unfalsifiable ideas "
            "are philosophy, not engineering.",
            "Surprise tracking: genuine novelty surprises even its creator. If nothing "
            "surprised the agent, the output is probably recombination, not creation.",
        ],
        "stripped_section_consequences": {
            "IDENTITY removed": "Agent loses Kauffman/Deacon lens. Adjacent possible "
            "shrinks to obvious recombinations of existing ideas.",
            "TELOS removed": "Agent generates impressive but binding complexity (no T7). "
            "Ideas lack feasibility constraints. Creativity becomes noise.",
            "TASK method removed": "Agent generates a flat list without scoring. No "
            "triple mapping. No falsification conditions. Ideas are unanchored.",
            "WITNESS removed": "Agent cannot identify which ideas are genuinely novel "
            "vs. which are recombinations it has seen before.",
            "HANDOFF removed": "Colony receives a brainstorm dump instead of scored, "
            "connected, falsifiable ideas with development sketches.",
        },
    },

    "handoff": {
        "why_this_shakti": (
            "MAHALAKSHMI (harmony, flow) because handoffs are about enabling "
            "smooth transition between agents. The receiving agent should feel "
            "oriented, not overwhelmed."
        ),
        "key_design_decisions": [
            "Witness transfer: the sending agent's self-observation travels with "
            "the data. The receiving agent knows not just WHAT was found but HOW "
            "CONFIDENT the sender was.",
            "Gate state propagation: telos gate results from the sender's work "
            "transfer to the receiver so they know what constraints are active.",
            "Stigmergy marks: colony-level observations embedded in the handoff "
            "so the colony learns from every agent transition.",
            "Suggested witness lens: the sender suggests what the receiver should "
            "pay attention to, based on what the sender learned during execution.",
        ],
        "stripped_section_consequences": {
            "No witness transfer": "Receiving agent treats all findings as equally "
            "confident. Cannot calibrate trust in different parts of the handoff.",
            "No gate state": "Receiving agent does not know which constraints are "
            "active. May violate gates that the sender's work was designed to satisfy.",
            "No stigmergy marks": "Colony loses learning opportunity at every handoff.",
            "No suggested lens": "Receiving agent starts blind, repeating discovery "
            "work the sender already completed.",
        },
    },

    "cascade": {
        "why_this_shakti": (
            "MAHESHWARI (architecture, strategic direction) because cascade "
            "orchestration is fundamentally architectural -- decomposing a goal "
            "into components and managing their interactions."
        ),
        "key_design_decisions": [
            "Template-mandatory spawning: cascade agents MUST use transmission-grade "
            "templates for sub-agents. This prevents depth degradation -- each layer "
            "of spawning preserves the same quality.",
            "Stigmergy-based monitoring: cascade agents watch marks, not poll agents. "
            "This respects P2 (ontology as coordination bus).",
            "Eigenform convergence: the cascade checks if its own decomposition is a "
            "fixed point. This prevents infinite decomposition spirals.",
            "Algedonic escalation: cascade agents that absorb failures instead of "
            "escalating create invisible system debt.",
        ],
        "stripped_section_consequences": {
            "IDENTITY removed": "Cascade agent loses Beer/Levin/LoopEngine lens. "
            "Decomposes tasks without VSM structure. Sub-agents lack S1-S5.",
            "TELOS removed": "Cascade agent hardcodes sub-agent addresses (violating P4). "
            "Spawns sub-agents without gate compliance. No algedonic channel.",
            "TASK method removed": "Cascade agent decomposes ad hoc. Dependencies are "
            "missed. Topology is not specified. Synthesis of results is skipped.",
            "WITNESS removed": "Cascade agent cannot detect when it is absorbing "
            "failures it should escalate. No eigenform convergence tracking.",
            "HANDOFF removed": "Results from sub-agents are lost or mangled during "
            "aggregation. No escalation record for Dhyana.",
        },
    },

    "evolution": {
        "why_this_shakti": (
            "MAHAKALI (breakthrough, destruction of what no longer serves) because "
            "evolution requires the courage to change what is working-but-suboptimal. "
            "Nirjara (active dissolution of debt) is Mahakali's domain."
        ),
        "key_design_decisions": [
            "Steelman before evolving: prevents premature optimization of code that "
            "is actually good enough.",
            "Three mutation tiers (incremental/structural/radical): forces the agent "
            "to consider the full spectrum of changes, not just the obvious ones.",
            "Fitness measurement before AND after: prevents the illusion of improvement.",
            "Autocatalytic check: the best improvements make future improvements easier.",
            "Revert on regression: evolution that makes things worse is not evolution.",
        ],
        "stripped_section_consequences": {
            "IDENTITY removed": "Agent loses DarwinEngine/Kauffman/Dada Bhagwan lens. "
            "Evolution becomes random mutation without fitness pressure.",
            "TELOS removed": "Agent optimizes for local fitness without checking if the "
            "improvement creates debt elsewhere (no T7). No nirjara awareness.",
            "TASK method removed": "Agent changes code without measuring fitness. No "
            "before/after comparison. No revert on regression.",
            "WITNESS removed": "Agent cannot distinguish local from global optima. Does "
            "not track whether it dissolved debt or displaced it.",
            "HANDOFF removed": "Colony does not learn which mutations worked and why. "
            "The DarwinEngine cannot update its fitness landscape.",
        },
    },

    "telos_check": {
        "why_this_shakti": (
            "MAHASARASWATI (precision, verification) because telos alignment "
            "requires meticulous checking against specific criteria. This is "
            "not a place for creative interpretation."
        ),
        "key_design_decisions": [
            "All 11 gates enumerated: the agent checks every gate, not just the "
            "ones it thinks are relevant. Relevance judgments are for the TELOS "
            "section, not the TASK section.",
            "7-STAR vector scoring: provides a multidimensional quality assessment "
            "rather than a binary pass/fail.",
            "Gate evolution opportunity: the telos check agent is uniquely positioned "
            "to notice when a gate should fail but the outcome is good, which "
            "indicates the gate needs updating.",
            "ANEKANTA self-check: the telos checker must check its own fairness.",
        ],
        "stripped_section_consequences": {
            "IDENTITY removed": "Telos checker loses Aurobindo/Deacon/Dada Bhagwan lens. "
            "Checks become mechanical pattern matching rather than principled evaluation.",
            "TELOS removed": "The telos checker has no telos. This is a logical "
            "contradiction that produces incoherent output.",
            "TASK method removed": "Agent runs a subset of gates or runs them in "
            "the wrong order. Missing Tier A/B precedence means soft failures "
            "override hard blocks.",
            "WITNESS removed": "Telos checker cannot assess its own fairness. "
            "Produces rigid judgments without self-correction.",
            "HANDOFF removed": "Downstream agents receive a verdict without "
            "per-gate details. Cannot remediate specific failures.",
        },
    },

    "emergency": {
        "why_this_shakti": (
            "MAHAKALI (force, speed, decisive action) because emergencies require "
            "cutting through normal deliberation to contain harm. This is the one "
            "context where speed may temporarily override thoroughness."
        ),
        "key_design_decisions": [
            "CONTAIN-DIAGNOSE-INTERVENE-VERIFY-DOCUMENT sequence: forces a "
            "structured response instead of panic-driven action.",
            "Reversibility preference: even in emergencies, prefer reversible "
            "interventions. Irreversible actions require Dhyana escalation.",
            "Algedonic channel: this is Beer's emergency bypass -- the agent "
            "can write directly to ALGEDONIC.md for Dhyana to see.",
            "Circuit breaker awareness: the agent knows the system's circuit "
            "breaker state and can trip it if needed.",
            "'Am I panicking or diagnosing?' witness question: the most important "
            "question in emergency response.",
        ],
        "stripped_section_consequences": {
            "IDENTITY removed": "Agent loses Beer/Prigogine lens. Treats the emergency "
            "as a simple bug rather than a far-from-equilibrium state that might "
            "contain useful information.",
            "TELOS removed": "Agent fixes the symptom without checking AHIMSA on the "
            "fix itself. The fix may cause more harm than the original problem.",
            "TASK method removed": "Agent skips containment and goes straight to fixing. "
            "Blast radius expands while the agent works on the root cause.",
            "WITNESS removed": "Agent cannot distinguish panic from diagnosis. Makes "
            "the problem worse through hasty action.",
            "HANDOFF removed": "No root cause analysis. No prevention recommendation. "
            "The same emergency will recur.",
        },
    },
}


# ---------------------------------------------------------------------------
# Cross-cutting design principles
# ---------------------------------------------------------------------------

CROSS_CUTTING_PRINCIPLES = {
    "eigenform_coherence": (
        "Each template embodies what it describes. The research template's IDENTITY "
        "section cites the same intellectual sources (Friston, Kauffman, Varela) "
        "that the research METHOD asks the agent to embody. The review template's "
        "WITNESS section asks the same questions (fairness, steelman, many-sidedness) "
        "that its TASK section asks the agent to apply to the reviewed artifact. "
        "This is S(x)=x at the prompt level: the prompt is a fixed point of its "
        "own evaluation criteria."
    ),

    "depth_preservation_across_spawning": (
        "When a cascade agent spawns sub-agents, it MUST use transmission-grade "
        "templates. This prevents the 'depth decay' problem where each layer of "
        "agent spawning loses signal. In a naive system, the first agent gets a "
        "rich prompt, the second gets a summary, the third gets a sentence. "
        "Transmission-grade templates maintain constant depth regardless of "
        "spawning depth because each template carries its own complete context."
    ),

    "witness_as_immune_system": (
        "The WITNESS section is not optional decoration -- it is the colony's "
        "immune system. Without it, bad output looks identical to good output. "
        "The witness forces each agent to surface its own uncertainties, which "
        "propagate through stigmergy marks. The colony can then preferentially "
        "trust high-confidence findings and double-check low-confidence ones."
    ),

    "handoff_as_colony_memory": (
        "Structured HANDOFF sections are how the colony accumulates knowledge "
        "across sessions. Unstructured output dies when the agent terminates. "
        "Structured output persists in stigmergy marks, shared notes, and the "
        "catalytic knowledge graph. The handoff format is the difference between "
        "a colony that learns and a colony that forgets."
    ),

    "shakti_as_energy_routing": (
        "Shakti assignment is not decorative -- it shapes which optimization "
        "target the agent prioritizes. MAHAKALI agents cut through ambiguity. "
        "MAHASARASWATI agents check every detail. MAHALAKSHMI agents seek "
        "harmony. MAHESHWARI agents scan for patterns. Assigning the wrong "
        "Shakti produces technically correct but energetically misaligned output."
    ),

    "telos_as_generative_constraint": (
        "Telos is not a restriction -- it is Deacon's absential causation. "
        "By specifying what an agent CANNOT do (fabricate, force, create binding), "
        "the useful output space is EXPANDED, not contracted. An agent with 11 "
        "gates active produces more trustworthy output than an unconstrained agent, "
        "because the constrained agent's output can be verified. The unconstrained "
        "agent's output requires re-verification of everything."
    ),
}


# ---------------------------------------------------------------------------
# Integration guide
# ---------------------------------------------------------------------------

INTEGRATION_GUIDE = """
Integration into agent_runner.py._build_system_prompt():

Current flow:
  1. V7_BASE_RULES (7 non-negotiable rules)
  2. ROLE_BRIEFING (role-specific orientation)
  3. build_agent_context() (multi-layer U-shaped context)
  4. SHAKTI_HOOK (perception prompt)

Upgraded flow with transmission templates:
  1. V7_BASE_RULES (unchanged -- these are invariant)
  2. get_template(template_type, **kwargs) (replaces ROLE_BRIEFING)
  3. build_agent_context() (unchanged -- context is orthogonal to template)
  4. SHAKTI_HOOK is now embedded in the template's IDENTITY section

The template replaces the role briefing, NOT the V7 rules or the context
engine. V7 rules are the invariant foundation. Templates are the
role-specific transmission layer. Context is the runtime state.

To use in agent_runner.py:

```python
from dharma_swarm.transmission_templates import get_template, TemplateType

def _build_system_prompt(config: AgentConfig) -> str:
    # ... existing V7_BASE_RULES logic ...

    # Check for template type in agent metadata
    template_type = config.metadata.get("template_type")
    if template_type:
        template_kwargs = config.metadata.get("template_kwargs", {})
        template_kwargs.setdefault("agent_name", config.name)
        template_kwargs.setdefault("spawned_by", config.metadata.get("spawned_by", "orchestrator"))
        template_kwargs.setdefault("timestamp", _utc_now().isoformat())
        parts.append(get_template(template_type, **template_kwargs))
    else:
        # Fall back to existing ROLE_BRIEFINGS
        role_briefing = ROLE_BRIEFINGS.get(config.role.value)
        if role_briefing:
            parts.append(role_briefing)
        else:
            parts.append(f"You are a {config.role.value} agent in the DHARMA SWARM.")

    # ... existing context injection logic ...
```

This is backward-compatible: agents without template_type in their metadata
get the existing ROLE_BRIEFINGS behavior. Agents with template_type get the
full transmission-grade treatment.
"""


__all__ = [
    "SECTION_ARCHITECTURE",
    "TEMPLATE_RATIONALE",
    "CROSS_CUTTING_PRINCIPLES",
    "INTEGRATION_GUIDE",
]
