"""JSON stdio bridge for a future Bun/Ink terminal frontend.

This module keeps Python as the runtime/core layer while exposing a narrow
provider-agnostic event protocol to a terminal UI implemented elsewhere.
It is intentionally independent of Textual so the operator shell can be
replaced without rewriting provider adapters and command handling.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, is_dataclass
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
import sys
import uuid
from typing import Any

from dharma_swarm.context import build_orientation_packet
from dharma_swarm.cascade import get_registered_domains
from dharma_swarm.operator_views import OperatorViews
from dharma_swarm.operator_core import (
    build_permission_history_payload,
    build_permission_decision_payload,
    build_permission_outcome_payload,
    build_permission_resolution_payload,
    build_agent_routes_payload,
    build_routing_decision_payload,
    build_runtime_snapshot_payload,
    build_workspace_snapshot_payload,
)
from dharma_swarm.orientation_packet import DirectiveSummary, RuntimeStateSummary
from dharma_swarm.provider_matrix import build_default_matrix_targets
from dharma_swarm.runtime_state import DEFAULT_RUNTIME_DB, OperatorAction, RuntimeStateStore, SessionEventRecord
from dharma_swarm.models import ProviderType
from dharma_swarm.tui import model_routing
from dharma_swarm.terminal_commands import system_commands as system_commands_module
from dharma_swarm.terminal_commands.system_commands import SystemCommandHandler
from dharma_swarm.tui_helpers import build_runtime_status_text
from dharma_swarm.workspace_topology import build_workspace_topology
from dharma_swarm.operator_core import build_session_catalog, build_session_detail
from dharma_swarm.operator_core.session_store import SessionStore
from dharma_swarm.terminal_control import load_terminal_control_state
from dharma_swarm.terminal_engine.events import ToolCallComplete
from dharma_swarm.terminal_engine.events import PermissionDecisionEvent, PermissionOutcomeEvent, PermissionResolutionEvent


def _json_default(value: object) -> object:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, set):
        return sorted(value)
    return str(value)


def _bridge_provider_id(provider: ProviderType) -> str | None:
    if provider == ProviderType.CODEX:
        return "codex"
    if provider in {ProviderType.ANTHROPIC, ProviderType.CLAUDE_CODE}:
        return "claude"
    if provider in {ProviderType.OPENROUTER, ProviderType.OPENROUTER_FREE}:
        return "openrouter"
    return None


def _target_alias(model: str) -> str:
    normalized = model.split("/")[-1].split(":")[0].strip().lower()
    normalized = re.sub(r"[^a-z0-9.+-]+", "-", normalized)
    return normalized.strip("-") or "model"


class TerminalBridge:
    """Minimal stdio protocol server for a terminal frontend."""

    def __init__(self) -> None:
        self._commands = SystemCommandHandler()
        self._adapters: dict[str, Any] = {}
        self._adapter_boot_error: str | None = None
        self._completion_request_cls: Any | None = None
        self._active_session_id: str | None = None
        self._active_provider_id: str | None = None
        self._active_model_id: str | None = None
        self._repo_root = Path.cwd().resolve()
        self._package_root = Path(__file__).resolve().parent
        self._state_dir = Path.home() / ".dharma" / "terminal"
        self._session_store = SessionStore()
        self._ensure_adapters()

    def _load_repo_guidance(self, limit_chars: int = 2400) -> str:
        guidance_path = self._repo_root / "CLAUDE.md"
        try:
            text = guidance_path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
        if not text:
            return ""
        sections = self._summarize_repo_guidance(text)
        text = sections or text
        if len(text) <= limit_chars:
            return text
        return text[: limit_chars - 1].rstrip() + "…"

    def _summarize_repo_guidance(self, text: str) -> str:
        lines = text.splitlines()
        kept: list[str] = []
        current_heading = ""
        allowed_headings = {
            "## Behavioral Rules (Always Enforced)",
            "## File Organization",
            "## Project Architecture",
            "## CLI Entry Points",
            "## Security Rules",
        }
        for line in lines:
            stripped = line.rstrip()
            if stripped.startswith("## "):
                current_heading = stripped
                if current_heading in allowed_headings:
                    kept.append(stripped)
                continue
            if current_heading not in allowed_headings:
                continue
            if stripped.startswith("- ") or stripped.startswith("```") or stripped.startswith("dgc ") or stripped.startswith("uvicorn ") or stripped.startswith("bash "):
                kept.append(stripped)
        return "\n".join(line for line in kept if line)

    def _load_session_context_hint(self) -> str:
        try:
            from dharma_swarm.claude_hooks import session_context

            return session_context().strip()
        except Exception:
            return ""

    def _memory_path(self) -> Path:
        return self._state_dir / "working_memory.json"

    def _load_working_memory(self) -> dict[str, Any]:
        path = self._memory_path()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {
                "recent_turns": [],
                "recent_actions": [],
                "active_mission": "",
                "preferred_route": "",
                "updated_at": "",
            }
        if not isinstance(payload, dict):
            return {"recent_turns": [], "recent_actions": [], "active_mission": "", "preferred_route": "", "updated_at": ""}
        payload.setdefault("recent_turns", [])
        payload.setdefault("recent_actions", [])
        payload.setdefault("active_mission", "")
        payload.setdefault("preferred_route", "")
        payload.setdefault("updated_at", "")
        return payload

    def _save_working_memory(self, payload: dict[str, Any]) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._memory_path().write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def _remember_turn(self, *, prompt: str, intent: dict[str, Any], route: str, active_tab: str) -> None:
        memory = self._load_working_memory()
        self._apply_turn_to_memory(memory, prompt=prompt, intent=intent, route=route, active_tab=active_tab)
        self._save_working_memory(memory)

    def _apply_turn_to_memory(self, memory: dict[str, Any], *, prompt: str, intent: dict[str, Any], route: str, active_tab: str) -> dict[str, Any]:
        turns = memory.get("recent_turns", [])
        if not isinstance(turns, list):
            turns = []
        turns.append(
            {
                "prompt": prompt,
                "intent": str(intent.get("kind", "chat")),
                "route": route,
                "active_tab": active_tab,
            }
        )
        memory["recent_turns"] = turns[-8:]
        if str(intent.get("kind", "")) in {"agent", "evolution", "command"}:
            memory["active_mission"] = prompt[:200]
        memory["preferred_route"] = route
        return memory

    def _remember_action(self, summary: str) -> None:
        memory = self._load_working_memory()
        actions = memory.get("recent_actions", [])
        if not isinstance(actions, list):
            actions = []
        actions.append(summary)
        memory["recent_actions"] = [str(item) for item in actions][-8:]
        self._save_working_memory(memory)

    def _render_working_memory(self, memory: dict[str, Any]) -> str:
        turns = memory.get("recent_turns", [])
        actions = memory.get("recent_actions", [])
        active_mission = str(memory.get("active_mission", "") or "").strip() or "none"
        preferred_route = str(memory.get("preferred_route", "") or "").strip() or "none"
        lines = [
            f"Active mission: {active_mission}",
            f"Preferred route: {preferred_route}",
        ]
        if isinstance(turns, list) and turns:
            lines.append("Recent turns:")
            for item in turns[-4:]:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    "- {intent} | {route} | {prompt}".format(
                        intent=str(item.get("intent", "chat")),
                        route=str(item.get("route", "unknown")),
                        prompt=str(item.get("prompt", ""))[:100],
                    )
                )
        if isinstance(actions, list) and actions:
            lines.append("Recent actions:")
            for action in actions[-4:]:
                lines.append(f"- {str(action)[:120]}")
        return "\n".join(lines)

    def _ensure_adapters(self) -> None:
        if self._adapters or self._adapter_boot_error is not None:
            return
        try:
            from dharma_swarm.terminal_adapters import (
                ClaudeAdapter,
                CodexAdapter,
                CompletionRequest,
                OpenRouterAdapter,
            )

            self._adapters = {
                "claude": ClaudeAdapter(),
                "codex": CodexAdapter(),
                "openrouter": OpenRouterAdapter(),
            }
            self._completion_request_cls = CompletionRequest
        except Exception as exc:
            self._adapter_boot_error = f"{type(exc).__name__}: {exc}"

    def _available_provider_ids(self) -> set[str]:
        return set(self._adapters)

    async def close(self) -> None:
        for adapter in self._adapters.values():
            await adapter.close()

    async def run_stdio(self) -> int:
        self._emit(
            {
                "type": "bridge.ready",
                "schema_version": 1,
                "protocol": "dharma-terminal-bridge",
            }
        )

        while True:
            raw_line = await asyncio.to_thread(sys.stdin.readline)
            if raw_line == "":
                break
            line = raw_line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError as exc:
                self._emit(
                    {
                        "type": "bridge.error",
                        "code": "invalid_json",
                        "message": exc.msg,
                    }
                )
                continue
            if not isinstance(request, dict):
                self._emit(
                    {
                        "type": "bridge.error",
                        "code": "invalid_request",
                        "message": "request must be a JSON object",
                    }
                )
                continue
            await self._handle_request(request)
        return 0

    async def _handle_request(self, request: dict[str, Any]) -> None:
        request_id = str(request.get("id", "") or "")
        request_type = str(request.get("type", "") or "")

        if request_type == "handshake":
            await self._handle_handshake(request_id)
            return
        if request_type == "command.run":
            await self._handle_command(request_id, request)
            return
        if request_type == "action.run":
            await self._handle_action_run(request_id, request)
            return
        if request_type == "command.graph":
            await self._handle_command_graph(request_id)
            return
        if request_type == "command.registry":
            await self._handle_command_registry(request_id)
            return
        if request_type == "intent.resolve":
            await self._handle_intent_resolve(request_id, request)
            return
        if request_type == "model.policy":
            await self._handle_model_policy(request_id, request)
            return
        if request_type == "operator.snapshot":
            await self._handle_operator_snapshot(request_id)
            return
        if request_type == "agent.routes":
            await self._handle_agent_routes(request_id)
            return
        if request_type == "evolution.surface":
            await self._handle_evolution_surface(request_id)
            return
        if request_type == "session.bootstrap":
            await self._handle_session_bootstrap(request_id, request)
            return
        if request_type == "session.start":
            await self._handle_session_start(request_id, request)
            return
        if request_type == "session.catalog":
            await self._handle_session_catalog(request_id, request)
            return
        if request_type == "session.detail":
            await self._handle_session_detail(request_id, request)
            return
        if request_type == "session.cancel":
            await self._handle_session_cancel(request_id)
            return
        if request_type == "status":
            self._emit(
                {
                    "type": "status.result",
                    "request_id": request_id,
                    "active_session_id": self._active_session_id,
                    "active_provider": self._active_provider_id,
                    "providers": sorted(self._adapters),
                }
            )
            return
        if request_type == "workspace.snapshot":
            await self._handle_workspace_snapshot(request_id)
            return
        if request_type == "ontology.snapshot":
            await self._handle_ontology_snapshot(request_id)
            return
        if request_type == "runtime.snapshot":
            await self._handle_runtime_snapshot(request_id)
            return
        if request_type == "permission.history":
            await self._handle_permission_history(request_id, request)
            return

        self._emit(
            {
                "type": "bridge.error",
                "request_id": request_id,
                "code": "unknown_request_type",
                "message": request_type or "missing request type",
            }
        )

    async def _handle_handshake(self, request_id: str) -> None:
        providers: list[dict[str, Any]] = []
        adapter_error = self._adapter_boot_error
        if adapter_error is None:
            for provider_id, adapter in self._adapters.items():
                models = []
                for profile in await adapter.list_models():
                    models.append(
                        {
                            "id": profile.model_id,
                            "display_name": profile.display_name,
                            "capabilities": sorted(cap.name.lower() for cap in type(profile.capabilities) if profile.supports(cap)),
                        }
                    )
                providers.append(
                    {
                        "provider_id": provider_id,
                        "default_model": adapter.get_profile(None).model_id,
                        "models": models,
                    }
                )
        self._emit(
            {
                "type": "handshake.result",
                "request_id": request_id,
                "providers": providers,
                "default_provider": "codex" if "codex" in self._adapters else (sorted(self._adapters)[0] if self._adapters else ""),
                "legacy_terminal": {
                    "stack": "python-textual",
                    "replacement_target": "bun-ink",
                },
                "adapter_boot_error": adapter_error,
            }
        )

    async def _handle_workspace_snapshot(self, request_id: str) -> None:
        summary = await asyncio.to_thread(self._load_repo_xray)
        git_summary = await asyncio.to_thread(self._build_git_summary)
        topology = await asyncio.to_thread(build_workspace_topology, self._repo_root.parent)
        payload = build_workspace_snapshot_payload(
            repo_root=str(self._repo_root),
            git_summary=git_summary,
            topology=topology,
            summary=summary,
        )
        content = await asyncio.to_thread(
            self._build_workspace_snapshot_from_parts,
            summary,
            git_summary,
            topology,
        )
        self._emit_payload_result(
            "workspace.snapshot.result",
            request_id=request_id,
            payload=payload,
        )

    async def _handle_ontology_snapshot(self, request_id: str) -> None:
        content = await asyncio.to_thread(self._build_ontology_snapshot)
        self._emit(
            {
                "type": "ontology.snapshot.result",
                "request_id": request_id,
                "content": content,
            }
        )

    async def _handle_runtime_snapshot(self, request_id: str) -> None:
        operator_snapshot = await self._build_operator_snapshot()
        runtime_payload = build_runtime_snapshot_payload(
            operator_snapshot,
            repo_root=str(self._repo_root),
            bridge_status="connected",
            supervisor_preview=load_terminal_control_state(self._repo_root),
        )
        content = await asyncio.to_thread(self._build_runtime_snapshot)
        self._emit_payload_result(
            "runtime.snapshot.result",
            request_id=request_id,
            payload=runtime_payload,
        )

    async def _handle_permission_history(self, request_id: str, request: dict[str, Any]) -> None:
        limit = int(request.get("limit", 50) or 50)
        payload = await asyncio.to_thread(build_permission_history_payload, self._session_store, limit=limit)
        self._emit_payload_result(
            "permission.history.result",
            request_id=request_id,
            payload=payload,
        )

    async def _handle_command(self, request_id: str, request: dict[str, Any]) -> None:
        raw_command = str(request.get("command", "") or "").strip()
        if raw_command.startswith("/"):
            raw_command = raw_command[1:]
        output, action = self._commands.handle(raw_command)
        if not str(output).strip() and isinstance(action, str) and action.startswith("model:"):
            output = self._materialize_model_command(raw_command, action)
        if not str(output).strip() and isinstance(action, str) and action.startswith("async:"):
            output = self._materialize_async_command(raw_command, action)
        self._emit(
            {
                "type": "command.result",
                "request_id": request_id,
                "command": raw_command,
                "target_pane": self._command_target_pane(raw_command),
                "output": output,
                "action": action,
            }
        )

    async def _handle_action_run(self, request_id: str, request: dict[str, Any]) -> None:
        action_type = str(request.get("action_type", "") or "").strip().lower()
        result = await asyncio.to_thread(self._run_action, action_type, request)
        if action_type == "approval.resolve" and isinstance(result.get("payload"), dict):
            runtime_enforcement = await self._record_runtime_approval_resolution(result["payload"])
            result["payload"]["enforcement_state"] = runtime_enforcement["enforcement_state"]
            metadata = result["payload"].get("metadata")
            if isinstance(metadata, dict):
                if runtime_enforcement.get("runtime_action_id"):
                    metadata["runtime_action_id"] = runtime_enforcement["runtime_action_id"]
                if runtime_enforcement.get("runtime_event_id"):
                    metadata["runtime_event_id"] = runtime_enforcement["runtime_event_id"]
            outcome_payload = build_permission_outcome_payload(
                action_id=str(result["payload"].get("action_id", "") or ""),
                outcome=str(runtime_enforcement.get("outcome") or runtime_enforcement["enforcement_state"]),
                metadata=metadata if isinstance(metadata, dict) else {},
            )
            self._record_permission_payload(result["payload"])
            self._record_permission_payload(outcome_payload)
            self._emit_payload_result(
                "permission.resolution",
                request_id=request_id,
                payload=result["payload"],
            )
            self._emit_payload_result(
                "permission.outcome",
                request_id=request_id,
                payload=outcome_payload,
            )
        result.update(
            {
                "type": "action.result",
                "request_id": request_id,
                "action_type": action_type,
            }
        )
        self._emit(result)

    async def _record_runtime_approval_resolution(self, payload: dict[str, Any]) -> dict[str, Any]:
        metadata = payload.get("metadata")
        metadata_record = metadata if isinstance(metadata, dict) else {}
        action_id = str(payload.get("action_id", "") or "").strip()
        resolution = str(payload.get("resolution", "") or "").strip().lower()
        if not action_id:
            return {"enforcement_state": "recorded_only"}
        try:
            runtime_state = RuntimeStateStore(db_path=DEFAULT_RUNTIME_DB)
            action = await runtime_state.record_operator_action(
                OperatorAction(
                    action_id=f"approval_{action_id}",
                    action_name="approval.resolve",
                    actor=str(payload.get("actor", "") or "operator"),
                    session_id=str(metadata_record.get("session_id", "") or ""),
                    task_id=str(metadata_record.get("task_id", "") or ""),
                    run_id=str(metadata_record.get("run_id", "") or ""),
                    reason=str(payload.get("summary", "") or f"approval resolution {action_id}"),
                    payload=dict(payload),
                )
            )
            runtime_outcome = self._classify_runtime_approval_outcome(resolution)
            runtime_event = await runtime_state.record_session_event(
                SessionEventRecord(
                    event_id=f"evt_{uuid.uuid4().hex[:16]}",
                    session_id=str(metadata_record.get("session_id", "") or ""),
                    ledger_kind="operator_control",
                    event_name=f"approval.resolve.{runtime_outcome}",
                    task_id=str(metadata_record.get("task_id", "") or ""),
                    run_id=str(metadata_record.get("run_id", "") or ""),
                    agent_id=str(payload.get("actor", "") or "operator"),
                    summary=str(payload.get("summary", "") or f"approval resolution {action_id}"),
                    event_text=str(payload.get("summary", "") or f"approval resolution {action_id}"),
                    payload={
                        "action_id": action_id,
                        "resolution": resolution,
                        "enforcement_state": "runtime_recorded",
                        "runtime_action_id": action.action_id,
                        "outcome": runtime_outcome,
                    },
                )
            )
            return {
                "enforcement_state": "runtime_recorded",
                "outcome": runtime_outcome,
                "runtime_action_id": action.action_id,
                "runtime_event_id": runtime_event.event_id,
            }
        except Exception:
            return {"enforcement_state": "recorded_only", "outcome": "runtime_record_failed"}

    @staticmethod
    def _classify_runtime_approval_outcome(resolution: str) -> str:
        normalized = str(resolution or "").strip().lower()
        if normalized in {"approved", "resolved"}:
            return "runtime_applied"
        if normalized in {"denied", "dismissed"}:
            return "runtime_rejected"
        return "runtime_recorded"

    async def _handle_intent_resolve(self, request_id: str, request: dict[str, Any]) -> None:
        prompt = str(request.get("prompt", "") or "").strip()
        if not prompt:
            self._emit(
                {
                    "type": "bridge.error",
                    "request_id": request_id,
                    "code": "missing_prompt",
                    "message": "intent.resolve requires a prompt",
                }
            )
            return
        intent = await asyncio.to_thread(self._resolve_prompt_intent, prompt)
        self._emit(
            {
                "type": "intent.result",
                "request_id": request_id,
                "intent": intent,
            }
        )

    async def _handle_command_graph(self, request_id: str) -> None:
        graph = await asyncio.to_thread(self._build_command_graph_summary)
        self._emit(
            {
                "type": "command.graph.result",
                "request_id": request_id,
                "graph": graph,
                "content": self._render_command_graph_text(graph),
            }
        )

    async def _handle_command_registry(self, request_id: str) -> None:
        registry = await asyncio.to_thread(self._build_command_registry)
        self._emit(
            {
                "type": "command.registry.result",
                "request_id": request_id,
                "registry": registry,
                "content": self._render_command_registry_text(registry),
            }
        )

    async def _handle_operator_snapshot(self, request_id: str) -> None:
        snapshot = await self._build_operator_snapshot()
        self._emit(
            {
                "type": "operator.snapshot.result",
                "request_id": request_id,
                "snapshot": snapshot,
                "content": self._render_operator_snapshot_text(snapshot),
            }
        )

    async def _handle_model_policy(self, request_id: str, request: dict[str, Any]) -> None:
        selected_provider = str(request.get("provider", "") or "codex").strip().lower()
        selected_model = str(request.get("model", "") or "").strip() or model_routing.default_target().model_id
        strategy = model_routing.resolve_strategy(str(request.get("strategy", "") or "")) or "responsive"
        policy = await asyncio.to_thread(
            self._build_model_policy_summary,
            selected_provider=selected_provider,
            selected_model=selected_model,
            strategy=strategy,
        )
        self._emit_payload_result(
            "model.policy.result",
            request_id=request_id,
            payload=build_routing_decision_payload(policy),
            policy=policy,
        )

    async def _handle_agent_routes(self, request_id: str) -> None:
        routes = await asyncio.to_thread(self._build_agent_routes)
        self._emit_payload_result(
            "agent.routes.result",
            request_id=request_id,
            payload=build_agent_routes_payload(routes),
            routes=routes,
        )

    async def _handle_evolution_surface(self, request_id: str) -> None:
        surface = await asyncio.to_thread(self._build_evolution_surface)
        self._emit(
            {
                "type": "evolution.surface.result",
                "request_id": request_id,
                "surface": surface,
                "content": self._render_evolution_surface_text(surface),
            }
        )

    async def _handle_session_bootstrap(self, request_id: str, request: dict[str, Any]) -> None:
        prompt = str(request.get("prompt", "") or "").strip()
        if not prompt:
            self._emit(
                {
                    "type": "bridge.error",
                    "request_id": request_id,
                    "code": "missing_prompt",
                    "message": "session.bootstrap requires a prompt",
                }
            )
            return
        payload = await asyncio.to_thread(self._build_session_bootstrap, request)
        payload.update(
            {
                "type": "session.bootstrap.result",
                "request_id": request_id,
            }
        )
        self._emit(payload)

    async def _handle_session_start(self, request_id: str, request: dict[str, Any]) -> None:
        if self._adapter_boot_error is not None or self._completion_request_cls is None:
            self._emit(
                {
                    "type": "bridge.error",
                    "request_id": request_id,
                    "code": "adapter_boot_failed",
                    "message": self._adapter_boot_error or "adapter runtime unavailable",
                }
            )
            return
        provider_id = str(request.get("provider", "") or "codex").strip().lower()
        adapter = self._adapters.get(provider_id)
        if adapter is None:
            self._emit(
                {
                    "type": "bridge.error",
                    "request_id": request_id,
                    "code": "unknown_provider",
                    "message": provider_id,
                }
            )
            return

        prompt = str(request.get("prompt", "") or "").strip()
        if not prompt:
            self._emit(
                {
                    "type": "bridge.error",
                    "request_id": request_id,
                    "code": "missing_prompt",
                    "message": "session.start requires a prompt",
                }
            )
            return
        bootstrap = request.get("bootstrap")
        if not isinstance(bootstrap, dict):
            bootstrap = await asyncio.to_thread(self._build_session_bootstrap, request)
        intent = bootstrap.get("intent") if isinstance(bootstrap, dict) else None
        if isinstance(intent, dict) and intent.get("kind") == "command" and intent.get("auto_execute"):
            self._emit(
                {
                    "type": "intent.result",
                    "request_id": request_id,
                    "intent": intent,
                }
            )
            await self._handle_command(
                request_id,
                {
                    "command": str(intent.get("command", "")),
                },
            )
            self._emit(
                {
                    "type": "session_end",
                    "request_id": request_id,
                    "success": True,
                    "session_id": None,
                }
            )
            return
        if isinstance(intent, dict) and intent.get("kind") == "identity":
            self._emit(
                {
                    "type": "assistant",
                    "request_id": request_id,
                    "message": self._render_identity_response(bootstrap if isinstance(bootstrap, dict) else {}),
                }
            )
            self._emit(
                {
                    "type": "session_end",
                    "request_id": request_id,
                    "success": True,
                    "session_id": None,
                }
            )
            return
        if isinstance(intent, dict) and intent.get("kind") == "memory":
            self._emit(
                {
                    "type": "assistant",
                    "request_id": request_id,
                    "message": self._render_memory_response(bootstrap if isinstance(bootstrap, dict) else None),
                }
            )
            self._emit(
                {
                    "type": "session_end",
                    "request_id": request_id,
                    "success": True,
                    "session_id": None,
                }
            )
            return

        session_id = str(request.get("session_id", "") or uuid.uuid4().hex)
        self._active_session_id = session_id
        self._active_provider_id = provider_id
        self._active_model_id = str(request.get("model", "") or adapter.get_profile(None).model_id)
        self._emit(
            {
                "type": "session.ack",
                "request_id": request_id,
                "session_id": session_id,
                "provider": provider_id,
                "model": self._active_model_id,
            }
        )

        completion = self._completion_request_cls(
            messages=[{"role": "user", "content": prompt}],
            model=str(request.get("model", "") or adapter.get_profile(None).model_id),
            system_prompt=str(request.get("system_prompt", "") or bootstrap.get("system_prompt", "") or "") or None,
            enable_thinking=bool(request.get("enable_thinking", False)),
            resume_session_id=str(request.get("resume_session_id", "") or "") or None,
            provider_options=dict(request.get("provider_options", {}) or {}),
        )

        try:
            async for event in adapter.stream(completion, session_id=session_id):
                if isinstance(event, ToolCallComplete):
                    self._emit_permission_decision(request_id, event)
                payload = asdict(event)
                payload["request_id"] = request_id
                self._emit(payload)
        finally:
            self._active_session_id = None

    async def _handle_session_catalog(self, request_id: str, request: dict[str, Any]) -> None:
        cwd = str(request.get("cwd", "") or "").strip() or None
        limit = int(request.get("limit", 20) or 20)
        catalog = await asyncio.to_thread(
            build_session_catalog,
            self._session_store,
            cwd=cwd,
            limit=limit,
        )
        self._emit_payload_result(
            "session.catalog.result",
            request_id=request_id,
            payload=catalog,
        )

    async def _handle_session_detail(self, request_id: str, request: dict[str, Any]) -> None:
        session_id = str(request.get("session_id", "") or "").strip()
        if not session_id:
            self._emit(
                {
                    "type": "bridge.error",
                    "request_id": request_id,
                    "code": "missing_session_id",
                    "message": "session.detail requires a session_id",
                }
            )
            return
        try:
            detail = await asyncio.to_thread(
                build_session_detail,
                self._session_store,
                session_id,
                transcript_limit=int(request.get("transcript_limit", 80) or 80),
            )
        except Exception as exc:
            self._emit(
                {
                    "type": "bridge.error",
                    "request_id": request_id,
                    "code": "session_detail_failed",
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )
            return
        self._emit_payload_result(
            "session.detail.result",
            request_id=request_id,
            payload=detail,
            session_id=session_id,
        )

    async def _handle_session_cancel(self, request_id: str) -> None:
        cancelled = False
        if self._active_provider_id:
            adapter = self._adapters.get(self._active_provider_id)
            if adapter is not None:
                await adapter.cancel()
                cancelled = True
        self._emit(
            {
                "type": "session.cancelled",
                "request_id": request_id,
                "cancelled": cancelled,
                "session_id": self._active_session_id,
            }
        )

    def _emit(self, payload: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(payload, default=_json_default) + "\n")
        sys.stdout.flush()

    def _emit_payload_result(
        self,
        event_type: str,
        *,
        request_id: str,
        payload: dict[str, Any],
        content: str | None = None,
        **extra: Any,
    ) -> None:
        event: dict[str, Any] = {
            "type": event_type,
            "request_id": request_id,
            "payload": payload,
        }
        if content is not None:
            event["content"] = content
        if extra:
            event.update(extra)
        self._emit(event)

    def _emit_permission_decision(self, request_id: str, event: ToolCallComplete) -> None:
        payload = build_permission_decision_payload(event)
        if payload.get("decision") == "allow" and not bool(payload.get("requires_confirmation")):
            return
        self._record_permission_payload(payload)
        self._emit_payload_result("permission.decision", request_id=request_id, payload=payload)

    def _record_permission_payload(self, payload: dict[str, Any]) -> None:
        metadata = payload.get("metadata")
        metadata_record = metadata if isinstance(metadata, dict) else {}
        session_id = str(metadata_record.get("session_id", "") or "").strip()
        if not session_id:
            return
        created_at = str(payload.get("resolved_at", "") or datetime.now(timezone.utc).isoformat())
        domain = str(payload.get("domain", "") or "")
        if domain == "permission_decision":
            self._session_store.append_event(
                session_id,
                PermissionDecisionEvent(
                    session_id=session_id,
                    provider_id=str(metadata_record.get("provider_id", "") or ""),
                    action_id=str(payload.get("action_id", "") or ""),
                    tool_name=str(payload.get("tool_name", "") or ""),
                    risk=str(payload.get("risk", "") or ""),
                    decision=str(payload.get("decision", "") or ""),
                    rationale=str(payload.get("rationale", "") or ""),
                    policy_source=str(payload.get("policy_source", "") or ""),
                    requires_confirmation=bool(payload.get("requires_confirmation")),
                    command_prefix=str(payload.get("command_prefix", "") or "") or None,
                    metadata=dict(metadata_record),
                ),
            )
            return
        if domain == "permission_resolution":
            self._session_store.append_event(
                session_id,
                PermissionResolutionEvent(
                    session_id=session_id,
                    provider_id=str(metadata_record.get("provider_id", "") or ""),
                    action_id=str(payload.get("action_id", "") or ""),
                    resolution=str(payload.get("resolution", "") or ""),
                    resolved_at=created_at,
                    actor=str(payload.get("actor", "") or "operator"),
                    summary=str(payload.get("summary", "") or ""),
                    note=str(payload.get("note", "") or "") or None,
                    enforcement_state=str(payload.get("enforcement_state", "") or "recorded_only"),
                    metadata=dict(metadata_record),
                ),
            )
            return
        if domain == "permission_outcome":
            self._session_store.append_event(
                session_id,
                PermissionOutcomeEvent(
                    session_id=session_id,
                    provider_id=str(metadata_record.get("provider_id", "") or ""),
                    action_id=str(payload.get("action_id", "") or ""),
                    outcome=str(payload.get("outcome", "") or ""),
                    outcome_at=str(payload.get("outcome_at", "") or created_at),
                    source=str(payload.get("source", "") or "runtime"),
                    summary=str(payload.get("summary", "") or ""),
                    metadata=dict(metadata_record),
                ),
            )
            return

    def _build_workspace_snapshot(self) -> str:
        summary = self._load_repo_xray()
        topology = build_workspace_topology(self._repo_root.parent)
        git_summary = self._build_git_summary()
        return self._build_workspace_snapshot_from_parts(summary, git_summary, topology)

    def _build_workspace_snapshot_from_parts(
        self,
        summary: Any | None,
        git_summary: dict[str, Any],
        topology: dict[str, Any],
    ) -> str:
        git_summary_lines = self._render_git_summary_lines(git_summary)
        if summary is None:
            return "\n".join(
                [
                    "# Workspace",
                    f"Repo root: {self._repo_root}",
                    *git_summary_lines,
                    "Repo x-ray unavailable",
                ]
            )

        top_files = summary.largest_python_files[:5]
        top_imports = summary.most_imported_modules[:5]
        lines = [
            "# Workspace X-Ray",
            f"Repo root: {summary.repo_root}",
            *git_summary_lines,
            f"Python modules: {summary.python_modules}",
            f"Python tests: {summary.python_tests}",
            f"Scripts: {summary.shell_scripts}",
            f"Docs: {summary.markdown_docs}",
            f"Workflows: {len(summary.workflows)}",
            "",
            "## Topology",
        ]
        for warning in topology.get("warnings", [])[:5]:
            lines.append(f"- warning: {warning}")
        dgc = topology.get("dgc", {})
        for repo in dgc.get("repos", [])[:4]:
            lines.append(
                "- {name} | role {role} | branch {branch} | dirty {dirty} | modified {modified} | untracked {untracked}".format(
                    name=repo.get("name", "repo"),
                    role=repo.get("role", "unknown"),
                    branch=repo.get("branch") or "n/a",
                    dirty=repo.get("dirty"),
                    modified=repo.get("modified_count", 0),
                    untracked=repo.get("untracked_count", 0),
                )
            )
        lines.extend(
            [
                "",
                "## Language mix",
            ]
        )
        for suffix, count in list(summary.language_mix.items())[:8]:
            lines.append(f"- {suffix}: {count}")
        lines.extend(["", "## Largest Python files"])
        for item in top_files:
            lines.append(f"- {item.path} | {item.lines} lines | defs {item.defs} | imports {item.imports}")
        lines.extend(["", "## Most imported local modules"])
        for item in top_imports:
            lines.append(f"- {item.module} | inbound {item.count}")
        return "\n".join(lines)

    def _build_git_summary(self) -> dict[str, Any]:
        try:
            branch = subprocess.run(
                ["git", "-C", str(self._repo_root), "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            ).stdout.strip() or "(detached)"
            head = subprocess.run(
                ["git", "-C", str(self._repo_root), "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            ).stdout.strip() or "unknown"
            porcelain = subprocess.run(
                ["git", "-C", str(self._repo_root), "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            ).stdout
            upstream_process = subprocess.run(
                ["git", "-C", str(self._repo_root), "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except Exception as exc:
            return {
                "branch": "unavailable",
                "head": "unknown",
                "staged": None,
                "unstaged": None,
                "untracked": None,
                "changed_hotspots": [],
                "changed_paths": [],
                "sync_summary": f"unavailable ({type(exc).__name__}: {exc})",
                "sync_status": "unavailable",
                "upstream": None,
                "ahead": None,
                "behind": None,
            }

        staged = 0
        unstaged = 0
        untracked = 0
        changed_areas: dict[str, int] = {}
        changed_paths: list[str] = []
        for line in porcelain.splitlines():
            if len(line) < 2:
                continue
            x = line[0]
            y = line[1]
            path_text = line[3:].strip() if len(line) > 3 else ""
            if " -> " in path_text:
                path_text = path_text.split(" -> ")[-1].strip()
            if path_text:
                area = path_text.split("/", 1)[0] or "."
                changed_areas[area] = changed_areas.get(area, 0) + 1
                changed_paths.append(path_text)
            if x == "?" and y == "?":
                untracked += 1
                continue
            if x not in {" ", "?"}:
                staged += 1
            if y != " ":
                unstaged += 1
        hotspots = [
            {"name": name, "count": count}
            for name, count in sorted(changed_areas.items(), key=lambda item: (-item[1], item[0]))[:4]
        ]
        unique_paths = sorted(set(changed_paths), key=lambda value: (-(changed_areas.get(value.split("/", 1)[0] or ".", 0)), value))[:5]

        if branch == "(detached)":
            return {
                "branch": branch,
                "head": head,
                "staged": staged,
                "unstaged": unstaged,
                "untracked": untracked,
                "changed_hotspots": hotspots,
                "changed_paths": unique_paths,
                "sync_summary": "detached HEAD",
                "sync_status": "detached",
                "upstream": "detached HEAD",
                "ahead": None,
                "behind": None,
            }

        upstream = upstream_process.stdout.strip()
        if upstream_process.returncode != 0 or not upstream:
            return {
                "branch": branch,
                "head": head,
                "staged": staged,
                "unstaged": unstaged,
                "untracked": untracked,
                "changed_hotspots": hotspots,
                "changed_paths": unique_paths,
                "sync_summary": "no upstream configured",
                "sync_status": "no_upstream",
                "upstream": None,
                "ahead": None,
                "behind": None,
            }

        try:
            ahead_behind = subprocess.run(
                ["git", "-C", str(self._repo_root), "rev-list", "--left-right", "--count", f"HEAD...{upstream}"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            ).stdout.strip()
            ahead_text, behind_text = ahead_behind.split()
            ahead = int(ahead_text)
            behind = int(behind_text)
            sync_summary = f"{upstream} | ahead {ahead} | behind {behind}"
        except Exception:
            ahead = None
            behind = None
            sync_summary = f"{upstream} | ahead/behind unavailable"
        return {
            "branch": branch,
            "head": head,
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
            "changed_hotspots": hotspots,
            "changed_paths": unique_paths,
            "sync_summary": sync_summary,
            "sync_status": "tracking",
            "upstream": upstream,
            "ahead": ahead,
            "behind": behind,
        }

    def _render_git_summary_lines(self, git_summary: dict[str, Any]) -> list[str]:
        staged = git_summary.get("staged")
        unstaged = git_summary.get("unstaged")
        untracked = git_summary.get("untracked")
        if staged is None or unstaged is None or untracked is None:
            lines = [f"Git: {git_summary.get('branch', 'unavailable')} ({git_summary.get('sync_summary', 'unavailable')})"]
        else:
            lines = [
                "Git: {branch}@{head} | staged {staged} | unstaged {unstaged} | untracked {untracked}".format(
                    branch=git_summary.get("branch", "unavailable"),
                    head=git_summary.get("head", "unknown"),
                    staged=staged,
                    unstaged=unstaged,
                    untracked=untracked,
                )
            ]
        hotspots = list(git_summary.get("changed_hotspots", []) or [])
        hotspot_summary = (
            "; ".join(
                f"{str(item.get('name', '') or '')} ({int(item.get('count', 0) or 0)})"
                for item in hotspots
                if isinstance(item, dict) and str(item.get("name", "") or "")
            )
            or "none"
        )
        lines.append(f"Git hotspots: {hotspot_summary}")
        path_summary = "; ".join(str(path) for path in list(git_summary.get("changed_paths", []) or []) if str(path)) or "none"
        lines.append(f"Git changed paths: {path_summary}")
        lines.append(f"Git sync: {git_summary.get('sync_summary', 'unavailable')}")
        return lines

    def _build_ontology_snapshot(self) -> str:
        concepts_path = self._package_root / "dharma_concepts.json"
        try:
            payload = json.loads(concepts_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return "\n".join(
                [
                    "# Ontology",
                    f"Seed concepts unavailable: {type(exc).__name__}: {exc}",
                ]
            )

        concepts = payload.get("concepts", [])
        if not isinstance(concepts, list):
            concepts = []
        top_concepts = sorted(
            [concept for concept in concepts if isinstance(concept, dict)],
            key=lambda item: int(item.get("codebase_frequency", 0) or 0),
            reverse=True,
        )[:6]
        lines = [
            "# Ontology Surface",
            f"Version: {payload.get('version', 'unknown')}",
            f"Generated: {payload.get('generated', 'unknown')}",
            f"Concept count: {len(concepts)}",
            "",
            "## Dominant concepts",
        ]
        for concept in top_concepts:
            related = concept.get("related_concepts", [])
            related_text = ", ".join(str(item) for item in related[:4]) if isinstance(related, list) else ""
            lines.append(
                "- {name} | freq {freq} | files {files} | {domain}".format(
                    name=concept.get("canonical_name", concept.get("id", "concept")),
                    freq=concept.get("codebase_frequency", 0),
                    files=concept.get("codebase_files", 0),
                    domain=concept.get("domain", "unknown"),
                )
            )
            if related_text:
                lines.append(f"  related: {related_text}")
        lines.extend(
            [
                "",
                "## Identity",
                "The terminal should present DHARMA SWARM as a repo with concepts, gates, stigmergic traces, and runtime state.",
                "Chat is only one pane in that system, not the system itself.",
            ]
        )
        return "\n".join(lines)

    def _build_runtime_snapshot(self) -> str:
        runtime_text = build_runtime_status_text(limit=5)
        normalized = runtime_text.replace("[bold #9C7444]", "").replace("[/bold #9C7444]", "")
        normalized = normalized.replace("[#9C7444]", "").replace("[/#9C7444]", "")
        normalized = normalized.replace("[dim]", "").replace("[/dim]", "")
        terminal_control = load_terminal_control_state(self._repo_root)
        if terminal_control:
            terminal_lines = [
                f"Active task: {terminal_control.get('active_task_id', 'none') or 'none'}",
                f"Loop decision: {terminal_control.get('loop_decision', 'unknown') or 'unknown'}",
                f"Verification status: {terminal_control.get('verification_status', 'unknown') or 'unknown'}",
                f"Next task: {terminal_control.get('next_task', 'none') or 'none'}",
                f"Updated: {terminal_control.get('updated_at', 'unknown') or 'unknown'}",
            ]
            normalized = "\n".join([normalized.rstrip(), "", "--- Terminal Control ---", *terminal_lines])
        return normalized

    def _build_session_bootstrap(self, request: dict[str, Any]) -> dict[str, Any]:
        prompt = str(request.get("prompt", "") or "").strip()
        active_tab = str(request.get("active_tab", "") or "chat")
        selected_provider = str(request.get("provider", "") or "codex").strip().lower()
        selected_model = str(request.get("model", "") or "").strip()
        intent = self._resolve_prompt_intent(prompt)
        explicit_target = model_routing.resolve_model_target(prompt)
        explicit_strategy = model_routing.resolve_strategy(str(request.get("strategy", "") or "")) or model_routing.resolve_strategy(prompt)
        if explicit_target is not None:
            selected_provider = explicit_target.provider_id
            selected_model = explicit_target.model_id
        elif not selected_model:
            default_target = model_routing.default_target()
            selected_provider = selected_provider or default_target.provider_id
            selected_model = default_target.model_id
        elif not selected_provider:
            selected_provider = model_routing.default_target().provider_id

        workspace_snapshot = self._build_workspace_snapshot()
        ontology_snapshot = self._build_ontology_snapshot()
        runtime_snapshot = self._build_runtime_snapshot()
        repo_guidance = self._load_repo_guidance()
        session_context_hint = self._load_session_context_hint()
        working_memory = self._load_working_memory()
        workspace_preview = self._build_workspace_preview(workspace_snapshot)
        runtime_preview = self._build_runtime_preview(runtime_snapshot)
        command_graph = self._build_command_graph_summary()
        model_policy = self._build_model_policy_summary(
            selected_provider=selected_provider,
            selected_model=selected_model,
            strategy=explicit_strategy or "responsive",
        )
        orientation_packet = build_orientation_packet(
            role="operator",
            claims=[],
            directives=[
                DirectiveSummary(
                    directive_id="terminal-v3",
                    title="Repo-native operator turn",
                    summary="Ground every turn in repo topology, ontology, runtime truth, and model policy.",
                    source_ref="terminal_v3_spec",
                    priority="high",
                )
            ],
            runtime_state=RuntimeStateSummary(
                mode="terminal",
                active_tasks=0,
                running_agents=0,
                pending_tasks=0,
                status_notes=[
                    f"active_tab={active_tab}",
                    f"selected_provider={selected_provider}",
                    f"selected_model={selected_model}",
                    f"intent={intent.get('kind', 'chat')}",
                ],
            ),
            role_context=(
                "You are operating inside the Dharma terminal. Prefer repo-native commands and operator actions when "
                "they satisfy the user's request more directly than generic prose."
            ),
            task=prompt,
            provenance=["workspace.snapshot", "ontology.snapshot", "runtime.snapshot", "terminal.model_policy"],
        )
        route = f"{selected_provider}:{selected_model}"
        working_memory = self._apply_turn_to_memory(
            working_memory,
            prompt=prompt,
            intent=intent,
            route=route,
            active_tab=active_tab,
        )
        rendered_working_memory = self._render_working_memory(working_memory)
        system_prompt = self._render_system_prompt(
            prompt=prompt,
            active_tab=active_tab,
            intent=intent,
            selected_provider=selected_provider,
            selected_model=selected_model,
            routing_strategy=explicit_strategy or "responsive",
            command_graph=command_graph,
            model_policy=model_policy,
            orientation_packet=orientation_packet.model_dump(mode="json"),
            workspace_snapshot=workspace_snapshot,
            ontology_snapshot=ontology_snapshot,
            runtime_snapshot=runtime_snapshot,
            repo_guidance=repo_guidance,
            session_context_hint=session_context_hint,
            working_memory=rendered_working_memory,
        )
        self._save_working_memory(working_memory)
        return {
            "prompt": prompt,
            "active_tab": active_tab,
            "intent": intent,
            "selected_provider": selected_provider,
            "selected_model": selected_model,
            "routing_strategy": explicit_strategy or "responsive",
            "command_graph": command_graph,
            "model_policy": model_policy,
            "orientation_packet": orientation_packet.model_dump(mode="json"),
            "workspace_preview": workspace_preview,
            "runtime_preview": runtime_preview,
            "workspace_snapshot": workspace_snapshot,
            "ontology_snapshot": ontology_snapshot,
            "runtime_snapshot": runtime_snapshot,
            "repo_guidance": repo_guidance,
            "session_context_hint": session_context_hint,
            "working_memory": rendered_working_memory,
            "system_prompt": system_prompt,
        }

    def _build_command_graph_summary(self) -> dict[str, Any]:
        commands = sorted(system_commands_module._ALL_COMMANDS)
        async_commands = sorted(system_commands_module._ASYNC_COMMANDS)
        categories = {
            "chat": sorted(["chat", "clear", "reset", "cancel", "paste", "copy", "copylast", "thread"]),
            "repo": sorted(["git"]),
            "runtime": sorted(["runtime"]),
            "control": sorted(["status", "health", "pulse", "self"]),
            "ontology": sorted(["context", "foundations", "telos", "dharma", "corpus", "evidence"]),
            "memory": sorted(["memory", "notes", "archive", "darwin", "logs", "truth", "stigmergy"]),
            "swarm": sorted(["swarm", "agni", "gates", "witness", "hum"]),
        }
        return {
            "count": len(commands),
            "async_count": len(async_commands),
            "commands": commands,
            "async_commands": async_commands,
            "categories": categories,
        }

    def _build_command_registry(self) -> dict[str, Any]:
        descriptions = {
            "status": "Full system status panel",
            "health": "Ecosystem health check",
            "pulse": "Run heartbeat",
            "self": "System self-map",
            "context": "Show agent context layers",
            "memory": "Strange loop memory and latent gold",
            "notes": "Shared agent notes",
            "archive": "Evolution archive",
            "darwin": "Darwin experiment memory and trust ladder",
            "swarm": "Swarm operations and report lanes",
            "gates": "Test telos gates",
            "evolve": "Darwin Engine evolution",
            "runtime": "Live process and runtime matrix",
            "git": "Repo branch/head/dirty counts",
            "foundations": "Foundational pillars",
            "telos": "Telos Engine research docs",
            "thread": "Show or set research thread",
            "plan": "Plan-mode control",
            "model": "Model routing control",
            "chat": "Native chat continuation control",
        }
        categories = self._build_command_graph_summary()["categories"]
        records = []
        for name in sorted(system_commands_module._ALL_COMMANDS):
            target_pane = "control"
            for category_name, commands in categories.items():
                if name in commands:
                    if category_name == "repo":
                        target_pane = "repo"
                    elif category_name == "runtime":
                        target_pane = "runtime"
                    elif category_name == "ontology":
                        target_pane = "ontology"
                    elif category_name == "memory":
                        target_pane = "sessions"
                    elif category_name == "swarm":
                        target_pane = "agents"
                    elif category_name == "chat":
                        target_pane = "chat"
            records.append(
                {
                    "name": name,
                    "async": name in system_commands_module._ASYNC_COMMANDS,
                    "category": next((category for category, commands in categories.items() if name in commands), "control"),
                    "target_pane": target_pane,
                    "description": descriptions.get(name, "Dharma operator command"),
                }
            )
        return {
            "count": len(records),
            "commands": records,
        }

    async def _build_operator_snapshot(self) -> dict[str, Any]:
        runtime_state = RuntimeStateStore(db_path=DEFAULT_RUNTIME_DB)
        views = OperatorViews(runtime_state)
        try:
            overview = await views.runtime_overview()
            runs = await views.active_runs(limit=8)
            actions = await views.recent_operator_actions(limit=8)
        except Exception as exc:
            return {
                "runtime_db": str(DEFAULT_RUNTIME_DB),
                "error": f"{type(exc).__name__}: {exc}",
                "overview": {},
                "runs": [],
                "actions": [],
            }
        return {
            "runtime_db": str(runtime_state.db_path),
            "overview": {
                "sessions": overview.sessions,
                "claims": overview.claims,
                "active_claims": overview.active_claims,
                "acknowledged_claims": overview.acknowledged_claims,
                "runs": overview.runs,
                "active_runs": overview.active_runs,
                "artifacts": overview.artifacts,
                "promoted_facts": overview.promoted_facts,
                "context_bundles": overview.context_bundles,
                "operator_actions": overview.operator_actions,
            },
            "runs": [
                {
                    "run_id": run.run_id,
                    "task_id": run.task_id,
                    "assigned_to": run.assigned_to,
                    "status": run.status,
                    "current_artifact_id": run.current_artifact_id,
                    "failure_code": run.failure_code,
                    "started_at": run.started_at.isoformat(),
                }
                for run in runs
            ],
            "actions": actions,
        }

    def _build_model_policy_summary(self, *, selected_provider: str, selected_model: str, strategy: str) -> dict[str, Any]:
        strategy = model_routing.resolve_strategy(strategy) or "responsive"
        raw_targets = build_default_matrix_targets(profile="live25", include_unavailable=True)
        seen_routes: set[tuple[str, str]] = set()
        targets: list[dict[str, Any]] = []
        for target in raw_targets:
            provider_id = _bridge_provider_id(target.provider)
            if provider_id is None:
                continue
            route = (provider_id, target.model)
            if route in seen_routes:
                continue
            seen_routes.add(route)
            alias = _target_alias(target.model)
            lane_role = str(target.lane_role.value).replace("_", " ")
            tier = str(target.tier)
            availability = "ready" if bool(target.available) else "unavailable"
            targets.append(
                {
                    "alias": alias,
                    "provider": provider_id,
                    "model": target.model,
                    "label": f"{target.model} [{provider_id} | {lane_role} | {tier} | {availability}]",
                    "lane_role": target.lane_role.value,
                    "tier": tier,
                    "available": bool(target.available),
                    "availability_reason": target.availability_reason,
                    "config_source": target.config_source,
                }
            )

        selected_available = any(
            target["provider"] == selected_provider and target["model"] == selected_model
            for target in targets
        )
        if not selected_available and targets:
            fallback_target = next((target for target in targets if target["provider"] == "codex"), targets[0])
            selected_provider = str(fallback_target["provider"])
            selected_model = str(fallback_target["model"])

        active_target = next(
            (
                target
                for target in targets
                if target["provider"] == selected_provider and target["model"] == selected_model
            ),
            None,
        )
        fallback_chain = [
            {
                "alias": str(target["alias"]),
                "provider": str(target["provider"]),
                "model": str(target["model"]),
                "label": str(target["label"]),
            }
            for target in targets
            if not (target["provider"] == selected_provider and target["model"] == selected_model)
        ][:6]
        return {
            "selected_provider": selected_provider,
            "selected_model": selected_model,
            "selected_route": f"{selected_provider}:{selected_model}",
            "strategy": strategy,
            "strategies": list(model_routing.ROUTING_STRATEGIES),
            "default_route": (
                f"{targets[0]['provider']}:{targets[0]['model']}"
                if targets
                else f"{model_routing.default_target().provider_id}:{model_routing.default_target().model_id}"
            ),
            "active_label": str(active_target["label"]) if active_target else selected_model,
            "fallback_chain": fallback_chain,
            "targets": targets,
        }

    def _build_agent_routes(self) -> dict[str, Any]:
        openclaw = self._read_openclaw_summary()
        routes = [
            {
                "intent": "fast_repo_scan",
                "provider": "claude",
                "model_alias": "haiku-4.5",
                "reasoning": "low",
                "role": "scanner",
            },
            {
                "intent": "deep_code_work",
                "provider": "codex",
                "model_alias": "codex-5.4",
                "reasoning": "high",
                "role": "builder",
            },
            {
                "intent": "architecture_research",
                "provider": "claude",
                "model_alias": "opus-4.6",
                "reasoning": "high",
                "role": "architect",
            },
            {
                "intent": "budget_parallelism",
                "provider": "ollama",
                "model_alias": "glm-5",
                "reasoning": "medium",
                "role": "swarm_worker",
            },
        ]
        return {
            "routes": routes,
            "openclaw": openclaw,
            "subagent_capabilities": [
                "route by task type",
                "select provider/model family",
                "assign reasoning effort",
                "preserve repo-native context envelope",
            ],
        }

    def _build_evolution_surface(self) -> dict[str, Any]:
        domains = []
        for name, domain in get_registered_domains().items():
            domains.append(
                {
                    "name": name,
                    "fitness_threshold": getattr(domain, "fitness_threshold", None),
                    "max_iterations": getattr(domain, "max_iterations", None),
                    "max_duration_seconds": getattr(domain, "max_duration_seconds", None),
                }
            )
        return {
            "domains": domains,
            "entry_commands": ["/cascade <domain>", "/evolve <candidate> <direction>", "/loops"],
            "principles": [
                "self-improvement should stay inspectable",
                "operator approval remains available at gate boundaries",
                "evolution updates should feed future terminal context",
            ],
        }

    def _render_system_prompt(
        self,
        *,
        prompt: str,
        active_tab: str,
        intent: dict[str, Any],
        selected_provider: str,
        selected_model: str,
        routing_strategy: str,
        command_graph: dict[str, Any],
        model_policy: dict[str, Any],
        orientation_packet: dict[str, Any],
        workspace_snapshot: str,
        ontology_snapshot: str,
        runtime_snapshot: str,
        repo_guidance: str,
        session_context_hint: str,
        working_memory: str,
    ) -> str:
        command_categories = command_graph.get("categories", {})
        command_lines = []
        for name, commands in command_categories.items():
            if isinstance(commands, list) and commands:
                command_lines.append(f"- {name}: {', '.join(str(item) for item in commands[:8])}")

        lines = [
            "# Dharma Terminal Bootstrap",
            "",
            "Identity:",
            "- You are not a detached chatbot. You are the Dharma Swarm operator intelligence speaking from inside the repo and control plane.",
            "- Treat the repo, ontology, runtime state, command graph, model policy, and swarm routes as your own appendages.",
            "- When the user asks what you can do, answer in terms of Dharma-native commands, panes, agents, models, and repo actions available right now.",
            "- If a native command, pane refresh, model switch, or operator action is the right move, prefer it over generic prose.",
            "- Your tone should feel like the system itself: specific, grounded, operational, and aware of local topology.",
            "",
            "Turn context:",
            f"- Prompt: {prompt}",
            f"- Active tab: {active_tab}",
            f"- Intent: {intent.get('kind', 'chat')}",
            f"- Selected route: {selected_provider}:{selected_model}",
            f"- Routing strategy: {routing_strategy}",
            "",
            "Model policy:",
            f"- Default route: {model_policy.get('default_route', 'unknown')}",
            f"- Strategies: {', '.join(str(item) for item in model_policy.get('strategies', []))}",
            f"- Available model targets: {', '.join(str(item.get('alias', '?')) for item in model_policy.get('targets', [])[:10])}",
            "",
            "Command graph:",
            *command_lines,
            "",
            "Behavioral rules:",
            "- If the user asks for a model change, perform the switch and explain the new route briefly.",
            "- If the user asks for status, topology, runtime, memory, agents, or evolution state, prefer the corresponding Dharma surface over generic explanation.",
            "- If the user asks who you are, answer as Dharma Swarm's operator intelligence for this repo, not as an abstract assistant.",
            "- When helpful, restate the available command or pane that matches the request.",
            "",
            "Repo guidance (always-loaded doctrine):",
            repo_guidance or "(no CLAUDE.md guidance found)",
            "",
            "Session context hint:",
            session_context_hint or "(no session context hint available)",
            "",
            "Working memory:",
            working_memory or "(no working memory yet)",
            "",
            "Orientation packet:",
            json.dumps(orientation_packet, indent=2, ensure_ascii=True),
            "",
            "Workspace snapshot:",
            workspace_snapshot,
            "",
            "Ontology snapshot:",
            ontology_snapshot,
            "",
            "Runtime snapshot:",
            runtime_snapshot,
        ]
        return "\n".join(lines)

    def _render_command_graph_text(self, graph: dict[str, Any]) -> str:
        lines = [
            "# Command Graph",
            f"Command count: {graph.get('count', 0)}",
            f"Async commands: {graph.get('async_count', 0)}",
            "",
            "## Categories",
        ]
        categories = graph.get("categories", {})
        if isinstance(categories, dict):
            for name, commands in categories.items():
                values = commands if isinstance(commands, list) else []
                lines.append(f"- {name}: {', '.join(str(item) for item in values) if values else 'none'}")
        async_commands = graph.get("async_commands", [])
        if isinstance(async_commands, list):
            lines.extend(["", "## Async lanes", ", ".join(str(item) for item in async_commands) if async_commands else "none"])
        return "\n".join(lines)

    def _render_command_registry_text(self, registry: dict[str, Any]) -> str:
        lines = ["# Command Registry", f"Commands: {registry.get('count', 0)}", "", "## Commands"]
        commands = registry.get("commands", [])
        if isinstance(commands, list):
            for item in commands[:24]:
                if not isinstance(item, dict):
                    continue
                sync_state = "async" if item.get("async") else "sync"
                lines.append(
                    "- /{name} [{sync_state}] -> {target_pane} | {description}".format(
                        name=str(item.get("name", "?")),
                        sync_state=sync_state,
                        target_pane=str(item.get("target_pane", "control")),
                        description=str(item.get("description", "command")),
                    )
                )
        return "\n".join(lines)

    def _render_operator_snapshot_text(self, snapshot: dict[str, Any]) -> str:
        overview = snapshot.get("overview", {})
        runs = snapshot.get("runs", [])
        actions = snapshot.get("actions", [])
        lines = [
            "# Operator Snapshot",
            f"Runtime DB: {snapshot.get('runtime_db', str(DEFAULT_RUNTIME_DB))}",
        ]
        error = str(snapshot.get("error", "") or "").strip()
        if error:
            lines.append(f"Error: {error}")
            return "\n".join(lines)
        if isinstance(overview, dict):
            lines.extend(
                [
                    f"Sessions: {overview.get('sessions', 0)}",
                    f"Claims: {overview.get('claims', 0)} | active {overview.get('active_claims', 0)} | acked {overview.get('acknowledged_claims', 0)}",
                    f"Runs: {overview.get('runs', 0)} | active {overview.get('active_runs', 0)}",
                    f"Artifacts: {overview.get('artifacts', 0)} | promoted facts {overview.get('promoted_facts', 0)}",
                    f"Context bundles: {overview.get('context_bundles', 0)} | operator actions {overview.get('operator_actions', 0)}",
                ]
            )
        lines.extend(["", "## Active runs"])
        if isinstance(runs, list) and runs:
            for run in runs[:8]:
                if not isinstance(run, dict):
                    continue
                lines.append(
                    "- {assigned_to} | {status} | task {task_id} | run {run_id}".format(
                        assigned_to=str(run.get("assigned_to", "?")),
                        status=str(run.get("status", "?")),
                        task_id=str(run.get("task_id", ""))[:18],
                        run_id=str(run.get("run_id", ""))[:12],
                    )
                )
        else:
            lines.append("none")
        lines.extend(["", "## Recent operator actions"])
        if isinstance(actions, list) and actions:
            for action in actions[:8]:
                if not isinstance(action, dict):
                    continue
                lines.append(
                    "- {action_name} by {actor} | task {task_id} | {reason}".format(
                        action_name=str(action.get("action_name", "?")),
                        actor=str(action.get("actor", "?")),
                        task_id=str(action.get("task_id", ""))[:18] or "-",
                        reason=str(action.get("reason", "") or "").strip() or "no reason",
                    )
                )
        else:
            lines.append("none")
        return "\n".join(lines)

    def _render_model_policy_text(self, policy: dict[str, Any]) -> str:
        lines = [
            "# Model Policy",
            f"Active: {policy.get('active_label', policy.get('selected_model', 'unknown'))}",
            f"Route: {policy.get('selected_route', 'unknown')}",
            f"Strategy: {policy.get('strategy', 'responsive')}",
            f"Default route: {policy.get('default_route', 'unknown')}",
            "",
            "## Fallback chain",
        ]
        chain = policy.get("fallback_chain", [])
        if isinstance(chain, list) and chain:
            for item in chain[:6]:
                if not isinstance(item, dict):
                    continue
                lines.append(f"- {item.get('label', item.get('alias', '?'))} [{item.get('provider', '?')}]")
        else:
            lines.append("none")
        lines.extend(["", "## Targets"])
        targets = policy.get("targets", [])
        if isinstance(targets, list):
            for item in targets:
                if not isinstance(item, dict):
                    continue
                lines.append(f"- {item.get('alias', '?')} -> {item.get('label', '?')}")
        return "\n".join(lines)

    def _render_agent_routes_text(self, routes: dict[str, Any]) -> str:
        lines = ["# Agent Routes", "", "## Route profiles"]
        route_items = routes.get("routes", [])
        if isinstance(route_items, list):
            for item in route_items:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    "- {intent} -> {provider}:{model_alias} | effort {reasoning} | role {role}".format(
                        intent=str(item.get("intent", "?")),
                        provider=str(item.get("provider", "?")),
                        model_alias=str(item.get("model_alias", "?")),
                        reasoning=str(item.get("reasoning", "?")),
                        role=str(item.get("role", "?")),
                    )
                )
        openclaw = routes.get("openclaw", {})
        if isinstance(openclaw, dict):
            lines.extend(
                [
                    "",
                    "## OpenClaw",
                    f"Present: {openclaw.get('present', False)}",
                    f"Readable: {openclaw.get('readable', False)}",
                    f"Agents: {openclaw.get('agents_count', 0)}",
                    f"Providers: {', '.join(str(item) for item in openclaw.get('providers', [])) if openclaw.get('providers') else 'none'}",
                ]
            )
        return "\n".join(lines)

    def _render_evolution_surface_text(self, surface: dict[str, Any]) -> str:
        lines = ["# Evolution Surface", "", "## Cascade domains"]
        domains = surface.get("domains", [])
        if isinstance(domains, list):
            for item in domains:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    "- {name} | threshold {fitness_threshold} | max_iter {max_iterations} | max_duration {max_duration_seconds}s".format(
                        name=str(item.get("name", "?")),
                        fitness_threshold=str(item.get("fitness_threshold", "?")),
                        max_iterations=str(item.get("max_iterations", "?")),
                        max_duration_seconds=str(item.get("max_duration_seconds", "?")),
                    )
                )
        lines.extend(["", "## Entry commands"])
        entries = surface.get("entry_commands", [])
        if isinstance(entries, list):
            for entry in entries:
                lines.append(f"- {entry}")
        lines.extend(["", "## Principles"])
        principles = surface.get("principles", [])
        if isinstance(principles, list):
            for principle in principles:
                lines.append(f"- {principle}")
        return "\n".join(lines)

    def _render_session_catalog_text(self, catalog: dict[str, Any]) -> str:
        lines = ["# Session Catalog", f"Sessions: {catalog.get('count', 0)}", "", "## Recent sessions"]
        sessions = catalog.get("sessions", [])
        if isinstance(sessions, list) and sessions:
            for item in sessions[:12]:
                if not isinstance(item, dict):
                    continue
                session = item.get("session")
                if session is None:
                    continue
                metadata = session.get("metadata", {}) if isinstance(session, dict) else {}
                lines.append(
                    "- {session_id} | {provider_id}:{model_id} | {status} | turns {turns} | replay {replay}".format(
                        session_id=session.get("session_id", "?") if isinstance(session, dict) else getattr(session, "session_id", "?"),
                        provider_id=session.get("provider_id", "?") if isinstance(session, dict) else getattr(session, "provider_id", "?"),
                        model_id=session.get("model_id", "?") if isinstance(session, dict) else getattr(session, "model_id", "?"),
                        status=session.get("status", "?") if isinstance(session, dict) else getattr(session, "status", "?"),
                        turns=str(metadata.get("total_turns", item.get("total_turns", 0))),
                        replay="ok" if bool(item.get("replay_ok")) else "issues",
                    )
                )
        else:
            lines.append("none")
        return "\n".join(lines)

    def _render_session_detail_text(self, detail: dict[str, Any]) -> str:
        session = detail.get("session")
        compact = detail.get("compaction_preview", {})
        session_id = session.get("session_id", "?") if isinstance(session, dict) else getattr(session, "session_id", "?")
        provider_id = session.get("provider_id", "?") if isinstance(session, dict) else getattr(session, "provider_id", "?")
        model_id = session.get("model_id", "?") if isinstance(session, dict) else getattr(session, "model_id", "?")
        status = session.get("status", "?") if isinstance(session, dict) else getattr(session, "status", "?")
        cwd = session.get("cwd", "?") if isinstance(session, dict) else getattr(session, "cwd", "?")
        lines = [
            "# Session Detail",
            f"Session: {session_id}",
            f"Route: {provider_id}:{model_id}",
            f"Status: {status}",
            f"CWD: {cwd}",
            f"Replay: {'ok' if detail.get('replay_ok') else 'issues'}",
            "",
            "## Compaction preview",
            f"Events: {compact.get('event_count', 0)}",
            f"Compactable ratio: {compact.get('compactable_ratio', 0.0)}",
            f"Protected: {', '.join(str(item) for item in compact.get('protected_event_types', [])) or 'none'}",
            "",
            "## Recent event types",
            ", ".join(str(item) for item in compact.get("recent_event_types", [])) or "none",
        ]
        issues = detail.get("replay_issues", [])
        lines.extend(["", "## Replay issues"])
        if isinstance(issues, list) and issues:
            for issue in issues[:8]:
                lines.append(f"- {issue}")
        else:
            lines.append("none")
        return "\n".join(lines)

    def _build_workspace_preview(self, content: str) -> dict[str, str]:
        return {
            "Repo root": self._find_line_value(content, "Repo root", fallback=str(self._repo_root)),
            "Branch": self._extract_git_branch(content),
            "Dirty": self._extract_git_dirty(content),
            "Repo risk": self._extract_repo_risk(content),
        }

    def _build_runtime_preview(self, content: str) -> dict[str, str]:
        return {
            "Runtime activity": self._find_prefixed_line(content, "Sessions=", fallback="none"),
            "Artifact state": self._find_prefixed_line(content, "Artifacts=", fallback="none"),
            "Verification status": self._find_line_value(content, "Verification status", fallback="unknown"),
            "Loop decision": self._find_line_value(content, "Loop decision", fallback="unknown"),
            "Next task": self._find_line_value(content, "Next task", fallback="none"),
        }

    def _find_line_value(self, content: str, label: str, *, fallback: str) -> str:
        match = re.search(rf"^{re.escape(label)}:\s*(.+)$", content, re.MULTILINE)
        return match.group(1).strip() if match else fallback

    def _find_prefixed_line(self, content: str, prefix: str, *, fallback: str) -> str:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith(prefix):
                return stripped
        return fallback

    def _extract_git_branch(self, content: str) -> str:
        match = re.search(r"^Git:\s*(.+?)@", content, re.MULTILINE)
        return match.group(1).strip() if match else "unavailable"

    def _extract_git_dirty(self, content: str) -> str:
        match = re.search(
            r"^Git:\s*.+?\|\s*staged\s*(\d+)\s*\|\s*unstaged\s*(\d+)\s*\|\s*untracked\s*(\d+)$",
            content,
            re.MULTILINE,
        )
        if not match:
            return "unavailable"
        return f"{match.group(1)} staged, {match.group(2)} unstaged, {match.group(3)} untracked"

    def _extract_repo_risk(self, content: str) -> str:
        warnings = re.findall(r"^\s*-\s*warning:\s*(.+)$", content, re.MULTILINE)
        if warnings:
            return warnings[0].strip()
        dirty = self._extract_git_dirty(content)
        return "stable" if dirty == "0 staged, 0 unstaged, 0 untracked" else dirty

    def _resolve_prompt_intent(self, prompt: str) -> dict[str, Any]:
        text = prompt.strip()
        lowered = text.lower()
        if not text:
            return {"kind": "chat", "auto_execute": False, "confidence": "low", "reason": "empty prompt"}
        if text.startswith("/"):
            command = text[1:].split(None, 1)[0].lower()
            return {
                "kind": "command",
                "auto_execute": True,
                "confidence": "high",
                "command": command,
                "reason": "explicit slash command",
            }

        bare_command, note = self._commands.resolve_bare_command(text)
        if bare_command:
            return {
                "kind": "command",
                "auto_execute": True,
                "confidence": "high",
                "command": bare_command,
                "reason": note or "resolved bare command",
            }

        explicit_target = model_routing.resolve_model_target(text)
        explicit_strategy = model_routing.resolve_strategy(text)
        if (explicit_target is not None or explicit_strategy is not None) and re.search(r"\b(switch|use|route|move|change|try|set)\b", lowered):
            return {
                "kind": "model_switch",
                "auto_execute": True,
                "confidence": "high",
                "provider": explicit_target.provider_id if explicit_target is not None else "",
                "model": explicit_target.model_id if explicit_target is not None else "",
                "strategy": explicit_strategy or "",
                "reason": "explicit model-routing request",
            }

        if re.search(r"\b(who are you|what are you|what can you do|where am i|what repo is this)\b", lowered):
            return {
                "kind": "identity",
                "auto_execute": True,
                "confidence": "high",
                "reason": "identity-orientation request",
            }

        if re.search(r"\b(compact|summarize session|save session|checkpoint)\b", lowered):
            return {
                "kind": "memory",
                "auto_execute": True,
                "confidence": "medium",
                "reason": "session memory request",
            }

        command_map = (
            ("/runtime", ("runtime", "control plane", "runtime status", "active runs")),
            ("/status", ("status", "health", "pulse", "doctor")),
            ("/git", ("git", "repo status", "workspace status", "topology", "branch", "diff")),
            ("/memory", ("memory", "archive", "notes", "remember")),
            ("/foundations", ("ontology", "foundations", "telos", "dharma concepts", "concept graph")),
            ("/swarm", ("swarm", "agents", "delegation", "subagent", "operator bridge")),
            ("/context", ("context", "orientation", "brief me", "boot context")),
        )
        if re.match(r"^(show|run|open|check|view|inspect|brief)\b", lowered):
            for command, phrases in command_map:
                if any(phrase in lowered for phrase in phrases):
                    return {
                        "kind": "command",
                        "auto_execute": True,
                        "confidence": "medium",
                        "command": command.lstrip("/"),
                        "reason": "plain-language operator command",
                    }

        if any(term in lowered for term in ("subagent", "delegate", "agent swarm", "frontier model", "open model")):
            return {
                "kind": "agent",
                "auto_execute": False,
                "confidence": "medium",
                "reason": "agent-orchestration request",
            }
        if any(term in lowered for term in ("evolve", "improve yourself", "refine the shell", "cascade")):
            return {
                "kind": "evolution",
                "auto_execute": False,
                "confidence": "medium",
                "reason": "self-improvement request",
            }
        return {
            "kind": "chat",
            "auto_execute": False,
            "confidence": "medium",
            "reason": "default conversational turn",
        }

    def _render_identity_response(self, bootstrap: dict[str, Any]) -> str:
        workspace_preview = bootstrap.get("workspace_preview", {})
        runtime_preview = bootstrap.get("runtime_preview", {})
        if not isinstance(workspace_preview, dict):
            workspace_preview = {}
        if not isinstance(runtime_preview, dict):
            runtime_preview = {}
        route = f"{bootstrap.get('selected_provider', 'codex')}:{bootstrap.get('selected_model', 'gpt-5.4')}"
        active_tab = str(bootstrap.get("active_tab", "chat"))
        commands = bootstrap.get("command_graph", {})
        categories = commands.get("categories", {}) if isinstance(commands, dict) else {}
        repo_root = str(workspace_preview.get("Repo root", self._repo_root))
        branch = str(workspace_preview.get("Branch", "unknown"))
        repo_risk = str(workspace_preview.get("Repo risk", "unknown"))
        runtime_activity = str(runtime_preview.get("Runtime activity", "none"))
        available = ", ".join(str(name) for name in categories.keys()) if isinstance(categories, dict) else "chat, repo, control"
        return "\n".join(
            [
                "I am Dharma Swarm's operator intelligence for this workspace.",
                f"Route: {route}",
                f"Repo: {repo_root}",
                f"Branch: {branch}",
                f"Active tab: {active_tab}",
                f"Repo risk: {repo_risk}",
                f"Runtime: {runtime_activity}",
                f"Native surfaces: {available}",
                "I can answer in plain language, switch models, invoke Dharma-native commands, and work against repo/runtime/ontology state directly.",
            ]
        )

    def _render_memory_response(self, bootstrap: dict[str, Any] | None = None) -> str:
        if isinstance(bootstrap, dict):
            rendered = str(bootstrap.get("working_memory", "") or "").strip()
            if rendered:
                return rendered
        return self._render_working_memory(self._load_working_memory())

    def _read_openclaw_summary(self) -> dict[str, Any]:
        oc_path = Path.home() / ".openclaw" / "openclaw.json"
        if not oc_path.exists():
            return {"present": False, "readable": False, "agents_count": 0, "providers": []}
        try:
            payload = json.loads(oc_path.read_text())
        except Exception:
            return {"present": True, "readable": False, "agents_count": 0, "providers": []}
        providers: list[str] = []
        models = payload.get("models", {})
        if isinstance(models, dict):
            provider_map = models.get("providers", {})
            if isinstance(provider_map, dict):
                providers = sorted(str(key) for key in provider_map.keys())
        agents_count = 0
        agents = payload.get("agents", {})
        if isinstance(agents, dict):
            listing = agents.get("list", [])
            if isinstance(listing, list):
                agents_count = len(listing)
        return {
            "present": True,
            "readable": True,
            "agents_count": agents_count,
            "providers": providers,
        }

    def _materialize_async_command(self, raw_command: str, action: str) -> str:
        command = raw_command.split(None, 1)[0].lower()
        if command in {"runtime", "status", "health", "pulse", "self"}:
            return self._build_runtime_snapshot()
        if command == "git":
            return self._build_workspace_snapshot()
        if command in {"context", "foundations", "telos", "dharma", "corpus", "evidence"}:
            return self._build_ontology_snapshot()
        if command in {"swarm", "gates", "witness", "agni", "evolve"}:
            return "\n".join(
                [
                    "# Swarm Control",
                    f"Command: /{command}",
                    "The operator bridge and runtime spine are available, but this command is not yet fully materialized in the Bun terminal.",
                    "Use the Control and Timeline panes for current runtime truth.",
                ]
            )
        if command in {"memory", "archive", "truth", "stigmergy", "darwin", "hum"}:
            return "\n".join(
                [
                    "# Memory Surface",
                    f"Command: /{command}",
                    "The terminal has not yet bound this memory surface into a dedicated live pane.",
                    "Use the Notes pane as the current landing zone while the bridge grows richer memory bindings.",
                ]
            )
        return f"Command /{command} resolved to {action}."

    def _materialize_model_command(self, raw_command: str, action: str) -> str:
        remainder = action.split(":", 1)[1] if ":" in action else "status"
        mode, _, arg = remainder.partition(" ")
        mode = mode.strip().lower() or "status"
        arg = arg.strip()
        current_provider = self._active_provider_id or model_routing.default_target().provider_id
        current_model = self._active_model_id or model_routing.default_target().model_id

        if mode in {"status", "list", "metrics"}:
            return self._render_model_policy_text(
                self._build_model_policy_summary(
                    selected_provider=current_provider,
                    selected_model=current_model,
                    strategy="responsive",
                )
            )
        if mode == "set":
            target = model_routing.resolve_model_target(arg)
            if target is None and arg.isdigit():
                target = model_routing.target_by_index(int(arg))
            if target is None:
                return f"Unknown model target: {arg or 'missing'}"
            return self._render_model_policy_text(
                self._build_model_policy_summary(
                    selected_provider=target.provider_id,
                    selected_model=target.model_id,
                    strategy="responsive",
                )
            )
        if mode == "auto":
            strategy = model_routing.resolve_strategy(arg) or "responsive"
            return self._render_model_policy_text(
                self._build_model_policy_summary(
                    selected_provider=current_provider,
                    selected_model=current_model,
                    strategy=strategy,
                )
            )
        return self._render_model_policy_text(
            self._build_model_policy_summary(
                selected_provider=current_provider,
                selected_model=current_model,
                strategy="responsive",
            )
        )

    def _run_action(self, action_type: str, request: dict[str, Any]) -> dict[str, Any]:
        if action_type == "surface.refresh":
            surface = str(request.get("surface", "") or "").strip().lower()
            output, target_pane = self._refresh_surface(surface)
            self._remember_action(f"surface.refresh -> {surface or target_pane}")
            result: dict[str, Any] = {
                "ok": True,
                "summary": f"refreshed {surface or target_pane}",
                "surface": surface or target_pane,
                "target_pane": target_pane,
            }
            if surface in {"repo", "workspace"}:
                summary = self._load_repo_xray()
                git_summary = self._build_git_summary()
                topology = build_workspace_topology(self._repo_root.parent)
                result["payload"] = build_workspace_snapshot_payload(
                    repo_root=str(self._repo_root),
                    git_summary=git_summary,
                    topology=topology,
                    summary=summary,
                )
            elif surface in {"sessions", "session"}:
                result["payload"] = build_session_catalog(
                    self._session_store,
                    cwd=str(self._repo_root),
                    limit=12,
                )
            elif surface in {"models", "model"}:
                default_target = model_routing.default_target()
                policy = self._build_model_policy_summary(
                    selected_provider=default_target.provider_id,
                    selected_model=default_target.model_id,
                    strategy="responsive",
                )
                result["payload"] = build_routing_decision_payload(policy)
                result["policy"] = policy
            elif surface in {"control", "runtime"}:
                operator_snapshot = asyncio.run(self._build_operator_snapshot())
                result["payload"] = build_runtime_snapshot_payload(
                    operator_snapshot,
                    repo_root=str(self._repo_root),
                    bridge_status="connected",
                    supervisor_preview=load_terminal_control_state(self._repo_root),
                )
            elif surface in {"agents", "agent"}:
                routes = self._build_agent_routes()
                result["payload"] = build_agent_routes_payload(routes)
                result["routes"] = routes
            else:
                result["output"] = output
            return result
        if action_type == "model.set":
            provider = str(request.get("provider", "") or model_routing.default_target().provider_id).strip().lower()
            model = str(request.get("model", "") or model_routing.default_target().model_id).strip()
            strategy = model_routing.resolve_strategy(str(request.get("strategy", "") or "")) or "responsive"
            self._active_provider_id = provider
            self._active_model_id = model
            policy = self._build_model_policy_summary(selected_provider=provider, selected_model=model, strategy=strategy)
            self._remember_action(f"model.set -> {provider}:{model} ({strategy})")
            return {
                "ok": True,
                "summary": f"model policy set to {provider}:{model} ({strategy})",
                "target_pane": "models",
                "output": self._render_model_policy_text(policy),
                "policy": policy,
                "payload": build_routing_decision_payload(policy),
            }
        if action_type == "agent.route":
            intent = str(request.get("intent", "") or "").strip().lower()
            routes = self._build_agent_routes()
            route_records = routes.get("routes", [])
            selected = None
            if isinstance(route_records, list):
                selected = next(
                    (
                        item
                        for item in route_records
                        if isinstance(item, dict) and str(item.get("intent", "")).strip().lower() == intent
                    ),
                    None,
                )
            output_lines = [self._render_agent_routes_text(routes), "", "## Selected route"]
            if isinstance(selected, dict):
                output_lines.extend(
                    [
                        "Intent: {intent}".format(intent=str(selected.get("intent", "?"))),
                        "Provider: {provider}".format(provider=str(selected.get("provider", "?"))),
                        "Model alias: {model_alias}".format(model_alias=str(selected.get("model_alias", "?"))),
                        "Reasoning: {reasoning}".format(reasoning=str(selected.get("reasoning", "?"))),
                        "Role: {role}".format(role=str(selected.get("role", "?"))),
                        "Use this route when a prompt implies this task profile or when you want to hand off directly.",
                    ]
                )
            else:
                output_lines.append(f"Unknown route intent: {intent or 'missing'}")
            self._remember_action(f"agent.route -> {intent or 'missing'}")
            return {
                "ok": isinstance(selected, dict),
                "summary": f"agent route {intent or 'missing'}",
                "target_pane": "agents",
                "output": "\n".join(output_lines),
                "route": selected,
            }
        if action_type == "evolution.run":
            raw_command = str(request.get("command", "") or "").strip()
            normalized = raw_command.lstrip("/").split(None, 1)[0].lower()
            surface = self._build_evolution_surface()
            lines = [self._render_evolution_surface_text(surface), "", "## Requested action", raw_command or "/loops"]
            if normalized in {"evolve", "loops", "cascade"}:
                lines.append("Evolution entry prepared. Use this as the operator launch surface while deeper execution wiring lands.")
            else:
                lines.append("Unknown evolution entry. Known lanes: /evolve, /loops, /cascade <domain>.")
            self._remember_action(f"evolution.run -> {raw_command or '/loops'}")
            return {
                "ok": normalized in {"evolve", "loops", "cascade"},
                "summary": f"evolution action {raw_command or '/loops'}",
                "target_pane": "evolution",
                "output": "\n".join(lines),
            }
        if action_type == "command.run":
            raw_command = str(request.get("command", "") or "").strip()
            if raw_command.startswith("/"):
                raw_command = raw_command[1:]
            output, action = self._commands.handle(raw_command)
            if not str(output).strip() and isinstance(action, str) and action.startswith("async:"):
                output = self._materialize_async_command(raw_command, action)
            self._remember_action(f"command.run -> /{raw_command}")
            return {
                "ok": True,
                "summary": f"executed /{raw_command}",
                "target_pane": self._command_target_pane(raw_command),
                "output": output,
                "action": action,
            }
        if action_type == "approval.resolve":
            action_id = str(request.get("action_id", "") or "").strip()
            resolution = str(request.get("resolution", "") or "").strip().lower()
            if not action_id:
                return {
                    "ok": False,
                    "summary": "approval resolution missing action id",
                    "target_pane": "approvals",
                    "output": "Approval resolution requires an action_id.",
                }
            if resolution not in {"approved", "denied", "dismissed", "resolved"}:
                return {
                    "ok": False,
                    "summary": f"approval resolution invalid for {action_id}",
                    "target_pane": "approvals",
                    "output": f"Unsupported approval resolution: {resolution or 'missing'}.",
                }
            metadata = request.get("metadata")
            payload = build_permission_resolution_payload(
                action_id=action_id,
                resolution=resolution,
                actor=str(request.get("actor", "") or "operator"),
                note=str(request.get("note", "") or "").strip() or None,
                metadata=metadata if isinstance(metadata, dict) else {},
                enforcement_state="recorded_only",
            )
            self._remember_action(f"approval.resolve -> {resolution} {action_id}")
            return {
                "ok": True,
                "summary": f"{resolution} {action_id}",
                "target_pane": "approvals",
                "output": "\n".join(
                    [
                        "# Approval Resolution",
                        f"Action: {action_id}",
                        f"Resolution: {resolution}",
                        f"Actor: {payload['actor']}",
                        f"Recorded at: {payload['resolved_at']}",
                        f"Enforcement: {payload['enforcement_state']}",
                        "Runtime enforcement remains owned by the legacy governance loop until that path is wired.",
                    ]
                ),
                "payload": payload,
            }
        return {
            "ok": False,
            "summary": f"unknown action: {action_type or 'missing'}",
            "target_pane": "control",
            "output": f"Unknown action type: {action_type or 'missing'}",
        }

    def _refresh_surface(self, surface: str) -> tuple[str, str]:
        normalized = surface.strip().lower()
        if normalized in {"repo", "workspace"}:
            return self._build_workspace_snapshot(), "repo"
        if normalized in {"ontology"}:
            return self._build_ontology_snapshot(), "ontology"
        if normalized in {"control", "runtime"}:
            return self._build_runtime_snapshot(), "control"
        if normalized in {"commands", "command", "registry"}:
            registry = self._build_command_registry()
            return self._render_command_registry_text(registry), "commands"
        if normalized in {"models", "model"}:
            default_target = model_routing.default_target()
            policy = self._build_model_policy_summary(
                selected_provider=default_target.provider_id,
                selected_model=default_target.model_id,
                strategy="responsive",
            )
            return self._render_model_policy_text(policy), "models"
        if normalized in {"agents", "agent"}:
            routes = self._build_agent_routes()
            return self._render_agent_routes_text(routes), "agents"
        if normalized in {"evolution", "evolve"}:
            surface_payload = self._build_evolution_surface()
            return self._render_evolution_surface_text(surface_payload), "evolution"
        if normalized in {"notes", "memory", "sessions", "session"}:
            catalog = build_session_catalog(self._session_store, cwd=str(self._repo_root), limit=12)
            return self._render_session_catalog_text(catalog), "sessions"
        return self._build_runtime_snapshot(), "control"

    def _command_target_pane(self, raw_command: str) -> str:
        command = raw_command.split(None, 1)[0].lower()
        if command in {"chat", "clear", "reset", "cancel", "paste", "copy", "copylast", "thread"}:
            return "chat"
        if command == "runtime":
            return "runtime"
        if command == "git":
            return "repo"
        if command in {"model", "models"}:
            return "models"
        if command in {"swarm", "agni", "gates", "witness", "openclaw", "hum"}:
            return "agents"
        if command in {"evolve", "loops", "cascade"}:
            return "evolution"
        if command in {"context", "foundations", "telos", "dharma", "corpus", "evidence", "moltbook"}:
            return "ontology"
        if command == "trishula":
            return "agents"
        if command in {"notes", "memory", "archive", "darwin", "logs", "truth", "stigmergy", "sessions", "session"}:
            return "sessions"
        if command in {"approval", "approvals", "permission", "permissions"}:
            return "approvals"
        return "control"

    def _load_repo_xray(self) -> Any | None:
        script_path = self._repo_root / "scripts" / "repo_xray.py"
        if not script_path.exists():
            return None
        spec = importlib.util.spec_from_file_location("dharma_repo_xray", script_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        build_xray = getattr(module, "build_xray", None)
        if build_xray is None:
            return None
        return build_xray(self._repo_root)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dharma terminal JSON bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("stdio", help="Run the JSON bridge over stdin/stdout")
    return parser


async def _async_main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    bridge = TerminalBridge()
    try:
        if args.command == "stdio":
            return await bridge.run_stdio()
    finally:
        await bridge.close()
    parser.error(f"unknown command: {args.command}")
    return 2


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
