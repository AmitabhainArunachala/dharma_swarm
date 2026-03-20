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
"""

from __future__ import annotations

import json
import logging
import uuid
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
    timestamp: datetime = Field(default_factory=_utc_now)
    metadata: dict = Field(default_factory=dict)
    confidence: float = 1.0
    temporal_valid_from: datetime | None = None
    temporal_valid_to: datetime | None = None  # None = still valid


class MemoryRelationship(BaseModel):
    """A typed relationship between two memory entities."""

    from_id: str
    to_id: str
    rel_type: str  # caused, preceded, improved, degraded, witnessed, resolved, enabled
    timestamp: datetime = Field(default_factory=_utc_now)
    metadata: dict = Field(default_factory=dict)


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
        """Record a new entity. Returns entity ID. Auto-persists."""
        try:
            entity = MemoryEntity(
                entity_type=entity_type,
                description=description,
                metadata=metadata or {},
                confidence=confidence,
            )
            self._entities.append(entity)
            self._save_entity(entity)
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
            return {
                "total_entities": len(self._entities),
                "total_relationships": len(self._relationships),
                "by_type": by_type,
                "self_model_accuracy": round(self.self_model_accuracy(), 3),
            }
        except Exception as exc:
            logger.debug("OrganismMemory.stats failed (non-fatal): %s", exc)
            return {"total_entities": 0, "total_relationships": 0}

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
