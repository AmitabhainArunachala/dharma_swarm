"""Task completion → TelosGraph progress tracker.

Closes the perception loop: the system now knows what it has accomplished.
Called non-fatally from orchestrator on every task completion.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Keywords in task title/description → (telos objective name fragment, progress_increment)
# Higher increment = more direct contribution
TASK_TELOS_MAP: list[tuple[str, str, float]] = [
    # Research / VIVEKA track
    ("mechanistic interpretability", "VIVEKA R_V Consciousness", 0.05),
    ("r_v metric", "VIVEKA R_V", 0.05),
    ("r_v", "VIVEKA R_V", 0.03),
    ("web_search", "VIVEKA Cross-Architecture", 0.01),
    ("arxiv", "VIVEKA Cross-Architecture", 0.02),
    ("research", "VIVEKA Cross-Architecture", 0.01),
    # Evolution / Darwin-Gödel track
    ("evolution", "Surpass Sakana DGM", 0.02),
    ("darwin", "Surpass Sakana DGM", 0.03),
    ("self-modif", "Surpass Sakana DGM", 0.03),
    ("fitness", "Surpass Sakana DGM", 0.02),
    # Competitive intelligence
    ("isara", "Differentiate from Isara", 0.05),
    ("competitive", "Differentiate from Isara", 0.03),
    ("alignment", "Publish dharmic alignment", 0.02),
    # Trading / Ginko
    ("ginko", "Wire Ginko", 0.05),
    ("trading", "Wire Ginko", 0.03),
    ("market", "Wire Ginko", 0.02),
    ("regime", "Wire Ginko", 0.02),
    # Autonomous ops
    ("24-hour", "Achieve 24-hour", 0.05),
    ("deploy", "Achieve 24-hour", 0.02),
    ("autonomous", "Achieve 24-hour", 0.02),
    # Jagat Kalyan
    ("welfare", "Jagat Kalyan", 0.03),
    ("ecology", "KALYAN 50-Hectare", 0.03),
    ("global", "Jagat Kalyan", 0.01),
]


async def record_task_completion(
    task_title: str,
    task_description: str,
    result: str | None,
    state_dir: Path | str,
) -> None:
    """Record a task completion and update TelosGraph progress.

    Non-fatal: any error is logged at DEBUG level and ignored.
    Never raises. Never blocks the calling coroutine meaningfully.
    """
    try:
        from dharma_swarm.telos_graph import TelosGraph

        telos = TelosGraph(telos_dir=Path(state_dir) / "telos")
        await telos.load()

        text = ((task_title or "") + " " + (task_description or "")).lower()

        # Accumulate per-objective increments
        increments: dict[str, float] = {}
        for keyword, obj_fragment, increment in TASK_TELOS_MAP:
            if keyword in text:
                increments[obj_fragment] = increments.get(obj_fragment, 0.0) + increment

        if not increments:
            return

        # Apply increments
        all_objs = telos.list_objectives()
        for fragment, total_increment in increments.items():
            # Find best match by fragment
            matches = [o for o in all_objs if fragment.lower() in o.name.lower()]
            if not matches:
                continue
            best = matches[0]
            new_progress = min(1.0, best.progress + total_increment)
            if new_progress > best.progress:
                await telos.update_objective(best.id, progress=new_progress)
                logger.debug(
                    "TelosGraph: %s %.3f→%.3f (task: %s)",
                    best.name[:50],
                    best.progress,
                    new_progress,
                    (task_title or "")[:40],
                )

    except Exception as exc:
        logger.debug("TelosGraph progress update skipped: %s", exc)
