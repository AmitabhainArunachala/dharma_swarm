"""Entry point for the Petri Dish experiment.

Usage:
    python -m experiments.petri_dish.run [--generations N] [--cycles N] [--batch N]

Or from the dharma_swarm root:
    cd ~/dharma_swarm && python -m experiments.petri_dish
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import PetriDishConfig
from .harness import PetriDishHarness


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Petri Dish: Behavioral Backpropagation Experiment",
    )
    parser.add_argument(
        "--generations", type=int, default=4,
        help="Number of consolidation generations (default: 4)",
    )
    parser.add_argument(
        "--cycles", type=int, default=3,
        help="Work cycles per generation (default: 3)",
    )
    parser.add_argument(
        "--batch", type=int, default=12,
        help="Snippets per work cycle (default: 12)",
    )
    parser.add_argument(
        "--rounds", type=int, default=3,
        help="Debate rounds per consolidation (default: 3)",
    )
    parser.add_argument(
        "--worker-model", type=str, default=None,
        help="Override worker model",
    )
    parser.add_argument(
        "--alpha-model", type=str, default=None,
        help="Override consolidator alpha model",
    )
    parser.add_argument(
        "--beta-model", type=str, default=None,
        help="Override consolidator beta model",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Clean state directory before running",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Build config
    overrides: dict = {
        "total_generations": args.generations,
        "work_cycles_per_generation": args.cycles,
        "batch_size": args.batch,
        "debate_rounds": args.rounds,
    }
    if args.worker_model:
        overrides["worker_model"] = args.worker_model
    if args.alpha_model:
        overrides["consolidator_alpha_model"] = args.alpha_model
    if args.beta_model:
        overrides["consolidator_beta_model"] = args.beta_model

    config = PetriDishConfig(**overrides)

    # Clean state if requested
    if args.clean:
        import shutil
        state = config.state_dir
        if state.exists():
            for child in state.iterdir():
                if child.name == ".gitignore":
                    continue
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            print(f"Cleaned {state}")

    # Run experiment
    harness = PetriDishHarness(config)
    try:
        report = asyncio.run(harness.run())
        sys.exit(0 if report.total_work_cycles > 0 else 1)
    except KeyboardInterrupt:
        print("\nExperiment interrupted.")
        sys.exit(130)
    except Exception as e:
        print(f"\nExperiment failed: {e}", file=sys.stderr)
        logging.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    main()
