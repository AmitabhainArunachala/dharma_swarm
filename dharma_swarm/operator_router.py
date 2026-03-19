"""WebSocket + HTTP SSE router for the Resident Operator.

Provides:
  WS  /api/operator/ws/{session_id}   — bidirectional streaming
  POST /api/operator/ask               — HTTP SSE fallback (curl/CLI)
  GET  /api/operator/sessions          — list recent sessions
  GET  /api/operator/sessions/{id}/history — session history
  GET  /api/operator/status            — operator + graduation status
  GET  /api/operator/notifications     — unread notifications

Auth:
  Localhost → pass (no auth)
  Remote → Bearer token from ~/.dharma/operator_tokens.json
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id
from dharma_swarm.resident_operator import ResidentOperator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/operator", tags=["operator"])

# Module-level reference to the operator — set by wire_operator()
_operator: ResidentOperator | None = None
_tokens_path = Path.home() / ".dharma" / "operator_tokens.json"


def wire_operator(op: ResidentOperator) -> None:
    """Called at startup to inject the operator instance."""
    global _operator
    _operator = op


def _get_operator() -> ResidentOperator:
    if _operator is None:
        raise HTTPException(503, "Operator not started")
    return _operator


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _load_tokens() -> set[str]:
    if _tokens_path.exists():
        try:
            data = json.loads(_tokens_path.read_text())
            return set(data.get("tokens", []))
        except Exception:
            pass
    return set()


def _save_tokens(tokens: set[str]) -> None:
    _tokens_path.parent.mkdir(parents=True, exist_ok=True)
    _tokens_path.write_text(json.dumps({"tokens": sorted(tokens)}))


async def _check_auth(request: Request) -> None:
    """Allow localhost unconditionally; require Bearer token for remote."""
    client_host = request.client.host if request.client else "127.0.0.1"
    if client_host in ("127.0.0.1", "::1", "localhost"):
        return

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")

    token = auth[7:]
    valid_tokens = _load_tokens()
    if token not in valid_tokens:
        raise HTTPException(403, "Invalid token")


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    content: str
    session_id: str = Field(default_factory=_new_id)
    client_id: str = "http"


class SessionInfo(BaseModel):
    session_id: str
    client_id: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws/{session_id}")
async def operator_websocket(ws: WebSocket, session_id: str) -> None:
    """Bidirectional WebSocket for real-time operator interaction.

    Client sends: {"type": "message", "content": "...", "source": "tui"}
                  {"type": "sync", "last_seq": 147}
    Server sends: OperatorEvent JSON
    """
    op = _get_operator()
    await ws.accept()

    client_id = f"ws_{_new_id()}"
    event_queue = op.register_client(client_id)

    # Background task to forward events from queue to WebSocket
    async def _forward_events() -> None:
        try:
            while True:
                event = await event_queue.get()
                await ws.send_text(event.to_json())
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass

    forward_task = asyncio.create_task(_forward_events())

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({
                    "type": "error", "content": "Invalid JSON",
                }))
                continue

            msg_type = msg.get("type", "")

            if msg_type == "sync":
                # Client wants to catch up from a sequence number
                last_seq = msg.get("last_seq", 0)
                history = await op._conversations.get_history(
                    session_id, after_seq=last_seq,
                )
                await ws.send_text(json.dumps({
                    "type": "history_catchup",
                    "messages": history,
                    "latest_seq": await op._conversations.get_latest_seq(session_id),
                }))

            elif msg_type == "message":
                content = msg.get("content", "")
                if not content:
                    continue

                # Stream operator response to this client AND broadcast
                async for event in op.handle_message(
                    session_id, content, client_id,
                ):
                    await ws.send_text(event.to_json())
                    # Also broadcast to other clients on same session
                    await op._broadcast(event)

            elif msg_type == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        pass
    finally:
        forward_task.cancel()
        op.unregister_client(client_id)


# ---------------------------------------------------------------------------
# HTTP SSE endpoint (fallback for CLI / curl / phone)
# ---------------------------------------------------------------------------

@router.post("/ask", dependencies=[Depends(_check_auth)])
async def operator_ask_http(req: AskRequest) -> StreamingResponse:
    """SSE streaming endpoint for non-WebSocket clients.

    Usage: curl -N -X POST http://localhost:8420/api/operator/ask \
           -H 'Content-Type: application/json' \
           -d '{"content": "check stigmergy"}'
    """
    op = _get_operator()

    async def _stream():
        async for event in op.handle_message(
            req.session_id, req.content, req.client_id,
        ):
            yield f"data: {event.to_json()}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@router.get("/status", dependencies=[Depends(_check_auth)])
async def operator_status() -> dict[str, Any]:
    return _get_operator().status_dict()


@router.get("/sessions", dependencies=[Depends(_check_auth)])
async def list_sessions(limit: int = 20) -> list[dict[str, Any]]:
    op = _get_operator()
    return await op._conversations.get_recent_sessions(limit)


@router.get("/sessions/{session_id}/history", dependencies=[Depends(_check_auth)])
async def session_history(
    session_id: str, limit: int = 100, after_seq: int = 0,
) -> list[dict[str, Any]]:
    op = _get_operator()
    return await op._conversations.get_history(session_id, limit, after_seq)


@router.get("/notifications", dependencies=[Depends(_check_auth)])
async def get_notifications() -> list[dict[str, Any]]:
    """Get recent proactive notifications."""
    op = _get_operator()
    events = await op._proactive_scan()
    return [e.to_dict() for e in events]


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------

@router.post("/tokens/generate", dependencies=[Depends(_check_auth)])
async def generate_token() -> dict[str, str]:
    """Generate a new auth token for remote access."""
    token = _new_id() + _new_id()  # 32 hex chars
    tokens = _load_tokens()
    tokens.add(token)
    _save_tokens(tokens)
    return {"token": token}


@router.get("/tokens", dependencies=[Depends(_check_auth)])
async def list_tokens() -> dict[str, Any]:
    tokens = _load_tokens()
    # Mask tokens for display
    masked = [t[:8] + "..." for t in sorted(tokens)]
    return {"tokens": masked, "count": len(tokens)}


@router.delete("/tokens/{token_prefix}", dependencies=[Depends(_check_auth)])
async def revoke_token(token_prefix: str) -> dict[str, Any]:
    tokens = _load_tokens()
    to_remove = [t for t in tokens if t.startswith(token_prefix)]
    if not to_remove:
        raise HTTPException(404, "Token not found")
    for t in to_remove:
        tokens.discard(t)
    _save_tokens(tokens)
    return {"revoked": len(to_remove), "remaining": len(tokens)}


# ---------------------------------------------------------------------------
# Dashboard-compatible /api/chat endpoints
# ---------------------------------------------------------------------------
# The DHARMA COMMAND dashboard (Next.js on :3420) uses these endpoints.
# SSE protocol: data: {"content": "..."} | {"tool_call": {...}} | {"tool_result": {...}} | {"error": "..."}

chat_router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    messages: list[dict[str, str]]
    context: str | None = None
    profile_id: str = "operator"


@chat_router.get("/status")
async def chat_status() -> dict[str, Any]:
    """Dashboard polls this to show chat readiness + profile info."""
    op = _get_operator()
    return {
        "status": "ok",
        "data": {
            "ready": op._running,
            "model": op.model,
            "provider": op.provider_type.value,
            "tools": 11,
            "max_tool_rounds": 40,
            "max_tokens": 8192,
            "timeout_seconds": 300,
            "tool_result_max_chars": 10000,
            "history_message_limit": 120,
            "temperature": 0.7,
            "default_profile_id": "operator",
            "profiles": [
                {
                    "id": "operator",
                    "label": "Resident Operator",
                    "provider": op.provider_type.value,
                    "model": op.model,
                    "accent": "aozora",
                    "summary": "Persistent conductor with full system access",
                },
            ],
        },
        "error": "",
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }


@chat_router.post("")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    """Dashboard-compatible SSE chat endpoint.

    Translates between the dashboard's SSE protocol and the operator's
    event stream.
    """
    op = _get_operator()

    # Extract the last user message as the question
    user_messages = [m for m in req.messages if m.get("role") == "user"]
    if not user_messages:
        async def _err():
            yield 'data: {"error": "No user message"}\n\n'
            yield "data: [DONE]\n\n"
        return StreamingResponse(_err(), media_type="text/event-stream")

    content = user_messages[-1].get("content", "")
    session_id = f"dashboard_{_new_id()}"

    async def _stream():
        async for event in op.handle_message(session_id, content, "dashboard"):
            if event.event_type == "text_delta" and event.content:
                yield f"data: {json.dumps({'content': event.content})}\n\n"
            elif event.event_type == "tool_call":
                try:
                    tc = json.loads(event.content)
                except (json.JSONDecodeError, TypeError):
                    tc = {"name": event.metadata.get("tool", "unknown")}
                yield f"data: {json.dumps({'tool_call': {'name': tc.get('name', 'unknown'), 'args': tc.get('args', {})}})}\n\n"
            elif event.event_type == "tool_result":
                yield f"data: {json.dumps({'tool_result': {'name': event.metadata.get('tool', ''), 'summary': event.content}})}\n\n"
            elif event.event_type == "error":
                yield f"data: {json.dumps({'error': event.content})}\n\n"
            elif event.event_type == "done":
                pass  # [DONE] sent below
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def wire_chat_router(app: Any) -> None:
    """Register the chat router on the app (called from api.py)."""
    app.include_router(chat_router)


__all__ = ["router", "wire_operator", "chat_router", "wire_chat_router"]
