"""Tests for GenomeInheritance -- child spec composition and provenance."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.agent_constitution import (
    AgentSpec,
    ConstitutionalLayer,
)
from dharma_swarm.genome_inheritance import GenomeInheritance, GenomeTemplate
from dharma_swarm.models import AgentRole, ProviderType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_parent_spec(name: str = "operator") -> AgentSpec:
    """Create a parent AgentSpec for testing."""
    return AgentSpec(
        name=name,
        role=AgentRole.OPERATOR,
        layer=ConstitutionalLayer.CORTEX,
        vsm_function="S2+S3 at swarm scale",
        domain="Orchestration, triage",
        system_prompt="You are the OPERATOR of dharma_swarm.",
        default_provider=ProviderType.OPENROUTER,
        default_model="llama-3.3-70b-instruct",
        backup_models=["deepseek-chat-v3"],
        constitutional_gates=["AHIMSA", "SATYA"],
        max_concurrent_workers=5,
        memory_namespace=name,
        spawn_authority=["triage_worker"],
        audit_cycle_seconds=0.0,
    )


def make_mock_kernel(*, valid: bool = True) -> MagicMock:
    """Create a mock DharmaKernel."""
    kernel = MagicMock()
    kernel.verify_integrity.return_value = valid
    kernel.compute_signature.return_value = "sha256_mock_signature_abc123"
    return kernel


# ---------------------------------------------------------------------------
# GenomeTemplate
# ---------------------------------------------------------------------------


class TestGenomeTemplate:
    def test_creation(self) -> None:
        g = GenomeTemplate(
            parent_name="operator",
            parent_generation=0,
            child_name="scanner_g1_20260322",
            child_generation=1,
            kernel_signature="abc123",
            inherited_gates=["AHIMSA", "SATYA"],
            system_prompt="child prompt",
            inherited_corpus_claims=[],
            inherited_memory_keys=["key1"],
            role_specialization="scanning",
            model="llama-3.3-70b",
            provider="openrouter",
            wake_interval_seconds=3600.0,
            spawn_authority=["worker"],
        )
        assert g.child_generation == 1
        assert g.kernel_signature == "abc123"
        assert g.parent_name == "operator"


# ---------------------------------------------------------------------------
# GenomeInheritance.compose_child_spec
# ---------------------------------------------------------------------------


class TestComposeChildSpec:
    @pytest.mark.asyncio
    async def test_basic(self, tmp_path: Path) -> None:
        gi = GenomeInheritance(state_dir=tmp_path)
        parent = make_parent_spec()
        kernel = make_mock_kernel()

        with patch.object(gi, "_filter_parent_memory", new_callable=AsyncMock, return_value=[]):
            child_spec, genome = await gi.compose_child_spec(
                parent_spec=parent,
                parent_generation=0,
                capability_gap="vulnerability scanning",
                proposed_role="scanner",
                proposed_spec_delta={},
                kernel=kernel,
            )

        assert isinstance(child_spec, AgentSpec)
        assert isinstance(genome, GenomeTemplate)
        assert "scanner" in child_spec.name
        assert genome.child_generation == 1

    @pytest.mark.asyncio
    async def test_child_inherits_kernel_signature(self, tmp_path: Path) -> None:
        gi = GenomeInheritance(state_dir=tmp_path)
        parent = make_parent_spec()
        kernel = make_mock_kernel()

        with patch.object(gi, "_filter_parent_memory", new_callable=AsyncMock, return_value=[]):
            _, genome = await gi.compose_child_spec(
                parent_spec=parent,
                parent_generation=0,
                capability_gap="monitoring",
                proposed_role="monitor",
                proposed_spec_delta={},
                kernel=kernel,
            )

        assert genome.kernel_signature == "sha256_mock_signature_abc123"

    @pytest.mark.asyncio
    async def test_child_gets_differentiated_prompt(self, tmp_path: Path) -> None:
        gi = GenomeInheritance(state_dir=tmp_path)
        parent = make_parent_spec()
        kernel = make_mock_kernel()

        with patch.object(gi, "_filter_parent_memory", new_callable=AsyncMock, return_value=[]):
            child_spec, _ = await gi.compose_child_spec(
                parent_spec=parent,
                parent_generation=0,
                capability_gap="deep analysis",
                proposed_role="analyst",
                proposed_spec_delta={"prompt_suffix": "Focus on metrics."},
                kernel=kernel,
            )

        # Child prompt contains parent prompt AND specialization
        assert "You are the OPERATOR" in child_spec.system_prompt
        assert "deep analysis" in child_spec.system_prompt
        assert "Focus on metrics." in child_spec.system_prompt
        assert "probation" in child_spec.system_prompt.lower()

    @pytest.mark.asyncio
    async def test_child_is_director_layer(self, tmp_path: Path) -> None:
        gi = GenomeInheritance(state_dir=tmp_path)
        parent = make_parent_spec()
        kernel = make_mock_kernel()

        with patch.object(gi, "_filter_parent_memory", new_callable=AsyncMock, return_value=[]):
            child_spec, _ = await gi.compose_child_spec(
                parent_spec=parent,
                parent_generation=0,
                capability_gap="testing",
                proposed_role="tester",
                proposed_spec_delta={},
                kernel=kernel,
            )

        assert child_spec.layer == ConstitutionalLayer.DIRECTOR

    @pytest.mark.asyncio
    async def test_genome_saved_to_disk(self, tmp_path: Path) -> None:
        gi = GenomeInheritance(state_dir=tmp_path)
        parent = make_parent_spec()
        kernel = make_mock_kernel()

        with patch.object(gi, "_filter_parent_memory", new_callable=AsyncMock, return_value=[]):
            child_spec, genome = await gi.compose_child_spec(
                parent_spec=parent,
                parent_generation=0,
                capability_gap="persistence",
                proposed_role="persister",
                proposed_spec_delta={},
                kernel=kernel,
            )

        genome_path = tmp_path / "replication" / "genomes" / f"{genome.child_name}.json"
        assert genome_path.exists()
        data = json.loads(genome_path.read_text(encoding="utf-8"))
        assert data["parent_name"] == "operator"
        assert data["kernel_signature"] == "sha256_mock_signature_abc123"

    @pytest.mark.asyncio
    async def test_kernel_integrity_failure(self, tmp_path: Path) -> None:
        gi = GenomeInheritance(state_dir=tmp_path)
        parent = make_parent_spec()
        bad_kernel = make_mock_kernel(valid=False)

        with pytest.raises(ValueError, match="Kernel integrity check failed"):
            await gi.compose_child_spec(
                parent_spec=parent,
                parent_generation=0,
                capability_gap="should fail",
                proposed_role="failer",
                proposed_spec_delta={},
                kernel=bad_kernel,
            )


# ---------------------------------------------------------------------------
# Name generation
# ---------------------------------------------------------------------------


class TestNameGeneration:
    def test_generate_name_format(self) -> None:
        gi = GenomeInheritance()
        name = gi._generate_name("Scanner Agent", 1)
        # Should be: scanner_agent_g1_YYYYMMDD
        assert re.match(r"^scanner_agent_g1_\d{8}$", name)

    def test_generate_name_sanitizes_special_chars(self) -> None:
        gi = GenomeInheritance()
        name = gi._generate_name("Caf!@#$% Worker!!", 2)
        # Non-alphanumeric chars become underscores, then collapsed
        assert "g2" in name
        assert "!" not in name
        assert "@" not in name

    def test_generate_name_empty_falls_back(self) -> None:
        gi = GenomeInheritance()
        name = gi._generate_name("!!!", 0)
        assert name.startswith("agent_g0_")


# ---------------------------------------------------------------------------
# Load genome round-trip
# ---------------------------------------------------------------------------


class TestGenomeLoadRoundTrip:
    @pytest.mark.asyncio
    async def test_load_genome(self, tmp_path: Path) -> None:
        gi = GenomeInheritance(state_dir=tmp_path)
        parent = make_parent_spec()
        kernel = make_mock_kernel()

        with patch.object(gi, "_filter_parent_memory", new_callable=AsyncMock, return_value=[]):
            _, genome = await gi.compose_child_spec(
                parent_spec=parent,
                parent_generation=0,
                capability_gap="round trip test",
                proposed_role="roundtripper",
                proposed_spec_delta={},
                kernel=kernel,
            )

        loaded = gi.load_genome(genome.child_name)
        assert loaded is not None
        assert loaded.parent_name == genome.parent_name
        assert loaded.kernel_signature == genome.kernel_signature

    def test_load_genome_missing(self, tmp_path: Path) -> None:
        gi = GenomeInheritance(state_dir=tmp_path)
        assert gi.load_genome("nonexistent_g99_20260101") is None
