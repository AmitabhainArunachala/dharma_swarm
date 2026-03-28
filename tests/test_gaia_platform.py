from __future__ import annotations

import json

from dharma_swarm.gaia_platform import (
    GaiaPlatform,
    GaiaProject,
    main,
)


def test_recommendations_prioritize_verified_projects(tmp_path):
    platform = GaiaPlatform(data_dir=tmp_path)

    recommendations = platform.recommend_projects("anthropic_claude_ops", top_n=3)

    assert recommendations
    top = recommendations[0]
    assert top.strategy.approved is True
    assert top.project.verification_status == "verified"
    assert top.welfare_tons > 0
    assert top.match_score > 0
    assert "anekanta" in top.strategy.principles
    assert "jagat_kalyan" in top.strategy.principles


def test_ahimsa_blocks_harmful_monoculture_project(tmp_path):
    harmful = GaiaProject(
        project_id="harmful-monoculture",
        name="Export Monoculture Plantation",
        project_type="monoculture",
        country="Nowhere",
        region="Test Region",
        hectares=500,
        carbon_potential_tons_yr=2000,
        labor_needed=10,
        funding_gap_usd=400_000,
        verification_status="verified",
        community_partner="Absent",
        description="Monoculture plantation that would clearcut native habitat.",
        verification_channels=("satellite", "ground", "community"),
    )
    platform = GaiaPlatform(data_dir=tmp_path, projects=[harmful])

    assessment = platform.assess_project(harmful)

    assert assessment.approved is False
    assert any("AHIMSA" in warning for warning in assessment.warnings)
    assert platform.recommend_projects("anthropic_claude_ops") == []


def test_stage_pilot_records_full_auditable_chain(tmp_path):
    platform = GaiaPlatform(data_dir=tmp_path)

    pilot = platform.stage_pilot(
        model_id="anthropic_claude_ops",
        energy_mwh=12.0,
        carbon_intensity=0.35,
    )

    summary = pilot["ledger_summary"]
    assert summary["chain_valid"] is True
    assert summary["compute_units"] == 1
    assert summary["funding_units"] == 1
    assert summary["labor_units"] == 1
    assert summary["offset_units"] == 1
    assert summary["verification_units"] >= 3
    assert summary["total_verified_offset"] > 0
    assert pilot["fitness"]["weighted_score"] > 0
    assert pilot["recommendation"].strategy.approved is True


def test_cli_dashboard_renders_user_interface(tmp_path, capsys):
    exit_code = main(
        [
            "dashboard",
            "--data-dir",
            str(tmp_path),
            "--model",
            "anthropic_claude_ops",
        ]
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "GAIA Platform" in out
    assert "Aptavani" in out
    assert "Top Recommendations" in out


def test_build_pilot_report_writes_monitoring_and_feedback_artifacts(tmp_path):
    platform = GaiaPlatform(data_dir=tmp_path)

    result = platform.build_pilot_report(
        model_id="anthropic_claude_ops",
        project_id="bayou-lafourche-mangroves",
        feedback_entries=[
            {
                "actor_id": "steward-1",
                "role": "community_steward",
                "satisfaction": 4.8,
                "confidence": 0.91,
                "summary": "The dashboard made the verification burden legible for field operators.",
                "requested_follow_up": "Add a monthly readiness checklist.",
            },
            {
                "actor_id": "reviewer-1",
                "role": "scientific_reviewer",
                "satisfaction": 4.2,
                "confidence": 0.87,
                "summary": "Evidence trace is strong, but shoreline survival should stay visible.",
                "requested_follow_up": "Track seedling survival at the 90-day review.",
            },
        ],
    )

    payload = json.loads(result["json_path"].read_text(encoding="utf-8"))
    markdown = result["markdown_path"].read_text(encoding="utf-8")

    assert result["project"].project_id == "bayou-lafourche-mangroves"
    assert payload["monitoring"]["snapshot_count"] >= 3
    assert payload["monitoring"]["snapshots"][0]["label"] == "baseline"
    assert payload["feedback_summary"]["response_count"] == 2
    assert payload["feedback_summary"]["average_satisfaction"] > 4.0
    assert payload["effectiveness"]["status"] == "on_track"
    assert "# GAIA Pilot Report" in markdown
    assert "## User Feedback" in markdown
    assert "Bayou Lafourche Mangrove Reciprocity Pilot" in markdown


def test_cli_pilot_report_writes_named_artifacts(tmp_path, capsys):
    feedback_file = tmp_path / "feedback.json"
    feedback_file.write_text(
        json.dumps(
            [
                {
                    "actor_id": "operator-1",
                    "role": "platform_operator",
                    "satisfaction": 4.4,
                    "confidence": 0.9,
                    "summary": "Pilot outputs are audit-friendly.",
                    "requested_follow_up": "Expose the report in facilitator training.",
                }
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "pilot-report",
            "--data-dir",
            str(tmp_path),
            "--model",
            "anthropic_claude_ops",
            "--project-id",
            "narmada-watershed-commons",
            "--feedback-file",
            str(feedback_file),
        ]
    )

    out = capsys.readouterr().out
    pilot_dir = (
        tmp_path
        / "pilots"
        / "anthropic_claude_ops-narmada-watershed-commons"
    )

    assert exit_code == 0
    assert "GAIA pilot report written" in out
    assert (pilot_dir / "pilot_report.json").exists()
    assert (pilot_dir / "pilot_report.md").exists()
