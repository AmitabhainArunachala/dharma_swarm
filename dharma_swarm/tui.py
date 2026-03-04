"""DGC Terminal UI — chat-first interface to the dharmic swarm.

Plain text talks to Claude. /commands for system operations.

Usage:
    dgc              (launch TUI)
    dgc --tui        (explicit TUI mode)
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import (
    Footer,
    Header,
    Input,
    RichLog,
    Static,
)

HOME = Path.home()
DHARMA_STATE = HOME / ".dharma"
DGC_CORE = HOME / "dgc-core"
DHARMA_SWARM = HOME / "dharma_swarm"


# ─── Helper functions ───────────────────────────────────────────────


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except Exception:
        return {}


def _file_age_str(path: Path) -> str:
    if not path.exists():
        return "n/a"
    age = time.time() - path.stat().st_mtime
    if age < 60:
        return f"{age:.0f}s ago"
    if age < 3600:
        return f"{age / 60:.0f}m ago"
    if age < 86400:
        return f"{age / 3600:.1f}h ago"
    return f"{age / 86400:.0f}d ago"


def _count_files(path: Path, pattern: str = "*") -> int:
    try:
        return len(list(path.glob(pattern))) if path.exists() else 0
    except Exception:
        return 0


def _get_memory_stats() -> dict[str, Any]:
    try:
        import sys
        sys.path.insert(0, str(DGC_CORE / "memory"))
        from strange_loop import StrangeLoopMemory
        mem = StrangeLoopMemory(str(DGC_CORE / "memory"))
        return mem.stats()
    except Exception as e:
        return {"error": str(e)}


def _get_gate_count_today() -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    gate_log = DGC_CORE / "memory" / "witness" / f"{today}.jsonl"
    if not gate_log.exists():
        return 0
    try:
        return sum(1 for _ in open(gate_log))
    except Exception:
        return 0


def _claude_version() -> str:
    try:
        r = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip() or "unknown"
    except Exception:
        return "not found"


def _build_status_text() -> str:
    lines = []

    ds = _read_json(DGC_CORE / "daemon" / "state.json")
    lines.append(f"[bold cyan]PULSE[/bold cyan]  count={ds.get('pulse_count', 0)}  last={ds.get('last_pulse', 'never')}  circuit={ds.get('circuit_breaker', 'ok')}")

    ms = _get_memory_stats()
    if "error" not in ms:
        lines.append(f"[bold green]MEMORY[/bold green]  sessions={ms.get('sessions', 0)}  developments={ms.get('developments', 0)}  witness={ms.get('witness_days', 0)}d  buffer={ms.get('immediate_buffer', 0)}")
    else:
        lines.append(f"[bold red]MEMORY[/bold red]  {ms['error']}")

    lines.append(f"[bold yellow]GATES[/bold yellow]  {_get_gate_count_today()} checks today")

    agni = HOME / "agni-workspace"
    if agni.exists():
        lines.append(f"[bold magenta]AGNI[/bold magenta]   synced  WORKING.md={_file_age_str(agni / 'WORKING.md')}")
    else:
        lines.append("[bold red]AGNI[/bold red]   NOT SYNCED")

    t_inbox = HOME / "trishula" / "inbox"
    t_count = _count_files(t_inbox, "*.json") + _count_files(t_inbox, "*.md")
    lines.append(f"[bold cyan]TRISHULA[/bold cyan]  {t_count} messages")

    lines.append(f"[bold white]CLAUDE[/bold white]  {_claude_version()}")

    shared = DHARMA_STATE / "shared"
    lines.append(f"[bold green]SHARED[/bold green]  {_count_files(shared, '*.md')} notes")

    mf = _read_json(HOME / ".dharma_manifest.json")
    if mf:
        eco = mf.get("ecosystem", {})
        lines.append(f"[bold yellow]ECOSYSTEM[/bold yellow]  {len(eco)} components mapped")

    return "\n".join(lines)


def _build_context_preview(role: str = "general", thread: str | None = None) -> str:
    try:
        from dharma_swarm.context import build_agent_context
        ctx = build_agent_context(role=role, thread=thread)
        headers = [l for l in ctx.split("\n") if l.startswith("# ") or l.startswith("## ")]
        summary = f"[bold]Context for role={role}[/bold]  [dim]{len(ctx):,} chars[/dim]\n"
        summary += "\n".join(f"  [green]{h}[/green]" for h in headers)
        return summary
    except Exception as e:
        return f"[red]Context error: {e}[/red]"


# ─── Splash Screen ──────────────────────────────────────────────────


class SplashScreen(Screen):
    BINDINGS = [
        Binding("enter", "dismiss_splash", "Enter DGC"),
        Binding("escape", "dismiss_splash", "Enter DGC"),
        Binding("q", "quit", "Quit"),
        Binding("any", "dismiss_splash", show=False),
    ]

    def compose(self) -> ComposeResult:
        from dharma_swarm.splash import get_splash
        yield Static(get_splash(compact=False), id="splash-art", markup=False)
        prompt = Text.from_markup(
            "\n[bold bright_white]  Press any key to enter  |  "
            "[bright_cyan]q[/bright_cyan] to quit[/bold bright_white]"
        )
        yield Static(prompt, id="splash-prompt", markup=False)

    def on_key(self, event) -> None:
        if event.key == "q":
            self.app.exit()
        else:
            self.app.pop_screen()

    def action_dismiss_splash(self) -> None:
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit()


# ─── Main App ────────────────────────────────────────────────────────


class DGCApp(App):
    TITLE = "DGC — Dharmic Godel Claw"
    CSS = """
    Screen {
        background: $surface;
    }

    #splash-art {
        width: 100%;
        content-align: center middle;
        text-align: center;
        padding: 1;
    }

    #splash-prompt {
        dock: bottom;
        height: 3;
        content-align: center middle;
        text-align: center;
        background: $primary-background;
    }

    #chat-log {
        height: 1fr;
        padding: 0 1;
    }

    #cmd-input {
        dock: bottom;
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+l", "clear_log", "Clear"),
        Binding("ctrl+s", "show_splash", "Splash"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="chat-log", highlight=True, markup=True, wrap=True)
        yield Input(placeholder="Talk to Claude, or /help for commands", id="cmd-input")
        yield Footer()

    def on_mount(self) -> None:
        self.push_screen(SplashScreen())
        # Auto-focus input when dashboard loads
        self.set_timer(0.1, self._focus_input)
        # Show welcome
        self._out("[bold cyan]DGC[/bold cyan] [dim]— Talk to Claude or type /help for system commands[/dim]\n")
        self._out(_build_status_text())
        self._out("")

    def _focus_input(self) -> None:
        try:
            self.query_one("#cmd-input", Input).focus()
        except Exception:
            pass

    def _out(self, msg: str) -> None:
        try:
            self.query_one("#chat-log", RichLog).write(msg)
        except Exception:
            pass

    def _out_thread(self, msg: str) -> None:
        self.call_from_thread(self._out, msg)

    # ─── Input handler ───

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        event.input.value = ""
        if not raw:
            return

        # /commands
        if raw.startswith("/"):
            self._handle_command(raw[1:])
            return

        # Everything else → ask Claude
        self._out(f"\n[bold bright_white]you:[/bold bright_white] {raw}")
        self._run_ask(raw)

    def _handle_command(self, raw: str) -> None:
        parts = raw.split(None, 1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1] if len(parts) > 1 else ""

        self._out(f"\n[dim]/{cmd} {arg}[/dim]")

        if cmd == "help":
            self._out(
                "[bold cyan]Commands:[/bold cyan]\n"
                "  [cyan]/status[/cyan]          System status\n"
                "  [cyan]/pulse[/cyan]           Run heartbeat\n"
                "  [cyan]/health[/cyan]          Ecosystem health check\n"
                "  [cyan]/gates[/cyan] <action>  Test telos gates\n"
                "  [cyan]/memory[/cyan]          Strange loop memory\n"
                "  [cyan]/witness[/cyan] <msg>   Record observation\n"
                "  [cyan]/context[/cyan] [role]  Show agent context\n"
                "  [cyan]/agni[/cyan] <cmd>      Run on AGNI VPS\n"
                "  [cyan]/swarm[/cyan]           Orchestrator state\n"
                "  [cyan]/notes[/cyan]           Shared agent notes\n"
                "  [cyan]/trishula[/cyan]        Trishula inbox\n"
                "  [cyan]/clear[/cyan]           Clear screen\n"
                "  [cyan]/help[/cyan]            This help\n\n"
                "[dim]Plain text (no /) talks to Claude.[/dim]"
            )

        elif cmd == "clear":
            try:
                self.query_one("#chat-log", RichLog).clear()
            except Exception:
                pass

        elif cmd == "status":
            self._out(_build_status_text())

        elif cmd == "pulse":
            self._run_pulse()

        elif cmd == "health":
            self._run_health()

        elif cmd == "gates":
            self._run_gates(arg or "echo test")

        elif cmd == "memory":
            self._run_memory()

        elif cmd == "witness":
            if not arg:
                self._out("[red]Usage: /witness <observation>[/red]")
            else:
                self._run_witness(arg)

        elif cmd == "context":
            self._out(_build_context_preview(role=arg or "general"))

        elif cmd == "agni":
            if not arg:
                self._out("[red]Usage: /agni <command>[/red]")
            else:
                self._run_agni(arg)

        elif cmd == "swarm":
            orch = _read_json(DHARMA_STATE / "orchestrator_state.json")
            if orch:
                for k, v in orch.items():
                    self._out(f"  {k}: {v}")
            else:
                self._out("[dim]No orchestrator state. Run 'dgc swarm' from terminal.[/dim]")

        elif cmd == "notes":
            shared = DHARMA_STATE / "shared"
            if not shared.exists():
                self._out("[dim]No agent notes.[/dim]")
            else:
                for f in sorted(shared.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
                    try:
                        content = f.read_text()[:300]
                        self._out(f"[bold cyan]{f.name}[/bold cyan]  [dim]{_file_age_str(f)}[/dim]")
                        for line in content.split("\n")[:3]:
                            self._out(f"  {line}")
                    except Exception:
                        pass

        elif cmd == "trishula":
            inbox = HOME / "trishula" / "inbox"
            msgs = []
            if inbox.exists():
                for f in sorted(inbox.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
                    try:
                        self._out(f"[bold magenta]{f.name}[/bold magenta]")
                        for line in f.read_text()[:200].split("\n")[:3]:
                            self._out(f"  {line}")
                    except Exception:
                        pass
            if not msgs:
                self._out("[dim]Showing latest 5 messages.[/dim]")

        else:
            self._out(f"[red]Unknown command: /{cmd}[/red]  (try /help)")

    # ─── Claude conversation ───

    @work(thread=True)
    def _run_ask(self, question: str) -> None:
        self._out_thread("[dim]thinking...[/dim]")
        try:
            env = {**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
            env.pop("CLAUDECODE", None)
            proc = subprocess.run(
                ["claude", "-p", question, "--output-format", "text"],
                capture_output=True, text=True, timeout=180,
                cwd=str(DHARMA_SWARM),
                env=env,
            )
            output = proc.stdout.strip()
            if output:
                self._out_thread(f"\n[bold cyan]claude:[/bold cyan]")
                for line in output.split("\n"):
                    self._out_thread(f"  {line}")
                self._out_thread("")
            else:
                err = proc.stderr.strip()[:300]
                self._out_thread(f"[red]No response. {err}[/red]")
        except subprocess.TimeoutExpired:
            self._out_thread("[red]Timed out (180s).[/red]")
        except FileNotFoundError:
            self._out_thread("[red]claude CLI not found.[/red]")
        except Exception as e:
            self._out_thread(f"[red]Error: {e}[/red]")

    # ─── System commands (threaded) ───

    @work(thread=True)
    def _run_pulse(self) -> None:
        self._out_thread("[dim]Running pulse...[/dim]")
        try:
            import sys
            sys.path.insert(0, str(DHARMA_SWARM))
            from dharma_swarm.pulse import pulse
            result = str(pulse())[:2000]
            for line in result.split("\n"):
                self._out_thread(f"  {line}")
            self._out_thread("[green]Pulse done.[/green]")
        except Exception as e:
            self._out_thread(f"[red]Pulse failed: {e}[/red]")

    @work(thread=True)
    def _run_health(self) -> None:
        self._out_thread("[dim]Checking health...[/dim]")
        try:
            import sys
            sys.path.insert(0, str(DGC_CORE / "context"))
            from ecosystem_map import check_health
            h = check_health()
            self._out_thread(f"  [green]{h['ok']} OK[/green]  [red]{h['missing']} missing[/red]")
            if h.get("details"):
                for p, d in h["details"].items():
                    self._out_thread(f"  [red]MISSING[/red] {p} -- {d}")
        except Exception as e:
            self._out_thread(f"[red]Health failed: {e}[/red]")

    @work(thread=True)
    def _run_gates(self, action: str) -> None:
        self._out_thread(f"[dim]Testing gates: {action}[/dim]")
        try:
            import sys
            sys.path.insert(0, str(DGC_CORE / "hooks"))
            from telos_gate import check_gates
            result = check_gates("Bash", {"command": action})
            d = result["decision"]
            color = "green" if d == "allow" else "red"
            self._out_thread(f"  [{color}]{d}[/{color}]: {result['reason']}")
        except Exception as e:
            self._out_thread(f"[red]Gates failed: {e}[/red]")

    @work(thread=True)
    def _run_memory(self) -> None:
        self._out_thread("[dim]Loading memory...[/dim]")
        try:
            import sys
            sys.path.insert(0, str(DGC_CORE / "memory"))
            from strange_loop import StrangeLoopMemory
            mem = StrangeLoopMemory(str(DGC_CORE / "memory"))
            ctx = mem.get_context()
            for line in ctx.split("\n")[:30]:
                self._out_thread(f"  {line}")
        except Exception as e:
            self._out_thread(f"[red]Memory failed: {e}[/red]")

    @work(thread=True)
    def _run_witness(self, msg: str) -> None:
        try:
            import sys
            sys.path.insert(0, str(DGC_CORE / "memory"))
            from strange_loop import StrangeLoopMemory
            mem = StrangeLoopMemory(str(DGC_CORE / "memory"))
            entry = mem.witness(msg)
            self._out_thread(f"  [green]Witnessed[/green] quality={entry.witness_quality:.2f}")
        except Exception as e:
            self._out_thread(f"[red]Witness failed: {e}[/red]")

    @work(thread=True)
    def _run_agni(self, command: str) -> None:
        self._out_thread(f"[dim]AGNI: {command}[/dim]")
        try:
            ssh_key = HOME / ".ssh" / "openclaw_do"
            proc = subprocess.run(
                ["ssh", "-i", str(ssh_key), "-o", "ConnectTimeout=10",
                 "root@157.245.193.15", command],
                capture_output=True, text=True, timeout=30,
            )
            if proc.stdout:
                for line in proc.stdout.split("\n")[:30]:
                    self._out_thread(f"  {line}")
            if proc.stderr:
                self._out_thread(f"  [red]{proc.stderr.strip()[:200]}[/red]")
        except subprocess.TimeoutExpired:
            self._out_thread("[red]AGNI timed out.[/red]")
        except Exception as e:
            self._out_thread(f"[red]AGNI failed: {e}[/red]")

    # ─── Actions ───

    def action_clear_log(self) -> None:
        try:
            self.query_one("#chat-log", RichLog).clear()
        except Exception:
            pass

    def action_show_splash(self) -> None:
        self.push_screen(SplashScreen())

    def action_quit(self) -> None:
        self.exit()


# ─── Entry point ─────────────────────────────────────────────────────


def run_tui() -> None:
    app = DGCApp()
    app.run()


if __name__ == "__main__":
    run_tui()
