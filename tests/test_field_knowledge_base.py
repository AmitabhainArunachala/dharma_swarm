"""Tests for field_knowledge_base.py — AI field intelligence knowledge base."""

from __future__ import annotations

import pytest

from dharma_swarm.field_knowledge_base import (
    ALL_FIELD_ENTRIES,
    FIELD_DOMAINS,
    dgc_competitors,
    dgc_gaps,
    dgc_unique,
    entries_by_field,
    entries_by_relation,
    field_summary,
)


# ---------------------------------------------------------------------------
# Data integrity
# ---------------------------------------------------------------------------


class TestDataIntegrity:
    def test_has_entries(self):
        assert len(ALL_FIELD_ENTRIES) >= 30

    def test_all_entries_have_required_keys(self):
        required = {"id", "source", "field", "type", "summary", "relation", "dgc_mapping"}
        for entry in ALL_FIELD_ENTRIES:
            missing = required - set(entry.keys())
            assert not missing, f"Entry '{entry.get('id', '?')}' missing keys: {missing}"

    def test_ids_unique(self):
        ids = [e["id"] for e in ALL_FIELD_ENTRIES]
        dupes = [i for i in ids if ids.count(i) > 1]
        assert not dupes, f"Duplicate IDs: {set(dupes)}"

    def test_valid_relations(self):
        valid = {"validates", "competes", "extends", "orthogonal", "gap", "unique", "supersedes"}
        for entry in ALL_FIELD_ENTRIES:
            assert entry["relation"] in valid, (
                f"Invalid relation '{entry['relation']}' for {entry['id']}"
            )

    def test_valid_types(self):
        valid = {"paper", "tool", "framework", "platform", "benchmark",
                 "protocol", "survey", "concept", "company", "dgc_internal"}
        for entry in ALL_FIELD_ENTRIES:
            assert entry["type"] in valid, (
                f"Invalid type '{entry['type']}' for {entry['id']}"
            )

    def test_dgc_mapping_is_list(self):
        for entry in ALL_FIELD_ENTRIES:
            assert isinstance(entry["dgc_mapping"], list), (
                f"dgc_mapping should be list for {entry['id']}"
            )

    def test_summary_not_empty(self):
        for entry in ALL_FIELD_ENTRIES:
            assert len(entry["summary"]) > 20, (
                f"Summary too short for {entry['id']}"
            )


# ---------------------------------------------------------------------------
# FIELD_DOMAINS
# ---------------------------------------------------------------------------


class TestFieldDomains:
    def test_has_domains(self):
        assert len(FIELD_DOMAINS) >= 6

    def test_all_entries_accounted_for(self):
        """FIELD_DOMAINS should cover all entries in ALL_FIELD_ENTRIES."""
        domain_total = sum(len(v) for v in FIELD_DOMAINS.values())
        assert domain_total == len(ALL_FIELD_ENTRIES)

    def test_expected_domains(self):
        expected = {
            "mech_interp", "self_evolving", "agentic_platforms",
            "multi_agent", "alignment_safety", "bootstrapping",
        }
        assert expected <= set(FIELD_DOMAINS.keys())


# ---------------------------------------------------------------------------
# Query functions
# ---------------------------------------------------------------------------


class TestEntryQueries:
    def test_entries_by_relation(self):
        extends = entries_by_relation("extends")
        assert all(e["relation"] == "extends" for e in extends)

    def test_entries_by_relation_empty(self):
        result = entries_by_relation("supersedes")
        # May or may not have entries, but shouldn't crash
        assert isinstance(result, list)

    def test_entries_by_field(self):
        mi = entries_by_field("mechanistic interpretability")
        assert len(mi) > 0
        assert all(e["field"] == "mechanistic interpretability" for e in mi)

    def test_entries_by_field_empty(self):
        result = entries_by_field("nonexistent_field")
        assert result == []

    def test_dgc_unique(self):
        unique = dgc_unique()
        assert all(e["relation"] == "unique" for e in unique)

    def test_dgc_gaps(self):
        gaps = dgc_gaps()
        assert all(e["relation"] == "gap" for e in gaps)

    def test_dgc_competitors(self):
        competitors = dgc_competitors()
        assert all(e["relation"] == "competes" for e in competitors)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


class TestFieldSummary:
    def test_summary_structure(self):
        s = field_summary()
        assert "total_entries" in s
        assert "by_relation" in s
        assert "by_field" in s
        assert "by_type" in s
        assert "dgc_unique" in s
        assert "dgc_gaps" in s
        assert "dgc_competitors" in s

    def test_summary_counts_match(self):
        s = field_summary()
        assert s["total_entries"] == len(ALL_FIELD_ENTRIES)
        assert sum(s["by_relation"].values()) == s["total_entries"]
        assert sum(s["by_field"].values()) == s["total_entries"]
        assert sum(s["by_type"].values()) == s["total_entries"]

    def test_dgc_unique_count_matches(self):
        s = field_summary()
        assert s["dgc_unique"] == len(dgc_unique())

    def test_dgc_gaps_count_matches(self):
        s = field_summary()
        assert s["dgc_gaps"] == len(dgc_gaps())
