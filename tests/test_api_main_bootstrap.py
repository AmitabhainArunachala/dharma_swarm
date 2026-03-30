from __future__ import annotations

import asyncio
import builtins
from datetime import datetime, timezone
import importlib
import json
import sys
from types import SimpleNamespace


def _clear_modules(*module_names: str) -> None:
    for module_name in module_names:
        sys.modules.pop(module_name, None)


def test_api_main_imports_without_api_keys(monkeypatch) -> None:
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "api_keys" and name not in sys.modules:
            raise ModuleNotFoundError("No module named 'api_keys'")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    _clear_modules("api.main", "api.routers.chat")

    module = importlib.import_module("api.main")

    assert module.app.title == "DHARMA COMMAND"


def test_daemon_health_reads_runtime_state_from_dharma_home(
    monkeypatch,
    tmp_path,
) -> None:
    home = tmp_path / "home"
    repo_root = tmp_path / "custom-repo"
    state_root = tmp_path / "runtime-state"

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("DHARMA_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("DHARMA_HOME", str(state_root))

    stigmergy_dir = state_root / "stigmergy"
    stigmergy_dir.mkdir(parents=True)
    (state_root / "daemon.pid").write_text("321\n", encoding="utf-8")
    (state_root / "operator.pid").write_text("654\n", encoding="utf-8")
    tick = datetime.now(timezone.utc).isoformat()
    (stigmergy_dir / "dgc_health.json").write_text(
        json.dumps(
            {
                "daemon_pid": 321,
                "source": "pulse",
                "timestamp": tick,
                "agent_count": 4,
                "task_count": 9,
                "anomaly_count": 0,
            }
        ),
        encoding="utf-8",
    )

    _clear_modules("dharma_swarm.runtime_paths", "api.chat_tools", "api.routers.chat", "api.main")
    module = importlib.import_module("api.main")

    payload = asyncio.run(module.daemon_health())

    assert module._OPERATOR_STATE_DIR == state_root
    assert payload["status"] == "healthy"
    assert payload["daemon_pid"] == 321
    assert payload["operator_pid"] == 654
    assert payload["dgc_health_status"] == "pulse"
    assert payload["last_tick"] == tick
    assert payload["maintenance_summary"] == "pulse snapshot fresh"
    assert payload["runtime_warnings"] == []


def test_health_routes_share_runtime_payload_fields(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    repo_root = tmp_path / "custom-repo"
    state_root = tmp_path / "runtime-state"

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("DHARMA_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("DHARMA_HOME", str(state_root))

    stigmergy_dir = state_root / "stigmergy"
    stigmergy_dir.mkdir(parents=True)
    (state_root / "daemon.pid").write_text("111\n", encoding="utf-8")
    (state_root / "operator.pid").write_text("222\n", encoding="utf-8")
    (stigmergy_dir / "dgc_health.json").write_text(
        json.dumps(
            {
                "daemon_pid": 111,
                "agent_count": 3,
                "task_count": 5,
                "anomaly_count": 1,
                "timestamp": "2026-03-30T00:00:00Z",
                "source": "maintenance",
            }
        ),
        encoding="utf-8",
    )

    _clear_modules("dharma_swarm.runtime_paths", "api.chat_tools", "api.routers.chat", "api.routers.health", "api.main")
    main_module = importlib.import_module("api.main")
    health_module = importlib.import_module("api.routers.health")

    fake_report = SimpleNamespace(
        overall_status=SimpleNamespace(value="healthy"),
        agent_health=[],
        anomalies=[],
        total_traces=12,
        traces_last_hour=4,
        failure_rate=0.0,
        mean_fitness=0.91,
    )

    class FakeMonitor:
        async def check_health(self):
            return fake_report

    monkeypatch.setattr(
        health_module,
        "_get_deps",
        lambda: (object(), object(), FakeMonitor()),
    )

    runtime_payload = asyncio.run(main_module.daemon_health())
    api_payload = asyncio.run(health_module.health_check()).data
    if hasattr(api_payload, "model_dump"):
        api_payload = api_payload.model_dump()

    assert api_payload["overall_status"] == "healthy"
    assert api_payload["runtime"]["status"] == runtime_payload["status"]
    assert api_payload["runtime"]["daemon_pid"] == runtime_payload["daemon_pid"]
    assert api_payload["runtime"]["operator_pid"] == runtime_payload["operator_pid"]
    assert api_payload["runtime"]["maintenance_summary"] == runtime_payload["maintenance_summary"]
    assert api_payload["runtime"]["runtime_warnings"] == runtime_payload["runtime_warnings"]
