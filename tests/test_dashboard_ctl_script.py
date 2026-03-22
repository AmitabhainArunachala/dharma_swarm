from __future__ import annotations

from pathlib import Path


def test_dashboard_ctl_avoids_bare_launchctl_kickstart_targets() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "dashboard_ctl.sh"
    )
    text = script.read_text(encoding="utf-8")

    assert 'launchctl kickstart -k "${label}"' not in text


def test_dashboard_ctl_checks_live_services_before_restart() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "dashboard_ctl.sh"
    )
    text = script.read_text(encoding="utf-8")

    assert "service_is_ready()" in text
    assert 'if service_is_ready "$label"; then' in text


def test_dashboard_ctl_uses_http_health_probes_for_live_services() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "dashboard_ctl.sh"
    )
    text = script.read_text(encoding="utf-8")

    assert "/api/health" in text
    assert "http://127.0.0.1:3420/" in text


def test_dashboard_ctl_reconciles_split_port_owners_before_kickstart() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "dashboard_ctl.sh"
    )
    text = script.read_text(encoding="utf-8")

    assert "reconcile_service_owner()" in text
    assert 'reconcile_service_owner "$API_LABEL"' in text
    assert 'reconcile_service_owner "$WEB_LABEL"' in text
    assert "process_descends_from()" in text


def test_run_dashboard_ui_rebuilds_when_sources_are_newer_than_build_id() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_dashboard_ui.sh"
    )
    text = script.read_text(encoding="utf-8")

    assert "dashboard_build_stale()" in text
    assert '.next/BUILD_ID' in text
    assert '-newer "$build_id"' in text
