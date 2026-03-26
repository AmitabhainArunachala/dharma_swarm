"""Remote-side poller for roaming mailbox workers.

Typical flow on a remote host:

1. git fetch/pull the mailbox branch
2. claim the next task for a recipient
3. run a responder command with task context in environment variables
4. write a mailbox response
5. git add/commit/push the mailbox changes
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
import shlex
import subprocess
import time
from typing import Any, Sequence

from dharma_swarm.roaming_mailbox import MailboxResponse, MailboxTask, RoamingMailbox


@dataclass(frozen=True)
class PollerResult:
    task_id: str
    recipient: str
    responder: str
    summary: str
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)


class GitMailboxSync:
    def __init__(self, repo_root: Path, branch: str) -> None:
        self.repo_root = repo_root
        self.branch = branch

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo_root), *args],
            check=True,
            capture_output=True,
            text=True,
        )

    def sync_inbound(self) -> None:
        self._run("fetch", "origin", self.branch)
        self._run("checkout", self.branch)
        self._run("pull", "--ff-only", "origin", self.branch)

    def sync_outbound(self, *, task_id: str, responder: str) -> None:
        status = self._run(
            "status",
            "--short",
            "--",
            "roaming_mailbox/tasks",
            "roaming_mailbox/responses",
            "roaming_mailbox/heartbeats",
        ).stdout.strip()
        if not status:
            return
        self._run(
            "add",
            "roaming_mailbox/tasks",
            "roaming_mailbox/responses",
            "roaming_mailbox/heartbeats",
        )
        self._run("commit", "-m", f"Respond from {responder} for {task_id}")
        self._run("push", "origin", f"HEAD:refs/heads/{self.branch}")


class RoamingPoller:
    def __init__(
        self,
        *,
        mailbox: RoamingMailbox,
        recipient: str,
        responder: str,
        command: Sequence[str],
        git_sync: GitMailboxSync | None = None,
        heartbeat_agent_id: str | None = None,
        heartbeat_interval_seconds: float = 300.0,
    ) -> None:
        self.mailbox = mailbox
        self.recipient = recipient
        self.responder = responder
        self.command = list(command)
        self.git_sync = git_sync
        self.heartbeat_agent_id = heartbeat_agent_id or responder
        self.heartbeat_interval_seconds = max(30.0, float(heartbeat_interval_seconds))
        self._last_heartbeat_at: datetime | None = None

    def _heartbeat_due(self) -> bool:
        if self._last_heartbeat_at is None:
            return True
        age = (datetime.now(timezone.utc) - self._last_heartbeat_at).total_seconds()
        return age >= self.heartbeat_interval_seconds

    def _emit_heartbeat(
        self,
        *,
        status: str,
        summary: str,
        current_task_id: str = "",
        progress: float | None = None,
        force: bool = False,
    ) -> None:
        if not force and not self._heartbeat_due():
            return
        self.mailbox.write_heartbeat(
            agent_id=self.heartbeat_agent_id,
            callsign=self.responder,
            status=status,
            summary=summary,
            current_task_id=current_task_id,
            progress=progress,
            metadata={
                "recipient": self.recipient,
                "responder": self.responder,
                "mode": "roaming_poller",
            },
        )
        self._last_heartbeat_at = datetime.now(timezone.utc)

    def _env_for_task(self, task: MailboxTask) -> dict[str, str]:
        env = dict(os.environ)
        env.update(
            {
                "ROAMING_TASK_ID": task.task_id,
                "ROAMING_TASK_PATH": str(self.mailbox.task_path(task.task_id)),
                "ROAMING_TASK_JSON": json.dumps(task.to_dict(), ensure_ascii=True),
                "ROAMING_TASK_SUMMARY": task.summary,
                "ROAMING_TASK_BODY": task.body,
                "ROAMING_RECIPIENT": self.recipient,
                "ROAMING_RESPONDER": self.responder,
                "ROAMING_MAILBOX_ROOT": str(self.mailbox.queue_root),
            }
        )
        return env

    @staticmethod
    def _parse_stdout(stdout: str, *, task: MailboxTask) -> tuple[str, str, dict[str, Any]]:
        text = stdout.strip()
        if not text:
            return (f"Handled {task.task_id}", "{}", {})
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return (f"Handled {task.task_id}", text, {})
        if isinstance(data, dict):
            summary = str(data.get("summary", f"Handled {task.task_id}"))
            body = str(data.get("body", ""))
            metadata = dict(data.get("metadata") or {})
            return (summary, body, metadata)
        return (f"Handled {task.task_id}", text, {})

    def process_once(self) -> PollerResult | None:
        if self.git_sync is not None:
            self.git_sync.sync_inbound()

        task = self.mailbox.claim_next_task(self.recipient)
        if task is None:
            self._emit_heartbeat(status="idle", summary="Polling for work")
            if self.git_sync is not None and self._last_heartbeat_at is not None:
                self.git_sync.sync_outbound(task_id="heartbeat", responder=self.responder)
            return None

        self._emit_heartbeat(
            status="working",
            summary=task.summary,
            current_task_id=task.task_id,
            progress=0.05,
            force=True,
        )

        proc = subprocess.run(
            self.command,
            check=False,
            capture_output=True,
            text=True,
            env=self._env_for_task(task),
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Responder command failed for {task.task_id}: {proc.stderr.strip() or proc.stdout.strip()}"
            )

        summary, body, metadata = self._parse_stdout(proc.stdout, task=task)
        response = self.mailbox.respond_to_task(
            task_id=task.task_id,
            responder=self.responder,
            summary=summary,
            body=body,
            metadata=metadata,
        )

        self._emit_heartbeat(
            status="idle",
            summary=f"Completed {task.task_id}",
            current_task_id="",
            progress=1.0,
            force=True,
        )

        if self.git_sync is not None:
            self.git_sync.sync_outbound(task_id=task.task_id, responder=self.responder)

        return PollerResult(
            task_id=task.task_id,
            recipient=self.recipient,
            responder=self.responder,
            summary=response.summary,
            body=response.body,
            metadata=response.metadata,
        )

    def run_loop(self, *, interval_seconds: float = 5.0) -> None:
        while True:
            try:
                self.process_once()
            except Exception:
                # Keep the remote worker alive; failures are surfaced by exit logs.
                pass
            time.sleep(interval_seconds)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a roaming mailbox poller.")
    parser.add_argument("--queue-root", default="")
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--responder", required=True)
    parser.add_argument("--command", required=True, help="Responder command string.")
    parser.add_argument("--repo-root", default="")
    parser.add_argument("--git-branch", default="")
    parser.add_argument("--heartbeat-agent-id", default="")
    parser.add_argument("--heartbeat-seconds", type=float, default=300.0)

    sub = parser.add_subparsers(dest="mode", required=True)
    once = sub.add_parser("run-once")
    once.add_argument("--json", action="store_true")
    loop = sub.add_parser("run-loop")
    loop.add_argument("--interval", type=float, default=5.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    mailbox = RoamingMailbox(queue_root=Path(args.queue_root) if args.queue_root else None)
    git_sync = None
    if args.repo_root and args.git_branch:
        git_sync = GitMailboxSync(Path(args.repo_root), args.git_branch)
    poller = RoamingPoller(
        mailbox=mailbox,
        recipient=args.recipient,
        responder=args.responder,
        command=shlex.split(args.command),
        git_sync=git_sync,
        heartbeat_agent_id=args.heartbeat_agent_id or args.responder,
        heartbeat_interval_seconds=args.heartbeat_seconds,
    )

    if args.mode == "run-once":
        result = poller.process_once()
        if args.json:
            print(json.dumps(None if result is None else result.__dict__, indent=2, ensure_ascii=True))
        elif result is not None:
            print(result.summary)
        return 0

    if args.mode == "run-loop":
        poller.run_loop(interval_seconds=args.interval)
        return 0

    parser.error("unknown mode")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
