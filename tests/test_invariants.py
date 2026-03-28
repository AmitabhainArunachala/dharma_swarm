"""Tests for the four computable invariants."""

import numpy as np
import pytest

from dharma_swarm.invariants import (
    InvariantSnapshot,
    compute_closure,
    compute_criticality,
    compute_diversity_equilibrium,
    compute_info_retention,
    snapshot,
)


class TestCriticality:
    def test_empty_matrix_is_subcritical(self):
        val, status = compute_criticality(np.zeros((0, 0)))
        assert status == "subcritical"
        assert val == 0.0

    def test_identity_is_healthy(self):
        # Identity matrix has eigenvalue 1.0 — right in the healthy band
        val, status = compute_criticality(np.eye(3))
        assert status == "healthy"
        assert abs(val - 1.0) < 0.01

    def test_zero_matrix_is_subcritical(self):
        val, status = compute_criticality(np.zeros((3, 3)))
        assert status == "subcritical"
        assert val == 0.0

    def test_large_weights_are_supercritical(self):
        # All edges with weight 2.0 → eigenvalues > 1.1
        mat = np.ones((3, 3)) * 2.0
        np.fill_diagonal(mat, 0.0)
        val, status = compute_criticality(mat)
        assert status == "supercritical"
        assert val > 1.1


class TestClosure:
    def test_full_closure(self):
        val, status = compute_closure(total_nodes=4, autocatalytic_node_count=4)
        assert val == 1.0
        assert status == "healthy"

    def test_no_closure(self):
        val, status = compute_closure(total_nodes=4, autocatalytic_node_count=0)
        assert val == 0.0
        assert status == "critical"

    def test_partial_closure(self):
        val, status = compute_closure(total_nodes=4, autocatalytic_node_count=2)
        assert val == 0.5
        assert status == "degraded"

    def test_empty_graph(self):
        val, status = compute_closure(total_nodes=0, autocatalytic_node_count=0)
        assert status == "subcritical"


class TestInfoRetention:
    def test_low_mutation_is_healthy(self):
        val, status = compute_info_retention(
            mutation_rate=0.001,
            selective_advantage=0.1,
            genome_length=10,
        )
        # threshold = 0.1/10 = 0.01, margin = 0.01 - 0.001 = 0.009
        assert status == "healthy"
        assert val > 0

    def test_high_mutation_is_critical(self):
        val, status = compute_info_retention(
            mutation_rate=0.5,
            selective_advantage=0.1,
            genome_length=10,
        )
        assert status == "critical"
        assert val < 0

    def test_zero_genome_is_unknown(self):
        val, status = compute_info_retention(0.01, 0.1, 0)
        assert status == "unknown"


class TestDiversityEquilibrium:
    def test_high_coverage_is_healthy(self):
        val, status = compute_diversity_equilibrium(coverage=0.7)
        assert status == "healthy"

    def test_low_coverage_is_critical(self):
        val, status = compute_diversity_equilibrium(coverage=0.05)
        assert status == "critical"

    def test_kv_diversity_overrides_coverage(self):
        val, status = compute_diversity_equilibrium(coverage=0.1, kv_diversity=0.8)
        assert status == "healthy"
        assert val == 0.8


class TestSnapshot:
    def test_snapshot_returns_all_fields(self):
        snap = snapshot()
        assert isinstance(snap, InvariantSnapshot)
        assert snap.timestamp != ""
        assert snap.overall in ("healthy", "degraded", "critical", "subcritical", "supercritical", "unknown")

    def test_worst_status_propagates(self):
        # Force one invariant to be critical via zero nodes
        snap = snapshot(total_nodes=0, archive_coverage=0.01)
        assert snap.overall in ("critical", "subcritical")

    def test_all_healthy(self):
        snap = snapshot(
            adjacency_matrix=np.eye(3),
            total_nodes=3,
            autocatalytic_node_count=3,
            mutation_rate=0.001,
            selective_advantage=0.1,
            genome_length=10,
            archive_coverage=0.7,
        )
        assert snap.criticality_status == "healthy"
        assert snap.closure_status == "healthy"
        assert snap.info_retention_status == "healthy"
        assert snap.diversity_status == "healthy"
        assert snap.overall == "healthy"
