"""organism_memory.py — The Organism's Autonoetic Self-Model.

The organism maintains a typed entity-relationship graph of its own
developmental history. This is NOT the Memory Palace (which stores
agent outputs). This is the organism knowing what it IS and how it
is becoming.

Storage: JSONL append-only, one record per line.
Inspired by Palantir's semantic ontology: entities, relationships,
temporal validity, confidence, provenance.

Ground: Varela (autopoiesis — the system maintains a model of itself),
        Damasio (somatic marker — past states bias future decisions),
        Dada Bhagwan (witness everything, Axiom P6).

Phase 6 additions:
- ingestion_time field (when we learned it, vs timestamp = when it happened)
- access_count + last_accessed (access tracking)
- invalidate_entity() / invalidate_contradicted() (soft invalidation)
- graph_traverse() (BFS relationship traversal)
- decay_confidence() (age-based confidence decay)
- gc() (soft-delete entities below threshold)
- find_related() (find entities connected by relationships)
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper: UTC now
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_mem_id(prefix: str = "m") -> str:
    """Generate a short unique ID with optional prefix."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class MemoryEntity(BaseModel):
    """A typed entity in the organism's developmental self-model."""

    id: str = Field(default_factory=lambda: _new_mem_id("e"))
    entity_type: str  # mutation, decision, algedonic_event, capability, insight,
    #                    agent_lineage, gnani_verdict
    description: str
    timestamp: datetime = Field(default_factory=_utc_now)   # event_time: when it happened
    metadata: dict = Field(default_factory=dict)
    confidence: float = 1.0
    temporal_valid_from: datetime | None = None
    temporal_valid_to: datetime | None = None  # None = still valid

    # Phase 6: bi-temporal + access tracking fields (all have defaults for backward compat)
    ingestion_time: datetime = Field(default_factory=_utc_now)  # when we recorded it
    access_count: int = 0
    last_accessed: datetime | None = None


class MemoryRelationship(BaseModel):
    """A typed relationship between two memory entities."""

    from_id: str
    to_id: str
    rel_type: str  # caused, preceded, improved, degraded, witnessed, resolved, enabled
    timestamp: datetime = Field(default_factory=_utc_now)
    metadata: dict = Field(default_factory=dict)
    # Phase 6: soft invalidation for edge temporal validity
    valid_until: datetime | None = None  # None = still valid


# ---------------------------------------------------------------------------
# OrganismMemory
# ---------------------------------------------------------------------------


class OrganismMemory:
    """The organism's autonoetic self-model.

    Typed entities with temporal validity and confidence scores.
    Append-only JSONL persistence — every write is immediately durable.

    Connected to:
    - Shakti (what the system CAN DO — capabilities, economic value)
    - Gnani (what the system SEES ABOUT ITSELF — self-model accuracy)
    """

    # Entity types
    ENTITY_TYPES: dict[str, str] = {
        "mutation": "A proposed or applied change to the organism",
        "decision": "A routing, scaling, or evolution decision",
        "algedonic_event": "A pain/pleasure signal and its resolution",
        "capability": "Something the organism can do (Shakti)",
        "insight": "Something the organism learned about itself (Gnani)",
        "agent_lineage": "An agent's birth, performance, and fate",
        "gnani_verdict": "A Gnani checkpoint result (PROCEED/HOLD)",
    }

    # Relationship types
    RELATIONSHIP_TYPES: dict[str, str] = {
        "caused": "Entity A caused Entity B",
        "preceded": "Entity A happened before Entity B",
        "improved": "Entity A improved metric X",
        "degraded": "Entity A degraded metric X",
        "witnessed": "The Gnani checkpoint witnessed this",
        "resolved": "This action resolved an algedonic event",
        "enabled": "This capability enabled this decision",
    }

    _ENTITIES_FILE = "entities.jsonl"
    _RELATIONSHIPS_FILE = "relationships.jsonl"

    def __init__(self, state_dir: Path) -> None:
        self._state_dir = state_dir / "organism_memory"
        self._entities: list[MemoryEntity] = []
        self._relationships: list[MemoryRelationship] = []
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.debug("OrganismMemory: could not create dir (non-fatal): %s", exc)
        self._load()

    # ------------------------------------------------------------------
    # Public write API
    # ------------------------------------------------------------------

    def record_event(
        self,
        entity_type: str,
        description: str,
        metadata: dict | None = None,
        confidence: float = 1.0,
    ) -> str:
        """Record a new entity. Returns entity ID. Auto-persists.

        Phase 6: if entity_type == 'insight', automatically calls
        invalidate_contradicted() to soft-invalidate conflicting older insights.
        """
        try:
            now = _utc_now()
            entity = MemoryEntity(
                entity_type=entity_type,
                description=description,
                metadata=metadata or {},
                confidence=confidence,
                timestamp=now,
                ingestion_time=now,
            )
            self._entities.append(entity)
            self._save_entity(entity)

            # Phase 6: auto-invalidate contradicted insights when a new insight arrives
            if entity_type == "insight":
                try:
                    self.invalidate_contradicted(entity.id)
                except Exception as exc:
                    logger.debug("invalidate_contradicted failed (non-fatal): %s", exc)

            return entity.id
        except Exception as exc:
            logger.debug("OrganismMemory.record_event failed (non-fatal): %s", exc)
            return ""

    def record_relationship(
        self,
        from_id: str,
        to_id: str,
        rel_type: str,
        metadata: dict | None = None,
    ) -> None:
        """Record a typed relationship between two entities. Auto-persists."""
        try:
            rel = MemoryRelationship(
                from_id=from_id,
                to_id=to_id,
                rel_type=rel_type,
                metadata=metadata or {},
            )
            self._relationships.append(rel)
            self._save_relationship(rel)
        except Exception as exc:
            logger.debug("OrganismMemory.record_relationship failed (non-fatal): %s", exc)

    # ------------------------------------------------------------------
    # Phase 6: Invalidation methods
    # ------------------------------------------------------------------

    def invalidate_entity(self, entity_id: str, reason: str = "") -> bool:
        """Soft-invalidate an entity by setting temporal_valid_to = now.

        Does NOT delete the record — preserves full history.
        Returns True if found and updated.
        """
        try:
            now = _utc_now()
            for entity in self._entities:
                if entity.id == entity_id:
                    entity.temporal_valid_to = now
                    if reason:
                        entity.metadata["invalidation_reason"] = reason
                        entity.metadata["invalidated_at"] = now.isoformat()
                    # Rewrite the full JSONL to reflect the update
                    self._rewrite_entities()
                    return True
            return False
        except Exception as exc:
            logger.debug("invalidate_entity failed (non-fatal): %s", exc)
            return False

    def invalidate_contradicted(self, new_entity_id: str) -> int:
        """When a new insight is added, check if it contradicts older insights.

        Simple heuristic: mark older insights with similar descriptions as
        superseded (temporal_valid_to = now). Similarity by shared key words.

        Returns number of entities invalidated.
        """
        try:
            new_entity = self._get_entity(new_entity_id)
            if new_entity is None or new_entity.entity_type != "insight":
                return 0

            now = _utc_now()
            new_words = set(new_entity.description.lower().split())
            invalidated = 0

            for entity in self._entities:
                # Skip self, already-invalid, and non-insights
                if entity.id == new_entity_id:
                    continue
                if entity.entity_type != "insight":
                    continue
                if entity.temporal_valid_to is not None:
                    continue

                # Jaccard similarity on words
                old_words = set(entity.description.lower().split())
                if not old_words or not new_words:
                    continue
                intersection = len(old_words & new_words)
                union = len(old_words | new_words)
                jaccard = intersection / union if union > 0 else 0.0

                # If ≥50% word overlap AND they share a key predicate word,
                # consider the new insight to supersede the old one
                if jaccard >= 0.5:
                    entity.temporal_valid_to = now
                    entity.metadata["superseded_by"] = new_entity_id
                    entity.metadata["superseded_at"] = now.isoformat()
                    invalidated += 1

            if invalidated > 0:
                self._rewrite_entities()

            return invalidated
        except Exception as exc:
            logger.debug("invalidate_contradicted failed (non-fatal): %s", exc)
            return 0

    # ------------------------------------------------------------------
    # Phase 6: Graph traversal
    # ------------------------------------------------------------------

    def graph_traverse(
        self,
        start_id: str,
        max_depth: int = 2,
        direction: str = "both",  # "out", "in", "both"
    ) -> list[MemoryEntity]:
        """BFS traversal of the entity relationship graph.

        Returns all entities reachable from start_id within max_depth hops.
        direction: "out" follows from_id→to_id, "in" follows to_id→from_id,
                   "both" follows both directions.
        """
        try:
            entity_map = {e.id: e for e in self._entities}
            if start_id not in entity_map:
                return []

            visited: set[str] = {start_id}
            queue: deque[tuple[str, int]] = deque([(start_id, 0)])
            result: list[MemoryEntity] = []

            while queue:
                current_id, depth = queue.popleft()
                if depth >= max_depth:
                    continue

                for rel in self._relationships:
                    # Skip invalidated relationships
                    if rel.valid_until is not None:
                        continue

                    neighbor_id: str | None = None
                    if direction in ("out", "both") and rel.from_id == current_id:
                        neighbor_id = rel.to_id
                    elif direction in ("in", "both") and rel.to_id == current_id:
                        neighbor_id = rel.from_id

                    if neighbor_id and neighbor_id not in visited and neighbor_id in entity_map:
                        visited.add(neighbor_id)
                        queue.append((neighbor_id, depth + 1))
                        result.append(entity_map[neighbor_id])

            return result
        except Exception as exc:
            logger.debug("graph_traverse failed (non-fatal): %s", exc)
            return []

    def find_related(
        self,
        entity_id: str,
        rel_types: list[str] | None = None,
    ) -> list[tuple[MemoryEntity, MemoryRelationship]]:
        """Find entities directly connected to entity_id by relationship.

        Returns list of (entity, relationship) tuples for immediate neighbors.
        rel_types: filter to specific relationship types, or None for all.
        """
        try:
            entity_map = {e.id: e for e in self._entities}
            result: list[tuple[MemoryEntity, MemoryRelationship]] = []

            for rel in self._relationships:
                # Skip invalidated
                if rel.valid_until is not None:
                    continue
                # Filter by rel_type if specified
                if rel_types is not None and rel.rel_type not in rel_types:
                    continue

                neighbor_id: str | None = None
                if rel.from_id == entity_id:
                    neighbor_id = rel.to_id
                elif rel.to_id == entity_id:
                    neighbor_id = rel.from_id

                if neighbor_id and neighbor_id in entity_map:
                    result.append((entity_map[neighbor_id], rel))

            return result
        except Exception as exc:
            logger.debug("find_related failed (non-fatal): %s", exc)
            return []

    # ------------------------------------------------------------------
    # Phase 6: Confidence decay and GC
    # ------------------------------------------------------------------

    def decay_confidence(
        self,
        max_age_days: float = 30.0,
        decay_rate: float = 0.95,
    ) -> int:
        """Apply age-based confidence decay to all valid entities.

        confidence *= decay_rate^(age_days) — exponential decay.
        Returns number of entities updated.
        """
        try:
            now = _utc_now().timestamp()
            updated = 0
            for entity in self._entities:
                # Only decay still-valid entities
                if entity.temporal_valid_to is not None:
                    continue
                try:
                    age_days = (now - entity.ingestion_time.timestamp()) / 86400.0
                    if age_days <= 0:
                        continue
                    decayed = entity.confidence * (decay_rate ** age_days)
                    decayed = max(0.0, min(1.0, decayed))
                    if abs(decayed - entity.confidence) > 1e-6:
                        entity.confidence = decayed
                        updated += 1
                except Exception:
                    pass

            if updated > 0:
                self._rewrite_entities()

            return updated
        except Exception as exc:
            logger.debug("decay_confidence failed (non-fatal): %s", exc)
            return 0

    def gc(self, min_confidence: float = 0.01) -> int:
        """Soft-delete entities below confidence threshold.

        Sets temporal_valid_to = now for entities with confidence < min_confidence.
        Does NOT remove records (append-only JSONL design).
        Returns number of entities soft-deleted.
        """
        try:
            now = _utc_now()
            removed = 0
            for entity in self._entities:
                if entity.temporal_valid_to is not None:
                    continue  # Already invalid
                if entity.confidence < min_confidence:
                    entity.temporal_valid_to = now
                    entity.metadata["gc_reason"] = f"confidence {entity.confidence:.4f} < {min_confidence}"
                    entity.metadata["gc_at"] = now.isoformat()
                    removed += 1

            if removed > 0:
                self._rewrite_entities()

            return removed
        except Exception as exc:
            logger.debug("gc failed (non-fatal): %s", exc)
            return 0

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    def developmental_narrative(self, last_n: int = 20) -> str:
        """Generate a text narrative of recent development.

        Format: chronological list of events with relationships noted.
        Used by dharma_attractor.full_attractor() to give the Gnani
        context about the organism's recent history.
        """
        try:
            recent = sorted(self._entities, key=lambda e: e.timestamp)[-last_n:]
            if not recent:
                return "No developmental history recorded yet."

            # Build a relationship lookup for quick access
            rel_lookup: dict[str, list[MemoryRelationship]] = {}
            for rel in self._relationships:
                rel_lookup.setdefault(rel.from_id, []).append(rel)

            lines: list[str] = ["Organism developmental history (most recent):"]
            for entity in recent:
                ts = entity.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
                line = f"  [{ts}] [{entity.entity_type}] {entity.description}"
                if entity.confidence < 1.0:
                    line += f" (confidence={entity.confidence:.2f})"
                if entity.temporal_valid_to is not None:
                    line += " [INVALIDATED]"
                lines.append(line)

                # Annotate relationships from this entity
                for rel in rel_lookup.get(entity.id, []):
                    lines.append(f"    → {rel.rel_type} → {rel.to_id}")

            return "\n".join(lines)
        except Exception as exc:
            logger.debug("developmental_narrative failed (non-fatal): %s", exc)
            return "Narrative unavailable."

    def self_model_accuracy(self) -> float:
        """Compare organism beliefs (insight entities) against metrics.

        Simple version: ratio of insights that are still temporally valid
        (not expired/contradicted) to total insights. Range 0.0-1.0.
        """
        try:
            insights = [e for e in self._entities if e.entity_type == "insight"]
            if not insights:
                return 1.0  # No beliefs recorded → no discrepancy known

            now = _utc_now()
            valid_insights = [
                e for e in insights
                if e.temporal_valid_to is None or e.temporal_valid_to > now
            ]
            return len(valid_insights) / len(insights)
        except Exception as exc:
            logger.debug("self_model_accuracy failed (non-fatal): %s", exc)
            return 1.0

    def shakti_profile(self) -> dict[str, list[dict[str, Any]]]:
        """Return capabilities with confidence scores.

        Returns dict of entity_type='capability' entities grouped by
        their metadata.get('domain', 'general').
        """
        try:
            capabilities = [e for e in self._entities if e.entity_type == "capability"]
            profile: dict[str, list[dict[str, Any]]] = {}
            for cap in capabilities:
                domain = cap.metadata.get("domain", "general")
                profile.setdefault(domain, []).append({
                    "id": cap.id,
                    "description": cap.description,
                    "confidence": cap.confidence,
                    "timestamp": cap.timestamp.isoformat(),
                })
            return profile
        except Exception as exc:
            logger.debug("shakti_profile failed (non-fatal): %s", exc)
            return {}

    def entities_by_type(
        self,
        entity_type: str,
        last_n: int = 10,
    ) -> list[MemoryEntity]:
        """Get recent entities of a given type."""
        try:
            filtered = [e for e in self._entities if e.entity_type == entity_type]
            return sorted(filtered, key=lambda e: e.timestamp)[-last_n:]
        except Exception:
            return []

    def stats(self) -> dict[str, Any]:
        """Summary stats for DGC status display."""
        try:
            by_type: dict[str, int] = {}
            for e in self._entities:
                by_type[e.entity_type] = by_type.get(e.entity_type, 0) + 1
            now = _utc_now()
            valid_count = sum(
                1 for e in self._entities
                if e.temporal_valid_to is None or e.temporal_valid_to > now
            )
            return {
                "total_entities": len(self._entities),
                "valid_entities": valid_count,
                "total_relationships": len(self._relationships),
                "by_type": by_type,
                "self_model_accuracy": round(self.self_model_accuracy(), 3),
            }
        except Exception as exc:
            logger.debug("OrganismMemory.stats failed (non-fatal): %s", exc)
            return {"total_entities": 0, "total_relationships": 0}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_entity(self, entity_id: str) -> MemoryEntity | None:
        """Look up an entity by ID."""
        for e in self._entities:
            if e.id == entity_id:
                return e
        return None

    def _touch_entity(self, entity: MemoryEntity) -> None:
        """Update access tracking on entity retrieval."""
        try:
            entity.access_count += 1
            entity.last_accessed = _utc_now()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_entity(self, entity: MemoryEntity) -> None:
        """Append entity to JSONL file."""
        try:
            record = {"type": "entity", **entity.model_dump(mode="json")}
            path = self._state_dir / self._ENTITIES_FILE
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
        except Exception as exc:
            logger.debug("_save_entity failed (non-fatal): %s", exc)

    def _save_relationship(self, rel: MemoryRelationship) -> None:
        """Append relationship to JSONL file."""
        try:
            record = {"type": "relationship", **rel.model_dump(mode="json")}
            path = self._state_dir / self._RELATIONSHIPS_FILE
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
        except Exception as exc:
            logger.debug("_save_relationship failed (non-fatal): %s", exc)

    def _rewrite_entities(self) -> None:
        """Rewrite the entire entities JSONL to reflect in-memory state.

        Called after mutations (invalidations, confidence changes).
        Uses a write-then-rename pattern for atomicity.
        """
        try:
            path = self._state_dir / self._ENTITIES_FILE
            tmp_path = path.with_suffix(".jsonl.tmp")
            with tmp_path.open("w", encoding="utf-8") as fh:
                for entity in self._entities:
                    record = {"type": "entity", **entity.model_dump(mode="json")}
                    fh.write(json.dumps(record) + "\n")
            tmp_path.replace(path)
        except Exception as exc:
            logger.debug("_rewrite_entities failed (non-fatal): %s", exc)

    def _load(self) -> None:
        """Load from JSONL files on disk."""
        # Load entities
        entities_path = self._state_dir / self._ENTITIES_FILE
        if entities_path.exists():
            try:
                with entities_path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            raw = json.loads(line)
                            raw.pop("type", None)
                            # Phase 6 backward compat: old records won't have
                            # ingestion_time / access_count / last_accessed
                            # Pydantic defaults handle this gracefully.
                            entity = MemoryEntity(**raw)
                            self._entities.append(entity)
                        except Exception as exc:
                            logger.debug("Skipping bad entity record: %s", exc)
            except Exception as exc:
                logger.debug("_load entities failed (non-fatal): %s", exc)

        # Load relationships
        rels_path = self._state_dir / self._RELATIONSHIPS_FILE
        if rels_path.exists():
            try:
                with rels_path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            raw = json.loads(line)
                            raw.pop("type", None)
                            # Phase 6 backward compat: old rels won't have valid_until
                            rel = MemoryRelationship(**raw)
                            self._relationships.append(rel)
                        except Exception as exc:
                            logger.debug("Skipping bad relationship record: %s", exc)
            except Exception as exc:
                logger.debug("_load relationships failed (non-fatal): %s", exc)

        logger.debug(
            "OrganismMemory loaded: %d entities, %d relationships",
            len(self._entities),
            len(self._relationships),
        )
