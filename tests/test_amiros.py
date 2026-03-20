"""Tests for AMIROS research registries."""

import pytest
from pathlib import Path
from dharma_swarm.amiros import (
    AMIROSRegistry,
    Experiment,
    Claim,
    Artifact,
    ConfigEntry,
    HarvestEntry,
)


class TestAMIROSRegistration:
    """Tests for registering experiments, claims, artifacts, configs."""

    def test_register_experiment(self, tmp_path):
        amiros = AMIROSRegistry(state_dir=tmp_path)
        exp = amiros.register_experiment(
            name="R_V across 8 models",
            hypothesis="V > O > K > Q hierarchy holds universally",
            lane="rv_metric",
        )
        assert exp.id
        assert exp.status == "proposed"
        assert exp.lane == "rv_metric"

    def test_register_claim_with_evidence(self, tmp_path):
        amiros = AMIROSRegistry(state_dir=tmp_path)
        exp = amiros.register_experiment("test", "test hypothesis")
        claim = amiros.register_claim(
            statement="Universal V > O > K > Q hierarchy",
            confidence=0.85,
            domain="rv_metric",
            evidence_experiments=[exp.id],
        )
        assert claim.confidence == 0.85
        assert exp.id in claim.evidence_experiment_ids
        # Claim should be linked back to experiment
        assert claim.id in amiros.get_experiment(exp.id).claim_ids

    def test_register_artifact_links_to_experiment(self, tmp_path):
        amiros = AMIROSRegistry(state_dir=tmp_path)
        exp = amiros.register_experiment("test", "hypothesis")
        artifact = amiros.register_artifact(
            name="rv_results.json",
            artifact_type="data",
            experiment_id=exp.id,
            path="results/rv_results.json",
        )
        assert artifact.experiment_id == exp.id
        assert artifact.id in amiros.get_experiment(exp.id).artifact_ids

    def test_register_config(self, tmp_path):
        amiros = AMIROSRegistry(state_dir=tmp_path)
        config = amiros.register_config(
            name="rv_sweep_config",
            parameters={"models": ["SmolLM2-135M", "Qwen2.5-0.5B"], "layers": "all"},
            model="local",
        )
        assert config.id
        assert not config.frozen

    def test_harvest_agent_output(self, tmp_path):
        amiros = AMIROSRegistry(state_dir=tmp_path)
        harvest = amiros.harvest(
            source="agent_output",
            agent_id="researcher_01",
            raw_text="Found strong V > O pattern in Qwen models...",
            claims=["V > O pattern holds for Qwen family"],
        )
        assert harvest.source == "agent_output"
        assert len(harvest.extracted_claims) == 1


class TestAMIROSLifecycle:
    """Tests for experiment lifecycle management."""

    def test_start_experiment_freezes_config(self, tmp_path):
        amiros = AMIROSRegistry(state_dir=tmp_path)
        config = amiros.register_config("test", {"lr": 0.001})
        exp = amiros.register_experiment("test", "hypothesis", config_id=config.id)

        amiros.start_experiment(exp.id)
        assert amiros.get_experiment(exp.id).status == "running"
        assert amiros._configs[config.id].frozen

    def test_complete_experiment(self, tmp_path):
        amiros = AMIROSRegistry(state_dir=tmp_path)
        exp = amiros.register_experiment("test", "hypothesis")
        amiros.start_experiment(exp.id)
        amiros.complete_experiment(exp.id, "V > O confirmed", success=True)

        completed = amiros.get_experiment(exp.id)
        assert completed.status == "completed"
        assert completed.result_summary == "V > O confirmed"
        assert completed.completed_at is not None

    def test_challenge_claim(self, tmp_path):
        amiros = AMIROSRegistry(state_dir=tmp_path)
        claim = amiros.register_claim("Bold claim", confidence=0.9)

        amiros.challenge_claim(claim.id, "Contradicted by new data")
        amiros.challenge_claim(claim.id, "Second contradiction")
        updated = amiros.get_claim(claim.id)
        assert updated.status == "challenged"
        assert len(updated.counterevidence) == 2

    def test_validate_claim(self, tmp_path):
        amiros = AMIROSRegistry(state_dir=tmp_path)
        claim = amiros.register_claim("Solid claim", confidence=0.8)
        amiros.validate_claim(claim.id)
        assert amiros.get_claim(claim.id).status == "validated"


class TestAMIROSQueries:
    """Tests for querying registries."""

    def test_experiments_by_lane(self, tmp_path):
        amiros = AMIROSRegistry(state_dir=tmp_path)
        amiros.register_experiment("e1", "h1", lane="rv_metric")
        amiros.register_experiment("e2", "h2", lane="triton")
        amiros.register_experiment("e3", "h3", lane="rv_metric")

        rv = amiros.experiments_by_lane("rv_metric")
        assert len(rv) == 2

    def test_claims_by_domain(self, tmp_path):
        amiros = AMIROSRegistry(state_dir=tmp_path)
        amiros.register_claim("c1", domain="rv_metric")
        amiros.register_claim("c2", domain="architecture")

        rv = amiros.claims_by_domain("rv_metric")
        assert len(rv) == 1

    def test_provenance_chain(self, tmp_path):
        amiros = AMIROSRegistry(state_dir=tmp_path)

        config = amiros.register_config("test_config", {"param": "value"})
        exp = amiros.register_experiment("test", "hypothesis", config_id=config.id)
        artifact = amiros.register_artifact("results.json", "data", experiment_id=exp.id)
        claim = amiros.register_claim(
            "Claim based on evidence",
            evidence_experiments=[exp.id],
            evidence_artifacts=[artifact.id],
        )

        chain = amiros.provenance_chain(claim.id)
        assert "claim" in chain
        assert "provenance" in chain
        assert len(chain["provenance"]) == 1
        assert chain["provenance"][0]["config"] is not None
        assert len(chain["provenance"][0]["artifacts"]) == 1

    def test_stats(self, tmp_path):
        amiros = AMIROSRegistry(state_dir=tmp_path)
        amiros.register_experiment("e1", "h1", lane="rv_metric")
        amiros.register_claim("c1", domain="rv_metric")
        amiros.register_artifact("a1", "data")

        stats = amiros.stats()
        assert stats["experiments"]["total"] == 1
        assert stats["claims"]["total"] == 1
        assert stats["artifacts"]["total"] == 1


class TestAMIROSPersistence:
    """Tests for save/load cycle."""

    def test_survives_reload(self, tmp_path):
        # Create and populate
        amiros1 = AMIROSRegistry(state_dir=tmp_path)
        exp = amiros1.register_experiment("test", "hypothesis", lane="rv_metric")
        claim = amiros1.register_claim("test claim", evidence_experiments=[exp.id])
        amiros1.register_artifact("data.json", "data", experiment_id=exp.id)

        # Reload from same directory
        amiros2 = AMIROSRegistry(state_dir=tmp_path)
        assert len(amiros2._experiments) == 1
        assert len(amiros2._claims) == 1
        assert len(amiros2._artifacts) == 1
        assert amiros2.get_experiment(exp.id).name == "test"

    def test_snapshot(self, tmp_path):
        amiros = AMIROSRegistry(state_dir=tmp_path)
        amiros.register_experiment("test", "hypothesis")
        snapshot_path = amiros.save_snapshot()
        assert snapshot_path.exists()
        import json
        data = json.loads(snapshot_path.read_text())
        assert "experiments" in data
        assert "stats" in data
