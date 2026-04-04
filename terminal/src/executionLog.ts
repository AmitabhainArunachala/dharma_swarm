import type {ActivityEntry, ActivityPhase, CanonicalExecutionEvent, PaneKind, TranscriptLine} from "./types";
import {
  permissionDecisionFromEvent,
  permissionOutcomeFromEvent,
  permissionResolutionFromEvent,
  resolveEventActionType,
  resolveEventCommand,
  resolveEventOutput,
} from "./protocol";

const EXECUTION_EVENT_RETENTION = 4000;
const CHAT_TURN_RETENTION = 200;
const CHAT_TRACE_LINE_RETENTION = 4000;
const PANE_LINE_RETENTION = 1000;
const ACTIVITY_ENTRY_RETENTION = 1000;

function line(kind: TranscriptLine["kind"], text: string, timestamp?: string): TranscriptLine {
  return {
    id: `${kind}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    kind,
    text,
    timestamp,
  };
}

function activity(
  kind: ActivityEntry["kind"],
  event: CanonicalExecutionEvent,
  summary?: string,
  detail?: string[],
): ActivityEntry {
  return {
    id: event.id,
    kind,
    title: event.title,
    phase: event.phase,
    summary: summary ?? event.summary,
    detail: detail ?? event.detail,
    raw: event.raw,
    timestamp: event.timestamp,
    correlationId: event.correlationId,
  };
}

function compactText(value: string, maxLength = 88): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength - 1)}…` : normalized;
}

function detailLines(value: unknown): string[] {
  if (typeof value === "string") {
    return value
      .split("\n")
      .map((lineText) => lineText.trimEnd())
      .filter((lineText) => lineText.length > 0);
  }
  try {
    return JSON.stringify(value, null, 2)
      .split("\n")
      .map((lineText) => lineText.trimEnd());
  } catch {
    return [String(value)];
  }
}

function phaseForTask(type: string): ActivityPhase {
  if (type === "task_complete") {
    return "complete";
  }
  if (type === "task_started") {
    return "queued";
  }
  return "running";
}

function timestampFromEvent(event: Record<string, unknown>): string | undefined {
  const timestamp = String(event.timestamp ?? event.created_at ?? "").trim();
  return timestamp || undefined;
}

function canonicalEvent(
  event: Record<string, unknown>,
  partial: Omit<CanonicalExecutionEvent, "id" | "raw">,
): CanonicalExecutionEvent {
  const sourceId = String(event.id ?? event.tool_call_id ?? event.action_id ?? event.task_id ?? event.type ?? "event");
  return {
    id: `${partial.kind}:${sourceId}:${String(event.created_at ?? event.timestamp ?? "")}:${String(event.content ?? event.summary ?? partial.title).slice(0, 24)}`,
    raw: event,
    ...partial,
  };
}

export function userPromptExecutionEvent(prompt: string, timestamp = new Date().toISOString()): CanonicalExecutionEvent {
  const content = prompt.trim();
  return {
    id: `user_prompt:${timestamp}:${content.slice(0, 24)}`,
    sourceEventType: "user_prompt",
    kind: "user_prompt",
    phase: "complete",
    title: compactText(content || "prompt"),
    content,
    timestamp,
    raw: {prompt: content, created_at: timestamp},
  };
}

export function localStatusExecutionEvent(
  title: string,
  summary?: string,
  phase: ActivityPhase = "queued",
  timestamp = new Date().toISOString(),
): CanonicalExecutionEvent {
  return {
    id: `status:${timestamp}:${title.slice(0, 24)}`,
    sourceEventType: "local_status",
    kind: "status",
    phase,
    title,
    summary,
    timestamp,
    raw: {title, summary, created_at: timestamp, source: "local"},
  };
}

export function canonicalEventsFromBridgeEvent(event: Record<string, unknown>): CanonicalExecutionEvent[] {
  const type = String(event.type ?? "");

  if (type === "text_delta" || type === "text_complete") {
    const content = String(event.content ?? "");
    if (!content.trim()) {
      return [];
    }
    return [
      canonicalEvent(event, {
        sourceEventType: type,
        kind: "assistant_text",
        phase: type === "text_complete" ? "complete" : "running",
        title: compactText(content),
        content,
        timestamp: timestampFromEvent(event),
      }),
    ];
  }

  if (type === "thinking_delta" || type === "thinking_complete") {
    const content = String(event.content ?? "");
    if (!content.trim()) {
      return [];
    }
    return [
      canonicalEvent(event, {
        sourceEventType: type,
        kind: "thinking",
        phase: type === "thinking_complete" ? "complete" : "running",
        title: compactText(content),
        content,
        detail: detailLines(content),
        timestamp: timestampFromEvent(event),
      }),
    ];
  }

  if (type === "tool_call_complete") {
    const toolName = String(event.tool_name ?? "tool");
    const argumentsText = String(event.arguments ?? "").trim();
    return [
      canonicalEvent(event, {
        sourceEventType: type,
        kind: "tool_call",
        phase: "running",
        title: toolName,
        summary: compactText(argumentsText || toolName),
        content: argumentsText,
        detail: [`Tool: ${toolName}`, ...detailLines(argumentsText || "no arguments")],
        timestamp: timestampFromEvent(event),
        correlationId: String(event.tool_call_id ?? "").trim() || undefined,
      }),
    ];
  }

  if (type === "tool_result") {
    const toolName = String(event.tool_name ?? "tool");
    const content = String(event.content ?? "").trim();
    const failed =
      event.success === false ||
      Boolean(event.error) ||
      Boolean(event.error_message) ||
      String(event.status ?? "").toLowerCase() === "failed";
    return [
      canonicalEvent(event, {
        sourceEventType: type,
        kind: "tool_result",
        phase: failed ? "failed" : "complete",
        title: toolName,
        summary: compactText(content || "no output"),
        content,
        detail: [`Tool: ${toolName}`, ...detailLines(content || "no output")],
        timestamp: timestampFromEvent(event),
        correlationId: String(event.tool_call_id ?? "").trim() || undefined,
      }),
    ];
  }

  if (type === "permission.decision") {
    const decision = permissionDecisionFromEvent(event);
    if (!decision) {
      return [];
    }
    return [
      canonicalEvent(event, {
        sourceEventType: type,
        kind: "approval",
        phase: decision.decision === "require_approval" ? "queued" : "complete",
        title: `${decision.tool_name} requires ${decision.decision}`,
        summary: `${decision.risk} | ${decision.action_id}`,
        detail: [`Risk: ${decision.risk}`, `Rationale: ${decision.rationale}`, `Policy: ${decision.policy_source}`],
        timestamp: String(decision.metadata.created_at ?? "").trim() || timestampFromEvent(event),
        correlationId: decision.action_id,
      }),
    ];
  }

  if (type === "permission.resolution") {
    const resolution = permissionResolutionFromEvent(event);
    if (!resolution) {
      return [];
    }
    return [
      canonicalEvent(event, {
        sourceEventType: type,
        kind: "approval",
        phase: "complete",
        title: `resolution ${resolution.resolution}`,
        summary: `${resolution.action_id} | ${resolution.enforcement_state}`,
        detail: [`Action: ${resolution.action_id}`, `Enforcement: ${resolution.enforcement_state}`, ...(resolution.note ? [`Note: ${resolution.note}`] : [])],
        timestamp: resolution.resolved_at,
        correlationId: resolution.action_id,
      }),
    ];
  }

  if (type === "permission.outcome") {
    const outcome = permissionOutcomeFromEvent(event);
    if (!outcome) {
      return [];
    }
    return [
      canonicalEvent(event, {
        sourceEventType: type,
        kind: "approval",
        phase: outcome.outcome === "runtime_record_failed" || outcome.outcome === "runtime_rejected" || outcome.outcome === "runtime_expired" ? "failed" : "complete",
        title: `runtime ${outcome.outcome}`,
        summary: `${outcome.action_id} | ${outcome.source}`,
        detail: [`Action: ${outcome.action_id}`, `Source: ${outcome.source}`, `Summary: ${outcome.summary}`],
        timestamp: outcome.outcome_at,
        correlationId: outcome.action_id,
      }),
    ];
  }

  if (type === "task_started" || type === "task_progress" || type === "task_complete") {
    const taskId = String(event.task_id ?? "task");
    const status = String(event.status ?? type.replace("task_", ""));
    const summary = compactText(String(event.summary ?? event.message ?? status));
    return [
      canonicalEvent(event, {
        sourceEventType: type,
        kind: "task",
        phase: phaseForTask(type),
        title: `${taskId} ${status}`,
        summary,
        detail: detailLines(event),
        timestamp: timestampFromEvent(event),
        correlationId: taskId,
      }),
    ];
  }

  if (type === "command.result" || (type === "action.result" && resolveEventActionType(event) === "command.run")) {
    const command = resolveEventCommand(event);
    const output = resolveEventOutput(event).trim();
    const summary = String(event.summary ?? "").trim();
    if (!command && !summary && !output) {
      return [];
    }
    return [
      canonicalEvent(event, {
        sourceEventType: type,
        kind: "command",
        phase: "complete",
        title: command ? `intent ${command}` : "command result",
        summary: compactText(summary || output || "completed"),
        content: output || undefined,
        detail: command ? [`Command: ${command}`] : [],
        timestamp: timestampFromEvent(event),
        correlationId: String(event.id ?? "").trim() || undefined,
      }),
    ];
  }

  if (type === "bridge.ready" || type === "handshake.result" || type === "session_end") {
    return [
      canonicalEvent(event, {
        sourceEventType: type,
        kind: "status",
        phase: "complete",
        title:
          type === "bridge.ready"
            ? "bridge process ready"
            : type === "handshake.result"
              ? "bridge handshake complete"
              : `session ${event.success === false ? "failed" : "ended"}`,
        summary: type === "session_end" ? String(event.session_id ?? "").trim() || undefined : undefined,
        detail:
          type === "session_end"
            ? [
                `Request ${String(event.request_id ?? "").trim() || "pending"}`,
                event.success === false ? "Turn failed" : "Turn completed",
              ]
            : undefined,
        timestamp: timestampFromEvent(event),
      }),
    ];
  }

  if (type === "session.bootstrap.result" || type === "session.ack") {
    return [
      canonicalEvent(event, {
        sourceEventType: type,
        kind: "status",
        phase: "complete",
        title: type === "session.bootstrap.result" ? "bootstrap ready" : "session acknowledged",
        summary:
          type === "session.ack"
            ? `${String(event.provider ?? "").trim()}:${String(event.model ?? "").trim()}`.replace(/^:/, "") || undefined
            : undefined,
        detail:
          type === "session.bootstrap.result"
            ? ["Context packet prepared", `Request ${String(event.request_id ?? "").trim() || "pending"}`]
            : [
                `Session ${String(event.session_id ?? "").trim() || "pending"}`,
                `${String(event.provider ?? "").trim()}:${String(event.model ?? "").trim()}`.replace(/^:/, "") || "route pending",
              ],
        timestamp: timestampFromEvent(event),
      }),
    ];
  }

  if (type === "error" || type === "bridge.error") {
    return [
      canonicalEvent(event, {
        sourceEventType: type,
        kind: "error",
        phase: "failed",
        title: String(event.message ?? event.code ?? "error"),
        detail: detailLines(event),
        timestamp: timestampFromEvent(event),
      }),
    ];
  }

  return [];
}

export function mergeExecutionEvents(current: CanonicalExecutionEvent[], incoming: CanonicalExecutionEvent[]): CanonicalExecutionEvent[] {
  const next = [...current];
  for (const event of incoming) {
    const existingIndex = next.findIndex((candidate) => candidate.id === event.id);
    if (existingIndex >= 0) {
      next[existingIndex] = event;
      continue;
    }
    next.push(event);
  }
  return next.slice(-EXECUTION_EVENT_RETENTION);
}

function stepGlyph(phase: ActivityPhase): string {
  if (phase === "failed") {
    return "!";
  }
  if (phase === "complete") {
    return "✓";
  }
  if (phase === "queued") {
    return "○";
  }
  return "⠋";
}

function stepLabel(event: CanonicalExecutionEvent): string {
  switch (event.kind) {
    case "thinking":
      return "Reasoning";
    case "tool_call":
    case "tool_result":
      return "Tool";
    case "approval":
      return "Approval";
    case "task":
      return "Task";
    case "command":
      return "Command";
    case "status":
      return "Status";
    case "error":
      return "Error";
    default:
      return "Trace";
  }
}

function rawLines(raw: Record<string, unknown> | undefined): string[] {
  if (!raw) {
    return [];
  }
  return JSON.stringify(raw, null, 2)
    .split("\n")
    .map((entry) => entry.trimEnd());
}

type ChatTraceProjectionOptions = {
  visibilityMode?: "compact" | "expanded";
  showRaw?: boolean;
};

type TraceStep = {
  key: string;
  kind: Exclude<CanonicalExecutionEvent["kind"], "assistant_text" | "user_prompt">;
  phase: ActivityPhase;
  title: string;
  summary?: string;
  detail: string[];
  timestamp?: string;
  raw?: Record<string, unknown>;
};

type ChatTurn = {
  key: string;
  prompt: string;
  phase: ActivityPhase;
  steps: TraceStep[];
  assistant?: string;
  assistantTimestamp?: string;
};

function mergeStepDetail(current: string[], incoming: string[] | undefined): string[] {
  const merged = [...current];
  for (const lineText of incoming ?? []) {
    if (!merged.includes(lineText)) {
      merged.push(lineText);
    }
  }
  return merged;
}

function traceStepFromEvent(event: CanonicalExecutionEvent): TraceStep | undefined {
  if (event.kind === "assistant_text" || event.kind === "user_prompt") {
    return undefined;
  }
  if (event.kind === "tool_call" || event.kind === "tool_result") {
    return {
      key: event.correlationId ? `tool:${event.correlationId}` : event.id,
      kind: "tool_result",
      phase: event.phase,
      title: event.title,
      summary: event.kind === "tool_result" ? event.summary ?? event.content : event.summary ?? event.title,
      detail: mergeStepDetail(
        event.kind === "tool_call" ? [`Call: ${event.summary ?? event.title}`] : [],
        event.detail,
      ),
      timestamp: event.timestamp,
      raw: event.raw,
    };
  }
  return {
    key: event.correlationId ? `${event.kind}:${event.correlationId}` : event.id,
    kind: event.kind,
    phase: event.phase,
    title: event.title,
    summary: event.summary,
    detail: event.detail ?? [],
    timestamp: event.timestamp,
    raw: event.raw,
  };
}

function projectChatTurns(events: CanonicalExecutionEvent[]): ChatTurn[] {
  const turns: ChatTurn[] = [];
  let activeTurn: ChatTurn | undefined;

  for (const event of events) {
    if (event.kind === "user_prompt") {
      activeTurn = {
        key: event.id,
        prompt: event.content ?? event.title,
        phase: "running",
        steps: [],
      };
      turns.push(activeTurn);
      continue;
    }
    if (!activeTurn) {
      continue;
    }
    if (event.kind === "assistant_text") {
      const content = (event.content ?? "").trim();
      if (content && activeTurn.assistant !== content) {
        activeTurn.assistant = content;
        activeTurn.assistantTimestamp = event.timestamp;
      }
      if (event.phase === "complete" && activeTurn.phase === "running") {
        activeTurn.phase = "complete";
      }
      continue;
    }
    const nextStep = traceStepFromEvent(event);
    if (nextStep) {
      const existing = activeTurn.steps.find((step) => step.key === nextStep.key);
      if (existing) {
        existing.phase = nextStep.phase;
        existing.summary = nextStep.summary ?? existing.summary;
        existing.detail = mergeStepDetail(existing.detail, nextStep.detail);
        existing.raw = nextStep.raw ?? existing.raw;
        existing.timestamp = nextStep.timestamp ?? existing.timestamp;
      } else {
        activeTurn.steps.push(nextStep);
      }
    }
    if (event.kind === "error" || event.phase === "failed") {
      activeTurn.phase = "failed";
    }
    if (event.kind === "status" && /session (failed|ended)/i.test(event.title)) {
      activeTurn.phase = /failed/i.test(event.title) || event.phase === "failed" ? "failed" : activeTurn.phase === "failed" ? "failed" : "complete";
      activeTurn = undefined;
    }
  }

  return turns.slice(-CHAT_TURN_RETENTION);
}

export function projectChatTraceLines(events: CanonicalExecutionEvent[], options: ChatTraceProjectionOptions = {}): TranscriptLine[] {
  const visibilityMode = options.visibilityMode ?? "expanded";
  const showRaw = options.showRaw ?? false;
  const turns = projectChatTurns(events);
  const projected: TranscriptLine[] = [];

  for (let index = 0; index < turns.length; index += 1) {
    const turn = turns[index];
    const turnLabel = turn.phase === "failed" ? "failed" : turn.phase === "complete" ? "complete" : "running";
    projected.push(line("system", `## Turn ${index + 1} | ${turnLabel}`, turn.assistantTimestamp ?? turn.steps.at(-1)?.timestamp));
    projected.push(line("user", `> ${turn.prompt}`));
    projected.push(line("system", `- Trace ${visibilityMode === "compact" ? "compact" : "expanded"} | ${turn.steps.length} steps`));

    for (const step of turn.steps) {
      projected.push(
        line(
          step.phase === "failed" || step.kind === "error" ? "error" : step.kind === "tool_call" || step.kind === "tool_result" || step.kind === "approval" ? "tool" : "system",
          `- ${stepGlyph(step.phase)} ${stepLabel({kind: step.kind} as CanonicalExecutionEvent)} | ${step.title}${step.summary ? ` | ${step.summary}` : ""}`,
          step.timestamp,
        ),
      );
      if (visibilityMode === "expanded") {
        for (const detailLine of step.detail) {
          projected.push(line("system", `  - ${detailLine}`, step.timestamp));
        }
      } else if (step.detail[0]) {
        projected.push(line("system", `  - ${step.detail[0]}`, step.timestamp));
      }
      if (showRaw) {
        for (const rawLine of rawLines(step.raw)) {
          projected.push(line("system", `    ${rawLine}`, step.timestamp));
        }
      }
    }

    if (turn.assistant) {
      projected.push(line("system", "### Response", turn.assistantTimestamp));
      for (const responseLine of turn.assistant.split("\n")) {
        projected.push(line("assistant", responseLine, turn.assistantTimestamp));
      }
    }
  }

  return projected.slice(-CHAT_TRACE_LINE_RETENTION);
}

export function projectPaneLines(paneKind: Extract<PaneKind, "thinking" | "tools" | "timeline">, events: CanonicalExecutionEvent[]): TranscriptLine[] {
  return events.flatMap((event) => {
    if (paneKind === "thinking") {
      if (event.kind === "thinking" && event.content) {
        return [line("thinking", event.content, event.timestamp)];
      }
      if (event.kind === "command" || event.kind === "error") {
        return [line(event.kind === "error" ? "error" : "system", `${event.title}${event.summary ? ` | ${event.summary}` : ""}`, event.timestamp)];
      }
      return [];
    }
    if (paneKind === "tools") {
      if (event.kind === "tool_call") {
        return [line("tool", `⠋ ${event.summary ?? event.title}`, event.timestamp)];
      }
      if (event.kind === "tool_result") {
        return [line("tool", `${event.phase === "failed" ? "!" : "✓"} ${event.title}: ${event.summary ?? event.content ?? "no output"}`, event.timestamp)];
      }
      if (event.kind === "approval" || event.kind === "error") {
        return [line(event.kind === "error" ? "error" : "system", `${event.title}${event.summary ? ` | ${event.summary}` : ""}`, event.timestamp)];
      }
      return [];
    }
    if (event.kind === "task" || event.kind === "status" || event.kind === "command" || event.kind === "error") {
      return [line(event.kind === "error" ? "error" : "system", `${event.title}${event.summary ? ` | ${event.summary}` : ""}`, event.timestamp)];
    }
    return [];
  }).slice(-PANE_LINE_RETENTION);
}

export function projectActivityEntries(events: CanonicalExecutionEvent[]): ActivityEntry[] {
  return events.flatMap((event) => {
    switch (event.kind) {
      case "thinking":
        return [activity("thinking", event)];
      case "tool_call":
      case "tool_result":
        return [activity("tool", event, event.kind === "tool_result" ? event.summary : event.title)];
      case "approval":
        return [activity("approval", event)];
      case "task":
        return [activity("task", event)];
      case "command":
        return [activity("pivot", event)];
      case "status":
        return [activity("status", event)];
      case "error":
        return [activity("error", event)];
      default:
        return [];
    }
  }).slice(-ACTIVITY_ENTRY_RETENTION);
}
