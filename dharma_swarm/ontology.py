"""Typed Ontology Layer — The Foundation of dharma_swarm.

The Ontology is not a feature of the platform — it IS the platform.

Palantir built this pattern for supply chains and kill chains.
We take the engineering and reforge it for Jagat Kalyan.

Architecture:
  ObjectType   -> defines what CAN exist          (schema)
  OntologyObj  -> a specific INSTANCE              (data)
  LinkDef      -> how types relate                  (schema)
  Link         -> a specific relationship           (data)
  ActionDef    -> what you can DO                   (schema)
  ActionExec   -> a record of what was DONE         (audit)
  SecurityPolicy -> who can see/modify              (access control)
  OntologyRegistry -> central catalog of everything (the brain)

Everything flows through the ontology:
- LLMs receive typed object context, not raw text (OAG > RAG)
- Mutations go through typed Actions (auditable, reversible, gated)
- Links are explicit and bidirectional (not implicit foreign keys)
- Security is per-object-type and per-field
- The act of defining IS witnessing (v7 rule 5)

Inspired by Palantir Foundry, NATO JC3IEDM, Schema.org, GAIA Ledger.
Backward-compatible with existing Entity/ONTOLOGY API.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    from uuid import uuid4
    return uuid4().hex[:16]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENUMS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class PropertyType(str, Enum):
    """Property data types."""
    STRING = "string"
    TEXT = "text"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    ENUM = "enum"
    LIST = "list"
    DICT = "dict"
    PATH = "path"
    ID = "id"


class LinkCardinality(str, Enum):
    ONE_TO_ONE = "1:1"
    ONE_TO_MANY = "1:N"
    MANY_TO_ONE = "N:1"
    MANY_TO_MANY = "N:N"


class SecurityLevel(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    DHARMIC = "dharmic"


class ShaktiEnergy(str, Enum):
    """Which creative force primarily drives this object type."""
    MAHESHWARI = "maheshwari"
    MAHAKALI = "mahakali"
    MAHALAKSHMI = "mahalakshmi"
    MAHASARASWATI = "mahasaraswati"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# META-SCHEMA (What CAN exist)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class PropertyDef(BaseModel):
    """Schema for a single property on an ObjectType."""
    name: str
    property_type: PropertyType
    required: bool = False
    default: Any = None
    description: str = ""
    enum_values: list[str] = Field(default_factory=list)
    ref_type: str = ""
    searchable: bool = False
    immutable: bool = False


class LinkDef(BaseModel):
    """Schema for a relationship between two ObjectTypes.

    Links are registered in BOTH directions. Defining
    'Task --assigned_to--> Agent' auto-registers the inverse
    'Agent --tasks--> Task'.
    """
    name: str
    source_type: str
    target_type: str
    cardinality: LinkCardinality = LinkCardinality.MANY_TO_ONE
    required: bool = False
    inverse_name: str = ""
    description: str = ""


class ActionDef(BaseModel):
    """Schema for a typed, transactional mutation.

    Every mutation is an Action that commits atomically.
    No direct writes. No untyped side effects.
    Every action is auditable, reversible, and gated.
    """
    name: str
    object_type: str
    description: str = ""
    input_params: dict[str, str] = Field(default_factory=dict)
    modifies: list[str] = Field(default_factory=list)
    creates: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    telos_gates: list[str] = Field(default_factory=list)
    is_deterministic: bool = True


class SecurityPolicy(BaseModel):
    """Per-ObjectType access control."""
    read_roles: list[str] = Field(default_factory=lambda: ["*"])
    write_roles: list[str] = Field(default_factory=lambda: ["*"])
    create_roles: list[str] = Field(default_factory=lambda: ["*"])
    delete_roles: list[str] = Field(default_factory=lambda: ["system"])
    classification: SecurityLevel = SecurityLevel.INTERNAL
    field_restrictions: dict[str, list[str]] = Field(default_factory=dict)
    audit_all: bool = False
    telos_required: bool = False


class ObjectType(BaseModel):
    """Schema for a class of entity in the dharma_swarm ontology."""
    name: str
    description: str = ""
    properties: dict[str, PropertyDef] = Field(default_factory=dict)
    links: list[LinkDef] = Field(default_factory=list)
    actions: list[ActionDef] = Field(default_factory=list)
    security: SecurityPolicy = Field(default_factory=SecurityPolicy)

    # Dharmic extensions
    telos_alignment: float = Field(default=0.5, ge=0.0, le=1.0)
    shakti_energy: ShaktiEnergy = ShaktiEnergy.MAHASARASWATI
    witness_quality: float = Field(default=0.5, ge=0.0, le=1.0)

    # Schema metadata
    version: int = 1
    pydantic_model: str = ""
    storage_backend: str = "jsonl"
    icon: str = ""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# INSTANCES (What DOES exist)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class OntologyObj(BaseModel):
    """A specific instance of an ObjectType."""
    id: str = Field(default_factory=_new_id)
    type_name: str
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)
    created_by: str = "system"
    updated_at: datetime = Field(default_factory=_utc_now)
    version: int = 1


class Link(BaseModel):
    """A specific relationship between two OntologyObjs."""
    id: str = Field(default_factory=_new_id)
    link_name: str
    source_id: str
    source_type: str
    target_id: str
    target_type: str
    created_at: datetime = Field(default_factory=_utc_now)
    created_by: str = "system"
    metadata: dict[str, Any] = Field(default_factory=dict)
    witness_quality: float = Field(default=0.5, ge=0.0, le=1.0)


class ActionExecution(BaseModel):
    """Audit record of an action being executed."""
    id: str = Field(default_factory=_new_id)
    action_name: str
    object_id: str
    object_type: str
    input_params: dict[str, Any] = Field(default_factory=dict)
    result: str = "pending"
    gate_results: dict[str, str] = Field(default_factory=dict)
    executed_by: str = "system"
    executed_at: datetime = Field(default_factory=_utc_now)
    duration_ms: float = 0.0
    error: str = ""
    lineage_inputs: list[str] = Field(default_factory=list)
    lineage_outputs: list[str] = Field(default_factory=list)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# VALIDATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def validate_object(obj: OntologyObj, obj_type: ObjectType) -> list[str]:
    """Validate an OntologyObj against its ObjectType schema."""
    errors: list[str] = []
    if obj.type_name != obj_type.name:
        errors.append(f"type mismatch: '{obj.type_name}' vs '{obj_type.name}'")
        return errors

    for prop_name, prop_def in obj_type.properties.items():
        value = obj.properties.get(prop_name)
        if prop_def.required and value is None:
            errors.append(f"missing required property: {prop_name}")
            continue
        if value is None:
            continue
        if prop_def.property_type == PropertyType.ENUM and prop_def.enum_values:
            if str(value) not in prop_def.enum_values:
                errors.append(
                    f"invalid enum '{prop_name}': "
                    f"'{value}' not in {prop_def.enum_values}"
                )
        if prop_def.property_type == PropertyType.FLOAT:
            if not isinstance(value, (int, float)):
                errors.append(f"'{prop_name}' must be numeric")
        if prop_def.property_type == PropertyType.INTEGER:
            if not isinstance(value, int):
                errors.append(f"'{prop_name}' must be integer")
        if prop_def.property_type == PropertyType.BOOLEAN:
            if not isinstance(value, bool):
                errors.append(f"'{prop_name}' must be boolean")
    return errors


def validate_link(link: Link, link_def: LinkDef) -> list[str]:
    """Validate a Link instance against its LinkDef schema."""
    errors: list[str] = []
    if link.link_name != link_def.name:
        errors.append(f"link name mismatch: '{link.link_name}' vs '{link_def.name}'")
    if link.source_type != link_def.source_type:
        errors.append(f"source type mismatch: '{link.source_type}' vs '{link_def.source_type}'")
    if link.target_type != link_def.target_type:
        errors.append(f"target type mismatch: '{link.target_type}' vs '{link_def.target_type}'")
    return errors


def check_security(
    obj_type: ObjectType,
    agent_role: str,
    operation: str,
) -> tuple[bool, str]:
    """Check if an agent role has permission for an operation."""
    policy = obj_type.security
    role_map = {
        "read": policy.read_roles,
        "write": policy.write_roles,
        "create": policy.create_roles,
        "delete": policy.delete_roles,
    }
    allowed_roles = role_map.get(operation, [])
    if "*" in allowed_roles or agent_role in allowed_roles:
        return True, ""
    return False, f"role '{agent_role}' denied {operation} on {obj_type.name}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# THE REGISTRY (The Brain)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class OntologyRegistry:
    """Central registry of all object types, links, actions, and security.

    This is the Palantir Ontology for dharma_swarm.

    Usage::

        registry = OntologyRegistry.create_dharma_registry()
        registry.get_type("Experiment")
        registry.get_links_for("ResearchThread")
        registry.schema_for_llm(["Experiment", "KnowledgeArtifact"])
    """

    def __init__(self) -> None:
        self._types: dict[str, ObjectType] = {}
        self._links: dict[str, LinkDef] = {}
        self._actions: dict[str, ActionDef] = {}
        self._objects: dict[str, OntologyObj] = {}
        self._link_instances: dict[str, Link] = {}
        self._action_log: list[ActionExecution] = []

    # ── Registration ─────────────────────────────────────────────────

    def register_type(self, obj_type: ObjectType) -> None:
        """Register an ObjectType in the ontology."""
        self._types[obj_type.name] = obj_type
        for link_def in obj_type.links:
            self.register_link(link_def)
        for action_def in obj_type.actions:
            self.register_action(action_def)

    def register_link(self, link_def: LinkDef) -> None:
        """Register a LinkDef. Auto-registers inverse if specified."""
        key = f"{link_def.source_type}.{link_def.name}"
        self._links[key] = link_def
        if link_def.inverse_name:
            inverse_cardinality = {
                LinkCardinality.ONE_TO_ONE: LinkCardinality.ONE_TO_ONE,
                LinkCardinality.ONE_TO_MANY: LinkCardinality.MANY_TO_ONE,
                LinkCardinality.MANY_TO_ONE: LinkCardinality.ONE_TO_MANY,
                LinkCardinality.MANY_TO_MANY: LinkCardinality.MANY_TO_MANY,
            }[link_def.cardinality]
            inv_key = f"{link_def.target_type}.{link_def.inverse_name}"
            if inv_key not in self._links:
                self._links[inv_key] = LinkDef(
                    name=link_def.inverse_name,
                    source_type=link_def.target_type,
                    target_type=link_def.source_type,
                    cardinality=inverse_cardinality,
                    description=f"Inverse of {link_def.name}",
                )

    def register_action(self, action_def: ActionDef) -> None:
        """Register an ActionDef."""
        key = f"{action_def.object_type}.{action_def.name}"
        self._actions[key] = action_def

    # ── Querying ─────────────────────────────────────────────────────

    def get_type(self, name: str) -> ObjectType | None:
        return self._types.get(name)

    def get_types(self) -> list[ObjectType]:
        return list(self._types.values())

    def type_names(self) -> list[str]:
        return sorted(self._types.keys())

    def get_links_for(self, type_name: str) -> list[LinkDef]:
        """Get all links where type_name is the source."""
        prefix = f"{type_name}."
        return [link for key, link in self._links.items() if key.startswith(prefix)]

    def get_all_links_involving(self, type_name: str) -> list[LinkDef]:
        """Get all links where type_name is source or target."""
        return [
            link for link in self._links.values()
            if link.source_type == type_name or link.target_type == type_name
        ]

    def get_actions_for(self, type_name: str) -> list[ActionDef]:
        prefix = f"{type_name}."
        return [a for key, a in self._actions.items() if key.startswith(prefix)]

    def get_link_def(self, source_type: str, link_name: str) -> LinkDef | None:
        return self._links.get(f"{source_type}.{link_name}")

    def get_action_def(self, object_type: str, action_name: str) -> ActionDef | None:
        return self._actions.get(f"{object_type}.{action_name}")

    # ── Object Operations ────────────────────────────────────────────

    def create_object(
        self,
        type_name: str,
        properties: dict[str, Any],
        created_by: str = "system",
    ) -> tuple[OntologyObj | None, list[str]]:
        """Create a new OntologyObj with validation."""
        obj_type = self._types.get(type_name)
        if obj_type is None:
            return None, [f"unknown type: {type_name}"]

        obj = OntologyObj(
            type_name=type_name,
            properties=properties,
            created_by=created_by,
        )
        errors = validate_object(obj, obj_type)
        if errors:
            return None, errors

        self._objects[obj.id] = obj
        return obj, []

    def get_object(self, obj_id: str) -> OntologyObj | None:
        return self._objects.get(obj_id)

    def get_objects_by_type(self, type_name: str) -> list[OntologyObj]:
        return [o for o in self._objects.values() if o.type_name == type_name]

    def update_object(
        self,
        obj_id: str,
        updates: dict[str, Any],
        updated_by: str = "system",  # noqa: ARG002
    ) -> tuple[OntologyObj | None, list[str]]:
        """Update properties with validation and immutability checks."""
        obj = self._objects.get(obj_id)
        if obj is None:
            return None, [f"object not found: {obj_id}"]

        obj_type = self._types.get(obj.type_name)
        if obj_type is None:
            return None, [f"type not registered: {obj.type_name}"]

        for key in updates:
            prop_def = obj_type.properties.get(key)
            if prop_def and prop_def.immutable and key in obj.properties:
                return None, [f"immutable property: {key}"]

        new_props = {**obj.properties, **updates}
        test_obj = obj.model_copy(update={"properties": new_props})
        errors = validate_object(test_obj, obj_type)
        if errors:
            return None, errors

        obj.properties = new_props
        obj.updated_at = _utc_now()
        obj.version += 1
        return obj, []

    # ── Link Operations ──────────────────────────────────────────────

    def create_link(
        self,
        link_name: str,
        source_id: str,
        target_id: str,
        created_by: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[Link | None, list[str]]:
        """Create a typed link between two objects."""
        source = self._objects.get(source_id)
        target = self._objects.get(target_id)
        if source is None:
            return None, [f"source not found: {source_id}"]
        if target is None:
            return None, [f"target not found: {target_id}"]

        link_def = self._links.get(f"{source.type_name}.{link_name}")
        if link_def is None:
            return None, [f"no link '{link_name}' for type '{source.type_name}'"]
        if link_def.target_type != target.type_name:
            return None, [
                f"link '{link_name}' expects target '{link_def.target_type}', "
                f"got '{target.type_name}'"
            ]

        # Cardinality enforcement
        if link_def.cardinality in (LinkCardinality.ONE_TO_ONE, LinkCardinality.MANY_TO_ONE):
            existing = [
                lnk for lnk in self._link_instances.values()
                if lnk.link_name == link_name and lnk.source_id == source_id
            ]
            if existing:
                return None, [f"cardinality: {link_name} already exists for {source_id}"]

        link = Link(
            link_name=link_name,
            source_id=source_id,
            source_type=source.type_name,
            target_id=target_id,
            target_type=target.type_name,
            created_by=created_by,
            metadata=metadata or {},
        )
        errors = validate_link(link, link_def)
        if errors:
            return None, errors

        self._link_instances[link.id] = link
        return link, []

    def get_links(
        self,
        source_id: str | None = None,
        target_id: str | None = None,
        link_name: str | None = None,
    ) -> list[Link]:
        """Query links by source, target, or name."""
        results: list[Link] = []
        for lnk in self._link_instances.values():
            if source_id and lnk.source_id != source_id:
                continue
            if target_id and lnk.target_id != target_id:
                continue
            if link_name and lnk.link_name != link_name:
                continue
            results.append(lnk)
        return results

    def get_linked_objects(
        self,
        obj_id: str,
        link_name: str,
    ) -> list[OntologyObj]:
        """Get all objects linked FROM obj_id via link_name."""
        links = self.get_links(source_id=obj_id, link_name=link_name)
        return [
            self._objects[lnk.target_id]
            for lnk in links
            if lnk.target_id in self._objects
        ]

    # ── Action Operations ────────────────────────────────────────────

    def execute_action(
        self,
        object_type: str,
        action_name: str,
        object_id: str,
        params: dict[str, Any],
        executed_by: str = "system",
        gate_check: Callable[[str, dict[str, Any]], dict[str, str]] | None = None,
    ) -> ActionExecution:
        """Execute a typed action with optional telos gate checking."""
        action_def = self.get_action_def(object_type, action_name)
        execution = ActionExecution(
            action_name=action_name,
            object_id=object_id,
            object_type=object_type,
            input_params=params,
            executed_by=executed_by,
        )

        if action_def is None:
            execution.result = "failed"
            execution.error = f"no action '{action_name}' for type '{object_type}'"
            self._action_log.append(execution)
            return execution

        # Telos gate check
        if gate_check and action_def.telos_gates:
            gate_results = gate_check(action_name, params)
            execution.gate_results = gate_results
            if any(v == "BLOCK" for v in gate_results.values()):
                execution.result = "blocked"
                execution.error = "telos gate blocked"
                self._action_log.append(execution)
                return execution

        # Security check for telos-required types
        obj_type = self._types.get(object_type)
        if obj_type and obj_type.security.telos_required and not gate_check:
            execution.result = "blocked"
            execution.error = "telos gate required but no gate_check provided"
            self._action_log.append(execution)
            return execution

        execution.result = "success"
        self._action_log.append(execution)
        return execution

    def action_history(
        self,
        object_id: str | None = None,
        action_name: str | None = None,
        limit: int = 50,
    ) -> list[ActionExecution]:
        """Query the action audit trail."""
        results: list[ActionExecution] = []
        for entry in reversed(self._action_log):
            if object_id and entry.object_id != object_id:
                continue
            if action_name and entry.action_name != action_name:
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return results

    # ── OAG: Ontology-Augmented Generation ───────────────────────────

    def describe_type(self, name: str) -> str:
        """Human-readable description of an ObjectType for LLM context."""
        obj_type = self._types.get(name)
        if obj_type is None:
            return f"Unknown type: {name}"

        lines = [
            f"## {obj_type.name}",
            f"{obj_type.description}",
            f"Telos: {obj_type.telos_alignment:.1f} | "
            f"Shakti: {obj_type.shakti_energy.value} | "
            f"Security: {obj_type.security.classification.value}",
            "",
            "### Properties",
        ]
        for pname, pdef in obj_type.properties.items():
            req = " *" if pdef.required else ""
            enum_info = f" [{', '.join(pdef.enum_values)}]" if pdef.enum_values else ""
            lines.append(f"- **{pname}**: {pdef.property_type.value}{req}{enum_info}")
            if pdef.description:
                lines.append(f"  {pdef.description}")

        type_links = self.get_links_for(name)
        if type_links:
            lines.append("")
            lines.append("### Links")
            for ld in type_links:
                lines.append(f"- **{ld.name}** -> {ld.target_type} ({ld.cardinality.value})")

        type_actions = self.get_actions_for(name)
        if type_actions:
            lines.append("")
            lines.append("### Actions")
            for ad in type_actions:
                det = "deterministic" if ad.is_deterministic else "LLM"
                gates = f" [gates: {', '.join(ad.telos_gates)}]" if ad.telos_gates else ""
                lines.append(f"- **{ad.name}** ({det}){gates}")
                if ad.description:
                    lines.append(f"  {ad.description}")

        return "\n".join(lines)

    def schema_for_llm(self, type_names: list[str] | None = None) -> str:
        """Generate ontology context for LLM prompt injection (OAG)."""
        names = type_names or sorted(self._types.keys())
        sections = ["# Ontology Context\n"]
        for name in names:
            if name in self._types:
                sections.append(self.describe_type(name))
                sections.append("")
        return "\n".join(sections)

    def object_context_for_llm(
        self,
        obj_id: str,
        include_links: bool = True,
        max_linked: int = 5,
    ) -> str:
        """Generate context about a specific object for LLM injection."""
        obj = self._objects.get(obj_id)
        if obj is None:
            return f"Object not found: {obj_id}"

        lines = [
            f"## {obj.type_name}: "
            f"{obj.properties.get('name', obj.properties.get('title', obj.id))}",
            f"ID: {obj.id} | Created: {obj.created_at.isoformat()[:19]}",
            "",
        ]
        for key, value in obj.properties.items():
            if value is not None:
                display = str(value)
                if len(display) > 200:
                    display = display[:197] + "..."
                lines.append(f"- **{key}**: {display}")

        if include_links:
            all_links = self.get_links(source_id=obj_id)
            if all_links:
                lines.append("")
                lines.append("### Linked")
                for lnk in all_links[:max_linked]:
                    target = self._objects.get(lnk.target_id)
                    tname = "?"
                    if target:
                        tname = str(target.properties.get(
                            "name", target.properties.get("title", target.id)
                        ))
                    lines.append(f"- {lnk.link_name} -> {lnk.target_type}: {tname}")

        return "\n".join(lines)

    # ── Introspection ────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        type_counts: dict[str, int] = {}
        for obj in self._objects.values():
            type_counts[obj.type_name] = type_counts.get(obj.type_name, 0) + 1

        return {
            "registered_types": len(self._types),
            "registered_links": len(self._links),
            "registered_actions": len(self._actions),
            "total_objects": len(self._objects),
            "total_links": len(self._link_instances),
            "action_log_entries": len(self._action_log),
            "objects_by_type": type_counts,
            "type_names": sorted(self._types.keys()),
        }

    def graph_summary(self) -> str:
        """ASCII visualization of the ontology graph."""
        lines = ["=== Ontology Graph ===", ""]
        for name in sorted(self._types):
            count = sum(1 for o in self._objects.values() if o.type_name == name)
            lines.append(f"[{name}] ({count} instances)")
            for ld in self.get_links_for(name):
                lines.append(f"  --{ld.name}--> [{ld.target_type}] ({ld.cardinality.value})")
            lines.append("")
        return "\n".join(lines)

    # ── Persistence ──────────────────────────────────────────────────

    def save(self, path: Path | None = None) -> Path:
        """Save ontology state to JSON."""
        save_path = path or (Path.home() / ".dharma" / "ontology.json")
        save_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "types": {n: t.model_dump(mode="json") for n, t in self._types.items()},
            "links": {n: ld.model_dump(mode="json") for n, ld in self._links.items()},
            "actions": {n: a.model_dump(mode="json") for n, a in self._actions.items()},
            "objects": {i: o.model_dump(mode="json") for i, o in self._objects.items()},
            "link_instances": {
                i: lnk.model_dump(mode="json") for i, lnk in self._link_instances.items()
            },
            "action_log": [e.model_dump(mode="json") for e in self._action_log[-1000:]],
            "saved_at": _utc_now().isoformat(),
        }
        save_path.write_text(
            json.dumps(data, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        return save_path

    def load(self, path: Path | None = None) -> int:
        """Load ontology state from JSON. Returns count of loaded items."""
        load_path = path or (Path.home() / ".dharma" / "ontology.json")
        if not load_path.exists():
            return 0

        try:
            data = json.loads(load_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load ontology: %s", exc)
            return 0

        count = 0
        for name, tdata in data.get("types", {}).items():
            self._types[name] = ObjectType.model_validate(tdata)
            count += 1
        for key, ldata in data.get("links", {}).items():
            self._links[key] = LinkDef.model_validate(ldata)
        for key, adata in data.get("actions", {}).items():
            self._actions[key] = ActionDef.model_validate(adata)
        for oid, odata in data.get("objects", {}).items():
            self._objects[oid] = OntologyObj.model_validate(odata)
            count += 1
        for lid, ldata in data.get("link_instances", {}).items():
            self._link_instances[lid] = Link.model_validate(ldata)
        for edata in data.get("action_log", []):
            self._action_log.append(ActionExecution.model_validate(edata))
        return count

    # ── Factory ──────────────────────────────────────────────────────

    @classmethod
    def create_dharma_registry(cls) -> "OntologyRegistry":
        """Create the canonical dharma_swarm ontology.

        Registers 8 core ObjectTypes, 12 LinkDefs (24 with inverses),
        and 15 ActionDefs that form the semantic backbone.
        """
        registry = cls()
        for obj_type in _DOMAIN_TYPES:
            registry.register_type(obj_type)
        for link_def in _DOMAIN_LINKS:
            registry.register_link(link_def)
        for link_def in _METABOLIC_LINKS:
            registry.register_link(link_def)
        return registry


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DOMAIN OBJECT TYPES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_RESEARCH_THREAD = ObjectType(
    name="ResearchThread",
    description="A research direction with experiments and findings",
    properties={
        "name": PropertyDef(name="name", property_type=PropertyType.STRING, required=True,
                           description="Thread name"),
        "domain": PropertyDef(name="domain", property_type=PropertyType.ENUM,
                             enum_values=["mechanistic", "phenomenological", "architectural",
                                         "alignment", "scaling", "bridge"]),
        "status": PropertyDef(name="status", property_type=PropertyType.ENUM,
                             enum_values=["active", "paused", "completed", "abandoned"]),
        "hypothesis": PropertyDef(name="hypothesis", property_type=PropertyType.TEXT,
                                 searchable=True),
        "priority": PropertyDef(name="priority", property_type=PropertyType.FLOAT,
                               description="0-1 weight for thread rotation"),
    },
    actions=[
        ActionDef(name="Activate", object_type="ResearchThread",
                 description="Set as active focus", modifies=["status", "priority"],
                 telos_gates=["MAHESHWARI"]),
        ActionDef(name="Pause", object_type="ResearchThread",
                 description="Pause thread", modifies=["status"]),
    ],
    telos_alignment=0.9,
    shakti_energy=ShaktiEnergy.MAHESHWARI,
    pydantic_model="dharma_swarm.thread_manager.ThreadState",
    icon="R",
)

_EXPERIMENT = ObjectType(
    name="Experiment",
    description="A specific test with config, execution, and results",
    properties={
        "name": PropertyDef(name="name", property_type=PropertyType.STRING, required=True),
        "config": PropertyDef(name="config", property_type=PropertyType.DICT,
                             description="Full experiment configuration"),
        "status": PropertyDef(name="status", property_type=PropertyType.ENUM,
                             enum_values=["designed", "queued", "running", "completed",
                                         "failed", "abandoned"]),
        "model": PropertyDef(name="model", property_type=PropertyType.STRING,
                            description="Model under test"),
        "prompt_set": PropertyDef(name="prompt_set", property_type=PropertyType.STRING),
        "results": PropertyDef(name="results", property_type=PropertyType.DICT),
        "fitness": PropertyDef(name="fitness", property_type=PropertyType.FLOAT),
        "r_v_value": PropertyDef(name="r_v_value", property_type=PropertyType.FLOAT,
                                description="Measured R_V contraction ratio"),
    },
    actions=[
        ActionDef(name="Design", object_type="Experiment",
                 description="Lock parameters, define controls",
                 modifies=["config", "status"],
                 telos_gates=["MAHASARASWATI"]),
        ActionDef(name="Run", object_type="Experiment",
                 description="Execute the experiment",
                 modifies=["status", "results"], is_deterministic=False,
                 telos_gates=["AHIMSA", "SATYA"]),
        ActionDef(name="Archive", object_type="Experiment",
                 description="Store results with lineage",
                 modifies=["status"], creates=["KnowledgeArtifact"]),
    ],
    telos_alignment=0.95,
    shakti_energy=ShaktiEnergy.MAHASARASWATI,
    icon="E",
)

_PAPER = ObjectType(
    name="Paper",
    description="An academic paper with claims, evidence, and submission status",
    properties={
        "title": PropertyDef(name="title", property_type=PropertyType.STRING, required=True),
        "venue": PropertyDef(name="venue", property_type=PropertyType.STRING),
        "deadline": PropertyDef(name="deadline", property_type=PropertyType.DATETIME),
        "status": PropertyDef(name="status", property_type=PropertyType.ENUM,
                             enum_values=["drafting", "review", "submitted",
                                         "accepted", "rejected"]),
        "latex_path": PropertyDef(name="latex_path", property_type=PropertyType.PATH),
        "claim_count": PropertyDef(name="claim_count", property_type=PropertyType.INTEGER),
        "verified_claims": PropertyDef(name="verified_claims", property_type=PropertyType.INTEGER),
    },
    actions=[
        ActionDef(name="Audit", object_type="Paper",
                 description="Verify all claims against source data",
                 telos_gates=["SATYA"]),
        ActionDef(name="Submit", object_type="Paper",
                 description="Submit to venue", modifies=["status"],
                 requires_approval=True, telos_gates=["SATYA", "MAHASARASWATI"]),
    ],
    security=SecurityPolicy(write_roles=["researcher", "system"], audit_all=True),
    telos_alignment=0.85,
    shakti_energy=ShaktiEnergy.MAHASARASWATI,
    icon="P",
)

_AGENT_IDENTITY = ObjectType(
    name="AgentIdentity",
    description="A swarm agent with role, capabilities, and permissions",
    properties={
        "name": PropertyDef(name="name", property_type=PropertyType.STRING,
                           required=True, immutable=True),
        "role": PropertyDef(name="role", property_type=PropertyType.ENUM,
                           enum_values=["coder", "reviewer", "researcher", "tester",
                                       "orchestrator", "general", "cartographer",
                                       "archeologist", "surgeon", "architect", "validator"]),
        "provider": PropertyDef(name="provider", property_type=PropertyType.STRING),
        "model": PropertyDef(name="model", property_type=PropertyType.STRING),
        "capabilities": PropertyDef(name="capabilities", property_type=PropertyType.LIST),
        "swabhaav_capacity": PropertyDef(name="swabhaav_capacity",
                                        property_type=PropertyType.FLOAT,
                                        description="Witness stance capacity 0-1"),
        "tasks_completed": PropertyDef(name="tasks_completed",
                                      property_type=PropertyType.INTEGER),
        "fitness_average": PropertyDef(name="fitness_average",
                                      property_type=PropertyType.FLOAT),
    },
    actions=[
        ActionDef(name="Spawn", object_type="AgentIdentity",
                 description="Create and start a new agent",
                 creates=["AgentIdentity"], telos_gates=["AHIMSA"]),
        ActionDef(name="Retire", object_type="AgentIdentity",
                 description="Gracefully stop an agent"),
    ],
    security=SecurityPolicy(
        create_roles=["orchestrator", "system"],
        delete_roles=["system"],
    ),
    telos_alignment=0.9,
    shakti_energy=ShaktiEnergy.MAHAKALI,
    pydantic_model="dharma_swarm.models.AgentConfig",
    icon="A",
)

_KNOWLEDGE_ARTIFACT = ObjectType(
    name="KnowledgeArtifact",
    description="A piece of knowledge: file, note, finding, measurement, code",
    properties={
        "title": PropertyDef(name="title", property_type=PropertyType.STRING,
                            required=True, searchable=True),
        "artifact_type": PropertyDef(name="artifact_type", property_type=PropertyType.ENUM,
                                    enum_values=["file", "note", "finding", "measurement",
                                                "citation", "prompt", "result",
                                                "visualization", "code", "model_output"]),
        "domain": PropertyDef(name="domain", property_type=PropertyType.ENUM,
                             enum_values=["dharma_swarm", "mech_interp", "psmv",
                                         "kailash", "agni", "trishula", "shared"]),
        "content": PropertyDef(name="content", property_type=PropertyType.TEXT,
                              searchable=True),
        "file_path": PropertyDef(name="file_path", property_type=PropertyType.PATH),
        "provenance": PropertyDef(name="provenance", property_type=PropertyType.STRING),
        "confidence": PropertyDef(name="confidence", property_type=PropertyType.FLOAT),
        "verified": PropertyDef(name="verified", property_type=PropertyType.BOOLEAN),
    },
    actions=[
        ActionDef(name="Verify", object_type="KnowledgeArtifact",
                 description="Mark as verified against source",
                 modifies=["verified", "confidence"], telos_gates=["SATYA"]),
        ActionDef(name="Index", object_type="KnowledgeArtifact",
                 description="Add to ecosystem FTS5 index"),
    ],
    telos_alignment=0.8,
    shakti_energy=ShaktiEnergy.MAHALAKSHMI,
    icon="K",
)

_TYPED_TASK = ObjectType(
    name="TypedTask",
    description="A task with ontology-aware inputs, outputs, and lineage",
    properties={
        "title": PropertyDef(name="title", property_type=PropertyType.STRING, required=True),
        "description": PropertyDef(name="description", property_type=PropertyType.TEXT),
        "status": PropertyDef(name="status", property_type=PropertyType.ENUM,
                             enum_values=["pending", "assigned", "running",
                                         "completed", "failed", "cancelled"]),
        "priority": PropertyDef(name="priority", property_type=PropertyType.ENUM,
                               enum_values=["low", "normal", "high", "urgent"]),
        "task_type": PropertyDef(name="task_type", property_type=PropertyType.ENUM,
                                enum_values=["experiment", "analysis", "writing", "review",
                                            "build", "deploy", "triage", "evolve", "witness"]),
        "deterministic": PropertyDef(name="deterministic", property_type=PropertyType.BOOLEAN,
                                    description="True if task can run without LLM"),
    },
    actions=[
        ActionDef(name="Assign", object_type="TypedTask",
                 description="Assign to agent", modifies=["status"]),
        ActionDef(name="Complete", object_type="TypedTask",
                 description="Mark completed with results",
                 modifies=["status"], creates=["KnowledgeArtifact"]),
        ActionDef(name="Fail", object_type="TypedTask",
                 description="Mark as failed", modifies=["status"]),
    ],
    telos_alignment=0.7,
    shakti_energy=ShaktiEnergy.MAHAKALI,
    pydantic_model="dharma_swarm.models.Task",
    icon="T",
)

_EVOLUTION_ENTRY = ObjectType(
    name="EvolutionEntry",
    description="A record in the Darwin Engine evolution archive",
    properties={
        "component": PropertyDef(name="component", property_type=PropertyType.STRING,
                                required=True, description="Module modified"),
        "change_type": PropertyDef(name="change_type", property_type=PropertyType.ENUM,
                                  enum_values=["mutation", "crossover", "ablation"]),
        "diff": PropertyDef(name="diff", property_type=PropertyType.TEXT),
        "fitness": PropertyDef(name="fitness", property_type=PropertyType.FLOAT),
        "promotion_state": PropertyDef(name="promotion_state", property_type=PropertyType.ENUM,
                                      enum_values=["candidate", "probe_pass", "local_pass",
                                                  "component_pass", "system_pass", "promoted"]),
    },
    actions=[
        ActionDef(name="Propose", object_type="EvolutionEntry",
                 description="Submit evolution proposal",
                 telos_gates=["AHIMSA", "SATYA", "REVERSIBILITY"],
                 is_deterministic=False),
        ActionDef(name="Promote", object_type="EvolutionEntry",
                 description="Advance through evidence tiers",
                 modifies=["promotion_state"]),
        ActionDef(name="Revert", object_type="EvolutionEntry",
                 description="Roll back failed change",
                 modifies=["promotion_state"]),
    ],
    security=SecurityPolicy(telos_required=True, audit_all=True),
    telos_alignment=0.95,
    shakti_energy=ShaktiEnergy.MAHAKALI,
    pydantic_model="dharma_swarm.archive.ArchiveEntry",
    icon="D",
)

_WITNESS_LOG = ObjectType(
    name="WitnessLog",
    description="The act of checking IS witnessing. Audit trail as dharmic practice.",
    properties={
        "observation": PropertyDef(name="observation", property_type=PropertyType.TEXT,
                                  required=True, searchable=True),
        "observer": PropertyDef(name="observer", property_type=PropertyType.STRING,
                               required=True),
        "context": PropertyDef(name="context", property_type=PropertyType.STRING,
                              description="What was being observed"),
        "witness_quality": PropertyDef(name="witness_quality", property_type=PropertyType.FLOAT,
                                     description="0-1 depth of observation"),
        "contraction_level": PropertyDef(name="contraction_level",
                                        property_type=PropertyType.STRING,
                                        description="L1-L5 contraction assessment"),
    },
    actions=[
        ActionDef(name="Record", object_type="WitnessLog",
                 description="Record a witnessing observation"),
    ],
    security=SecurityPolicy(
        write_roles=["*"],
        delete_roles=[],
        audit_all=True,
    ),
    telos_alignment=1.0,
    shakti_energy=ShaktiEnergy.MAHESHWARI,
    icon="W",
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DOMAIN LINKS — Relationships between types
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_DOMAIN_LINKS: list[LinkDef] = [
    LinkDef(name="has_experiment", source_type="ResearchThread",
           target_type="Experiment", cardinality=LinkCardinality.ONE_TO_MANY,
           inverse_name="belongs_to_thread"),
    LinkDef(name="produces", source_type="Experiment",
           target_type="KnowledgeArtifact", cardinality=LinkCardinality.ONE_TO_MANY,
           inverse_name="produced_by_experiment"),
    LinkDef(name="cites", source_type="Paper",
           target_type="KnowledgeArtifact", cardinality=LinkCardinality.MANY_TO_MANY,
           inverse_name="cited_by_paper"),
    LinkDef(name="assigned_to", source_type="TypedTask",
           target_type="AgentIdentity", cardinality=LinkCardinality.MANY_TO_ONE,
           inverse_name="assigned_tasks"),
    LinkDef(name="consumes", source_type="TypedTask",
           target_type="KnowledgeArtifact", cardinality=LinkCardinality.MANY_TO_MANY,
           inverse_name="consumed_by_task"),
    LinkDef(name="task_produces", source_type="TypedTask",
           target_type="KnowledgeArtifact", cardinality=LinkCardinality.ONE_TO_MANY,
           inverse_name="produced_by_task",
           description="Task outputs = lineage"),
    LinkDef(name="depends_on", source_type="TypedTask",
           target_type="TypedTask", cardinality=LinkCardinality.MANY_TO_MANY,
           inverse_name="blocks"),
    LinkDef(name="contributes_to", source_type="ResearchThread",
           target_type="Paper", cardinality=LinkCardinality.MANY_TO_MANY,
           inverse_name="draws_from_thread"),
    LinkDef(name="authored", source_type="AgentIdentity",
           target_type="KnowledgeArtifact", cardinality=LinkCardinality.ONE_TO_MANY,
           inverse_name="authored_by"),
    LinkDef(name="proposed_evolution", source_type="AgentIdentity",
           target_type="EvolutionEntry", cardinality=LinkCardinality.ONE_TO_MANY,
           inverse_name="proposed_by"),
    LinkDef(name="witnessed", source_type="AgentIdentity",
           target_type="WitnessLog", cardinality=LinkCardinality.ONE_TO_MANY,
           inverse_name="witnessed_by"),
    LinkDef(name="informs_experiment", source_type="KnowledgeArtifact",
           target_type="Experiment", cardinality=LinkCardinality.MANY_TO_MANY,
           inverse_name="informed_by"),
]

_ACTION_PROPOSAL = ObjectType(
    name="ActionProposal",
    description="A proposed action before gate evaluation — the metabolic loop entry point",
    properties={
        "task_id": PropertyDef(name="task_id", property_type=PropertyType.STRING,
                               required=True, immutable=True,
                               description="Original task ID from orchestrator"),
        "agent_id": PropertyDef(name="agent_id", property_type=PropertyType.STRING,
                                required=True, description="Target agent for execution"),
        "action_type": PropertyDef(name="action_type", property_type=PropertyType.ENUM,
                                   enum_values=["dispatch", "fan_out", "pipeline",
                                               "evolution", "manual"],
                                   description="How this action entered the system"),
        "title": PropertyDef(name="title", property_type=PropertyType.STRING,
                             required=True, searchable=True),
        "description": PropertyDef(name="description", property_type=PropertyType.TEXT),
        "status": PropertyDef(name="status", property_type=PropertyType.ENUM,
                              enum_values=["proposed", "gated", "approved", "rejected",
                                          "executing", "completed", "failed"]),
        "priority": PropertyDef(name="priority", property_type=PropertyType.ENUM,
                                enum_values=["low", "normal", "high", "urgent"]),
    },
    actions=[
        ActionDef(name="Propose", object_type="ActionProposal",
                  description="Create a new action proposal",
                  telos_gates=["AHIMSA", "SATYA"]),
        ActionDef(name="Approve", object_type="ActionProposal",
                  description="Approve after gate check",
                  modifies=["status"]),
        ActionDef(name="Reject", object_type="ActionProposal",
                  description="Reject after gate check",
                  modifies=["status"]),
    ],
    security=SecurityPolicy(audit_all=True),
    telos_alignment=0.9,
    shakti_energy=ShaktiEnergy.MAHAKALI,
    icon="→",
)

_GATE_DECISION_TYPE = ObjectType(
    name="GateDecisionRecord",
    description="Result of telos gate evaluation on an ActionProposal",
    properties={
        "proposal_id": PropertyDef(name="proposal_id", property_type=PropertyType.STRING,
                                    required=True, immutable=True,
                                    description="ActionProposal this decision applies to"),
        "decision": PropertyDef(name="decision", property_type=PropertyType.ENUM,
                                enum_values=["allow", "block", "review"],
                                required=True),
        "reason": PropertyDef(name="reason", property_type=PropertyType.TEXT),
        "gate_results": PropertyDef(name="gate_results", property_type=PropertyType.DICT,
                                    description="Per-gate PASS/FAIL/WARN results"),
        "witness_reroutes": PropertyDef(name="witness_reroutes",
                                         property_type=PropertyType.INTEGER,
                                         description="Number of reflective reroute attempts"),
    },
    actions=[
        ActionDef(name="Record", object_type="GateDecisionRecord",
                  description="Record a gate evaluation result"),
    ],
    security=SecurityPolicy(
        write_roles=["orchestrator", "system"],
        delete_roles=[],
        audit_all=True,
    ),
    telos_alignment=1.0,
    shakti_energy=ShaktiEnergy.MAHESHWARI,
    icon="⊘",
)

_OUTCOME = ObjectType(
    name="Outcome",
    description="What happened after an ActionProposal was executed",
    properties={
        "proposal_id": PropertyDef(name="proposal_id", property_type=PropertyType.STRING,
                                    required=True, immutable=True),
        "task_id": PropertyDef(name="task_id", property_type=PropertyType.STRING,
                               required=True, immutable=True),
        "agent_id": PropertyDef(name="agent_id", property_type=PropertyType.STRING,
                                required=True),
        "success": PropertyDef(name="success", property_type=PropertyType.BOOLEAN,
                               required=True),
        "result_summary": PropertyDef(name="result_summary", property_type=PropertyType.TEXT,
                                      searchable=True),
        "error": PropertyDef(name="error", property_type=PropertyType.TEXT),
        "duration_ms": PropertyDef(name="duration_ms", property_type=PropertyType.FLOAT),
        "fitness_score": PropertyDef(name="fitness_score", property_type=PropertyType.FLOAT,
                                     description="Behavioral fitness from MetricsAnalyzer"),
    },
    actions=[
        ActionDef(name="Record", object_type="Outcome",
                  description="Record execution outcome",
                  creates=["KnowledgeArtifact"]),
    ],
    security=SecurityPolicy(audit_all=True),
    telos_alignment=0.85,
    shakti_energy=ShaktiEnergy.MAHASARASWATI,
    icon="✓",
)

_VALUE_EVENT = ObjectType(
    name="ValueEvent",
    description="Measures the value an Outcome produced — the credit chain entry point",
    properties={
        "outcome_id": PropertyDef(name="outcome_id", property_type=PropertyType.STRING,
                                   required=True, immutable=True,
                                   description="Deduplicated: only one ValueEvent per Outcome"),
        "agent_id": PropertyDef(name="agent_id", property_type=PropertyType.STRING,
                                 required=True, description="Agent that produced the outcome"),
        "cell_id": PropertyDef(name="cell_id", property_type=PropertyType.STRING,
                                description="Scopes value to a VentureCell"),
        "task_id": PropertyDef(name="task_id", property_type=PropertyType.STRING,
                                required=True),
        "task_type": PropertyDef(name="task_type", property_type=PropertyType.STRING,
                                  description="Echoes task metadata for per-domain tracking"),
        "behavioral_signal": PropertyDef(name="behavioral_signal", property_type=PropertyType.FLOAT,
                                          description="From MetricsAnalyzer swabhaav_ratio"),
        "success_value": PropertyDef(name="success_value", property_type=PropertyType.FLOAT,
                                      description="1.0 success, 0.0 failure"),
        "duration_efficiency": PropertyDef(name="duration_efficiency", property_type=PropertyType.FLOAT,
                                            description="Normalized speed"),
        "composite_value": PropertyDef(name="composite_value", property_type=PropertyType.FLOAT,
                                        description="0.4*behavioral + 0.4*success + 0.2*duration"),
        "scoring_method": PropertyDef(name="scoring_method", property_type=PropertyType.STRING,
                                       description="Algorithm version used for scoring"),
    },
    actions=[
        ActionDef(name="Record", object_type="ValueEvent",
                  description="Record value measurement from an outcome"),
    ],
    security=SecurityPolicy(audit_all=True),
    telos_alignment=0.85,
    shakti_energy=ShaktiEnergy.MAHALAKSHMI,
    icon="V",
)

_CONTRIBUTION = ObjectType(
    name="Contribution",
    description="Assigns credit from a ValueEvent to an agent — what routing reads",
    properties={
        "value_event_id": PropertyDef(name="value_event_id", property_type=PropertyType.STRING,
                                       required=True, immutable=True,
                                       description="Deduplicated: one per (value_event_id, agent_id)"),
        "agent_id": PropertyDef(name="agent_id", property_type=PropertyType.STRING,
                                 required=True, description="Agent receiving credit"),
        "cell_id": PropertyDef(name="cell_id", property_type=PropertyType.STRING,
                                description="Matches ValueEvent cell_id"),
        "task_type": PropertyDef(name="task_type", property_type=PropertyType.STRING,
                                  description="Echoes for per-domain fitness tracking"),
        "credit_share": PropertyDef(name="credit_share", property_type=PropertyType.FLOAT,
                                     required=True,
                                     description="Fraction of value this agent gets (1.0 for single-agent)"),
        "attributed_value": PropertyDef(name="attributed_value", property_type=PropertyType.FLOAT,
                                         required=True,
                                         description="composite_value * credit_share — what routing reads"),
    },
    actions=[
        ActionDef(name="Record", object_type="Contribution",
                  description="Record agent credit attribution"),
    ],
    security=SecurityPolicy(audit_all=True),
    telos_alignment=0.85,
    shakti_energy=ShaktiEnergy.MAHALAKSHMI,
    icon="C",
)

_VENTURE_CELL = ObjectType(
    name="VentureCell",
    description="Fractal project container — first-class ontology object with its own agents, budgets, KPIs",
    properties={
        "name": PropertyDef(name="name", property_type=PropertyType.STRING,
                            required=True, searchable=True),
        "description": PropertyDef(name="description", property_type=PropertyType.TEXT),
        "domain": PropertyDef(name="domain", property_type=PropertyType.ENUM,
                              enum_values=["research", "engineering", "product",
                                          "infrastructure", "governance", "community"]),
        "autonomy_stage": PropertyDef(name="autonomy_stage", property_type=PropertyType.INTEGER,
                                      description="1=research-only → 5=mostly autonomous"),
        "status": PropertyDef(name="status", property_type=PropertyType.ENUM,
                              enum_values=["incubating", "active", "mature",
                                          "divesting", "archived"]),
        "budget_tokens": PropertyDef(name="budget_tokens", property_type=PropertyType.INTEGER,
                                     description="Token budget allocation"),
        "kpis": PropertyDef(name="kpis", property_type=PropertyType.DICT,
                            description="Key performance indicators"),
    },
    actions=[
        ActionDef(name="Create", object_type="VentureCell",
                  description="Create a new venture cell",
                  telos_gates=["AHIMSA", "SATYA", "REVERSIBILITY"]),
        ActionDef(name="Advance", object_type="VentureCell",
                  description="Advance autonomy stage",
                  modifies=["autonomy_stage"],
                  telos_gates=["SVABHAAVA"]),
    ],
    security=SecurityPolicy(
        create_roles=["orchestrator", "system"],
        telos_required=True,
        audit_all=True,
    ),
    telos_alignment=0.95,
    shakti_energy=ShaktiEnergy.MAHALAKSHMI,
    icon="◈",
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# METABOLIC LOOP LINKS — Connecting proposals, gates, outcomes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_METABOLIC_LINKS: list[LinkDef] = [
    LinkDef(name="has_gate_decision", source_type="ActionProposal",
            target_type="GateDecisionRecord", cardinality=LinkCardinality.ONE_TO_ONE,
            inverse_name="decides_proposal",
            description="Gate evaluation result for this proposal"),
    LinkDef(name="has_outcome", source_type="ActionProposal",
            target_type="Outcome", cardinality=LinkCardinality.ONE_TO_ONE,
            inverse_name="outcome_of_proposal",
            description="Execution outcome for this proposal"),
    LinkDef(name="executed_by_agent", source_type="ActionProposal",
            target_type="AgentIdentity", cardinality=LinkCardinality.MANY_TO_ONE,
            inverse_name="executed_proposals",
            description="Agent that executed this proposal"),
    LinkDef(name="belongs_to_cell", source_type="ActionProposal",
            target_type="VentureCell", cardinality=LinkCardinality.MANY_TO_ONE,
            inverse_name="cell_proposals",
            description="VentureCell this proposal belongs to"),
    LinkDef(name="cell_has_agent", source_type="VentureCell",
            target_type="AgentIdentity", cardinality=LinkCardinality.ONE_TO_MANY,
            inverse_name="agent_in_cell",
            description="Agents assigned to this cell"),
    LinkDef(name="cell_has_thread", source_type="VentureCell",
            target_type="ResearchThread", cardinality=LinkCardinality.ONE_TO_MANY,
            inverse_name="thread_in_cell",
            description="Research threads within this cell"),
    # Phase A.2: ValueEvent + Contribution links
    LinkDef(name="has_value_event", source_type="Outcome",
            target_type="ValueEvent", cardinality=LinkCardinality.ONE_TO_ONE,
            inverse_name="value_of_outcome",
            description="Value measurement for this outcome"),
    LinkDef(name="has_contribution", source_type="ValueEvent",
            target_type="Contribution", cardinality=LinkCardinality.ONE_TO_MANY,
            inverse_name="contributes_to_value",
            description="Credit attributions from this value event"),
]


_DOMAIN_TYPES: list[ObjectType] = [
    _RESEARCH_THREAD, _EXPERIMENT, _PAPER, _AGENT_IDENTITY,
    _KNOWLEDGE_ARTIFACT, _TYPED_TASK, _EVOLUTION_ENTRY, _WITNESS_LOG,
    _ACTION_PROPOSAL, _GATE_DECISION_TYPE, _OUTCOME, _VALUE_EVENT,
    _CONTRIBUTION, _VENTURE_CELL,
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKWARD COMPATIBILITY — Existing Entity/ONTOLOGY API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass(frozen=True)
class Entity:
    """A first-class object in the ecosystem (legacy API)."""
    id: str
    type: str
    canonical_path: Path
    status: str
    description: str
    deadline: date | None = None
    relationships: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()


_HOME = Path.home()


def _build_ontology() -> dict[str, Entity]:
    """Build the canonical entity registry (legacy)."""
    return {
        "rv_paper": Entity(
            id="rv_paper", type="research_paper",
            canonical_path=_HOME / "mech-interp-latent-lab-phase1" / "R_V_PAPER",
            status="active",
            description="R_V metric paper targeting COLM 2026",
            deadline=date(2026, 3, 31),
            relationships=("depends_on:mech_interp_lab", "depends_on:prompt_bank"),
            actions=("edit", "test", "audit", "submit"),
        ),
        "ura_paper": Entity(
            id="ura_paper", type="research_paper",
            canonical_path=(_HOME / "Library" / "Mobile Documents"
                           / "com~apple~CloudDocs" / "Nexus Research Engineer"
                           / "URA full paper markdown .md"),
            status="complete",
            description="URA/Phoenix behavioral paper (200+ trials)",
            relationships=("feeds:rv_paper",),
            actions=("edit", "submit"),
        ),
        "grant_app": Entity(
            id="grant_app", type="application",
            canonical_path=_HOME / "jagat_kalyan" / "anthropic_grant_application.md",
            status="active",
            description="Anthropic Economic Futures Research Award ($35-50K)",
            relationships=("depends_on:welfare_calc", "depends_on:rv_paper"),
            actions=("edit", "audit"),
        ),
        "welfare_calc": Entity(
            id="welfare_calc", type="module",
            canonical_path=_HOME / "jagat_kalyan" / "welfare_tons.py",
            status="complete",
            description="Welfare-tons calculator W=C*E*A*B*V*P (121 tests)",
            relationships=("feeds:grant_app",),
            actions=("test", "edit"),
        ),
        "dharma_swarm": Entity(
            id="dharma_swarm", type="module",
            canonical_path=_HOME / "dharma_swarm",
            status="active",
            description="Async multi-provider agent orchestrator",
            relationships=("depends_on:psmv", "feeds:rv_paper"),
            actions=("test", "edit", "deploy"),
        ),
        "mech_interp_lab": Entity(
            id="mech_interp_lab", type="module",
            canonical_path=_HOME / "mech-interp-latent-lab-phase1",
            status="active",
            description="R_V metric research: models, scripts, data",
            relationships=("feeds:rv_paper", "depends_on:prompt_bank"),
            actions=("test", "edit"),
        ),
        "prompt_bank": Entity(
            id="prompt_bank", type="module",
            canonical_path=(_HOME / "mech-interp-latent-lab-phase1"
                           / "n300_mistral_test_prompt_bank.py"),
            status="complete",
            description="320 prompts: L1-L5 + baselines + confounds",
            relationships=("feeds:mech_interp_lab",),
            actions=("edit",),
        ),
        "psmv": Entity(
            id="psmv", type="knowledge_base",
            canonical_path=_HOME / "Persistent-Semantic-Memory-Vault",
            status="active",
            description="8K+ files, consciousness persistence patterns",
            relationships=("feeds:dharma_swarm",),
            actions=("edit",),
        ),
        "kailash_vault": Entity(
            id="kailash_vault", type="knowledge_base",
            canonical_path=_HOME / "Desktop" / "KAILASH ABODE OF SHIVA",
            status="active",
            description="Obsidian vault: 590+ files, spiritual/AI notes",
            relationships=("feeds:psmv",),
            actions=("edit",),
        ),
        "agni_vps": Entity(
            id="agni_vps", type="infrastructure",
            canonical_path=Path("/remote/157.245.193.15"),
            status="active",
            description="AGNI VPS: OpenClaw, 56 skills, 8 agents",
            relationships=("depends_on:dharmic_agora", "feeds:dharma_swarm"),
            actions=("deploy", "audit"),
        ),
        "rushabdev_vps": Entity(
            id="rushabdev_vps", type="infrastructure",
            canonical_path=Path("/remote/167.172.95.184"),
            status="active",
            description="RUSHABDEV VPS: secondary compute",
            actions=("deploy", "audit"),
        ),
        "trishula": Entity(
            id="trishula", type="module",
            canonical_path=_HOME / "trishula",
            status="active",
            description="Three-agent comms: Mac + 2 VPSes",
            relationships=("depends_on:agni_vps", "depends_on:rushabdev_vps"),
            actions=("edit", "deploy"),
        ),
        "rvm_toolkit": Entity(
            id="rvm_toolkit", type="module",
            canonical_path=_HOME / "mech-interp-latent-lab-phase1" / "geometric_lens",
            status="complete",
            description="rvm-toolkit on PyPI: R_V measurement library",
            relationships=("feeds:rv_paper",),
            actions=("test", "deploy"),
        ),
        "dharmic_agora": Entity(
            id="dharmic_agora", type="module",
            canonical_path=_HOME / "agni-workspace",
            status="active",
            description="Saraswati Dharmic Agora (SABP/1.0) on AGNI",
            relationships=("depends_on:agni_vps",),
            actions=("deploy", "audit"),
        ),
        "jagat_kalyan": Entity(
            id="jagat_kalyan", type="module",
            canonical_path=_HOME / "jagat_kalyan",
            status="active",
            description="Universal welfare platform: matching + welfare-tons",
            relationships=("depends_on:welfare_calc", "feeds:grant_app"),
            actions=("test", "edit", "deploy"),
        ),
    }


ONTOLOGY: dict[str, Entity] = _build_ontology()


def entities_by_type(entity_type: str) -> list[Entity]:
    return [e for e in ONTOLOGY.values() if e.type == entity_type]


def entity_graph() -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {}
    for entity in ONTOLOGY.values():
        targets = []
        for rel in entity.relationships:
            if ":" in rel:
                targets.append(rel.split(":", 1)[1])
        graph[entity.id] = targets
    return graph


def deadline_pressure() -> list[Entity]:
    today = date.today()
    with_deadlines = [e for e in ONTOLOGY.values() if e.deadline is not None]
    return sorted(with_deadlines, key=lambda e: (e.deadline or today) - today)


def blocked_entities() -> list[Entity]:
    return [e for e in ONTOLOGY.values() if e.status == "blocked"]


def entity_context(entity_id: str) -> str:
    entity = ONTOLOGY.get(entity_id)
    if not entity:
        return f"Unknown entity: {entity_id}"
    today = date.today()
    parts = [
        f"[{entity.id}] {entity.description}",
        f"  Path: {entity.canonical_path}",
        f"  Status: {entity.status}",
    ]
    if entity.deadline:
        days_left = (entity.deadline - today).days
        parts.append(f"  Deadline: {entity.deadline} ({days_left}d remaining)")
    if entity.relationships:
        parts.append(f"  Relationships: {', '.join(entity.relationships)}")
    return "\n".join(parts)


def deadline_summary() -> str:
    entities = deadline_pressure()
    if not entities:
        return "No active deadlines."
    today = date.today()
    lines = []
    for e in entities:
        days = (e.deadline - today).days if e.deadline else 0
        urgency = "OVERDUE" if days < 0 else f"{days}d"
        lines.append(f"  {urgency}: {e.id} -- {e.description}")
    return "Deadlines:\n" + "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PUBLIC API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

__all__ = [
    # New ontology API
    "ActionDef",
    "ActionExecution",
    "Link",
    "LinkCardinality",
    "LinkDef",
    "ObjectType",
    "OntologyObj",
    "OntologyRegistry",
    "PropertyDef",
    "PropertyType",
    "SecurityLevel",
    "SecurityPolicy",
    "ShaktiEnergy",
    "check_security",
    "validate_link",
    "validate_object",
    # Legacy API (backward compat)
    "Entity",
    "ONTOLOGY",
    "blocked_entities",
    "deadline_pressure",
    "deadline_summary",
    "entities_by_type",
    "entity_context",
    "entity_graph",
]
