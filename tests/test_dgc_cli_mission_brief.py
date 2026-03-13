from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_dgc_cli_mission_brief_command_dispatch():
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "mission-brief", "--json", "--path", "/tmp/mission.json"]):
        with patch("dharma_swarm.dgc_cli.cmd_mission_brief", return_value=0) as mock:
            main()
            mock.assert_called_once()
            assert mock.call_args.kwargs["path"] == "/tmp/mission.json"
            assert mock.call_args.kwargs["state_dir"] is None
            assert mock.call_args.kwargs["as_json"] is True


def test_dgc_cli_campaign_brief_command_dispatch():
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "campaign-brief", "--json", "--path", "/tmp/campaign.json"]):
        with patch("dharma_swarm.dgc_cli.cmd_campaign_brief", return_value=0) as mock:
            main()
            mock.assert_called_once()
            assert mock.call_args.kwargs["path"] == "/tmp/campaign.json"
            assert mock.call_args.kwargs["state_dir"] is None
            assert mock.call_args.kwargs["as_json"] is True


def test_dgc_cli_mission_brief_nonzero_exits():
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "mission-brief"]):
        with patch("dharma_swarm.dgc_cli.cmd_mission_brief", return_value=1):
            with pytest.raises(SystemExit) as exc:
                main()
    assert exc.value.code == 1


def test_cmd_mission_brief_renders_text(tmp_path, capsys):
    import dharma_swarm.dgc_cli as cli

    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "mission.json").write_text(
        json.dumps(
            {
                "mission_title": "Stabilize live mission continuity",
                "mission_thesis": "Operators should see active mission state instantly.",
                "mission_theme": "operations",
                "last_cycle_id": "1776",
                "last_cycle_ts": "2026-03-11T13:10:00Z",
                "status": "delegated",
                "task_titles": ["Read mission.json", "Render CLI brief"],
            }
        ),
        encoding="utf-8",
    )

    rc = cli.cmd_mission_brief(state_dir=str(state_dir))

    out = capsys.readouterr().out
    assert rc == 0
    assert "Mission: Stabilize live mission continuity" in out
    assert "Tasks:" in out


def test_cmd_mission_brief_renders_json(tmp_path, capsys):
    import dharma_swarm.dgc_cli as cli

    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "mission.json").write_text(
        json.dumps(
            {
                "mission_title": "Emit mission JSON",
                "mission_theme": "ops",
                "status": "planned",
            }
        ),
        encoding="utf-8",
    )

    rc = cli.cmd_mission_brief(state_dir=str(state_dir), as_json=True)

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["source_kind"] == "mission_file"
    assert payload["state"]["mission_title"] == "Emit mission JSON"


def test_cmd_campaign_brief_renders_text(tmp_path, capsys):
    import dharma_swarm.dgc_cli as cli

    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "campaign.json").write_text(
        json.dumps(
            {
                "campaign_id": "campaign-2002",
                "mission_title": "Dual engine",
                "mission_theme": "autonomy",
                "status": "delegated",
                "semantic_briefs": [{"brief_id": "semantic-a", "title": "Semantic hub"}],
                "execution_briefs": [{"brief_id": "exec-a", "title": "Build hub"}],
            }
        ),
        encoding="utf-8",
    )

    rc = cli.cmd_campaign_brief(state_dir=str(state_dir))

    out = capsys.readouterr().out
    assert rc == 0
    assert "Campaign: Dual engine" in out
    assert "Semantic briefs: 1" in out
