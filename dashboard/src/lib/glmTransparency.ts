export interface GLMTransparencyToolEvent {
  type: "call" | "result";
  name: string;
  args?: Record<string, unknown>;
  summary?: string;
  timestamp: string;
}

export interface GLMTransparencyStep {
  kind: "call" | "result";
  label: string;
  detail: string | null;
  timestamp: string;
}

export interface GLMTransparencySummary {
  cue: string | null;
  preview: string;
  stepCount: number;
  toolCallCount: number;
  toolResultCount: number;
  hasObservableTrace: boolean;
  steps: GLMTransparencyStep[];
}

const PREVIEW_PART_LIMIT = 3;
const PREVIEW_MAX_CHARS = 96;
const CUE_MAX_CHARS = 140;

function collapseWhitespace(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function truncate(text: string, maxChars: number): string {
  if (text.length <= maxChars) return text;
  return `${text.slice(0, maxChars - 3).trimEnd()}...`;
}

function basename(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 1] || path;
}

function formatToolDetail(name: string, args: Record<string, unknown> | undefined): string | null {
  if (!args) return null;

  if (name === "read_file" || name === "write_file" || name === "edit_file") {
    const path = String(args.path || "").trim();
    return path ? basename(path) : null;
  }

  if (name === "shell_exec") {
    const command = collapseWhitespace(String(args.command || "").trim());
    return command || null;
  }

  if (name === "grep_search") {
    const pattern = collapseWhitespace(String(args.pattern || "").trim());
    return pattern || null;
  }

  if (name === "glob_files") {
    const pattern = collapseWhitespace(String(args.pattern || "").trim());
    return pattern || null;
  }

  const first = Object.values(args)[0];
  if (first == null) return null;
  return collapseWhitespace(String(first));
}

function formatToolAction(name: string): string {
  const labels: Record<string, string> = {
    read_file: "Read",
    write_file: "Write",
    edit_file: "Edit",
    shell_exec: "Run",
    grep_search: "Search",
    glob_files: "Glob",
    swarm_status: "Swarm",
    evolution_query: "Evolution",
    stigmergy_query: "Stigmergy",
    trace_query: "Trace",
    agent_control: "Agent",
  };
  return labels[name] ?? capitalize(name.replace(/_/g, " "));
}

function capitalize(text: string): string {
  if (!text) return text;
  return text[0].toUpperCase() + text.slice(1);
}

function formatResultLabel(name: string): string {
  return `${formatToolAction(name)} result`;
}

export function extractVisibleSynthesisCue(content: string): string | null {
  const normalized = collapseWhitespace(content);
  if (!normalized) return null;

  const sentenceMatch = normalized.match(/.+?[.!?](?:\s|$)/);
  const cue = sentenceMatch?.[0]?.trim() || normalized;
  return truncate(cue, CUE_MAX_CHARS);
}

function previewStep(step: GLMTransparencyStep): string {
  if (!step.detail) return step.label;
  return `${step.label} ${truncate(step.detail, PREVIEW_MAX_CHARS)}`;
}

export function buildGLMTransparencySummary(
  content: string,
  events: GLMTransparencyToolEvent[],
): GLMTransparencySummary {
  const steps: GLMTransparencyStep[] = events.map((event) => ({
    kind: event.type,
    label: event.type === "call" ? formatToolAction(event.name) : formatResultLabel(event.name),
    detail:
      event.type === "call"
        ? formatToolDetail(event.name, event.args)
        : event.summary
          ? collapseWhitespace(event.summary)
          : null,
    timestamp: event.timestamp,
  }));

  const cue = extractVisibleSynthesisCue(content);
  const previewParts: string[] = [];
  if (cue) {
    previewParts.push(cue);
  }
  previewParts.push(...steps.filter((step) => step.kind === "call").slice(0, PREVIEW_PART_LIMIT - previewParts.length).map(previewStep));

  if (previewParts.length === 0 && steps[0]) {
    previewParts.push(previewStep(steps[0]));
  }

  if (previewParts.length === 0) {
    previewParts.push("Waiting for observable trace");
  }

  return {
    cue,
    preview: previewParts.join(" | "),
    stepCount: steps.length,
    toolCallCount: steps.filter((step) => step.kind === "call").length,
    toolResultCount: steps.filter((step) => step.kind === "result").length,
    hasObservableTrace: steps.length > 0,
    steps,
  };
}
