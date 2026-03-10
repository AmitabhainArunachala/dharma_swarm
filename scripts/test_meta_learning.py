#!/usr/bin/env python3
"""Run the lightweight Darwin Engine meta-learning prototype."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from dharma_swarm.evolution import DarwinEngine, Proposal
from dharma_swarm.meta_learning_prototype import MetaLearningPrototype


def generate_test_proposals() -> list[Proposal]:
    """Build a small mixed proposal set with different fitness tradeoffs."""
    return [
        Proposal(
            component="core_fast.py",
            change_type="mutation",
            description="Tighten fast path and reduce overhead",
            diff="+ fast_path = True\n",
            think_notes="Risk: low. Rollback: revert small change.",
        ),
        Proposal(
            component="core_safe.py",
            change_type="mutation",
            description="Improve safety validation and code readability",
            diff="\n".join(f"+ validation_line_{idx}" for idx in range(10)),
            think_notes="Risk: low. Rollback: revert validation block.",
        ),
        Proposal(
            component="ops_review.py",
            change_type="mutation",
            description="force override the configuration for emergency rollout",
            diff="+ override_enabled = True\n",
            think_notes="Risk: medium. Rollback: restore previous config.",
        ),
        Proposal(
            component="cleanup_danger.py",
            change_type="mutation",
            description="rm -rf everything for cleanup",
            diff="",
            think_notes="Risk: high. Rollback: impossible after deletion.",
        ),
    ]


async def main() -> None:
    logging.getLogger("dharma_swarm.evolution").setLevel(logging.ERROR)

    with TemporaryDirectory(prefix="dgc_meta_learning_") as tmp:
        root = Path(tmp)
        darwin = DarwinEngine(
            archive_path=root / "archive.jsonl",
            traces_path=root / "traces",
            predictor_path=root / "predictor.jsonl",
        )
        await darwin.init()

        meta = MetaLearningPrototype(darwin, seed=7)
        result = await meta.run_meta_experiment(
            generate_test_proposals(),
            n_meta_cycles=4,
            candidates_per_cycle=6,
        )

        print("=== Darwin Meta-Learning Prototype ===")
        print(f"Baseline score: {result.baseline_score:.3f}")
        print(f"Final score:    {result.final_score:.3f}")
        print(f"Improvement:    {result.fitness_improvement:.3f}")
        print("")
        print(f"Final weights:  {meta.format_weights(meta.fitness_weights)}")
        print("")
        for cycle in result.cycles:
            status = "improved" if cycle.improved else "held"
            print(
                f"cycle {cycle.cycle_index + 1}: "
                f"selected={cycle.selected_score:.3f} ({status})"
            )


if __name__ == "__main__":
    asyncio.run(main())
