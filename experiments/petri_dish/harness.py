"""Petri Dish Harness: orchestrates work cycles and consolidation.

Main loop:
  For each generation:
    1. Run work_cycles_per_generation work cycles (all 3 workers classify batches)
    2. Run consolidation (thesis/antithesis analyze, debate, extract mods)
    3. Apply DNA modifications
    4. Archive old DNA, increment generation
    5. Record metrics
"""

from __future__ import annotations

import logging
from pathlib import Path

from .config import PetriDishConfig
from .consolidator import (
    ConsolidationOrchestrator,
    ConsolidatorAgent,
    save_consolidation,
)
from .dataset import get_partitioned_batches
from .dna import BehavioralDNA, initialize_dna
from .llm_client import PetriDishLLM
from .models import CycleMetrics, ExperimentReport, Modification
from .worker import WorkerAgent, save_trace

logger = logging.getLogger(__name__)


class PetriDishHarness:
    """Orchestrates the full petri dish experiment."""

    def __init__(self, config: PetriDishConfig | None = None) -> None:
        self.config = config or PetriDishConfig()
        self.llm = PetriDishLLM(api_key=self.config.api_key)
        self.all_metrics: list[CycleMetrics] = []
        self.all_modifications: list[Modification] = []
        self.cycle_counter = 0

    async def run(self) -> ExperimentReport:
        """Execute the full experiment."""
        cfg = self.config

        # Ensure state directories exist
        for d in [cfg.dna_dir, cfg.dna_archive_dir, cfg.traces_dir,
                  cfg.metrics_dir, cfg.debates_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Initialize DNA
        dna_map = initialize_dna(cfg.dna_dir)
        agent_names = sorted(dna_map.keys())

        # Pre-compute all batches for reproducibility
        total_cycles = cfg.work_cycles_per_generation * cfg.total_generations
        batches = get_partitioned_batches(
            cfg.batch_size, total_cycles, seed=42,
        )

        self._print_header(cfg)

        for gen in range(cfg.total_generations):
            self._print_gen_header(gen, cfg.total_generations)

            # --- Work cycles ---
            gen_traces = []
            for cycle_in_gen in range(cfg.work_cycles_per_generation):
                cycle_id = self.cycle_counter
                batch = batches[cycle_id]
                self.cycle_counter += 1

                # Run all workers on this batch
                workers = self._make_workers(dna_map)
                cycle_traces = []
                for name in agent_names:
                    trace = await workers[name].classify_batch(
                        batch, cycle_id=cycle_id, generation=gen,
                    )
                    save_trace(trace, cfg.traces_dir)
                    cycle_traces.append(trace)
                    gen_traces.append(trace)

                # Record metrics
                metrics = self._compute_metrics(cycle_id, gen, cycle_traces)
                self.all_metrics.append(metrics)
                self._save_metrics(metrics)
                self._print_cycle(gen, cycle_in_gen, cfg.work_cycles_per_generation, metrics)

            # --- Consolidation ---
            if gen < cfg.total_generations:  # Always consolidate (even last gen for measurement)
                self._print_consolidation_header(gen)

                # Read current DNA content
                worker_dnas = {
                    name: dna.load() for name, dna in dna_map.items()
                }

                # Build consolidation orchestrator
                orchestrator = self._make_consolidator()

                # Run consolidation
                result = await orchestrator.run(
                    worker_dnas=worker_dnas,
                    traces=gen_traces,
                    generation=gen,
                )
                save_consolidation(result, cfg.debates_dir)

                # Apply modifications
                applied = 0
                for mod in result.modifications:
                    if mod.agent in dna_map:
                        success = dna_map[mod.agent].apply_modification(
                            section=mod.section,
                            action=mod.action,
                            old_text=mod.old_text,
                            new_text=mod.new_text,
                        )
                        if success:
                            applied += 1
                            dna_map[mod.agent].append_to_changelog(
                                f"Gen {gen}: {mod.rationale[:80]}"
                            )
                    self.all_modifications.append(mod)

                # Archive and increment generation
                for name, dna in dna_map.items():
                    dna.archive(gen, cfg.dna_archive_dir)
                    dna.increment_generation()

                self._print_consolidation_result(
                    gen, len(result.modifications), applied,
                )

        # --- Final report ---
        report = self._build_report()
        self._save_report(report)
        self._print_report(report)
        return report

    def _make_workers(self, dna_map: dict[str, BehavioralDNA]) -> dict[str, WorkerAgent]:
        """Create worker agents from current DNA."""
        cfg = self.config
        return {
            name: WorkerAgent(
                name=name, dna=dna, llm=self.llm,
                model=cfg.worker_model,
                temperature=cfg.worker_temperature,
                max_tokens=cfg.max_tokens,
            )
            for name, dna in dna_map.items()
        }

    def _make_consolidator(self) -> ConsolidationOrchestrator:
        """Create the consolidation orchestrator."""
        cfg = self.config
        thesis = ConsolidatorAgent(
            role="thesis", llm=self.llm,
            model=cfg.consolidator_alpha_model,
            temperature=cfg.consolidator_temperature,
        )
        antithesis = ConsolidatorAgent(
            role="antithesis", llm=self.llm,
            model=cfg.consolidator_beta_model,
            temperature=cfg.consolidator_temperature,
        )
        return ConsolidationOrchestrator(
            thesis=thesis, antithesis=antithesis,
            llm=self.llm,
            extraction_model=cfg.consolidator_alpha_model,
            debate_rounds=cfg.debate_rounds,
        )

    def _compute_metrics(
        self, cycle_id: int, generation: int,
        traces: list,
    ) -> CycleMetrics:
        """Compute cycle-level metrics from worker traces."""
        agent_scores = {}
        for t in traces:
            agent_scores[t.agent_name] = {
                "sentiment": t.sentiment_accuracy,
                "topic": t.topic_accuracy,
                "urgency": t.urgency_accuracy,
                "overall": t.overall_accuracy,
            }
        system_score = (
            sum(s["overall"] for s in agent_scores.values()) / len(agent_scores)
            if agent_scores else 0.0
        )
        return CycleMetrics(
            cycle_id=cycle_id, generation=generation,
            agent_scores=agent_scores, system_score=system_score,
        )

    def _save_metrics(self, metrics: CycleMetrics) -> None:
        path = self.config.metrics_dir / f"cycle_{metrics.cycle_id}.json"
        path.write_text(metrics.model_dump_json(indent=2), encoding="utf-8")

    def _build_report(self) -> ExperimentReport:
        """Build final experiment report."""
        scores = [m.system_score for m in self.all_metrics]
        per_gen: dict[int, list[float]] = {}
        for m in self.all_metrics:
            gen = m.generation
            if gen not in per_gen:
                per_gen[gen] = []
            per_gen[gen].append(m.system_score)
        per_gen_avg = {g: sum(s) / len(s) for g, s in per_gen.items()}

        return ExperimentReport(
            total_generations=self.config.total_generations,
            total_work_cycles=len(self.all_metrics),
            total_consolidations=self.config.total_generations,
            initial_system_score=scores[0] if scores else 0.0,
            final_system_score=scores[-1] if scores else 0.0,
            improvement=(scores[-1] - scores[0]) if len(scores) >= 2 else 0.0,
            score_trajectory=scores,
            all_modifications=self.all_modifications,
            per_generation_scores=per_gen_avg,
        )

    def _save_report(self, report: ExperimentReport) -> None:
        path = self.config.state_dir / "report.json"
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    # --- Console output ---

    def _print_header(self, cfg: PetriDishConfig) -> None:
        print("\n" + "=" * 60)
        print("  PETRI DISH: Behavioral Backpropagation Experiment")
        print("=" * 60)
        print(f"  Generations: {cfg.total_generations}")
        print(f"  Work cycles/gen: {cfg.work_cycles_per_generation}")
        print(f"  Batch size: {cfg.batch_size}")
        print(f"  Debate rounds: {cfg.debate_rounds}")
        print(f"  Worker model: {cfg.worker_model}")
        print(f"  Consolidator models: {cfg.consolidator_alpha_model} vs {cfg.consolidator_beta_model}")
        print("=" * 60, flush=True)

    def _print_gen_header(self, gen: int, total: int) -> None:
        print(f"\n--- Generation {gen}/{total - 1} ---", flush=True)

    def _print_cycle(
        self, gen: int, cycle_in_gen: int, total_cycles: int,
        metrics: CycleMetrics,
    ) -> None:
        print(f"  Cycle {cycle_in_gen + 1}/{total_cycles}:", flush=True)
        for name, scores in sorted(metrics.agent_scores.items()):
            print(
                f"    {name}: "
                f"sent={scores['sentiment']:.2f} "
                f"topic={scores['topic']:.2f} "
                f"urgency={scores['urgency']:.2f} "
                f"| overall={scores['overall']:.2f}",
                flush=True,
            )
        print(f"    SYSTEM: {metrics.system_score:.3f}", flush=True)

    def _print_consolidation_header(self, gen: int) -> None:
        print(f"\n  === CONSOLIDATION (Gen {gen} -> Gen {gen + 1}) ===", flush=True)

    def _print_consolidation_result(
        self, gen: int, proposed: int, applied: int,
    ) -> None:
        print(
            f"  Debate complete: {proposed} modifications proposed, "
            f"{applied} applied",
            flush=True,
        )

    def _print_report(self, report: ExperimentReport) -> None:
        print("\n" + "=" * 60)
        print("  EXPERIMENT COMPLETE")
        print("=" * 60)
        print(f"  Total work cycles: {report.total_work_cycles}")
        print(f"  Total consolidations: {report.total_consolidations}")
        print(f"  Initial system score: {report.initial_system_score:.3f}")
        print(f"  Final system score: {report.final_system_score:.3f}")
        print(f"  Improvement: {report.improvement:+.3f}")
        print(f"  Total modifications: {len(report.all_modifications)}")
        print(f"\n  Score trajectory: {[f'{s:.3f}' for s in report.score_trajectory]}")
        print(f"\n  Per-generation averages:")
        for gen, score in sorted(report.per_generation_scores.items()):
            print(f"    Gen {gen}: {score:.3f}")
        print(f"\n  LLM stats: {self.llm.stats}")
        print("=" * 60, flush=True)
