"""Ontology Adapters -- Wire live subsystems into the Ontology Hub.

Each adapter reads a subsystem's native format (JSONL/JSON) and emits
OntologyObj + Link instances. Adapters are idempotent: re-running
produces the same objects (deduplication by source ID).

This is the bridge between "118K lines of working code" and
"every entity can find every other entity through typed relationships."
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from dharma_swarm.ontology import (
    Link,
    LinkCardinality,
    LinkDef,
    ObjectType,
    OntologyObj,
    OntologyRegistry,
    PropertyDef,
    PropertyType,
    _utc_now,
    validate_object,
)

logger = logging.getLogger(__name__)

_DEFAULT_BASE = Path.home() / ".dharma"


# ---------------------------------------------------------------------------
# New ObjectTypes for hub subsystems
# ---------------------------------------------------------------------------

_STIGMERGY_MARK_TYPE = ObjectType(
    name="StigmergyMark",
    description="A pheromone mark left by an agent on the stigmergic lattice",
    properties={
        "agent": PropertyDef(
            name="agent",
            property_type=PropertyType.STRING,
            required=True,
            description="Agent that left this mark",
        ),
        "file_path": PropertyDef(
            name="file_path",
            property_type=PropertyType.PATH,
            description="File the mark references",
        ),
        "action": PropertyDef(
            name="action",
            property_type=PropertyType.STRING,
            description="Action type: read, write, scan, connect, dream",
        ),
        "observation": PropertyDef(
            name="observation",
            property_type=PropertyType.TEXT,
            searchable=True,
            description="What the agent observed",
        ),
        "salience": PropertyDef(
            name="salience",
            property_type=PropertyType.FLOAT,
            description="Salience weight 0.0-1.0",
        ),
        "connections": PropertyDef(
            name="connections",
            property_type=PropertyType.LIST,
            description="Connected file paths",
        ),
        "access_count": PropertyDef(
            name="access_count",
            property_type=PropertyType.INTEGER,
            description="Times this mark has been read",
        ),
    },
    links=[
        LinkDef(
            name="left_by",
            source_type="StigmergyMark",
            target_type="AgentIdentity",
            cardinality=LinkCardinality.MANY_TO_ONE,
            inverse_name="stigmergy_marks",
            description="Agent that left this mark",
        ),
    ],
    telos_alignment=0.6,
    icon="S",
)

_ZEITGEIST_SIGNAL_TYPE = ObjectType(
    name="ZeitgeistSignal",
    description="An environmental signal detected by the S4 zeitgeist scanner",
    properties={
        "source": PropertyDef(
            name="source",
            property_type=PropertyType.STRING,
            description="Signal origin: local_scan, claude_scan, gate_pattern, manual",
        ),
        "category": PropertyDef(
            name="category",
            property_type=PropertyType.ENUM,
            enum_values=[
                "competing_research",
                "tool_release",
                "methodology",
                "threat",
                "opportunity",
            ],
            description="Signal classification",
        ),
        "title": PropertyDef(
            name="title",
            property_type=PropertyType.STRING,
            searchable=True,
            description="Human-readable signal summary",
        ),
        "relevance_score": PropertyDef(
            name="relevance_score",
            property_type=PropertyType.FLOAT,
            description="Relevance to active research 0.0-1.0",
        ),
        "keywords": PropertyDef(
            name="keywords",
            property_type=PropertyType.LIST,
            description="Matched keywords",
        ),
        "description": PropertyDef(
            name="description",
            property_type=PropertyType.TEXT,
            searchable=True,
            description="Extended signal explanation",
        ),
    },
    links=[
        LinkDef(
            name="detected_in",
            source_type="ZeitgeistSignal",
            target_type="ResearchThread",
            cardinality=LinkCardinality.MANY_TO_ONE,
            inverse_name="zeitgeist_signals",
            description="Research thread this signal relates to",
        ),
    ],
    telos_alignment=0.7,
    icon="Z",
)

_IDENTITY_SNAPSHOT_TYPE = ObjectType(
    name="IdentitySnapshot",
    description="S5 identity coherence measurement snapshot",
    properties={
        "tcs": PropertyDef(
            name="tcs",
            property_type=PropertyType.FLOAT,
            description="Telos Coherence Score",
        ),
        "gpr": PropertyDef(
            name="gpr",
            property_type=PropertyType.FLOAT,
            description="Gate Passage Rate",
        ),
        "bsi": PropertyDef(
            name="bsi",
            property_type=PropertyType.FLOAT,
            description="Behavioral Swabhaav Index",
        ),
        "rm": PropertyDef(
            name="rm",
            property_type=PropertyType.FLOAT,
            description="Research Momentum",
        ),
        "regime": PropertyDef(
            name="regime",
            property_type=PropertyType.ENUM,
            enum_values=["stable", "drifting", "critical"],
            description="Current identity regime",
        ),
        "correction_issued": PropertyDef(
            name="correction_issued",
            property_type=PropertyType.BOOLEAN,
            description="Whether a .FOCUS correction was written",
        ),
    },
    telos_alignment=0.95,
    icon="I",
)

_CORPUS_CLAIM_TYPE = ObjectType(
    name="CorpusClaim",
    description="An ethical or operational claim in the dharma corpus",
    properties={
        "claim_text": PropertyDef(
            name="claim_text",
            property_type=PropertyType.TEXT,
            searchable=True,
            required=True,
            description="The claim statement",
        ),
        "status": PropertyDef(
            name="status",
            property_type=PropertyType.ENUM,
            enum_values=["proposed", "accepted", "deprecated", "rejected"],
            description="Claim lifecycle status",
        ),
        "evidence": PropertyDef(
            name="evidence",
            property_type=PropertyType.TEXT,
            description="Serialized evidence links",
        ),
        "confidence": PropertyDef(
            name="confidence",
            property_type=PropertyType.FLOAT,
            description="Confidence score 0.0-1.0",
        ),
    },
    links=[
        LinkDef(
            name="authored_by",
            source_type="CorpusClaim",
            target_type="AgentIdentity",
            cardinality=LinkCardinality.MANY_TO_ONE,
            inverse_name="corpus_claims",
            description="Agent that authored this claim",
        ),
    ],
    telos_alignment=0.9,
    icon="C",
)

_HUB_TYPES: list[ObjectType] = [
    _STIGMERGY_MARK_TYPE,
    _ZEITGEIST_SIGNAL_TYPE,
    _IDENTITY_SNAPSHOT_TYPE,
    _CORPUS_CLAIM_TYPE,
]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_hub_types(registry: OntologyRegistry) -> None:
    """Register the 4 new hub ObjectTypes and their links into a registry.

    Safe to call multiple times -- ObjectType registration overwrites
    by name, so re-registration is idempotent.
    """
    for obj_type in _HUB_TYPES:
        registry.register_type(obj_type)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Return type alias for adapter results.
AdapterResult = list[tuple[OntologyObj, list[Link]]]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file, skipping blank or corrupt lines.

    Args:
        path: Path to the JSONL file.

    Returns:
        List of parsed JSON dicts (one per valid line).
    """
    if not path.exists():
        logger.debug("JSONL file not found: %s", path)
        return []
    records: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to read %s: %s", path, exc)
        return []
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            records.append(json.loads(stripped))
        except json.JSONDecodeError:
            logger.warning("Corrupt JSON at %s:%d -- skipping", path, lineno)
    return records


def _make_obj(
    obj_id: str,
    type_name: str,
    properties: dict[str, Any],
    created_by: str = "adapter",
) -> OntologyObj:
    """Create an OntologyObj with a deterministic ID.

    Args:
        obj_id: Stable identifier for idempotent sync.
        type_name: Registered ObjectType name.
        properties: Property dict matching the ObjectType schema.
        created_by: Creator tag.

    Returns:
        A fully constructed OntologyObj.
    """
    now = _utc_now()
    return OntologyObj(
        id=obj_id,
        type_name=type_name,
        properties=properties,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )


def _make_link(
    link_name: str,
    source_id: str,
    source_type: str,
    target_id: str,
    target_type: str,
) -> Link:
    """Create a Link instance.

    Args:
        link_name: Name of the link definition.
        source_id: Source OntologyObj ID.
        source_type: Source ObjectType name.
        target_id: Target OntologyObj ID.
        target_type: Target ObjectType name.

    Returns:
        A Link instance.
    """
    return Link(
        link_name=link_name,
        source_id=source_id,
        source_type=source_type,
        target_id=target_id,
        target_type=target_type,
        created_by="adapter",
    )


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------


def adapt_stigmergy(base_path: Path | None = None) -> AdapterResult:
    """Read ~/.dharma/stigmergy/marks.jsonl -> StigmergyMark objects.

    Each mark gets a deterministic ID ``stig_{mark.id}`` so re-runs
    produce the same objects. The ``left_by`` link targets an
    AgentIdentity object named ``agent_{mark.agent}``.

    Args:
        base_path: Override for ``~/.dharma``.

    Returns:
        List of (OntologyObj, [Link, ...]) tuples.
    """
    base = base_path or _DEFAULT_BASE
    marks_file = base / "stigmergy" / "marks.jsonl"
    records = _read_jsonl(marks_file)

    results: AdapterResult = []
    for rec in records:
        try:
            mark_id = rec.get("id", "")
            if not mark_id:
                continue
            agent = rec.get("agent", "")
            if not agent:
                continue

            obj_id = f"stig_{mark_id}"
            props: dict[str, Any] = {
                "agent": agent,
                "file_path": rec.get("file_path", ""),
                "action": rec.get("action", ""),
                "observation": rec.get("observation", ""),
                "salience": float(rec.get("salience", 0.5)),
                "connections": rec.get("connections", []),
                "access_count": int(rec.get("access_count", 0)),
            }
            obj = _make_obj(obj_id, "StigmergyMark", props)
            links: list[Link] = [
                _make_link(
                    "left_by",
                    obj_id,
                    "StigmergyMark",
                    f"agent_{agent}",
                    "AgentIdentity",
                ),
            ]
            results.append((obj, links))
        except Exception as exc:
            logger.warning("adapt_stigmergy: skipping record: %s", exc)
    return results


def adapt_file_profiles(db_path: Path | None = None) -> AdapterResult:
    """Read ~/.dharma/file_profiles.db -> FileProfile ontology objects.

    Each profile gets a deterministic ID ``fprof_{profile.id}``.
    Creates ``profiles`` link targets to file path nodes.
    """
    import sqlite3

    db = db_path or (_DEFAULT_BASE / "file_profiles.db")
    if not db.exists():
        return []

    results: AdapterResult = []
    try:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM file_profiles ORDER BY impact_score DESC LIMIT 500")
        for row in cursor:
            obj_id = f"fprof_{row['id']}"
            props: dict[str, Any] = {
                "path": row["path"],
                "filename": row["filename"],
                "domain": row["domain"] or "",
                "semantic_density": float(row["semantic_density"] or 0),
                "connectivity_degree": int(row["connectivity_degree"] or 0),
                "impact_score": float(row["impact_score"] or 0),
                "mission_alignment": float(row["mission_alignment"] or 0),
                "lines": int(row["lines"] or 0),
                "complexity": float(row["complexity"] or 0),
                "mark_count": int(row["mark_count"] or 0),
            }
            obj = _make_obj(obj_id, "FileProfile", props)
            links: list[Link] = []
            results.append((obj, links))
        conn.close()
    except Exception as exc:
        logger.warning("adapt_file_profiles: %s", exc)

    return results


def adapt_zeitgeist(base_path: Path | None = None) -> AdapterResult:
    """Read ~/.dharma/meta/zeitgeist.jsonl -> ZeitgeistSignal objects.

    Each signal gets a deterministic ID ``zeit_{signal.id}``.

    Args:
        base_path: Override for ``~/.dharma``.

    Returns:
        List of (OntologyObj, [Link, ...]) tuples.
    """
    base = base_path or _DEFAULT_BASE
    log_file = base / "meta" / "zeitgeist.jsonl"
    records = _read_jsonl(log_file)

    results: AdapterResult = []
    for rec in records:
        try:
            sig_id = rec.get("id", "")
            if not sig_id:
                continue

            obj_id = f"zeit_{sig_id}"
            props: dict[str, Any] = {
                "source": rec.get("source", ""),
                "category": rec.get("category", ""),
                "title": rec.get("title", ""),
                "relevance_score": float(rec.get("relevance_score", 0.0)),
                "keywords": rec.get("keywords", []),
                "description": rec.get("description", ""),
            }
            obj = _make_obj(obj_id, "ZeitgeistSignal", props)
            # No automatic link -- detected_in requires knowing which
            # ResearchThread the signal relates to, which is not encoded
            # in the raw JSONL.
            results.append((obj, []))
        except Exception as exc:
            logger.warning("adapt_zeitgeist: skipping record: %s", exc)
    return results


def adapt_identity(base_path: Path | None = None) -> AdapterResult:
    """Read ~/.dharma/meta/identity_history.jsonl -> IdentitySnapshot objects.

    Each snapshot gets a deterministic ID ``ident_{snapshot.id}``.

    Args:
        base_path: Override for ``~/.dharma``.

    Returns:
        List of (OntologyObj, [Link, ...]) tuples.
    """
    base = base_path or _DEFAULT_BASE
    history_file = base / "meta" / "identity_history.jsonl"
    records = _read_jsonl(history_file)

    results: AdapterResult = []
    for rec in records:
        try:
            snap_id = rec.get("id", "")
            if not snap_id:
                continue

            obj_id = f"ident_{snap_id}"
            props: dict[str, Any] = {
                "tcs": float(rec.get("tcs", 0.5)),
                "gpr": float(rec.get("gpr", 0.5)),
                "bsi": float(rec.get("bsi", 0.5)),
                "rm": float(rec.get("rm", 0.5)),
                "regime": rec.get("regime", "stable"),
                "correction_issued": bool(rec.get("correction_issued", False)),
            }
            obj = _make_obj(obj_id, "IdentitySnapshot", props)
            results.append((obj, []))
        except Exception as exc:
            logger.warning("adapt_identity: skipping record: %s", exc)
    return results


def adapt_gates(base_path: Path | None = None) -> AdapterResult:
    """Read ~/.dharma/witness/*.jsonl -> GateDecisionRecord objects.

    Reads all JSONL files in the witness directory. Each entry gets a
    deterministic ID based on the file name and line content hash.

    Args:
        base_path: Override for ``~/.dharma``.

    Returns:
        List of (OntologyObj, [Link, ...]) tuples.
    """
    base = base_path or _DEFAULT_BASE
    witness_dir = base / "witness"
    if not witness_dir.exists():
        return []

    results: AdapterResult = []
    for log_file in sorted(witness_dir.glob("*.jsonl")):
        records = _read_jsonl(log_file)
        for idx, rec in enumerate(records):
            try:
                # Build a stable ID from filename + index
                stem = log_file.stem
                obj_id = f"gate_{stem}_{idx:06d}"

                decision = rec.get("outcome", rec.get("decision", ""))
                if not decision:
                    continue

                # Normalize decision values
                decision_lower = decision.lower()
                if decision_lower in ("pass", "allow"):
                    decision_norm = "allow"
                elif decision_lower in ("block", "blocked"):
                    decision_norm = "block"
                elif decision_lower in ("warn", "review"):
                    decision_norm = "review"
                else:
                    decision_norm = "review"

                props: dict[str, Any] = {
                    "proposal_id": rec.get("proposal_id", rec.get("task_id", "")),
                    "decision": decision_norm,
                    "reason": rec.get("reason", rec.get("detail", "")),
                    "gate_results": rec.get("gate_results", {}),
                    "witness_reroutes": int(rec.get("witness_reroutes", 0)),
                }
                obj = _make_obj(obj_id, "GateDecisionRecord", props)
                results.append((obj, []))
            except Exception as exc:
                logger.warning("adapt_gates: skipping record in %s: %s", log_file, exc)
    return results


def adapt_evolution(base_path: Path | None = None) -> AdapterResult:
    """Read ~/.dharma/evolution/archive.jsonl -> EvolutionEntry objects.

    Each archive entry gets a deterministic ID based on its index in
    the file (or its ``id`` field if present).

    Args:
        base_path: Override for ``~/.dharma``.

    Returns:
        List of (OntologyObj, [Link, ...]) tuples.
    """
    base = base_path or _DEFAULT_BASE
    archive_file = base / "evolution" / "archive.jsonl"
    records = _read_jsonl(archive_file)

    results: AdapterResult = []
    for idx, rec in enumerate(records):
        try:
            raw_id = rec.get("id", "")
            obj_id = f"evo_{raw_id}" if raw_id else f"evo_{idx:06d}"

            props: dict[str, Any] = {
                "component": rec.get("component", rec.get("module", "")),
                "change_type": rec.get("change_type", "mutation"),
                "diff": rec.get("diff", rec.get("description", "")),
                "fitness": (
                    sum(rec["fitness"].values()) / max(len(rec["fitness"]), 1)
                    if isinstance(rec.get("fitness"), dict)
                    else float(rec.get("fitness", 0.0))
                ),
                "promotion_state": rec.get(
                    "promotion_state", rec.get("status", "candidate")
                ),
            }

            # Normalize change_type to valid enum values
            if props["change_type"] not in ("mutation", "crossover", "ablation"):
                props["change_type"] = "mutation"

            # Normalize promotion_state to valid enum values
            valid_promo = {
                "candidate", "probe_pass", "local_pass",
                "component_pass", "system_pass", "promoted",
            }
            if props["promotion_state"] not in valid_promo:
                props["promotion_state"] = "candidate"

            obj = _make_obj(obj_id, "EvolutionEntry", props)
            results.append((obj, []))
        except Exception as exc:
            logger.warning("adapt_evolution: skipping record %d: %s", idx, exc)
    return results


def adapt_corpus(base_path: Path | None = None) -> AdapterResult:
    """Read ~/.dharma/corpus/claims.jsonl -> CorpusClaim objects.

    Falls back to ``~/.dharma/corpus.jsonl`` (the DharmaCorpus default
    path) if the subdirectory variant does not exist.

    Each claim gets a deterministic ID ``claim_{claim.id}``.

    Args:
        base_path: Override for ``~/.dharma``.

    Returns:
        List of (OntologyObj, [Link, ...]) tuples.
    """
    base = base_path or _DEFAULT_BASE
    claims_file = base / "corpus" / "claims.jsonl"
    if not claims_file.exists():
        # Fallback to the DharmaCorpus default path
        claims_file = base / "corpus.jsonl"
    records = _read_jsonl(claims_file)

    results: AdapterResult = []
    for rec in records:
        try:
            claim_id = rec.get("id", "")
            if not claim_id:
                continue

            obj_id = f"claim_{claim_id}"

            # Serialize evidence links to text for the flat property
            evidence_links = rec.get("evidence_links", [])
            if isinstance(evidence_links, list) and evidence_links:
                evidence_text = json.dumps(evidence_links, default=str)
            else:
                evidence_text = ""

            status_raw = rec.get("status", "proposed")
            # Normalize to the reduced enum set
            valid_statuses = {"proposed", "accepted", "deprecated", "rejected"}
            if status_raw not in valid_statuses:
                # Map extended statuses
                status_map = {
                    "under_review": "proposed",
                    "parked": "rejected",
                }
                status_raw = status_map.get(status_raw, "proposed")

            props: dict[str, Any] = {
                "claim_text": rec.get("statement", ""),
                "status": status_raw,
                "evidence": evidence_text,
                "confidence": float(rec.get("confidence", 0.5)),
            }

            if not props["claim_text"]:
                continue

            obj = _make_obj(obj_id, "CorpusClaim", props)

            # Link to author agent if present
            links: list[Link] = []
            created_by = rec.get("created_by", "")
            if created_by and created_by != "system":
                links.append(
                    _make_link(
                        "authored_by",
                        obj_id,
                        "CorpusClaim",
                        f"agent_{created_by}",
                        "AgentIdentity",
                    )
                )
            results.append((obj, links))
        except Exception as exc:
            logger.warning("adapt_corpus: skipping record: %s", exc)
    return results


# ---------------------------------------------------------------------------
# Sync-all orchestrator
# ---------------------------------------------------------------------------

# All adapters with their names, for iteration.
_ADAPTERS: list[tuple[str, Any]] = [
    ("stigmergy", adapt_stigmergy),
    ("zeitgeist", adapt_zeitgeist),
    ("identity", adapt_identity),
    ("gates", adapt_gates),
    ("evolution", adapt_evolution),
    ("corpus", adapt_corpus),
]


def sync_all(
    registry: OntologyRegistry,
    base_path: Path | None = None,
) -> dict[str, int]:
    """Run all adapters and ingest results into the registry.

    For each adapter result, creates the object in the registry if it
    does not already exist (checked by ID). Links are created only when
    both source and target objects exist in the registry.

    Args:
        registry: The OntologyRegistry to populate.
        base_path: Override for ``~/.dharma``.

    Returns:
        Dict mapping adapter name to count of newly ingested objects.
        Example: ``{"stigmergy": 42, "zeitgeist": 7, ...}``
    """
    # Ensure hub types are registered
    register_hub_types(registry)

    counts: dict[str, int] = {}
    for name, adapter_fn in _ADAPTERS:
        try:
            items = adapter_fn(base_path=base_path)
        except Exception as exc:
            logger.error("Adapter %s failed: %s", name, exc)
            counts[name] = 0
            continue

        ingested = 0
        for obj, links in items:
            # Deduplication: skip if object already exists
            if registry.get_object(obj.id) is not None:
                continue

            # Validate against the registered type
            obj_type = registry.get_type(obj.type_name)
            if obj_type is None:
                logger.warning(
                    "sync_all: type %s not registered, skipping %s",
                    obj.type_name,
                    obj.id,
                )
                continue

            errors = validate_object(obj, obj_type)
            if errors:
                logger.warning(
                    "sync_all: validation errors for %s: %s", obj.id, errors
                )
                continue

            inserted, errors = registry.put_object(obj)
            if inserted is None or errors:
                logger.warning(
                    "sync_all: put_object failed for %s: %s", obj.id, errors
                )
                continue
            ingested += 1

            # Create links where both endpoints exist (via public API)
            for link in links:
                src = registry.get_object(link.source_id)
                tgt = registry.get_object(link.target_id)
                if src is not None and tgt is not None:
                    created_link, errors = registry.create_link(
                        link_name=link.link_name,
                        source_id=link.source_id,
                        target_id=link.target_id,
                        created_by="ontology_sync",
                        metadata=link.metadata,
                    )
                    if errors:
                        logger.debug(
                            "sync_all: link %s→%s skipped: %s",
                            link.source_id, link.target_id, errors,
                        )

        counts[name] = ingested
        if ingested:
            logger.info("sync_all: %s ingested %d objects", name, ingested)

    return counts
