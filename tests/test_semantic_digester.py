"""Tests for semantic_digester.py — deep reading of source files into ConceptGraph."""

from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.semantic_digester import (
    CATEGORY_KEYWORDS,
    CLAIM_INDICATORS,
    CLAIM_RE,
    FORMAL_PATTERNS,
    SKIP_DIRS,
    SemanticDigester,
    _build_formal_edges,
    _build_import_edges,
    _build_reference_edges,
    _classify_category,
    _coerce_frontmatter_value,
    _compute_salience,
    _detect_formal_structures,
    _extract_claims,
    _extract_markdown_concepts,
    _extract_note_links,
    _extract_python_concepts,
    _extract_python_imports,
    _normalize_note_link_value,
    _semantic_density,
    _should_skip,
    _split_frontmatter,
)
from dharma_swarm.metrics import BehavioralSignature


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_formal_patterns_exist(self):
        assert len(FORMAL_PATTERNS) >= 10

    def test_formal_patterns_are_tuples(self):
        for pattern, label in FORMAL_PATTERNS:
            assert isinstance(pattern, str)
            assert isinstance(label, str)

    def test_claim_indicators_exist(self):
        assert len(CLAIM_INDICATORS) >= 3

    def test_category_keywords_has_keys(self):
        expected = {"mathematical", "philosophical", "measurement", "engineering", "coordination"}
        assert expected <= set(CATEGORY_KEYWORDS.keys())

    def test_skip_dirs(self):
        assert ".git" in SKIP_DIRS
        assert "__pycache__" in SKIP_DIRS


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------


class TestCoerceFrontmatterValue:
    def test_bool_true(self):
        assert _coerce_frontmatter_value("true") is True

    def test_bool_false(self):
        assert _coerce_frontmatter_value("false") is False

    def test_null(self):
        assert _coerce_frontmatter_value("null") is None

    def test_none(self):
        assert _coerce_frontmatter_value("none") is None

    def test_integer(self):
        assert _coerce_frontmatter_value("42") == 42

    def test_float(self):
        assert _coerce_frontmatter_value("3.14") == 3.14

    def test_string(self):
        assert _coerce_frontmatter_value("hello world") == "hello world"

    def test_quoted_string(self):
        assert _coerce_frontmatter_value('"hello"') == "hello"

    def test_list(self):
        result = _coerce_frontmatter_value("[a, b, c]")
        assert result == ["a", "b", "c"]

    def test_empty_list(self):
        assert _coerce_frontmatter_value("[]") == []

    def test_whitespace_stripped(self):
        assert _coerce_frontmatter_value("  42  ") == 42


class TestSplitFrontmatter:
    def test_no_frontmatter(self):
        meta, body = _split_frontmatter("Just some text.")
        assert meta == {}
        assert body == "Just some text."

    def test_with_frontmatter(self):
        text = "---\ntitle: Hello\ntags: [a, b]\n---\nBody text."
        meta, body = _split_frontmatter(text)
        assert meta["title"] == "Hello"
        assert isinstance(meta["tags"], list)
        assert body.strip() == "Body text."

    def test_unclosed_frontmatter(self):
        text = "---\ntitle: Hello\nno closing"
        meta, body = _split_frontmatter(text)
        assert meta == {}

    def test_empty_frontmatter(self):
        text = "---\n---\nBody."
        meta, body = _split_frontmatter(text)
        assert meta == {}
        # Empty frontmatter with no content between delimiters
        assert "Body." in body


# ---------------------------------------------------------------------------
# Note links
# ---------------------------------------------------------------------------


class TestNormalizeNoteLink:
    def test_plain(self):
        assert _normalize_note_link_value("hello") == "hello"

    def test_with_pipe(self):
        assert _normalize_note_link_value("page|display") == "page"

    def test_with_hash(self):
        assert _normalize_note_link_value("page#section") == "page"

    def test_empty(self):
        assert _normalize_note_link_value("") == ""

    def test_whitespace(self):
        assert _normalize_note_link_value("  hello  ") == "hello"


class TestExtractNoteLinks:
    def test_wikilinks(self):
        content = "See [[PageA]] and [[PageB]]."
        links = _extract_note_links(content)
        assert "PageA" in links
        assert "PageB" in links

    def test_markdown_links(self):
        content = "Check [link](./other.md)."
        links = _extract_note_links(content)
        assert "./other.md" in links

    def test_frontmatter_links(self):
        content = "---\nrelated: [foo, bar]\n---\nBody."
        links = _extract_note_links(content)
        assert "foo" in links
        assert "bar" in links


# ---------------------------------------------------------------------------
# Formal structure detection
# ---------------------------------------------------------------------------


class TestDetectFormalStructures:
    def test_finds_monad(self):
        result = _detect_formal_structures("This implements a monad pattern.")
        assert "monad" in result

    def test_finds_multiple(self):
        result = _detect_formal_structures("The coalgebra extends the sheaf cohomology.")
        assert "coalgebra" in result
        assert "sheaf" in result
        assert "cohomology" in result

    def test_no_matches(self):
        result = _detect_formal_structures("Just a simple hello world program.")
        assert result == []

    def test_case_insensitive(self):
        result = _detect_formal_structures("MONAD and Functor")
        assert "monad" in result
        assert "functor" in result


# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------


class TestExtractClaims:
    def test_finds_must_claim(self):
        text = "The system must maintain consistency at all times."
        claims = _extract_claims(text)
        assert len(claims) >= 1

    def test_finds_invariant_claim(self):
        text = "This invariant guarantees safety under concurrent access."
        claims = _extract_claims(text)
        assert len(claims) >= 1

    def test_caps_at_ten(self):
        text = ". ".join(
            f"Claim {i}: the system must ensure property {i} holds" for i in range(20)
        )
        claims = _extract_claims(text)
        assert len(claims) <= 10

    def test_empty_text(self):
        assert _extract_claims("") == []


# ---------------------------------------------------------------------------
# Category classification
# ---------------------------------------------------------------------------


class TestClassifyCategory:
    def test_mathematical(self):
        assert _classify_category("monad coalgebra functor category morphism") == "mathematical"

    def test_engineering(self):
        assert _classify_category("pipeline runtime daemon cli api provider config") == "engineering"

    def test_coordination(self):
        assert _classify_category("swarm agent orchestration stigmergy pheromone task") == "coordination"

    def test_default_engineering(self):
        assert _classify_category("xyz abc nothing special") == "engineering"


# ---------------------------------------------------------------------------
# Salience and density
# ---------------------------------------------------------------------------


class TestComputeSalience:
    def test_empty_text(self):
        sig = BehavioralSignature()
        result = _compute_salience("", [], [], sig)
        assert 0.0 <= result <= 1.0

    def test_rich_text_higher(self):
        sig = BehavioralSignature(entropy=0.8, complexity=0.6)
        low = _compute_salience("short", [], [], BehavioralSignature())
        high = _compute_salience(
            "A long text with many words " * 20,
            ["monad", "coalgebra"],
            ["This must hold invariant."],
            sig,
        )
        assert high > low

    def test_clamped(self):
        sig = BehavioralSignature(entropy=1.0, complexity=1.0)
        result = _compute_salience("x " * 500, ["a"] * 20, ["c"] * 20, sig)
        assert result <= 1.0


class TestSemanticDensity:
    def test_basic(self):
        result = _semantic_density("hello world testing code example", 1)
        assert result > 0

    def test_zero_lines(self):
        assert _semantic_density("some text", 0) == 0.0

    def test_filters_short_words(self):
        # "a", "is", "the" are < 4 chars, filtered out
        result = _semantic_density("a is the", 1)
        assert result == 0.0


# ---------------------------------------------------------------------------
# Should skip
# ---------------------------------------------------------------------------


class TestShouldSkip:
    def test_skip_git(self):
        assert _should_skip(Path(".git/config"))

    def test_skip_pycache(self):
        assert _should_skip(Path("src/__pycache__/mod.pyc"))

    def test_skip_dotdir(self):
        assert _should_skip(Path(".hidden/file.py"))

    def test_allow_normal(self):
        assert not _should_skip(Path("src/module.py"))


# ---------------------------------------------------------------------------
# Python extraction
# ---------------------------------------------------------------------------


class TestExtractPythonConcepts:
    def test_extracts_module_doc(self):
        source = '"""Module docstring with enough text to be meaningful."""\n\nclass Foo:\n    pass\n'
        nodes = _extract_python_concepts(source, "test.py")
        # Should have at least module concept + Foo class
        names = [n.name for n in nodes]
        assert "test" in names  # module-level
        assert "Foo" in names

    def test_skips_private(self):
        source = 'def _helper():\n    pass\n\ndef public():\n    pass\n'
        nodes = _extract_python_concepts(source, "m.py")
        names = [n.name for n in nodes]
        assert "_helper" not in names
        assert "public" in names

    def test_syntax_error_returns_empty(self):
        nodes = _extract_python_concepts("def broken(:", "bad.py")
        assert nodes == []

    def test_class_higher_salience_than_function(self):
        source = (
            'class MyClass:\n    """A class."""\n    pass\n\n'
            'def my_func():\n    """A function."""\n    pass\n'
        )
        nodes = _extract_python_concepts(source, "m.py")
        cls_node = [n for n in nodes if n.name == "MyClass"][0]
        fn_node = [n for n in nodes if n.name == "my_func"][0]
        assert cls_node.salience >= fn_node.salience


class TestExtractPythonImports:
    def test_import_statement(self):
        source = "import os\nimport sys\n"
        imports = _extract_python_imports(source)
        assert "os" in imports
        assert "sys" in imports

    def test_from_import(self):
        source = "from pathlib import Path\nfrom os.path import join\n"
        imports = _extract_python_imports(source)
        assert "pathlib" in imports
        assert "os.path" in imports

    def test_syntax_error(self):
        assert _extract_python_imports("def broken(:") == []


# ---------------------------------------------------------------------------
# Markdown extraction
# ---------------------------------------------------------------------------


class TestExtractMarkdownConcepts:
    def test_extracts_title(self):
        content = "# Main Title\n\nSome body text with enough content to be meaningful here.\n"
        nodes = _extract_markdown_concepts(content, "readme.md")
        assert len(nodes) >= 1

    def test_extracts_headers(self):
        content = (
            "# Top\n\nIntro paragraph with sufficient detail.\n\n"
            "## Section A\n\nSection A has detailed content about a specific topic.\n\n"
            "## Section B\n\nSection B has detailed content about another topic.\n"
        )
        nodes = _extract_markdown_concepts(content, "doc.md")
        names = [n.name for n in nodes]
        assert "Section A" in names
        assert "Section B" in names

    def test_extracts_bold_terms(self):
        content = "# Title\n\nThe **Requisite Variety** principle states that governance must match threat variety.\n"
        nodes = _extract_markdown_concepts(content, "doc.md")
        names = [n.name for n in nodes]
        assert "Requisite Variety" in names

    def test_frontmatter_title(self):
        content = "---\ntitle: Custom Title\n---\n\nBody text with some real content.\n"
        nodes = _extract_markdown_concepts(content, "note.md")
        assert any(n.name == "Custom Title" for n in nodes)


# ---------------------------------------------------------------------------
# Edge building
# ---------------------------------------------------------------------------


class TestBuildImportEdges:
    def test_creates_import_edge(self):
        from dharma_swarm.semantic_gravity import ConceptNode

        # _build_import_edges uses Path(file_path).stem to map — so file
        # stems must match imported module names.
        node_a = ConceptNode(name="alpha", definition="Module A", source_file="alpha.py")
        node_b = ConceptNode(name="beta", definition="Module B", source_file="beta.py")

        nodes_by_file = {"alpha.py": [node_a], "beta.py": [node_b]}
        # alpha imports "beta"
        file_imports = {"alpha.py": ["beta"]}

        edges = _build_import_edges(nodes_by_file, file_imports)
        assert len(edges) >= 1
        assert edges[0].source_id == node_a.id
        assert edges[0].target_id == node_b.id

    def test_no_self_edge(self):
        from dharma_swarm.semantic_gravity import ConceptNode

        node_a = ConceptNode(name="alpha", definition="Module A", source_file="alpha.py")
        nodes_by_file = {"alpha.py": [node_a]}
        file_imports = {"alpha.py": ["alpha"]}

        edges = _build_import_edges(nodes_by_file, file_imports)
        assert len(edges) == 0


class TestBuildReferenceEdges:
    def test_creates_reference_when_mentioned(self):
        from dharma_swarm.semantic_gravity import ConceptNode

        node_a = ConceptNode(name="stigmergy", definition="A coordination mechanism for swarm agents")
        node_b = ConceptNode(name="swarm_coordinator", definition="Uses stigmergy marks for task routing")

        edges = _build_reference_edges([node_a, node_b])
        assert len(edges) >= 1


class TestBuildFormalEdges:
    def test_shared_formal_structure(self):
        from dharma_swarm.semantic_gravity import ConceptNode

        node_a = ConceptNode(name="A", definition="x", formal_structures=["monad"])
        node_b = ConceptNode(name="B", definition="y", formal_structures=["monad"])

        edges = _build_formal_edges([node_a, node_b])
        assert len(edges) == 1
        assert "monad" in edges[0].evidence


# ---------------------------------------------------------------------------
# SemanticDigester
# ---------------------------------------------------------------------------


class TestSemanticDigester:
    def test_digest_python_file(self):
        digester = SemanticDigester()
        source = '"""A test module for digester verification."""\n\nclass Widget:\n    """A widget that does things."""\n    pass\n'
        nodes = digester.digest_file(source, "widget.py", suffix=".py")
        assert len(nodes) >= 1
        names = [n.name for n in nodes]
        assert "Widget" in names

    def test_digest_markdown_file(self):
        digester = SemanticDigester()
        content = "# Architecture\n\nThe system uses **Strange Loops** for self-reference.\n"
        nodes = digester.digest_file(content, "arch.md", suffix=".md")
        assert len(nodes) >= 1

    def test_digest_text_file(self):
        digester = SemanticDigester()
        content = "This is a plain text research note about coalgebra and categorical structures.\n"
        nodes = digester.digest_file(content, "notes.txt", suffix=".txt")
        assert len(nodes) == 1
        assert "coalgebra" in nodes[0].formal_structures

    def test_digest_unknown_suffix(self):
        digester = SemanticDigester()
        nodes = digester.digest_file("data", "file.csv", suffix=".csv")
        assert nodes == []

    def test_digest_text(self):
        digester = SemanticDigester()
        node = digester.digest_text(
            "The monad pattern ensures compositional safety in the pipeline.",
            "monad_safety",
        )
        assert node.name == "monad_safety"
        assert "monad" in node.formal_structures

    def test_digest_directory(self, tmp_path):
        # Create a small directory with py and md files
        (tmp_path / "module.py").write_text(
            '"""A module about entropy and coordination."""\n\n'
            'class Coordinator:\n    """Coordinates agents."""\n    pass\n'
        )
        (tmp_path / "notes.md").write_text(
            "# Design Notes\n\nThis uses **stigmergy** for indirect coordination.\n"
        )
        (tmp_path / "data.csv").write_text("a,b,c\n1,2,3\n")  # should be skipped

        digester = SemanticDigester()
        graph = digester.digest_directory(tmp_path)

        assert graph.node_count >= 2
        assert graph.edge_count >= 0  # may have reference edges

    def test_digest_directory_under_dot_prefixed_ancestor(self, tmp_path):
        scan_root = tmp_path / ".worktrees" / "scan-root"
        scan_root.mkdir(parents=True)
        (scan_root / "module.py").write_text(
            '"""A module about entropy and coordination."""\n\n'
            'class Coordinator:\n    """Coordinates agents."""\n    pass\n'
        )

        digester = SemanticDigester()
        graph = digester.digest_directory(scan_root)

        assert graph.node_count >= 1
