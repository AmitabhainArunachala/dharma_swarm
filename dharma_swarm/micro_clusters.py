"""Micro-cluster integrations — cross-subsystem wiring.

Kauffman's adjacent possible: each connection expands possibility space.

Five high-ROI integration clusters, each 20-50 lines:
1. Stigmergy → Evolution: hot marks become evolution proposal seeds
2. Gate Results → Provider Routing: gate scores inform model selection
3. Monitor Anomalies → Cascade: anomaly patterns feed META cascade domain
4. SubconsciousStream → Context: lateral associations enrich agent context
5. Evolution Archive → Fitness Predictor: completed proposals train predictor
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from dharma_swarm.evolution import DarwinEngine, Proposal
    from dharma_swarm.monitor import Anomaly, HealthReport
    from dharma_swarm.stigmergy import StigmergicMark, StigmergyStore
    from dharma_swarm.subconscious import SubconsciousAssociation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cluster 1: Stigmergy → Evolution
# Hot stigmergy marks (high salience) become evolution proposal seeds.
# ---------------------------------------------------------------------------

async def stigmergy_to_evolution_seeds(
    stigmergy: StigmergyStore,
    engine: DarwinEngine,
    *,
    salience_threshold: float = 0.7,
    max_seeds: int = 5,
) -> list[str]:
    """Convert high-salience stigmergy marks into evolution proposals.

    Returns list of created proposal IDs.
    """
    marks = await stigmergy.read_marks(limit=50)
    hot = [m for m in marks if m.salience >= salience_threshold]
    hot.sort(key=lambda m: m.salience, reverse=True)

    created: list[str] = []
    for mark in hot[:max_seeds]:
        try:
            proposal = await engine.propose(
                component=mark.file_path or "unknown",
                change_type="stigmergy_inspired",
                description=(
                    f"Stigmergy-seeded proposal from mark {mark.id} "
                    f"(action={mark.action}, salience={mark.salience:.2f}): "
                    f"{', '.join(mark.connections[:3]) if mark.connections else 'no connections'}"
                ),
            )
            created.append(proposal.id)
            logger.info(
                "Stigmergy→Evolution: mark %s (salience=%.2f) → proposal %s",
                mark.id, mark.salience, proposal.id,
            )
        except Exception as exc:
            logger.debug("Stigmergy→Evolution proposal creation failed: %s", exc)

    return created


# ---------------------------------------------------------------------------
# Cluster 2: Gate Results → Provider Routing
# Gate scores inform model selection — risky tasks get stronger models.
# ---------------------------------------------------------------------------

def gate_score_to_model_hint(
    gate_score: float,
    *,
    strong_model: str = "anthropic/claude-sonnet-4",
    weak_model: str = "meta-llama/llama-3.3-70b-instruct:free",
    threshold: float = 0.5,
) -> str:
    """Map a telos gate score to a model selection.

    Low gate score (risky) → stronger model. High score (safe) → efficient model.
    """
    if gate_score < threshold:
        logger.debug(
            "Gate→Routing: low score %.2f → strong model %s",
            gate_score, strong_model,
        )
        return strong_model
    return weak_model


# ---------------------------------------------------------------------------
# Cluster 3: Monitor Anomalies → Cascade META domain
# Anomaly patterns feed the meta cascade domain for self-healing.
# ---------------------------------------------------------------------------

def anomalies_to_cascade_input(
    anomalies: list[Anomaly],
) -> list[dict[str, Any]]:
    """Transform monitor anomalies into META cascade domain inputs.

    Each anomaly becomes a mutation candidate for the self-healing loop.
    """
    cascade_inputs: list[dict[str, Any]] = []
    for anomaly in anomalies:
        cascade_inputs.append({
            "source": "monitor",
            "anomaly_type": anomaly.anomaly_type,
            "severity": anomaly.severity,
            "description": anomaly.description,
            "suggested_action": _suggest_action(anomaly.anomaly_type),
            "anomaly_id": anomaly.id,
        })
    logger.info(
        "Monitor→Cascade: %d anomalies converted to META inputs",
        len(cascade_inputs),
    )
    return cascade_inputs


def _suggest_action(anomaly_type: str) -> str:
    """Map anomaly type to a suggested self-healing action."""
    actions = {
        "failure_spike": "investigate_error_pattern",
        "fitness_drift": "recalibrate_fitness_weights",
        "agent_silent": "restart_agent_or_reassign",
        "throughput_drop": "scale_up_or_rebalance",
    }
    return actions.get(anomaly_type, "investigate")


# ---------------------------------------------------------------------------
# Cluster 4: SubconsciousStream → Context Enrichment
# Lateral associations enrich agent context layers (Tier 5).
# ---------------------------------------------------------------------------

def associations_to_context_layer(
    associations: list[SubconsciousAssociation],
    *,
    min_strength: float = 0.3,
    max_items: int = 5,
) -> dict[str, Any]:
    """Build a Tier 5 context enrichment from subconscious associations.

    Returns a context dict suitable for injection into agent system prompts.
    """
    strong = [a for a in associations if a.strength >= min_strength]
    strong.sort(key=lambda a: a.strength, reverse=True)
    selected = strong[:max_items]

    if not selected:
        return {"tier5_associations": [], "tier5_summary": ""}

    summaries = []
    for assoc in selected:
        summaries.append(
            f"{assoc.source_a} ↔ {assoc.source_b} "
            f"({assoc.resonance_type}, strength={assoc.strength:.2f})"
        )

    return {
        "tier5_associations": [
            {
                "source_a": a.source_a,
                "source_b": a.source_b,
                "type": a.resonance_type,
                "strength": a.strength,
            }
            for a in selected
        ],
        "tier5_summary": (
            "Lateral associations from the subconscious stream:\n"
            + "\n".join(f"  - {s}" for s in summaries)
        ),
    }


# ---------------------------------------------------------------------------
# Cluster 5: Evolution Archive → Fitness Predictor feedback
# Completed proposals train the predictor (feedback loop).
# ---------------------------------------------------------------------------

async def archive_to_fitness_feedback(
    engine: DarwinEngine,
    *,
    last_n: int = 20,
) -> dict[str, Any]:
    """Feed completed evolution results back into the fitness predictor.

    Returns statistics about the feedback cycle.
    """
    archive = engine.archive
    entries = await archive.recent(limit=last_n)

    if not entries:
        return {"fed_back": 0, "avg_fitness": 0.0}

    total_fitness = 0.0
    count = 0
    for entry in entries:
        fitness = getattr(entry, "fitness", None)
        if fitness is not None and isinstance(fitness, (int, float)):
            total_fitness += float(fitness)
            count += 1

    avg = total_fitness / count if count > 0 else 0.0

    # Feed results into predictor if available
    predictor = getattr(engine, "_predictor", None)
    if predictor is not None:
        train_fn = getattr(predictor, "update_from_archive", None)
        if train_fn:
            try:
                await train_fn(entries)
                logger.info(
                    "Evolution→Predictor: fed %d entries (avg fitness=%.3f)",
                    len(entries), avg,
                )
            except Exception as exc:
                logger.debug("Predictor update failed: %s", exc)

    return {"fed_back": len(entries), "avg_fitness": round(avg, 4)}


# ---------------------------------------------------------------------------
# Unified wiring: run all clusters in one tick
# ---------------------------------------------------------------------------

async def run_micro_clusters(
    *,
    stigmergy: Any = None,
    engine: Any = None,
    monitor: Any = None,
    subconscious: Any = None,
) -> dict[str, Any]:
    """Run all available micro-cluster integrations in one pass.

    Safe to call with None subsystems — each cluster is independent.
    """
    results: dict[str, Any] = {}

    # Cluster 1: Stigmergy → Evolution
    if stigmergy is not None and engine is not None:
        try:
            seeds = await stigmergy_to_evolution_seeds(stigmergy, engine)
            results["stigmergy_evolution_seeds"] = len(seeds)
        except Exception as exc:
            logger.info("Stigmergy→Evolution cluster failed: %s", exc)

    # Cluster 3: Monitor → Cascade
    if monitor is not None:
        try:
            report = await monitor.check_health()
            if report.anomalies:
                cascade_inputs = anomalies_to_cascade_input(report.anomalies)
                results["anomaly_cascade_inputs"] = len(cascade_inputs)
        except Exception as exc:
            logger.info("Monitor→Cascade cluster failed: %s", exc)

    # Cluster 4: Subconscious → Context
    if subconscious is not None:
        try:
            dreams = await subconscious.dream()
            if dreams:
                ctx = associations_to_context_layer(dreams)
                results["context_enrichments"] = len(ctx.get("tier5_associations", []))
        except Exception as exc:
            logger.info("Subconscious→Context cluster failed: %s", exc)

    # Cluster 5: Evolution → Fitness Predictor
    if engine is not None:
        try:
            feedback = await archive_to_fitness_feedback(engine)
            results["fitness_feedback"] = feedback
        except Exception as exc:
            logger.info("Evolution→Predictor cluster failed: %s", exc)

    return results
