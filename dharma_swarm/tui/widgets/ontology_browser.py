"""Ontology browser widget — type tree + detail panel.

Shows the ontology type hierarchy with objects, links, and actions.
Selecting a tree node updates the detail panel.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Static, Tree

INDIGO = "#94A3B8"
VERDIGRIS = "#8FA89B"
OCHRE = "#C5B198"
ASH = "#A7AEBE"
PAPER = "#D8DCE6"

# Shakti energy to icon mapping
_SHAKTI_ICONS = {
    "maheshwari": "👁",
    "mahakali": "⚡",
    "mahalakshmi": "✨",
    "mahasaraswati": "🔬",
}


class OntologyTree(Tree):
    """Tree widget showing ontology types and their objects."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__("Ontology", *args, **kwargs)
        self._type_data: dict[str, Any] = {}

    def populate(self, registry: Any) -> None:
        """Build tree from OntologyRegistry."""
        self.clear()
        self.root.expand()
        self._type_data.clear()

        types = registry.get_types()
        for obj_type in sorted(types, key=lambda t: t.name):
            icon = _SHAKTI_ICONS.get(
                obj_type.shakti_energy.value if hasattr(obj_type, "shakti_energy") else "",
                "◆",
            )
            type_node = self.root.add(
                f"{icon} {obj_type.name}",
                data={"kind": "type", "name": obj_type.name},
            )
            # Add properties as children
            if obj_type.properties:
                props_node = type_node.add("Properties", data={"kind": "section"})
                for pname, pdef in obj_type.properties.items():
                    req = " *" if pdef.required else ""
                    props_node.add_leaf(
                        f"{pname}: {pdef.property_type.value}{req}",
                        data={"kind": "property", "type": obj_type.name, "prop": pname},
                    )

            # Add links
            links = registry.get_links_for(obj_type.name)
            if links:
                links_node = type_node.add("Links", data={"kind": "section"})
                for ld in links:
                    links_node.add_leaf(
                        f"{ld.name} → {ld.target_type} ({ld.cardinality.value})",
                        data={"kind": "link", "source": obj_type.name, "link": ld.name},
                    )

            # Add actions
            actions = registry.get_actions_for(obj_type.name)
            if actions:
                actions_node = type_node.add("Actions", data={"kind": "section"})
                for ad in actions:
                    det = "⚙" if ad.is_deterministic else "🤖"
                    actions_node.add_leaf(
                        f"{det} {ad.name}",
                        data={"kind": "action", "type": obj_type.name, "action": ad.name},
                    )

            # Add object instances
            objects = registry.get_objects_by_type(obj_type.name)
            if objects:
                objs_node = type_node.add(
                    f"Instances ({len(objects)})", data={"kind": "section"}
                )
                for obj in objects[:20]:  # cap display
                    label = obj.properties.get(
                        "name", obj.properties.get("title", obj.id[:12])
                    )
                    objs_node.add_leaf(
                        str(label),
                        data={"kind": "object", "id": obj.id, "type": obj.type_name},
                    )


class OntologyDetail(Static):
    """Detail panel for selected ontology node."""

    def show_type(self, registry: Any, type_name: str) -> None:
        """Display type description from registry."""
        desc = registry.describe_type(type_name)
        # Escape Rich markup in description
        safe = desc.replace("[", "\\[")
        self.update(safe)

    def show_object(self, registry: Any, obj_id: str) -> None:
        """Display object detail."""
        context = registry.object_context_for_llm(obj_id, include_links=True)
        safe = context.replace("[", "\\[")
        self.update(safe)

    def clear_detail(self) -> None:
        self.update(f"[{ASH}]Select a type or object to view details[/{ASH}]")


class OntologyTab(Horizontal):
    """Composite widget for the Ontology tab."""

    def compose(self) -> ComposeResult:
        yield OntologyTree(id="onto-tree-container")
        with VerticalScroll(id="onto-detail-container"):
            yield OntologyDetail(id="onto-detail")

    def on_mount(self) -> None:
        detail = self.query_one("#onto-detail", OntologyDetail)
        detail.clear_detail()

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Update detail when tree selection changes."""
        data = event.node.data
        if not data or not isinstance(data, dict):
            return
        detail = self.query_one("#onto-detail", OntologyDetail)
        registry = getattr(self.screen, "_registry", None)
        if registry is None:
            return

        kind = data.get("kind", "")
        if kind == "type":
            detail.show_type(registry, data["name"])
        elif kind == "object":
            detail.show_object(registry, data["id"])
        else:
            detail.clear_detail()
