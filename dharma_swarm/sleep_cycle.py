"""Sleep-cycle memory consolidation for the Garden Daemon.

During quiet hours (default 2-5 AM), the daemon stops doing real work and
instead consolidates colony memory.  Four phases mirror biological sleep:

1. **LIGHT** -- stigmergy decay (pheromone evaporation)
2. **DEEP** -- agent memory consolidation (expire, demote, prune)
3. **REM** -- subconscious dreaming (lateral association via random sampling)
4. **WAKE** -- generate a sleep report and write it to disk

Each phase is fault-isolated: an error in one phase is recorded but does
not prevent subsequent phases from running.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class SleepPhase(str, Enum):
    """Phases of the sleep cycle, inspired by real sleep stages."""

    LIGHT = "light"      # Quick cleanup: expire old stigmergy marks
    DEEP = "deep"        # Heavy lifting: consolidate all agent memories
    REM = "rem"          # Creative: subconscious dreaming + association
    NEURAL = "neural"    # Neural consolidation: forward scan → loss → contrarian discuss → backprop
    SEMANTIC = "semantic" # Semantic evolution: digest→research→synthesize→harden→gravitize
    BRIDGE = "bridge"    # Cross-graph bridge discovery: connect semantic↔temporal↔telos
    PRUNE = "prune"      # Sweep the zen garden: archive noise, merge duplicates
    WAKE = "wake"        # Prepare for morning: generate sleep report


class SleepReport(BaseModel):
    """Summary of what happened during the sleep cycle."""

    started_at: datetime
    ended_at: datetime | None = None
    phases_completed: list[str] = Field(default_factory=list)
    marks_decayed: int = 0
    memories_consolidated: int = 0
    dreams_generated: int = 0
    hot_paths_found: list[str] = Field(default_factory=list)
    high_salience_observations: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    # Neural consolidation stats
    neural_losses: int = 0
    neural_corrections: int = 0
    neural_division_proposals: int = 0
    # Colony-level R_V: dimensional contraction through sleep
    colony_rv: float | None = None
    density_before: int = 0
    density_after: int = 0


# ---------------------------------------------------------------------------
# Sleep cycle
# ---------------------------------------------------------------------------

_REPORTS_DIR = Path.home() / ".dharma" / "sleep_reports"


class SleepCycle:
    """Runs memory consolidation during daemon quiet hours.

    All three subsystems (stigmergy, agent memory, subconscious) are
    optional.  When absent the corresponding phase is skipped gracefully.
    """

    def __init__(
        self,
        agent_memory_dir: Path | None = None,
        stigmergy_store: Any | None = None,
        subconscious_stream: Any | None = None,
        reports_dir: Path | None = None,
    ) -> None:
        self._memory_dir = agent_memory_dir or (
            Path.home() / ".dharma" / "agent_memory"
        )
        self._stigmergy = stigmergy_store
        self._subconscious = subconscious_stream
        self._reports_dir = reports_dir or _REPORTS_DIR

    # -- public API ----------------------------------------------------------

    async def run_full_cycle(self) -> SleepReport:
        """Run all sleep phases in order: LIGHT -> DEEP -> REM -> WAKE.

        Also computes colony-level R_V: the geometric contraction of
        stigmergic memory through the sleep cycle. density_before / density_after
        maps directly to PR_early / PR_late — the colony's participation ratio.
        """
        report = SleepReport(started_at=datetime.now(timezone.utc))

        # Measure colony dimensionality BEFORE sleep
        try:
            if self._stigmergy is not None:
                d = self._stigmergy.density()
                report.density_before = int(d) if isinstance(d, (int, float)) else 0
        except Exception:
            logger.debug("Pre-sleep density measurement failed", exc_info=True)

        for phase in (SleepPhase.LIGHT, SleepPhase.DEEP, SleepPhase.REM, SleepPhase.NEURAL, SleepPhase.SEMANTIC, SleepPhase.BRIDGE, SleepPhase.PRUNE):
            try:
                result = await self.run_phase(phase)
                report.phases_completed.append(phase.value)
                self._merge_phase_result(report, phase, result)
            except Exception as exc:
                msg = f"{phase.value}: {exc}"
                logger.warning("Sleep phase %s failed: %s", phase.value, exc)
                report.errors.append(msg)

        # Measure colony dimensionality AFTER sleep
        try:
            if self._stigmergy is not None:
                d = self._stigmergy.density()
                report.density_after = int(d) if isinstance(d, (int, float)) else 0
                if report.density_before > 0 and report.density_after >= 0:
                    report.colony_rv = report.density_after / report.density_before
        except Exception:
            logger.debug("Post-sleep density measurement failed", exc_info=True)

        # WAKE always runs (writes the report itself)
        try:
            result = await self._wake(report)
            report.phases_completed.append(SleepPhase.WAKE.value)
        except Exception as exc:
            msg = f"wake: {exc}"
            logger.warning("Sleep wake phase failed: %s", exc)
            report.errors.append(msg)

        report.ended_at = datetime.now(timezone.utc)
        return report

    async def run_phase(self, phase: SleepPhase) -> dict[str, Any]:
        """Run a single sleep phase. Returns phase-specific metrics."""
        dispatch = {
            SleepPhase.LIGHT: self._light_sleep,
            SleepPhase.DEEP: self._deep_sleep,
            SleepPhase.REM: self._rem_sleep,
            SleepPhase.NEURAL: self._neural_sleep,
            SleepPhase.SEMANTIC: self._semantic_sleep,
            SleepPhase.BRIDGE: self._bridge_sleep,
            SleepPhase.PRUNE: self._prune_sleep,
        }
        handler = dispatch.get(phase)
        if handler is None:
            return {}
        return await handler()

    # -- phase implementations ----------------------------------------------

    async def _light_sleep(self) -> dict[str, Any]:
        """Phase 1: Decay old stigmergy marks (pheromone evaporation).

        Returns:
            Dict with ``marks_decayed`` count and ``hot_paths`` list.
        """
        result: dict[str, Any] = {"marks_decayed": 0, "hot_paths": []}

        if self._stigmergy is None:
            return result

        decayed = await self._stigmergy.decay()
        result["marks_decayed"] = decayed

        faded = await self._stigmergy.access_decay()
        result["marks_faded"] = faded

        hot = await self._stigmergy.hot_paths()
        result["hot_paths"] = [path for path, _count in hot]

        return result

    async def _deep_sleep(self) -> dict[str, Any]:
        """Phase 2: Consolidate all agent memory banks.

        Scans ``agent_memory_dir`` for agent subdirectories, loads each
        :class:`AgentMemoryBank`, runs ``consolidate()``, and saves.

        Returns:
            Dict with ``agents_processed`` and ``total_consolidated`` counts.
        """
        from dharma_swarm.agent_memory import AgentMemoryBank

        result: dict[str, Any] = {"agents_processed": 0, "total_consolidated": 0}

        if not self._memory_dir.exists():
            return result

        for agent_dir in sorted(self._memory_dir.iterdir()):
            if not agent_dir.is_dir():
                continue
            try:
                bank = AgentMemoryBank(
                    agent_name=agent_dir.name, base_path=self._memory_dir
                )
                await bank.load()
                consolidated = await bank.consolidate()
                await bank.save()
                result["agents_processed"] += 1
                result["total_consolidated"] += consolidated
            except Exception as exc:
                logger.warning(
                    "Failed to consolidate agent '%s': %s", agent_dir.name, exc
                )

        return result

    async def _rem_sleep(self) -> dict[str, Any]:
        """Phase 3: Run subconscious dreaming.

        Checks :meth:`should_wake` on the subconscious stream and, if
        triggered, runs :meth:`dream`.  Also collects high-salience
        observations from the stigmergy store.

        Returns:
            Dict with ``dreams`` count and ``high_salience`` list.
        """
        result: dict[str, Any] = {"dreams": 0, "high_salience": []}

        # Subconscious dreaming
        if self._subconscious is not None:
            should = await self._subconscious.should_wake()
            if should:
                associations = await self._subconscious.dream()
                result["dreams"] = len(associations)

        # High-salience observations from stigmergy
        if self._stigmergy is not None:
            marks = await self._stigmergy.high_salience()
            result["high_salience"] = [m.observation for m in marks]

        return result

    async def _neural_sleep(self) -> dict[str, Any]:
        """Phase 3.5: Neural consolidation — the backpropagation loop.

        Two consolidation agents (advocate + critic) read all system state,
        have a contrarian discussion, and modify the behavioral correction
        files that agents read on their next forward pass.

        This mirrors what happens in the brain during sleep: memory replay,
        error correction, and weight adjustment.

        Returns:
            Dict with losses_found, corrections_applied, division_proposals.
        """
        from dharma_swarm.neural_consolidator import NeuralConsolidator

        result: dict[str, Any] = {
            "losses_found": 0,
            "corrections_applied": 0,
            "division_proposals": 0,
        }
        state_root = self._memory_dir.parent

        consolidator = NeuralConsolidator(
            provider=None,  # Algorithmic mode during sleep (no LLM spend)
            base_path=state_root,
            corrections_dir=state_root / "consolidation" / "corrections",
            reports_dir=state_root / "consolidation" / "reports",
        )

        report = await consolidator.consolidation_cycle()
        result["losses_found"] = report.losses_found
        result["corrections_applied"] = report.corrections_applied
        result["division_proposals"] = report.division_proposals
        if report.errors:
            result["errors"] = report.errors

        return result

    async def _semantic_sleep(self) -> dict[str, Any]:
        """Phase 4: Semantic evolution + recognition synthesis.

        Runs semantic indexing, then generates a recognition seed that
        closes the strange loop: artifacts -> scores -> synthesis ->
        agent context -> artifacts.
        """
        import sqlite3 as _sqlite3

        from dharma_swarm.semantic_memory_bridge import run_semantic_sleep_phase

        state_root = self._memory_dir.parent
        project_root = state_root
        default_project_root = Path(__file__).resolve().parent.parent
        if not (project_root / "dharma_swarm").is_dir():
            if state_root == Path.home() / ".dharma" and (
                default_project_root / "dharma_swarm"
            ).is_dir():
                project_root = default_project_root
            else:
                return {"phase": "semantic", "skipped": True, "reason": "no_project_root"}
        try:
            result = await run_semantic_sleep_phase(
                project_root=project_root,
                graph_path=state_root / "semantic" / "concept_graph.json",
                db_path=state_root / "memory" / "semantic_sleep.db",
            )
        except _sqlite3.OperationalError as exc:
            lowered = str(exc).lower()
            if "locked" in lowered or "readonly" in lowered:
                logger.warning("Semantic sleep skipped: DB locked (%s)", exc)
                return {"phase": "semantic", "skipped": True}
            raise

        # Recognition synthesis — the strange loop closure
        try:
            from dharma_swarm.meta_daemon import RecognitionEngine
            engine = RecognitionEngine(state_dir=self._memory_dir.parent)
            seed = await engine.synthesize("deep")
            result["recognition_seed_length"] = len(seed)
            logger.info("Recognition seed generated (%d chars)", len(seed))
        except Exception as exc:
            logger.warning("Recognition synthesis failed: %s", exc)

        return result

    async def _bridge_sleep(self) -> dict[str, Any]:
        """Phase 5: Cross-graph bridge discovery.

        Runs the BridgeCoordinator to discover edges connecting the
        semantic, temporal, telos, and catalytic graphs.  These bridge
        edges enable cross-graph queries like conceptual blast radius.
        """
        result: dict[str, Any] = {"bridges_discovered": 0, "errors": []}
        try:
            from dharma_swarm.bridge_coordinator import BridgeCoordinator

            state_root = self._memory_dir.parent
            if not (state_root / "semantic" / "concept_graph.json").exists():
                return {"bridges_discovered": 0, "errors": [], "skipped": True}

            coordinator = BridgeCoordinator(state_dir=state_root)
            discovery = await coordinator.discover_all()
            result["bridges_discovered"] = discovery.discovered
            result["duration_seconds"] = discovery.duration_seconds
            if discovery.errors:
                result["errors"] = discovery.errors
            logger.info(
                "Bridge sleep: discovered %d edges in %.1fs",
                discovery.discovered,
                discovery.duration_seconds,
            )
        except Exception as exc:
            logger.warning("Bridge sleep failed: %s", exc)
            result["errors"].append(str(exc))
        return result

    async def _prune_sleep(self) -> dict[str, Any]:
        """Phase 6: Sweep the zen garden.

        Archives low-salience stigmergy, prunes weak bridges,
        flags duplicate telos objectives, identifies isolated concepts.
        Signal stays, noise goes.
        """
        result: dict[str, Any] = {"noise_removed": 0, "signal_remaining": 0}
        try:
            from dharma_swarm.pruner import Pruner

            pruner = Pruner(state_dir=self._memory_dir.parent)
            report = await pruner.sweep()
            result["noise_removed"] = report.noise_removed
            result["signal_remaining"] = report.signal_remaining
            result["actions"] = report.actions_taken[:5]
            if report.errors:
                result["errors"] = report.errors
            logger.info(
                "Prune sleep: removed %d noise, %d signal remaining (%.2fs)",
                report.noise_removed,
                report.signal_remaining,
                report.duration_seconds,
            )
        except Exception as exc:
            logger.warning("Prune sleep failed: %s", exc)
            result["errors"] = [str(exc)]
        return result

    async def _wake(self, report: SleepReport) -> dict[str, Any]:
        """Phase 6: Generate morning summary + update bootstrap manifest.

        Writes the sleep report as JSON to
        ``~/.dharma/sleep_reports/YYYY-MM-DD.json``.
        Also regenerates NOW.json so the next LLM instance has fresh state.

        Returns:
            Dict with ``report_path`` and ``manifest_path`` strings.
        """
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        report_path = self._reports_dir / f"{date_str}.json"

        report_data = report.model_dump(mode="json")
        report_path.write_text(json.dumps(report_data, indent=2, default=str))

        # Update bootstrap manifest so next instance is oriented
        manifest_path = ""
        state_root = self._memory_dir.parent
        default_state_root = Path.home() / ".dharma"
        if state_root == default_state_root:
            try:
                from dharma_swarm.bootstrap import NOW_PATH, generate_manifest
                manifest = generate_manifest()
                manifest_path = str(NOW_PATH)
                logger.info("Bootstrap manifest updated: %s", manifest_path)
                # Log whether the kernel crystal was loaded
                crystal = manifest.get("kernel_crystal", "")
                if crystal:
                    logger.info(
                        "Kernel crystal loaded (%d chars) — orientation active",
                        len(crystal),
                    )
                else:
                    logger.warning(
                        "Kernel crystal NOT found — check specs/KERNEL_CORE_SPEC.md"
                    )
            except Exception as exc:
                logger.warning("Failed to update bootstrap manifest: %s", exc)
        else:
            logger.info(
                "Skipping bootstrap manifest refresh for non-default state root: %s",
                state_root,
            )

        return {"report_path": str(report_path), "manifest_path": manifest_path}

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _merge_phase_result(
        report: SleepReport,
        phase: SleepPhase,
        result: dict[str, Any],
    ) -> None:
        """Fold phase-specific metrics into the cumulative report."""
        if phase == SleepPhase.LIGHT:
            report.marks_decayed += result.get("marks_decayed", 0)
            report.hot_paths_found.extend(result.get("hot_paths", []))
        elif phase == SleepPhase.DEEP:
            report.memories_consolidated += result.get("total_consolidated", 0)
        elif phase == SleepPhase.REM:
            report.dreams_generated += result.get("dreams", 0)
            report.high_salience_observations.extend(
                result.get("high_salience", [])
            )
        elif phase == SleepPhase.NEURAL:
            losses = result.get("losses_found", 0)
            corrections = result.get("corrections_applied", 0)
            divisions = result.get("division_proposals", 0)
            if losses or corrections:
                report.high_salience_observations.append(
                    f"neural: {losses} losses → {corrections} corrections, "
                    f"{divisions} division proposals"
                )
        elif phase == SleepPhase.SEMANTIC:
            # Semantic phase results are informational; log key stats
            concepts = result.get("concepts_digested", 0)
            clusters = result.get("clusters_generated", 0)
            if concepts:
                report.high_salience_observations.append(
                    f"semantic: {concepts} concepts digested, {clusters} clusters"
                )
        elif phase == SleepPhase.BRIDGE:
            bridges = result.get("bridges_discovered", 0)
            if bridges:
                report.high_salience_observations.append(
                    f"bridge: {bridges} cross-graph edges discovered"
                )

    @staticmethod
    def is_quiet_hours(config: Any | None = None) -> bool:
        """Check if current time falls within configured quiet hours.

        Args:
            config: A :class:`DaemonConfig` instance. Uses defaults when
                    *None*.

        Returns:
            ``True`` when the current hour is listed in
            ``config.quiet_hours``.
        """
        from dharma_swarm.daemon_config import DaemonConfig

        cfg = config or DaemonConfig()
        hour = datetime.now().hour
        return hour in cfg.quiet_hours
