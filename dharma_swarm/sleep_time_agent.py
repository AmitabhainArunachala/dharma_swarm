"""sleep_time_agent.py — Background memory refinement during organism idle time.

Borrowed from Letta's sleep-time compute pattern:
    The organism does memory hygiene between active tasks rather than
    burning context window during agent runs.

Phases (original algorithmic pipeline):
1. Entity extraction: scan recent pulse history → OrganismMemory
2. Knowledge consolidation: merge duplicate/near-duplicate entities
3. Confidence decay: age-based decay on all entities
4. Implicit inference: discover relationships from shared metadata keys
5. Learned context generation: briefing block from high-confidence entities
6. Memory garbage collection: soft-delete very low confidence entities

Sprint 2 addition — PlugMem-inspired knowledge extraction:
7. Knowledge extraction: decompose context into Propositions + Prescriptions
   via LLM-driven KnowledgeExtractor, then store in KnowledgeStore.
   Controlled by ENABLE_KNOWLEDGE_EXTRACTION env var (default: true).

The Gnani provides wisdom. This agent provides plumbing.

Design:
- tick_interval: int = 5 (run every 5th heartbeat, configurable)
- tick() returns a stats dict so the organism can track what was done
- learned_context() returns precomputed briefing for agent prompt injection
- consolidate_knowledge() async method for post-task knowledge extraction
- Never-fatal: all failures caught and logged
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    pass  # Avoid circular imports; organism type used as Any

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _jaccard(a: str, b: str) -> float:
    """Jaccard similarity between two strings (word-level)."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    return intersection / union if union > 0 else 0.0


class SleepTimeAgent:
    """Background memory refinement during organism idle time.

    Runs on the heartbeat cycle (every N ticks, configurable).
    No LLM — pure algorithmic memory hygiene.

    Phases per tick:
    1. Extract entities from recent pulse history → OrganismMemory
    2. Consolidate duplicates (Jaccard similarity > consolidation_threshold)
    3. Decay confidence (age-based)
    4. Discover implicit relationships (shared metadata keys)
    5. Generate learned context block
    6. Garbage collect very low confidence entities

    Usage:
        agent = SleepTimeAgent(tick_interval=5)
        stats = agent.tick(cycle_number=42, organism=self)
        context = agent.learned_context()
    """

    def __init__(
        self,
        tick_interval: int = 5,
        consolidation_threshold: float = 0.6,
        decay_rate: float = 0.95,
        max_age_days: float = 30.0,
        gc_min_confidence: float = 0.01,
        max_context_entities: int = 10,
    ) -> None:
        self.tick_interval = tick_interval
        self.consolidation_threshold = consolidation_threshold
        self.decay_rate = decay_rate
        self.max_age_days = max_age_days
        self.gc_min_confidence = gc_min_confidence
        self.max_context_entities = max_context_entities

        self._last_tick_cycle: int = -1
        self._tick_count: int = 0
        self._learned_context_block: str = ""
        self._stats_history: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Main tick
    # ------------------------------------------------------------------

    def tick(self, cycle_number: int, organism: Any) -> dict[str, Any]:
        """Main sleep-time tick. Returns stats dict.

        Only runs every tick_interval heartbeat cycles.
        All phases are non-fatal — individual failures don't abort the tick.
        """
        # Only run on configured interval
        if (cycle_number % self.tick_interval) != 0:
            return {"skipped": True, "cycle": cycle_number}

        t0 = time.monotonic()
        self._tick_count += 1
        self._last_tick_cycle = cycle_number

        stats: dict[str, Any] = {
            "cycle": cycle_number,
            "tick_number": self._tick_count,
            "phases": {},
        }

        # Get memory subsystem references (never-fatal access)
        memory = getattr(organism, "memory", None)
        palace = getattr(organism, "palace", None)
        pulses = getattr(organism, "_pulses", [])

        # Phase 1: Extract entities from recent pulses
        try:
            extracted = self._phase_extract_entities(memory, pulses)
            stats["phases"]["extract"] = {"entities_extracted": extracted}
        except Exception as exc:
            logger.debug("SleepTimeAgent phase 1 (extract) failed: %s", exc)
            stats["phases"]["extract"] = {"error": str(exc)}

        # Phase 2: Consolidate duplicate entities
        try:
            consolidated = self._phase_consolidate(memory)
            stats["phases"]["consolidate"] = {"merged": consolidated}
        except Exception as exc:
            logger.debug("SleepTimeAgent phase 2 (consolidate) failed: %s", exc)
            stats["phases"]["consolidate"] = {"error": str(exc)}

        # Phase 3: Decay confidence
        try:
            decayed = self._phase_decay(memory, palace)
            stats["phases"]["decay"] = {"entities_decayed": decayed}
        except Exception as exc:
            logger.debug("SleepTimeAgent phase 3 (decay) failed: %s", exc)
            stats["phases"]["decay"] = {"error": str(exc)}

        # Phase 4: Discover implicit relationships
        try:
            inferred = self._phase_infer_relationships(memory)
            stats["phases"]["infer"] = {"relationships_inferred": inferred}
        except Exception as exc:
            logger.debug("SleepTimeAgent phase 4 (infer) failed: %s", exc)
            stats["phases"]["infer"] = {"error": str(exc)}

        # Phase 5: Generate learned context block
        try:
            context_len = self._phase_generate_context(memory)
            stats["phases"]["context"] = {"context_length": context_len}
        except Exception as exc:
            logger.debug("SleepTimeAgent phase 5 (context) failed: %s", exc)
            stats["phases"]["context"] = {"error": str(exc)}

        # Phase 6: Garbage collection
        try:
            gc_count = self._phase_gc(memory, palace)
            stats["phases"]["gc"] = {"removed": gc_count}
        except Exception as exc:
            logger.debug("SleepTimeAgent phase 6 (gc) failed: %s", exc)
            stats["phases"]["gc"] = {"error": str(exc)}

        stats["duration_ms"] = round((time.monotonic() - t0) * 1000, 2)
        self._stats_history.append(stats)
        if len(self._stats_history) > 100:
            self._stats_history = self._stats_history[-100:]

        logger.debug(
            "SleepTimeAgent tick %d (cycle %d): %s",
            self._tick_count,
            cycle_number,
            {k: v for k, v in stats["phases"].items()},
        )
        return stats

    # ------------------------------------------------------------------
    # Phase implementations
    # ------------------------------------------------------------------

    def _phase_extract_entities(
        self,
        memory: Any,
        pulses: list[Any],
    ) -> int:
        """Phase 1: Extract entities from recent pulse data.

        Scans the last N pulses and extracts structured observations
        (health transitions, algedonic events, scaling triggers) as
        MemoryEntity records.

        Returns number of entities extracted.
        """
        if memory is None or not pulses:
            return 0

        # Only process the most recent pulses since last tick
        recent_pulses = pulses[-self.tick_interval * 2:]
        extracted = 0

        for pulse in recent_pulses:
            try:
                pulse_data = pulse.to_dict()
                cycle = pulse_data.get("cycle", 0)

                # Extract algedonic events
                if pulse_data.get("algedonic_active", 0) > 0:
                    # Don't duplicate — check if we've already recorded this pulse's algedonic
                    already_recorded = any(
                        e.entity_type == "algedonic_event" and
                        e.metadata.get("pulse_cycle") == cycle
                        for e in getattr(memory, "_entities", [])
                    )
                    if not already_recorded:
                        memory.record_event(
                            entity_type="algedonic_event",
                            description=(
                                f"Algedonic signals active in cycle {cycle}: "
                                f"count={pulse_data['algedonic_active']}, "
                                f"health={pulse_data.get('fleet_health', 0):.2f}"
                            ),
                            metadata={
                                "pulse_cycle": cycle,
                                "source": "sleep_time_agent",
                                "algedonic_count": pulse_data["algedonic_active"],
                            },
                            confidence=0.9,
                        )
                        extracted += 1

                # Extract health state observations as insights
                health = pulse_data.get("fleet_health", 1.0)
                coherence = pulse_data.get("identity_coherence", 1.0)
                if health < 0.4 or coherence < 0.3:
                    already_recorded = any(
                        e.entity_type == "insight" and
                        e.metadata.get("pulse_cycle") == cycle and
                        e.metadata.get("source") == "sleep_time_agent_health"
                        for e in getattr(memory, "_entities", [])
                    )
                    if not already_recorded:
                        memory.record_event(
                            entity_type="insight",
                            description=(
                                f"Organism in degraded state at cycle {cycle}: "
                                f"health={health:.2f}, coherence={coherence:.2f}"
                            ),
                            metadata={
                                "pulse_cycle": cycle,
                                "source": "sleep_time_agent_health",
                                "health": health,
                                "coherence": coherence,
                            },
                            confidence=0.7,
                        )
                        extracted += 1

            except Exception as exc:
                logger.debug("Entity extraction from pulse failed: %s", exc)

        return extracted

    def _phase_consolidate(self, memory: Any) -> int:
        """Phase 2: Merge near-duplicate entities.

        For each entity type, find pairs with Jaccard similarity > threshold
        and soft-invalidate the older one (the newer retains the knowledge).

        Returns number of entities consolidated (invalidated as duplicates).
        """
        if memory is None:
            return 0

        entities = getattr(memory, "_entities", [])
        if len(entities) < 2:
            return 0

        consolidated = 0

        # Group by entity_type for efficiency
        by_type: dict[str, list[Any]] = {}
        for e in entities:
            if e.temporal_valid_to is None:  # Only process still-valid entities
                by_type.setdefault(e.entity_type, []).append(e)

        for entity_type, group in by_type.items():
            if len(group) < 2:
                continue

            # Sort by timestamp (oldest first) so we invalidate older dups
            group_sorted = sorted(group, key=lambda e: e.timestamp)

            # O(n²) pairwise — acceptable for small groups (< 100)
            invalidated_ids: set[str] = set()
            for i, ea in enumerate(group_sorted):
                if ea.id in invalidated_ids:
                    continue
                for eb in group_sorted[i + 1:]:
                    if eb.id in invalidated_ids:
                        continue
                    sim = _jaccard(ea.description, eb.description)
                    if sim >= self.consolidation_threshold:
                        # Invalidate the older entity (ea), keep the newer (eb)
                        try:
                            memory.invalidate_entity(
                                ea.id,
                                reason=f"consolidated_duplicate_of:{eb.id} (jaccard={sim:.2f})",
                            )
                            invalidated_ids.add(ea.id)
                            consolidated += 1
                        except Exception:
                            pass
                        break  # Move to next ea

        return consolidated

    def _phase_decay(self, memory: Any, palace: Any) -> int:
        """Phase 3: Apply age-based confidence decay.

        Delegates to both OrganismMemory.decay_confidence() and
        MemoryPalace.decay() (which forwards to VectorStore).

        Returns total number of records decayed.
        """
        total = 0

        if memory is not None:
            try:
                total += memory.decay_confidence(
                    max_age_days=self.max_age_days,
                    decay_rate=self.decay_rate,
                )
            except Exception as exc:
                logger.debug("OrganismMemory decay failed: %s", exc)

        if palace is not None:
            try:
                total += palace.decay(
                    max_age_days=self.max_age_days,
                    decay_rate=self.decay_rate,
                )
            except Exception as exc:
                logger.debug("MemoryPalace decay failed: %s", exc)

        return total

    def _phase_infer_relationships(self, memory: Any) -> int:
        """Phase 4: Discover implicit relationships between entities.

        Heuristic: entities sharing the same metadata key values are likely
        related. For example, two entities with the same 'agent_id' or
        'pulse_cycle' in their metadata may be related by 'preceded' or
        'caused'.

        Returns number of relationships inferred and recorded.
        """
        if memory is None:
            return 0

        entities = getattr(memory, "_entities", [])
        existing_rels = getattr(memory, "_relationships", [])

        # Build set of existing (from_id, to_id) pairs for dedup
        existing_pairs: set[tuple[str, str]] = set()
        for rel in existing_rels:
            existing_pairs.add((rel.from_id, rel.to_id))

        inferred = 0

        # Group entities by shared metadata keys
        # Focus on high-value linking keys
        link_keys = ["agent_id", "pulse_cycle", "trigger", "domain"]

        key_groups: dict[str, dict[str, list[Any]]] = {}
        for e in entities:
            if e.temporal_valid_to is not None:
                continue
            for key in link_keys:
                val = e.metadata.get(key)
                if val is not None:
                    val_str = str(val)
                    key_groups.setdefault(key, {}).setdefault(val_str, []).append(e)

        for key, val_map in key_groups.items():
            for val, group in val_map.items():
                if len(group) < 2:
                    continue
                # Create 'preceded' relationships between consecutive entities
                sorted_group = sorted(group, key=lambda e: e.timestamp)
                for i in range(len(sorted_group) - 1):
                    ea = sorted_group[i]
                    eb = sorted_group[i + 1]
                    pair = (ea.id, eb.id)
                    if pair not in existing_pairs:
                        try:
                            memory.record_relationship(
                                from_id=ea.id,
                                to_id=eb.id,
                                rel_type="preceded",
                                metadata={
                                    "inferred_by": "sleep_time_agent",
                                    "shared_key": key,
                                    "shared_value": val,
                                },
                            )
                            existing_pairs.add(pair)
                            inferred += 1
                            # Cap inference to avoid explosive relationship growth
                            if inferred >= 20:
                                return inferred
                        except Exception as exc:
                            logger.debug("Relationship inference failed: %s", exc)

        return inferred

    def _phase_generate_context(self, memory: Any) -> int:
        """Phase 5: Compile learned context block from high-confidence entities.

        This is the sleep-time compute output — precomputed understanding
        that can be injected into agent prompts without re-querying.

        Selects: highest-confidence, most-recently-accessed entities.
        Returns length of context string.
        """
        if memory is None:
            self._learned_context_block = ""
            return 0

        entities = getattr(memory, "_entities", [])
        if not entities:
            self._learned_context_block = ""
            return 0

        now = _utc_now()

        # Filter to valid, high-confidence entities
        valid = [
            e for e in entities
            if (e.temporal_valid_to is None or e.temporal_valid_to > now)
            and e.confidence >= 0.3
        ]

        if not valid:
            self._learned_context_block = ""
            return 0

        # Sort by composite score: confidence × recency
        def _score(e: Any) -> float:
            try:
                age_days = (now.timestamp() - e.ingestion_time.timestamp()) / 86400.0
                recency = max(0.0, 1.0 - age_days / 30.0)
                access_bonus = min(1.0, getattr(e, "access_count", 0) / 10.0)
                return e.confidence * 0.5 + recency * 0.3 + access_bonus * 0.2
            except Exception:
                return e.confidence

        ranked = sorted(valid, key=_score, reverse=True)
        top = ranked[:self.max_context_entities]

        lines: list[str] = ["[LEARNED CONTEXT — generated by SleepTimeAgent]"]
        for e in top:
            conf_str = f" (conf={e.confidence:.2f})" if e.confidence < 1.0 else ""
            lines.append(f"• [{e.entity_type}]{conf_str} {e.description}")

        self._learned_context_block = "\n".join(lines)
        return len(self._learned_context_block)

    def _phase_gc(self, memory: Any, palace: Any) -> int:
        """Phase 6: Garbage collect very low confidence records.

        Soft-deletes in OrganismMemory and hard-deletes in VectorStore.
        Returns total records removed.
        """
        total = 0

        if memory is not None:
            try:
                total += memory.gc(min_confidence=self.gc_min_confidence)
            except Exception as exc:
                logger.debug("OrganismMemory gc failed: %s", exc)

        if palace is not None:
            try:
                total += palace.gc(min_confidence=self.gc_min_confidence)
            except Exception as exc:
                logger.debug("MemoryPalace gc failed: %s", exc)

        return total

    # ------------------------------------------------------------------
    # Output API
    # ------------------------------------------------------------------

    def learned_context(self) -> str:
        """Return the current learned context block.

        This is the sleep-time compute output — precomputed understanding
        for injection into agent prompts.

        Returns empty string if no context has been generated yet.
        """
        return self._learned_context_block

    def stats(self) -> dict[str, Any]:
        """Return SleepTimeAgent statistics."""
        return {
            "tick_count": self._tick_count,
            "last_tick_cycle": self._last_tick_cycle,
            "tick_interval": self.tick_interval,
            "context_length": len(self._learned_context_block),
            "recent_ticks": self._stats_history[-5:] if self._stats_history else [],
        }

    # ------------------------------------------------------------------
    # Sprint 2: Knowledge extraction (PlugMem-inspired)
    # ------------------------------------------------------------------

    async def consolidate_knowledge(
        self,
        task_context: str,
        task_outcome: dict[str, Any] | None = None,
        llm_client: Any = None,
        knowledge_store: Any = None,
    ) -> dict[str, Any]:
        """Extract structured knowledge from task context.

        Decomposes episodic task context into Propositions (facts) and
        Prescriptions (skills), scores them based on outcome, and stores
        in KnowledgeStore.  This is the PlugMem-inspired consolidation
        pipeline that runs after task completion.

        Controlled by ENABLE_KNOWLEDGE_EXTRACTION env var (default: true).

        Returns stats dict with counts of extracted knowledge units.
        """
        # Check if knowledge extraction is enabled
        enabled = os.getenv("ENABLE_KNOWLEDGE_EXTRACTION", "true").strip().lower()
        if enabled not in ("1", "true", "yes", "on"):
            return {"skipped": True, "reason": "knowledge_extraction_disabled"}

        if not task_context or not task_context.strip():
            return {"skipped": True, "reason": "empty_context"}

        task_outcome = task_outcome or {}
        result: dict[str, Any] = {
            "propositions": 0,
            "prescriptions": 0,
            "errors": [],
        }

        try:
            from dharma_swarm.knowledge_extractor import KnowledgeExtractor
            from dharma_swarm.knowledge_units import KnowledgeStore, get_default_knowledge_db_path

            extractor = KnowledgeExtractor(llm_client)

            # Extract both knowledge types in parallel
            propositions, prescriptions = await extractor.extract_all(task_context)

            # Score prescriptions based on task outcome
            for presc in prescriptions:
                if task_outcome.get("success"):
                    presc.return_score = max(presc.return_score, 0.7)
                else:
                    presc.return_score = min(presc.return_score, 0.3)

            # Store in KnowledgeStore
            if knowledge_store is None:
                db_path = get_default_knowledge_db_path()
                knowledge_store = KnowledgeStore(db_path)

            for prop in propositions:
                try:
                    knowledge_store.store_proposition(prop)
                    result["propositions"] += 1
                except Exception as exc:
                    result["errors"].append(f"prop_store: {exc}")

            for presc in prescriptions:
                try:
                    knowledge_store.store_prescription(presc)
                    result["prescriptions"] += 1
                except Exception as exc:
                    result["errors"].append(f"presc_store: {exc}")

        except Exception as exc:
            logger.debug("Knowledge consolidation failed: %s", exc)
            result["errors"].append(str(exc))

        return result


__all__ = ["SleepTimeAgent"]
