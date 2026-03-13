"""DGC TUI Application -- main Textual app composing all layers.

This is the central hub that:
- Composes MainScreen (status bar, stream output, prompt input, footer)
- Routes canonical provider events from ProviderRunner to widgets
- Handles slash commands via SystemCommandHandler
- Manages mode cycling (N/A/P/S)
- Manages session state
- Provides threaded execution for async system commands
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import secrets
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.timer import Timer

from .engine.adapters import CompletionRequest
from .engine.events import (
    ErrorEvent,
    RateLimitEvent,
    SessionEnd,
    SessionStart,
    TaskComplete,
    TaskProgress,
    TaskStarted,
    TextComplete,
    TextDelta,
    ThinkingComplete,
    ThinkingDelta,
    ToolCallComplete,
    ToolProgress,
    ToolResult,
    UsageReport,
)
from .engine.provider_runner import ProviderRunner
from .engine.session_store import SessionStore
from .engine.session_state import SessionState
from .screens.btw import BTWScreen
from .screens.main import MainScreen
from .screens.splash import SplashScreen
from .widgets.prompt_input import PromptInput
from .widgets.stream_output import StreamOutput
from .widgets.status_bar import StatusBar
from .commands.palette import DGCCommandProvider
from .commands.system_commands import SystemCommandHandler
from .model_routing import (
    ROUTING_STRATEGIES,
    all_targets,
    default_target,
    detect_inline_switch_intent,
    fallback_chain,
    format_model_list,
    format_model_status,
    route_key,
    resolve_model_target,
    resolve_strategy,
    target_by_index,
    target_for_route,
)

HOME = Path.home()
DHARMA_SWARM = Path(__file__).resolve().parent.parent.parent
DHARMA_STATE = HOME / ".dharma"
MODEL_POLICY_PATH = DHARMA_STATE / "tui_model_policy.json"
MODEL_STATS_PATH = DHARMA_STATE / "tui_model_stats.json"
MODEL_COOLDOWN_SEC = max(30, int(os.getenv("DGC_MODEL_COOLDOWN_SEC", "300")))
INDIGO = "#9C7444"
VERDIGRIS = "#62725D"
OCHRE = "#A17A47"
BENGARA = "#8C5448"

_MODE_NAMES: dict[str, str] = {
    "N": "normal",
    "A": "auto",
    "P": "plan",
    "S": "sage",
}
_MODE_KEYS = list(_MODE_NAMES.keys())

_PLAN_MODE_SYSTEM_PROMPT = (
    "PLAN MODE CONTRACT (strict):\n"
    "1) Plan before acting. Produce a numbered execution plan first.\n"
    "2) Do not run mutating tools or write files until the user explicitly approves execution.\n"
    "3) Read-only inspection is allowed for scoping and risk analysis.\n"
    "4) If using EnterPlanMode, call it with an empty input object: {}.\n"
    "5) If a tool returns InputValidationError for unexpected parameters, correct the call schema and retry.\n"
    "6) End with a clear approval checkpoint."
)


class DGCApp(App):
    """DGC Terminal Interface -- Dharmic Godel Claw.

    Composes the Textual widget tree and routes events between the
    ProviderRunner (provider-agnostic canonical stream), system command
    handlers, and the display widgets.
    """

    TITLE = "DGC"
    CSS_PATH = "theme/dharma_dark.tcss"
    COMMAND_PALETTE_BINDING = "ctrl+p"
    COMMANDS = {DGCCommandProvider}

    BINDINGS = [
        Binding("ctrl+c", "smart_cancel_or_copy", "Stop/Copy", show=True),
        Binding("ctrl+d", "quit", "Exit", show=True),
        Binding("ctrl+l", "clear_output", "Clear", show=True),
        Binding("ctrl+o", "cycle_mode", "Mode", show=True),
        Binding("ctrl+y", "copy_last", "Copy reply", show=False),
        Binding("ctrl+n", "new_session", "New", show=False),
        Binding("end", "scroll_to_bottom", "Bottom", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._session = SessionState()
        self._session_store = SessionStore()
        self._commands = SystemCommandHandler()
        self._mode: str = "N"
        self._commands.set_mode(self._mode)
        self._provider_runner: ProviderRunner | None = None
        self._provider_session_id: str | None = None
        initial = default_target()
        self._active_provider: str = initial.provider_id
        self._active_model: str = initial.model_id
        self._preferred_provider: str = initial.provider_id
        self._preferred_model: str = initial.model_id
        self._auto_model_fallback: bool = True
        self._model_strategy: str = "responsive"
        self._last_user_prompt: str | None = None
        self._fallback_queue: list[tuple[str, str]] = []
        self._cooldown_until_by_alias: dict[str, float] = {}
        self._last_error_code: str | None = None
        self._last_error_message: str | None = None
        self._chat_history: list[dict[str, str]] = []
        self._chat_history_max: int = 24
        self._model_stats: dict[str, dict[str, float | int | str]] = {}
        self._inflight_provider: str | None = None
        self._inflight_model: str | None = None
        self._inflight_started_ts: float | None = None
        self._last_session_success: bool | None = None
        self._pending_fallback: bool = False
        self._provider_event_seen: bool = False
        self._provider_idle_timer: Timer | None = None
        self._last_provider_event_ts: float | None = None
        self._last_provider_event_label: str = ""
        self._last_idle_notice_ts: float = 0.0
        # State context cache (same 60s TTL as old TUI)
        self._state_cache: str = ""
        self._state_cache_time: float = 0.0

    # ─── Composition ─────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        """Yield the invisible ProviderRunner worker widget.

        ProviderRunner owns provider adapter execution. The visible UI is
        rendered by screens and widgets on top of this headless worker.
        """
        runner = ProviderRunner(id="provider-runner")
        self._provider_runner = runner
        yield runner

    def on_mount(self) -> None:
        """Push screens and register theme on startup."""
        self._load_model_policy()
        self._load_model_stats()

        # Push main screen first (it becomes the base), then splash on top.
        # The callback fires when the *pushed* screen is dismissed, so attach
        # it to SplashScreen — when the user presses Enter/Esc/Space on the
        # splash, it is dismissed and _on_main_ready runs.
        self.push_screen(MainScreen())
        self.push_screen(SplashScreen(), callback=self._on_main_ready)

        # Register and activate the warm dark theme
        try:
            from .theme.dharma_dark import DharmaDarkTheme

            self.register_theme(DharmaDarkTheme)
            self.theme = "dharma-dark"
        except Exception:
            pass  # Textual version may not support custom themes

    def _on_main_ready(self, result: Any = None) -> None:
        """Called when splash is dismissed and main screen becomes active."""
        main = self._get_main_screen()
        if main:
            self._init_status_bar(main.status_bar, model=self._status_model_label())  # type: ignore[arg-type]
            main.stream_output.write_system(
                f"[bold {INDIGO}]DGC[/bold {INDIGO}] mission console ready. "
                f"Route: [bold]{self._status_model_label()}[/bold]. "
                "Use /help for commands.\n"
            )
            self._restore_last_session_context()
            self._run_status_on_startup()

    # ─── Screen Access ───────────────────────────────────────────────

    def _get_main_screen(self) -> MainScreen | None:
        """Find the MainScreen in the screen stack."""
        for screen in self.screen_stack:
            if isinstance(screen, MainScreen):
                return screen
        return None

    def _get_btw_screen(self) -> BTWScreen | None:
        for screen in self.screen_stack:
            if isinstance(screen, BTWScreen):
                return screen
        return None

    def _status_model_label(self) -> str:
        return f"{self._active_provider}:{self._active_model}"

    def _open_btw_screen(self, *, initial_text: str = "") -> None:
        existing = self._get_btw_screen()
        if existing is not None:
            if initial_text:
                existing.chat_output.write_system(  # type: ignore[union-attr]
                    "[dim]BTW overlay already open. Paste the next prompt there or /merge it back.[/dim]"
                )
            return
        self.push_screen(BTWScreen(initial_text=initial_text))

    def merge_btw_thread(
        self,
        *,
        transcript: list[dict[str, str]],
        source_session_id: str,
        note: str | None = None,
    ) -> None:
        if not transcript:
            main = self._get_main_screen()
            if main:
                main.stream_output.write_system(  # type: ignore[union-attr]
                    "[dim]BTW merge skipped: thread was empty.[/dim]"
                )
            return

        excerpt_lines: list[str] = []
        for item in transcript[-8:]:
            role = str(item.get("role", "note")).strip().upper()
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            excerpt_lines.append(f"{role}: {content}")
        if note:
            excerpt_lines.append(f"MERGE_NOTE: {note.strip()}")
        payload = (
            f"[BTW merge from parallel thread {source_session_id}]\n"
            "Fold this context into the main task only if relevant.\n\n"
            + "\n\n".join(excerpt_lines)
        )[:6000]
        self._append_chat(role="user", content=payload)
        main = self._get_main_screen()
        if main:
            main.stream_output.write_system(  # type: ignore[union-attr]
                "[dim]BTW thread merged into main context for the next turn.[/dim]"
            )

    def _reset_status_runtime(
        self,
        status: StatusBar,
        *,
        activity: str = "ready",
    ) -> None:
        """Reset live per-run telemetry while keeping session counters intact."""
        status.activity = activity
        status.tool_count = 0
        status.last_tool = ""
        status.input_tokens = 0
        status.output_tokens = 0
        status.is_running = False

    def _init_status_bar(
        self,
        status: StatusBar,
        *,
        model: str = "",
        session_name: str = "",
    ) -> None:
        """Initialize the status widget, including light test doubles."""
        if hasattr(status, "update_from_init"):
            status.update_from_init(model=model, session_name=session_name)  # type: ignore[call-arg]
            return
        if model:
            status.model = model
        if session_name:
            status.session_name = session_name
        self._reset_status_runtime(status)

    def _set_status_activity(
        self,
        status: StatusBar,
        activity: str,
        *,
        tool_name: str | None = None,
        increment_tools: bool = False,
    ) -> None:
        """Update the live status banner with the latest execution phase."""
        status.activity = activity
        if increment_tools:
            status.tool_count = int(getattr(status, "tool_count", 0)) + 1
        if tool_name:
            status.last_tool = tool_name

    def _recover_stale_provider_lock_from_session_meta(self) -> bool:
        """Release a stale provider lock when persisted session metadata says the run ended."""
        if not self._provider_runner or not self._provider_runner.is_running:
            return False

        local_session_id = self._session.session_id
        if not local_session_id:
            return False

        try:
            meta = self._session_store.load_meta(local_session_id)
        except Exception:
            return False

        persisted_status = str(meta.get("status", "") or "").strip().lower()
        if persisted_status in {"", "running"}:
            return False

        main = self._get_main_screen()
        status_bar = getattr(main, "status_bar", None)
        if status_bar is not None:
            status_bar.is_running = False
            if persisted_status == "completed":
                self._set_status_activity(status_bar, "complete")
            elif persisted_status == "cancelled":
                self._set_status_activity(status_bar, "cancelled")
            else:
                self._set_status_activity(status_bar, persisted_status)

        self._stop_provider_idle_watch()
        self._session.is_running = False
        self._last_session_success = persisted_status == "completed"
        self._pending_fallback = False
        self._provider_event_seen = False
        self._inflight_provider = None
        self._inflight_model = None
        self._inflight_started_ts = None
        with contextlib.suppress(Exception):
            self._provider_runner.mark_session_end()  # type: ignore[union-attr]

        if main is not None:
            main.stream_output.write_system(  # type: ignore[union-attr]
                "[dim]Recovered stale provider lock from persisted session "
                f"status={persisted_status}.[/dim]"
            )
        return True

    def _set_active_model(
        self,
        *,
        provider_id: str,
        model_id: str,
        announce: bool = False,
        reason: str = "",
        set_preferred: bool = False,
        persist_preference: bool = False,
    ) -> None:
        provider_changed = provider_id != self._active_provider
        model_changed = model_id != self._active_model
        self._active_provider = provider_id
        self._active_model = model_id
        if set_preferred:
            self._preferred_provider = provider_id
            self._preferred_model = model_id
            target = target_for_route(provider_id, model_id)
            if target:
                self._cooldown_until_by_alias.pop(target.alias, None)
            if persist_preference:
                self._save_model_policy()
        if provider_changed or model_changed:
            # Model/provider switches start a fresh provider-level session.
            self._provider_session_id = None

        main = self._get_main_screen()
        if main:
            main.status_bar.model = self._status_model_label()  # type: ignore[union-attr]
            if announce:
                suffix = f" ({reason})" if reason else ""
                main.stream_output.write_system(  # type: ignore[union-attr]
                    f"[dim {INDIGO}]Model switched -> "
                    f"{self._active_provider}:{self._active_model}{suffix}[/dim]"
                )

    def _preferred_target(self):
        return target_for_route(self._preferred_provider, self._preferred_model)

    def _load_model_policy(self) -> None:
        try:
            data = json.loads(MODEL_POLICY_PATH.read_text())
        except Exception:
            return

        auto = data.get("auto_fallback")
        if isinstance(auto, bool):
            self._auto_model_fallback = auto

        strategy = resolve_strategy(str(data.get("strategy", "")).strip())
        if strategy:
            self._model_strategy = strategy

        preferred_provider = str(data.get("preferred_provider", "")).strip()
        preferred_model = str(data.get("preferred_model", "")).strip()
        target = target_for_route(preferred_provider, preferred_model)
        if target is not None:
            self._preferred_provider = preferred_provider
            self._preferred_model = preferred_model
            self._active_provider = preferred_provider
            self._active_model = preferred_model
            self._provider_session_id = None

    def _save_model_policy(self) -> None:
        payload = {
            "auto_fallback": self._auto_model_fallback,
            "strategy": self._model_strategy,
            "preferred_provider": self._preferred_provider,
            "preferred_model": self._preferred_model,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            MODEL_POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
            MODEL_POLICY_PATH.write_text(json.dumps(payload, indent=2))
        except Exception:
            # Policy persistence should never break chat flow.
            return

    def _load_model_stats(self) -> None:
        try:
            data = json.loads(MODEL_STATS_PATH.read_text())
        except Exception:
            return
        if not isinstance(data, dict):
            return
        stats = data.get("model_stats")
        if isinstance(stats, dict):
            self._model_stats = stats

    def _save_model_stats(self) -> None:
        payload = {
            "model_stats": self._model_stats,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            MODEL_STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
            MODEL_STATS_PATH.write_text(json.dumps(payload, indent=2))
        except Exception:
            return

    def _provider_ready(self, provider_id: str) -> bool:
        if provider_id == "claude":
            return shutil.which("claude") is not None
        if provider_id == "codex":
            return shutil.which("codex") is not None
        if provider_id == "openrouter":
            return bool(os.getenv("OPENROUTER_API_KEY"))
        return True

    def _expire_model_cooldowns(self, *, now_ts: float | None = None) -> None:
        now = now_ts if now_ts is not None else time.time()
        expired = [k for k, v in self._cooldown_until_by_alias.items() if v <= now]
        for key in expired:
            self._cooldown_until_by_alias.pop(key, None)

    def _cooldown_active_count(self) -> int:
        self._expire_model_cooldowns()
        now = time.time()
        return sum(1 for until in self._cooldown_until_by_alias.values() if until > now)

    def _available_route_keys(self) -> set[str]:
        self._expire_model_cooldowns()
        keys: set[str] = set()
        now = time.time()
        for target in all_targets():
            if not self._provider_ready(target.provider_id):
                continue
            until = self._cooldown_until_by_alias.get(target.alias, 0.0)
            if until > now:
                continue
            keys.add(route_key(target.provider_id, target.model_id))
        return keys

    def _build_fallback_queue(self) -> list[tuple[str, str]]:
        available = self._available_route_keys()
        allowed_aliases = {
            target.alias
            for target in all_targets()
            if route_key(target.provider_id, target.model_id) in available
        }
        candidates = fallback_chain(
            self._active_provider,
            self._active_model,
            strategy=self._model_strategy,
            allowed_aliases=allowed_aliases,
            cooldown_until=self._cooldown_until_by_alias,
        )
        base_index = {t.alias: idx for idx, t in enumerate(candidates)}

        def _score(target) -> tuple[float, float, float]:
            stats = self._model_stats.get(target.alias, {})
            consecutive = float(stats.get("consecutive_failures", 0) or 0.0)
            latency = float(stats.get("ema_latency_ms", 0.0) or 0.0)
            base = float(base_index.get(target.alias, 999))
            if self._model_strategy == "responsive":
                return (consecutive, latency or 999999.0, base)
            if self._model_strategy == "cost":
                return (consecutive, base, latency or 999999.0)
            # genius
            return (consecutive, base, latency or 999999.0)

        candidates.sort(key=_score)
        return [(target.provider_id, target.model_id) for target in candidates]

    def _parse_model_set_target(self, raw: str):
        cleaned = raw.strip().lstrip("#")
        if cleaned.isdigit():
            return target_by_index(int(cleaned))
        return resolve_model_target(raw)

    def _mark_active_model_failed(self) -> None:
        target = target_for_route(self._active_provider, self._active_model)
        if target is None:
            return

        code = (self._last_error_code or "").lower()
        message = (self._last_error_message or "").lower()
        critical_terms = {
            "missing_api_key",
            "subscription",
            "quota",
            "billing",
            "auth",
            "401",
            "403",
        }
        severe = any(term in code or term in message for term in critical_terms)
        cooldown = MODEL_COOLDOWN_SEC * (3 if severe else 1)
        self._cooldown_until_by_alias[target.alias] = time.time() + cooldown

    def _record_model_result(
        self,
        *,
        provider_id: str | None,
        model_id: str | None,
        success: bool | None,
        latency_ms: float | None,
        error_code: str | None = None,
    ) -> None:
        if not provider_id or not model_id or success is None:
            return
        target = target_for_route(provider_id, model_id)
        alias = target.alias if target else route_key(provider_id, model_id)
        row = self._model_stats.setdefault(
            alias,
            {
                "successes": 0,
                "failures": 0,
                "consecutive_failures": 0,
                "ema_latency_ms": 0.0,
                "last_error": "",
                "last_seen": "",
            },
        )

        if success:
            row["successes"] = int(row.get("successes", 0) or 0) + 1
            row["consecutive_failures"] = 0
            row["last_error"] = ""
        else:
            row["failures"] = int(row.get("failures", 0) or 0) + 1
            row["consecutive_failures"] = int(
                row.get("consecutive_failures", 0) or 0
            ) + 1
            if error_code:
                row["last_error"] = error_code

        if latency_ms is not None and latency_ms > 0.0:
            previous = float(row.get("ema_latency_ms", 0.0) or 0.0)
            row["ema_latency_ms"] = (
                latency_ms if previous <= 0.0 else (0.7 * previous + 0.3 * latency_ms)
            )

        row["last_seen"] = datetime.now(timezone.utc).isoformat()
        self._save_model_stats()

    def _format_model_metrics_report(self) -> str:
        if not self._model_stats:
            return "[dim]No model metrics recorded yet.[/dim]"
        lines = ["Model metrics:", ""]
        for alias, stats in sorted(
            self._model_stats.items(),
            key=lambda item: (
                -int(item[1].get("successes", 0) or 0),
                int(item[1].get("failures", 0) or 0),
            ),
        ):
            ok = int(stats.get("successes", 0) or 0)
            bad = int(stats.get("failures", 0) or 0)
            consecutive = int(stats.get("consecutive_failures", 0) or 0)
            lat = float(stats.get("ema_latency_ms", 0.0) or 0.0)
            err = str(stats.get("last_error", "") or "-")
            lines.append(
                f"[{INDIGO}]{alias}[/{INDIGO}] ok={ok} fail={bad} "
                f"streak={consecutive} latency~{lat:.0f}ms last_error={err}"
            )
        return "\n".join(lines)

    def _try_auto_fallback(self, output: StreamOutput, *, reason: str) -> bool:
        if not (
            self._auto_model_fallback
            and self._last_user_prompt
            and self._is_fallback_eligible_failure()
        ):
            return False

        self._mark_active_model_failed()
        if not self._fallback_queue:
            self._fallback_queue = self._build_fallback_queue()
        if self._prefer_cross_provider_fallback():
            self._fallback_queue = self._reorder_fallback_queue_cross_provider_first(
                self._fallback_queue
            )

        next_target: tuple[str, str] | None = None
        while self._fallback_queue:
            candidate = self._fallback_queue.pop(0)
            if self._can_route_to(candidate[0], candidate[1]):
                next_target = candidate
                break

        if next_target is None:
            output.write_error(
                f"[{BENGARA}]Auto-fallback exhausted; no route is currently available.[/{BENGARA}]"
            )
            self._pending_fallback = False
            return False

        provider_id, model_id = next_target
        prev = f"{self._active_provider}:{self._active_model}"
        promote_preference = (
            self._prefer_cross_provider_fallback()
            and provider_id != self._preferred_provider
        )
        self._set_active_model(
            provider_id=provider_id,
            model_id=model_id,
            announce=False,
            set_preferred=promote_preference,
            persist_preference=promote_preference,
        )
        output.write_system(
            f"[{OCHRE}]Auto-fallback[/{OCHRE}]: "
            f"{prev} -> {provider_id}:{model_id} [dim]({reason})[/dim]"
        )
        if promote_preference:
            output.write_system(
                "[dim]Preferred route updated to "
                f"{provider_id}:{model_id} after hard provider failure.[/dim]"
            )
        self._pending_fallback = False
        self._dispatch_prompt(
            self._last_user_prompt,
            append_user=False,
            reset_fallback_queue=False,
        )
        return True

    def _prefer_cross_provider_fallback(self) -> bool:
        code = (self._last_error_code or "").lower()
        msg = (self._last_error_message or "").lower()
        hay = f"{code} {msg}"
        hard_provider_failure_terms = (
            "out of extra usage",
            "usage_exhausted",
            "rate limit: rejected",
            "rate_limit_rejected",
            "subscription",
            "quota",
            "billing",
            "missing_auth",
            "logged out",
            "sign in",
            "login",
            "unauthorized",
            "401",
            "403",
        )
        return any(term in hay for term in hard_provider_failure_terms)

    def _reorder_fallback_queue_cross_provider_first(
        self,
        queue: list[tuple[str, str]],
    ) -> list[tuple[str, str]]:
        cross_provider = [
            route for route in queue if route[0] != self._active_provider
        ]
        same_provider = [
            route for route in queue if route[0] == self._active_provider
        ]
        return cross_provider + same_provider

    def _can_route_to(self, provider_id: str, model_id: str) -> bool:
        target = target_for_route(provider_id, model_id)
        if target is None:
            return False
        if not self._provider_ready(provider_id):
            return False
        self._expire_model_cooldowns()
        return self._cooldown_until_by_alias.get(target.alias, 0.0) <= time.time()

    def _maybe_restore_preferred_model(self) -> None:
        if (
            self._active_provider == self._preferred_provider
            and self._active_model == self._preferred_model
        ):
            return
        if not self._can_route_to(self._preferred_provider, self._preferred_model):
            return
        self._set_active_model(
            provider_id=self._preferred_provider,
            model_id=self._preferred_model,
            announce=True,
            reason="preferred restored",
        )

    def _append_chat(self, *, role: str, content: str) -> None:
        if not content:
            return
        self._chat_history.append({"role": role, "content": content})
        if len(self._chat_history) > self._chat_history_max:
            self._chat_history = self._chat_history[-self._chat_history_max:]

    def _restore_last_session_context(self) -> None:
        """Restore Claude continuity only when Claude is still the preferred route."""
        auto_resume = os.getenv("DGC_AUTO_RESUME", "0").strip().lower()
        if auto_resume in {"0", "false", "no", "off"}:
            return

        main = self._get_main_screen()
        if not main:
            return

        if self._preferred_provider != "claude":
            return

        try:
            min_turns = int(os.getenv("DGC_AUTO_RESUME_MIN_TURNS", "2"))
        except Exception:
            min_turns = 2

        allow_cross_workspace = os.getenv(
            "DGC_AUTO_RESUME_CROSS_WORKSPACE", "0"
        ).strip().lower() in {"1", "true", "yes", "on"}
        debug_resume = os.getenv("DGC_AUTO_RESUME_DEBUG", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        candidates: list[tuple[str, dict[str, Any]]] = [
            (
                "workspace+provider+min_turns",
                {
                    "cwd": str(DHARMA_SWARM),
                    "provider_id": "claude",
                    "min_turns": min_turns,
                },
            ),
            (
                "workspace+provider",
                {
                    "cwd": str(DHARMA_SWARM),
                    "provider_id": "claude",
                },
            ),
        ]
        if allow_cross_workspace:
            candidates.extend(
                [
                    (
                        "provider+min_turns",
                        {
                            "provider_id": "claude",
                            "min_turns": min_turns,
                        },
                    ),
                    (
                        "provider",
                        {
                            "provider_id": "claude",
                        },
                    ),
                ]
            )

        meta: dict[str, Any] | None = None
        selected_scope = ""
        for scope, kwargs in candidates:
            try:
                meta = self._session_store.latest_session(**kwargs)
            except Exception:
                meta = None
            if meta:
                selected_scope = scope
                break
        if not meta:
            if debug_resume:
                main.stream_output.write_system(  # type: ignore[union-attr]
                    "[dim]Auto-resume: no resumable Claude session found.[/dim]"
                )
            return

        provider_sid = str(meta.get("provider_session_id", "") or "").strip()
        local_sid = str(meta.get("session_id", "") or "").strip()
        if not provider_sid or not local_sid:
            if debug_resume:
                main.stream_output.write_system(  # type: ignore[union-attr]
                    "[dim]Auto-resume: session metadata missing provider session id.[/dim]"
                )
            return

        self._session.session_id = local_sid
        self._provider_session_id = provider_sid
        restored_provider = str(meta.get("provider_id", "claude") or "claude")
        restored_model = str(meta.get("model_id", self._active_model) or self._active_model)
        self._active_provider = restored_provider
        self._active_model = restored_model
        with contextlib.suppress(Exception):
            self._session.turn_count = int(meta.get("total_turns", 0) or 0)
        with contextlib.suppress(Exception):
            self._session.total_cost_usd = float(meta.get("total_cost_usd", 0.0) or 0.0)

        status: StatusBar = main.status_bar  # type: ignore[assignment]
        self._init_status_bar(
            status,
            model=self._status_model_label(),
            session_name=provider_sid[:8],
        )
        status.turn_count = self._session.turn_count
        status.cost_usd = self._session.total_cost_usd
        status.activity = "resumed"
        main.stream_output.write_system(  # type: ignore[union-attr]
            "[dim]Restored prior Claude context: "
            f"{provider_sid[:12]}... (turns={status.turn_count}). "
            "Use Ctrl+N for a clean new session.[/dim]"
        )
        if selected_scope and selected_scope != "workspace+provider+min_turns":
            main.stream_output.write_system(  # type: ignore[union-attr]
                f"[dim]Auto-resume scope fallback: {selected_scope}.[/dim]"
            )

    # ─── Event Routing: ProviderRunner -> Widgets ────────────────────

    def on_provider_runner_agent_event(
        self, event: ProviderRunner.AgentEvent
    ) -> None:
        """Route canonical provider events to display widgets."""
        ev = event.event
        self._provider_event_seen = True
        self._last_provider_event_ts = time.time()
        self._last_provider_event_label = self._provider_event_label(ev)
        self._session.handle_event(ev)

        main = self._get_main_screen()
        if not main:
            return

        btw = self._get_btw_screen()
        if btw is not None:
            btw.notify_main_event(ev)

        output: StreamOutput = main.stream_output  # type: ignore[assignment]
        status: StatusBar = main.status_bar  # type: ignore[assignment]

        if isinstance(ev, SessionStart):
            self._active_provider = ev.provider_id or self._active_provider
            self._active_model = ev.model or self._active_model
            self._init_status_bar(
                status,
                model=self._status_model_label(),
                session_name=(
                    (ev.provider_session_id or ev.session_id)[:8]
                    if (ev.provider_session_id or ev.session_id)
                    else "dgc"
                ),
            )
            status.is_running = True
            self._set_status_activity(status, "connected")
            if ev.provider_session_id:
                self._provider_session_id = ev.provider_session_id
            output.write_system(
                f"[dim]Session: {(ev.provider_session_id or ev.session_id)[:12]}... | "
                f"Model: {ev.model} | Tools: {len(ev.tools_available)}[/dim]"
            )

        elif isinstance(ev, TextDelta):
            self._set_status_activity(status, "answering")
            output.handle_text_delta(ev)

        elif isinstance(ev, TextComplete):
            output.handle_text_complete(ev)
            if ev.role == "assistant":
                status.turn_count = self._session.turn_count
                self._set_status_activity(status, "assistant")
                self._append_chat(role="assistant", content=ev.content)
            else:
                self._set_status_activity(status, "progress")

        elif isinstance(ev, ThinkingDelta):
            self._set_status_activity(status, "thinking")
            output.handle_thinking_delta(ev)

        elif isinstance(ev, ThinkingComplete):
            self._set_status_activity(status, "reasoned")
            output.handle_thinking_complete(ev)

        elif isinstance(ev, ToolCallComplete):
            tool_name = ev.tool_name or "tool"
            self._set_status_activity(
                status,
                f"tool:{tool_name}",
                tool_name=tool_name,
                increment_tools=True,
            )
            output.handle_tool_call_complete(ev)

        elif isinstance(ev, ToolProgress):
            tool_name = ev.tool_name or status.last_tool or "tool"
            self._set_status_activity(
                status,
                f"{tool_name} {ev.elapsed_seconds:.1f}s",
                tool_name=tool_name,
            )
            output.handle_tool_progress_canonical(ev)

        elif isinstance(ev, ToolResult):
            tool_name = ev.tool_name or status.last_tool or "tool"
            self._set_status_activity(
                status,
                f"{tool_name} {'err' if ev.is_error else 'ok'}",
                tool_name=tool_name,
            )
            output.handle_tool_result_canonical(ev)

        elif isinstance(ev, UsageReport):
            output.handle_usage_report(ev)
            status.input_tokens = ev.input_tokens
            status.output_tokens = ev.output_tokens
            if ev.total_cost_usd is not None:
                status.cost_usd = ev.total_cost_usd

        elif isinstance(ev, SessionEnd):
            status.is_running = False
            self._stop_provider_idle_watch()
            self._last_session_success = ev.success
            if not ev.success:
                self._last_error_code = ev.error_code or self._last_error_code
                self._last_error_message = ev.error_message or self._last_error_message
                self._pending_fallback = (
                    self._auto_model_fallback
                    and self._last_user_prompt is not None
                    and self._is_fallback_eligible_failure()
                )
            # SessionEnd means Claude has logically finished this turn. Release
            # runner lock immediately to avoid completed-but-stuck UX states.
            with contextlib.suppress(Exception):
                self._provider_runner.mark_session_end()  # type: ignore[union-attr]
            if ev.success:
                target = target_for_route(self._active_provider, self._active_model)
                if target:
                    self._cooldown_until_by_alias.pop(target.alias, None)
                self._set_status_activity(status, "complete")
                output.write_system("[dim]\u2713 Session complete.[/dim]")
                self._pending_fallback = False
            else:
                detail = f"{ev.error_code}: {ev.error_message}" if ev.error_code else (
                    ev.error_message or "unknown provider failure"
                )
                self._set_status_activity(
                    status,
                    f"failed:{(ev.error_code or 'error')[:12]}",
                )
                detail = f"{ev.error_code}: {ev.error_message}" if ev.error_code else (
                    ev.error_message or "unknown provider failure"
                )
                output.write_error(f"[{BENGARA}]\u2717 Session failed -- {detail}[/{BENGARA}]")

        elif isinstance(ev, TaskStarted):
            self._set_status_activity(status, "agent:start")
            output.write_system(
                f"[dim]Subagent started: {ev.description}[/dim]"
            )

        elif isinstance(ev, TaskProgress):
            self._set_status_activity(status, "agent:work")
            output.write_system(f"[dim]Subagent progress: {ev.summary}[/dim]")

        elif isinstance(ev, TaskComplete):
            self._set_status_activity(
                status,
                f"agent:{'done' if ev.success else 'fail'}",
            )
            state = "ok" if ev.success else "error"
            output.write_system(
                f"[dim]Subagent complete ({state}): {ev.summary}[/dim]"
            )

        elif isinstance(ev, RateLimitEvent):
            msg = f"Rate limit: {ev.status}"
            if ev.utilization is not None:
                msg += f" ({ev.utilization * 100:.0f}%)"
            status_lower = (ev.status or "").lower()
            if status_lower:
                self._last_error_code = "rate_limit"
                self._last_error_message = msg
                if "rejected" in status_lower or "exhaust" in status_lower:
                    self._pending_fallback = (
                        self._auto_model_fallback
                        and self._last_user_prompt is not None
                    )
            self._set_status_activity(status, "rate-limited")
            output.write_system(f"[{OCHRE}]{msg}[/{OCHRE}]")

        elif isinstance(ev, ErrorEvent):
            self._last_error_code = ev.code or self._last_error_code
            self._last_error_message = ev.message or self._last_error_message
            self._set_status_activity(status, f"error:{(ev.code or 'provider')[:12]}")
            output.write_error(f"[{BENGARA}]{ev.code}: {ev.message}[/{BENGARA}]")

    def on_provider_runner_process_started(
        self, event: ProviderRunner.ProcessStarted
    ) -> None:
        """Update status bar when provider stream starts."""
        main = self._get_main_screen()
        if main:
            status: StatusBar = main.status_bar  # type: ignore[assignment]
            status.is_running = True
            self._set_status_activity(status, "starting")
            route = self._status_model_label()
            if self._inflight_provider == "codex":
                main.stream_output.write_system(  # type: ignore[union-attr]
                    "[dim]Starting Codex session on "
                    f"{route}. Live tools, usage, and cost will stream here; Ctrl+C cancels.[/dim]"
                )
            else:
                main.stream_output.write_system(  # type: ignore[union-attr]
                    f"[dim]Starting {route}...[/dim]"
                )
            self._start_provider_idle_watch()
            self.set_timer(1.5, self._report_slow_provider_start)
        btw = self._get_btw_screen()
        if btw is not None:
            btw.notify_main_process_started(self._status_model_label())

    def _report_slow_provider_start(self) -> None:
        """Surface a hint when a provider has not emitted any event yet."""
        if (
            not self._provider_runner
            or not self._provider_runner.is_running
            or self._provider_event_seen
        ):
            return
        main = self._get_main_screen()
        if not main:
            return
        route = self._status_model_label()
        self._set_status_activity(main.status_bar, "waiting")  # type: ignore[arg-type]
        main.stream_output.write_system(  # type: ignore[union-attr]
            "[dim]Still waiting for "
            f"{route} to emit its first event. Startup can be quiet for a few seconds; Ctrl+C cancels.[/dim]"
        )

    def _start_provider_idle_watch(self) -> None:
        self._stop_provider_idle_watch()
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self._provider_idle_timer = None
            return
        self._last_provider_event_ts = time.time()
        self._last_provider_event_label = "process started"
        self._last_idle_notice_ts = 0.0
        self._provider_idle_timer = self.set_interval(5.0, self._report_provider_inactivity)

    def _stop_provider_idle_watch(self) -> None:
        if self._provider_idle_timer is not None:
            self._provider_idle_timer.stop()
            self._provider_idle_timer = None

    def _provider_event_label(self, ev: Any) -> str:
        if isinstance(ev, SessionStart):
            return "session connected"
        if isinstance(ev, TextDelta):
            return "assistant text"
        if isinstance(ev, TextComplete):
            return "assistant reply" if ev.role == "assistant" else "codex progress note"
        if isinstance(ev, ThinkingDelta | ThinkingComplete):
            return "thinking"
        if isinstance(ev, ToolCallComplete):
            return f"tool {ev.tool_name or 'shell'} started"
        if isinstance(ev, ToolProgress):
            return f"tool {ev.tool_name or 'shell'} running"
        if isinstance(ev, ToolResult):
            return f"tool {ev.tool_name or 'shell'} finished"
        if isinstance(ev, UsageReport):
            return "usage update"
        if isinstance(ev, ErrorEvent):
            return f"error {ev.code or 'provider'}"
        if isinstance(ev, SessionEnd):
            return "session complete"
        if isinstance(ev, TaskStarted):
            return "subagent started"
        if isinstance(ev, TaskProgress):
            return "subagent progress"
        if isinstance(ev, TaskComplete):
            return "subagent complete"
        return getattr(ev, "type", "provider event")

    def _report_provider_inactivity(self) -> None:
        if not self._provider_runner or not self._provider_runner.is_running:
            self._stop_provider_idle_watch()
            return
        if self._recover_stale_provider_lock_from_session_meta():
            return
        if self._last_provider_event_ts is None:
            return
        idle_for = time.time() - self._last_provider_event_ts
        if idle_for < 8:
            return
        now = time.time()
        if (now - self._last_idle_notice_ts) < 10:
            return
        main = self._get_main_screen()
        if not main:
            return
        route = self._status_model_label()
        self._set_status_activity(main.status_bar, "waiting")  # type: ignore[arg-type]
        detail = (
            f"No new events from {route} for {int(idle_for)}s. "
            f"Last activity: {self._last_provider_event_label or 'startup'}."
        )
        if self._active_provider == "codex":
            if self._last_provider_event_label.startswith("tool ") and self._last_provider_event_label.endswith(" finished"):
                detail += (
                    " Codex may still be reasoning off-stream after the last tool result; "
                    "DGC only sees new output when Codex emits another JSON event or exits."
                )
            else:
                detail += (
                    " Codex can stay silent between JSON events; "
                    "DGC only sees new output when Codex emits another event or exits."
                )
            if idle_for >= 120:
                detail += " If this keeps stretching, Ctrl+C or /cancel recovers the lane."
            else:
                detail += " Ctrl+C or /cancel cancels."
        else:
            if idle_for >= 120:
                detail += " If this keeps stretching, Ctrl+C or /cancel recovers the lane."
            else:
                detail += " Ctrl+C or /cancel cancels."
        main.stream_output.write_system(  # type: ignore[union-attr]
            f"[dim]{detail}[/dim]"
        )
        self._last_idle_notice_ts = now

    def on_provider_runner_process_exited(
        self, event: ProviderRunner.ProcessExited
    ) -> None:
        """Update status bar and show exit info when provider run finishes."""
        main = self._get_main_screen()
        if not main:
            return

        status: StatusBar = main.status_bar  # type: ignore[assignment]
        status.is_running = False
        output: StreamOutput = main.stream_output  # type: ignore[assignment]
        self._stop_provider_idle_watch()
        btw = self._get_btw_screen()
        if btw is not None:
            btw.notify_main_process_exited(event.exit_code, event.was_cancelled)

        if event.was_cancelled:
            self._set_status_activity(status, "cancelled")
            output.write_system(f"[{OCHRE}]Cancelled.[/{OCHRE}]")
            self._inflight_provider = None
            self._inflight_model = None
            self._inflight_started_ts = None
            self._last_session_success = None
            self._pending_fallback = False
            self._provider_event_seen = False
        else:
            latency_ms: float | None = None
            if self._inflight_started_ts is not None:
                latency_ms = max(1.0, (time.time() - self._inflight_started_ts) * 1000.0)
            inferred_success: bool | None
            if event.was_cancelled:
                inferred_success = None
            elif self._last_session_success is not None:
                inferred_success = self._last_session_success
            else:
                inferred_success = event.exit_code == 0
            self._record_model_result(
                provider_id=self._inflight_provider,
                model_id=self._inflight_model,
                success=inferred_success,
                latency_ms=latency_ms,
                error_code=self._last_error_code,
            )
            self._inflight_provider = None
            self._inflight_model = None
            self._inflight_started_ts = None
            self._last_session_success = None
            self._provider_event_seen = False

        if (not event.was_cancelled) and event.exit_code != 0:
            self._set_status_activity(status, f"process:{event.exit_code}")
            output.write_error(
                f"[{BENGARA}]Process exited with code {event.exit_code}[/{BENGARA}]"
            )
        needs_fallback = (not event.was_cancelled) and (
            self._pending_fallback
            or (event.exit_code != 0 and self._is_fallback_eligible_failure())
        )
        if needs_fallback:
            self._try_auto_fallback(
                output,
                reason="session failure" if self._pending_fallback else "process exit",
            )

    def _is_fallback_eligible_failure(self) -> bool:
        code = (self._last_error_code or "").lower()
        msg = (self._last_error_message or "").lower()
        hay = f"{code} {msg}"
        retry_terms = (
            "timeout",
            "rate_limit",
            "rate limit",
            "rate_limit_rejected",
            "429",
            "subscription",
            "quota",
            "billing",
            "usage_exhausted",
            "out of extra usage",
            "rejected",
            "logged out",
            "sign in",
            "login",
            "missing_auth",
            "unauthorized",
            "missing_api_key",
            "401",
            "403",
            "process_exit",
            "provider_not_implemented",
            "http_5",
            "http_4",
            "openrouter_error",
        )
        return any(term in hay for term in retry_terms)

    # ─── Input Handling ──────────────────────────────────────────────

    def on_prompt_input_submitted(self, event: PromptInput.Submitted) -> None:
        """Handle user input -- route to command handler or active provider."""
        text = event.text.strip()
        if not text:
            return

        main = self._get_main_screen()
        if not main:
            return

        output: StreamOutput = main.stream_output  # type: ignore[assignment]

        if text.startswith("/"):
            cmd_text = text[1:]
            self._dispatch_system_command(cmd_text, output)
        else:
            bare_cmd, notice = self._commands.resolve_bare_command(text)
            if notice:
                output.write_system(notice)
            if bare_cmd:
                self._dispatch_system_command(bare_cmd, output)
                return
            if notice:
                return
            output.write_user(text)
            if self._maybe_handle_inline_model_switch(text):
                return
            self._send_to_claude(text)

    def _dispatch_system_command(self, cmd_text: str, output: StreamOutput) -> None:
        """Echo and execute a system command from prompt input."""
        output.write_system(f"[dim]/{cmd_text}[/dim]")
        out_text, action = self._commands.handle(cmd_text)

        if out_text:
            output.write(out_text)

        if action:
            self._handle_action(action, cmd_text)

    def _handle_action(self, action: str, raw_cmd: str) -> None:
        """Dispatch action signals returned by SystemCommandHandler."""
        main = self._get_main_screen()
        if not main:
            return

        output: StreamOutput = main.stream_output  # type: ignore[assignment]

        if action == "clear":
            output.clear()

        elif action == "cancel":
            if self._provider_runner and self._provider_runner.is_running:
                self._provider_runner.cancel()
                output.write_system(f"[{OCHRE}]Cancel signal sent.[/{OCHRE}]")
            else:
                output.write_system("[dim]No active provider run.[/dim]")

        elif action == "chat:new":
            self._launch_chat_shell(continue_last=False)

        elif action == "chat:continue":
            self._launch_chat_shell(continue_last=True)

        elif action == "paste":
            self._paste_clipboard()

        elif action in {"copy", "copylast"}:
            self._copy_last_reply()

        elif action == "btw:open":
            _, _, arg = raw_cmd.partition(" ")
            self._open_btw_screen(initial_text=arg.strip())

        elif action.startswith("mode:set:"):
            target_mode = action.split(":", 2)[2] if ":" in action else ""
            if self._set_mode(target_mode):
                mode_name = _MODE_NAMES[self._mode].title()
                output.write_system(f"[dim]Mode set to [{self._mode}] {mode_name}.[/dim]")
            else:
                output.write_error(f"[{BENGARA}]Unknown mode: {target_mode}[/{BENGARA}]")

        elif action == "model:status":
            output.write(
                format_model_status(
                    self._active_provider,
                    self._active_model,
                    self._auto_model_fallback,
                    strategy=self._model_strategy,
                    preferred=self._preferred_target(),
                    cooldown_count=self._cooldown_active_count(),
                )
            )

        elif action == "model:list":
            output.write(
                format_model_list(
                    self._active_provider,
                    self._active_model,
                    auto_fallback=self._auto_model_fallback,
                    strategy=self._model_strategy,
                    preferred_key=route_key(
                        self._preferred_provider, self._preferred_model
                    ),
                    available_keys=self._available_route_keys(),
                    cooldown_until=self._cooldown_until_by_alias,
                    model_stats_by_alias=self._model_stats,
                )
            )

        elif action == "model:metrics":
            output.write(self._format_model_metrics_report())

        elif action.startswith("model:cooldown "):
            mode = action[len("model:cooldown ") :].strip().lower()
            if mode == "status":
                active = self._cooldown_active_count()
                output.write_system(
                    f"[dim]Cooling models: {active}[/dim]"
                )
            elif mode == "clear":
                self._cooldown_until_by_alias = {}
                output.write_system("[dim]Model cooldowns cleared.[/dim]")
            else:
                output.write_error(
                    f"[{BENGARA}]Usage: /model cooldown [status|clear][/{BENGARA}]"
                )

        elif action.startswith("model:set "):
            raw = action[len("model:set ") :].strip()
            target = self._parse_model_set_target(raw)
            if target is None:
                output.write_error(
                    f"[{BENGARA}]Unknown model '{raw}'. Use /model list.[/{BENGARA}]"
                )
                return
            self._set_active_model(
                provider_id=target.provider_id,
                model_id=target.model_id,
                announce=True,
                reason="manual switch",
                set_preferred=True,
                persist_preference=True,
            )

        elif action.startswith("model:auto "):
            mode = action[len("model:auto ") :].strip().lower()
            if mode == "status":
                output.write_system(
                    "[dim]Auto-fallback: "
                    f"{'ON' if self._auto_model_fallback else 'OFF'} "
                    f"| Strategy: {self._model_strategy}[/dim]"
                )
            elif mode in {"on", "off"}:
                self._auto_model_fallback = mode == "on"
                self._save_model_policy()
                output.write_system(
                    "[dim]Auto-fallback "
                    f"{'enabled' if self._auto_model_fallback else 'disabled'}.[/dim]"
                )
            elif mode in ROUTING_STRATEGIES:
                self._model_strategy = mode
                self._auto_model_fallback = True
                self._save_model_policy()
                output.write_system(
                    "[dim]Auto-fallback strategy set to "
                    f"{self._model_strategy}.[/dim]"
                )
            else:
                output.write_error(
                    f"[{BENGARA}]Usage: /model auto "
                    "[on|off|status|responsive|cost|genius]"
                    f"[/{BENGARA}]"
                )

        elif action.startswith("async:"):
            parts = action.split(":", 2)
            cmd = parts[1] if len(parts) > 1 else ""
            arg = parts[2] if len(parts) > 2 else ""
            self._run_async_command(cmd, arg)

    # ─── Provider Chat ───────────────────────────────────────────────

    def _maybe_handle_inline_model_switch(self, text: str) -> bool:
        target = detect_inline_switch_intent(text)
        if target is None:
            return False

        # Only intercept if this is a direct switch request.
        if not re.match(
            r"^\s*(?:hey[,\s]+)?(?:please\s+)?(?:switch|change|set|move|use)\b",
            text,
            re.IGNORECASE,
        ):
            return False

        self._set_active_model(
            provider_id=target.provider_id,
            model_id=target.model_id,
            announce=True,
            reason="inline request",
            set_preferred=True,
            persist_preference=True,
        )
        return True

    def _send_to_claude(self, text: str) -> None:
        """Backward-compatible entrypoint for prompt dispatch."""
        self._dispatch_prompt(text)

    def _dispatch_prompt(
        self,
        text: str,
        *,
        append_user: bool = True,
        reset_fallback_queue: bool = True,
    ) -> None:
        """Send user prompt through the active provider/model route."""
        if not self._provider_runner:
            return

        if self._provider_runner.is_running:
            main = self._get_main_screen()
            if self._recover_stale_provider_lock_from_session_meta():
                main = self._get_main_screen()
            if (
                self._provider_runner.is_running
                and main
                and not main.status_bar.is_running  # type: ignore[union-attr]
            ):
                # Stale lock recovery: semantic session ended, worker finalization
                # may still be winding down. Unlock and continue.
                with contextlib.suppress(Exception):
                    self._provider_runner.cancel()
                with contextlib.suppress(Exception):
                    self._provider_runner.mark_session_end()  # type: ignore[attr-defined]
                main.stream_output.write_system(  # type: ignore[union-attr]
                    "[dim]Recovered stale provider lock after session end.[/dim]"
                )
            if self._provider_runner.is_running:
                if main:
                    main.stream_output.write_error(  # type: ignore[union-attr]
                        f"[{OCHRE}]Provider is already running. Use /cancel first.[/{OCHRE}]"
                    )
                return

        local_session_id = self._ensure_local_session_id()
        self._last_user_prompt = text
        self._last_error_code = None
        self._last_error_message = None

        if append_user:
            self._append_chat(role="user", content=text)

        if reset_fallback_queue:
            self._maybe_restore_preferred_model()

        if reset_fallback_queue:
            self._fallback_queue = self._build_fallback_queue()

        if not self._can_route_to(self._active_provider, self._active_model):
            main = self._get_main_screen()
            switched = False
            while self._auto_model_fallback and self._fallback_queue:
                provider_id, model_id = self._fallback_queue.pop(0)
                if not self._can_route_to(provider_id, model_id):
                    continue
                self._set_active_model(
                    provider_id=provider_id,
                    model_id=model_id,
                    announce=True,
                    reason="availability fallback",
                )
                switched = True
                break
            if not switched and not self._can_route_to(
                self._active_provider, self._active_model
            ):
                if main:
                    main.stream_output.write_error(  # type: ignore[union-attr]
                        f"[{BENGARA}]No available model route. Check /model list and credentials.[/{BENGARA}]"
                    )
                return

        # Build state context for system prompt injection
        state_ctx = self._get_state_context()
        system_parts: list[str] = []
        mode_prompt = self._build_mode_system_prompt()
        if mode_prompt:
            system_parts.append(mode_prompt)
        if state_ctx:
            system_parts.append(
                "DGC mission-control context snapshot. "
                "Treat as hints and verify.\n\n" + state_ctx[:6000]
            )
        system_append: str | None = "\n\n".join(system_parts) if system_parts else None

        if self._active_provider == "claude" and self._provider_session_id:
            messages = [{"role": "user", "content": text}]
            resume_session_id: str | None = self._provider_session_id
        else:
            messages = list(self._chat_history)
            if not messages or messages[-1].get("role") != "user":
                messages.append({"role": "user", "content": text})
            resume_session_id = None

        request = CompletionRequest(
            messages=messages,
            model=self._active_model,
            system_prompt=system_append,
            resume_session_id=resume_session_id,
            enable_thinking=True,
            provider_options={
                "internet_enabled": self._commands.internet_enabled,
                "permission_mode": self._resolve_permission_mode(),
            },
        )
        main = self._get_main_screen()
        if main:
            status: StatusBar = main.status_bar  # type: ignore[assignment]
            status.model = self._status_model_label()
            status.session_name = local_session_id[:8]
            self._reset_status_runtime(status, activity="queued")
            status.is_running = True
        self._inflight_provider = self._active_provider
        self._inflight_model = self._active_model
        self._inflight_started_ts = time.time()
        self._last_session_success = None
        self._pending_fallback = False
        self._provider_event_seen = False
        self._provider_runner.run_provider(
            request,
            session_id=local_session_id,
            provider_id=self._active_provider,
        )

    def _ensure_local_session_id(self) -> str:
        if self._session.session_id:
            return self._session.session_id
        sid = (
            f"dgc-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-"
            f"{secrets.token_hex(2)}"
        )
        self._session.session_id = sid
        return sid

    def _get_state_context(self) -> str:
        """Build live state context for Claude injection. Cached 60s."""
        now = time.time()
        if (now - self._state_cache_time) < 60 and self._state_cache:
            return self._state_cache

        parts: list[str] = []

        # Current research thread
        thread_file = DHARMA_STATE / "thread_state.json"
        if thread_file.exists():
            try:
                ts = json.loads(thread_file.read_text())
                parts.append(
                    f"Active thread: {ts.get('current_thread', 'unknown')}"
                )
            except Exception:
                pass

        # Recent memory
        try:
            from dharma_swarm.context import read_latent_gold_overview, read_memory_context

            mem = read_memory_context()
            if mem and "No memory" not in mem:
                parts.append(f"Recent memory:\n{mem}")
            latent = read_latent_gold_overview(state_dir=DHARMA_STATE, limit=3)
            if latent:
                parts.append(f"Latent gold:\n{latent}")
        except Exception:
            pass

        # Ecosystem status from manifest
        manifest = HOME / ".dharma_manifest.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text())
                eco = data.get("ecosystem", {})
                if eco:
                    alive = sum(1 for v in eco.values() if v.get("exists"))
                    parts.append(f"Ecosystem: {alive}/{len(eco)} alive")
            except Exception:
                pass

        result = "\n".join(parts) if parts else ""
        self._state_cache = result
        self._state_cache_time = now
        return result

    def _launch_chat_shell(self, continue_last: bool = False) -> None:
        """Suspend TUI and launch native Claude Code interactive UI."""
        env = dict(os.environ)
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", None)

        cmd = ["claude"]
        if continue_last:
            cmd.append("--continue")

        if self._commands.internet_enabled:
            cmd.extend([
                "--permission-mode",
                "bypassPermissions",
                "--dangerously-skip-permissions",
            ])
        else:
            env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"

        main = self._get_main_screen()
        if main:
            main.stream_output.write_system(  # type: ignore[union-attr]
                "[dim]Launching native Claude Code UI. Exit to return.[/dim]"
            )

        try:
            with self.suspend():
                subprocess.run(cmd, cwd=str(DHARMA_SWARM), env=env, check=False)
        except Exception as exc:
            if main:
                main.stream_output.write_error(  # type: ignore[union-attr]
                    f"[{BENGARA}]/chat failed: {exc}[/{BENGARA}]"
                )
        finally:
            if main:
                main.stream_output.write_system(  # type: ignore[union-attr]
                    "[dim]Returned from Claude Code.[/dim]"
                )
                self.set_timer(0.05, main._focus_input)

    # ─── Async System Commands (threaded) ────────────────────────────

    @work(thread=True)
    def _run_async_command(self, cmd: str, arg: str) -> None:
        """Run system commands that need I/O or subprocesses in a thread."""
        main = self._get_main_screen()
        if not main:
            return

        def out(msg: str) -> None:
            self.call_from_thread(main.stream_output.write, msg)

        try:
            self._dispatch_async(cmd, arg, out)
        except Exception as exc:
            out(f"[{BENGARA}]Command error: {exc}[/{BENGARA}]")

    def _dispatch_async(
        self,
        cmd: str,
        arg: str,
        out: Any,
    ) -> None:
        """Dispatch a threaded system command to its handler.

        Args:
            cmd: Command name (status, pulse, health, etc.).
            arg: Arguments string after the command name.
            out: Callable that writes Rich-markup text to the output widget.
        """
        if cmd == "status":
            from dharma_swarm.tui_helpers import build_status_text

            out(build_status_text())

        elif cmd == "pulse":
            out("[dim]Running pulse...[/dim]")
            from dharma_swarm.pulse import pulse

            result = str(pulse())[:2000]
            for line in result.split("\n"):
                out(f"  {line}")
            out(f"[{VERDIGRIS}]Pulse done.[/{VERDIGRIS}]")

        elif cmd == "health":
            out("[dim]Checking health...[/dim]")
            from dharma_swarm.ecosystem_bridge import scan_ecosystem

            eco = scan_ecosystem()
            ok = sum(1 for v in eco.values() if v.get("exists"))
            missing = sum(1 for v in eco.values() if not v.get("exists"))
            out(
                f"  [{VERDIGRIS}]{ok} OK[/{VERDIGRIS}]  "
                f"[{BENGARA}]{missing} missing[/{BENGARA}]"
            )
            for name, info in eco.items():
                if not info.get("exists"):
                    out(f"  [{BENGARA}]MISSING[/{BENGARA}] {name} -- {info.get('path', '?')}")

        elif cmd == "memory":
            out("[dim]Loading memory...[/dim]")
            from dharma_swarm.context import read_latent_gold_overview, read_memory_context

            ctx = read_memory_context()
            for line in ctx.split("\n")[:30]:
                out(f"  {line}")
            latent = read_latent_gold_overview(state_dir=DHARMA_STATE, limit=5)
            if latent:
                out(f"  [{INDIGO}]Latent gold[/{INDIGO}]")
                for line in latent.split("\n")[:10]:
                    out(f"  {line}")

        elif cmd == "witness":
            if not arg:
                out(f"[{BENGARA}]Usage: /witness <observation>[/{BENGARA}]")
            else:
                from datetime import datetime, timezone

                witness_dir = DHARMA_STATE / "witness"
                witness_dir.mkdir(parents=True, exist_ok=True)
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                log_file = witness_dir / f"{today}.jsonl"
                entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "observation": arg,
                    "source": "tui",
                }
                with open(log_file, "a") as fh:
                    fh.write(json.dumps(entry) + "\n")
                out(f"  [{VERDIGRIS}]Witnessed[/{VERDIGRIS}] -> {log_file.name}")

        elif cmd == "gates":
            action = arg or "echo test"
            out(f"[dim]Testing gates: {action}[/dim]")
            from dharma_swarm.telos_gates import check_action

            result = check_action(action=action)
            decision = result.decision.value
            color = "green" if decision == "allow" else "red"
            out(f"  [{color}]{decision}[/{color}]: {result.reason}")

        elif cmd == "agni":
            if not arg:
                out(f"[{BENGARA}]Usage: /agni <command>[/{BENGARA}]")
            else:
                from dharma_swarm.telos_gates import check_with_reflective_reroute

                gate = check_with_reflective_reroute(
                    action=f"agni:{arg}",
                    content=arg,
                    tool_name="tui_agni",
                    think_phase="before_complete",
                    reflection=(
                        "Remote AGNI execution request. Validate blast radius, "
                        "rollback path, and least-privilege command intent."
                    ),
                    max_reroutes=1,
                    requirement_refs=["agni:remote_exec"],
                )
                if gate.result.decision.value == "block":
                    out(f"[{BENGARA}]TELOS BLOCK[/{BENGARA}]: {gate.result.reason}")
                    return
                if gate.attempts:
                    out(
                        "[dim]Witness reroute applied "
                        f"({gate.attempts} attempts).[/dim]"
                    )

                out(f"[dim]AGNI: {arg}[/dim]")
                ssh_key = HOME / ".ssh" / "openclaw_do"
                proc = subprocess.run(
                    [
                        "ssh",
                        "-i",
                        str(ssh_key),
                        "-o",
                        "ConnectTimeout=10",
                        "root@157.245.193.15",
                        arg,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if proc.stdout:
                    for line in proc.stdout.split("\n")[:30]:
                        out(f"  {line}")
                if proc.stderr:
                    out(f"  [{BENGARA}]{proc.stderr.strip()[:200]}[/{BENGARA}]")

        elif cmd == "swarm":
            out(f"[dim]swarm {arg}[/dim]")
            orch_path = DHARMA_STATE / "orchestrator_state.json"
            if orch_path.exists():
                try:
                    orch = json.loads(orch_path.read_text())
                    for k, v in orch.items():
                        out(f"  {k}: {v}")
                except Exception:
                    out("[dim]Orchestrator state unreadable.[/dim]")
            else:
                out("[dim]No orchestrator state.[/dim]")

        elif cmd == "evolve":
            evolve_mode = arg.strip().lower()
            if evolve_mode in {"status", "report", "memory"}:
                from dharma_swarm.tui_helpers import build_darwin_status_text

                out(build_darwin_status_text())
            elif not arg or len(arg.split(None, 1)) < 2:
                out(f"[{BENGARA}]Usage: /evolve <component> <description>[/{BENGARA}]")
            else:
                parts = arg.split(None, 1)
                out(f"[dim]Evolving {parts[0]}...[/dim]")
                try:
                    import asyncio

                    from dharma_swarm.swarm import SwarmManager

                    mgr = SwarmManager()
                    result = asyncio.run(mgr.evolve(parts[0], parts[1]))
                    out(f"  [{VERDIGRIS}]Evolution result: {result}[/{VERDIGRIS}]")
                except Exception as exc:
                    out(f"  [{BENGARA}]Evolution failed: {exc}[/{BENGARA}]")

        elif cmd == "darwin":
            from dharma_swarm.tui_helpers import build_darwin_status_text

            out(build_darwin_status_text())

        elif cmd == "archive":
            out("[dim]Loading archive...[/dim]")
            archive_path = DHARMA_STATE / "evolution" / "archive.jsonl"
            if archive_path.exists():
                from dharma_swarm.archive import FitnessScore

                entries: list[dict[str, Any]] = []
                for line in archive_path.read_text().strip().split("\n")[-10:]:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
                for entry in entries:
                    fitness_payload = entry.get("fitness", {})
                    try:
                        weighted = FitnessScore(**fitness_payload).weighted()
                    except Exception:
                        weighted = 0.0
                    out(
                        f"  {entry.get('id', '?')[:12]}  "
                        f"{entry.get('component', '?')}  "
                        f"{entry.get('promotion_state', 'candidate')}  "
                        f"{entry.get('execution_profile', 'default')}  "
                        f"fit={weighted:.2f}"
                    )
            else:
                out("[dim]No archive found.[/dim]")

        elif cmd == "logs":
            out("[dim]Tailing logs...[/dim]")
            log_dir = DHARMA_STATE / "logs"
            if log_dir.exists():
                logs = sorted(
                    log_dir.glob("*.log"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )[:3]
                for lf in logs:
                    out(f"  [bold]{lf.name}[/bold]")
                    try:
                        for line in lf.read_text().split("\n")[-5:]:
                            out(f"    {line}")
                    except Exception:
                        pass
            else:
                out("[dim]No logs directory.[/dim]")

        elif cmd == "self":
            out("[dim]Building self-map...[/dim]")
            src_files = list((DHARMA_SWARM / "dharma_swarm").glob("*.py"))
            test_files = list((DHARMA_SWARM / "tests").glob("test_*.py"))
            out(f"  Source modules: {len(src_files)}")
            out(f"  Test files: {len(test_files)}")
            total = sum(len(f.read_text().split("\n")) for f in src_files)
            out(f"  Total source lines: ~{total}")

        elif cmd == "context":
            role = arg or "general"
            out(f"[dim]Context layers for role: {role}[/dim]")
            try:
                from dharma_swarm.context import build_agent_context

                ctx = build_agent_context(role=role)
                for line in ctx.split("\n")[:40]:
                    out(f"  {line}")
            except Exception as exc:
                out(f"  [{BENGARA}]Context failed: {exc}[/{BENGARA}]")

        elif cmd == "runtime":
            from dharma_swarm.tui_helpers import build_runtime_status_text

            out(build_runtime_status_text())

        elif cmd == "git":
            out("[dim]Git status...[/dim]")
            proc = subprocess.run(
                ["git", "log", "--oneline", "-5"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(DHARMA_SWARM),
            )
            for line in proc.stdout.strip().split("\n"):
                out(f"  {line}")

        elif cmd == "truth":
            out("[dim]Truth report...[/dim]")
            manifest = HOME / ".dharma_manifest.json"
            if manifest.exists():
                try:
                    data = json.loads(manifest.read_text())
                    out(f"  Manifest: {len(data)} entries")
                except Exception:
                    out("  [dim]Manifest unreadable[/dim]")
            else:
                out("  [dim]No manifest found[/dim]")

        elif cmd == "dharma":
            sub = arg.split(None, 1) if arg else []
            subcmd = sub[0].lower() if sub else "status"
            if subcmd == "status":
                out("[dim]Dharma status...[/dim]")
                try:
                    from dharma_swarm.dharma_kernel import DharmaKernel

                    k = DharmaKernel.create_default()
                    out(f"  Axioms: {len(k.principles)}")
                    out(f"  Integrity: {k.verify_integrity()}")
                except Exception as exc:
                    out(f"  [{BENGARA}]Dharma kernel: {exc}[/{BENGARA}]")
            elif subcmd == "corpus":
                self._dispatch_async("corpus", "", out)
            else:
                out(f"[{BENGARA}]Usage: /dharma [status|corpus][/{BENGARA}]")

        elif cmd == "corpus":
            out("[dim]Corpus claims...[/dim]")
            try:
                import asyncio

                from dharma_swarm.dharma_corpus import DharmaCorpus

                corpus = DharmaCorpus()
                claims = asyncio.run(corpus.list_claims())
                out(f"  Total claims: {len(claims)}")
                for c in claims[:10]:
                    out(f"  [{c.status.value}] {c.statement[:60]}")
            except Exception as exc:
                out(f"  [{BENGARA}]Corpus: {exc}[/{BENGARA}]")

        elif cmd == "stigmergy":
            out("[dim]Stigmergy...[/dim]")
            try:
                import asyncio

                from dharma_swarm.stigmergy import StigmergyStore

                store = StigmergyStore()
                hot = asyncio.run(
                    store.hot_paths(window_hours=24, min_marks=2)
                )
                high = asyncio.run(store.high_salience(threshold=0.7, limit=5))
                out(f"  Hot paths ({len(hot)}):")
                for path, count in hot[:5]:
                    out(f"    {path}: {count} marks")
                out(f"  High salience ({len(high)}):")
                for m in high[:5]:
                    out(
                        f"    {m.file_path}: {m.observation[:50]} "
                        f"(s={m.salience:.2f})"
                    )
            except Exception as exc:
                out(f"  [{BENGARA}]Stigmergy: {exc}[/{BENGARA}]")

        elif cmd == "hum":
            out("[dim]Subconscious dreams...[/dim]")
            try:
                import asyncio

                from dharma_swarm.stigmergy import StigmergyStore
                from dharma_swarm.subconscious import SubconsciousStream

                store = StigmergyStore()
                sub = SubconsciousStream(stigmergy=store)
                dreams = asyncio.run(sub.dream(sample_size=5))
                out(f"  Dreams ({len(dreams)}):")
                for d in dreams[:5]:
                    out(
                        f"    {d.source_a[:25]} <-> {d.source_b[:25]}: "
                        f"{d.resonance_type} ({d.strength:.2f})"
                    )
            except Exception as exc:
                out(f"  [{BENGARA}]HUM: {exc}[/{BENGARA}]")

        else:
            out(f"[{BENGARA}]Unknown async command: {cmd}[/{BENGARA}]")

    @work(thread=True)
    def _run_status_on_startup(self) -> None:
        """Display system status on first load."""
        main = self._get_main_screen()
        if not main:
            return

        def out(msg: str) -> None:
            self.call_from_thread(main.stream_output.write, msg)

        try:
            from dharma_swarm.tui_helpers import build_status_text

            out(build_status_text())
        except ImportError:
            out("[dim]DGC v1 -- Ready[/dim]")

    # ─── Actions (key bindings) ──────────────────────────────────────

    def action_cancel_run(self) -> None:
        """Cancel the running provider stream."""
        if self._provider_runner and self._provider_runner.is_running:
            self._provider_runner.cancel()

    def action_smart_cancel_or_copy(self) -> None:
        """Ctrl+C: if running, cancel. If idle, copy last reply to clipboard."""
        # If a provider is running, cancel it
        if self._provider_runner and self._provider_runner.is_running:
            self.action_cancel_run()
            return
        # Otherwise, copy the last assistant reply to clipboard
        main = self._get_main_screen()
        if main:
            output = main.stream_output
            if hasattr(output, "copy_last_reply_to_clipboard"):
                if output.copy_last_reply_to_clipboard():
                    output.write_system(
                        f"[dim {INDIGO}]Copied last reply to clipboard.[/dim {INDIGO}]"
                    )
                else:
                    output.write_system(
                        "[dim]No reply to copy. "
                        "Tip: Shift+drag for native terminal selection.[/dim]"
                    )

    def action_scroll_to_bottom(self) -> None:
        """Jump to bottom of stream output and re-enable auto-scroll."""
        main = self._get_main_screen()
        if main and hasattr(main.stream_output, "scroll_to_bottom"):
            main.stream_output.scroll_to_bottom()

    def action_clear_output(self) -> None:
        """Clear the stream output widget."""
        main = self._get_main_screen()
        if main:
            main.stream_output.clear()

    def action_cycle_mode(self) -> None:
        """Cycle through N -> A -> P -> S operating modes."""
        idx = _MODE_KEYS.index(self._mode) if self._mode in _MODE_KEYS else 0
        self._set_mode(_MODE_KEYS[(idx + 1) % len(_MODE_KEYS)])

    def action_new_session(self) -> None:
        """Reset session state and clear the output."""
        self._session = SessionState()
        self._provider_session_id = None
        self._chat_history = []
        self._last_user_prompt = None
        self._fallback_queue = []
        self._last_error_code = None
        self._last_error_message = None
        self._inflight_provider = None
        self._inflight_model = None
        self._inflight_started_ts = None
        self._last_session_success = None
        self._pending_fallback = False
        main = self._get_main_screen()
        if main:
            main.stream_output.clear()
            main.stream_output.write_system(  # type: ignore[union-attr]
                "[dim]New session started.[/dim]"
            )
            status: StatusBar = main.status_bar  # type: ignore[assignment]
            self._init_status_bar(status, model=self._status_model_label())
            status.session_name = ""
            status.cost_usd = 0.0
            status.turn_count = 0
            self._reset_status_runtime(status)

    # ─── Clipboard ───────────────────────────────────────────────────

    def _paste_clipboard(self) -> None:
        """Paste clipboard contents into the prompt input."""
        try:
            proc = subprocess.run(
                ["pbpaste"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if proc.stdout:
                main = self._get_main_screen()
                if main:
                    pi = main.prompt_input
                    # Insert text at cursor via the TextArea API
                    start, end = pi.selection
                    pi._replace_via_keyboard(proc.stdout, start, end)
        except Exception:
            pass

    def _copy_last_reply(self) -> None:
        """Copy last assistant reply to clipboard."""
        main = self._get_main_screen()
        if main:
            output = main.stream_output
            if hasattr(output, "copy_last_reply_to_clipboard"):
                if output.copy_last_reply_to_clipboard():
                    output.write_system(
                        f"[dim {INDIGO}]Copied last reply to clipboard.[/dim {INDIGO}]"
                    )
                    return
            output.write_system(  # type: ignore[union-attr]
                "[dim]No reply to copy.\n"
                "  [bold]Ctrl+C[/bold] (when idle) copies last reply.\n"
                "  [bold]Shift+drag[/bold] for native terminal selection.[/dim]"
            )

    def action_copy_last(self) -> None:
        """Ctrl+Y: copy last assistant reply to clipboard."""
        self._copy_last_reply()

    # ─── Mode Policy ─────────────────────────────────────────────────

    def _resolve_permission_mode(self) -> str:
        """Resolve provider permission mode based on active DGC mode."""
        if self._mode == "P":
            return "default"
        return "bypassPermissions"

    def _build_mode_system_prompt(self) -> str | None:
        """Build mode-specific system policy instructions."""
        if self._mode == "P":
            return _PLAN_MODE_SYSTEM_PROMPT
        return None

    def _set_mode(self, mode: str) -> bool:
        """Apply mode change and synchronize UI + command handler state."""
        if mode not in _MODE_NAMES:
            return False

        self._mode = mode
        self._commands.set_mode(mode)

        main = self._get_main_screen()
        if main:
            main.status_bar.mode = self._mode  # type: ignore[union-attr]
            for name in _MODE_NAMES.values():
                self.remove_class(f"mode-{name}")
            self.add_class(f"mode-{_MODE_NAMES[self._mode]}")

        return True
