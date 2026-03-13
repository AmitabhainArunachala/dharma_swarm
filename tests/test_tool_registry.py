"""Tests for the Tool Registry (Hermes-inspired)."""

from __future__ import annotations

import json

import pytest

from dharma_swarm.tool_registry import ToolRegistry, registry


class TestToolRegistration:
    """Tests for tool registration and lookup."""

    def test_register_and_lookup(self):
        reg = ToolRegistry()
        reg.register(
            name="test_tool",
            toolset="core",
            schema={"name": "test_tool", "description": "A test", "parameters": {}},
            handler=lambda args, **kw: json.dumps({"ok": True}),
        )
        assert "test_tool" in reg
        assert len(reg) == 1
        assert reg.get_all_tool_names() == ["test_tool"]

    def test_get_toolset_for_tool(self):
        reg = ToolRegistry()
        reg.register(
            name="alpha",
            toolset="group_a",
            schema={"name": "alpha", "description": "A"},
            handler=lambda args, **kw: "{}",
        )
        assert reg.get_toolset_for_tool("alpha") == "group_a"
        assert reg.get_toolset_for_tool("nonexistent") is None

    def test_tool_to_toolset_map(self):
        reg = ToolRegistry()
        reg.register(name="a", toolset="x", schema={"name": "a"}, handler=lambda a, **kw: "{}")
        reg.register(name="b", toolset="y", schema={"name": "b"}, handler=lambda a, **kw: "{}")
        mapping = reg.get_tool_to_toolset_map()
        assert mapping == {"a": "x", "b": "y"}

    def test_contains(self):
        reg = ToolRegistry()
        reg.register(name="foo", toolset="t", schema={"name": "foo"}, handler=lambda a, **kw: "{}")
        assert "foo" in reg
        assert "bar" not in reg


class TestToolDefinitions:
    """Tests for schema retrieval with availability checks."""

    def test_get_all_definitions(self):
        reg = ToolRegistry()
        reg.register(name="a", toolset="t", schema={"name": "a", "description": "A"}, handler=lambda a, **kw: "{}")
        reg.register(name="b", toolset="t", schema={"name": "b", "description": "B"}, handler=lambda a, **kw: "{}")
        defs = reg.get_definitions()
        assert len(defs) == 2
        assert all(d["type"] == "function" for d in defs)

    def test_get_definitions_filtered(self):
        reg = ToolRegistry()
        reg.register(name="a", toolset="t", schema={"name": "a"}, handler=lambda a, **kw: "{}")
        reg.register(name="b", toolset="t", schema={"name": "b"}, handler=lambda a, **kw: "{}")
        defs = reg.get_definitions(tool_names={"a"})
        assert len(defs) == 1

    def test_check_fn_filters_unavailable(self):
        reg = ToolRegistry()
        reg.register(
            name="available", toolset="t",
            schema={"name": "available"}, handler=lambda a, **kw: "{}",
            check_fn=lambda: True,
        )
        reg.register(
            name="unavailable", toolset="t",
            schema={"name": "unavailable"}, handler=lambda a, **kw: "{}",
            check_fn=lambda: False,
        )
        defs = reg.get_definitions()
        assert len(defs) == 1
        assert defs[0]["function"]["name"] == "available"

    def test_check_fn_exception_skips(self):
        reg = ToolRegistry()
        def bad_check():
            raise RuntimeError("broken")
        reg.register(
            name="broken", toolset="t",
            schema={"name": "broken"}, handler=lambda a, **kw: "{}",
            check_fn=bad_check,
        )
        defs = reg.get_definitions(quiet=True)
        assert len(defs) == 0


class TestToolDispatch:
    """Tests for tool execution dispatch."""

    def test_dispatch_sync(self):
        reg = ToolRegistry()
        reg.register(
            name="echo",
            toolset="core",
            schema={"name": "echo"},
            handler=lambda args, **kw: json.dumps({"echo": args.get("msg")}),
        )
        result = json.loads(reg.dispatch("echo", {"msg": "hello"}))
        assert result == {"echo": "hello"}

    def test_dispatch_unknown_tool(self):
        reg = ToolRegistry()
        result = json.loads(reg.dispatch("nonexistent", {}))
        assert "error" in result
        assert "Unknown tool" in result["error"]

    def test_dispatch_error_handling(self):
        reg = ToolRegistry()
        def bad_handler(args, **kw):
            raise ValueError("boom")
        reg.register(name="bad", toolset="t", schema={"name": "bad"}, handler=bad_handler)
        result = json.loads(reg.dispatch("bad", {}))
        assert "error" in result
        assert "boom" in result["error"]


class TestToolsetAvailability:
    """Tests for toolset-level checks."""

    def test_toolset_available_no_check(self):
        reg = ToolRegistry()
        reg.register(name="a", toolset="open", schema={"name": "a"}, handler=lambda a, **kw: "{}")
        assert reg.is_toolset_available("open") is True

    def test_toolset_available_with_check(self):
        reg = ToolRegistry()
        reg.register(
            name="a", toolset="gated",
            schema={"name": "a"}, handler=lambda a, **kw: "{}",
            check_fn=lambda: True,
        )
        assert reg.is_toolset_available("gated") is True

    def test_toolset_unavailable(self):
        reg = ToolRegistry()
        reg.register(
            name="a", toolset="locked",
            schema={"name": "a"}, handler=lambda a, **kw: "{}",
            check_fn=lambda: False,
        )
        assert reg.is_toolset_available("locked") is False

    def test_check_toolset_requirements(self):
        reg = ToolRegistry()
        reg.register(name="a", toolset="yes", schema={"name": "a"}, handler=lambda a, **kw: "{}", check_fn=lambda: True)
        reg.register(name="b", toolset="no", schema={"name": "b"}, handler=lambda a, **kw: "{}", check_fn=lambda: False)
        reqs = reg.check_toolset_requirements()
        assert reqs["yes"] is True
        assert reqs["no"] is False

    def test_get_available_toolsets(self):
        reg = ToolRegistry()
        reg.register(
            name="x", toolset="ts1",
            schema={"name": "x"}, handler=lambda a, **kw: "{}",
            requires_env=["API_KEY"],
        )
        toolsets = reg.get_available_toolsets()
        assert "ts1" in toolsets
        assert "x" in toolsets["ts1"]["tools"]
        assert "API_KEY" in toolsets["ts1"]["requirements"]


class TestModuleSingleton:
    """Test the module-level singleton."""

    def test_singleton_exists(self):
        assert isinstance(registry, ToolRegistry)
