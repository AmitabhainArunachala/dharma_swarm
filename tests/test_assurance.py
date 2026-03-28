from __future__ import annotations

import subprocess
from pathlib import Path

from dharma_swarm.assurance import (
    scanner_api_envelope,
    scanner_context_isolation,
    scanner_lifecycle,
    scanner_providers,
    scanner_routes,
    scanner_storage,
    scanner_test_gaps,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_provider_scan_ignores_comments_and_assurance_sources(tmp_path: Path) -> None:
    repo_root = tmp_path
    _write(
        repo_root / "dharma_swarm" / "conductors.py",
        "\n".join(
            [
                "from dharma_swarm.models import ProviderType",
                'CONFIG = {"provider_type": ProviderType.CODEX, "model": "claude-sonnet-4-20250514"}',
            ]
        ),
    )
    _write(
        repo_root / "dharma_swarm" / "subconscious_fleet.py",
        "# ProviderType.NIM\n# ProviderType.MOONSHOT\n",
    )
    _write(
        repo_root / "dharma_swarm" / "assurance" / "scanner_providers.py",
        'if "ProviderType.CODEX" in line:\n    return "anthropic"\n',
    )

    report = scanner_providers.scan(repo_root=repo_root)

    descriptions = [finding.description for finding in report.findings]
    files = {finding.file for finding in report.findings}
    assert any("claude-sonnet-4-20250514" in text for text in descriptions)
    assert "dharma_swarm/conductors.py" in files
    assert "dharma_swarm/subconscious_fleet.py" not in files
    assert "dharma_swarm/assurance/scanner_providers.py" not in files


def test_storage_scan_ignores_assurance_paths_for_message_bus_detection(tmp_path: Path) -> None:
    repo_root = tmp_path
    _write(
        repo_root / "dharma_swarm" / "swarm.py",
        'self._message_bus = MessageBus(db_dir / "messages.db")\n',
    )
    _write(
        repo_root / "dharma_swarm" / "persistent_agent.py",
        'db_path = Path.home() / ".dharma" / "db" / "messages.db"\n',
    )
    _write(
        repo_root / "dharma_swarm" / "assurance" / "scanner_storage.py",
        'legacy = "message_bus.db"\n',
    )

    report = scanner_storage.scan(repo_root=repo_root)

    assert not any(finding.category == "message_bus_path_split" for finding in report.findings)
    assert not any(finding.file.startswith("dharma_swarm/assurance/") for finding in report.findings)


def test_storage_scan_checks_project_root_not_file_path(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    fake_home = tmp_path / "home"
    (fake_home / "dharma_swarm").mkdir(parents=True)
    monkeypatch.setattr(scanner_storage.Path, "home", lambda: fake_home)
    _write(
        repo_root / "dharma_swarm" / "ecosystem_index.py",
        'idx.related("~/dharma_swarm/rv.py")\n',
    )

    report = scanner_storage.scan(repo_root=repo_root)

    assert not report.findings


def test_git_changed_files_ignores_deleted_entries(monkeypatch, tmp_path: Path) -> None:
    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(
            args=["git"],
            returncode=0,
            stdout=" D dharma_swarm/old_module.py\n M dharma_swarm/new_module.py\n?? api/new_router.py\n",
            stderr="",
        )

    monkeypatch.setattr(scanner_test_gaps.subprocess, "run", fake_run)

    changed = scanner_test_gaps._git_changed_files(tmp_path)

    assert "dharma_swarm/old_module.py" not in changed
    assert "dharma_swarm/new_module.py" in changed
    assert "api/new_router.py" in changed


def test_api_envelope_scanner_detects_typed_wrapper_mismatch(tmp_path: Path) -> None:
    repo_root = tmp_path
    _write(
        repo_root / "api" / "models.py",
        "class ApiResponse:\n    pass\n",
    )
    _write(
        repo_root / "dashboard" / "src" / "lib" / "api.ts",
        "\n".join(
            [
                "async function _fetchWrapped<T>(): Promise<ApiResponse<T>> {",
                "  const data: T = await res.json();",
                "  return { status: 'ok', data, error: '', timestamp: '' };",
                "}",
                "export async function apiFetch<T>(): Promise<T> {",
                "  const json = await res.json();",
                "  if (json && typeof json === 'object' && 'data' in json && 'status' in json) {",
                "    return json.data as T;",
                "  }",
                "  return json as T;",
                "}",
            ]
        ),
    )

    report = scanner_api_envelope.scan(repo_root=repo_root)

    assert len(report.findings) == 1
    assert report.findings[0].category == "typed_fetch_envelope_mismatch"


def test_api_envelope_scanner_accepts_unwrapped_typed_wrapper(tmp_path: Path) -> None:
    repo_root = tmp_path
    _write(
        repo_root / "api" / "models.py",
        "class ApiResponse:\n    pass\n",
    )
    _write(
        repo_root / "dashboard" / "src" / "lib" / "api.ts",
        "\n".join(
            [
                "async function _fetchWrapped<T>(): Promise<ApiResponse<T>> {",
                "  const json = await res.json();",
                "  if (json && typeof json === 'object' && 'data' in json && 'status' in json) {",
                "    return { status: json.status, data: json.data as T, error: '', timestamp: '' };",
                "  }",
                "  return { status: 'ok', data: json as T, error: '', timestamp: '' };",
                "}",
                "export async function apiFetch<T>(): Promise<T> {",
                "  const json = await res.json();",
                "  if (json && typeof json === 'object' && 'data' in json && 'status' in json) {",
                "    return json.data as T;",
                "  }",
                "  return json as T;",
                "}",
            ]
        ),
    )

    report = scanner_api_envelope.scan(repo_root=repo_root)

    assert report.findings == []


def test_provider_scan_derives_known_providers_from_enum(tmp_path: Path) -> None:
    repo_root = tmp_path
    _write(
        repo_root / "dharma_swarm" / "models.py",
        "\n".join(
            [
                "from enum import Enum",
                "class ProviderType(str, Enum):",
                "    ANTHROPIC = 'anthropic'",
                "    SILICONFLOW = 'siliconflow'",
                "    TOGETHER = 'together'",
                "    FIREWORKS = 'fireworks'",
            ]
        ),
    )
    _write(
        repo_root / "dharma_swarm" / "provider_policy.py",
        "\n".join(
            [
                "from dharma_swarm.models import ProviderType",
                "PREFERRED = (",
                "    ProviderType.SILICONFLOW,",
                "    ProviderType.TOGETHER,",
                "    ProviderType.FIREWORKS,",
                ")",
            ]
        ),
    )

    report = scanner_providers.scan(repo_root=repo_root)

    assert not any(f.category == "unknown_provider" for f in report.findings)


def test_provider_scan_accepts_codex_lane_mapping(tmp_path: Path) -> None:
    repo_root = tmp_path
    _write(
        repo_root / "dharma_swarm" / "models.py",
        "\n".join(
            [
                "from enum import Enum",
                "class ProviderType(str, Enum):",
                "    CODEX = 'codex'",
            ]
        ),
    )
    _write(
        repo_root / "dharma_swarm" / "persistent_agent.py",
        "\n".join(
            [
                "from dharma_swarm.models import ProviderType",
                "def _provider_string(provider_type: ProviderType) -> str:",
                "    if provider_type == ProviderType.CODEX:",
                '        return "codex"',
                '    return "anthropic"',
            ]
        ),
    )

    report = scanner_providers.scan(repo_root=repo_root)

    assert not any(f.category == "provider_alias_mismatch" for f in report.findings)


def test_lifecycle_scanner_accepts_gate_decision_alias_and_optional_steps(tmp_path: Path) -> None:
    repo_root = tmp_path
    _write(
        repo_root / "dharma_swarm" / "ontology.py",
        "\n".join(
            [
                "ActionProposal = object()",
                "GateDecisionRecord = object()",
                "ExecutionLease = object()",
                "ActionExecution = object()",
                "Outcome = object()",
                "ValueEvent = object()",
                "Contribution = object()",
            ]
        ),
    )
    _write(repo_root / "dharma_swarm" / "telic_seam.py", "GateDecisionRecord = object()\n")
    _write(repo_root / "dharma_swarm" / "orchestrator.py", "ExecutionLease = object()\n")

    report = scanner_lifecycle.scan(repo_root=repo_root)

    assert report.findings == []


def test_context_isolation_scanner_detects_global_note_leak(tmp_path: Path) -> None:
    repo_root = tmp_path
    _write(
        repo_root / "dharma_swarm" / "context.py",
        "\n".join(
            [
                "SHARED_DIR = STATE_DIR / 'shared'",
                "def read_agent_notes(exclude_role: str | None = None, max_per_agent: int = 500) -> str:",
                "    if not SHARED_DIR.exists():",
                "        return ''",
                "    distilled_path = STATE_DIR / \"context\" / \"distilled\" / f\"{exclude_role}_distilled.md\"",
                "    return ''",
                "def build_agent_context(role: str | None = None, thread: str | None = None, state_dir: Path | None = None) -> str:",
                "    notes = read_agent_notes(exclude_role=role, max_per_agent=50)",
                "    return notes",
            ]
        ),
    )

    report = scanner_context_isolation.scan(repo_root=repo_root)

    assert len(report.findings) == 1
    assert report.findings[0].category == "state_dir_isolation_leak"


def test_route_scanner_flags_dynamic_template_mismatches(tmp_path: Path) -> None:
    repo_root = tmp_path
    _write(
        repo_root / "api" / "routers" / "lineage.py",
        "\n".join(
            [
                "from fastapi import APIRouter",
                'router = APIRouter(prefix=\"/api\")',
                '@router.get(\"/lineage/{artifact_id}/provenance\")',
                "async def provenance():",
                "    return {}",
            ]
        ),
    )
    _write(
        repo_root / "api" / "routers" / "stigmergy.py",
        "\n".join(
            [
                "from fastapi import APIRouter",
                'router = APIRouter(prefix=\"/api\")',
                '@router.get(\"/stigmergy/heatmap\")',
                "async def heatmap():",
                "    return {}",
            ]
        ),
    )
    _write(
        repo_root / "dashboard" / "src" / "lib" / "api.ts",
        "\n".join(
            [
                "export function fetchHeatmap(metric: string): Promise<ApiResponse<HeatmapCell[]>> {",
                "  return apiGet<HeatmapCell[]>(`/api/heatmap/${encodeURIComponent(metric)}`);",
                "}",
                "export function fetchProvenance(artifactId: string): Promise<ApiResponse<ProvenanceOut>> {",
                "  return apiGet<ProvenanceOut>(`/api/provenance/${encodeURIComponent(artifactId)}`);",
                "}",
            ]
        ),
    )

    report = scanner_routes.scan(repo_root=repo_root)

    descriptions = [finding.description for finding in report.findings]
    assert any("/api/heatmap/" in text for text in descriptions)
    assert any("/api/provenance/" in text for text in descriptions)
