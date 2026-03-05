# DGC Terminal Interface — Definitive Component Architecture

**Version:** 1.1 — Provider-Agnostic  
**Date:** 2026-03-05  
**Baseline:** v1.0 (2026-03-05) — Claude-specific architecture  
**Target:** Python Textual 8.0.2 + Any LLM provider (Claude, OpenAI, OpenRouter, Ollama, custom)  
**Platform:** macOS M3 Pro, Python 3.14  
**Status:** Architecture Blueprint — Ready for Implementation

---

## Table of Contents

1. [Architecture Diff vs v1.0](#1-architecture-diff-vs-v10)
2. [ProviderAdapter Interface](#2-provideradapter-interface)
3. [Canonical Normalized Event Schema](#3-canonical-normalized-event-schema)
4. [Capability Matrix & Graceful Degradation](#4-capability-matrix--graceful-degradation)
5. [Provider-Neutral Session Store](#5-provider-neutral-session-store)
6. [Concrete Provider Mappings](#6-concrete-provider-mappings)
7. [Governance & Safety Layer](#7-governance--safety-layer)
8. [Revised Package Structure](#8-revised-package-structure)
9. [Preserved TUI UX Goals](#9-preserved-tui-ux-goals)
10. [2-Week Implementation Plan](#10-2-week-implementation-plan)
11. [Phase-1 Code Prompt for Claude Code](#11-phase-1-code-prompt-for-claude-code)

---

## 1. Architecture Diff vs v1.0

### What Stays (v1.0 foundations preserved)

| v1.0 Component | Status | Notes |
|----------------|--------|-------|
| Decomposed package with hard boundaries | **KEPT** | Structure refined, not replaced |
| `engine/` has zero Textual imports | **KEPT** | This was the best decision in v1.0 |
| One widget per file | **KEPT** | — |
| Screens as composition, not behavior | **KEPT** | — |
| Theme as separate concern (TCSS) | **KEPT** | — |
| Message bus architecture | **KEPT** | Event types change; bus pattern stays |
| Warm dark amber theme (Appendix B) | **KEPT** | Verbatim from v1.0 |
| Keyboard binding map | **KEPT** | — |
| Widget inventory (18 components) | **KEPT** | StatusBar gets provider-aware fields |
| Phased build approach | **REVISED** | Resequenced around adapter-first |
| RichLog-based StreamOutput | **KEPT** | Consumes canonical events, not raw provider events |
| TextArea multi-line PromptInput | **KEPT** | — |
| Widget registry for Darwin | **KEPT** | — |
| Stigmergy bridge hooks | **KEPT** | — |

### What Changes

| v1.0 Component | v1.1 Change | Why |
|----------------|-------------|-----|
| `engine/stream_parser.py` (Claude NDJSON only) | **REPLACED** by `engine/adapters/` package with per-provider adapters | v1.0 hardcoded `parse_ndjson_line()` for Claude's wire format |
| `engine/subprocess_manager.py` (Claude Code process) | **REPLACED** by `engine/provider_runner.py` dispatching to adapter's `start()`/`stream()` | v1.0 assumed subprocess + NDJSON stdout; OpenAI/Ollama use HTTP SSE/NDJSON |
| `engine/event_types.py` (Claude-shaped dataclasses) | **REPLACED** by `engine/events.py` with canonical schema v1 | v1.0 had `SystemInit.mcp_servers`, `AssistantMessage.parent_tool_use_id`, etc. — Claude-specific fields |
| Appendix A (Claude NDJSON protocol) | **MOVED** to `engine/adapters/claude.py` docstring | Protocol details belong with the adapter, not the architecture doc |
| `~/.claude/sessions/` session browser | **REPLACED** by `~/.dharma/sessions/` with provider metadata | v1.0 tied to Claude Code's session storage |
| `StatusBar` fields | **REVISED** — `model` → `provider:model`, add provider badge | Must show which provider is active |
| Event routing table | **REVISED** — routes canonical events, not Claude NDJSON types | Left column changes from `system/init` → `session_start`, etc. |
| Build sequence | **RESEQUENCED** — Phase 0 now includes adapter interface + Claude adapter | Adapter is the foundation, not an afterthought |

### What's New in v1.1

| New Component | Purpose |
|---------------|---------|
| `engine/adapters/` package | Abstract `ProviderAdapter` + concrete adapters |
| `engine/adapters/base.py` | `ProviderAdapter` ABC + `ModelProfile` + `ProviderCapabilities` |
| `engine/adapters/claude.py` | Claude Code CLI adapter (subprocess + NDJSON) |
| `engine/adapters/openai.py` | OpenAI Responses API adapter (HTTP SSE) |
| `engine/adapters/openrouter.py` | OpenRouter adapter (OpenAI-compatible SSE) |
| `engine/adapters/ollama.py` | Ollama local adapter (HTTP NDJSON) |
| `engine/events.py` | Canonical normalized event schema v1 |
| `engine/session_store.py` | Provider-neutral session persistence |
| `engine/governance.py` | Permission boundaries, redaction, audit log |
| `engine/provider_runner.py` | Replaces `subprocess_manager.py` — dispatches to adapters |
| `config/providers.toml` | Provider configuration (keys, endpoints, defaults) |

---

## 2. ProviderAdapter Interface

### Design Principles (Stolen from the Best)

| Source | Pattern Stolen | Why It's Right |
|--------|---------------|----------------|
| Vercel AI SDK `LanguageModelV3` | Two methods: `doGenerate()` + `doStream()` | Minimal surface = fewer bugs, easier to implement new adapters |
| pydantic-ai `ModelProfile` | Declarative capability matrix drives behavior | No runtime `if provider == "claude"` conditionals scattered through the codebase |
| aisuite `provider:model` string | Single string identifies provider + model | Clean config, clean CLI, clean UI display |
| Mirascope `@call` decorator | Provider is a parameter, not a class hierarchy | Runtime swappability without inheritance acrobatics |
| Instructor `Mode` enum | Output strategy depends on provider capabilities | Graceful degradation: tools → json_schema → markdown |

### Abstract Base

```python
# engine/adapters/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Any
from enum import Flag, auto

from ..events import CanonicalEvent, SessionStartEvent


class Capability(Flag):
    """Provider capability flags. Queried before use, never assumed."""
    STREAMING       = auto()
    TOOL_USE        = auto()
    THINKING        = auto()  # Extended thinking / reasoning tokens
    VISION          = auto()
    JSON_SCHEMA     = auto()  # Structured output via schema
    PARALLEL_TOOLS  = auto()  # Multiple tool calls in one turn
    RESUME          = auto()  # Resume a previous session
    COST_TRACKING   = auto()  # Per-request cost data available
    CONTEXT_USAGE   = auto()  # Reports tokens used / remaining
    SYSTEM_PROMPT   = auto()  # Supports system messages
    CANCEL          = auto()  # Can cancel in-flight request


@dataclass(frozen=True)
class ModelProfile:
    """Immutable capability snapshot for a specific model."""
    provider_id: str
    model_id: str
    display_name: str                         # e.g. "Claude Sonnet 4.5"
    capabilities: Capability = Capability(0)
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    cost_per_input_mtok: float | None = None  # USD per million input tokens
    cost_per_output_mtok: float | None = None
    supports_temperature: bool = True
    default_temperature: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)  # Provider-specific metadata
    
    def supports(self, cap: Capability) -> bool:
        return bool(self.capabilities & cap)


@dataclass
class ProviderConfig:
    """Configuration for a provider instance."""
    provider_id: str               # "claude", "openai", "openrouter", "ollama"
    api_key: str | None = None     # None for Ollama (local)
    base_url: str | None = None    # Override default endpoint
    default_model: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionRequest:
    """Provider-agnostic request. Adapters translate to wire format."""
    messages: list[dict[str, Any]]
    model: str | None = None           # Override adapter's default
    system_prompt: str | None = None
    tools: list[dict] | None = None
    tool_choice: str | dict | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    stop_sequences: list[str] | None = None
    enable_thinking: bool = False      # Request reasoning if available
    resume_session_id: str | None = None
    provider_options: dict[str, Any] = field(default_factory=dict)  # Escape hatch


class ProviderAdapter(ABC):
    """Abstract interface every provider must implement.
    
    Contract:
    - __init__ receives ProviderConfig only
    - start() is called once at session start
    - stream() yields CanonicalEvents — the ONLY output type
    - Adapters NEVER import Textual or any UI code
    - Adapters are unit-testable with zero external dependencies
    """
    
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
    
    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Stable identifier: 'claude', 'openai', 'openrouter', 'ollama'"""
        ...
    
    @abstractmethod
    async def list_models(self) -> list[ModelProfile]:
        """Return all available models with capability profiles."""
        ...
    
    @abstractmethod
    async def get_profile(self, model_id: str | None = None) -> ModelProfile:
        """Return capability profile for a specific model (or default)."""
        ...
    
    @abstractmethod
    async def stream(self, request: CompletionRequest) -> AsyncIterator[CanonicalEvent]:
        """Stream a completion request. Yields canonical events.
        
        This is the primary execution method. Even non-streaming providers
        yield at minimum: session_start, text_complete, usage, done.
        """
        ...
    
    async def cancel(self) -> None:
        """Cancel in-flight request. Default: no-op."""
        pass
    
    async def close(self) -> None:
        """Release resources (HTTP clients, subprocesses). Called on shutdown."""
        pass
```

### Adapter Lifecycle

```
┌──────────────────────────────────────────────┐
│            ProviderRunner                      │
│                                                │
│  1. Load config from providers.toml            │
│  2. Instantiate adapter: ClaudeAdapter(cfg)    │
│  3. profile = await adapter.get_profile()      │
│  4. Check capabilities → adjust UI             │
│  5. events = adapter.stream(request)           │
│  6. async for event in events:                 │
│       post_message(AgentEvent(event))          │
│  7. await adapter.close()                      │
└──────────────────────────────────────────────┘
```

---

## 3. Canonical Normalized Event Schema

### Design: Envelope + Typed Payload

Every event shares an envelope. The `type` field is the discriminator. Version field enables future evolution without breaking consumers.

```python
# engine/events.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import time

SCHEMA_VERSION = 1

@dataclass
class CanonicalEvent:
    """Base envelope for all events in the DGC event bus.
    
    Every event has:
    - type: discriminator string (dispatch key)
    - schema_version: for forward compatibility
    - timestamp: when the adapter produced this event
    - provider_id: which adapter produced it
    - session_id: DGC session (NOT provider session)
    - raw: optional original provider event (for debugging/audit)
    """
    type: str
    schema_version: int = SCHEMA_VERSION
    timestamp: float = field(default_factory=time.time)
    provider_id: str = ""
    session_id: str = ""
    raw: dict | None = None  # Original provider event, redacted in production


# ─── Session lifecycle ────────────────────────────────────

@dataclass
class SessionStart(CanonicalEvent):
    """Emitted once when a provider connection is established."""
    type: str = "session_start"
    model: str = ""
    provider_session_id: str | None = None  # Provider's own session ID
    capabilities: list[str] = field(default_factory=list)  # ["streaming","tool_use","thinking"]
    tools_available: list[str] = field(default_factory=list)
    system_info: dict = field(default_factory=dict)  # provider version, cwd, etc.


@dataclass
class SessionEnd(CanonicalEvent):
    """Emitted when the session terminates (success or error)."""
    type: str = "session_end"
    success: bool = True
    error_code: str | None = None     # "max_turns", "budget_exceeded", "network_error", etc.
    error_message: str | None = None


# ─── Content streaming ────────────────────────────────────

@dataclass
class TextDelta(CanonicalEvent):
    """Token-level text streaming. Accumulate deltas for full response."""
    type: str = "text_delta"
    content: str = ""
    content_index: int = 0         # For multi-part responses
    role: str = "assistant"


@dataclass
class TextComplete(CanonicalEvent):
    """Complete text block. Emitted after all deltas for a block."""
    type: str = "text_complete"
    content: str = ""
    content_index: int = 0
    role: str = "assistant"


@dataclass
class ThinkingDelta(CanonicalEvent):
    """Reasoning / extended thinking token stream."""
    type: str = "thinking_delta"
    content: str = ""


@dataclass
class ThinkingComplete(CanonicalEvent):
    """Complete thinking block."""
    type: str = "thinking_complete"
    content: str = ""
    is_redacted: bool = False  # Some providers encrypt thinking


# ─── Tool use ─────────────────────────────────────────────

@dataclass
class ToolCallStart(CanonicalEvent):
    """A tool call has been initiated by the model."""
    type: str = "tool_call_start"
    tool_call_id: str = ""
    tool_name: str = ""
    arguments_partial: str = ""    # May be empty at start


@dataclass
class ToolArgumentsDelta(CanonicalEvent):
    """Streaming tool call arguments (JSON string fragments)."""
    type: str = "tool_args_delta"
    tool_call_id: str = ""
    delta: str = ""


@dataclass
class ToolCallComplete(CanonicalEvent):
    """Tool call fully specified — ready for execution."""
    type: str = "tool_call_complete"
    tool_call_id: str = ""
    tool_name: str = ""
    arguments: str = ""            # Complete JSON string


@dataclass
class ToolResult(CanonicalEvent):
    """Result of tool execution (sent back to the model)."""
    type: str = "tool_result"
    tool_call_id: str = ""
    tool_name: str = ""
    content: str = ""
    is_error: bool = False
    structured_result: dict | None = None  # Provider-specific parsed output
    duration_ms: int | None = None


# ─── Progress & status ────────────────────────────────────

@dataclass
class ToolProgress(CanonicalEvent):
    """Long-running tool execution progress."""
    type: str = "tool_progress"
    tool_call_id: str = ""
    tool_name: str = ""
    elapsed_seconds: float = 0.0


@dataclass
class TaskStarted(CanonicalEvent):
    """A subagent/background task began (Claude Task tool, etc.)."""
    type: str = "task_started"
    task_id: str = ""
    description: str = ""
    parent_tool_call_id: str | None = None


@dataclass
class TaskProgress(CanonicalEvent):
    """Subagent progress update."""
    type: str = "task_progress"
    task_id: str = ""
    summary: str = ""


@dataclass
class TaskComplete(CanonicalEvent):
    """Subagent finished."""
    type: str = "task_complete"
    task_id: str = ""
    success: bool = True
    summary: str = ""


# ─── Usage & cost ─────────────────────────────────────────

@dataclass
class UsageReport(CanonicalEvent):
    """Token usage and cost data. Emitted per-turn and/or at session end."""
    type: str = "usage"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    thinking_tokens: int = 0       # Reasoning tokens (OpenAI o-series, Claude thinking)
    total_cost_usd: float | None = None
    model_breakdown: dict = field(default_factory=dict)  # Per-model if multi-model session


# ─── Errors & rate limits ─────────────────────────────────

@dataclass
class ErrorEvent(CanonicalEvent):
    """Non-fatal error during streaming."""
    type: str = "error"
    code: str = ""                 # "rate_limit", "auth_failed", "network", "provider_error"
    message: str = ""
    retryable: bool = False
    retry_after_seconds: float | None = None


@dataclass
class RateLimitEvent(CanonicalEvent):
    """Rate limit warning or rejection."""
    type: str = "rate_limit"
    status: str = ""               # "warning", "rejected"
    utilization: float | None = None
    resets_at: float | None = None  # Unix timestamp


# ─── Type registry for deserialization ────────────────────

EVENT_TYPES: dict[str, type[CanonicalEvent]] = {
    "session_start": SessionStart,
    "session_end": SessionEnd,
    "text_delta": TextDelta,
    "text_complete": TextComplete,
    "thinking_delta": ThinkingDelta,
    "thinking_complete": ThinkingComplete,
    "tool_call_start": ToolCallStart,
    "tool_args_delta": ToolArgumentsDelta,
    "tool_call_complete": ToolCallComplete,
    "tool_result": ToolResult,
    "tool_progress": ToolProgress,
    "task_started": TaskStarted,
    "task_progress": TaskProgress,
    "task_complete": TaskComplete,
    "usage": UsageReport,
    "error": ErrorEvent,
    "rate_limit": RateLimitEvent,
}
```

### Schema Version Contract

- `schema_version = 1`: current schema as defined above
- Future additions: new event types can be added without incrementing version (additive change)
- Breaking changes (removing fields, changing semantics): increment `schema_version`
- Consumers MUST ignore unknown `type` values gracefully
- The `raw` field preserves the original provider event for debugging but is stripped in production (governance layer)

---

## 4. Capability Matrix & Graceful Degradation

### Capability Matrix by Provider

| Capability | Claude (CLI) | OpenAI (Responses) | OpenRouter | Ollama (Local) |
|---|---|---|---|---|
| `STREAMING` | Yes | Yes | Yes | Yes |
| `TOOL_USE` | Yes (17+ built-in) | Yes (function_call items) | Yes (provider-dependent) | Yes (model-dependent) |
| `THINKING` | Yes (thinking blocks) | Yes (reasoning_summary) | Yes (unified `reasoning`) | Yes (`think: true`, model-dependent) |
| `VISION` | Yes | Yes | Yes (provider-dependent) | Yes (model-dependent) |
| `JSON_SCHEMA` | No (use tool workaround) | Yes (`text.format`) | Yes (provider-dependent) | Yes (`format: schema`) |
| `PARALLEL_TOOLS` | Yes | Yes | Yes | No |
| `RESUME` | Yes (`--resume`) | Yes (`previous_response_id`) | No | No |
| `COST_TRACKING` | Yes (`total_cost_usd`) | Yes (`usage` in response) | Yes (`/api/v1/generation`) | No (local = free) |
| `CONTEXT_USAGE` | Yes (per-turn `usage`) | Yes (`usage` in completed) | Yes (usage chunk) | Partial (final chunk only) |
| `SYSTEM_PROMPT` | Yes (`--system-prompt`) | Yes (`instructions` / system msg) | Yes (system msg) | Yes (system msg) |
| `CANCEL` | Yes (SIGTERM process) | Yes (cancel background) | No | Yes (close HTTP connection) |

### Transport Differences

| Provider | Transport | Wire Format | Termination Signal |
|----------|-----------|-------------|-------------------|
| Claude CLI | Subprocess stdout | NDJSON (`\n`-delimited JSON) | `result` event + process exit |
| OpenAI Responses | HTTP SSE | `event: type\ndata: {json}` | `response.completed` event |
| OpenAI Chat Completions | HTTP SSE | `data: {json}` | `data: [DONE]` sentinel |
| OpenRouter | HTTP SSE | `data: {json}` (OpenAI-compatible) | `data: [DONE]` sentinel |
| Ollama Native | HTTP NDJSON | `\n`-delimited JSON | `done: true` in final chunk |
| Ollama /v1/ | HTTP SSE | `data: {json}` (OpenAI-compatible) | `data: [DONE]` sentinel |

### Graceful Degradation Rules

When a capability is unavailable, the system degrades gracefully rather than failing:

```python
# engine/degradation.py

DEGRADATION_RULES: dict[str, dict] = {
    "THINKING": {
        "when_unavailable": "hide_thinking_panel",
        "ui_effect": "ThinkingPanel not rendered; no toggle shown in footer",
        "user_message": None,  # Silent degradation
    },
    "TOOL_USE": {
        "when_unavailable": "text_only_mode",
        "ui_effect": "ToolCallCard never rendered; tool log hidden",
        "user_message": "This model does not support tool use. Running in text-only mode.",
    },
    "COST_TRACKING": {
        "when_unavailable": "hide_cost_display",
        "ui_effect": "StatusBar cost field shows '—' instead of $X.XX",
        "user_message": None,
    },
    "RESUME": {
        "when_unavailable": "disable_resume_command",
        "ui_effect": "Resume command grayed out in palette; session browser shows 'new only'",
        "user_message": "This provider does not support session resume.",
    },
    "CONTEXT_USAGE": {
        "when_unavailable": "hide_context_meter",
        "ui_effect": "StatusBar context field shows '—' instead of XX%",
        "user_message": None,
    },
    "PARALLEL_TOOLS": {
        "when_unavailable": "sequential_tool_calls",
        "ui_effect": "Tool calls rendered sequentially even if model tries parallel",
        "user_message": None,
    },
    "CANCEL": {
        "when_unavailable": "disable_ctrl_c_cancel",
        "ui_effect": "Ctrl+C shows 'Cannot cancel — wait for completion'",
        "user_message": "This provider does not support cancellation. Please wait.",
    },
}
```

### Runtime Capability Check Pattern

```python
# In any widget or screen
profile = self.app.current_profile  # ModelProfile cached on session start

if profile.supports(Capability.THINKING):
    self.query_one(ThinkingPanel).display = True
    self.query_one(Footer).add_binding("t", "toggle_thinking", "Thinking")
else:
    self.query_one(ThinkingPanel).display = False
```

---

## 5. Provider-Neutral Session Store

### Location

```
~/.dharma/
├── sessions/
│   ├── index.json                          # Session index (fast lookup)
│   └── {session_id}/
│       ├── meta.json                       # Session metadata
│       ├── transcript.jsonl                # Canonical events (JSONL)
│       └── audit.jsonl                     # Governance audit log
├── providers.toml                          # Provider configuration
└── config.toml                             # Global DGC config
```

### Session Metadata (`meta.json`)

```json
{
  "schema_version": 1,
  "session_id": "dgc-20260305-143022-a7f3",
  "created_at": "2026-03-05T14:30:22+09:00",
  "updated_at": "2026-03-05T15:12:45+09:00",
  "provider_id": "claude",
  "model_id": "claude-sonnet-4-5-20250929",
  "provider_session_id": "5620625c-b4c7-4185-9b2b-8de430dd2184",
  "title": "Rate limiting implementation",
  "cwd": "/Users/dhyana/dharma_swarm",
  "git_branch": "feature/rate-limit",
  "tags": ["coding", "api"],
  "total_cost_usd": 0.0423,
  "total_turns": 12,
  "total_input_tokens": 45000,
  "total_output_tokens": 3200,
  "capabilities_used": ["streaming", "tool_use", "thinking"],
  "status": "completed",
  "parent_session_id": null,
  "forked_from": null
}
```

### Session ID Format

```
dgc-{YYYYMMDD}-{HHMMSS}-{4hex}
```

- Human-readable (date + time + uniquifier)
- Not a UUID (UUIDs are provider-specific implementation details)
- Sortable chronologically via string comparison
- The `4hex` suffix prevents collisions for sessions started in the same second

### Session Index (`index.json`)

```json
{
  "schema_version": 1,
  "sessions": [
    {
      "session_id": "dgc-20260305-143022-a7f3",
      "title": "Rate limiting implementation",
      "provider_id": "claude",
      "model_id": "claude-sonnet-4-5-20250929",
      "created_at": "2026-03-05T14:30:22+09:00",
      "updated_at": "2026-03-05T15:12:45+09:00",
      "status": "completed",
      "total_cost_usd": 0.0423,
      "total_turns": 12
    }
  ]
}
```

### Transcript Format (`transcript.jsonl`)

Each line is a serialized `CanonicalEvent` (with `raw` field stripped in production):

```jsonl
{"type":"session_start","schema_version":1,"timestamp":1709622622.0,"provider_id":"claude","session_id":"dgc-20260305-143022-a7f3","model":"claude-sonnet-4-5-20250929","capabilities":["streaming","tool_use","thinking"]}
{"type":"text_delta","schema_version":1,"timestamp":1709622623.1,"provider_id":"claude","session_id":"dgc-20260305-143022-a7f3","content":"I'll implement","content_index":0,"role":"assistant"}
{"type":"tool_call_complete","schema_version":1,"timestamp":1709622625.0,"provider_id":"claude","session_id":"dgc-20260305-143022-a7f3","tool_call_id":"tc_001","tool_name":"Bash","arguments":"{\"command\":\"pytest tests/\"}"}
{"type":"usage","schema_version":1,"timestamp":1709622630.0,"provider_id":"claude","session_id":"dgc-20260305-143022-a7f3","input_tokens":2400,"output_tokens":180,"total_cost_usd":0.0035}
```

### Provider Configuration (`providers.toml`)

```toml
[defaults]
provider = "claude"
model = "claude-sonnet-4-5"

[providers.claude]
type = "claude_cli"
# API key from ANTHROPIC_API_KEY env var (never stored in file)
default_model = "claude-sonnet-4-5"
cli_path = "claude"  # or full path
permission_mode = "default"
max_turns = 50

[providers.openai]
type = "openai_responses"
# API key from OPENAI_API_KEY env var
default_model = "gpt-4.1"
base_url = "https://api.openai.com/v1"

[providers.openrouter]
type = "openrouter"
# API key from OPENROUTER_API_KEY env var
default_model = "anthropic/claude-sonnet-4-5"
base_url = "https://openrouter.ai/api/v1"

[providers.ollama]
type = "ollama"
default_model = "llama3.2"
base_url = "http://localhost:11434"
# No API key needed

[providers.custom_lab]
type = "openai_compatible"
base_url = "http://internal-lab.local:8080/v1"
default_model = "our-finetuned-model"
# API key from CUSTOM_LAB_KEY env var
```

---

## 6. Concrete Provider Mappings

### 6.1 Claude CLI Adapter (Subprocess + NDJSON)

```python
# engine/adapters/claude.py

class ClaudeAdapter(ProviderAdapter):
    """Adapts Claude Code CLI stream-json to canonical events.
    
    Transport: subprocess.Popen → stdout NDJSON
    Key flags: -p, --output-format stream-json, --verbose
    Optional: --include-partial-messages (token-level)
    """
    
    provider_id = "claude"
```

**Event Mapping:**

| Claude Wire Event | Canonical Event(s) |
|---|---|
| `{"type":"system","subtype":"init",...}` | `SessionStart(model=msg.model, provider_session_id=msg.session_id, tools_available=msg.tools)` |
| `{"type":"stream_event","event":{"delta":{"type":"text_delta","text":"..."}}}` | `TextDelta(content=delta.text)` |
| `{"type":"stream_event","event":{"delta":{"type":"thinking_delta","thinking":"..."}}}` | `ThinkingDelta(content=delta.thinking)` |
| `{"type":"assistant","message":{"content":[{"type":"text","text":"..."}]}}` | `TextComplete(content=block.text)` |
| `{"type":"assistant","message":{"content":[{"type":"tool_use","id":"...","name":"...","input":{}}]}}` | `ToolCallComplete(tool_call_id=block.id, tool_name=block.name, arguments=json.dumps(block.input))` |
| `{"type":"assistant","message":{"content":[{"type":"thinking","thinking":"..."}]}}` | `ThinkingComplete(content=block.thinking)` |
| `{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"..."}]}}` | `ToolResult(tool_call_id=block.tool_use_id, content=block.content, is_error=block.is_error)` |
| `{"type":"tool_progress","tool_use_id":"...","elapsed_time_seconds":12.4}` | `ToolProgress(tool_call_id=msg.tool_use_id, elapsed_seconds=msg.elapsed_time_seconds)` |
| `{"type":"system","subtype":"task_started","task_id":"..."}` | `TaskStarted(task_id=msg.task_id, description=msg.description)` |
| `{"type":"result","subtype":"success","total_cost_usd":0.018}` | `UsageReport(total_cost_usd=msg.total_cost_usd, input_tokens=...) + SessionEnd(success=True)` |
| `{"type":"result","subtype":"error_*","errors":[...]}` | `ErrorEvent(code=msg.subtype, message=errors[0]) + SessionEnd(success=False)` |
| `{"type":"rate_limit_event","rate_limit_info":{...}}` | `RateLimitEvent(status=info.status, utilization=info.utilization)` |

**Capabilities:**
```python
CLAUDE_CAPABILITIES = (
    Capability.STREAMING | Capability.TOOL_USE | Capability.THINKING |
    Capability.VISION | Capability.PARALLEL_TOOLS | Capability.RESUME |
    Capability.COST_TRACKING | Capability.CONTEXT_USAGE |
    Capability.SYSTEM_PROMPT | Capability.CANCEL
)
```

### 6.2 OpenAI Responses API Adapter (HTTP SSE)

```python
# engine/adapters/openai.py

class OpenAIAdapter(ProviderAdapter):
    """Adapts OpenAI Responses API SSE to canonical events.
    
    Transport: HTTP SSE via openai Python SDK
    Endpoint: POST /v1/responses with stream=True
    """
    
    provider_id = "openai"
```

**Event Mapping:**

| OpenAI SSE Event | Canonical Event(s) |
|---|---|
| `response.created` | `SessionStart(model=response.model)` |
| `response.output_text.delta` | `TextDelta(content=event.delta)` |
| `response.output_text.done` | `TextComplete(content=event.text)` |
| `response.reasoning_summary_text.delta` | `ThinkingDelta(content=event.delta)` |
| `response.reasoning_summary_text.done` | `ThinkingComplete(content=event.text)` |
| `response.output_item.added` (type=function_call) | `ToolCallStart(tool_call_id=item.call_id, tool_name=item.name)` |
| `response.function_call_arguments.delta` | `ToolArgumentsDelta(tool_call_id=..., delta=event.delta)` |
| `response.function_call_arguments.done` | `ToolCallComplete(tool_call_id=..., tool_name=..., arguments=event.arguments)` |
| `response.completed` | `UsageReport(input_tokens=usage.input_tokens, output_tokens=usage.output_tokens) + SessionEnd(success=True)` |
| `response.failed` | `ErrorEvent(code=error.code, message=error.message) + SessionEnd(success=False)` |
| `error` (SSE error event) | `ErrorEvent(code=event.code, message=event.message)` |

**Capabilities (model-dependent):**
```python
# GPT-4.1, GPT-4o
GPT4_CAPABILITIES = (
    Capability.STREAMING | Capability.TOOL_USE | Capability.VISION |
    Capability.JSON_SCHEMA | Capability.PARALLEL_TOOLS |
    Capability.COST_TRACKING | Capability.CONTEXT_USAGE |
    Capability.SYSTEM_PROMPT
)

# o3, o4-mini (reasoning models)
O_SERIES_CAPABILITIES = GPT4_CAPABILITIES | Capability.THINKING
```

### 6.3 OpenRouter Adapter (OpenAI-Compatible SSE)

```python
# engine/adapters/openrouter.py

class OpenRouterAdapter(ProviderAdapter):
    """Adapts OpenRouter's OpenAI-compatible SSE to canonical events.
    
    Transport: HTTP SSE (OpenAI chat completions format)
    Endpoint: POST /api/v1/chat/completions with stream=True
    Key difference: `provider` field in responses, cost in usage chunk
    """
    
    provider_id = "openrouter"
```

**Event Mapping:**

| OpenRouter SSE Chunk | Canonical Event(s) |
|---|---|
| First chunk (has `model`, `provider`) | `SessionStart(model=chunk.model, system_info={"provider":chunk.provider})` |
| `choices[0].delta.content = "..."` | `TextDelta(content=delta.content)` |
| `choices[0].delta.reasoning = "..."` | `ThinkingDelta(content=delta.reasoning)` |
| `choices[0].delta.tool_calls[0].function.name = "..."` | `ToolCallStart(tool_call_id=tc.id, tool_name=tc.function.name)` |
| `choices[0].delta.tool_calls[0].function.arguments = "..."` | `ToolArgumentsDelta(tool_call_id=tc.id, delta=tc.function.arguments)` |
| `choices[0].finish_reason = "tool_calls"` | `ToolCallComplete(...)` (assemble from accumulated deltas) |
| `choices[0].finish_reason = "stop"` | `TextComplete(content=accumulated_text)` |
| Usage chunk (`choices: [], usage: {...}`) | `UsageReport(input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens, total_cost_usd=usage.cost)` |
| `data: [DONE]` | `SessionEnd(success=True)` |
| `: OPENROUTER PROCESSING` (SSE comment) | *Ignored* (keepalive) |
| Error chunk (`finish_reason: "error"`) | `ErrorEvent(code="provider_error", message=chunk.error.message)` |

**Capabilities:** Dynamic per model — query `/api/v1/models` and map `supported_parameters` to `Capability` flags.

### 6.4 Ollama Local Adapter (HTTP NDJSON)

```python
# engine/adapters/ollama.py

class OllamaAdapter(ProviderAdapter):
    """Adapts Ollama's native API NDJSON to canonical events.
    
    Transport: HTTP NDJSON via /api/chat
    No API key required. Local-only.
    """
    
    provider_id = "ollama"
```

**Event Mapping:**

| Ollama NDJSON Chunk | Canonical Event(s) |
|---|---|
| First chunk (model loaded) | `SessionStart(model=chunk.model)` |
| `{"message":{"content":"..."},"done":false}` | `TextDelta(content=msg.content)` |
| `{"message":{"thinking":"...","content":""},"done":false}` | `ThinkingDelta(content=msg.thinking)` |
| `{"message":{"tool_calls":[...]},"done":false}` | `ToolCallComplete(tool_call_id=generated, tool_name=tc.function.name, arguments=json.dumps(tc.function.arguments))` |
| `{"done":true,"eval_count":282,...}` | `UsageReport(input_tokens=prompt_eval_count, output_tokens=eval_count) + SessionEnd(success=True)` |
| `{"error":"out of memory"}` | `ErrorEvent(code="provider_error", message=msg.error) + SessionEnd(success=False)` |

**Key Ollama quirks:**
- Tool call arguments are **parsed JSON objects**, not strings (unlike OpenAI) — adapter must `json.dumps()` them
- No `tool_call_id` — adapter generates a UUID
- No cost tracking (local inference is "free")
- `think: true` must be set in request; not all models support it
- Must check `/api/show` for `capabilities` array to determine model support

**Capabilities (model-dependent, queried from `/api/show`):**
```python
def _build_capabilities(self, model_info: dict) -> Capability:
    caps = Capability.STREAMING | Capability.SYSTEM_PROMPT | Capability.CANCEL
    model_caps = model_info.get("capabilities", [])
    if "tools" in model_caps:
        caps |= Capability.TOOL_USE
    if "thinking" in model_caps:
        caps |= Capability.THINKING
    if "vision" in model_caps:
        caps |= Capability.VISION
    return caps
```

---

## 7. Governance & Safety Layer

### Architecture

The governance layer sits between the adapter output and the TUI event bus. Every event passes through it.

```
Adapter.stream() → GovernanceFilter → Post to Textual message bus
```

```python
# engine/governance.py
from dataclasses import dataclass, field
from pathlib import Path
import json, time, hashlib
from .events import CanonicalEvent, ToolCallComplete, TextDelta, ThinkingComplete

AUDIT_DIR = Path.home() / ".dharma" / "sessions"

@dataclass
class GovernancePolicy:
    """Configurable governance rules."""
    
    # Permission boundaries
    redact_thinking_in_audit: bool = True      # Strip thinking from audit log
    redact_raw_events: bool = True             # Strip `raw` field from all events
    max_tool_output_chars: int = 50_000        # Truncate large tool outputs
    
    # Tool permission rules (Dharma gate integration)
    blocked_tools: set[str] = field(default_factory=set)  # Tools never allowed
    gated_tools: set[str] = field(default_factory=lambda: {
        "Bash", "Write", "Edit", "NotebookEdit"  # Require confirmation
    })
    auto_approved_tools: set[str] = field(default_factory=lambda: {
        "Read", "Glob", "Grep", "WebSearch", "WebFetch"  # Safe read-only tools
    })
    
    # Prompt injection containment
    sanitize_tool_results: bool = True         # Strip control characters from tool output
    max_system_prompt_tokens: int = 10_000     # Limit injected system prompt size
    
    # Audit
    audit_enabled: bool = True
    audit_retention_days: int = 90


class GovernanceFilter:
    """Filters, redacts, and audits all events before they reach the UI."""
    
    def __init__(self, policy: GovernancePolicy, session_id: str):
        self.policy = policy
        self.session_id = session_id
        self._audit_path = AUDIT_DIR / session_id / "audit.jsonl"
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)
    
    def process(self, event: CanonicalEvent) -> CanonicalEvent | None:
        """Process an event through governance rules.
        
        Returns:
            - The event (possibly modified) to forward to the UI
            - None if the event should be suppressed
        """
        # 1. Redact raw provider data
        if self.policy.redact_raw_events:
            event.raw = None
        
        # 2. Tool permission check
        if isinstance(event, ToolCallComplete):
            if event.tool_name in self.policy.blocked_tools:
                self._audit("tool_blocked", event)
                return None  # Suppress — do not forward to UI
            # Gated tools will need UI confirmation — mark them
            if event.tool_name in self.policy.gated_tools:
                event.provider_options = {"requires_confirmation": True}
        
        # 3. Truncate large tool outputs
        if hasattr(event, 'content') and isinstance(event.content, str):
            if len(event.content) > self.policy.max_tool_output_chars:
                original_len = len(event.content)
                event.content = event.content[:self.policy.max_tool_output_chars]
                event.content += f"\n\n… (truncated from {original_len} chars)"
        
        # 4. Sanitize tool results (prompt injection containment)
        if self.policy.sanitize_tool_results and hasattr(event, 'content'):
            if isinstance(event.content, str):
                # Strip null bytes and other control characters
                event.content = event.content.replace('\x00', '')
                # Could add more sophisticated injection detection here
        
        # 5. Audit logging
        if self.policy.audit_enabled:
            self._audit("event_forwarded", event)
        
        return event
    
    def _audit(self, action: str, event: CanonicalEvent) -> None:
        """Write audit log entry."""
        entry = {
            "timestamp": time.time(),
            "action": action,
            "event_type": event.type,
            "session_id": self.session_id,
        }
        
        # Include event details (but redact thinking if configured)
        if self.policy.redact_thinking_in_audit and isinstance(event, ThinkingComplete):
            entry["content_hash"] = hashlib.sha256(event.content.encode()).hexdigest()
            entry["content_length"] = len(event.content)
        elif isinstance(event, ToolCallComplete):
            entry["tool_name"] = event.tool_name
            entry["tool_call_id"] = event.tool_call_id
        
        with open(self._audit_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
```

### Prompt Injection Containment

The governance layer implements defense-in-depth against prompt injection:

| Layer | Mechanism | Implementation |
|-------|-----------|----------------|
| **Input** | System prompt size limit | `max_system_prompt_tokens` in policy |
| **Input** | User prompt sanitization | Strip invisible Unicode, normalize whitespace |
| **Tool output** | Control character stripping | `sanitize_tool_results` removes null bytes, BEL, etc. |
| **Tool output** | Size truncation | `max_tool_output_chars` prevents context flooding |
| **Tool permission** | Blocklist / gatelist / allowlist | Three tiers of tool access control |
| **Audit** | Full event logging | Every event logged for forensic analysis |
| **Audit** | Thinking redaction | Thinking content hashed, not stored in cleartext |

### Integration with Dharma Gates

The governance layer is designed to compose with DGC's existing Dharma Kernel gates:

```python
# In ProviderRunner (the widget that manages the adapter)
async def _process_event(self, event: CanonicalEvent) -> None:
    # 1. Governance filter (security, redaction, audit)
    event = self.governance.process(event)
    if event is None:
        return  # Blocked by governance
    
    # 2. Dharma gate check (ethical/safety)
    if isinstance(event, ToolCallComplete):
        gate_result = await self.dharma_kernel.check_gate(event)
        if gate_result.blocked:
            self.post_message(self.GateBlocked(event, gate_result.reason))
            return
    
    # 3. Forward to UI
    self.post_message(self.AgentEvent(event))
```

---

## 8. Revised Package Structure

```
dgc/tui/
├── __init__.py
├── app.py                         # DGCApp — 150 lines max
├── screens/
│   ├── __init__.py
│   ├── main.py                    # MainScreen
│   ├── session_browser.py         # SessionBrowserScreen
│   ├── settings.py                # SettingsScreen
│   └── help.py                    # HelpScreen
├── widgets/
│   ├── __init__.py
│   ├── stream_output.py           # StreamOutput (RichLog) — consumes CanonicalEvents
│   ├── prompt_input.py            # PromptInput (TextArea)
│   ├── thinking_panel.py          # ThinkingPanel — hidden when !THINKING
│   ├── tool_call_card.py          # ToolCallCard
│   ├── task_list.py               # TaskListWidget
│   ├── status_bar.py              # StatusBar — provider:model, cost, ctx%
│   ├── mode_indicator.py          # ModeIndicator
│   ├── file_tree.py               # FileTreeWidget
│   ├── diff_viewer.py             # DiffViewer
│   ├── session_card.py            # SessionCard
│   └── provider_badge.py          # NEW: Provider icon/badge widget
├── engine/
│   ├── __init__.py
│   ├── events.py                  # CHANGED: Canonical event schema v1
│   ├── provider_runner.py         # CHANGED: Replaces subprocess_manager.py
│   ├── session_store.py           # CHANGED: ~/.dharma/sessions/ store
│   ├── session_state.py           # Session state machine
│   ├── governance.py              # NEW: Permission, redaction, audit
│   ├── degradation.py             # NEW: Graceful capability degradation
│   └── adapters/
│       ├── __init__.py            # Registry + factory
│       ├── base.py                # ProviderAdapter ABC + ModelProfile
│       ├── claude.py              # Claude Code CLI adapter
│       ├── openai.py              # OpenAI Responses API adapter
│       ├── openrouter.py          # OpenRouter adapter
│       ├── ollama.py              # Ollama local adapter
│       └── openai_compat.py       # Generic OpenAI-compatible adapter
├── theme/
│   ├── __init__.py
│   ├── dharma_dark.py
│   └── dharma_dark.tcss
├── commands/
│   ├── __init__.py
│   └── palette.py
└── config/
    └── providers.toml             # NEW: Provider configuration
```

### What Moved / Changed

| v1.0 File | v1.1 File | Change |
|-----------|-----------|--------|
| `engine/stream_parser.py` | `engine/adapters/claude.py` (internal) | Parser logic moved into Claude adapter |
| `engine/event_types.py` | `engine/events.py` | Completely rewritten — canonical schema |
| `engine/subprocess_manager.py` | `engine/provider_runner.py` | Now dispatches to any adapter, not just subprocess |
| — | `engine/adapters/base.py` | NEW: Abstract interface |
| — | `engine/adapters/openai.py` | NEW |
| — | `engine/adapters/openrouter.py` | NEW |
| — | `engine/adapters/ollama.py` | NEW |
| — | `engine/governance.py` | NEW |
| — | `engine/degradation.py` | NEW |
| — | `config/providers.toml` | NEW |

---

## 9. Preserved TUI UX Goals

All v1.0 TUI goals are preserved. Here is how they work with provider-agnostic events:

| UX Goal | v1.0 Implementation | v1.1 Change |
|---------|---------------------|-------------|
| Multi-line input (Enter=submit, Shift+Enter=newline) | `PromptInput(TextArea)` | **No change** |
| Streaming text output | `StreamOutput(RichLog)` consuming Claude events | Now consumes `TextDelta` / `TextComplete` canonical events |
| Tool call cards | `ToolCallCard` rendering Claude `tool_use` blocks | Now consumes `ToolCallStart` / `ToolCallComplete` / `ToolResult` |
| Thinking toggle | `ThinkingPanel` always rendered | **Conditionally rendered** based on `Capability.THINKING` |
| Cost/timing footer | `StatusBar` with Claude cost fields | Shows `—` when provider lacks `COST_TRACKING` |
| Command palette | `commands/palette.py` | Adds `:provider` command to switch providers |
| Tabs | `TabbedContent` for drawer panels | **No change** |
| Warm dark theme | `dharma_dark.tcss` | **No change** |
| Mode cycling (Shift+Tab) | N→A→P→S cycle | **No change** |
| Keyboard grammar (/:?Tab) | Key bindings map | **No change** |
| lazygit-style command log | `ToolCallLog` in drawer | Now populated from canonical `ToolCallComplete` events |
| Session browser | Read from `~/.claude/sessions/` | **CHANGED**: reads from `~/.dharma/sessions/` |

### New UX Elements in v1.1

| Element | Widget | Purpose |
|---------|--------|---------|
| Provider badge | `provider_badge.py` | Shows active provider icon/name in StatusBar |
| `:provider` command | palette.py | Switch between configured providers mid-session |
| `:models` command | palette.py | List available models for current provider |
| Capability indicators | StatusBar | Dim icons for unavailable capabilities |
| Provider config screen | SettingsScreen | Edit `providers.toml` from within TUI |

### Revised Event Routing Table

| Canonical Event | Target Widget(s) | Display Action |
|---|---|---|
| `session_start` | StatusBar, StreamOutput | Set model, provider badge, show capabilities |
| `text_delta` | StreamOutput | Append to text buffer, flush at 15fps |
| `text_complete` | StreamOutput | Render complete markdown block |
| `thinking_delta` | ThinkingPanel, StreamOutput | Append to thinking buffer (if panel visible) |
| `thinking_complete` | ThinkingPanel | Render collapsible thinking block |
| `tool_call_start` | StreamOutput, ToolCallLog | Create tool card in "running" state |
| `tool_args_delta` | ToolCallLog | Live-update argument preview |
| `tool_call_complete` | StreamOutput, ToolCallLog | Update tool card to "complete" |
| `tool_result` | StreamOutput, ToolCallLog, DiffViewer | Render result; if Edit tool, show diff |
| `tool_progress` | ToolCallLog | Update elapsed timer |
| `task_started` | TaskList, StreamOutput | Add subagent entry |
| `task_progress` | TaskList | Update progress |
| `task_complete` | TaskList | Mark complete/failed |
| `usage` | StatusBar | Update cost, token counts, context % |
| `error` | StatusBar, StreamOutput | Show error notification |
| `rate_limit` | StatusBar | Show rate limit warning |
| `session_end` | StatusBar, StreamOutput | Show completion/error badge |

---

## 10. 2-Week Implementation Plan

### Week 1: Foundation (Engine Layer)

| Day | Task | Files | Test Coverage |
|-----|------|-------|---------------|
| **Day 1** | Define canonical events + ProviderAdapter ABC | `events.py`, `adapters/base.py` | Unit tests for all event dataclasses, Capability flag combinations |
| **Day 2** | Build Claude adapter (extract from current `tui.py`) | `adapters/claude.py` | Test against recorded NDJSON fixtures from real Claude Code sessions |
| **Day 3** | Build governance filter + session store | `governance.py`, `session_store.py` | Test redaction, audit writing, session CRUD |
| **Day 4** | Build ProviderRunner (replaces SubprocessManager) | `provider_runner.py`, `degradation.py` | Integration test: Claude adapter → governance → canonical events |
| **Day 5** | Build Ollama adapter (simplest HTTP adapter) | `adapters/ollama.py` | Test against local Ollama instance |

### Week 2: TUI Integration + Additional Adapters

| Day | Task | Files | Test Coverage |
|-----|------|-------|---------------|
| **Day 6** | Refactor StreamOutput to consume canonical events | `widgets/stream_output.py` | Pilot test: feed canonical events, verify rendering |
| **Day 7** | Refactor StatusBar for provider-agnostic display + graceful degradation | `widgets/status_bar.py`, `widgets/provider_badge.py` | Test with different capability profiles |
| **Day 8** | Build OpenAI Responses adapter | `adapters/openai.py` | Test against OpenAI API with recorded SSE fixtures |
| **Day 9** | Build OpenRouter adapter + providers.toml config | `adapters/openrouter.py`, `config/providers.toml` | Test with recorded SSE fixtures |
| **Day 10** | Integration testing: full TUI with all 4 providers + session browser update | All files | End-to-end: start DGC → select provider → stream → review session |

### Dependencies

```
Day 1 ──→ Day 2 ──→ Day 4 ──→ Day 6 ──→ Day 7
  │                    ↑         ↑
  └──→ Day 3 ─────────┘         │
  └──→ Day 5 ───────────────────┘
  └──→ Day 8 ──→ Day 9 ──→ Day 10
```

Phase 0 (Day 1) blocks everything. Days 2, 3, 5, 8 can be parallelized after Day 1.

---

## 11. Phase-1 Code Prompt for Claude Code

This prompt is designed to be given directly to Claude Code for the minimal-risk Day 1–2 implementation.

---

```markdown
## Task: DGC Provider-Agnostic Event Layer (Phase 1)

### Context
The DGC terminal interface currently has a 1,600-line monolith `tui.py` that directly 
consumes Claude Code CLI's `--output-format stream-json` NDJSON. We're making it 
provider-agnostic. This is Phase 1: define the canonical event schema and extract the 
Claude adapter.

### Constraints
- Do NOT touch any Textual widget code yet. Engine layer only.
- Do NOT install any new dependencies. stdlib + dataclasses only.
- All new code goes under `dgc/tui/engine/`.
- Every file must have zero Textual imports.
- All tests must pass with `pytest dgc/tui/engine/tests/`.

### Deliverables

#### 1. Create `dgc/tui/engine/events.py`
- Define the `CanonicalEvent` base dataclass with: type, schema_version (=1), 
  timestamp, provider_id, session_id, raw (optional dict).
- Define these event types as dataclasses inheriting CanonicalEvent:
  - SessionStart, SessionEnd
  - TextDelta, TextComplete
  - ThinkingDelta, ThinkingComplete
  - ToolCallStart, ToolArgumentsDelta, ToolCallComplete, ToolResult
  - ToolProgress, TaskStarted, TaskProgress, TaskComplete
  - UsageReport, ErrorEvent, RateLimitEvent
- Define EVENT_TYPES registry dict mapping type strings to classes.
- Include docstrings explaining each event's purpose and fields.

#### 2. Create `dgc/tui/engine/adapters/__init__.py`
- Empty for now (will hold registry later).

#### 3. Create `dgc/tui/engine/adapters/base.py`
- Define `Capability` as a Flag enum with: STREAMING, TOOL_USE, THINKING, VISION, 
  JSON_SCHEMA, PARALLEL_TOOLS, RESUME, COST_TRACKING, CONTEXT_USAGE, SYSTEM_PROMPT, CANCEL.
- Define `ModelProfile` frozen dataclass with: provider_id, model_id, display_name, 
  capabilities (Capability), max_input_tokens, max_output_tokens, cost_per_input_mtok, 
  cost_per_output_mtok, extra (dict). Add `supports(cap)` method.
- Define `ProviderConfig` dataclass with: provider_id, api_key, base_url, default_model, extra.
- Define `CompletionRequest` dataclass with: messages, model, system_prompt, tools, 
  tool_choice, temperature, max_tokens, stop_sequences, enable_thinking, 
  resume_session_id, provider_options.
- Define `ProviderAdapter` ABC with: provider_id (abstract property), list_models(), 
  get_profile(), stream() -> AsyncIterator[CanonicalEvent], cancel(), close().

#### 4. Create `dgc/tui/engine/adapters/claude.py`
- Implement `ClaudeAdapter(ProviderAdapter)`.
- `stream()` method: build the `claude -p ... --output-format stream-json --verbose` 
  command, run it as a subprocess (asyncio.create_subprocess_exec), read stdout line by 
  line, parse each NDJSON line, yield CanonicalEvent instances.
- Handle all Claude event types from the mapping table (system/init → SessionStart, 
  assistant → TextComplete/ToolCallComplete, user → ToolResult, result → UsageReport+SessionEnd, 
  stream_event → TextDelta/ThinkingDelta, tool_progress → ToolProgress, rate_limit_event → RateLimitEvent).
- `cancel()`: send SIGTERM to subprocess.
- `close()`: ensure subprocess is dead.
- `list_models()`: return hardcoded profiles for claude-sonnet-4-5, claude-opus-4, claude-haiku-4-5.
- `get_profile()`: return profile for the configured model.
- CLAUDE_CAPABILITIES constant combining all flags except JSON_SCHEMA.

#### 5. Create `dgc/tui/engine/tests/test_events.py`
- Test that all event dataclasses can be instantiated with defaults.
- Test EVENT_TYPES registry is complete.
- Test CanonicalEvent.timestamp is auto-populated.
- Test schema_version is 1.

#### 6. Create `dgc/tui/engine/tests/test_claude_adapter.py`
- Create NDJSON fixtures (multi-line strings) representing:
  - Simple query (init → assistant → result/success)
  - Tool use flow (init → assistant+tool_use → user/tool_result → assistant → result)
  - Thinking flow (init → assistant with thinking block → result)
  - Error flow (init → result/error_max_turns)
- Test that ClaudeAdapter.stream() yields the correct canonical events for each fixture.
- Mock subprocess — do not call real Claude Code.

### Do NOT
- Do not create provider_runner.py yet (that's Phase 2).
- Do not create governance.py yet (Phase 2).
- Do not create session_store.py yet (Phase 2).
- Do not modify any existing files.
- Do not add OpenAI/OpenRouter/Ollama adapters yet.
```

---

## Appendix: Research Sources

### Provider APIs
- [Claude Code CLI Reference](https://code.claude.com/docs/en/cli-reference) — NDJSON stream-json protocol
- [Claude Code Agent SDK Streaming](https://platform.claude.com/docs/en/agent-sdk/streaming-output) — TypeScript event types
- [OpenAI Responses API Reference](https://platform.openai.com/docs/api-reference/responses) — SSE event taxonomy
- [OpenAI Responses vs Chat Completions](https://platform.openai.com/docs/guides/responses-vs-chat-completions) — Migration guide
- [OpenAI Reasoning Guide](https://platform.openai.com/docs/guides/reasoning) — o-series reasoning tokens
- [OpenRouter Documentation](https://openrouter.ai/docs) — Unified API, cost tracking, reasoning normalization
- [OpenRouter Models API](https://openrouter.ai/docs/api-reference/models) — Model listing + capability metadata
- [Ollama API Documentation](https://github.com/ollama/ollama/blob/main/docs/api.md) — Native NDJSON streaming
- [Ollama Thinking Support](https://ollama.com/blog/thinking) — DeepSeek R1 / Qwen 3 thinking mode
- [Ollama Tool Support](https://ollama.com/blog/streaming-tool) — Streaming tool calls

### Adapter Pattern Research
- [Vercel AI SDK — LanguageModelV3](https://ai-sdk.dev) — Cleanest provider interface
- [pydantic-ai — ModelProfile](https://ai.pydantic.dev) — Capability matrix pattern
- [LiteLLM](https://github.com/BerriAI/litellm) — OpenAI-normalized adapter pattern (strengths and scale issues)
- [aisuite](https://github.com/andrewyng/aisuite) — Convention-based plugin discovery
- [Instructor](https://python.useinstructor.com) — Mode enum + validation-retry for structured output
- [Mirascope](https://mirascope.com) — Decorator-based provider abstraction

### TUI and Architecture (from v1.0 research, still valid)
- [Textual Documentation](https://textual.textualize.io/) — Workers, Screens, Widgets, CSS
- [Harlequin](https://github.com/tconbeer/harlequin) — Complex Textual app reference architecture
- [lazygit](https://github.com/jesseduffield/lazygit) — Command log transparency pattern

---

*Architecture document v1.1 compiled 2026-03-05. Based on v1.0 baseline + 5,800+ lines of primary research across 4 provider API research documents and 1 adapter pattern analysis. All provider event mappings verified against official documentation.*
