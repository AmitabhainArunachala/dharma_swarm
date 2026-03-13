"""BTW side-thread modal for parallel conversations during main-agent runs."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import RichLog, Static

from ..engine.adapters import CompletionRequest
from ..engine.events import (
    ErrorEvent,
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
from ..engine.provider_runner import ProviderRunner
from ..engine.session_state import SessionState
from ..widgets.prompt_input import PromptInput
from ..widgets.stream_output import StreamOutput

INDIGO = "#9C7444"
VERDIGRIS = "#62725D"
OCHRE = "#A17A47"
BENGARA = "#8C5448"
WISTERIA = "#74677D"


class BTWScreen(ModalScreen[None]):
    """Parallel side-thread modal with its own chat runner and main watcher."""

    BINDINGS = [
        Binding("escape", "dismiss_overlay", "Close"),
        Binding("ctrl+m", "merge_thread", "Merge"),
    ]

    DEFAULT_CSS = """
    BTWScreen {
        align: center middle;
    }

    #btw-shell {
        width: 92%;
        height: 88%;
        border: thick #46525B;
        background: #0D0E13;
        padding: 1 1 0 1;
    }

    #btw-header {
        height: 3;
        margin: 0 0 1 0;
        color: #DCCFBD;
    }

    #btw-columns {
        height: 1fr;
    }

    #btw-chat {
        width: 2fr;
        border: tall #313B37;
        margin: 0 1 1 0;
    }

    #btw-watch {
        width: 1fr;
        border: tall #46525B;
        background: #111218;
        color: #A89A8B;
        margin: 0 0 1 0;
        padding: 0 1;
    }

    #btw-prompt {
        margin: 0;
    }
    """

    def __init__(self, *, initial_text: str = "") -> None:
        super().__init__()
        self._initial_text = initial_text.strip()
        self._session = SessionState()
        self._provider_runner: ProviderRunner | None = None
        self._thread_id = f"btw-{datetime.now():%H%M%S}-{secrets.token_hex(2)}"
        self._transcript: list[dict[str, str]] = []
        self._status: str = "ready"
        self._cost_usd: float = 0.0

    def compose(self) -> ComposeResult:
        with Vertical(id="btw-shell"):
            yield Static(id="btw-header")
            with Horizontal(id="btw-columns"):
                yield StreamOutput(id="btw-chat")
                yield RichLog(
                    id="btw-watch",
                    markup=True,
                    highlight=False,
                    wrap=True,
                )
            yield PromptInput(id="btw-prompt")
            runner = ProviderRunner(id="btw-provider-runner")
            self._provider_runner = runner
            yield runner

    def on_mount(self) -> None:
        self._refresh_header()
        self.watch_log.write(
            "[dim]Watching the main agent here while this BTW thread runs in parallel.[/dim]"
        )
        self.watch_log.write(
            "[dim]/merge folds this side thread into main context. Esc closes the overlay.[/dim]"
        )
        if self._initial_text:
            self.set_timer(0.05, self._send_initial_prompt)
        else:
            self.set_timer(0.05, self._focus_prompt)

    def _focus_prompt(self) -> None:
        with self.app.batch_update():
            self.prompt_input.focus()

    def _send_initial_prompt(self) -> None:
        text = self._initial_text
        self._initial_text = ""
        if not text:
            self._focus_prompt()
            return
        self.chat_output.write_user(text)
        self._transcript.append({"role": "user", "content": text})
        self._dispatch_prompt(text)

    @property
    def chat_output(self) -> StreamOutput:
        return self.query_one("#btw-chat", StreamOutput)

    @property
    def watch_log(self) -> RichLog:
        return self.query_one("#btw-watch", RichLog)

    @property
    def prompt_input(self) -> PromptInput:
        return self.query_one("#btw-prompt", PromptInput)

    def action_dismiss_overlay(self) -> None:
        self.dismiss()

    def action_merge_thread(self) -> None:
        self._merge_into_main()

    def on_prompt_input_submitted(self, event: PromptInput.Submitted) -> None:
        event.stop()
        text = event.text.strip()
        if not text:
            return
        if text.startswith("/"):
            self._handle_local_command(text[1:].strip())
            return
        self.chat_output.write_user(text)
        self._transcript.append({"role": "user", "content": text})
        self._dispatch_prompt(text)

    def _handle_local_command(self, raw: str) -> None:
        parts = raw.split(None, 1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1] if len(parts) > 1 else ""
        if cmd in {"merge", "m"}:
            self._merge_into_main(extra_note=arg or None)
            return
        if cmd in {"close", "quit", "q", "dismiss"}:
            self.dismiss()
            return
        if cmd == "help":
            self.chat_output.write_system(
                "[dim]/merge folds this side thread into the main conversation. "
                "/close dismisses the BTW window.[/dim]"
            )
            return
        self.chat_output.write_error(
            f"[{BENGARA}]Unknown BTW command: /{cmd}[/{BENGARA}]"
        )

    def _dispatch_prompt(self, text: str) -> None:
        if not self._provider_runner:
            return
        if self._provider_runner.is_running:
            self.chat_output.write_error(
                f"[{OCHRE}]BTW thread is already running. Wait or /close it.[/{OCHRE}]"
            )
            return

        app = self.app
        provider = getattr(app, "_active_provider", "codex")
        model = getattr(app, "_active_model", "gpt-5.4")
        system_parts = [
            "BTW side thread: this is a parallel conversation beside the main DGC run. "
            "Stay self-contained, concise, and merge-ready."
        ]
        get_state_context = getattr(app, "_get_state_context", None)
        if callable(get_state_context):
            state_ctx = get_state_context()
            if state_ctx:
                system_parts.append(
                    "Relevant mission-control context. Verify as needed.\n\n"
                    + state_ctx[:4000]
                )
        permission_mode = "suggest"
        resolve_permission_mode = getattr(app, "_resolve_permission_mode", None)
        if callable(resolve_permission_mode):
            permission_mode = resolve_permission_mode()
        internet_enabled = getattr(getattr(app, "_commands", None), "internet_enabled", True)

        request = CompletionRequest(
            messages=list(self._transcript),
            model=model,
            system_prompt="\n\n".join(system_parts),
            enable_thinking=True,
            provider_options={
                "internet_enabled": internet_enabled,
                "permission_mode": permission_mode,
            },
        )
        self._status = "queued"
        self._refresh_header()
        self._provider_runner.run_provider(
            request,
            session_id=self._thread_id,
            provider_id=provider,
        )

    def _merge_into_main(self, extra_note: str | None = None) -> None:
        app = self.app
        merge_fn = getattr(app, "merge_btw_thread", None)
        if not callable(merge_fn):
            self.chat_output.write_error(
                f"[{BENGARA}]Main app does not support BTW merge.[/{BENGARA}]"
            )
            return
        merge_fn(
            transcript=list(self._transcript),
            source_session_id=self._thread_id,
            note=extra_note,
        )
        self.chat_output.write_system(
            "[dim]Merged BTW thread into main context for the next main turn.[/dim]"
        )

    def notify_main_process_started(self, route: str) -> None:
        self._watch(
            f"[dim]MAIN start -> {route}. Watching tools, tasks, and session state.[/dim]"
        )

    def notify_main_process_exited(self, exit_code: int, was_cancelled: bool) -> None:
        state = "cancelled" if was_cancelled else ("ok" if exit_code == 0 else "error")
        color = VERDIGRIS if state == "ok" else (OCHRE if state == "cancelled" else BENGARA)
        self._watch(f"[{color}]MAIN exit -> {state} (code {exit_code})[/{color}]")

    def notify_main_event(self, ev: Any) -> None:
        if isinstance(ev, SessionStart):
            self._watch(
                f"[dim]MAIN session {ev.model} | tools:{len(ev.tools_available)}[/dim]"
            )
        elif isinstance(ev, ToolCallComplete):
            self._watch(
                f"[{OCHRE}]tool start[/{OCHRE}] {ev.tool_name or 'tool'} "
                f"{ev.arguments[:120]}"
            )
        elif isinstance(ev, ToolProgress):
            self._watch(
                f"[dim]tool run {ev.tool_name or 'tool'} {ev.elapsed_seconds:.1f}s[/dim]"
            )
        elif isinstance(ev, ToolResult):
            color = BENGARA if ev.is_error else VERDIGRIS
            label = "err" if ev.is_error else "ok"
            self._watch(f"[{color}]tool {label}[/{color}] {ev.tool_name or 'tool'}")
        elif isinstance(ev, TaskStarted):
            self._watch(f"[{WISTERIA}]agent start[/{WISTERIA}] {ev.description}")
        elif isinstance(ev, TaskProgress):
            self._watch(f"[dim]agent prog {ev.summary}[/dim]")
        elif isinstance(ev, TaskComplete):
            color = VERDIGRIS if ev.success else BENGARA
            state = "ok" if ev.success else "fail"
            self._watch(f"[{color}]agent {state}[/{color}] {ev.summary}")
        elif isinstance(ev, UsageReport):
            if ev.total_cost_usd is not None:
                self._watch(
                    f"[dim]MAIN usage in={ev.input_tokens} out={ev.output_tokens} "
                    f"cost=${ev.total_cost_usd:.4f}[/dim]"
                )
        elif isinstance(ev, SessionEnd):
            color = VERDIGRIS if ev.success else BENGARA
            state = "complete" if ev.success else "failed"
            self._watch(f"[{color}]MAIN {state}[/{color}]")
        elif isinstance(ev, ErrorEvent):
            self._watch(f"[{BENGARA}]MAIN error[/{BENGARA}] {ev.code}: {ev.message}")

    def on_provider_runner_process_started(self, event: ProviderRunner.ProcessStarted) -> None:
        event.stop()
        self._status = "running"
        self._refresh_header()
        self.chat_output.write_system(
            f"[dim]BTW thread starting on {self._route_label()}.[/dim]"
        )

    def on_provider_runner_process_exited(self, event: ProviderRunner.ProcessExited) -> None:
        event.stop()
        if event.was_cancelled:
            self._status = "cancelled"
            self.chat_output.write_system(f"[{OCHRE}]BTW cancelled.[/{OCHRE}]")
        else:
            self._status = "ready" if event.exit_code == 0 else f"error:{event.exit_code}"
            if event.exit_code != 0:
                self.chat_output.write_error(
                    f"[{BENGARA}]BTW process exited with code {event.exit_code}[/{BENGARA}]"
                )
        self._refresh_header()

    def on_provider_runner_agent_event(self, event: ProviderRunner.AgentEvent) -> None:
        event.stop()
        ev = event.event
        self._session.handle_event(ev)

        if isinstance(ev, SessionStart):
            self._status = "connected"
            self._refresh_header()
            self.chat_output.write_system(
                f"[dim]BTW session: {(ev.provider_session_id or ev.session_id)[:12]}... | "
                f"Model: {ev.model} | Tools: {len(ev.tools_available)}[/dim]"
            )

        elif isinstance(ev, TextDelta):
            self.chat_output.handle_text_delta(ev)

        elif isinstance(ev, TextComplete):
            self.chat_output.handle_text_complete(ev)
            if ev.role == "assistant":
                self._transcript.append({"role": "assistant", "content": ev.content})
                self._status = "assistant"
                self._refresh_header()

        elif isinstance(ev, ThinkingDelta):
            self._status = "thinking"
            self._refresh_header()
            self.chat_output.handle_thinking_delta(ev)

        elif isinstance(ev, ThinkingComplete):
            self._status = "reasoned"
            self._refresh_header()
            self.chat_output.handle_thinking_complete(ev)

        elif isinstance(ev, ToolCallComplete):
            self._status = f"tool:{ev.tool_name or 'tool'}"
            self._refresh_header()
            self.chat_output.handle_tool_call_complete(ev)

        elif isinstance(ev, ToolProgress):
            self._status = f"{ev.tool_name or 'tool'} {ev.elapsed_seconds:.1f}s"
            self._refresh_header()
            self.chat_output.handle_tool_progress_canonical(ev)

        elif isinstance(ev, ToolResult):
            self._status = f"{ev.tool_name or 'tool'} {'err' if ev.is_error else 'ok'}"
            self._refresh_header()
            self.chat_output.handle_tool_result_canonical(ev)

        elif isinstance(ev, UsageReport):
            self._cost_usd = ev.total_cost_usd or self._cost_usd
            self._refresh_header()
            self.chat_output.handle_usage_report(ev)

        elif isinstance(ev, SessionEnd):
            self._status = "complete" if ev.success else "failed"
            self._refresh_header()
            if ev.success:
                self.chat_output.write_system("[dim]BTW session complete.[/dim]")
            else:
                self.chat_output.write_error(
                    f"[{BENGARA}]BTW session failed -- "
                    f"{ev.error_code or 'error'}: {ev.error_message or 'unknown'}[/{BENGARA}]"
                )

        elif isinstance(ev, ErrorEvent):
            self._status = f"error:{ev.code or 'provider'}"
            self._refresh_header()
            self.chat_output.write_error(
                f"[{BENGARA}]{ev.code}: {ev.message}[/{BENGARA}]"
            )

    def _watch(self, msg: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.watch_log.write(f"[dim]{timestamp} BTW-WATCH[/dim] {msg}")

    def _route_label(self) -> str:
        app = self.app
        provider = getattr(app, "_active_provider", "codex")
        model = getattr(app, "_active_model", "gpt-5.4")
        return f"{provider}:{model}"

    def _refresh_header(self) -> None:
        status_color = VERDIGRIS
        label = (self._status or "ready").lower()
        if any(term in label for term in ("error", "fail")):
            status_color = BENGARA
        elif "think" in label:
            status_color = WISTERIA
        elif "tool" in label or "run" in label:
            status_color = OCHRE
        header = self.query_one("#btw-header", Static)
        header.update(
            f"[bold {INDIGO}]BTW[/bold {INDIGO}] parallel thread "
            f"[dim]{self._thread_id}[/dim]\n"
            f"Route: [bold]{self._route_label()}[/bold]  |  "
            f"status: [{status_color}]{self._status}[/{status_color}]  |  "
            f"cost: ${self._cost_usd:.4f}  |  "
            "[dim]/merge folds this thread into main context; Esc closes.[/dim]"
        )
