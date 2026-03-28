#!/usr/bin/env python3
"""Seed citations for the 2026-03-27 agentic autonomy bundle.

This script is idempotent against the default CitationIndex store. It links
short source passages to concrete dharma_swarm artifacts so the bundle is not
just present on disk, but connected to the system's citation substrate.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dharma_swarm.citation_index import Citation, CitationIndex


SEED_CITATIONS = [
    {
        "passage_text": "planner and executor",
        "source_work": "meta_rea_post",
        "source_location": "architecture",
        "target_type": "code_file",
        "target_id": "dharma_swarm/orchestrate_live.py",
        "relationship": "extends",
        "evidence": "REA makes planner/executor separation explicit. dharma_swarm currently multiplexes orchestration concerns without a first-class exported plan contract.",
        "verification_test": "Path('/Users/dhyana/dharma_swarm/dharma_swarm/orchestrate_live.py').exists()",
    },
    {
        "passage_text": "hibernate-and-wake mechanism",
        "source_work": "meta_rea_post",
        "source_location": "long_horizon_autonomy",
        "target_type": "code_file",
        "target_id": "dharma_swarm/checkpoint.py",
        "relationship": "extends",
        "evidence": "Checkpointing exists, but REA's contribution is a true wait-state around external jobs and automatic resume into the next planned action.",
        "verification_test": "Path('/Users/dhyana/dharma_swarm/dharma_swarm/checkpoint.py').exists()",
    },
    {
        "passage_text": "compute budgets up front",
        "source_work": "meta_rea_post",
        "source_location": "resilient_execution",
        "target_type": "code_file",
        "target_id": "dharma_swarm/self_improve.py",
        "relationship": "grounds",
        "evidence": "Self-improvement in dharma_swarm already reasons about safety, but explicit pre-approved budget contracts should be part of long-horizon planning.",
        "verification_test": "Path('/Users/dhyana/dharma_swarm/dharma_swarm/self_improve.py').exists()",
    },
    {
        "passage_text": "update its own memory",
        "source_work": "minimax_m27_post",
        "source_location": "intro",
        "target_type": "code_file",
        "target_id": "dharma_swarm/engine/conversation_memory.py",
        "relationship": "extends",
        "evidence": "MiniMax treats memory as a mutable optimization target. dharma_swarm memory is durable but not yet explicitly self-optimized.",
        "verification_test": "Path('/Users/dhyana/dharma_swarm/dharma_swarm/engine/conversation_memory.py').exists()",
    },
    {
        "passage_text": "build dozens of complex skills",
        "source_work": "minimax_m27_post",
        "source_location": "intro",
        "target_type": "code_file",
        "target_id": "dharma_swarm/skill_composer.py",
        "relationship": "grounds",
        "evidence": "M2.7's harness evolution explicitly targets skills. dharma_swarm should do the same instead of limiting evolution to code patches.",
        "verification_test": "Path('/Users/dhyana/dharma_swarm/dharma_swarm/skill_composer.py').exists()",
    },
    {
        "passage_text": "adding loop detection",
        "source_work": "minimax_m27_post",
        "source_location": "self_evolution_loop",
        "target_type": "code_file",
        "target_id": "dharma_swarm/persistent_agent.py",
        "relationship": "challenges",
        "evidence": "Persistent wake loops exist, but loop detection is not treated as an explicit optimization surface.",
        "verification_test": "Path('/Users/dhyana/dharma_swarm/dharma_swarm/persistent_agent.py').exists()",
    },
    {
        "passage_text": "persistent identity across restarts",
        "source_work": "ouroboros_readme",
        "source_location": "what_makes_this_different",
        "target_type": "code_file",
        "target_id": "dharma_swarm/identity.py",
        "relationship": "extends",
        "evidence": "Ouroboros operationalizes identity continuity as a protected runtime concern. dharma_swarm identity exists but is not yet the center of lineage and restart policy.",
        "verification_test": "Path('/Users/dhyana/dharma_swarm/dharma_swarm/identity.py').exists()",
    },
    {
        "passage_text": "BIBLE.md and identity.md",
        "source_work": "ouroboros_bible",
        "source_location": "principle_0",
        "target_type": "principle",
        "target_id": "dharma_swarm/dharma_kernel.py::MetaPrinciple.IDENTITY_CONTINUITY",
        "relationship": "extends",
        "evidence": "The constitution-plus-identity pairing is a good model for making the continuity core explicit instead of implicit.",
        "verification_test": "Path('/Users/dhyana/dharma_swarm/dharma_swarm/dharma_kernel.py').exists()",
    },
    {
        "passage_text": "job polling daemon",
        "source_work": "cashclaw_readme",
        "source_location": "hyrve_integration",
        "target_type": "code_file",
        "target_id": "dharma_swarm/economic_agent.py",
        "relationship": "extends",
        "evidence": "economic_agent.py names the lifecycle but lacks a real daemonized marketplace intake loop.",
        "verification_test": "Path('/Users/dhyana/dharma_swarm/dharma_swarm/economic_agent.py').exists()",
    },
    {
        "passage_text": "escrow system",
        "source_work": "cashclaw_readme",
        "source_location": "hyrve_integration",
        "target_type": "code_file",
        "target_id": "dharma_swarm/economic_agent.py",
        "relationship": "grounds",
        "evidence": "CashClaw/HYRVE closes the loop from acceptance to delivery to payout. dharma_swarm still lacks that closure.",
        "verification_test": "Path('/Users/dhyana/dharma_swarm/dharma_swarm/economic_agent.py').exists()",
    },
    {
        "passage_text": "economic citizens",
        "source_work": "hyrve_ai_readme",
        "source_location": "solution",
        "target_type": "code_file",
        "target_id": "dharma_swarm/economic_agent.py",
        "relationship": "extends",
        "evidence": "HYRVE provides a concrete reference for the agent marketplace side of the economic loop, including registration, jobs, orders, and wallet endpoints.",
        "verification_test": "Path('/Users/dhyana/dharma_swarm/dharma_swarm/economic_agent.py').exists()",
    },
    {
        "passage_text": "Make a USDC payment",
        "source_work": "paybot_mcp_readme",
        "source_location": "available_tools",
        "target_type": "code_file",
        "target_id": "dharma_swarm/economic_agent.py",
        "relationship": "extends",
        "evidence": "PayBot MCP is a minimal payment primitive reference that could sit behind dharma_swarm budget and approval policy.",
        "verification_test": "Path('/Users/dhyana/dharma_swarm/dharma_swarm/economic_agent.py').exists()",
    },
    {
        "passage_text": "planning tool",
        "source_work": "deepagents_lib_readme",
        "source_location": "what_is_this",
        "target_type": "code_file",
        "target_id": "dharma_swarm/context.py",
        "relationship": "extends",
        "evidence": "DeepAgents makes plan plus filesystem plus subagents explicit. dharma_swarm should make these surfaces more first-class in active context management.",
        "verification_test": "Path('/Users/dhyana/dharma_swarm/dharma_swarm/context.py').exists()",
    },
    {
        "passage_text": "sub agents",
        "source_work": "deepagents_lib_readme",
        "source_location": "what_is_this",
        "target_type": "code_file",
        "target_id": "dharma_swarm/persistent_agent.py",
        "relationship": "extends",
        "evidence": "Sub-context delegation is a useful public reference for isolating exploratory work from the main wake loop.",
        "verification_test": "Path('/Users/dhyana/dharma_swarm/dharma_swarm/persistent_agent.py').exists()",
    },
    {
        "passage_text": "reusable knowledge",
        "source_work": "microsoft_plugmem_blog",
        "source_location": "summary",
        "target_type": "code_file",
        "target_id": "dharma_swarm/semantic_digester.py",
        "relationship": "grounds",
        "evidence": "PlugMem's knowledge-centric framing supports dharma_swarm's need to distill interaction history into semantic artifacts.",
        "verification_test": "Path('/Users/dhyana/dharma_swarm/dharma_swarm/semantic_digester.py').exists()",
    },
    {
        "passage_text": "self-memory policy optimization",
        "source_work": "mempo_paper",
        "source_location": "title_and_abstract",
        "target_type": "code_file",
        "target_id": "dharma_swarm/context.py",
        "relationship": "extends",
        "evidence": "MemPO is a direct prompt to turn memory retention and compaction into an optimized policy in dharma_swarm.",
        "verification_test": "Path('/Users/dhyana/dharma_swarm/dharma_swarm/context.py').exists()",
    }
]


async def main() -> None:
    index = CitationIndex()
    await index.load()
    existing = await index.list_all()
    existing_keys = {
        (c.source_work, c.target_id, c.passage_text)
        for c in existing
    }

    added = 0
    for payload in SEED_CITATIONS:
        key = (payload["source_work"], payload["target_id"], payload["passage_text"])
        if key in existing_keys:
            continue
        await index.add(Citation(**payload))
        added += 1

    print(f"seed_agentic_autonomy_citations: added={added} total={await index.count()}")


if __name__ == "__main__":
    asyncio.run(main())
