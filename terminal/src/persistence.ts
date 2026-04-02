import {existsSync, mkdirSync, readFileSync, readdirSync, statSync, unlinkSync, writeFileSync} from "node:fs";
import os from "node:os";
import path from "node:path";
import {fileURLToPath} from "node:url";

import {freshnessToken} from "./freshness.js";
import type {AppState, SupervisorControlState, TabPreview} from "./types.js";
import {
  buildVerificationSummaryRows,
  isGenericVerificationLabel,
  parseVerificationBundle,
  type VerificationEntry,
  verificationBundleLabel,
} from "./verification.js";

const THIS_DIR = path.dirname(fileURLToPath(import.meta.url));
const TERMINAL_ROOT = path.resolve(THIS_DIR, "..");
const REPO_ROOT = path.resolve(TERMINAL_ROOT, "..");
const STATE_PATH = path.join(TERMINAL_ROOT, ".dharma-terminal-state.json");
const STATE_VERSION = 3;
const MAX_STATE_BYTES = 128 * 1024;
const SUPERVISOR_STATE_ENV_VARS = ["DHARMA_TERMINAL_SUPERVISOR_STATE_DIR", "DHARMA_TERMINAL_STATE_DIR"];
const DEFAULT_SUPERVISOR_ROOT = path.join(os.homedir(), ".dharma", "terminal_supervisor");
const CONTROL_SUMMARY_FILENAME = "terminal-control-summary.json";
const CONTROL_PREVIEW_FIELDS = [
  "Active task",
  "Acceptance",
  "Alerts",
  "Artifact state",
  "Active runs detail",
  "Context state",
  "Control pulse preview",
  "Durable state",
  "Last result",
  "Loop decision",
  "Loop state",
  "Next task",
  "Result status",
  "Recent operator actions",
  "Runtime DB",
  "Runtime freshness",
  "Runtime summary",
  "Runtime activity",
  "Run state",
  "Session state",
  "Task progress",
  "Toolchain",
  "Updated",
  "Verification checks",
  "Verification status",
  "Verification passing",
  "Verification failing",
  "Verification bundle",
  "Verification summary",
] as const;
const REPO_PREVIEW_FIELDS = [
  "Repo root",
  "Branch",
  "Head",
  "Sync",
  "Branch status",
  "Upstream",
  "Ahead",
  "Behind",
  "Branch sync preview",
  "Repo risk preview",
  "Repo/control preview",
  "Repo risk",
  "Dirty",
  "Dirty pressure",
  "Staged",
  "Unstaged",
  "Untracked",
  "Topology status",
  "Topology peer count",
  "Topology warnings",
  "Topology warning severity",
  "Topology risk",
  "Risk preview",
  "Topology preview",
  "Topology pressure preview",
  "Primary warning",
  "Primary peer drift",
  "Primary topology peer",
  "Peer drift markers",
  "Topology peers",
  "Topology pressure",
  "Changed hotspots",
  "Hotspot summary",
  "Lead hotspot preview",
  "Hotspot pressure preview",
  "Changed paths",
  "Primary changed hotspot",
  "Primary changed path",
  "Primary file hotspot",
  "Primary dependency hotspot",
  "Hotspots",
  "Inbound hotspots",
  "Inventory",
  "Language mix",
] as const;

type StoredState = Pick<AppState, "sidebarVisible" | "sidebarMode"> & {
  version: number;
};

type RestoredState = Omit<StoredState, "version">;

export function loadStoredState(): RestoredState | null {
  if (!existsSync(STATE_PATH)) {
    return null;
  }
  try {
    const stats = statSync(STATE_PATH);
    if (stats.size > MAX_STATE_BYTES) {
      unlinkSync(STATE_PATH);
      return null;
    }
    const decoded = JSON.parse(readFileSync(STATE_PATH, "utf8")) as Partial<StoredState>;
    if (decoded.version !== STATE_VERSION) {
      return null;
    }
    return {
      sidebarVisible: decoded.sidebarVisible ?? true,
      sidebarMode: decoded.sidebarMode ?? "toc",
    };
  } catch {
    return null;
  }
}

export function saveStoredState(state: AppState): void {
  const payload: StoredState = {
    version: STATE_VERSION,
    sidebarVisible: state.sidebarVisible,
    sidebarMode: state.sidebarMode,
  };
  writeFileSync(STATE_PATH, JSON.stringify(payload, null, 2));
}

function readJsonFile(filePath: string): Record<string, unknown> {
  if (!existsSync(filePath)) {
    return {};
  }
  try {
    return JSON.parse(readFileSync(filePath, "utf8")) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function summaryField(summary: Record<string, unknown>, key: string): string {
  const value = summary[key];
  return typeof value === "string" ? value.trim() : "";
}

function parseVerificationChecks(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((check) => {
      if (typeof check !== "object" || check === null) {
        return "";
      }
      const name = String((check as {name?: unknown}).name ?? "").trim();
      const ok = Boolean((check as {ok?: unknown}).ok);
      return name ? `${name} ${ok ? "ok" : "fail"}` : "";
    })
    .filter((entry) => entry.length > 0);
}

function previewField(preview: TabPreview | undefined, key: string): string {
  const value = preview?.[key];
  return typeof value === "string" ? value.trim() : "";
}

function buildControlPulsePreview(lastResult: string, runtimeFreshness: string, updatedAt: string, now: Date = new Date()): string {
  return [freshnessToken(updatedAt, now), lastResult.trim() || "unknown", runtimeFreshness.trim() || "unknown"].join(" | ");
}

function normalizeVerificationPreview(preview: TabPreview): void {
  const bundle = parseVerificationBundle(previewField(preview, "Verification checks"), previewField(preview, "Verification summary"));
  if (bundle.length === 0) {
    return;
  }

  const rows = buildVerificationSummaryRows(bundle);
  if (isGenericVerificationLabel(previewField(preview, "Verification summary"))) {
    preview["Verification summary"] = rows.bundle;
  }
  if (isGenericVerificationLabel(previewField(preview, "Verification status"))) {
    preview["Verification status"] = rows.status;
  }
  if (isGenericVerificationLabel(previewField(preview, "Verification passing"))) {
    preview["Verification passing"] = rows.passing;
  }
  if (isGenericVerificationLabel(previewField(preview, "Verification failing"))) {
    preview["Verification failing"] = rows.failing;
  }
  if (isGenericVerificationLabel(previewField(preview, "Verification bundle"))) {
    preview["Verification bundle"] = rows.bundle;
  }
}

function buildRuntimeSummaryPreview(preview: TabPreview | undefined): string {
  const explicit = previewField(preview, "Runtime summary");
  const runtimeDb = previewField(preview, "Runtime DB") || "runtime db not reported";
  const sessionState = previewField(preview, "Session state") || "none";
  const runState = previewField(preview, "Run state") || "none";
  const contextState = previewField(preview, "Context state") || "none";
  const derived = [runtimeDb, sessionState, runState, contextState].join(" | ");
  if (!explicit) {
    return derived;
  }

  const hasDetailedRuntimeRows = [sessionState, runState, contextState].some(
    (value) => value !== "none" && value !== "n/a" && value !== "unknown",
  );
  const placeholderSummaries = new Set([
    `${runtimeDb} | none | none | none`,
    `${runtimeDb} | n/a | n/a | n/a`,
    `${runtimeDb} | unknown | unknown | unknown`,
    "runtime db not reported | none | none | none",
    "runtime db not reported | n/a | n/a | n/a",
    "runtime db not reported | unknown | unknown | unknown",
  ]);
  if (hasDetailedRuntimeRows && placeholderSummaries.has(explicit)) {
    return derived;
  }

  return explicit;
}

function controlPulsePrefix(preview: TabPreview | undefined, now: Date = new Date()): string {
  const explicitPulse = previewField(preview, "Control pulse preview");
  const explicitPrefix = explicitPulse.match(/^(fresh|stale|unknown)\b/i)?.[1]?.toLowerCase();
  if (explicitPrefix) {
    return explicitPrefix;
  }
  return freshnessToken(previewField(preview, "Updated") || "unknown", now);
}

function repoRiskPreviewValue(preview: TabPreview | undefined): string {
  const explicit = previewField(preview, "Repo risk preview");
  if (explicit) {
    return explicit;
  }
  const branchStatus = previewField(preview, "Branch status") || "unknown";
  const riskPreview = previewField(preview, "Risk preview");
  if (!riskPreview || riskPreview === "stable") {
    return branchStatus;
  }
  return `${branchStatus} | ${riskPreview}`;
}

function buildRepoControlPreview(
  repoPreview: TabPreview | undefined,
  controlPreview: TabPreview | undefined,
  now: Date = new Date(),
): string {
  if (!repoPreview || !controlPreview) {
    return "";
  }
  const runtimeFreshness =
    previewField(controlPreview, "Runtime freshness") ||
    [
      previewField(controlPreview, "Loop state") || "unknown",
      `updated ${previewField(controlPreview, "Updated") || "unknown"}`,
      `verify ${previewField(controlPreview, "Verification bundle") || "none"}`,
    ].join(" | ");
  const activeTask = previewField(controlPreview, "Active task");
  return [
    controlPulsePrefix(controlPreview, now),
    ...(activeTask ? [`task ${activeTask}`] : []),
    repoRiskPreviewValue(repoPreview),
    runtimeFreshness,
  ].join(" | ");
}

function hasPreviewValue(value: string): boolean {
  return value.length > 0 && value !== "n/a" && value !== "unknown";
}

function firstSegment(value: string): string {
  return value
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.length > 0) ?? value.trim();
}

function deriveRepoPreviewFields(preview: TabPreview, controlPreview?: TabPreview, now: Date = new Date()): TabPreview {
  const branchStatus = previewField(preview, "Branch status");
  const ahead = previewField(preview, "Ahead");
  const behind = previewField(preview, "Behind");
  const topologyRisk = previewField(preview, "Topology risk");
  const dirtyPressure = previewField(preview, "Dirty pressure");
  const primaryWarning = previewField(preview, "Primary warning");
  const primaryPeer = previewField(preview, "Primary topology peer");
  const topologyPressure = previewField(preview, "Topology pressure");
  const primaryChangedHotspot = previewField(preview, "Primary changed hotspot");
  const primaryChangedPath = previewField(preview, "Primary changed path");
  const primaryDependencyHotspot = previewField(preview, "Primary dependency hotspot");
  const topologyWarnings = previewField(preview, "Topology warnings");

  const riskPreview =
    previewField(preview, "Risk preview") ||
    [
      ...(primaryWarning && primaryWarning !== "none" ? [primaryWarning] : []),
      ...(hasPreviewValue(primaryPeer) && primaryPeer !== "none" ? [primaryPeer] : []),
    ].join(" | ");

  const repoRisk =
    previewField(preview, "Repo risk") ||
    [
      ...(topologyRisk && topologyRisk !== "none" ? [`topology ${topologyRisk}`] : []),
      ...(hasPreviewValue(dirtyPressure) ? [dirtyPressure] : []),
    ].join("; ");

  const topologyPreview =
    previewField(preview, "Topology preview") ||
    [
      ...(primaryWarning && primaryWarning !== "none" ? [primaryWarning] : []),
      ...(hasPreviewValue(primaryPeer) && primaryPeer !== "none" ? [primaryPeer] : []),
      ...(hasPreviewValue(topologyPressure) && topologyPressure !== "none" ? [topologyPressure] : []),
    ].join(" | ");

  const topologyPressurePreview =
    previewField(preview, "Topology pressure preview") ||
    [
      ...(hasPreviewValue(topologyWarnings) && topologyWarnings !== "0" && hasPreviewValue(topologyPressure) && topologyPressure !== "none"
        ? [topologyWarnings]
        : []),
      ...(hasPreviewValue(topologyPressure) && topologyPressure !== "none" ? [firstSegment(topologyPressure)] : []),
    ].join(" | ");

  const leadHotspotPreview =
    previewField(preview, "Lead hotspot preview") ||
    [
      ...(hasPreviewValue(primaryChangedHotspot) && primaryChangedHotspot !== "none" ? [`change ${primaryChangedHotspot}`] : []),
      ...(hasPreviewValue(primaryChangedPath) && primaryChangedPath !== "none" ? [`path ${primaryChangedPath}`] : []),
      ...(hasPreviewValue(primaryDependencyHotspot) && primaryDependencyHotspot !== "none"
        ? [`dep ${primaryDependencyHotspot}`]
        : []),
    ].join(" | ");

  const hotspotPressurePreview =
    previewField(preview, "Hotspot pressure preview") ||
    [
      ...(hasPreviewValue(primaryChangedHotspot) && primaryChangedHotspot !== "none" ? [`change ${primaryChangedHotspot}`] : []),
      ...(hasPreviewValue(primaryDependencyHotspot) && primaryDependencyHotspot !== "none"
        ? [`dep ${primaryDependencyHotspot}`]
        : []),
    ].join(" | ");

  const repoRiskPreview =
    previewField(preview, "Repo risk preview") ||
    [branchStatus, riskPreview].filter((value) => hasPreviewValue(value) && value !== "stable").join(" | ") ||
    branchStatus;

  const branchSyncPreview =
    previewField(preview, "Branch sync preview") ||
    (hasPreviewValue(branchStatus) || hasPreviewValue(repoRisk)
      ? [
          branchStatus,
          `+${ahead || "n/a"}/-${behind || "n/a"}`,
          repoRisk,
        ]
          .filter((value) => value.length > 0)
          .join(" | ")
      : "");

  const enrichedPreview = {
    ...preview,
    ...(riskPreview ? {"Risk preview": riskPreview} : {}),
    ...(repoRisk ? {"Repo risk": repoRisk} : {}),
    ...(topologyPreview ? {"Topology preview": topologyPreview} : {}),
    ...(topologyPressurePreview ? {"Topology pressure preview": topologyPressurePreview} : {}),
    ...(leadHotspotPreview ? {"Lead hotspot preview": leadHotspotPreview} : {}),
    ...(hotspotPressurePreview ? {"Hotspot pressure preview": hotspotPressurePreview} : {}),
    ...(repoRiskPreview ? {"Repo risk preview": repoRiskPreview} : {}),
    ...(branchSyncPreview ? {"Branch sync preview": branchSyncPreview} : {}),
  };

  const repoControlPreview =
    previewField(preview, "Repo/control preview") || buildRepoControlPreview(enrichedPreview, controlPreview, now);

  return {
    ...enrichedPreview,
    ...(repoControlPreview ? {"Repo/control preview": repoControlPreview} : {}),
  };
}

function previewStorageKey(key: string): string {
  return `preview_${key.replaceAll(" ", "_")}`;
}

function previewLabelFromStorageKey(key: string): string {
  return key.replace(/^preview_/, "").replaceAll("_", " ");
}

function readStoredPreview(summaryPath: string, allowedKeys: readonly string[]): TabPreview | null {
  const allowed = new Set(allowedKeys);
  const stored = readJsonFile(summaryPath);
  const previewEntries = Object.entries(stored).filter(
    (entry): entry is [string, string] =>
      typeof entry[1] === "string" &&
      entry[1].trim().length > 0 &&
      entry[0].startsWith("preview_") &&
      allowed.has(previewLabelFromStorageKey(entry[0])),
  );
  if (previewEntries.length === 0) {
    return null;
  }
  return Object.fromEntries(previewEntries.map(([key, value]) => [previewLabelFromStorageKey(key), value]));
}

function writeStoredPreview(
  summary: SupervisorControlState,
  preview: TabPreview | undefined,
  allowedKeys: readonly string[],
): void {
  if (!preview) {
    return;
  }
  const summaryPath = path.join(summary.stateDir, CONTROL_SUMMARY_FILENAME);
  const payload = readJsonFile(summaryPath);
  for (const key of allowedKeys) {
    const value = previewField(preview, key);
    if (value) {
      payload[previewStorageKey(key)] = value;
    }
  }
  payload.ts = new Date().toISOString();
  mkdirSync(summary.stateDir, {recursive: true});
  writeFileSync(summaryPath, JSON.stringify(payload, null, 2) + "\n");
}

function mergeStoredPreviewFields(
  summaryPath: string,
  allowedKeys: readonly string[],
  preview: TabPreview | undefined,
): TabPreview | undefined {
  const storedPreview = readStoredPreview(summaryPath, allowedKeys) ?? {};
  const mergedPreview: TabPreview = {...storedPreview};

  if (preview) {
    for (const key of allowedKeys) {
      const value = previewField(preview, key);
      if (value) {
        mergedPreview[key] = value;
      }
    }
  }

  return Object.keys(mergedPreview).length > 0 ? mergedPreview : undefined;
}

function mergeVerificationChecks(
  existingValue: unknown,
  bundle: VerificationEntry[],
): Array<Record<string, unknown> & {name: string; ok: boolean}> {
  const existingChecks = Array.isArray(existingValue)
    ? existingValue.filter(
        (entry): entry is Record<string, unknown> & {name: string; ok: boolean} =>
          typeof entry === "object" &&
          entry !== null &&
          typeof (entry as {name?: unknown}).name === "string" &&
          typeof (entry as {ok?: unknown}).ok === "boolean",
      )
    : [];

  if (bundle.length === 0) {
    return existingChecks;
  }

  return bundle.map((entry) => {
    const existing = existingChecks.find((candidate) => candidate.name === entry.name);
    return {
      ...existing,
      name: entry.name,
      ok: entry.ok,
    };
  });
}

function writeVerificationSummaryFile(
  summary: SupervisorControlState,
  verificationSummary: string,
  verificationBundle: VerificationEntry[],
): void {
  const verificationPath = path.join(summary.stateDir, "verification.json");
  const existingPayload = readJsonFile(verificationPath);
  const effectiveSummary =
    verificationSummary || (typeof existingPayload.summary === "string" ? String(existingPayload.summary) : "") || "none";
  const payload: Record<string, unknown> = {
    ...existingPayload,
    ts: new Date().toISOString(),
    summary: effectiveSummary,
    checks: mergeVerificationChecks(existingPayload.checks, verificationBundle),
  };

  if (summary.continueRequired !== null) {
    payload.continue_required = summary.continueRequired;
  } else if (typeof existingPayload.continue_required !== "boolean") {
    payload.continue_required = false;
  }

  mkdirSync(summary.stateDir, {recursive: true});
  writeFileSync(verificationPath, JSON.stringify(payload, null, 2) + "\n");
}

function candidateSupervisorStateDirs(): string[] {
  const explicit = SUPERVISOR_STATE_ENV_VARS.map((name) => process.env[name]?.trim() ?? "").filter(Boolean);
  if (explicit.length > 0) {
    return explicit;
  }
  if (!existsSync(DEFAULT_SUPERVISOR_ROOT)) {
    return [];
  }
  return readdirSync(DEFAULT_SUPERVISOR_ROOT, {withFileTypes: true})
    .filter((entry) => entry.isDirectory())
    .map((entry) => path.join(DEFAULT_SUPERVISOR_ROOT, entry.name, "state"));
}

export function resolveSupervisorStateDir(repoRoot = REPO_ROOT): string | null {
  const candidates = candidateSupervisorStateDirs()
    .filter((stateDir) => existsSync(path.join(stateDir, "run.json")))
    .map((stateDir) => {
      const run = readJsonFile(path.join(stateDir, "run.json"));
      const runRepoRoot = typeof run.repo_root === "string" ? run.repo_root : "";
      const updatedAt = typeof run.updated_at === "string" ? run.updated_at : "";
      return {stateDir, runRepoRoot, updatedAt};
    })
    .filter((candidate) => !candidate.runRepoRoot || path.resolve(candidate.runRepoRoot) === path.resolve(repoRoot));

  if (candidates.length === 0) {
    return null;
  }

  candidates.sort((left, right) => {
    const byUpdatedAt = right.updatedAt.localeCompare(left.updatedAt);
    if (byUpdatedAt !== 0) {
      return byUpdatedAt;
    }
    const rightMtime = statSync(path.join(right.stateDir, "run.json")).mtimeMs;
    const leftMtime = statSync(path.join(left.stateDir, "run.json")).mtimeMs;
    return rightMtime - leftMtime;
  });

  return candidates[0]?.stateDir ?? null;
}

export function loadSupervisorControlState(repoRoot = REPO_ROOT): SupervisorControlState | null {
  const stateDir = resolveSupervisorStateDir(repoRoot);
  if (!stateDir) {
    return null;
  }

  const run = readJsonFile(path.join(stateDir, "run.json"));
  const verification = readJsonFile(path.join(stateDir, "verification.json"));
  const summary = asRecord(run.last_summary_fields);
  const lastVerification = asRecord(run.last_verification);
  const checks = parseVerificationChecks(verification.checks ?? lastVerification.checks);

  return {
    stateDir,
    cycle: typeof run.cycle === "number" ? run.cycle : null,
    runStatus: typeof run.status === "string" ? run.status : "unknown",
    tasksTotal: typeof run.tasks_total === "number" ? run.tasks_total : null,
    tasksPending: typeof run.tasks_pending === "number" ? run.tasks_pending : null,
    activeTaskId: typeof run.last_task_id === "string" ? run.last_task_id : "",
    lastResultStatus: summaryField(summary, "status"),
    acceptance: summaryField(summary, "acceptance"),
    verificationSummary:
      typeof verification.summary === "string"
        ? verification.summary
        : typeof lastVerification.summary === "string"
          ? lastVerification.summary
          : "",
    verificationChecks: checks,
    continueRequired:
      typeof verification.continue_required === "boolean"
        ? verification.continue_required
        : typeof run.last_continue_required === "boolean"
          ? run.last_continue_required
          : null,
    nextTask: summaryField(summary, "next_task"),
    updatedAt: typeof run.updated_at === "string" ? run.updated_at : "",
  };
}

export function loadSupervisorControlPreview(repoRoot = REPO_ROOT, now: Date = new Date()): TabPreview | null {
  const summary = loadSupervisorControlState(repoRoot);
  if (!summary) {
    return null;
  }

  const verificationRows = buildVerificationSummaryRows(
    parseVerificationBundle(summary.verificationChecks.join("; "), summary.verificationSummary || "none"),
  );

  const fallbackPreview: TabPreview = {
    "Loop state": `cycle ${summary.cycle ?? "n/a"} ${summary.runStatus}`,
    "Task progress":
      summary.tasksTotal !== null && summary.tasksPending !== null
        ? `${Math.max(summary.tasksTotal - summary.tasksPending, 0)} done, ${summary.tasksPending} pending of ${summary.tasksTotal}`
        : "unknown",
    "Active task": summary.activeTaskId || "none",
    "Result status": summary.lastResultStatus || "unknown",
    Acceptance: summary.acceptance || "unknown",
    "Last result": [summary.lastResultStatus, summary.acceptance].filter((value) => value.length > 0).join(" / ") || "unknown",
    "Verification summary": summary.verificationSummary || "none",
    "Verification checks": summary.verificationChecks.length > 0 ? summary.verificationChecks.join("; ") : "none",
    "Verification status": verificationRows.status,
    "Verification passing": verificationRows.passing,
    "Verification failing": verificationRows.failing,
    "Verification bundle": verificationBundleLabel(
      summary.verificationChecks.map((entry) => {
        const [name, status = "fail"] = entry.split(/\s+/);
        return {name, ok: status.toLowerCase() === "ok"};
      }),
    ),
    "Loop decision":
      summary.continueRequired === null ? "unknown" : summary.continueRequired ? "continue required" : "ready to stop",
    "Next task": summary.nextTask || "none",
    Updated: summary.updatedAt || "unknown",
    "Durable state": summary.stateDir,
  };
  fallbackPreview["Runtime freshness"] = [
    fallbackPreview["Loop state"],
    `updated ${fallbackPreview.Updated}`,
    `verify ${fallbackPreview["Verification bundle"]}`,
  ].join(" | ");
  fallbackPreview["Control pulse preview"] = buildControlPulsePreview(
    fallbackPreview["Last result"] || "unknown",
    fallbackPreview["Runtime freshness"] || "unknown",
    fallbackPreview.Updated || "unknown",
    now,
  );
  fallbackPreview["Runtime summary"] = buildRuntimeSummaryPreview(fallbackPreview);

  const storedPreview = readStoredPreview(path.join(summary.stateDir, CONTROL_SUMMARY_FILENAME), CONTROL_PREVIEW_FIELDS);
  const effectivePreview = storedPreview
    ? {
        ...fallbackPreview,
        ...storedPreview,
      }
    : fallbackPreview;
  normalizeVerificationPreview(effectivePreview);
  const explicitRuntimeSummary = previewField(storedPreview ?? undefined, "Runtime summary");
  effectivePreview["Runtime summary"] =
    explicitRuntimeSummary || buildRuntimeSummaryPreview({...effectivePreview, "Runtime summary": ""});
  effectivePreview["Control pulse preview"] =
    previewField(storedPreview ?? undefined, "Control pulse preview") ||
    buildControlPulsePreview(
      previewField(effectivePreview, "Last result") || "unknown",
      previewField(effectivePreview, "Runtime freshness") || "unknown",
      previewField(effectivePreview, "Updated") || "unknown",
      now,
    );
  if (storedPreview) {
    return effectivePreview;
  }

  return effectivePreview;
}

export function loadSupervisorRepoPreview(repoRoot = REPO_ROOT): TabPreview | null {
  const summary = loadSupervisorControlState(repoRoot);
  if (!summary) {
    return null;
  }
  const storedPreview = readStoredPreview(path.join(summary.stateDir, CONTROL_SUMMARY_FILENAME), REPO_PREVIEW_FIELDS);
  if (!storedPreview) {
    return null;
  }
  const controlPreview = loadSupervisorControlPreview(repoRoot);
  return deriveRepoPreviewFields(storedPreview, controlPreview ?? undefined);
}

export function saveSupervisorRepoPreview(summary: SupervisorControlState, preview?: TabPreview): void {
  if (!preview) {
    return;
  }
  const summaryPath = path.join(summary.stateDir, CONTROL_SUMMARY_FILENAME);
  const storedControlPreview = readStoredPreview(summaryPath, CONTROL_PREVIEW_FIELDS);
  const enrichedPreview = deriveRepoPreviewFields(preview, storedControlPreview ?? undefined);
  writeStoredPreview(summary, enrichedPreview, REPO_PREVIEW_FIELDS);
}

export function saveSupervisorControlSummary(summary: SupervisorControlState, preview?: TabPreview): void {
  const summaryPath = path.join(summary.stateDir, CONTROL_SUMMARY_FILENAME);
  const existingPayload = readJsonFile(summaryPath);
  const mergedPreview = mergeStoredPreviewFields(summaryPath, CONTROL_PREVIEW_FIELDS, preview);
  const previewVerificationSummary = previewField(mergedPreview, "Verification summary");
  const previewVerificationChecks = previewField(mergedPreview, "Verification checks");
  const effectiveVerificationSummary = previewVerificationSummary || summary.verificationSummary;
  const effectiveVerificationChecks = previewVerificationChecks || summary.verificationChecks.join("; ");
  const effectiveVerificationBundle = parseVerificationBundle(effectiveVerificationChecks, effectiveVerificationSummary);
  const verificationRows = buildVerificationSummaryRows(effectiveVerificationBundle);
  const normalizedVerificationSummary =
    effectiveVerificationBundle.length > 0 && isGenericVerificationLabel(effectiveVerificationSummary)
      ? verificationRows.bundle
      : effectiveVerificationSummary;
  const normalizedVerificationStatus =
    effectiveVerificationBundle.length > 0 && isGenericVerificationLabel(previewField(mergedPreview, "Verification status"))
      ? verificationRows.status
      : previewField(mergedPreview, "Verification status") || verificationRows.status;
  const normalizedVerificationPassing =
    effectiveVerificationBundle.length > 0 && isGenericVerificationLabel(previewField(mergedPreview, "Verification passing"))
      ? verificationRows.passing
      : previewField(mergedPreview, "Verification passing") || verificationRows.passing;
  const normalizedVerificationFailing =
    effectiveVerificationBundle.length > 0 && isGenericVerificationLabel(previewField(mergedPreview, "Verification failing"))
      ? verificationRows.failing
      : previewField(mergedPreview, "Verification failing") || verificationRows.failing;
  const normalizedVerificationBundle = verificationBundleLabel(effectiveVerificationBundle);
  const effectiveLoopState = previewField(mergedPreview, "Loop state") || `cycle ${summary.cycle ?? "n/a"} ${summary.runStatus}`;
  const effectiveUpdated = previewField(mergedPreview, "Updated") || summary.updatedAt || "unknown";
  const effectiveLastResult =
    previewField(mergedPreview, "Last result") ||
    [summary.lastResultStatus, summary.acceptance].filter((value) => value.length > 0).join(" / ") ||
    "unknown";
  const effectiveRuntimeFreshness =
    previewField(preview, "Runtime freshness") ||
    [effectiveLoopState, `updated ${effectiveUpdated}`, `verify ${verificationBundleLabel(effectiveVerificationBundle)}`].join(" | ");
  const effectiveControlPulse =
    previewField(preview, "Control pulse preview") ||
    buildControlPulsePreview(effectiveLastResult, effectiveRuntimeFreshness, effectiveUpdated);
  const effectiveRuntimeSummary = buildRuntimeSummaryPreview(mergedPreview);
  const previewPayload = Object.fromEntries(
    CONTROL_PREVIEW_FIELDS.map((key) => [previewStorageKey(key), previewField(mergedPreview, key)]),
  );

  const payload = {
    ...existingPayload,
    ts: new Date().toISOString(),
    cycle: summary.cycle,
    run_status: summary.runStatus,
    tasks_total: summary.tasksTotal,
    tasks_pending: summary.tasksPending,
    active_task_id: summary.activeTaskId,
    last_result_status: summary.lastResultStatus,
    acceptance: summary.acceptance,
    verification_summary: normalizedVerificationSummary,
    verification_checks: effectiveVerificationBundle.map((entry) => `${entry.name} ${entry.ok ? "ok" : "fail"}`),
    verification_bundle: effectiveVerificationBundle,
    verification_status: normalizedVerificationStatus,
    verification_passing: normalizedVerificationPassing,
    verification_failing: normalizedVerificationFailing,
    continue_required: summary.continueRequired,
    next_task: summary.nextTask,
    updated_at: summary.updatedAt,
    ...previewPayload,
    [previewStorageKey("Durable state")]: previewField(mergedPreview, "Durable state") || summary.stateDir,
    [previewStorageKey("Control pulse preview")]: effectiveControlPulse,
    [previewStorageKey("Next task")]: previewField(mergedPreview, "Next task") || summary.nextTask,
    [previewStorageKey("Runtime freshness")]: effectiveRuntimeFreshness,
    [previewStorageKey("Runtime summary")]: effectiveRuntimeSummary,
    [previewStorageKey("Updated")]: previewField(mergedPreview, "Updated") || summary.updatedAt,
    [previewStorageKey("Verification checks")]: effectiveVerificationChecks,
    [previewStorageKey("Verification status")]: normalizedVerificationStatus,
    [previewStorageKey("Verification passing")]: normalizedVerificationPassing,
    [previewStorageKey("Verification failing")]: normalizedVerificationFailing,
    [previewStorageKey("Verification bundle")]: normalizedVerificationBundle,
    [previewStorageKey("Verification summary")]: normalizedVerificationSummary,
  };
  mkdirSync(summary.stateDir, {recursive: true});
  writeFileSync(summaryPath, JSON.stringify(payload, null, 2) + "\n");
  writeVerificationSummaryFile(summary, normalizedVerificationSummary, effectiveVerificationBundle);
}
