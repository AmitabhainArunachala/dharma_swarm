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

import json
import os
import secrets
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding

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
from .engine.session_state import SessionState
from .screens.main import MainScreen
from .screens.splash import SplashScreen
from .widgets.prompt_input import PromptInput
from .widgets.stream_output import StreamOutput
from .widgets.status_bar import StatusBar
from .commands.palette import DGCCommandProvider
from .commands.system_commands import SystemCommandHandler

HOME = Path.home()
DHARMA_SWARM = Path(__file__).resolve().parent.parent.parent
DHARMA_STATE = HOME / ".dharma"

_MODE_NAMES: dict[str, str] = {
    "N": "normal",
    "A": "auto",
    "P": "plan",
    "S": "sage",
}
_MODE_KEYS = list(_MODE_NAMES.keys())


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
        Binding("ctrl+c", "cancel_run", "Cancel", show=True),
        Binding("ctrl+d", "quit", "Exit", show=True),
        Binding("ctrl+l", "clear_output", "Clear", show=True),
        Binding("ctrl+o", "cycle_mode", "Mode", show=True),
        Binding("ctrl+n", "new_session", "New Session", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._session = SessionState()
        self._commands = SystemCommandHandler()
        self._mode: str = "N"
        self._provider_runner: ProviderRunner | None = None
        self._provider_session_id: str | None = None
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
        # Push main screen first (it becomes the base), then splash on top
        self.push_screen(MainScreen(), callback=self._on_main_ready)
        self.push_screen(SplashScreen())

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
            main.stream_output.write_system(
                "[bold cyan]DGC[/bold cyan] -- Talk to Claude or type /help "
                "for system commands\n"
            )
            self._run_status_on_startup()

    # ─── Screen Access ───────────────────────────────────────────────

    def _get_main_screen(self) -> MainScreen | None:
        """Find the MainScreen in the screen stack."""
        for screen in self.screen_stack:
            if isinstance(screen, MainScreen):
                return screen
        return None

    # ─── Event Routing: ProviderRunner -> Widgets ────────────────────

    def on_provider_runner_agent_event(
        self, event: ProviderRunner.AgentEvent
    ) -> None:
        """Route canonical provider events to display widgets."""
        ev = event.event
        self._session.handle_event(ev)

        main = self._get_main_screen()
        if not main:
            return

        output: StreamOutput = main.stream_output  # type: ignore[assignment]
        status: StatusBar = main.status_bar  # type: ignore[assignment]

        if isinstance(ev, SessionStart):
            status.model = ev.model
            status.session_name = (
                (ev.provider_session_id or ev.session_id)[:8]
                if (ev.provider_session_id or ev.session_id)
                else "dgc"
            )
            status.is_running = True
            if ev.provider_session_id:
                self._provider_session_id = ev.provider_session_id
            output.write_system(
                f"[dim]Session: {(ev.provider_session_id or ev.session_id)[:12]}... | "
                f"Model: {ev.model} | Tools: {len(ev.tools_available)}[/dim]"
            )

        elif isinstance(ev, TextDelta):
            output.handle_text_delta(ev)

        elif isinstance(ev, TextComplete):
            output.handle_text_complete(ev)
            if ev.role == "assistant":
                status.turn_count = self._session.turn_count

        elif isinstance(ev, ThinkingDelta):
            output.handle_thinking_delta(ev)

        elif isinstance(ev, ThinkingComplete):
            output.handle_thinking_complete(ev)

        elif isinstance(ev, ToolCallComplete):
            output.handle_tool_call_complete(ev)

        elif isinstance(ev, ToolProgress):
            output.handle_tool_progress_canonical(ev)

        elif isinstance(ev, ToolResult):
            output.handle_tool_result_canonical(ev)

        elif isinstance(ev, UsageReport):
            output.handle_usage_report(ev)
            if ev.total_cost_usd is not None:
                status.cost_usd = ev.total_cost_usd

        elif isinstance(ev, SessionEnd):
            status.is_running = False
            if ev.success:
                output.write_system("[dim]\u2713 Session complete.[/dim]")
            else:
                detail = f"{ev.error_code}: {ev.error_message}" if ev.error_code else (
                    ev.error_message or "unknown provider failure"
                )
                output.write_error(f"[red]\u2717 Session failed -- {detail}[/red]")

        elif isinstance(ev, TaskStarted):
            output.write_system(
                f"[dim]Subagent started: {ev.description}[/dim]"
            )

        elif isinstance(ev, TaskProgress):
            output.write_system(f"[dim]Subagent progress: {ev.summary}[/dim]")

        elif isinstance(ev, TaskComplete):
            state = "ok" if ev.success else "error"
            output.write_system(
                f"[dim]Subagent complete ({state}): {ev.summary}[/dim]"
            )

        elif isinstance(ev, RateLimitEvent):
            msg = f"Rate limit: {ev.status}"
            if ev.utilization is not None:
                msg += f" ({ev.utilization * 100:.0f}%)"
            output.write_system(f"[yellow]{msg}[/yellow]")

        elif isinstance(ev, ErrorEvent):
            output.write_error(f"[red]{ev.code}: {ev.message}[/red]")

    def on_provider_runner_process_started(
        self, event: ProviderRunner.ProcessStarted
    ) -> None:
        """Update status bar when provider stream starts."""
        main = self._get_main_screen()
        if main:
            main.status_bar.is_running = True  # type: ignore[union-attr]

    def on_provider_runner_process_exited(
        self, event: ProviderRunner.ProcessExited
    ) -> None:
        """Update status bar and show exit info when provider run finishes."""
        main = self._get_main_screen()
        if not main:
            return

        main.status_bar.is_running = False  # type: ignore[union-attr]
        output: StreamOutput = main.stream_output  # type: ignore[assignment]

        if event.was_cancelled:
            output.write_system("[yellow]Cancelled.[/yellow]")
        elif event.exit_code != 0:
            output.write_error(
                f"[red]Process exited with code {event.exit_code}[/red]"
            )

    # ─── Input Handling ──────────────────────────────────────────────

    def on_prompt_input_submitted(self, event: PromptInput.Submitted) -> None:
        """Handle user input -- route to command handler or Claude."""
        text = event.text.strip()
        if not text:
            return

        main = self._get_main_screen()
        if not main:
            return

        output: StreamOutput = main.stream_output  # type: ignore[assignment]

        if text.startswith("/"):
            cmd_text = text[1:]
            output.write_system(f"[dim]/{cmd_text}[/dim]")
            out_text, action = self._commands.handle(cmd_text)

            if out_text:
                output.write(out_text)

            if action:
                self._handle_action(action, cmd_text)
        else:
            output.write_user(text)
            self._send_to_claude(text)

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
                output.write_system("[yellow]Cancel signal sent.[/yellow]")
            else:
                output.write_system("[dim]No active Claude run.[/dim]")

        elif action == "chat:new":
            self._launch_chat_shell(continue_last=False)

        elif action == "chat:continue":
            self._launch_chat_shell(continue_last=True)

        elif action == "paste":
            self._paste_clipboard()

        elif action in {"copy", "copylast"}:
            self._copy_last_reply()

        elif action.startswith("async:"):
            parts = action.split(":", 2)
            cmd = parts[1] if len(parts) > 1 else ""
            arg = parts[2] if len(parts) > 2 else ""
            self._run_async_command(cmd, arg)

    # ─── Claude Chat ─────────────────────────────────────────────────

    def _send_to_claude(self, text: str) -> None:
        """Send user prompt through provider-agnostic runner."""
        if not self._provider_runner:
            return

        if self._provider_runner.is_running:
            main = self._get_main_screen()
            if main:
                main.stream_output.write_error(  # type: ignore[union-attr]
                    "[yellow]Claude is already running. Use /cancel first.[/yellow]"
                )
            return

        local_session_id = self._ensure_local_session_id()

        # Build state context for system prompt injection
        state_ctx = self._get_state_context()
        system_append: str | None = None
        if state_ctx:
            system_append = (
                "DGC mission-control context snapshot. "
                "Treat as hints and verify.\n\n" + state_ctx[:6000]
            )

        request = CompletionRequest(
            messages=[{"role": "user", "content": text}],
            system_prompt=system_append,
            resume_session_id=self._provider_session_id,
            enable_thinking=True,
            provider_options={
                "internet_enabled": self._commands.internet_enabled,
                "permission_mode": "bypassPermissions",
            },
        )
        self._provider_runner.run_provider(
            request,
            session_id=local_session_id,
            provider_id="claude",
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
            from dharma_swarm.context import read_memory_context

            mem = read_memory_context()
            if mem and "No memory" not in mem:
                parts.append(f"Recent memory:\n{mem}")
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
                    f"[red]/chat failed: {exc}[/red]"
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
            out(f"[red]Command error: {exc}[/red]")

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
            out("[green]Pulse done.[/green]")

        elif cmd == "health":
            out("[dim]Checking health...[/dim]")
            from dharma_swarm.ecosystem_bridge import scan_ecosystem

            eco = scan_ecosystem()
            ok = sum(1 for v in eco.values() if v.get("exists"))
            missing = sum(1 for v in eco.values() if not v.get("exists"))
            out(f"  [green]{ok} OK[/green]  [red]{missing} missing[/red]")
            for name, info in eco.items():
                if not info.get("exists"):
                    out(f"  [red]MISSING[/red] {name} -- {info.get('path', '?')}")

        elif cmd == "memory":
            out("[dim]Loading memory...[/dim]")
            from dharma_swarm.context import read_memory_context

            ctx = read_memory_context()
            for line in ctx.split("\n")[:30]:
                out(f"  {line}")

        elif cmd == "witness":
            if not arg:
                out("[red]Usage: /witness <observation>[/red]")
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
                out(f"  [green]Witnessed[/green] -> {log_file.name}")

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
                out("[red]Usage: /agni <command>[/red]")
            else:
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
                    out(f"  [red]{proc.stderr.strip()[:200]}[/red]")

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
            if not arg or len(arg.split(None, 1)) < 2:
                out("[red]Usage: /evolve <component> <description>[/red]")
            else:
                parts = arg.split(None, 1)
                out(f"[dim]Evolving {parts[0]}...[/dim]")
                try:
                    import asyncio

                    from dharma_swarm.swarm import SwarmManager

                    mgr = SwarmManager()
                    result = asyncio.run(mgr.evolve(parts[0], parts[1]))
                    out(f"  [green]Evolution result: {result}[/green]")
                except Exception as exc:
                    out(f"  [red]Evolution failed: {exc}[/red]")

        elif cmd == "archive":
            out("[dim]Loading archive...[/dim]")
            archive_path = DHARMA_STATE / "evolution" / "archive.jsonl"
            if archive_path.exists():
                entries: list[dict[str, Any]] = []
                for line in archive_path.read_text().strip().split("\n")[-10:]:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
                for entry in entries:
                    out(
                        f"  {entry.get('id', '?')[:12]}  "
                        f"fitness={entry.get('fitness', '?')}  "
                        f"{entry.get('component', '?')}"
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
                out(f"  [red]Context failed: {exc}[/red]")

        elif cmd == "runtime":
            out("[dim]Runtime matrix...[/dim]")
            import shutil

            for prog in ["claude", "python3", "node"]:
                path = shutil.which(prog)
                out(f"  {prog}: {path or 'not found'}")

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
                    out(f"  [red]Dharma kernel: {exc}[/red]")
            elif subcmd == "corpus":
                self._dispatch_async("corpus", "", out)
            else:
                out("[red]Usage: /dharma [status|corpus][/red]")

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
                out(f"  [red]Corpus: {exc}[/red]")

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
                out(f"  [red]Stigmergy: {exc}[/red]")

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
                out(f"  [red]HUM: {exc}[/red]")

        else:
            out(f"[red]Unknown async command: {cmd}[/red]")

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

    def action_clear_output(self) -> None:
        """Clear the stream output widget."""
        main = self._get_main_screen()
        if main:
            main.stream_output.clear()

    def action_cycle_mode(self) -> None:
        """Cycle through N -> A -> P -> S operating modes."""
        idx = _MODE_KEYS.index(self._mode) if self._mode in _MODE_KEYS else 0
        self._mode = _MODE_KEYS[(idx + 1) % len(_MODE_KEYS)]

        main = self._get_main_screen()
        if main:
            main.status_bar.mode = self._mode  # type: ignore[union-attr]
            # Update CSS classes for mode-specific styling
            for key, name in _MODE_NAMES.items():
                self.remove_class(f"mode-{name}")
            self.add_class(f"mode-{_MODE_NAMES[self._mode]}")

    def action_new_session(self) -> None:
        """Reset session state and clear the output."""
        self._session = SessionState()
        self._provider_session_id = None
        main = self._get_main_screen()
        if main:
            main.stream_output.clear()
            main.stream_output.write_system(  # type: ignore[union-attr]
                "[dim]New session started.[/dim]"
            )
            status: StatusBar = main.status_bar  # type: ignore[assignment]
            status.session_name = ""
            status.cost_usd = 0.0
            status.turn_count = 0

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
        """Hint user on how to copy text from the TUI."""
        main = self._get_main_screen()
        if main:
            main.stream_output.write_system(  # type: ignore[union-attr]
                "[dim]To copy text: hold [bold]Shift[/bold] and drag-select "
                "with mouse, then Cmd+C.\n"
                "  (Shift bypasses Textual's mouse capture for native "
                "terminal selection.)[/dim]"
            )
