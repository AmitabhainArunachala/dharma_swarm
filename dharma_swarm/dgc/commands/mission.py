"""Mission-oriented command pack for the modular DGC CLI."""

from __future__ import annotations


def cmd_mission_status(
    *,
    as_json: bool = False,
    strict_core: bool = False,
    require_tracked: bool = False,
    profile: str | None = None,
) -> int:
    """Delegate to the legacy mission-status handler during migration."""
    from dharma_swarm import dgc_cli

    return dgc_cli.cmd_mission_status(
        as_json=as_json,
        strict_core=strict_core,
        require_tracked=require_tracked,
        profile=profile,
    )


def cmd_mission_brief(
    *,
    path: str | None = None,
    state_dir: str | None = None,
    as_json: bool = False,
) -> int:
    """Delegate to the legacy mission-brief handler during migration."""
    from dharma_swarm import dgc_cli

    return dgc_cli.cmd_mission_brief(
        path=path,
        state_dir=state_dir,
        as_json=as_json,
    )


def cmd_campaign_brief(
    *,
    path: str | None = None,
    state_dir: str | None = None,
    as_json: bool = False,
) -> int:
    """Delegate to the legacy campaign-brief handler during migration."""
    from dharma_swarm import dgc_cli

    return dgc_cli.cmd_campaign_brief(
        path=path,
        state_dir=state_dir,
        as_json=as_json,
    )


def cmd_canonical_status(*, as_json: bool = False) -> int:
    """Delegate to the legacy canonical-status handler during migration."""
    from dharma_swarm import dgc_cli

    return dgc_cli.cmd_canonical_status(as_json=as_json)
