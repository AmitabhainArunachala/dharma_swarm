"""Tests for context_compiler.py — canonical runtime context compilation."""

from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.context_compiler import (
    ContextCompiler,
    ContextSection,
    _approx_char_budget,
    _canonical_json,
    _dedupe,
    _sha256,
    _truncate,
    _utc_now,
)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


class TestCanonicalJson:
    def test_sorted_keys(self):
        result = _canonical_json({"b": 2, "a": 1})
        assert result == '{"a":1,"b":2}'

    def test_no_whitespace(self):
        result = _canonical_json({"key": "value"})
        assert " " not in result

    def test_nested(self):
        result = _canonical_json({"outer": {"inner": 1}})
        assert '"outer":{"inner":1}' in result


class TestSha256:
    def test_returns_hex(self):
        h = _sha256("hello")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        assert _sha256("test") == _sha256("test")

    def test_different_inputs(self):
        assert _sha256("a") != _sha256("b")


class TestUtcNow:
    def test_has_timezone(self):
        now = _utc_now()
        assert now.tzinfo is not None


class TestApproxCharBudget:
    def test_scales_with_tokens(self):
        assert _approx_char_budget(1000) == 4000

    def test_minimum_800(self):
        assert _approx_char_budget(0) == 800
        assert _approx_char_budget(1) == 800

    def test_negative_clamps(self):
        assert _approx_char_budget(-100) == 800


class TestDedupe:
    def test_removes_duplicates(self):
        assert _dedupe(["a", "b", "a", "c"]) == ["a", "b", "c"]

    def test_preserves_order(self):
        assert _dedupe(["c", "b", "a"]) == ["c", "b", "a"]

    def test_strips_whitespace(self):
        assert _dedupe(["  hello  ", "hello"]) == ["hello"]

    def test_removes_empty(self):
        assert _dedupe(["", "a", "  ", "b"]) == ["a", "b"]

    def test_empty_input(self):
        assert _dedupe([]) == []


class TestTruncate:
    def test_short_text_unchanged(self):
        assert _truncate("hello", 100) == "hello"

    def test_long_text_truncated(self):
        text = "x" * 200
        result = _truncate(text, 100)
        # Truncation marker adds ~16 chars; result is approximately budget-sized
        assert len(result) < 110
        assert "[truncated]" in result

    def test_zero_budget(self):
        assert _truncate("hello", 0) == ""

    def test_negative_budget(self):
        assert _truncate("hello", -5) == ""

    def test_exact_length(self):
        text = "hello"
        assert _truncate(text, 5) == "hello"

    def test_very_small_budget(self):
        result = _truncate("hello world", 10)
        assert len(result) <= 10


# ---------------------------------------------------------------------------
# ContextSection
# ---------------------------------------------------------------------------


class TestContextSection:
    def test_creation(self):
        section = ContextSection(name="Test", priority=1, content="body")
        assert section.name == "Test"
        assert section.priority == 1
        assert section.content == "body"

    def test_as_dict(self):
        section = ContextSection(
            name="Test", priority=1, content="body",
            source_refs=["ref1"], metadata={"key": "val"},
        )
        d = section.as_dict()
        assert d["name"] == "Test"
        assert d["priority"] == 1
        assert d["source_refs"] == ["ref1"]
        assert d["metadata"] == {"key": "val"}

    def test_frozen(self):
        section = ContextSection(name="Test", priority=1, content="body")
        with pytest.raises(AttributeError):
            section.name = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ContextCompiler — section weights
# ---------------------------------------------------------------------------


class TestSectionWeights:
    def test_weights_sum_to_one(self):
        total = sum(ContextCompiler._SECTION_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01

    def test_all_weights_positive(self):
        for name, weight in ContextCompiler._SECTION_WEIGHTS.items():
            assert weight > 0, f"Weight for {name} is not positive"


# ---------------------------------------------------------------------------
# ContextCompiler — _fit_sections and _render (pure methods)
# ---------------------------------------------------------------------------


class TestFitSections:
    def _make_compiler(self):
        """Create a compiler with mocked dependencies (only using pure methods)."""
        from unittest.mock import MagicMock
        compiler = ContextCompiler(
            runtime_state=MagicMock(),
            memory_lattice=MagicMock(),
        )
        return compiler

    def test_render_basic(self):
        compiler = self._make_compiler()
        sections = [
            ContextSection(name="Governance", priority=1, content="- rule 1"),
            ContextSection(name="Task State", priority=3, content="- task_id=t1"),
        ]
        rendered = compiler._render(sections)
        assert "# DGC Context Bundle" in rendered
        assert "## Governance" in rendered
        assert "## Task State" in rendered
        assert "rule 1" in rendered

    def test_render_empty(self):
        compiler = self._make_compiler()
        rendered = compiler._render([])
        assert rendered == "# DGC Context Bundle"

    def test_fit_sections_within_budget(self):
        compiler = self._make_compiler()
        sections = [
            ContextSection(name="Governance", priority=1, content="- rule 1"),
            ContextSection(name="Task State", priority=3, content="- task_id=t1"),
        ]
        rendered, kept = compiler._fit_sections(sections, char_budget=5000)
        assert len(rendered) <= 5000
        assert len(kept) == 2

    def test_fit_sections_truncates_on_tight_budget(self):
        compiler = self._make_compiler()
        sections = [
            ContextSection(name="Governance", priority=1, content="x" * 500),
            ContextSection(name="Task State", priority=3, content="y" * 500),
            ContextSection(name="Operator Intent", priority=2, content="z" * 500),
        ]
        rendered, kept = compiler._fit_sections(sections, char_budget=300)
        assert len(rendered) <= 300

    def test_fit_sections_priority_order(self):
        compiler = self._make_compiler()
        sections = [
            ContextSection(name="Low", priority=9, content="low stuff"),
            ContextSection(name="High", priority=1, content="high stuff"),
        ]
        rendered, kept = compiler._fit_sections(sections, char_budget=5000)
        # Higher priority (lower number) comes first
        high_pos = rendered.index("High")
        low_pos = rendered.index("Low")
        assert high_pos < low_pos


# ---------------------------------------------------------------------------
# ContextCompiler — freeze/thaw API
# ---------------------------------------------------------------------------


class TestFreezeThaw:
    def _make_compiler(self):
        from unittest.mock import MagicMock
        return ContextCompiler(
            runtime_state=MagicMock(),
            memory_lattice=MagicMock(),
        )

    def test_not_frozen_initially(self):
        compiler = self._make_compiler()
        assert not compiler.is_frozen("session-1")

    def test_freeze_and_check(self):
        compiler = self._make_compiler()
        from unittest.mock import MagicMock
        bundle = MagicMock()
        compiler.freeze("session-1", bundle)
        assert compiler.is_frozen("session-1")

    def test_thaw_returns_bundle(self):
        compiler = self._make_compiler()
        from unittest.mock import MagicMock
        bundle = MagicMock()
        compiler.freeze("session-1", bundle)
        thawed = compiler.thaw("session-1")
        assert thawed is bundle
        assert not compiler.is_frozen("session-1")

    def test_thaw_missing_returns_none(self):
        compiler = self._make_compiler()
        assert compiler.thaw("nonexistent") is None


# ---------------------------------------------------------------------------
# ContextCompiler — _compose_recall_query
# ---------------------------------------------------------------------------


class TestComposeRecallQuery:
    def _make_compiler(self):
        from unittest.mock import MagicMock
        return ContextCompiler(
            runtime_state=MagicMock(),
            memory_lattice=MagicMock(),
        )

    def test_explicit_query(self):
        compiler = self._make_compiler()
        result = compiler._compose_recall_query(
            operator_intent="intent", task_description="desc",
            query="explicit query", task_id="t1",
        )
        assert result == "explicit query"

    def test_composed_from_parts(self):
        compiler = self._make_compiler()
        result = compiler._compose_recall_query(
            operator_intent="find bugs", task_description="audit code",
            query=None, task_id="task-42",
        )
        assert "find bugs" in result
        assert "audit code" in result
        assert "task-42" in result

    def test_empty_parts(self):
        compiler = self._make_compiler()
        result = compiler._compose_recall_query(
            operator_intent="", task_description="",
            query=None, task_id="",
        )
        assert result == ""


# ---------------------------------------------------------------------------
# ContextCompiler — _workspace_section
# ---------------------------------------------------------------------------


class TestWorkspaceSection:
    def _make_compiler(self):
        from unittest.mock import MagicMock
        return ContextCompiler(
            runtime_state=MagicMock(),
            memory_lattice=MagicMock(),
        )

    def test_with_active_paths(self, tmp_path):
        compiler = self._make_compiler()
        f = tmp_path / "code.py"
        f.write_text("print('hello')")

        content, refs = compiler._workspace_section(
            workspace_root=None, active_paths=[f],
        )
        assert "code.py" in content
        assert str(f) in refs

    def test_with_workspace_root(self, tmp_path):
        compiler = self._make_compiler()
        (tmp_path / "a.py").write_text("module a")
        (tmp_path / "b.py").write_text("module b")

        content, refs = compiler._workspace_section(
            workspace_root=tmp_path, active_paths=[],
        )
        assert content  # should find files

    def test_empty_workspace(self, tmp_path):
        compiler = self._make_compiler()
        empty = tmp_path / "empty_dir"
        empty.mkdir()

        content, refs = compiler._workspace_section(
            workspace_root=empty, active_paths=[],
        )
        assert content == ""
        assert refs == []

    def test_no_workspace(self):
        compiler = self._make_compiler()
        content, refs = compiler._workspace_section(
            workspace_root=None, active_paths=[],
        )
        assert content == ""
