from __future__ import annotations

import asyncio

import dharma_swarm.terminal_bridge as terminal_bridge_module
from dharma_swarm.terminal_bridge import TerminalBridge
from dharma_swarm.runtime_state import OperatorAction, RuntimeStateStore
from dharma_swarm.tui.engine.events import ToolCallComplete, ToolResult


def test_resolve_prompt_intent_detects_plain_language_command() -> None:
    bridge = TerminalBridge()
    intent = bridge._resolve_prompt_intent("show me runtime status")
    assert intent["kind"] == "command"
    assert intent["command"] == "runtime"
    assert intent["auto_execute"] is True


def test_resolve_prompt_intent_detects_model_switch() -> None:
    bridge = TerminalBridge()
    intent = bridge._resolve_prompt_intent("switch to opus 4.6 for the hardest reasoning")
    assert intent["kind"] == "model_switch"
    assert intent["provider"] == "claude"
    assert "claude-opus-4-6" in intent["model"]


def test_resolve_prompt_intent_detects_identity_request() -> None:
    bridge = TerminalBridge()
    intent = bridge._resolve_prompt_intent("who are you now?")
    assert intent["kind"] == "identity"
    assert intent["auto_execute"] is True


def test_resolve_prompt_intent_detects_memory_request() -> None:
    bridge = TerminalBridge()
    intent = bridge._resolve_prompt_intent("compact this session and save the checkpoint")
    assert intent["kind"] == "memory"
    assert intent["auto_execute"] is True


def test_build_session_bootstrap_includes_context_and_system_prompt(monkeypatch) -> None:
    bridge = TerminalBridge()
    monkeypatch.setattr(bridge, "_load_repo_guidance", lambda limit_chars=4000: "Behavioral Rules: obey CLAUDE.md")
    monkeypatch.setattr(bridge, "_load_session_context_hint", lambda: "Active thread: terminal-v3")
    monkeypatch.setattr(
        bridge,
        "_load_working_memory",
        lambda: {
            "recent_turns": [{"prompt": "show runtime", "intent": "command", "route": "codex:gpt-5.4"}],
            "recent_actions": ["command.run -> /runtime"],
            "active_mission": "stabilize terminal operator shell",
            "preferred_route": "codex:gpt-5.4",
            "updated_at": "2026-04-01T00:00:00Z",
        },
    )
    monkeypatch.setattr(bridge, "_remember_turn", lambda **_: None)
    monkeypatch.setattr(
        bridge,
        "_build_workspace_snapshot",
        lambda: "\n".join(
            [
                "# Workspace X-Ray",
                "Repo root: /Users/dhyana/dharma_swarm",
                "Git: main@abc1234 | staged 0 | unstaged 1 | untracked 0",
                "## Topology",
                "- warning: sab_canonical_repo_missing",
            ]
        ),
    )
    monkeypatch.setattr(
        bridge,
        "_build_ontology_snapshot",
        lambda: "# Ontology Surface\nVersion: v1\nConcept count: 10",
    )
    monkeypatch.setattr(
        bridge,
        "_build_runtime_snapshot",
        lambda: "--- Runtime Control Plane ---\nSessions=3  Claims=0\nArtifacts=1  PromotedFacts=0",
    )
    payload = bridge._build_session_bootstrap(
        {
            "prompt": "switch to codex 5.4 and summarize the repo",
            "active_tab": "chat",
            "provider": "claude",
            "model": "claude-sonnet-4-5",
        }
    )

    assert payload["selected_provider"] == "codex"
    assert payload["selected_model"] == "gpt-5.4"
    assert payload["workspace_preview"]["Branch"] == "main"
    assert payload["runtime_preview"]["Runtime activity"] == "Sessions=3  Claims=0"
    assert "Dharma Terminal Bootstrap" in payload["system_prompt"]
    assert "not a detached chatbot" in payload["system_prompt"]
    assert "Available model targets" in payload["system_prompt"]
    assert payload["repo_guidance"] == "Behavioral Rules: obey CLAUDE.md"
    assert payload["session_context_hint"] == "Active thread: terminal-v3"
    assert "stabilize terminal operator shell" in payload["working_memory"]
    assert "switch to codex 5.4 and summarize the repo" in payload["working_memory"]
    assert "Behavioral Rules: obey CLAUDE.md" in payload["system_prompt"]
    assert "Working memory:" in payload["system_prompt"]


def test_build_command_graph_summary_exposes_categories() -> None:
    bridge = TerminalBridge()
    graph = bridge._build_command_graph_summary()
    assert graph["count"] >= 10
    assert "chat" in graph["categories"]
    assert "repo" in graph["categories"]
    assert "logs" in graph["categories"]["memory"]
    assert "runtime" in graph["categories"]
    assert graph["categories"]["runtime"] == ["runtime"]


def test_render_operator_snapshot_text_handles_error() -> None:
    bridge = TerminalBridge()
    text = bridge._render_operator_snapshot_text(
        {
            "runtime_db": "/tmp/runtime.db",
            "error": "db unavailable",
            "overview": {},
            "runs": [],
            "actions": [],
        }
    )
    assert "Operator Snapshot" in text
    assert "db unavailable" in text


def test_build_runtime_snapshot_includes_terminal_control(monkeypatch) -> None:
    bridge = TerminalBridge()
    monkeypatch.setattr(
        "dharma_swarm.terminal_bridge.build_runtime_status_text",
        lambda limit=5: "--- Runtime Control Plane ---\nSessions=3  Claims=0\nArtifacts=1  PromotedFacts=0",
    )
    monkeypatch.setattr(
        "dharma_swarm.terminal_bridge.load_terminal_control_state",
        lambda repo_root: {
            "active_task_id": "task-7",
            "loop_decision": "continue required",
            "verification_status": "1 failing, 1/2 passing",
            "next_task": "fix tests",
            "updated_at": "2026-04-02T00:00:00Z",
        },
    )

    snapshot = bridge._build_runtime_snapshot()

    assert "Verification status: 1 failing, 1/2 passing" in snapshot
    assert "Loop decision: continue required" in snapshot
    assert "Next task: fix tests" in snapshot


def test_build_agent_routes_exposes_profiles() -> None:
    bridge = TerminalBridge()
    routes = bridge._build_agent_routes()
    assert routes["routes"]
    assert routes["subagent_capabilities"]


def test_build_evolution_surface_lists_domains() -> None:
    bridge = TerminalBridge()
    surface = bridge._build_evolution_surface()
    assert any(item["name"] == "code" for item in surface["domains"])


def test_build_model_policy_summary_includes_fallback_chain() -> None:
    bridge = TerminalBridge()
    summary = bridge._build_model_policy_summary(
        selected_provider="codex",
        selected_model="gpt-5.4",
        strategy="responsive",
    )
    assert summary["fallback_chain"]
    assert summary["strategies"]


def test_build_model_policy_summary_filters_unavailable_providers() -> None:
    bridge = TerminalBridge()
    summary = bridge._build_model_policy_summary(
        selected_provider="ollama",
        selected_model="glm-5:cloud",
        strategy="responsive",
    )
    providers = {target["provider"] for target in summary["targets"]}
    assert "ollama" not in providers
    assert summary["selected_provider"] in {"codex", "claude", "openrouter"}


def test_build_model_policy_summary_uses_expanded_core_targets() -> None:
    bridge = TerminalBridge()
    summary = bridge._build_model_policy_summary(
        selected_provider="openrouter",
        selected_model="deepseek/deepseek-r1",
        strategy="responsive",
    )

    target_models = {target["model"] for target in summary["targets"]}

    assert "deepseek/deepseek-r1" in target_models
    assert "openai/gpt-5-codex" in target_models
    assert any("qwen" in model for model in target_models)
    assert any("kimi" in model for model in target_models)


def test_handle_runtime_snapshot_emits_typed_payload_without_legacy_content(monkeypatch) -> None:
    bridge = TerminalBridge()
    captured: list[dict[str, object]] = []
    operator_snapshot = {
        "runtime_db": "/tmp/runtime.db",
        "overview": {
            "sessions": 2,
            "claims": 3,
            "active_claims": 1,
            "acknowledged_claims": 1,
            "runs": 4,
            "active_runs": 1,
            "artifacts": 5,
            "promoted_facts": 2,
            "context_bundles": 1,
            "operator_actions": 6,
        },
        "runs": [],
        "actions": [],
    }
    monkeypatch.setattr(bridge, "_build_operator_snapshot", lambda: operator_snapshot)
    monkeypatch.setattr("dharma_swarm.terminal_bridge.load_terminal_control_state", lambda repo_root: {"Verification status": "ok"})
    monkeypatch.setattr(bridge, "_emit", lambda payload: captured.append(payload))

    asyncio.run(bridge._handle_runtime_snapshot("req-runtime"))

    assert captured[0]["type"] == "runtime.snapshot.result"
    assert "content" not in captured[0]
    assert captured[0]["payload"]["version"] == "v1"
    assert captured[0]["payload"]["domain"] == "runtime_snapshot"
    assert captured[0]["payload"]["snapshot"]["active_session_count"] == 2


def test_handle_workspace_snapshot_emits_typed_payload_without_legacy_content(monkeypatch) -> None:
    bridge = TerminalBridge()
    captured: list[dict[str, object]] = []
    summary = type(
        "Summary",
        (),
        {
            "python_modules": 10,
            "python_tests": 5,
            "shell_scripts": 3,
            "markdown_docs": 2,
            "workflows": ["ci.yml"],
            "language_mix": {".py": 20},
            "largest_python_files": [
                type("FileMetric", (), {"path": "dharma_swarm/app.py", "lines": 120, "defs": 8, "classes": 1, "imports": 5})()
            ],
            "most_imported_modules": [
                type("ModuleMetric", (), {"module": "dharma_swarm.models", "count": 7})()
            ],
        },
    )()
    git_summary = {
        "branch": "main",
        "head": "abc1234",
        "staged": 1,
        "unstaged": 2,
        "untracked": 3,
        "changed_hotspots": [{"name": "terminal", "count": 4}],
        "changed_paths": ["terminal/src/app.tsx"],
        "sync_summary": "origin/main | ahead 0 | behind 1",
        "sync_status": "tracking",
        "upstream": "origin/main",
        "ahead": 0,
        "behind": 1,
    }
    topology = {
        "warnings": ["sab_canonical_repo_missing"],
        "dgc": {
            "repos": [
                {
                    "name": "dharma_swarm",
                    "role": "canonical_core",
                    "canonical": True,
                    "path": "/repo",
                    "exists": True,
                    "is_git": True,
                    "branch": "main...origin/main",
                    "head": "abc1234",
                    "dirty": True,
                    "modified_count": 2,
                    "untracked_count": 1,
                }
            ]
        },
        "sab": {"repos": []},
    }
    monkeypatch.setattr(bridge, "_load_repo_xray", lambda: summary)
    monkeypatch.setattr(bridge, "_build_git_summary", lambda: git_summary)
    monkeypatch.setattr("dharma_swarm.terminal_bridge.build_workspace_topology", lambda root: topology)
    monkeypatch.setattr(bridge, "_emit", lambda payload: captured.append(payload))

    asyncio.run(bridge._handle_workspace_snapshot("req-workspace"))

    assert captured[0]["type"] == "workspace.snapshot.result"
    assert captured[0]["payload"]["domain"] == "workspace_snapshot"
    assert captured[0]["payload"]["git"]["branch"] == "main"
    assert captured[0]["payload"]["topology"]["warnings"] == ["sab_canonical_repo_missing"]
    assert captured[0]["payload"]["inventory"]["python_modules"] == 10
    assert "content" not in captured[0]


def test_surface_refresh_repo_returns_typed_workspace_payload(monkeypatch) -> None:
    bridge = TerminalBridge()
    summary = type(
        "Summary",
        (),
        {
            "python_modules": 10,
            "python_tests": 5,
            "shell_scripts": 3,
            "markdown_docs": 2,
            "workflows": ["ci.yml"],
            "language_mix": {".py": 20},
            "largest_python_files": [],
            "most_imported_modules": [],
        },
    )()
    monkeypatch.setattr(bridge, "_refresh_surface", lambda surface: ("workspace:text", "repo"))
    monkeypatch.setattr(bridge, "_load_repo_xray", lambda: summary)
    monkeypatch.setattr(
        bridge,
        "_build_git_summary",
        lambda: {
            "branch": "main",
            "head": "abc1234",
            "staged": 1,
            "unstaged": 2,
            "untracked": 3,
            "changed_hotspots": [{"name": "terminal", "count": 4}],
            "changed_paths": ["terminal/src/app.tsx"],
            "sync_summary": "origin/main | ahead 0 | behind 1",
            "sync_status": "tracking",
            "upstream": "origin/main",
            "ahead": 0,
            "behind": 1,
        },
    )
    monkeypatch.setattr(
        "dharma_swarm.terminal_bridge.build_workspace_topology",
        lambda root: {"warnings": [], "dgc": {"repos": []}, "sab": {"repos": []}},
    )

    result = bridge._run_action("surface.refresh", {"surface": "repo"})

    assert result["target_pane"] == "repo"
    assert "output" not in result
    assert result["payload"]["domain"] == "workspace_snapshot"
    assert result["payload"]["git"]["branch"] == "main"


def test_handle_permission_history_emits_typed_payload(monkeypatch) -> None:
    bridge = TerminalBridge()
    captured: list[dict[str, object]] = []
    monkeypatch.setattr(
        "dharma_swarm.terminal_bridge.build_permission_history_payload",
        lambda store, limit=50: {"version": "v1", "domain": "permission_history", "count": 1, "entries": []},
    )
    monkeypatch.setattr(bridge, "_emit", lambda payload: captured.append(payload))

    asyncio.run(bridge._handle_permission_history("req-history", {"limit": 7}))

    assert captured[0]["type"] == "permission.history.result"
    assert captured[0]["payload"]["domain"] == "permission_history"
    assert captured[0]["payload"]["count"] == 1


def test_handle_model_policy_emits_typed_payload_without_legacy_content(monkeypatch) -> None:
    bridge = TerminalBridge()
    captured: list[dict[str, object]] = []
    policy = {
        "selected_provider": "codex",
        "selected_model": "gpt-5.4",
        "selected_route": "codex:gpt-5.4",
        "strategy": "responsive",
        "strategies": ["responsive", "genius"],
        "default_route": "codex:gpt-5.4",
        "active_label": "GPT-5.4",
        "fallback_chain": [{"provider": "claude", "model": "sonnet-4.6", "label": "Sonnet 4.6"}],
        "targets": [{"alias": "primary", "provider": "codex", "model": "gpt-5.4", "label": "GPT-5.4"}],
    }
    monkeypatch.setattr(bridge, "_build_model_policy_summary", lambda **kwargs: policy)
    monkeypatch.setattr(bridge, "_emit", lambda payload: captured.append(payload))

    asyncio.run(bridge._handle_model_policy("req-model", {"provider": "codex", "model": "gpt-5.4", "strategy": "responsive"}))

    assert captured[0]["type"] == "model.policy.result"
    assert "content" not in captured[0]
    assert captured[0]["payload"]["version"] == "v1"
    assert captured[0]["payload"]["domain"] == "routing_decision"
    assert captured[0]["payload"]["decision"]["route_id"] == "codex:gpt-5.4"
    assert captured[0]["policy"] == policy


def test_run_action_model_set_returns_policy() -> None:
    bridge = TerminalBridge()
    result = bridge._run_action(
        "model.set",
        {"provider": "codex", "model": "gpt-5.4", "strategy": "genius"},
    )
    assert result["ok"] is True
    assert result["target_pane"] == "models"
    assert "genius" in result["summary"]
    assert result["payload"]["domain"] == "routing_decision"


def test_run_action_surface_refresh_returns_registry() -> None:
    bridge = TerminalBridge()
    result = bridge._run_action("surface.refresh", {"surface": "commands"})
    assert result["ok"] is True
    assert result["target_pane"] == "commands"
    assert "Command Registry" in result["output"]


def test_run_action_surface_refresh_returns_typed_session_payload(monkeypatch) -> None:
    bridge = TerminalBridge()
    catalog = {
        "version": "v1",
        "domain": "session_catalog",
        "count": 1,
        "sessions": [
            {
                "session": {
                    "session_id": "sess-1",
                    "provider_id": "codex",
                    "model_id": "gpt-5.4",
                    "cwd": "/repo",
                    "created_at": "2026-04-01T00:00:00Z",
                    "updated_at": "2026-04-01T01:00:00Z",
                    "status": "completed",
                },
                "replay_ok": True,
                "replay_issues": [],
                "total_turns": 1,
                "total_cost_usd": 1.5,
            }
        ],
    }
    monkeypatch.setattr("dharma_swarm.terminal_bridge.build_session_catalog", lambda *args, **kwargs: catalog)

    result = bridge._run_action("surface.refresh", {"surface": "sessions"})

    assert result["ok"] is True
    assert result["target_pane"] == "sessions"
    assert "output" not in result
    assert result["payload"] == catalog


def test_run_action_surface_refresh_returns_typed_runtime_payload(monkeypatch) -> None:
    bridge = TerminalBridge()
    operator_snapshot = {
        "runtime_db": "/tmp/runtime.db",
        "overview": {
            "sessions": 2,
            "claims": 3,
            "active_claims": 1,
            "acknowledged_claims": 1,
            "runs": 4,
            "active_runs": 1,
            "artifacts": 5,
            "promoted_facts": 2,
            "context_bundles": 1,
            "operator_actions": 6,
        },
        "runs": [],
        "actions": [],
    }
    monkeypatch.setattr(bridge, "_refresh_surface", lambda surface: ("runtime:text", "control"))
    monkeypatch.setattr(bridge, "_build_operator_snapshot", lambda: operator_snapshot)
    monkeypatch.setattr("dharma_swarm.terminal_bridge.load_terminal_control_state", lambda repo_root: {"Verification status": "ok"})

    result = bridge._run_action("surface.refresh", {"surface": "control"})

    assert result["ok"] is True
    assert result["target_pane"] == "control"
    assert "output" not in result
    assert result["payload"]["domain"] == "runtime_snapshot"
    assert result["payload"]["snapshot"]["active_session_count"] == 2


def test_run_action_surface_refresh_returns_typed_model_payload_without_output() -> None:
    bridge = TerminalBridge()

    result = bridge._run_action("surface.refresh", {"surface": "models"})

    assert result["ok"] is True
    assert result["target_pane"] == "models"
    assert "output" not in result
    assert result["payload"]["domain"] == "routing_decision"
    assert isinstance(result["policy"], dict)


def test_run_action_surface_refresh_returns_typed_agent_routes_without_output(monkeypatch) -> None:
    bridge = TerminalBridge()
    routes = [
        {
            "intent": "deep_code_work",
            "routing_mode": "auto",
            "primary": {"provider": "codex", "model": "gpt-5.4"},
            "fallback": [{"provider": "claude", "model": "sonnet-4.6"}],
            "reason": "default lane",
        }
    ]
    monkeypatch.setattr(bridge, "_build_agent_routes", lambda: routes)

    result = bridge._run_action("surface.refresh", {"surface": "agents"})

    assert result["ok"] is True
    assert result["target_pane"] == "agents"
    assert "output" not in result
    assert result["payload"]["domain"] == "agent_routes"
    assert result["routes"] == routes


def test_handle_agent_routes_emits_typed_payload_without_legacy_content(monkeypatch) -> None:
    bridge = TerminalBridge()
    captured: list[dict[str, object]] = []
    routes = {
        "routes": [{"intent": "deep_code_work", "provider": "codex", "model_alias": "codex-5.4", "reasoning": "high", "role": "builder"}],
        "openclaw": {"present": True, "readable": True, "agents_count": 3, "providers": ["codex", "claude"]},
        "subagent_capabilities": ["route by task type"],
    }
    monkeypatch.setattr(bridge, "_build_agent_routes", lambda: routes)
    monkeypatch.setattr(bridge, "_emit", lambda payload: captured.append(payload))

    asyncio.run(bridge._handle_agent_routes("req-routes"))

    assert captured[0]["type"] == "agent.routes.result"
    assert "content" not in captured[0]
    assert captured[0]["payload"]["version"] == "v1"
    assert captured[0]["payload"]["domain"] == "agent_routes"
    assert captured[0]["payload"]["routes"][0]["intent"] == "deep_code_work"


def test_run_action_command_run_materializes_runtime() -> None:
    bridge = TerminalBridge()
    result = bridge._run_action("command.run", {"command": "/runtime"})
    assert result["ok"] is True
    assert result["target_pane"] == "runtime"
    assert "Runtime Control Plane" in result["output"]


def test_command_target_pane_routes_runtime_to_runtime() -> None:
    bridge = TerminalBridge()
    assert bridge._command_target_pane("runtime") == "runtime"
    assert bridge._command_target_pane("runtime status") == "runtime"


def test_command_target_pane_routes_memory_to_sessions() -> None:
    bridge = TerminalBridge()
    assert bridge._command_target_pane("memory") == "sessions"
    assert bridge._command_target_pane("archive backlog") == "sessions"
    assert bridge._command_target_pane("logs --tail 50") == "sessions"
    assert bridge._command_target_pane("session") == "sessions"
    assert bridge._command_target_pane("sessions recent") == "sessions"


def test_command_target_pane_routes_trishula_to_agents() -> None:
    bridge = TerminalBridge()
    assert bridge._command_target_pane("trishula") == "agents"
    assert bridge._command_target_pane("trishula inbox") == "agents"


def test_command_target_pane_routes_hum_to_agents() -> None:
    bridge = TerminalBridge()
    assert bridge._command_target_pane("hum") == "agents"
    assert bridge._command_target_pane("hum status") == "agents"


def test_handle_command_materializes_model_status() -> None:
    bridge = TerminalBridge()
    output = bridge._materialize_model_command("model", "model:status")
    assert "Available models:" in output
    assert "GLM-5" in output


def test_run_action_agent_route_returns_selected_route() -> None:
    bridge = TerminalBridge()
    result = bridge._run_action("agent.route", {"intent": "deep_code_work"})
    assert result["ok"] is True
    assert result["target_pane"] == "agents"
    assert "Selected route" in result["output"]
    assert "deep_code_work" in result["output"]


def test_render_memory_response_prefers_bootstrap_memory() -> None:
    bridge = TerminalBridge()
    rendered = bridge._render_memory_response(
        {
            "working_memory": "Active mission: stabilize terminal operator shell\nPreferred route: codex:gpt-5.4"
        }
    )
    assert "stabilize terminal operator shell" in rendered
    assert "codex:gpt-5.4" in rendered


def test_run_action_evolution_run_returns_surface() -> None:
    bridge = TerminalBridge()
    result = bridge._run_action("evolution.run", {"command": "/loops"})
    assert result["ok"] is True
    assert result["target_pane"] == "evolution"
    assert "Evolution Surface" in result["output"]
    assert "/loops" in result["output"]


def test_run_action_command_run_materializes_sessions() -> None:
    bridge = TerminalBridge()
    result = bridge._run_action("command.run", {"command": "/memory"})
    assert result["ok"] is True
    assert result["target_pane"] == "sessions"


def test_handle_session_catalog_emits_typed_payload_without_legacy_content(monkeypatch) -> None:
    bridge = TerminalBridge()
    catalog = {
        "count": 1,
        "sessions": [
            {
                "session": {
                    "session_id": "sess-1",
                    "provider_id": "codex",
                    "model_id": "gpt-5.4",
                    "status": "running",
                },
                "replay_ok": True,
                "total_turns": 3,
            }
        ],
    }
    captured: list[dict[str, object]] = []

    def _fake_build_session_catalog(store: object, *, cwd: str | None = None, limit: int = 20) -> dict[str, object]:
        assert store is bridge._session_store
        assert cwd == "/tmp/repo"
        assert limit == 7
        return catalog

    monkeypatch.setattr("dharma_swarm.terminal_bridge.build_session_catalog", _fake_build_session_catalog)
    monkeypatch.setattr(bridge, "_emit", lambda payload: captured.append(payload))

    asyncio.run(bridge._handle_session_catalog("req-1", {"cwd": "/tmp/repo", "limit": 7}))

    assert captured == [
        {
            "type": "session.catalog.result",
            "request_id": "req-1",
            "payload": catalog,
        }
    ]
    assert "catalog" not in captured[0]


def test_handle_session_detail_emits_typed_payload_without_legacy_content(monkeypatch) -> None:
    bridge = TerminalBridge()
    detail = {
        "session": {
            "session_id": "sess-1",
            "provider_id": "codex",
            "model_id": "gpt-5.4",
            "cwd": "/tmp/repo",
            "status": "running",
        },
        "replay_ok": True,
        "replay_issues": [],
        "compaction_preview": {"event_count": 4, "compactable_ratio": 0.25, "protected_event_types": [], "recent_event_types": []},
        "recent_events": [],
    }
    captured: list[dict[str, object]] = []

    def _fake_build_session_detail(
        store: object,
        session_id: str,
        *,
        transcript_limit: int = 80,
    ) -> dict[str, object]:
        assert store is bridge._session_store
        assert session_id == "sess-1"
        assert transcript_limit == 11
        return detail

    monkeypatch.setattr("dharma_swarm.terminal_bridge.build_session_detail", _fake_build_session_detail)
    monkeypatch.setattr(bridge, "_emit", lambda payload: captured.append(payload))

    asyncio.run(bridge._handle_session_detail("req-2", {"session_id": "sess-1", "transcript_limit": 11}))

    assert captured == [
        {
            "type": "session.detail.result",
            "request_id": "req-2",
            "session_id": "sess-1",
            "payload": detail,
        }
    ]
    assert "detail" not in captured[0]


def test_emit_payload_result_keeps_content_optional(monkeypatch) -> None:
    bridge = TerminalBridge()
    captured: list[dict[str, object]] = []
    monkeypatch.setattr(bridge, "_emit", lambda payload: captured.append(payload))

    bridge._emit_payload_result("session.catalog.result", request_id="req-3", payload={"count": 0})

    assert captured == [
        {
            "type": "session.catalog.result",
            "request_id": "req-3",
            "payload": {"count": 0},
        }
    ]


def test_session_start_emits_permission_decision_for_tool_calls(monkeypatch) -> None:
    bridge = TerminalBridge()
    emitted: list[dict[str, object]] = []

    class FakeProfile:
        model_id = "gpt-5.4"

    class FakeCompletionRequest:
        def __init__(self, **kwargs) -> None:
            self.model = kwargs["model"]
            self.kwargs = kwargs

    class FakeAdapter:
        def get_profile(self, _profile) -> FakeProfile:
            return FakeProfile()

        async def stream(self, completion, session_id: str):
            assert session_id == "sess-1"
            assert completion.model == "gpt-5.4"
            yield ToolCallComplete(
                session_id=session_id,
                provider_id="codex",
                tool_call_id="tool-1",
                tool_name="Bash",
                arguments="git status",
                provider_options={"requires_confirmation": True},
            )
            yield ToolResult(
                session_id=session_id,
                provider_id="codex",
                tool_call_id="tool-1",
                tool_name="Bash",
                content="ok",
                is_error=False,
            )

        async def cancel(self) -> None:
            return None

    monkeypatch.setattr("dharma_swarm.terminal_bridge.build_permission_decision_payload", lambda event: {
        "version": "v1",
        "domain": "permission_decision",
        "action_id": "perm-123",
        "tool_name": event.tool_name,
        "risk": "shell_or_network",
        "decision": "require_approval",
        "rationale": "Bash is not classified as safe and remains operator-gated",
        "policy_source": "legacy-governance",
        "requires_confirmation": True,
        "command_prefix": "git status",
        "metadata": {
            "tool_call_id": event.tool_call_id,
            "provider_id": event.provider_id,
            "session_id": event.session_id,
        },
    })
    monkeypatch.setattr(bridge, "_emit", lambda payload: emitted.append(payload))
    bridge._adapters = {"codex": FakeAdapter()}
    bridge._adapter_boot_error = None
    bridge._completion_request_cls = FakeCompletionRequest

    asyncio.run(
        bridge._handle_session_start(
            "req-1",
            {
                "session_id": "sess-1",
                "provider": "codex",
                "model": "gpt-5.4",
                "prompt": "please run the repo check",
                "bootstrap": {"intent": {"kind": "chat"}, "system_prompt": "bootstrap"},
            },
        )
    )

    assert [event["type"] for event in emitted] == [
        "session.ack",
        "permission.decision",
        "tool_call_complete",
        "tool_result",
    ]
    assert emitted[1]["payload"]["metadata"]["tool_call_id"] == "tool-1"
    assert emitted[1]["payload"]["metadata"]["session_id"] == "sess-1"
    assert emitted[1]["payload"]["decision"] == "require_approval"


def test_handle_action_run_emits_permission_resolution_before_action_result(monkeypatch) -> None:
    bridge = TerminalBridge()
    emitted: list[dict[str, object]] = []
    monkeypatch.setattr(bridge, "_emit", lambda payload: emitted.append(payload))
    recorded: list[OperatorAction] = []

    async def fake_record_runtime(payload: dict[str, object]) -> dict[str, object]:
        recorded.append(
            OperatorAction(
                action_id="approval_perm-123",
                action_name="approval.resolve",
                actor="operator",
                session_id="sess-1",
                reason=str(payload.get("summary", "") or ""),
                payload=dict(payload),
            )
        )
        return {
            "enforcement_state": "runtime_recorded",
            "runtime_action_id": "approval_perm-123",
            "runtime_event_id": "evt_perm_123",
            "outcome": "runtime_applied",
        }

    monkeypatch.setattr(bridge, "_record_runtime_approval_resolution", fake_record_runtime)

    asyncio.run(
        bridge._handle_action_run(
            "req-9",
            {
                "action_type": "approval.resolve",
                "action_id": "perm-123",
                "resolution": "approved",
                "metadata": {"session_id": "sess-1"},
            },
        )
    )

    assert [event["type"] for event in emitted] == ["permission.resolution", "permission.outcome", "action.result"]
    assert emitted[0]["payload"]["domain"] == "permission_resolution"
    assert emitted[0]["payload"]["action_id"] == "perm-123"
    assert emitted[0]["payload"]["resolution"] == "approved"
    assert emitted[0]["payload"]["enforcement_state"] == "runtime_recorded"
    assert emitted[0]["payload"]["metadata"]["runtime_action_id"] == "approval_perm-123"
    assert emitted[0]["payload"]["metadata"]["runtime_event_id"] == "evt_perm_123"
    assert emitted[1]["payload"]["domain"] == "permission_outcome"
    assert emitted[1]["payload"]["action_id"] == "perm-123"
    assert emitted[1]["payload"]["outcome"] == "runtime_applied"
    assert emitted[1]["payload"]["metadata"]["runtime_event_id"] == "evt_perm_123"
    assert emitted[2]["action_type"] == "approval.resolve"
    assert emitted[2]["target_pane"] == "approvals"
    assert recorded[0].action_name == "approval.resolve"


def test_record_runtime_approval_resolution_writes_runtime_action_and_event(tmp_path, monkeypatch) -> None:
    runtime_db = tmp_path / "runtime.db"
    monkeypatch.setattr(terminal_bridge_module, "DEFAULT_RUNTIME_DB", runtime_db)
    bridge = TerminalBridge()

    result = asyncio.run(
        bridge._record_runtime_approval_resolution(
            {
                "action_id": "perm-runtime-1",
                "resolution": "approved",
                "actor": "operator",
                "summary": "approved perm-runtime-1",
                "metadata": {
                    "session_id": "sess-runtime-1",
                    "task_id": "task-runtime-1",
                    "run_id": "run-runtime-1",
                },
            }
        )
    )

    assert result["enforcement_state"] == "runtime_recorded"
    assert result["outcome"] == "runtime_applied"
    assert result["runtime_action_id"] == "approval_perm-runtime-1"
    assert str(result["runtime_event_id"]).startswith("evt_")

    runtime_state = RuntimeStateStore(runtime_db)
    action = asyncio.run(runtime_state.get_operator_action("approval_perm-runtime-1"))
    assert action is not None
    assert action.action_name == "approval.resolve"
    assert action.session_id == "sess-runtime-1"

    events = asyncio.run(runtime_state.list_session_events(session_id="sess-runtime-1", limit=10))
    assert len(events) == 1
    assert events[0].event_name == "approval.resolve.runtime_applied"
    assert events[0].ledger_kind == "operator_control"
    assert events[0].payload["enforcement_state"] == "runtime_recorded"
    assert events[0].payload["runtime_action_id"] == "approval_perm-runtime-1"
    assert events[0].payload["outcome"] == "runtime_applied"


def test_record_runtime_approval_resolution_classifies_denial_as_runtime_rejected(tmp_path, monkeypatch) -> None:
    runtime_db = tmp_path / "runtime.db"
    monkeypatch.setattr(terminal_bridge_module, "DEFAULT_RUNTIME_DB", runtime_db)
    bridge = TerminalBridge()

    result = asyncio.run(
        bridge._record_runtime_approval_resolution(
            {
                "action_id": "perm-runtime-2",
                "resolution": "denied",
                "actor": "operator",
                "summary": "denied perm-runtime-2",
                "metadata": {
                    "session_id": "sess-runtime-2",
                    "task_id": "task-runtime-2",
                    "run_id": "run-runtime-2",
                },
            }
        )
    )

    assert result["enforcement_state"] == "runtime_recorded"
    assert result["outcome"] == "runtime_rejected"

    runtime_state = RuntimeStateStore(runtime_db)
    events = asyncio.run(runtime_state.list_session_events(session_id="sess-runtime-2", limit=10))
    assert len(events) == 1
    assert events[0].event_name == "approval.resolve.runtime_rejected"
    assert events[0].payload["outcome"] == "runtime_rejected"


def test_record_permission_payload_appends_transcript_events() -> None:
    bridge = TerminalBridge()
    session_id = bridge._session_store.create_session(
        session_id="sess-record",
        provider_id="codex",
        model_id="gpt-5.4",
        cwd="/repo",
    )

    bridge._record_permission_payload(
        {
            "version": "v1",
            "domain": "permission_decision",
            "action_id": "perm-record-1",
            "tool_name": "Bash",
            "risk": "shell_or_network",
            "decision": "require_approval",
            "rationale": "gated",
            "policy_source": "legacy-governance",
            "requires_confirmation": True,
            "metadata": {"session_id": session_id, "provider_id": "codex"},
        }
    )
    bridge._record_permission_payload(
        {
            "version": "v1",
            "domain": "permission_resolution",
            "action_id": "perm-record-1",
            "resolution": "approved",
            "resolved_at": "2026-04-02T00:10:00Z",
            "actor": "operator",
            "summary": "approved perm-record-1",
            "enforcement_state": "recorded_only",
            "metadata": {"session_id": session_id, "provider_id": "codex"},
        }
    )

    events = bridge._session_store.load_transcript(
        session_id,
        include_types={"permission_decision", "permission_resolution"},
    )
    audit = bridge._session_store.load_audit(
        session_id,
        include_domains={"permission_decision", "permission_resolution"},
    )

    assert len(events) == 2
    assert events[0].type == "permission_decision"
    assert events[1].type == "permission_resolution"
    assert audit == []
