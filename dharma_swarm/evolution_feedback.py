"""Evolution Feedback Loop — closes the fitness->evolution circle.

Monitors agent fitness via SignalBus events and periodic polling.
When agents struggle, proposes prompt reviews. When they excel,
locks golden prompts and shares patterns via stigmergy.

Designed to run as a background asyncio task alongside the daemon.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DHARMA_HOME = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma"))
KAIZEN_DIR = DHARMA_HOME / "kaizen"
EVOLUTION_DIR = DHARMA_HOME / "evolution"
STIGMERGY_DIR = DHARMA_HOME / "stigmergy"

# Thresholds
FITNESS_POOR_THRESHOLD = 0.5
FITNESS_GOOD_THRESHOLD = 0.8
CONSECUTIVE_POOR_TRIGGER = 3
CONSECUTIVE_GOOD_TRIGGER = 3
POLL_INTERVAL_SECONDS = 300  # 5 minutes
KAIZEN_INTERVAL_SECONDS = 3600  # 1 hour


class FeedbackLoop:
    """Async feedback loop that monitors agent fitness and triggers evolution."""

    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task[None] | None = None
        # Track consecutive poor/good fitness per agent
        self._poor_streak: dict[str, int] = {}
        self._good_streak: dict[str, int] = {}
        self._golden_prompts: set[str] = set()  # agents with locked golden prompts

    async def start(self) -> None:
        """Start the feedback loop as a background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Evolution feedback loop started")

    async def stop(self) -> None:
        """Stop the feedback loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Evolution feedback loop stopped")

    async def _run_loop(self) -> None:
        """Main loop: drain signals + poll fitness + periodic kaizen."""
        kaizen_counter = 0
        while self._running:
            try:
                # 1. Drain fitness signals from the bus
                self._process_signals()

                # 2. Poll all agents' fitness
                await self._poll_agent_fitness()

                # 3. Periodic kaizen analysis (every KAIZEN_INTERVAL)
                kaizen_counter += POLL_INTERVAL_SECONDS
                if kaizen_counter >= KAIZEN_INTERVAL_SECONDS:
                    kaizen_counter = 0
                    await self._run_kaizen_analysis()

            except Exception as e:
                logger.error("Feedback loop error: %s", e)

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    def _process_signals(self) -> None:
        """Drain FITNESS_SIGNAL events from SignalBus."""
        try:
            from dharma_swarm.signal_bus import SignalBus

            bus = SignalBus.get()
            events = bus.drain(["FITNESS_SIGNAL", "AGENT_TASK_COMPLETE"])
            for event in events:
                agent = event.get("agent", "")
                fitness = event.get("composite_fitness", 0.0)
                if agent and fitness:
                    self._update_streaks(agent, fitness)
        except Exception as e:
            logger.debug("Signal drain error: %s", e)

    def _update_streaks(self, agent: str, fitness: float) -> None:
        """Update consecutive poor/good streaks and trigger actions."""
        if fitness < FITNESS_POOR_THRESHOLD:
            self._poor_streak[agent] = self._poor_streak.get(agent, 0) + 1
            self._good_streak[agent] = 0

            if self._poor_streak[agent] >= CONSECUTIVE_POOR_TRIGGER:
                self._propose_prompt_review(agent, fitness)
                self._poor_streak[agent] = 0  # Reset after trigger

        elif fitness > FITNESS_GOOD_THRESHOLD:
            self._good_streak[agent] = self._good_streak.get(agent, 0) + 1
            self._poor_streak[agent] = 0

            if self._good_streak[agent] >= CONSECUTIVE_GOOD_TRIGGER:
                self._lock_golden_prompt(agent, fitness)
                self._good_streak[agent] = 0
        else:
            # Middle ground -- decay streaks slowly
            self._poor_streak[agent] = max(
                0, self._poor_streak.get(agent, 0) - 1
            )
            self._good_streak[agent] = max(
                0, self._good_streak.get(agent, 0) - 1
            )

    async def _poll_agent_fitness(self) -> None:
        """Poll all registered agents and update streaks."""
        try:
            from dharma_swarm.agent_registry import get_registry

            reg = get_registry()
            for identity in reg.list_agents():
                name = identity.get("name", "")
                if not name:
                    continue
                fitness = reg.get_agent_fitness(name)
                comp = fitness.get("composite_fitness", 0.0)
                if fitness.get("total_calls", 0) > 0:
                    self._update_streaks(name, comp)
        except Exception as e:
            logger.debug("Fitness poll error: %s", e)

    def _propose_prompt_review(self, agent: str, fitness: float) -> None:
        """Log an evolution proposal when agent fitness is consistently poor."""
        now = datetime.now(timezone.utc).isoformat()
        proposal = {
            "type": "prompt_review",
            "agent": agent,
            "trigger": "consecutive_poor_fitness",
            "fitness_at_trigger": round(fitness, 4),
            "threshold": FITNESS_POOR_THRESHOLD,
            "timestamp": now,
            "status": "proposed",
            "description": (
                f"Agent '{agent}' has composite_fitness={fitness:.3f} "
                f"for {CONSECUTIVE_POOR_TRIGGER}+ consecutive evaluations. "
                f"Prompt review recommended."
            ),
        }

        # Write to evolution proposals
        EVOLUTION_DIR.mkdir(parents=True, exist_ok=True)
        proposals_path = EVOLUTION_DIR / "feedback_proposals.jsonl"
        try:
            with proposals_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(proposal, default=str) + "\n")
            logger.warning(
                "EVOLUTION PROPOSAL: Agent '%s' needs prompt review (fitness=%.3f)",
                agent,
                fitness,
            )
        except Exception as e:
            logger.error("Failed to write proposal: %s", e)

        # Emit signal for other systems to pick up
        try:
            from dharma_swarm.signal_bus import SignalBus

            SignalBus.get().emit(
                {
                    "type": "EVOLUTION_PROPOSAL",
                    "agent": agent,
                    "reason": "poor_fitness",
                    "fitness": fitness,
                }
            )
        except Exception:
            pass

    def _lock_golden_prompt(self, agent: str, fitness: float) -> None:
        """Lock current prompt as golden variant when fitness is consistently high."""
        if agent in self._golden_prompts:
            return  # Already locked

        now = datetime.now(timezone.utc).isoformat()

        try:
            from dharma_swarm.agent_registry import get_registry

            reg = get_registry()

            # Read current active prompt
            prompt_path = reg._active_prompt_path(agent)
            if not prompt_path.exists():
                return

            current_prompt = prompt_path.read_text(encoding="utf-8").strip()
            if not current_prompt:
                return

            # Save as golden variant
            golden_dir = reg._prompt_dir(agent)
            golden_dir.mkdir(parents=True, exist_ok=True)
            golden_path = golden_dir / "golden.txt"
            golden_path.write_text(current_prompt + "\n", encoding="utf-8")

            # Log the lock event
            lock_record = {
                "type": "golden_lock",
                "agent": agent,
                "fitness_at_lock": round(fitness, 4),
                "threshold": FITNESS_GOOD_THRESHOLD,
                "timestamp": now,
                "prompt_hash": hash(current_prompt) & 0xFFFFFFFF,
            }

            EVOLUTION_DIR.mkdir(parents=True, exist_ok=True)
            locks_path = EVOLUTION_DIR / "golden_locks.jsonl"
            with locks_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(lock_record, default=str) + "\n")

            self._golden_prompts.add(agent)
            logger.info(
                "GOLDEN PROMPT locked for '%s' (fitness=%.3f)",
                agent,
                fitness,
            )

            # Share success pattern via stigmergy
            self._share_success_pattern(agent, fitness)

        except Exception as e:
            logger.error("Failed to lock golden prompt for '%s': %s", agent, e)

    def _share_success_pattern(self, agent: str, fitness: float) -> None:
        """Write success pattern to stigmergy so other agents can learn."""
        now = datetime.now(timezone.utc).isoformat()
        mark = {
            "agent": agent,
            "file_path": f"golden_prompt:{agent}",
            "action": "golden_lock",
            "observation": (
                f"Agent '{agent}' achieved consistent fitness>{FITNESS_GOOD_THRESHOLD:.1f}. "
                f"Current fitness={fitness:.3f}. Prompt locked as golden variant."
            ),
            "salience": 0.9,
            "timestamp": now,
            "connections": [],
        }

        STIGMERGY_DIR.mkdir(parents=True, exist_ok=True)
        marks_path = STIGMERGY_DIR / "marks.jsonl"
        try:
            with marks_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(mark, default=str) + "\n")
        except Exception as e:
            logger.debug("Stigmergy write error: %s", e)

    async def _run_kaizen_analysis(self) -> None:
        """Periodic kaizen analysis -- surface optimization targets."""
        now = datetime.now(timezone.utc).isoformat()
        KAIZEN_DIR.mkdir(parents=True, exist_ok=True)

        try:
            from dharma_swarm.agent_registry import get_registry

            reg = get_registry()
            agents = reg.list_agents()

            report_lines = [
                f"# Kaizen Report -- {now}",
                f"## Fleet: {len(agents)} agents",
                "",
            ]

            # Fitness summary
            fitness_data: list[dict[str, Any]] = []
            for identity in agents:
                name = identity.get("name", "")
                if not name:
                    continue
                f = reg.get_agent_fitness(name)
                if f.get("total_calls", 0) > 0:
                    fitness_data.append(f)

            if fitness_data:
                avg_fitness = sum(
                    f["composite_fitness"] for f in fitness_data
                ) / len(fitness_data)
                avg_success = sum(
                    f["success_rate"] for f in fitness_data
                ) / len(fitness_data)
                total_cost = sum(f["total_cost_usd"] for f in fitness_data)

                report_lines.extend(
                    [
                        "### Fleet Metrics",
                        f"- Mean composite fitness: {avg_fitness:.3f}",
                        f"- Mean success rate: {avg_success:.3f}",
                        f"- Total fleet cost: ${total_cost:.4f}",
                        f"- Active agents: {len(fitness_data)}/{len(agents)}",
                        "",
                    ]
                )

                # Identify optimization targets
                poor = [
                    f
                    for f in fitness_data
                    if f["composite_fitness"] < FITNESS_POOR_THRESHOLD
                ]
                if poor:
                    report_lines.append(
                        "### Optimization Targets (fitness < 0.5)"
                    )
                    for p in sorted(
                        poor, key=lambda x: x["composite_fitness"]
                    ):
                        report_lines.append(
                            f"- **{p['name']}**: fitness={p['composite_fitness']:.3f}, "
                            f"success={p['success_rate']:.1%}, latency={p['avg_latency']:.0f}ms"
                        )
                    report_lines.append("")

                # Identify top performers
                top = [
                    f
                    for f in fitness_data
                    if f["composite_fitness"] > FITNESS_GOOD_THRESHOLD
                ]
                if top:
                    report_lines.append(
                        "### Top Performers (fitness > 0.8)"
                    )
                    for t in sorted(
                        top,
                        key=lambda x: x["composite_fitness"],
                        reverse=True,
                    ):
                        report_lines.append(
                            f"- **{t['name']}**: fitness={t['composite_fitness']:.3f}, "
                            f"success={t['success_rate']:.1%}, cost=${t['total_cost_usd']:.4f}"
                        )
                    report_lines.append("")

                # Cost efficiency
                if total_cost > 0:
                    report_lines.append("### Cost Efficiency")
                    for f in sorted(
                        fitness_data,
                        key=lambda x: x["total_cost_usd"],
                        reverse=True,
                    ):
                        if f["total_cost_usd"] > 0:
                            efficiency = f["composite_fitness"] / max(
                                f["total_cost_usd"], 0.0001
                            )
                            report_lines.append(
                                f"- {f['name']}: ${f['total_cost_usd']:.4f} "
                                f"(efficiency={efficiency:.1f} fitness/$)"
                            )
                    report_lines.append("")
            else:
                report_lines.append("No agents with task history found.\n")

            # Write report
            report_path = KAIZEN_DIR / (
                f"report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.md"
            )
            report_path.write_text("\n".join(report_lines), encoding="utf-8")

            # Also write latest.md for easy access
            latest_path = KAIZEN_DIR / "latest.md"
            latest_path.write_text("\n".join(report_lines), encoding="utf-8")

            logger.info("Kaizen report written: %s", report_path.name)

        except Exception as e:
            logger.error("Kaizen analysis failed: %s", e)


# Module-level singleton
_feedback_loop: FeedbackLoop | None = None


def get_feedback_loop() -> FeedbackLoop:
    """Return the module-level FeedbackLoop singleton."""
    global _feedback_loop
    if _feedback_loop is None:
        _feedback_loop = FeedbackLoop()
    return _feedback_loop


async def start_feedback_loop() -> FeedbackLoop:
    """Convenience: get the singleton and start it."""
    loop = get_feedback_loop()
    await loop.start()
    return loop
