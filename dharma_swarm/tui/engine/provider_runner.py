"""Provider runner widget: adapter stream -> governance -> session store -> UI."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Any

from textual import work
from textual.message import Message
from textual.widget import Widget
from textual.worker import get_current_worker

from .adapters import ClaudeAdapter, CompletionRequest
from .events import CanonicalEventType, ErrorEvent
from .governance import GovernanceFilter, GovernancePolicy
from .session_store import SessionStore

HOME = Path.home()
DEFAULT_CWD = HOME / "dharma_swarm"


class ProviderRunner(Widget):
    """Headless worker widget to execute provider streams."""

    DEFAULT_CSS = "ProviderRunner { display: none; }"

    class AgentEvent(Message):
        def __init__(self, event: CanonicalEventType) -> None:
            super().__init__()
            self.event = event

    class ProcessStarted(Message):
        pass

    class ProcessExited(Message):
        def __init__(self, exit_code: int, was_cancelled: bool = False) -> None:
            super().__init__()
            self.exit_code = exit_code
            self.was_cancelled = was_cancelled

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._adapter = ClaudeAdapter(workdir=DEFAULT_CWD)
        self._active_task = False
        self._cancel_requested = False
        self._store = SessionStore()

    def _ensure_session(
        self,
        *,
        session_id: str,
        provider_id: str,
        model_id: str,
    ) -> None:
        """Create session metadata if this is the first event for session_id."""
        session_dir = self._store.root / session_id
        if (session_dir / "meta.json").exists():
            return
        self._store.create_session(
            session_id=session_id,
            provider_id=provider_id,
            model_id=model_id,
            cwd=str(DEFAULT_CWD),
        )

    @property
    def is_running(self) -> bool:
        return self._active_task

    def mark_session_end(self) -> None:
        """Release UI lock once semantic session end is observed.

        Claude can emit a logical SessionEnd event before the subprocess fully
        exits. Unlocking here prevents the UI from appearing stuck in a
        completed-but-still-finalizing state.
        """
        self._active_task = False

    @work(thread=True, exclusive=True, group="provider", exit_on_error=False)
    def run_provider(
        self,
        request: CompletionRequest,
        *,
        session_id: str,
        provider_id: str = "claude",
    ) -> None:
        """Execute one provider stream round and emit canonical events."""
        if provider_id != "claude":
            self.post_message(
                self.AgentEvent(
                    ErrorEvent(
                        provider_id=provider_id,
                        session_id=session_id,
                        code="provider_not_implemented",
                        message=f"Provider '{provider_id}' is not wired yet",
                    )
                )
            )
            self.post_message(self.ProcessExited(-1))
            return

        worker = get_current_worker()
        profile = self._adapter.get_profile(request.model)
        self._ensure_session(
            session_id=session_id,
            provider_id=provider_id,
            model_id=profile.model_id,
        )
        self._active_task = True
        self._cancel_requested = False
        self.post_message(self.ProcessStarted())

        governance = GovernanceFilter(
            policy=GovernancePolicy(),
            session_id=session_id,
            audit_writer=lambda entry: self._store.append_audit(session_id, entry),
        )

        stats: dict[str, Any] = {
            "cost": 0.0,
            "turns": 0,
            "in_tokens": 0,
            "out_tokens": 0,
            "provider_session_id": None,
            "success": None,
            "error_code": None,
        }

        try:
            async def _run() -> None:
                async for event in self._adapter.stream(request, session_id=session_id):
                    if worker.is_cancelled:
                        await self._adapter.cancel()
                        break

                    try:
                        filtered = governance.process(event)
                        if filtered is None:
                            continue

                        if filtered.type == "session_start":
                            provider_session_id = getattr(
                                filtered, "provider_session_id", None
                            )
                            if provider_session_id:
                                stats["provider_session_id"] = provider_session_id
                                self._store.set_provider_session_id(
                                    session_id, provider_session_id
                                )
                        elif filtered.type == "text_complete":
                            if getattr(filtered, "role", "assistant") == "assistant":
                                stats["turns"] += 1
                        elif filtered.type == "usage":
                            stats["cost"] = getattr(filtered, "total_cost_usd", 0.0) or 0.0
                            stats["in_tokens"] = getattr(filtered, "input_tokens", 0) or 0
                            stats["out_tokens"] = getattr(filtered, "output_tokens", 0) or 0
                        elif filtered.type == "session_end":
                            stats["success"] = getattr(filtered, "success", True)
                            stats["error_code"] = getattr(filtered, "error_code", None)

                        self._store.append_event(session_id, filtered)
                        self.post_message(self.AgentEvent(filtered))
                    except Exception as event_exc:
                        # Keep the stream alive even if one event fails processing.
                        err = ErrorEvent(
                            provider_id=provider_id,
                            session_id=session_id,
                            code="event_pipeline_error",
                            message=f"{type(event_exc).__name__}: {event_exc}",
                        )
                        with contextlib.suppress(Exception):
                            self._store.append_event(session_id, err)
                        self.post_message(self.AgentEvent(err))

            asyncio.run(_run())

            status = "cancelled" if self._cancel_requested else (
                "completed" if (stats["success"] is not False) else "failed"
            )
            self._store.finalize_session(
                session_id,
                status=status,
                total_cost_usd=stats["cost"],
                total_turns=stats["turns"],
                total_input_tokens=stats["in_tokens"],
                total_output_tokens=stats["out_tokens"],
                provider_session_id=stats["provider_session_id"],
            )
            code = 0 if status in {"completed", "cancelled"} else -1
            self.post_message(self.ProcessExited(code, was_cancelled=self._cancel_requested))

        except Exception as exc:
            err = ErrorEvent(
                provider_id=provider_id,
                session_id=session_id,
                code="runner_exception",
                message=str(exc),
            )
            self._store.append_event(session_id, err)
            self.post_message(self.AgentEvent(err))
            self._store.finalize_session(
                session_id,
                status="failed",
                total_cost_usd=stats["cost"],
                total_turns=stats["turns"],
                total_input_tokens=stats["in_tokens"],
                total_output_tokens=stats["out_tokens"],
                provider_session_id=stats["provider_session_id"],
            )
            self.post_message(self.ProcessExited(-1))

        finally:
            self._active_task = False
            self._cancel_requested = False
            with contextlib.suppress(Exception):
                asyncio.run(self._adapter.close())

    def cancel(self) -> None:
        """Cancel active provider stream and worker."""
        self._cancel_requested = True
        self.workers.cancel_group(self, "provider")
        # Schedule adapter cancel on the running event loop (Textual main loop).
        # asyncio.run() cannot be used here — it would raise RuntimeError
        # because Textual's event loop is already running.
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._adapter.cancel())
        except RuntimeError:
            # No running loop (e.g. called from a plain thread) — fallback
            with contextlib.suppress(Exception):
                asyncio.run(self._adapter.cancel())
