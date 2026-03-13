from __future__ import annotations

import json

import pytest

from dharma_swarm.mission_contract import (
    CampaignArtifact,
    ExecutionBrief,
    MISSION_CONTRACT_VERSION,
    MissionState,
    SemanticBrief,
    build_campaign_state,
    default_campaign_state_path,
    load_active_campaign_state,
    default_latest_snapshot_path,
    default_mission_state_path,
    load_active_mission_state,
    render_mission_brief,
    save_campaign_state,
    save_mission_state,
)


def test_load_active_mission_state_reads_raw_mission_json(tmp_path):
    state_dir = tmp_path / "state"
    mission_path = default_mission_state_path(state_dir)
    mission_path.parent.mkdir(parents=True, exist_ok=True)
    mission_path.write_text(
        json.dumps(
            {
                "mission_title": "Ship mission-mode default path",
                "mission_thesis": "Force DGC to converge on one artifact at a time.",
                "mission_theme": "autonomy",
                "last_cycle_id": "1773",
                "last_cycle_ts": "2026-03-11T12:34:56Z",
                "status": "delegated",
                "task_count": "0",
                "task_titles": ["Spec mission contract", "Add CLI reader"],
                "delegated_task_ids": ["tsk_1", "tsk_2"],
                "review_summary": "Clean delegation and good convergence.",
                "blockers": ["Need merge on mission-mode default."],
                "rapid_ascent": "true",
                "previous_missions": [
                    {"title": "Repair routing memory", "cycle_id": "1772", "status": "completed"}
                ],
            }
        ),
        encoding="utf-8",
    )

    artifact = load_active_mission_state(state_dir=state_dir)

    assert artifact is not None
    assert artifact.source_kind == "mission_file"
    assert artifact.state.contract_version == MISSION_CONTRACT_VERSION
    assert artifact.state.task_count == 2
    assert artifact.state.rapid_ascent is True
    assert artifact.state.previous_missions[0].title == "Repair routing memory"


def test_load_active_mission_state_falls_back_to_latest_snapshot(tmp_path):
    state_dir = tmp_path / "state"
    latest_path = default_latest_snapshot_path(state_dir)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(
        json.dumps(
            {
                "cycle_id": "1774",
                "ts": "2026-03-11T12:35:10Z",
                "delegated": True,
                "delegated_task_ids": ["tsk_a"],
                "workflow": {
                    "opportunity_title": "Build mission continuity",
                    "thesis": "Continuity should survive between autonomous cycles.",
                    "theme": "memory",
                    "tasks": [
                        {"title": "Write mission.json"},
                        {"title": "Render mission brief"},
                    ],
                },
                "review": {
                    "note": "Rapid completion indicates immediate resynthesis.",
                    "blockers": ["Need default mission mode."],
                },
                "rapid_ascent": True,
            }
        ),
        encoding="utf-8",
    )

    artifact = load_active_mission_state(state_dir=state_dir)

    assert artifact is not None
    assert artifact.source_kind == "latest_snapshot"
    assert artifact.state.mission_title == "Build mission continuity"
    assert artifact.state.status == "delegated"
    assert artifact.state.task_titles == ["Write mission.json", "Render mission brief"]
    assert artifact.state.review_summary == "Rapid completion indicates immediate resynthesis."


def test_render_mission_brief_includes_key_sections(tmp_path):
    mission_path = tmp_path / "mission.json"
    state = MissionState(
        mission_title="Advance DGC mission mode",
        mission_thesis="Mission selection should dominate idle drift.",
        mission_theme="autonomy",
        last_cycle_id="1775",
        last_cycle_ts="2026-03-11T13:00:00Z",
        status="delegated",
        task_titles=["Select mission", "Ship artifact"],
        blockers=["Need user approval on default behavior."],
        rapid_ascent=True,
    )
    save_mission_state(mission_path, state)

    artifact = load_active_mission_state(path=mission_path)
    assert artifact is not None

    brief = render_mission_brief(artifact)
    assert "Mission: Advance DGC mission mode" in brief
    assert "Rapid ascent: yes" in brief
    assert "Tasks:" in brief
    assert "Blockers:" in brief


def test_save_mission_state_round_trips(tmp_path):
    mission_path = tmp_path / "mission.json"
    state = MissionState(
        mission_title="Create stable mission contract",
        mission_theme="runtime",
        task_titles=["Add pydantic model"],
    )

    saved = save_mission_state(mission_path, state)
    artifact = load_active_mission_state(path=saved)

    assert artifact is not None
    assert artifact.state.mission_title == "Create stable mission contract"
    assert artifact.state.task_count == 1


def test_load_mission_state_raises_for_invalid_payload(tmp_path):
    broken = tmp_path / "mission.json"
    broken.write_text(json.dumps({"status": "delegated"}), encoding="utf-8")

    with pytest.raises(ValueError, match="mission_title"):
        load_active_mission_state(path=broken)


def test_campaign_state_round_trip_and_merges_briefs(tmp_path):
    state_dir = tmp_path / "state"
    mission = MissionState(
        mission_title="Dual engine mission",
        mission_thesis="Bind semantic depth to execution discipline.",
        mission_theme="autonomy",
        last_cycle_id="2001",
        task_titles=["Compile briefs", "Run probe"],
    )
    campaign = build_campaign_state(
        mission_state=mission,
        semantic_briefs=[
            SemanticBrief(
                brief_id="semantic-a",
                title="Semantic hub",
                readiness_score=0.8,
                evidence_paths=["graph.json"],
            )
        ],
        execution_briefs=[
            ExecutionBrief(
                brief_id="exec-a",
                title="Build hub",
                readiness_score=0.7,
                task_titles=["Implement hub.py"],
            )
        ],
        artifacts=[
            CampaignArtifact(
                artifact_kind="report",
                title="Brief packet",
                path="briefs.md",
            )
        ],
        evidence_paths=["graph.json", "briefs.md"],
        metrics={"avg_readiness": 0.75},
    )

    path = default_campaign_state_path(state_dir)
    save_campaign_state(path, campaign)
    artifact = load_active_campaign_state(state_dir=state_dir)

    assert artifact is not None
    assert artifact.state.mission_title == "Dual engine mission"
    assert artifact.state.campaign_id == "campaign-2001"
    assert artifact.state.task_count == 2
    assert artifact.state.evidence_paths == ["graph.json", "briefs.md"]
    assert artifact.state.semantic_briefs[0].brief_id == "semantic-a"
    assert artifact.state.execution_briefs[0].brief_id == "exec-a"
