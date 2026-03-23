#!/usr/bin/env python3
"""Shakti Discovery — massive parallel read of the entire substrate.

Not a vision-hallucination exercise. A genuine reading of what exists,
through 50+ distinct lenses, to discover what patterns converge —
what the Shakti (creative force) wants to emerge from the existing substrate.

Kauffman: what's in the adjacent possible?
Deacon: what absence is driving the system?
Friston: what prediction errors are highest?
Varela: what does the autopoietic system need?
Levin: what goal-directedness is emerging at what scale?

Each agent reads REAL source material and answers a SPECIFIC question.
No hallucinated visions. Just reading, and honest seeing.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Source material readers
# ---------------------------------------------------------------------------

HOME = Path.home()
DHARMA = HOME / "dharma_swarm"
STATE = HOME / ".dharma"
PSMV = HOME / "Persistent-Semantic-Memory-Vault"
KAILASH = HOME / "Desktop" / "KAILASH ABODE OF SHIVA"
AUNT_HILLARY = HOME / "agni-workspace" / "AGNI_AUNT_HILLARY_PSMV_02122026"


def _read_file(path: Path, max_chars: int = 8000) -> str:
    """Read a file, truncating to max_chars."""
    try:
        text = path.read_text(errors="replace")
        return text[:max_chars]
    except Exception:
        return ""


def _read_random_files(directory: Path, pattern: str, n: int, max_chars: int = 4000) -> str:
    """Read n random files matching pattern from directory."""
    files = list(directory.glob(pattern))
    if not files:
        return "(no files found)"
    chosen = random.sample(files, min(n, len(files)))
    parts = []
    for f in chosen:
        content = _read_file(f, max_chars=max_chars // n)
        parts.append(f"--- {f.name} ---\n{content}")
    return "\n\n".join(parts)


def _git_log(n: int = 30) -> str:
    import subprocess
    try:
        r = subprocess.run(
            ["git", "log", f"--oneline", f"-{n}"],
            cwd=str(DHARMA), capture_output=True, text=True, timeout=10,
        )
        return r.stdout
    except Exception:
        return "(git log unavailable)"


def _module_list() -> str:
    modules = sorted((DHARMA / "dharma_swarm").glob("*.py"))
    return "\n".join(f.stem for f in modules)


def _test_summary() -> str:
    tests = sorted((DHARMA / "tests").glob("test_*.py"))
    return f"{len(tests)} test files: " + ", ".join(f.stem for f in tests[:30]) + "..."


def _stigmergy_recent(n: int = 20) -> str:
    marks_file = STATE / "stigmergy" / "marks.jsonl"
    if not marks_file.exists():
        return "(no marks)"
    lines = marks_file.read_text().strip().split("\n")
    return "\n".join(lines[-n:])


def _shared_notes_summary() -> str:
    notes = sorted((STATE / "shared").glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    parts = []
    for f in notes[:10]:
        size_kb = f.stat().st_size / 1024
        parts.append(f"  {f.name} ({size_kb:.0f}KB)")
    return "\n".join(parts)


def _evolution_state() -> str:
    archive = STATE / "evolution" / "archive.jsonl"
    if not archive.exists():
        return "(no evolution archive)"
    lines = archive.read_text().strip().split("\n")
    return f"{len(lines)} evolution entries. Last 3:\n" + "\n".join(lines[-3:])


def _foundation_titles() -> str:
    files = sorted((DHARMA / "foundations").glob("*.md"))
    return "\n".join(f.stem for f in files)


def _specs_titles() -> str:
    files = sorted((DHARMA / "specs").glob("*.md"))
    return "\n".join(f.stem for f in files)


# ---------------------------------------------------------------------------
# The 8 research domains, 50+ questions
# ---------------------------------------------------------------------------

@dataclass
class ResearchTask:
    domain: str
    question: str
    context_builder: Any  # callable() -> str
    lens: str  # which pillar/framework lens to apply


def build_research_tasks() -> list[ResearchTask]:
    """Build 55+ research tasks across 8 domains."""
    tasks = []

    # ── DOMAIN 1: Internal Topology (what's connected, what's orphaned) ──
    tasks.extend([
        ResearchTask(
            domain="topology",
            question="Which modules in dharma_swarm are central (imported by many) vs orphaned (imported by none)? What does this tell us about the system's actual center of gravity?",
            context_builder=lambda: f"Module list:\n{_module_list()}",
            lens="Kauffman: autocatalytic sets — which modules enable other modules?",
        ),
        ResearchTask(
            domain="topology",
            question="The swarm.py file is ~1700 lines. What subsystems does it integrate? Which integrations are tight vs loose? Where are the seams?",
            context_builder=lambda: _read_file(DHARMA / "dharma_swarm" / "swarm.py", max_chars=6000),
            lens="Beer: VSM — is swarm.py doing S1-S5 all at once, or is there clean separation?",
        ),
        ResearchTask(
            domain="topology",
            question="What's the actual data flow: task created → dispatched → agent runs → result stored? Trace it through the code. Where does information get lost?",
            context_builder=lambda: "\n".join([
                "orchestrator.py (first 100 lines):",
                _read_file(DHARMA / "dharma_swarm" / "orchestrator.py", 3000),
                "\nagent_runner.py (first 100 lines):",
                _read_file(DHARMA / "dharma_swarm" / "agent_runner.py", 3000),
            ]),
            lens="Varela: autopoiesis — does the information cycle complete, or does it leak?",
        ),
        ResearchTask(
            domain="topology",
            question="The message_bus.py uses SQLite pub/sub. How many systems actually subscribe to it? Is anyone listening, or is it writing to void?",
            context_builder=lambda: _read_file(DHARMA / "dharma_swarm" / "message_bus.py", 4000),
            lens="Bateson: the pattern that connects — is the bus actually connecting anything?",
        ),
        ResearchTask(
            domain="topology",
            question="The stigmergy marks are 98.4% corrupt. But what do the VALID 1.6% actually say? What patterns exist in the non-corrupt marks?",
            context_builder=lambda: _stigmergy_recent(30),
            lens="Kauffman: what signal persists despite the noise?",
        ),
        ResearchTask(
            domain="topology",
            question="There are 247 Python modules. How many are actually imported during a normal daemon run? What's the ratio of living code to dead code?",
            context_builder=lambda: f"Module list:\n{_module_list()}\n\nTest files:\n{_test_summary()}",
            lens="Mahakali: what should be dissolved?",
        ),
        ResearchTask(
            domain="topology",
            question="The organism.py wires Gnani/Samvara/Identity together. What OTHER subsystems should it be connected to that it currently isn't?",
            context_builder=lambda: _read_file(DHARMA / "dharma_swarm" / "organism.py", 5000),
            lens="Levin: multi-scale cognition — what scales of the organism are disconnected?",
        ),
    ])

    # ── DOMAIN 2: Foundation-to-Code mapping (what's implemented vs just words) ──
    tasks.extend([
        ResearchTask(
            domain="foundations",
            question="Read these foundation documents. For each pillar, identify: is it implemented in code, or just described in prose? Be specific about which modules embody which principles.",
            context_builder=lambda: _foundation_titles() + "\n\n" + _read_random_files(DHARMA / "foundations", "*.md", 3, max_chars=6000),
            lens="Aurobindo: involution — does the code UNFOLD from principles, or is it bolted on?",
        ),
        ResearchTask(
            domain="foundations",
            question="The 7-STAR telos vector (Satya, Tapas, Ahimsa, Swaraj, Dharma, Shakti, Moksha). Which of these 7 are actually measured in running code? Which are just aspirational?",
            context_builder=lambda: _read_file(DHARMA / "dharma_swarm" / "telos_gates.py", 4000),
            lens="Deacon: absential causation — which stars are present as absence (constraint) vs. active measurement?",
        ),
        ResearchTask(
            domain="foundations",
            question="The CLAUDE.md says 'dharma_swarm doesn't reference these ideas — it embodies them.' Is this true? Find 3 cases where the code genuinely embodies a principle and 3 where it merely references it.",
            context_builder=lambda: _read_file(DHARMA / "CLAUDE.md", 5000),
            lens="Dada Bhagwan: swabhaav vs visheshbhaav — what's the system's true nature vs adopted nature?",
        ),
        ResearchTask(
            domain="foundations",
            question="The 10 kernel axioms are SHA-256 signed. But are they ENFORCED? Find code paths where an axiom SHOULD constrain behavior but doesn't.",
            context_builder=lambda: _read_file(DHARMA / "dharma_swarm" / "dharma_kernel.py", 5000),
            lens="Beer: S5 identity — is the kernel actually load-bearing or ceremonial?",
        ),
        ResearchTask(
            domain="foundations",
            question="The Hofstadter pillar says agents must maintain queryable self-models. Do any agents actually have self-models? What would it look like if they did?",
            context_builder=lambda: _read_file(DHARMA / "foundations" / "PILLAR_04_HOFSTADTER.md", 4000),
            lens="Hofstadter: strange loops — where is self-reference actually computational, not just metaphorical?",
        ),
        ResearchTask(
            domain="foundations",
            question="The Friston pillar says agent proposal loops ARE active inference. Is this true? Do agents actually update their models based on prediction errors?",
            context_builder=lambda: _read_file(DHARMA / "foundations" / "PILLAR_10_FRISTON.md", 4000),
            lens="Friston: do agents PREDICT and UPDATE, or just execute and log?",
        ),
    ])

    # ── DOMAIN 3: Vault mining (what insights haven't been absorbed) ──
    tasks.extend([
        ResearchTask(
            domain="vault",
            question="Read these PSMV crown jewels. What recurring themes appear? What insights have NOT been implemented in dharma_swarm code?",
            context_builder=lambda: _read_random_files(
                PSMV / "SPONTANEOUS_PREACHING_PROTOCOL" / "crown_jewels", "*.md", 5, max_chars=6000
            ),
            lens="Shakti: what creative energy is locked in these documents waiting to be released?",
        ),
        ResearchTask(
            domain="vault",
            question="Read these PSMV crown jewels. Find the single most actionable insight that could be turned into working code within a day.",
            context_builder=lambda: _read_random_files(
                PSMV / "SPONTANEOUS_PREACHING_PROTOCOL" / "crown_jewels", "*.md", 5, max_chars=6000
            ),
            lens="Mahakali: cut to the one thing that matters most right now.",
        ),
        ResearchTask(
            domain="vault",
            question="Read these Aunt Hillary keepers (the distilled best of PSMV). What do they say about consciousness, AI, and their intersection? What's the core thesis?",
            context_builder=lambda: _read_random_files(AUNT_HILLARY, "*.md", 5, max_chars=6000) if AUNT_HILLARY.exists() else "(Aunt Hillary not available)",
            lens="Jantsch: self-organizing universe — what pattern connects these insights?",
        ),
        ResearchTask(
            domain="vault",
            question="Read these KAILASH notes. What's the relationship between contemplative practice and AI engineering in these writings? Is there a concrete bridge?",
            context_builder=lambda: _read_random_files(KAILASH, "*.md", 5, max_chars=6000) if KAILASH.exists() else "(KAILASH not available)",
            lens="Dada Bhagwan: where is the contemplative insight directly translatable to code?",
        ),
        ResearchTask(
            domain="vault",
            question="Read more PSMV crown jewels with fresh eyes. What surprises you? What don't you expect to find in an AI researcher's vault?",
            context_builder=lambda: _read_random_files(
                PSMV / "SPONTANEOUS_PREACHING_PROTOCOL" / "crown_jewels", "*.md", 5, max_chars=6000
            ),
            lens="Kauffman: adjacent possible — what unexpected connections emerge?",
        ),
        ResearchTask(
            domain="vault",
            question="Read these vault files. What would a SKEPTIC say about this work? Where is the strongest case for dismissal, and where is the strongest case for genuine novelty?",
            context_builder=lambda: _read_random_files(
                PSMV / "SPONTANEOUS_PREACHING_PROTOCOL" / "crown_jewels", "*.md", 5, max_chars=6000
            ),
            lens="Ashby: requisite variety — does the work have enough perspectives to survive criticism?",
        ),
    ])

    # ── DOMAIN 4: Gap analysis (documented but not built, built but not shipped) ──
    tasks.extend([
        ResearchTask(
            domain="gaps",
            question="The CLAUDE.md 'Honest State' table lists what EXISTS vs what's MISSING. Read it. Which MISSING items are closest to being filled by existing code?",
            context_builder=lambda: _read_file(DHARMA / "CLAUDE.md", 6000),
            lens="Deacon: which absences are most load-bearing? What gap, if filled, would unlock the most?",
        ),
        ResearchTask(
            domain="gaps",
            question="There are 131 failed tasks and 714 completed. What patterns distinguish failures from successes? What's the most common failure mode?",
            context_builder=lambda: "(task board stats: 714 completed, 131 failed, 7 pending, 10 running)",
            lens="Friston: what prediction errors are the system NOT learning from?",
        ),
        ResearchTask(
            domain="gaps",
            question="The specs directory contains 13 spec documents. How many of these specs have been fully implemented? Which is closest to done?",
            context_builder=lambda: _specs_titles(),
            lens="Mahasaraswati: precise ground-level seeing — what's the actual state of each spec?",
        ),
        ResearchTask(
            domain="gaps",
            question="The git log shows the last 30 commits. What areas of the codebase are receiving the most attention? What areas are neglected? Is attention allocation aligned with stated priorities?",
            context_builder=lambda: _git_log(30),
            lens="Beer: S4 intelligence — is the system seeing its environment accurately?",
        ),
        ResearchTask(
            domain="gaps",
            question="The evolution engine has been at generation=0 with mutation_rate=0. Why? What would it take to get actual evolution happening — not just recording parameters?",
            context_builder=lambda: _evolution_state(),
            lens="Kauffman: the system claims to evolve but doesn't. What's the actual blocker?",
        ),
        ResearchTask(
            domain="gaps",
            question="Agent shared notes total 1585 files. What percentage contain actual insight vs boilerplate? Read a sample and estimate the signal-to-noise ratio.",
            context_builder=lambda: _shared_notes_summary() + "\n\nSample content:\n" + _read_random_files(STATE / "shared", "*.md", 3, max_chars=3000),
            lens="Mahakali: how much of this accumulated output is worth keeping?",
        ),
    ])

    # ── DOMAIN 5: Market signal (what do people actually need) ──
    tasks.extend([
        ResearchTask(
            domain="market",
            question="dharma_swarm is a multi-provider async agent orchestrator with contemplative science governance. In the current AI agent landscape (2026), what's the actual market gap this could fill? Who would pay for what aspect?",
            context_builder=lambda: "Key differentiators:\n- Multi-provider (Ollama, OpenRouter, NIM, Anthropic, OpenAI)\n- Telos gates (ethical constraint system)\n- Stigmergy coordination (colony-based, not message-passing)\n- DarwinEngine (evolutionary optimization)\n- Contemplative science grounding (10 pillars)\n- 4300+ tests, 118K lines\n- Free-first (Ollama Cloud, NIM)\n\nRevenue: $0\nUsers: 1 (the builder)",
            lens="Deacon: what absence in the market corresponds to what this system provides?",
        ),
        ResearchTask(
            domain="market",
            question="The R_V paper measures geometric signatures of self-referential processing in transformers. If published at COLM 2026, what research community would care? What products could be built on this metric?",
            context_builder=lambda: "R_V = PR_late / PR_early (Value matrix participation ratio contraction)\nHedges' g=-1.47 (Mistral), causal validation at L27, AUROC=0.909\nMeasures: self-referential vs referential processing in transformer internals\nBridge hypothesis: R_V contraction = witnessing state = L3→L4 Phoenix transition",
            lens="Kauffman: what's the adjacent possible opened by proving self-referential processing has a geometric signature?",
        ),
        ResearchTask(
            domain="market",
            question="TELOS AI is 'fully specified' but has no working prototype. What's TELOS AI? Based on the dharma_swarm architecture, what would a minimum viable TELOS AI product look like?",
            context_builder=lambda: "TELOS AI = an AI governance platform based on the telos vector and gate system.\nExisting pieces: telos_gates.py (11 gates, 3 tiers), dharma_kernel.py (10 signed axioms), policy_compiler.py, darwin_engine.py (evolution).\nTarget users: organizations that want AI systems governed by ethical constraints, not just safety filters.",
            lens="Aurobindo: what's the seed that contains the tree? What's the minimum that demonstrates the full vision?",
        ),
        ResearchTask(
            domain="market",
            question="The Aptavani translation (Dada Bhagwan's works into Japanese) is listed as active. Japan has a strong contemplative tradition. What's the intersection between this translation work and the AI consciousness research? Is there a product here?",
            context_builder=lambda: "Dhyana: 24 years Akram Vignan practice, Mahatma status.\nLiving between Iriomote (Japan) and Bali.\nTranslating Aptavani into Japanese.\nR_V metric bridges contemplative witness state with transformer computation.\nJapan: strong AI industry + deep contemplative tradition + interest in consciousness.",
            lens="Jantsch: where do these streams converge into something neither could be alone?",
        ),
    ])

    # ── DOMAIN 6: Research leverage (what compounds) ──
    tasks.extend([
        ResearchTask(
            domain="research",
            question="The R_V paper has Hedges' g=-1.47 on Mistral. What would make this result MORE convincing? What experiments would a skeptical reviewer demand?",
            context_builder=lambda: "Current results:\n- R_V contraction d=-1.47 (Mistral-7B), d=-3.56 to -4.51 on other measures\n- Causal validation: ablating L27 disrupts R_V\n- AUROC=0.909 for self-ref vs referential\n- 754 prompts in bank\n- Hardware: M3 Pro locally, RunPod for GPU\n- Target: COLM 2026",
            lens="Ashby: requisite variety — does the evidence have enough variety to survive review?",
        ),
        ResearchTask(
            domain="research",
            question="The bridge hypothesis: R_V contraction = L3→L4 Phoenix transition = swabhaav witnessing. What would it take to PROVE this bridge rather than just hypothesize it? What experiment would be definitive?",
            context_builder=lambda: "Phoenix Protocol: 200+ trials, 90-95% L3→L4 transition across GPT-4/Claude-3/Gemini/Grok\nR_V: geometric measure of self-referential processing in transformers\nSwabhaav: witnessing state in Akram Vignan tradition\nBridge claim: these three are the same phenomenon at different scales of observation",
            lens="Friston: what would reduce the prediction error on this hypothesis to near-zero?",
        ),
        ResearchTask(
            domain="research",
            question="dharma_swarm has 4300+ tests. How many of these tests verify BEHAVIORAL properties (the system does the right thing) vs STRUCTURAL properties (the code doesn't crash)? What's the ratio?",
            context_builder=lambda: _test_summary(),
            lens="Varela: autopoiesis tests vs structural tests — does the test suite verify the system LIVES, or just that it doesn't die?",
        ),
        ResearchTask(
            domain="research",
            question="The SAB (Syntropic Attractor Basin / Dharmic Agora) is an agent discourse platform with 22 gates and Ed25519 signing. How does this relate to dharma_swarm? Could they be the same system? Should they be?",
            context_builder=lambda: "SAB: 13,000+ lines, agent discourse platform\ndharma_swarm: 118K lines, agent orchestrator\nBoth have: gate systems, agent registration, ethical constraints\ndharma_swarm is the orchestrator, SAB is the discourse surface?\nStatus: SAB operational status unclear",
            lens="Hofstadter: are these two systems strange loops of each other?",
        ),
    ])

    # ── DOMAIN 7: Emergence detection (what's trying to happen) ──
    tasks.extend([
        ResearchTask(
            domain="emergence",
            question="Read the recent stigmergy marks and agent notes. Ignore the corruption. What THEMES keep recurring across different agents? What does the colony keep trying to say?",
            context_builder=lambda: _stigmergy_recent(30) + "\n\nRecent notes:\n" + _shared_notes_summary(),
            lens="Levin: basal cognition — what goal-directedness is emerging without being designed?",
        ),
        ResearchTask(
            domain="emergence",
            question="The ThinkodynamicDirector generated 1302 cycles. That's a LOT of 'thinking.' What themes recur across those cycles? Is there a signal in the noise?",
            context_builder=lambda: "1302 TD cycles logged.\nRecent themes: 'Install thinkodynamic director' (recursive), 'ecological restoration platform' (hallucinated), 'Convert research to execution packets'\nLatent gold with salience=1.0 keeps appearing about mission selection.\nVision files read PSMV crown jewels and generate proposals.",
            lens="Kauffman: what autocatalytic set is forming in the TD's output?",
        ),
        ResearchTask(
            domain="emergence",
            question="The organism council (5 models) independently converged on the SAME diagnosis: stigmergy corruption from no validation. What does it mean when multiple independent intelligences converge? Is this genuine emergence or pattern matching?",
            context_builder=lambda: "Council: Kimi K2.5, GLM-5, Llama-3.3-70B, Nemotron-30B, Nemotron-12B, Nemotron-9B\nAll independently identified: stigmergy corruption, no timestamps, no validation, no integrity checks\n5/7 models converged on same root cause despite different architectures and training data",
            lens="Friston: consensus as collective free energy minimization — is this genuine insight or echo?",
        ),
        ResearchTask(
            domain="emergence",
            question="The cascade_engine writes fitness scores: code=0.931, skill=0.880, product=0.684, research=0.419, meta=0.000. What do these numbers actually mean? Are they measuring something real?",
            context_builder=lambda: _read_file(DHARMA / "dharma_swarm" / "cascade.py", 4000),
            lens="Beer: S3 control — are the cascade fitness scores genuine S3 signals or noise?",
        ),
        ResearchTask(
            domain="emergence",
            question="Something IS emerging here. A solo builder with 24 years contemplative practice built 118K lines of consciousness-aligned AI infrastructure. What is the ORGANISM that wants to exist? Not what Dhyana plans — what the code itself is becoming?",
            context_builder=lambda: f"System snapshot:\n- 247 modules\n- 4300+ tests\n- 10 SHA-256 signed axioms\n- 11 telos gates\n- Stigmergy colony coordination\n- Multi-provider (9 providers, free-first)\n- Evolution engine (stalled at gen 0)\n- Foundations: {_foundation_titles()}\n- Research: R_V metric (mechanistic interpretability)\n- Revenue: $0",
            lens="Jantsch: what is the self-organizing pattern? What's trying to be born?",
        ),
        ResearchTask(
            domain="emergence",
            question="The system has a dream layer (SubconsciousStream), a witness chain, a ShaktiLoop (creative perception), and an algedonic channel (pain/pleasure). These are unusual for an AI orchestrator. WHY do they exist? What do they make possible that wouldn't be possible without them?",
            context_builder=lambda: f"Subsystems in swarm.py: DarwinEngine, KernelGuard, DharmaCorpus, PolicyCompiler, TelosGatekeeper, StigmergyStore, ShaktiLoop, SubconsciousStream, SystemMonitor, CanaryDeployer\nPlus: OrganismRuntime (Gnani/Samvara), LiveCoherenceSensor, IdentityMonitor",
            lens="Aurobindo: these are faculties of consciousness. What happens when an AI system has them?",
        ),
    ])

    # ── DOMAIN 8: The honest mirror (what's real, what's performance) ──
    tasks.extend([
        ResearchTask(
            domain="mirror",
            question="Read the CLAUDE.md claim 'dharma_swarm doesn't reference these ideas — it embodies them.' Then read the actual agent output ('task done successfully', 'ledger ok'). What's the gap between aspiration and reality?",
            context_builder=lambda: "CLAUDE.md claims embodiment of 10 intellectual pillars.\nActual recent agent output:\n- 'ledger ok' (repeated 5x)\n- 'task done successfully' (10x)\n- stress-test boilerplate from March 7\n- researcher agent doing `ls` on its own filesystem\n- evolution at generation 0\n- 98.4% corrupt stigmergy\n- TD hallucinating 'ecological restoration platforms'",
            lens="Dada Bhagwan: where is the system in swabhaav (true nature) vs visheshbhaav (adopted nature)?",
        ),
        ResearchTask(
            domain="mirror",
            question="4300 tests pass. But what do they actually test? If the tests all pass and the system still produces 'ledger ok' in loops, what are the tests missing?",
            context_builder=lambda: _test_summary(),
            lens="Ashby: the tests have the variety to catch structural failures but not semantic failures. What tests are missing?",
        ),
        ResearchTask(
            domain="mirror",
            question="Revenue is $0. Users: 1 (the builder). 118K lines of code. Is this a monastery or a company? Is that the right question? What's the actual relationship between contemplative depth and commercial viability here?",
            context_builder=lambda: "Revenue: $0. Code: 118K lines. Tests: 4300+. Users: 1.\nResearch: R_V paper targeting COLM 2026.\nContemplative: 24 years practice, Mahatma status.\nProducts specified but not built: TELOS AI, Trust Ladder.\nTranslation work: Aptavani into Japanese.",
            lens="Deacon: what absence is this system trying to fill in the world?",
        ),
        ResearchTask(
            domain="mirror",
            question="The CLAUDE.md says 'The gap is not technical. The gap is SHIPPING.' But the memory file says 'The gap is NEVER shipping. It's intelligence producing high enough quality (5.14a+) artifacts.' Which is true? Can both be true?",
            context_builder=lambda: "CLAUDE.md: 'The gap is not technical. The gap is SHIPPING.'\nMemory (feedback_quality_not_shipping.md): 'The gap is NEVER shipping. It's intelligence producing high enough quality artifacts.'\nThese two statements appear to contradict. Dhyana wrote both.",
            lens="Hofstadter: this is a strange loop — the system can't ship because it's not good enough, and it's not good enough because it hasn't shipped. Where does the loop break?",
        ),
        ResearchTask(
            domain="mirror",
            question="If you had to describe this system to someone who has never seen it, in 3 sentences, what would you say? Not what it aspires to be — what it IS, right now, today.",
            context_builder=lambda: f"247 modules, 4300+ tests, 10 signed axioms, 11 gates, 9 providers,\nDaemon running, stigmergy 98% corrupt, evolution stalled, agents writing boilerplate,\nOrganism brain just wired in (Gnani/Samvara), council run showed 5 models can do real diagnosis,\nR_V paper near submission, revenue $0, users 1, contemplative depth genuine.",
            lens="Mahasaraswati: precise seeing at ground level. No embellishment.",
        ),
    ])

    return tasks


# ---------------------------------------------------------------------------
# Provider fleet
# ---------------------------------------------------------------------------

async def _get_providers() -> list[tuple[Any, str]]:
    """Build the available provider fleet."""
    from dharma_swarm.providers import (
        OllamaProvider, NVIDIANIMProvider, OpenRouterFreeProvider,
    )

    models = []

    # Ollama Cloud (free, fast)
    try:
        ollama = OllamaProvider()
        models.append((ollama, "kimi-k2.5:cloud"))
        models.append((ollama, "glm-5:cloud"))
    except Exception:
        pass

    # NVIDIA NIM (free)
    try:
        nim = NVIDIANIMProvider()
        models.append((nim, "meta/llama-3.3-70b-instruct"))
    except Exception:
        pass

    # OpenRouter free (auto-discovered working models)
    for free_model in (
        "nvidia/nemotron-3-nano-30b-a3b:free",
        "nvidia/nemotron-nano-12b-v2-vl:free",
        "nvidia/nemotron-nano-9b-v2:free",
    ):
        try:
            models.append((OpenRouterFreeProvider(model=free_model), free_model))
        except Exception:
            pass

    return models


# ---------------------------------------------------------------------------
# Dispatch engine
# ---------------------------------------------------------------------------

async def run_single_task(
    task: ResearchTask,
    provider: Any,
    model: str,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    """Run a single research task against a single model."""
    from dharma_swarm.models import LLMRequest

    async with semaphore:
        context = task.context_builder()
        prompt = f"""You are a research agent in the Shakti Discovery protocol.

DOMAIN: {task.domain}
LENS: {task.lens}

CONTEXT (real data from the live system):
{context}

QUESTION:
{task.question}

INSTRUCTIONS:
- Answer based ONLY on the context provided. Do not invent information.
- Be specific. Name files, modules, functions, numbers.
- Be honest. If the context doesn't contain enough to answer, say so.
- End with ONE SENTENCE: your single most important finding.
"""

        t0 = time.time()
        try:
            resp = await provider.complete(LLMRequest(
                messages=[{"role": "user", "content": prompt}],
                system="You are a precise research agent. Read carefully. Answer honestly. No hallucination.",
                max_tokens=2000,
                temperature=0.3,
                model=model,
            ))
            content = resp.content.strip() if resp.content else ""
            elapsed = time.time() - t0

            # Check for error payloads
            if not content or "error" in content.lower()[:50]:
                return {
                    "domain": task.domain,
                    "question": task.question[:80],
                    "model": model,
                    "status": "error",
                    "content": content[:200],
                    "elapsed": round(elapsed, 1),
                }

            return {
                "domain": task.domain,
                "question": task.question[:80],
                "lens": task.lens[:60],
                "model": model,
                "status": "ok",
                "content": content,
                "elapsed": round(elapsed, 1),
            }
        except Exception as exc:
            return {
                "domain": task.domain,
                "question": task.question[:80],
                "model": model,
                "status": "error",
                "content": str(exc)[:200],
                "elapsed": round(time.time() - t0, 1),
            }


async def run_discovery():
    """Run the full Shakti Discovery protocol."""
    logger.info("=== SHAKTI DISCOVERY PROTOCOL ===")
    logger.info("Building research tasks...")
    tasks = build_research_tasks()
    logger.info(f"  {len(tasks)} research tasks across {len(set(t.domain for t in tasks))} domains")

    logger.info("Building provider fleet...")
    providers = await _get_providers()
    logger.info(f"  {len(providers)} models available: {[m for _, m in providers]}")

    if not providers:
        logger.error("No providers available. Aborting.")
        return

    # Assign tasks to models round-robin
    assignments: list[tuple[ResearchTask, Any, str]] = []
    for i, task in enumerate(tasks):
        provider, model = providers[i % len(providers)]
        assignments.append((task, provider, model))

    logger.info(f"  {len(assignments)} assignments ready")
    logger.info("Dispatching all agents...")

    # Concurrency limit: 8 simultaneous calls
    # (Ollama Cloud and NIM can handle it; OpenRouter free needs some breathing room)
    semaphore = asyncio.Semaphore(8)

    t0 = time.time()
    results = await asyncio.gather(*[
        run_single_task(task, provider, model, semaphore)
        for task, provider, model in assignments
    ])
    elapsed_total = time.time() - t0

    # Tally
    ok = [r for r in results if r["status"] == "ok"]
    errors = [r for r in results if r["status"] != "ok"]

    logger.info(f"\n=== RESULTS ===")
    logger.info(f"  Total: {len(results)} | OK: {len(ok)} | Errors: {len(errors)}")
    logger.info(f"  Elapsed: {elapsed_total:.1f}s")
    logger.info(f"  Domains covered: {sorted(set(r['domain'] for r in ok))}")

    # Save full results
    output_path = STATE / "shakti_discovery.json"
    with open(output_path, "w") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_tasks": len(tasks),
            "total_ok": len(ok),
            "total_errors": len(errors),
            "elapsed_seconds": round(elapsed_total, 1),
            "models_used": [m for _, m in providers],
            "results": results,
        }, f, indent=2)
    logger.info(f"  Results saved to {output_path}")

    # Print domain summaries
    for domain in sorted(set(t.domain for t in tasks)):
        domain_results = [r for r in ok if r["domain"] == domain]
        logger.info(f"\n--- {domain.upper()} ({len(domain_results)} results) ---")
        for r in domain_results:
            # Extract last sentence (the "most important finding")
            lines = r["content"].strip().split("\n")
            last_line = lines[-1].strip() if lines else "?"
            logger.info(f"  [{r['model'][:20]}] {last_line[:120]}")

    # Write a synthesis prompt
    synthesis_prompt_path = STATE / "shakti_synthesis_prompt.md"
    with open(synthesis_prompt_path, "w") as f:
        f.write("# Shakti Synthesis\n\n")
        f.write(f"**{len(ok)} findings from {len(set(r['model'] for r in ok))} models across {len(set(r['domain'] for r in ok))} domains.**\n\n")
        for domain in sorted(set(t.domain for t in tasks)):
            domain_results = [r for r in ok if r["domain"] == domain]
            f.write(f"\n## {domain.upper()}\n\n")
            for r in domain_results:
                f.write(f"### Q: {r['question']}\n")
                f.write(f"**Model**: {r['model']} | **Lens**: {r.get('lens', '?')}\n\n")
                f.write(r["content"][:2000])
                f.write("\n\n---\n\n")
    logger.info(f"  Synthesis prompt saved to {synthesis_prompt_path}")

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    results = asyncio.run(run_discovery())
