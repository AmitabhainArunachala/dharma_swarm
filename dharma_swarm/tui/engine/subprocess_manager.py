"""Claude Code subprocess manager -- reads NDJSON, posts typed messages."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from textual import work
from textual.message import Message
from textual.widget import Widget
from textual.worker import get_current_worker

from .stream_parser import parse_ndjson_line

DHARMA_SWARM = Path(__file__).resolve().parent.parent.parent.parent


class SubprocessManager(Widget):
    """Manages Claude Code subprocess lifecycle.

    Invisible widget -- no render. Exists solely to own the worker lifecycle
    and post typed messages to the app's message bus.
    """

    DEFAULT_CSS = "SubprocessManager { display: none; }"

    class AgentEvent(Message):
        """Typed event from Claude Code stream."""

        def __init__(self, event: object) -> None:
            super().__init__()
            self.event = event

    class ProcessStarted(Message):
        """Claude Code process has started."""

    class ProcessExited(Message):
        """Claude Code process has exited."""

        def __init__(self, exit_code: int, was_cancelled: bool = False) -> None:
            super().__init__()
            self.exit_code = exit_code
            self.was_cancelled = was_cancelled

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._proc: subprocess.Popen[str] | None = None

    @work(thread=True, exclusive=True, group="claude", exit_on_error=False)
    def run_claude(
        self,
        prompt: str,
        session_id: str | None = None,
        continue_last: bool = False,
        model: str | None = None,
        permission_mode: str = "bypassPermissions",
        max_turns: int | None = None,
        internet_enabled: bool = True,
        system_prompt_append: str | None = None,
    ) -> None:
        """Start Claude Code subprocess and stream NDJSON events.

        Args:
            prompt: The user prompt to send to Claude Code.
            session_id: Resume a specific session by ID.
            continue_last: Continue the most recent session.
            model: Override the default model.
            permission_mode: Permission mode string (default: bypassPermissions).
            max_turns: Maximum number of agentic turns.
            internet_enabled: Whether to allow non-essential network traffic.
            system_prompt_append: Extra text appended to the system prompt.
        """
        worker = get_current_worker()

        cmd = [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
        ]

        if session_id:
            cmd.extend(["--resume", session_id])
        elif continue_last:
            cmd.append("--continue")

        if model:
            cmd.extend(["--model", model])

        if permission_mode:
            cmd.extend(["--permission-mode", permission_mode])
            if permission_mode == "bypassPermissions":
                cmd.extend([
                    "--allowedTools",
                    "*",
                    "--dangerously-skip-permissions",
                ])

        if max_turns:
            cmd.extend(["--max-turns", str(max_turns)])

        if system_prompt_append:
            cmd.extend(["--append-system-prompt", system_prompt_append])

        env = dict(os.environ)
        env.pop("CLAUDECODE", None)
        if not internet_enabled:
            env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        else:
            env.pop("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", None)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,
                text=True,
                cwd=str(DHARMA_SWARM),
                env=env,
            )
            self._proc = proc
            self.post_message(self.ProcessStarted())

            assert proc.stdout is not None  # guaranteed by PIPE
            for raw_line in proc.stdout:
                if worker.is_cancelled:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    self._proc = None
                    self.post_message(
                        self.ProcessExited(proc.returncode or -1, was_cancelled=True)
                    )
                    return

                line = raw_line.strip()
                if not line:
                    continue

                event = parse_ndjson_line(line)
                if event is not None:
                    self.post_message(self.AgentEvent(event))

            proc.wait()
            self._proc = None
            self.post_message(self.ProcessExited(proc.returncode or 0))

        except FileNotFoundError:
            self._proc = None
            self.post_message(self.ProcessExited(-1))
        except Exception:
            if self._proc:
                try:
                    self._proc.kill()
                except ProcessLookupError:
                    pass
                self._proc = None
            self.post_message(self.ProcessExited(-1))

    def cancel(self) -> None:
        """Cancel the running worker (and thus the subprocess)."""
        self.workers.cancel_group(self, "claude")

    @property
    def is_running(self) -> bool:
        """True if the Claude Code subprocess is alive."""
        return self._proc is not None and self._proc.poll() is None
