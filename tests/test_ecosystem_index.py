"""Tests for dharma_swarm.ecosystem_index -- EcosystemIndex FTS5 search."""

import time
from pathlib import Path

import pytest

from dharma_swarm.ecosystem_index import EcosystemIndex, DOMAINS, _extract_top_terms


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    """Return a fresh temporary path for the SQLite index database."""
    return tmp_path / "db" / "ecosystem_index.db"


@pytest.fixture
def index(db_file: Path) -> EcosystemIndex:
    """Return an EcosystemIndex pointed at the temporary DB."""
    return EcosystemIndex(db_path=db_file)


def _create_domain_tree(tmp_path: Path, domain_name: str, files: dict[str, str]) -> Path:
    """Create a domain directory with the given files and return the base path.

    Args:
        tmp_path: Pytest tmp_path root.
        domain_name: Subdirectory name for this domain.
        files: Mapping of relative filename to content.

    Returns:
        The base directory path.
    """
    base = tmp_path / domain_name
    base.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        fpath = base / name
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
    return base


# ---------------------------------------------------------------------------
# test_build_indexes_files
# ---------------------------------------------------------------------------


def test_build_indexes_files(tmp_path: Path, db_file: Path, monkeypatch: pytest.MonkeyPatch):
    """Create a tmp dir with .py and .md files, build index, verify correct counts."""
    base = _create_domain_tree(tmp_path, "test_domain", {
        "alpha.py": "def compute_rv(): pass  # R_V contraction metric",
        "beta.py": "class SwarmManager: pass  # orchestration core",
        "readme.md": "# Notes\nSome documentation about activation patching.",
    })

    monkeypatch.setitem(DOMAINS, "test_domain", {
        "base": base,
        "extensions": {".py", ".md"},
    })

    idx = EcosystemIndex(db_path=db_file)
    counts = idx.build(domains=["test_domain"])

    assert counts["test_domain"] == 3
    st = idx.stats()
    assert st["test_domain"] == 3


# ---------------------------------------------------------------------------
# test_search_returns_results
# ---------------------------------------------------------------------------


def test_search_returns_results(tmp_path: Path, db_file: Path, monkeypatch: pytest.MonkeyPatch):
    """Build index with known content, search for a keyword, verify it's found."""
    base = _create_domain_tree(tmp_path, "search_dom", {
        "metrics.py": "participation_ratio = compute_pr(values)\n# contraction measurement",
        "util.py": "import os\nprint('hello world')",
    })

    monkeypatch.setitem(DOMAINS, "search_dom", {
        "base": base,
        "extensions": {".py"},
    })

    idx = EcosystemIndex(db_path=db_file)
    idx.build(domains=["search_dom"])

    results = idx.search("participation_ratio")
    assert len(results) >= 1
    assert any("metrics" in r["path"] for r in results)


# ---------------------------------------------------------------------------
# test_search_filters_by_domain
# ---------------------------------------------------------------------------


def test_search_filters_by_domain(
    tmp_path: Path, db_file: Path, monkeypatch: pytest.MonkeyPatch
):
    """Build with multiple domains, verify domain filtering works."""
    base_a = _create_domain_tree(tmp_path, "dom_a", {
        "contraction.py": "R_V contraction is the key measurement for layer 27",
    })
    base_b = _create_domain_tree(tmp_path, "dom_b", {
        "contraction.md": "R_V contraction also appears in phenomenological reports",
    })

    monkeypatch.setitem(DOMAINS, "dom_a", {"base": base_a, "extensions": {".py"}})
    monkeypatch.setitem(DOMAINS, "dom_b", {"base": base_b, "extensions": {".md"}})

    idx = EcosystemIndex(db_path=db_file)
    idx.build(domains=["dom_a", "dom_b"])

    # Search only dom_a
    results_a = idx.search("contraction", domains=["dom_a"])
    assert all(r["domain"] == "dom_a" for r in results_a)

    # Search only dom_b
    results_b = idx.search("contraction", domains=["dom_b"])
    assert all(r["domain"] == "dom_b" for r in results_b)


# ---------------------------------------------------------------------------
# test_incremental_indexing
# ---------------------------------------------------------------------------


def test_incremental_indexing(
    tmp_path: Path, db_file: Path, monkeypatch: pytest.MonkeyPatch
):
    """Build once, modify a file, rebuild, verify only changed file re-indexed."""
    base = _create_domain_tree(tmp_path, "incr", {
        "stable.py": "# This file will not change",
        "mutable.py": "# Original content version one",
    })

    monkeypatch.setitem(DOMAINS, "incr", {"base": base, "extensions": {".py"}})

    idx = EcosystemIndex(db_path=db_file)
    counts_first = idx.build(domains=["incr"])
    assert counts_first["incr"] == 2

    # Second build without changes -- should index 0 files
    counts_noop = idx.build(domains=["incr"])
    assert counts_noop["incr"] == 0

    # Modify mutable.py (must also advance mtime)
    mutable = base / "mutable.py"
    time.sleep(0.05)  # ensure mtime changes on filesystems with coarse granularity
    mutable.write_text("# Updated content version two", encoding="utf-8")

    counts_incr = idx.build(domains=["incr"])
    assert counts_incr["incr"] == 1  # only the changed file re-indexed


# ---------------------------------------------------------------------------
# test_related_finds_similar
# ---------------------------------------------------------------------------


def test_related_finds_similar(
    tmp_path: Path, db_file: Path, monkeypatch: pytest.MonkeyPatch
):
    """Index files with overlapping keywords, verify related() returns them."""
    base = _create_domain_tree(tmp_path, "rel_dom", {
        "metrics.py": (
            "participation_ratio contraction measurement "
            "geometric signature value space collapse\n" * 5
        ),
        "bridge.py": (
            "participation_ratio behavioral transfer "
            "geometric contraction layer analysis\n" * 5
        ),
        "unrelated.py": "import json\nprint('completely different content')\n" * 5,
    })

    monkeypatch.setitem(DOMAINS, "rel_dom", {"base": base, "extensions": {".py"}})

    idx = EcosystemIndex(db_path=db_file)
    idx.build(domains=["rel_dom"])

    # Ask for files related to metrics.py
    results = idx.related(str(base / "metrics.py"))
    paths = [r["path"] for r in results]
    # bridge.py shares keywords, should appear
    assert any("bridge" in p for p in paths)


# ---------------------------------------------------------------------------
# test_rebuild_clears_old
# ---------------------------------------------------------------------------


def test_rebuild_clears_old(
    tmp_path: Path, db_file: Path, monkeypatch: pytest.MonkeyPatch
):
    """Build, rebuild, verify fresh counts after full wipe."""
    base = _create_domain_tree(tmp_path, "reb_dom", {
        "one.py": "first file content for rebuild test",
        "two.py": "second file content for rebuild test",
    })

    monkeypatch.setitem(DOMAINS, "reb_dom", {"base": base, "extensions": {".py"}})

    # Clear all other domains so rebuild only touches reb_dom
    real_domains = dict(DOMAINS)
    for k in list(DOMAINS):
        if k != "reb_dom":
            monkeypatch.setitem(DOMAINS, k, {"base": tmp_path / "nonexistent", "extensions": set()})

    idx = EcosystemIndex(db_path=db_file)
    idx.build(domains=["reb_dom"])
    assert idx.stats().get("reb_dom") == 2

    # Rebuild should wipe and re-index
    counts = idx.rebuild()
    assert counts.get("reb_dom", 0) == 2
    assert idx.stats().get("reb_dom") == 2


# ---------------------------------------------------------------------------
# test_missing_directory_handled
# ---------------------------------------------------------------------------


def test_missing_directory_handled(
    tmp_path: Path, db_file: Path, monkeypatch: pytest.MonkeyPatch
):
    """Build with non-existent domain dir -- no crash."""
    monkeypatch.setitem(DOMAINS, "ghost", {
        "base": tmp_path / "does_not_exist",
        "extensions": {".py"},
    })

    idx = EcosystemIndex(db_path=db_file)
    counts = idx.build(domains=["ghost"])
    assert counts["ghost"] == 0


# ---------------------------------------------------------------------------
# test_stats_returns_domain_counts
# ---------------------------------------------------------------------------


def test_stats_returns_domain_counts(
    tmp_path: Path, db_file: Path, monkeypatch: pytest.MonkeyPatch
):
    """Verify stats() returns correct per-domain document counts."""
    base_x = _create_domain_tree(tmp_path, "dom_x", {
        "a.py": "content a", "b.py": "content b",
    })
    base_y = _create_domain_tree(tmp_path, "dom_y", {
        "c.md": "content c",
    })

    monkeypatch.setitem(DOMAINS, "dom_x", {"base": base_x, "extensions": {".py"}})
    monkeypatch.setitem(DOMAINS, "dom_y", {"base": base_y, "extensions": {".md"}})

    idx = EcosystemIndex(db_path=db_file)
    idx.build(domains=["dom_x", "dom_y"])

    st = idx.stats()
    assert st["dom_x"] == 2
    assert st["dom_y"] == 1


# ---------------------------------------------------------------------------
# _extract_top_terms unit tests
# ---------------------------------------------------------------------------


def test_extract_top_terms_filters_stopwords():
    """Verify common stopwords are excluded from term extraction."""
    text = "the and for that this with from are was were been have has had"
    terms = _extract_top_terms(text)
    assert len(terms) == 0


def test_extract_top_terms_finds_meaningful():
    """Verify meaningful terms are extracted."""
    text = "participation contraction geometric measurement " * 10
    terms = _extract_top_terms(text, n=5)
    assert "participation" in terms
    assert "contraction" in terms
