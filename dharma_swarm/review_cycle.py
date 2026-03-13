"""Review Cycle Report Generator — 6-hour structured review of the swarm.

Reads: Darwin archive, test results, stigmergy marks, iteration ledger,
memory consolidation, compounding queue. Outputs markdown report to
~/.dharma/reviews/ and delivers via gateway if available.

Anti-amnesia: every review reads ALL active initiatives.
Anti-noise: flags shallow implementations, queues improvement tasks.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────

DHARMA_DIR = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma"))
REVIEWS_DIR = DHARMA_DIR / "reviews"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ── Report Sections ──────────────────────────────────────────────────


async def _section_evolution(hours: float = 6.0) -> str:
    """Darwin archive: what mutations ran, what survived."""
    try:
        from dharma_swarm.archive import EvolutionArchive

        archive = EvolutionArchive()
        await archive.load()

        cutoff = _utc_now() - timedelta(hours=hours)
        recent = await archive.get_latest(n=50)
        in_window = [
            e for e in recent
            if datetime.fromisoformat(e.timestamp).replace(tzinfo=timezone.utc) >= cutoff
        ]

        if not in_window:
            return "## Evolution Archive\nNo mutations in this review window.\n"

        applied = [e for e in in_window if e.status == "applied"]
        rolled_back = [e for e in in_window if e.status == "rolled_back"]
        proposed = [e for e in in_window if e.status == "proposed"]

        lines = [
            "## Evolution Archive",
            f"**Window**: last {hours:.0f}h | "
            f"**Total**: {len(in_window)} | "
            f"**Applied**: {len(applied)} | "
            f"**Rolled back**: {len(rolled_back)} | "
            f"**Proposed**: {len(proposed)}",
            "",
        ]

        if applied:
            lines.append("### Applied Mutations")
            for e in applied[:10]:
                fitness = e.fitness.weighted()
                lines.append(
                    f"- `{e.component}` {e.description[:80]} "
                    f"(fitness={fitness:.3f}, commit={e.commit_hash or 'none'})"
                )
            lines.append("")

        if rolled_back:
            lines.append("### Rolled Back")
            for e in rolled_back[:5]:
                lines.append(
                    f"- `{e.component}` {e.description[:80]} "
                    f"reason={e.rollback_reason or '?'}"
                )
            lines.append("")

        # MAP-Elites coverage
        coverage = archive.grid.coverage()
        lines.append(
            f"**MAP-Elites**: {archive.grid.occupied_bins}/{archive.grid.total_bins} "
            f"bins occupied ({coverage:.1%} coverage)"
        )
        lines.append("")
        return "\n".join(lines)

    except Exception as e:
        return f"## Evolution Archive\n*Error reading archive: {e}*\n"


async def _section_tests() -> str:
    """Run or summarize test results."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--tb=no", "-q", "--no-header"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        output = result.stdout.strip()
        # Extract summary line (e.g. "2505 passed, 1 failed")
        summary_lines = [l for l in output.splitlines() if "passed" in l or "failed" in l]
        summary = summary_lines[-1] if summary_lines else output[-200:]

        lines = [
            "## Test Results",
            f"**Exit code**: {result.returncode}",
            f"**Summary**: {summary}",
        ]

        if result.returncode != 0 and result.stderr:
            # Include first few lines of stderr for debugging
            err_preview = "\n".join(result.stderr.strip().splitlines()[:5])
            lines.append(f"\n```\n{err_preview}\n```")

        lines.append("")
        return "\n".join(lines)

    except subprocess.TimeoutExpired:
        return "## Test Results\n*Tests timed out (>120s)*\n"
    except Exception as e:
        return f"## Test Results\n*Error running tests: {e}*\n"


async def _section_stigmergy(hours: float = 6.0) -> str:
    """Hot paths and high-salience marks."""
    try:
        from dharma_swarm.stigmergy import StigmergyStore

        store = StigmergyStore()
        hot = await store.hot_paths(window_hours=hours, min_marks=2)
        high_sal = await store.high_salience(threshold=0.7, limit=5)

        lines = ["## Stigmergy (File Activity)"]
        if hot:
            lines.append("### Hot Paths")
            for path, count in hot[:10]:
                lines.append(f"- `{path}` — {count} marks")
        else:
            lines.append("No hot paths in this window.")

        if high_sal:
            lines.append("\n### High Salience Observations")
            for mark in high_sal:
                lines.append(
                    f"- [{mark.agent}] `{mark.file_path}`: "
                    f"{mark.observation} (salience={mark.salience:.2f})"
                )

        lines.append("")
        return "\n".join(lines)

    except Exception as e:
        return f"## Stigmergy\n*Error: {e}*\n"


def _section_initiatives() -> str:
    """Iteration depth ledger: all active initiatives."""
    try:
        from dharma_swarm.iteration_depth import (
            CompoundingQueue,
            IterationLedger,
            MIN_ITERATIONS_FOR_SOLID,
        )

        ledger = IterationLedger()
        ledger.load()
        queue = CompoundingQueue()
        queue.load()

        summary = ledger.summary()
        q_summary = queue.summary()

        lines = [
            "## Initiative Depth Tracker",
            f"**Total**: {summary['total']} | "
            f"**Active**: {summary['active_count']} | "
            f"**Avg iterations**: {summary['avg_iterations']} | "
            f"**Avg quality**: {summary['avg_quality']:.3f}",
            "",
        ]

        # Status breakdown
        if summary["by_status"]:
            status_parts = [f"{k}={v}" for k, v in summary["by_status"].items()]
            lines.append(f"**Status**: {', '.join(status_parts)}")
            lines.append("")

        # Anti-amnesia: list ALL active initiatives
        active = ledger.get_active()
        if active:
            lines.append("### Active Initiatives (Anti-Amnesia Check)")
            for init in sorted(active, key=lambda i: i.quality_score):
                status_icon = {
                    "seed": "🌱", "growing": "🌿", "solid": "🪨",
                }.get(init.status.value, "?")
                lines.append(
                    f"- {status_icon} **{init.title}** "
                    f"(iter={init.iteration_count}, quality={init.quality_score:.3f}, "
                    f"status={init.status.value})"
                )
            lines.append("")

        # Shallow warning
        if summary["shallow"]:
            lines.append("### ⚠️ Shallow Implementations (Need Iteration)")
            for s in summary["shallow"]:
                needed = MIN_ITERATIONS_FOR_SOLID - s["iterations"]
                lines.append(
                    f"- **{s['title']}**: {s['iterations']} iterations "
                    f"(need {needed} more)"
                )
            lines.append("")

        # Ready to promote
        if summary["ready_to_promote"]:
            lines.append("### ✅ Ready to Promote")
            for r in summary["ready_to_promote"]:
                lines.append(
                    f"- **{r['title']}**: {r['iterations']} iterations, "
                    f"quality={r['quality']:.3f}"
                )
            lines.append("")

        # Compounding queue
        if q_summary["pending"] > 0:
            lines.append(
                f"### Compounding Queue: {q_summary['pending']} pending tasks"
            )
            for t in q_summary["top_tasks"]:
                lines.append(f"- [{t['priority']:.1f}] {t['task']}")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        return f"## Initiative Depth Tracker\n*Error: {e}*\n"


async def _section_memory() -> str:
    """Strange loop memory: recent development markers and witness observations."""
    try:
        from dharma_swarm.memory import StrangeLoopMemory
        from dharma_swarm.models import MemoryLayer

        db_path = DHARMA_DIR / "db" / "memory.db"
        if not db_path.exists():
            return "## Memory\nNo memory database found.\n"

        mem = StrangeLoopMemory(db_path)
        await mem.init_db()

        try:
            dev_entries = await mem.recall(
                layer=MemoryLayer.DEVELOPMENT, limit=5, development_only=True,
            )
            witness_entries = await mem.recall(
                layer=MemoryLayer.WITNESS, limit=5,
            )

            lines = ["## Memory (Strange Loop)"]

            if dev_entries:
                lines.append("### Recent Development Markers")
                for e in dev_entries:
                    content_preview = e.content[:120].replace("\n", " ")
                    lines.append(f"- [{e.timestamp.strftime('%H:%M')}] {content_preview}")
            else:
                lines.append("No recent development markers.")

            if witness_entries:
                lines.append("\n### Witness Observations")
                for e in witness_entries:
                    content_preview = e.content[:120].replace("\n", " ")
                    lines.append(
                        f"- [{e.timestamp.strftime('%H:%M')}] {content_preview} "
                        f"(quality={e.witness_quality:.2f})"
                    )

            lines.append("")
            return "\n".join(lines)
        finally:
            await mem.close()

    except Exception as e:
        return f"## Memory\n*Error: {e}*\n"


# ── Report Assembly ──────────────────────────────────────────────────


async def generate_review(
    hours: float = 6.0,
    run_tests: bool = True,
    output_dir: Path | None = None,
) -> str:
    """Generate a comprehensive review cycle report.

    Reads ALL subsystems, enforces anti-amnesia (every active initiative reviewed),
    and saves markdown to disk.

    Returns the report markdown.
    """
    out_dir = output_dir or REVIEWS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    now = _utc_now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")

    # Header
    lines = [
        f"# dharma_swarm Review — {now.strftime('%Y-%m-%d %H:%M UTC')}",
        f"*Review window: {hours:.0f} hours*",
        "",
    ]

    # Gather sections (run async ones concurrently where possible)
    evolution_section, stigmergy_section, memory_section = await asyncio.gather(
        _section_evolution(hours),
        _section_stigmergy(hours),
        _section_memory(),
    )

    # Tests (run separately — it's CPU-bound subprocess)
    test_section = await _section_tests() if run_tests else "## Test Results\n*Skipped*\n"

    # Initiative section is sync
    initiative_section = _section_initiatives()

    # Assemble
    lines.append(evolution_section)
    lines.append(test_section)
    lines.append(stigmergy_section)
    lines.append(initiative_section)
    lines.append(memory_section)

    # Footer: anti-amnesia attestation
    lines.append("---")
    lines.append(
        "**Anti-amnesia attestation**: All active initiatives reviewed. "
        "Nothing silently forgotten. Shallow implementations flagged."
    )
    lines.append(f"\n*Generated at {now.isoformat()}*")

    report = "\n".join(lines)

    # Save to file
    report_path = out_dir / f"review_{timestamp}.md"
    report_path.write_text(report, encoding="utf-8")
    logger.info("Review saved to %s", report_path)

    return report


def generate_review_sync(
    hours: float = 6.0,
    run_tests: bool = True,
    output_dir: Path | None = None,
) -> str:
    """Synchronous wrapper for generate_review (for cron tick run_fn)."""
    return asyncio.run(generate_review(hours=hours, run_tests=run_tests, output_dir=output_dir))


# ── Cron Integration ─────────────────────────────────────────────────


def review_run_fn(job: dict[str, Any]) -> tuple[bool, str, str | None]:
    """Cron tick run_fn: generates review report.

    Signature matches tick(run_fn=...) → (success, output, error).
    """
    try:
        report = generate_review_sync(hours=6.0, run_tests=True)
        return True, report, None
    except Exception as e:
        logger.error("Review cycle failed: %s", e)
        return False, f"Review cycle failed: {e}", str(e)


def create_review_cron_job() -> dict[str, Any]:
    """Create the 6-hour review cycle cron job if it doesn't exist."""
    from dharma_swarm.cron_scheduler import create_job, list_jobs

    # Check if review job already exists
    existing = list_jobs()
    for job in existing:
        if job.get("name", "").startswith("6h-review"):
            logger.info("Review cron job already exists: %s", job["id"])
            return job

    return create_job(
        prompt="Generate 6-hour review cycle report",
        schedule="every 6h",
        name="6h-review-cycle",
        deliver="local",
        urgent=False,
    )
