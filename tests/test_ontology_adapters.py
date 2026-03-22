"""Tests for dharma_swarm.ontology_adapters -- subsystem-to-ontology bridge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.ontology import OntologyRegistry
from dharma_swarm.ontology_adapters import (
    adapt_corpus,
    adapt_evolution,
    adapt_gates,
    adapt_identity,
    adapt_stigmergy,
    adapt_zeitgeist,
    register_hub_types,
    sync_all,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def registry() -> OntologyRegistry:
    """A fresh dharma registry with hub types registered."""
    reg = OntologyRegistry.create_dharma_registry()
    register_hub_types(reg)
    return reg


@pytest.fixture()
def dharma_tree(tmp_path: Path) -> Path:
    """Create a minimal ~/.dharma tree with sample JSONL data."""
    # Stigmergy marks
    stig_dir = tmp_path / "stigmergy"
    stig_dir.mkdir()
    marks = [
        {
            "id": "mark001",
            "agent": "coder-1",
            "file_path": "/src/ontology.py",
            "action": "write",
            "observation": "Refactored property validation",
            "salience": 0.7,
            "connections": ["/src/tests.py"],
            "access_count": 3,
            "timestamp": "2026-03-18T04:00:00+00:00",
        },
        {
            "id": "mark002",
            "agent": "reviewer-1",
            "file_path": "/src/models.py",
            "action": "read",
            "observation": "Checked type annotations",
            "salience": 0.5,
            "connections": [],
            "access_count": 1,
            "timestamp": "2026-03-18T04:10:00+00:00",
        },
    ]
    with open(stig_dir / "marks.jsonl", "w") as f:
        for m in marks:
            f.write(json.dumps(m) + "\n")

    # Zeitgeist signals
    meta_dir = tmp_path / "meta"
    meta_dir.mkdir()
    signals = [
        {
            "id": "sig001",
            "source": "local_scan",
            "category": "methodology",
            "title": "Keywords in shared_note.md",
            "relevance_score": 0.6,
            "keywords": ["mechanistic interpretability", "phase transition"],
            "description": "Found 2 research keywords",
            "timestamp": "2026-03-18T05:00:00+00:00",
        },
    ]
    with open(meta_dir / "zeitgeist.jsonl", "w") as f:
        for s in signals:
            f.write(json.dumps(s) + "\n")

    # Identity snapshots
    snapshots = [
        {
            "id": "snap001",
            "tcs": 0.72,
            "gpr": 0.8,
            "bsi": 0.65,
            "rm": 0.7,
            "regime": "stable",
            "correction_issued": False,
            "timestamp": "2026-03-18T04:30:00+00:00",
        },
        {
            "id": "snap002",
            "tcs": 0.35,
            "gpr": 0.3,
            "bsi": 0.4,
            "rm": 0.35,
            "regime": "drifting",
            "correction_issued": True,
            "timestamp": "2026-03-18T05:00:00+00:00",
        },
    ]
    with open(meta_dir / "identity_history.jsonl", "w") as f:
        for s in snapshots:
            f.write(json.dumps(s) + "\n")

    # Gate witness logs
    witness_dir = tmp_path / "witness"
    witness_dir.mkdir()
    gate_entries = [
        {
            "ts": "2026-03-18T04:00:00+00:00",
            "outcome": "PASS",
            "task_id": "task-001",
            "reason": "All gates clear",
        },
        {
            "ts": "2026-03-18T04:05:00+00:00",
            "outcome": "BLOCKED",
            "task_id": "task-002",
            "reason": "AHIMSA gate failed",
        },
    ]
    with open(witness_dir / "witness_20260318.jsonl", "w") as f:
        for e in gate_entries:
            f.write(json.dumps(e) + "\n")

    # Evolution archive
    evo_dir = tmp_path / "evolution"
    evo_dir.mkdir()
    evo_entries = [
        {
            "id": "evo001",
            "component": "dharma_swarm.ontology",
            "change_type": "mutation",
            "diff": "+added validation",
            "fitness": 0.85,
            "promotion_state": "promoted",
        },
    ]
    with open(evo_dir / "archive.jsonl", "w") as f:
        for e in evo_entries:
            f.write(json.dumps(e) + "\n")

    # Corpus claims (using DharmaCorpus default location)
    claims = [
        {
            "id": "DC-2026-0001",
            "statement": "Observer separation is non-negotiable",
            "category": "safety",
            "status": "accepted",
            "confidence": 0.95,
            "evidence_links": [
                {"type": "reasoning", "url_or_ref": "kernel axiom 1", "description": "Core axiom"}
            ],
            "created_by": "dhyana",
        },
        {
            "id": "DC-2026-0002",
            "statement": "All mutations require gate evaluation",
            "category": "operational",
            "status": "proposed",
            "confidence": 0.8,
            "evidence_links": [],
            "created_by": "system",
        },
    ]
    with open(tmp_path / "corpus.jsonl", "w") as f:
        for c in claims:
            f.write(json.dumps(c) + "\n")

    return tmp_path


# ---------------------------------------------------------------------------
# Type registration tests
# ---------------------------------------------------------------------------


class TestRegisterHubTypes:
    def test_registers_four_new_types(self, registry: OntologyRegistry) -> None:
        expected = {"StigmergyMark", "ZeitgeistSignal", "IdentitySnapshot", "CorpusClaim"}
        registered = set(registry.type_names())
        assert expected.issubset(registered)

    def test_idempotent_registration(self, registry: OntologyRegistry) -> None:
        count_before = len(registry.type_names())
        register_hub_types(registry)
        count_after = len(registry.type_names())
        assert count_before == count_after

    def test_stigmergy_has_left_by_link(self, registry: OntologyRegistry) -> None:
        links = registry.get_links_for("StigmergyMark")
        link_names = {ld.name for ld in links}
        assert "left_by" in link_names

    def test_corpus_has_authored_by_link(self, registry: OntologyRegistry) -> None:
        links = registry.get_links_for("CorpusClaim")
        link_names = {ld.name for ld in links}
        assert "authored_by" in link_names

    def test_zeitgeist_has_detected_in_link(self, registry: OntologyRegistry) -> None:
        links = registry.get_links_for("ZeitgeistSignal")
        link_names = {ld.name for ld in links}
        assert "detected_in" in link_names

    def test_identity_snapshot_properties(self, registry: OntologyRegistry) -> None:
        obj_type = registry.get_type("IdentitySnapshot")
        assert obj_type is not None
        props = obj_type.properties
        assert "tcs" in props
        assert "regime" in props
        assert props["regime"].property_type.value == "enum"
        assert "stable" in props["regime"].enum_values


# ---------------------------------------------------------------------------
# Individual adapter tests
# ---------------------------------------------------------------------------


class TestAdaptStigmergy:
    def test_reads_marks(self, dharma_tree: Path) -> None:
        results = adapt_stigmergy(base_path=dharma_tree)
        assert len(results) == 2

    def test_deterministic_ids(self, dharma_tree: Path) -> None:
        results = adapt_stigmergy(base_path=dharma_tree)
        ids = {obj.id for obj, _ in results}
        assert "stig_mark001" in ids
        assert "stig_mark002" in ids

    def test_properties_populated(self, dharma_tree: Path) -> None:
        results = adapt_stigmergy(base_path=dharma_tree)
        obj, _links = results[0]
        assert obj.properties["agent"] == "coder-1"
        assert obj.properties["salience"] == 0.7
        assert obj.properties["access_count"] == 3
        assert obj.type_name == "StigmergyMark"

    def test_left_by_link_created(self, dharma_tree: Path) -> None:
        results = adapt_stigmergy(base_path=dharma_tree)
        _, links = results[0]
        assert len(links) == 1
        assert links[0].link_name == "left_by"
        assert links[0].target_id == "agent_coder-1"

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        results = adapt_stigmergy(base_path=tmp_path)
        assert results == []

    def test_idempotent(self, dharma_tree: Path) -> None:
        r1 = adapt_stigmergy(base_path=dharma_tree)
        r2 = adapt_stigmergy(base_path=dharma_tree)
        ids1 = {obj.id for obj, _ in r1}
        ids2 = {obj.id for obj, _ in r2}
        assert ids1 == ids2


class TestAdaptZeitgeist:
    def test_reads_signals(self, dharma_tree: Path) -> None:
        results = adapt_zeitgeist(base_path=dharma_tree)
        assert len(results) == 1

    def test_deterministic_id(self, dharma_tree: Path) -> None:
        results = adapt_zeitgeist(base_path=dharma_tree)
        obj, _ = results[0]
        assert obj.id == "zeit_sig001"

    def test_properties_populated(self, dharma_tree: Path) -> None:
        results = adapt_zeitgeist(base_path=dharma_tree)
        obj, _ = results[0]
        assert obj.properties["category"] == "methodology"
        assert obj.properties["relevance_score"] == 0.6
        assert len(obj.properties["keywords"]) == 2

    def test_no_automatic_links(self, dharma_tree: Path) -> None:
        results = adapt_zeitgeist(base_path=dharma_tree)
        _, links = results[0]
        assert links == []


class TestAdaptIdentity:
    def test_reads_snapshots(self, dharma_tree: Path) -> None:
        results = adapt_identity(base_path=dharma_tree)
        assert len(results) == 2

    def test_deterministic_ids(self, dharma_tree: Path) -> None:
        results = adapt_identity(base_path=dharma_tree)
        ids = {obj.id for obj, _ in results}
        assert "ident_snap001" in ids
        assert "ident_snap002" in ids

    def test_regime_values(self, dharma_tree: Path) -> None:
        results = adapt_identity(base_path=dharma_tree)
        regimes = {obj.properties["regime"] for obj, _ in results}
        assert "stable" in regimes
        assert "drifting" in regimes


class TestAdaptGates:
    def test_reads_witness_entries(self, dharma_tree: Path) -> None:
        results = adapt_gates(base_path=dharma_tree)
        assert len(results) == 2

    def test_decision_normalization(self, dharma_tree: Path) -> None:
        results = adapt_gates(base_path=dharma_tree)
        decisions = {obj.properties["decision"] for obj, _ in results}
        assert "allow" in decisions
        assert "block" in decisions

    def test_missing_witness_dir_returns_empty(self, tmp_path: Path) -> None:
        results = adapt_gates(base_path=tmp_path)
        assert results == []


class TestAdaptEvolution:
    def test_reads_archive(self, dharma_tree: Path) -> None:
        results = adapt_evolution(base_path=dharma_tree)
        assert len(results) == 1

    def test_deterministic_id(self, dharma_tree: Path) -> None:
        results = adapt_evolution(base_path=dharma_tree)
        obj, _ = results[0]
        assert obj.id == "evo_evo001"

    def test_properties_populated(self, dharma_tree: Path) -> None:
        results = adapt_evolution(base_path=dharma_tree)
        obj, _ = results[0]
        assert obj.properties["component"] == "dharma_swarm.ontology"
        assert obj.properties["fitness"] == 0.85
        assert obj.properties["promotion_state"] == "promoted"


class TestAdaptCorpus:
    def test_reads_claims(self, dharma_tree: Path) -> None:
        results = adapt_corpus(base_path=dharma_tree)
        assert len(results) == 2

    def test_deterministic_ids(self, dharma_tree: Path) -> None:
        results = adapt_corpus(base_path=dharma_tree)
        ids = {obj.id for obj, _ in results}
        assert "claim_DC-2026-0001" in ids
        assert "claim_DC-2026-0002" in ids

    def test_claim_text_populated(self, dharma_tree: Path) -> None:
        results = adapt_corpus(base_path=dharma_tree)
        texts = {obj.properties["claim_text"] for obj, _ in results}
        assert "Observer separation is non-negotiable" in texts

    def test_authored_by_link_for_non_system(self, dharma_tree: Path) -> None:
        results = adapt_corpus(base_path=dharma_tree)
        # DC-2026-0001 created_by "dhyana" should have a link
        dhyana_results = [
            (obj, links) for obj, links in results
            if obj.id == "claim_DC-2026-0001"
        ]
        assert len(dhyana_results) == 1
        _, links = dhyana_results[0]
        assert len(links) == 1
        assert links[0].link_name == "authored_by"
        assert links[0].target_id == "agent_dhyana"

    def test_no_link_for_system_author(self, dharma_tree: Path) -> None:
        results = adapt_corpus(base_path=dharma_tree)
        system_results = [
            (obj, links) for obj, links in results
            if obj.id == "claim_DC-2026-0002"
        ]
        assert len(system_results) == 1
        _, links = system_results[0]
        assert links == []


# ---------------------------------------------------------------------------
# Fault tolerance tests
# ---------------------------------------------------------------------------


class TestFaultTolerance:
    def test_corrupt_jsonl_line_skipped(self, tmp_path: Path) -> None:
        """A corrupt JSON line should be skipped, not crash the adapter."""
        stig_dir = tmp_path / "stigmergy"
        stig_dir.mkdir()
        with open(stig_dir / "marks.jsonl", "w") as f:
            f.write(json.dumps({
                "id": "ok1",
                "agent": "a",
                "file_path": "/x",
                "observation": "good",
            }) + "\n")
            f.write("THIS IS NOT JSON\n")
            f.write(json.dumps({
                "id": "ok2",
                "agent": "b",
                "file_path": "/y",
                "observation": "also good",
            }) + "\n")
        results = adapt_stigmergy(base_path=tmp_path)
        assert len(results) == 2

    def test_empty_file_returns_empty(self, tmp_path: Path) -> None:
        stig_dir = tmp_path / "stigmergy"
        stig_dir.mkdir()
        (stig_dir / "marks.jsonl").write_text("")
        results = adapt_stigmergy(base_path=tmp_path)
        assert results == []

    def test_missing_id_field_skipped(self, tmp_path: Path) -> None:
        stig_dir = tmp_path / "stigmergy"
        stig_dir.mkdir()
        with open(stig_dir / "marks.jsonl", "w") as f:
            # No "id" field
            f.write(json.dumps({
                "agent": "a",
                "file_path": "/x",
                "observation": "no id",
            }) + "\n")
        results = adapt_stigmergy(base_path=tmp_path)
        assert results == []


# ---------------------------------------------------------------------------
# Sync-all tests
# ---------------------------------------------------------------------------


class TestSyncAll:
    def test_populates_registry(
        self, registry: OntologyRegistry, dharma_tree: Path
    ) -> None:
        counts = sync_all(registry, base_path=dharma_tree)
        assert counts["stigmergy"] == 2
        assert counts["zeitgeist"] == 1
        assert counts["identity"] == 2
        assert counts["gates"] == 2
        assert counts["evolution"] == 1
        assert counts["corpus"] == 2

    def test_idempotent_sync(
        self, registry: OntologyRegistry, dharma_tree: Path
    ) -> None:
        sync_all(registry, base_path=dharma_tree)
        counts2 = sync_all(registry, base_path=dharma_tree)
        # Second run should ingest zero because objects already exist
        for name, count in counts2.items():
            assert count == 0, f"Expected 0 for {name} on re-sync, got {count}"

    def test_objects_queryable_after_sync(
        self, registry: OntologyRegistry, dharma_tree: Path
    ) -> None:
        sync_all(registry, base_path=dharma_tree)
        marks = registry.get_objects_by_type("StigmergyMark")
        assert len(marks) == 2

        claims = registry.get_objects_by_type("CorpusClaim")
        assert len(claims) == 2

    def test_total_object_count(
        self, registry: OntologyRegistry, dharma_tree: Path
    ) -> None:
        sync_all(registry, base_path=dharma_tree)
        total = sum(
            len(registry.get_objects_by_type(t))
            for t in [
                "StigmergyMark",
                "ZeitgeistSignal",
                "IdentitySnapshot",
                "GateDecisionRecord",
                "EvolutionEntry",
                "CorpusClaim",
            ]
        )
        # 2 + 1 + 2 + 2 + 1 + 2 = 10
        assert total == 10

    def test_handles_empty_base_path(self, registry: OntologyRegistry, tmp_path: Path) -> None:
        """Sync on an empty directory should return all zeros, not crash."""
        counts = sync_all(registry, base_path=tmp_path)
        for _name, count in counts.items():
            assert count == 0
