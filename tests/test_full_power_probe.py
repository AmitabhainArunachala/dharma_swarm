import os
from pathlib import Path

from dharma_swarm.full_power_probe import (
    build_probe_specs,
    latest_files,
    parse_task_status_counts,
    preview_text,
)


def test_preview_text_truncates_lines_and_marks_ellipsis() -> None:
    text = "\n".join(f"line-{idx}" for idx in range(6))
    preview = preview_text(text, lines=3, chars=100)

    assert preview == "line-0\nline-1\nline-2\n..."


def test_parse_task_status_counts_reads_cli_table() -> None:
    text = """
      ID  STATUS      PRI       ASSIGNED    TITLE
----------------------------------------------------------------------
abc12345  pending     normal    -           first
def67890  running     high      agent-1     second
xyz99999  failed      high      agent-2     third
"""
    assert parse_task_status_counts(text) == {
        "pending": 1,
        "running": 1,
        "completed": 0,
        "failed": 1,
    }


def test_latest_files_returns_newest_first(tmp_path: Path) -> None:
    older = tmp_path / "older.md"
    newer = tmp_path / "newer.md"
    older.write_text("older")
    newer.write_text("newer")

    os.utime(older, (10, 10))
    os.utime(newer, (20, 20))

    paths = latest_files(tmp_path, "*.md", limit=2)
    assert paths[0] == newer
    assert paths[1] == older


def test_build_probe_specs_uses_local_sprint_probe() -> None:
    specs = build_probe_specs(
        python_executable="python3",
        route_task="route me",
        context_search_query="find me",
        compose_task="compose me",
        autonomy_action="approve me",
        include_sprint_probe=True,
    )

    sprint = next(spec for spec in specs if spec.name == "sprint")
    assert sprint.command[-2:] == ("sprint", "--local")
    assert any(spec.name == "campaign-brief" for spec in specs)
    provider_smoke = next(spec for spec in specs if spec.name == "provider-smoke")
    assert provider_smoke.command[-2:] == ("provider-smoke", "--json")
