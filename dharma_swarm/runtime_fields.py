"""Runtime field registry for safe prompt/parameter evolution.

This module borrows the strongest idea from EvoAgentX: make runtime values
first-class mutation targets without forcing code-file edits. The registry is
pure runtime state. Darwin or other evaluators can later mutate these fields
and rely on snapshot/reset support for rollback.
"""

from __future__ import annotations

import copy
import json
import re
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable

from dharma_swarm.models import AgentConfig

_PATH_RE = re.compile(
    r"""
    ([a-zA-Z_]\w*)               |
    \[\s*(-?\d+)\s*\]            |
    \[\s*['"]([^'"]+)['"]\s*\]
    """,
    re.VERBOSE,
)


def safe_deepcopy(value: Any) -> Any:
    """Return a best-effort deep copy, falling back to the original object."""
    try:
        return copy.deepcopy(value)
    except Exception:
        return value


@dataclass(frozen=True)
class RuntimeFieldSpec:
    """Declarative description of a config/runtime mutation target."""

    name: str
    path: str


@dataclass
class OptimizableField:
    """A runtime value exposed through getter/setter hooks."""

    name: str
    getter: Callable[[], Any]
    setter: Callable[[Any], None]
    _initial_value: Any = field(default=None, init=False, repr=False)
    _has_snapshot: bool = field(default=False, init=False, repr=False)

    def get(self) -> Any:
        return self.getter()

    def set(self, value: Any) -> None:
        self.setter(value)

    def init_snapshot(self) -> None:
        self._initial_value = safe_deepcopy(self.get())
        self._has_snapshot = True

    def reset(self) -> None:
        if not self._has_snapshot:
            raise ValueError(
                f"Field '{self.name}' has no snapshot. Call init_snapshot() first."
            )
        current = self.get()
        reset_method = getattr(current, "__reset__", None)
        if callable(reset_method):
            reset_method()
            return
        self.set(safe_deepcopy(self._initial_value))


class RuntimeFieldRegistry:
    """Track runtime mutation targets and support rollback to initial state."""

    def __init__(self) -> None:
        self.fields: dict[str, OptimizableField] = {}

    def register_field(self, field: OptimizableField) -> "RuntimeFieldRegistry":
        if field.name in self.fields:
            warnings.warn(f"Field '{field.name}' is already registered. Overwriting.")
        field.init_snapshot()
        self.fields[field.name] = field
        return self

    def get(self, name: str) -> Any:
        return self.get_field(name).get()

    def get_field(self, name: str) -> OptimizableField:
        if name not in self.fields:
            raise KeyError(f"Field '{name}' is not registered.")
        return self.fields[name]

    def set(self, name: str, value: Any) -> None:
        self.get_field(name).set(value)

    def names(self) -> list[str]:
        return list(self.fields.keys())

    def reset(self) -> None:
        for field in self.fields.values():
            field.reset()

    def reset_field(self, name: str) -> None:
        self.get_field(name).reset()

    def track(
        self,
        root_or_items: Any,
        path_or_attr: str | None = None,
        *,
        name: str | None = None,
    ) -> "RuntimeFieldRegistry":
        """Register a direct attribute or a nested path as optimizable.

        Examples:
            registry.track(workflow, "system_prompt")
            registry.track(workflow, "sampler.temperature", name="temperature")
            registry.track(workflow, "metadata['style']", name="style")
            registry.track([
                (workflow, "system_prompt"),
                (workflow, "sampler.temperature", "temperature"),
            ])
        """
        if path_or_attr is None:
            if not isinstance(root_or_items, (list, tuple)):
                raise ValueError("Batch registration requires an iterable of tuples.")
            for item in root_or_items:
                if len(item) == 2:
                    self.track(item[0], item[1])
                elif len(item) == 3:
                    self.track(item[0], item[1], name=item[2])
                else:
                    raise ValueError("Batch items must be (obj, path) or (obj, path, name).")
            return self

        if "." in path_or_attr or "[" in path_or_attr:
            return self._track_path(root_or_items, path_or_attr, name)

        key = name or path_or_attr

        def getter() -> Any:
            return getattr(root_or_items, path_or_attr)

        def setter(value: Any) -> None:
            setattr(root_or_items, path_or_attr, value)

        return self.register_field(OptimizableField(key, getter, setter))

    def _track_path(
        self,
        root: Any,
        path: str,
        name: str | None = None,
    ) -> "RuntimeFieldRegistry":
        key = name or path
        parent, leaf = self._walk(root, path)

        def getter() -> Any:
            return parent[leaf] if isinstance(parent, (list, dict)) else getattr(parent, leaf)

        def setter(value: Any) -> None:
            if isinstance(parent, (list, dict)):
                parent[leaf] = value
            else:
                setattr(parent, leaf, value)

        return self.register_field(OptimizableField(key, getter, setter))

    def _walk(self, root: Any, path: str) -> tuple[Any, Any]:
        current = root
        parts = path.split(".")
        for part in parts[:-1]:
            current = self._descend(current, part)

        operations = self._parse_token(parts[-1])
        if not operations:
            raise ValueError(f"Invalid path token: {parts[-1]!r}")

        parent = current
        for operation in operations[:-1]:
            parent = self._apply_operation(parent, operation)

        leaf_kind, leaf_value = operations[-1]
        if leaf_kind == "item":
            return parent, leaf_value
        return parent, leaf_value

    def _descend(self, current: Any, token: str) -> Any:
        operations = self._parse_token(token)
        if not operations:
            raise ValueError(f"Invalid path token: {token!r}")
        for operation in operations:
            current = self._apply_operation(current, operation)
        return current

    def _apply_operation(self, current: Any, operation: tuple[str, Any]) -> Any:
        kind, value = operation
        if kind == "attr":
            return getattr(current, value)
        return current[value]

    def _parse_token(self, token: str) -> list[tuple[str, Any]]:
        operations: list[tuple[str, Any]] = []
        for match in _PATH_RE.finditer(token):
            attr, index, key = match.groups()
            if attr is not None:
                operations.append(("attr", attr))
            elif index is not None:
                operations.append(("item", int(index)))
            elif key is not None:
                operations.append(("item", key))
        return operations

    @staticmethod
    def _coerce_index(index: str) -> Any:
        value = index.strip()
        if (value.startswith("'") and value.endswith("'")) or (
            value.startswith('"') and value.endswith('"')
        ):
            return value[1:-1]
        if re.fullmatch(r"-?\d+", value):
            return int(value)
        return value


def infer_field_name(path: str) -> str:
    """Infer a stable field name from a dotted/indexed path."""
    registry = RuntimeFieldRegistry()
    operations = registry._parse_token(path.split(".")[-1])  # noqa: SLF001 - shared parser
    if not operations:
        return path
    _kind, value = operations[-1]
    return str(value)


def runtime_field_specs_from_agent_config(config: AgentConfig) -> list[RuntimeFieldSpec]:
    """Extract runtime field specs from agent config metadata.

    `system_prompt` is always tracked. Additional declarations can be passed via
    `config.metadata["optimizable_fields"]` as either:
    - `"sampler.temperature"`
    - `{"name": "temperature", "path": "sampler.temperature"}`
    """
    specs: list[RuntimeFieldSpec] = [RuntimeFieldSpec(name="system_prompt", path="system_prompt")]
    seen = {"system_prompt"}
    raw_items = config.metadata.get("optimizable_fields", [])
    if not isinstance(raw_items, list):
        return specs

    for item in raw_items:
        if isinstance(item, str):
            path = item.strip()
            if not path:
                continue
            name = infer_field_name(path)
        elif isinstance(item, dict):
            raw_path = item.get("path")
            if not isinstance(raw_path, str) or not raw_path.strip():
                continue
            path = raw_path.strip()
            raw_name = item.get("name")
            name = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else infer_field_name(path)
        else:
            continue

        if name in seen:
            continue
        seen.add(name)
        specs.append(RuntimeFieldSpec(name=name, path=path))

    return specs


def build_runtime_field_registry_from_agent_config(config: AgentConfig) -> RuntimeFieldRegistry:
    """Build a registry from an AgentConfig and its metadata declarations."""
    registry = RuntimeFieldRegistry()
    for spec in runtime_field_specs_from_agent_config(config):
        try:
            registry.track(config, spec.path, name=spec.name)
        except Exception as exc:
            warnings.warn(
                f"Skipping optimizable field '{spec.name}' at path '{spec.path}': {exc}"
            )
    return registry


def _manifest_value(value: Any) -> Any:
    """Return a JSON-safe manifest value or a compact preview string."""
    preview = safe_deepcopy(value)
    try:
        json.dumps(preview)
    except TypeError:
        return repr(value)
    return preview


def runtime_field_manifest_for_agent_config(config: AgentConfig) -> list[dict[str, Any]]:
    """Return a serializable manifest describing current runtime field values."""
    registry = build_runtime_field_registry_from_agent_config(config)
    manifest: list[dict[str, Any]] = []
    for spec in runtime_field_specs_from_agent_config(config):
        if spec.name not in registry.fields:
            continue
        value = registry.get(spec.name)
        manifest.append(
            {
                "name": spec.name,
                "path": spec.path,
                "value_type": type(value).__name__,
                "current_value": _manifest_value(value),
            }
        )
    return manifest
