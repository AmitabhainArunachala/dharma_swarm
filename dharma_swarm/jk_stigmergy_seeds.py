"""
JK Stigmergy Seeds — High-salience marks encoding the Ruthless Critique findings.

These marks are injected into the stigmergy store so that ANY agent working
on JK tasks will encounter them through the PULL protocol (query_relevant).

Run once to seed. Idempotent — checks for existing marks before adding.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

# Late imports to avoid circular deps at module level


async def seed_critique_marks() -> int:
    """Inject high-salience stigmergy marks from the 2026-03-21 Ruthless Critique.

    Returns the number of marks injected.
    """
    from dharma_swarm.stigmergy import StigmergyStore, StigmergicMark

    store = StigmergyStore()
    injected = 0
    now = datetime.now(timezone.utc).isoformat()

    marks = [
        StigmergicMark(
            id="jk_critique_001",
            timestamp=now,
            agent="sage-critic",
            file_path="dharma_swarm/jagat_kalyan.py",
            action="scan",
            observation=(
                "CREDIBILITY STACK BROKEN at Layer 0: DBC (27,825 wt) vs Eden "
                "(588.5 wt) contradiction in proof artifacts. Fix truth ledger "
                "BEFORE any external submission."
            ),
            salience=0.95,
            connections=[
                "~/.dharma/shared/jk_welfare_ton_proof.md",
                "dharma_swarm/jk_credibility_gates.py",
                "docs/missions/JK_CREDIBILITY_STACK_MISSION_2026-03-21.md",
            ],
            access_count=0,
            channel="governance",
        ),
        StigmergicMark(
            id="jk_critique_002",
            timestamp=now,
            agent="sage-critic",
            file_path="dharma_swarm/jagat_kalyan.py",
            action="scan",
            observation=(
                "INVISIBLE TO WORLD: 118K lines, 4300 tests, $0 revenue, "
                "0 public repos, 0 websites, 0 papers, 0 users. A system "
                "nobody can see is equivalent to not existing."
            ),
            salience=0.92,
            connections=[
                "docs/missions/JK_CREDIBILITY_STACK_MISSION_2026-03-21.md",
                "dharma_swarm/jk_subteams.py",
            ],
            access_count=0,
            channel="strategy",
        ),
        StigmergicMark(
            id="jk_critique_003",
            timestamp=now,
            agent="sage-critic",
            file_path="~/.dharma/shared/jk_welfare_ton_proof.md",
            action="scan",
            observation=(
                "PROOF NOT AUDITABLE: 5+ citations rely on private sources "
                "(Eden payment records, payroll audit, FPIC package, Salesforce "
                "CRM, WhatsApp group). Not proof to a buyer, registry, or reviewer."
            ),
            salience=0.90,
            connections=[
                "dharma_swarm/jk_credibility_gates.py",
                "dharma_swarm/jk_credibility_seed.py",
            ],
            access_count=0,
            channel="governance",
        ),
        StigmergicMark(
            id="jk_critique_004",
            timestamp=now,
            agent="sage-critic",
            file_path="dharma_swarm/jk_credibility_seed.py",
            action="connect",
            observation=(
                "PRODUCT WEDGE: Don't build marketplace. Build micro-SaaS for "
                "just-transition carbon diligence: ingest docs → output C/E/A/B/V/P "
                "scores with confidence bands + standards crosswalk. Freemium."
            ),
            salience=0.88,
            connections=[
                "docs/missions/JK_CREDIBILITY_STACK_MISSION_2026-03-21.md",
                "dharma_swarm/jk_subteams.py",
            ],
            access_count=0,
            channel="strategy",
        ),
        StigmergicMark(
            id="jk_critique_005",
            timestamp=now,
            agent="sage-critic",
            file_path="dharma_swarm/jk_subteams.py",
            action="connect",
            observation=(
                "COMPETITION: Sylvera ($96M), BeZero ($50M+), Calyx (Moody's). "
                "GS and Verra do co-benefits. Our opening: joint tradeable unit "
                "+ diligence + allocation logic. Narrow but real."
            ),
            salience=0.85,
            connections=[
                "dharma_swarm/jk_credibility_seed.py",
            ],
            access_count=0,
            channel="research",
        ),
        StigmergicMark(
            id="jk_critique_006",
            timestamp=now,
            agent="sage-critic",
            file_path="docs/missions/JK_CREDIBILITY_STACK_MISSION_2026-03-21.md",
            action="connect",
            observation=(
                "GLOBAL BLIND SPOTS: China CETS (world's largest carbon market), "
                "India (100M+ displaced workers), Article 6.4, TNFD, EU CBAM, "
                "Just Transition Fund, COP31 Australia 2026. Scan is still "
                "Western-centric."
            ),
            salience=0.85,
            connections=[
                "dharma_swarm/jk_credibility_seed.py",
                "dharma_swarm/jagat_kalyan.py",
            ],
            access_count=0,
            channel="research",
        ),
        StigmergicMark(
            id="jk_critique_007",
            timestamp=now,
            agent="sage-critic",
            file_path="dharma_swarm/jk_credibility_gates.py",
            action="connect",
            observation=(
                "FORMULA NAIVE: W = C*E*A*B*V*P weights arbitrary. No derivation "
                "for multiply vs add. No adversarial stress-test or sensitivity "
                "analysis. Good metric papers include gaming analysis."
            ),
            salience=0.87,
            connections=[
                "~/.dharma/shared/jk_welfare_ton_proof.md",
                "dharma_swarm/jk_credibility_seed.py",
            ],
            access_count=0,
            channel="governance",
        ),
    ]

    for mark in marks:
        # Check if mark already exists (idempotent)
        existing = await store.read_marks(mark.file_path, limit=50)
        already_exists = any(m.id == mark.id for m in existing)
        if not already_exists:
            await store.leave_mark(mark)
            injected += 1

    return injected


def seed_sync() -> int:
    """Synchronous wrapper for seeding."""
    return asyncio.run(seed_critique_marks())


if __name__ == "__main__":
    count = seed_sync()
    print(f"Seeded {count} stigmergy marks from Ruthless Critique")
