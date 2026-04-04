import {existsSync, mkdirSync, readFileSync, readdirSync, statSync, unlinkSync, writeFileSync} from "node:fs";
import os from "node:os";
import path from "node:path";
import {fileURLToPath} from "node:url";

import {freshnessToken, parseControlPulsePreview, parseRuntimeFreshness} from "./freshness";
import {
  runtimePayloadToPreview,
  runtimeSnapshotPayloadFromEvent,
  workspacePayloadToPreview,
  workspaceSnapshotPayloadFromEvent,
} from "./protocol";
import {parseRepoControlPreview} from "./repoControlPreview";
import type {AppState, RuntimeSnapshotPayload, SupervisorControlState, TabPreview, WorkspaceSnapshotPayload} from "./types";
import {
  buildVerificationSummaryRows,
  isGenericVerificationLabel,
  parseVerificationBundle,
  resolveVerificationEntries,
  type VerificationEntry,
  verificationBundleLabel,
} from "./verification";

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
  "Control truth preview",
  "Context state",
  "Control pulse preview",
  "Durable state",
  "Last result",
  "Loop decision",
  "Loop state",
  "Next task",
  "Repo/control preview",
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
  "Verification receipt",
  "Verification summary",
  "Verification updated",
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
  "Repo truth preview",
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
  "Topology warning members",
  "Topology warning severity",
  "Topology risk",
  "Risk preview",
  "Topology preview",
  "Topology pressure preview",
  "Primary warning",
  "Primary peer drift",
  "Branch divergence",
  "Detached peers",
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

type StoredState = {
  version: number;
  sidebarVisible: "visible" | "collapsed" | "hidden" | boolean;
  sidebarMode: AppState["uiMode"]["sidebarMode"];
};

type RestoredState = {
  sidebarVisible: "visible" | "collapsed" | "hidden";
  sidebarMode: AppState["uiMode"]["sidebarMode"];
};
type PersistedSnapshotOptions = {
  workspacePayload?: WorkspaceSnapshotPayload;
  runtimePayload?: RuntimeSnapshotPayload;
};

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
      sidebarVisible: typeof decoded.sidebarVisible === "string" ? (decoded.sidebarVisible as "visible" | "collapsed" | "hidden") : decoded.sidebarVisible === false ? "hidden" : "collapsed",
      sidebarMode: decoded.sidebarMode ?? "toc",
    };
  } catch {
    return null;
  }
}

export function saveStoredState(state: Pick<AppState, "uiMode">): void {
  const payload: StoredState = {
    version: STATE_VERSION,
    sidebarVisible: state.uiMode.sidebarVisible,
    sidebarMode: state.uiMode.sidebarMode,
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

function recordField(record: Record<string, unknown>, key: string): string {
  const value = record[key];
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

function defaultVerificationReceiptPath(preview: TabPreview | undefined, fallbackStateDir = ""): string {
  const durableState = previewField(preview, "Durable state") || fallbackStateDir.trim();
  if (!durableState || durableState === "n/a" || durableState === "none" || durableState === "unknown") {
    return fallbackStateDir.trim() ? path.join(fallbackStateDir.trim(), "verification.json") : "";
  }
  return path.join(durableState, "verification.json");
}

function isPlaceholderPreviewValue(key: string, value: string): boolean {
  if (!value || value === "n/a" || value === "none" || value === "unknown") {
    return true;
  }
  return /^Verification(?:\s|$)/.test(key) && isGenericVerificationLabel(value);
}

function mergePreviewSources(...previews: Array<TabPreview | undefined>): TabPreview | undefined {
  const merged: TabPreview = {};
  for (const preview of previews) {
    if (!preview) {
      continue;
    }
    for (const key of CONTROL_PREVIEW_FIELDS) {
      const candidate = previewField(preview, key);
      if (!candidate) {
        continue;
      }
      const existing = previewField(merged, key);
      if (!existing || isPlaceholderPreviewValue(key, existing) || !isPlaceholderPreviewValue(key, candidate)) {
        merged[key] = candidate;
      }
    }
  }
  return Object.keys(merged).length > 0 ? merged : undefined;
}

function buildControlPulsePreview(lastResult: string, runtimeFreshness: string, updatedAt: string, now: Date = new Date()): string {
  return [freshnessToken(updatedAt, now), lastResult.trim() || "unknown", runtimeFreshness.trim() || "unknown"].join(" | ");
}

function buildControlTruthPreview(preview: TabPreview | undefined): string {
  const bundle = normalizedVerificationBundleFromPreview(preview);
  const loopState = previewField(preview, "Loop state") || derivedCompactLoopState(preview) || "unknown";
  const nextTask = previewField(preview, "Next task") || "none";
  return [bundle, loopState, `next ${nextTask}`].join(" | ");
}

function normalizedVerificationBundleFromPreview(preview: TabPreview | undefined): string {
  const explicitBundle = previewField(preview, "Verification bundle");
  if (explicitBundle && !isGenericVerificationLabel(explicitBundle)) {
    return explicitBundle;
  }

  const bundle = resolveVerificationEntries({
    checksText: previewField(preview, "Verification checks"),
    summaryText: previewField(preview, "Verification summary"),
    bundleText: explicitBundle,
    passingText: previewField(preview, "Verification passing"),
    failingText: previewField(preview, "Verification failing"),
  });
  return bundle.length > 0 ? verificationBundleLabel(bundle) : explicitBundle || "none";
}

function verificationEntriesFromPreview(preview: TabPreview | undefined): VerificationEntry[] {
  return resolveVerificationEntries({
    checksText: previewField(preview, "Verification checks"),
    summaryText: previewField(preview, "Verification summary"),
    bundleText: normalizedVerificationBundleFromPreview(preview),
    passingText: previewField(preview, "Verification passing"),
    failingText: previewField(preview, "Verification failing"),
  });
}

function normalizeVerificationPreview(preview: TabPreview): void {
  const explicitChecks = previewField(preview, "Verification checks");
  const explicitSummary = previewField(preview, "Verification summary");
  const bundle = verificationEntriesFromPreview(preview);
  if (bundle.length === 0) {
    return;
  }

  const rows = buildVerificationSummaryRows(bundle);
  const checksAreExplicit = explicitChecks && !isGenericVerificationLabel(explicitChecks);
  if (!checksAreExplicit) {
    preview["Verification checks"] = bundle.map((entry) => `${entry.name} ${entry.ok ? "ok" : "fail"}`).join("; ");
  }
  if (isGenericVerificationLabel(explicitSummary) || (checksAreExplicit && explicitSummary !== rows.bundle)) {
    preview["Verification summary"] = rows.bundle;
  }
  if (isGenericVerificationLabel(previewField(preview, "Verification status")) || (checksAreExplicit && previewField(preview, "Verification status") !== rows.status)) {
    preview["Verification status"] = rows.status;
  }
  if (
    isGenericVerificationLabel(previewField(preview, "Verification passing")) ||
    (checksAreExplicit && previewField(preview, "Verification passing") !== rows.passing)
  ) {
    preview["Verification passing"] = rows.passing;
  }
  if (
    isGenericVerificationLabel(previewField(preview, "Verification failing")) ||
    (checksAreExplicit && previewField(preview, "Verification failing") !== rows.failing)
  ) {
    preview["Verification failing"] = rows.failing;
  }
  if (isGenericVerificationLabel(previewField(preview, "Verification bundle")) || (checksAreExplicit && previewField(preview, "Verification bundle") !== rows.bundle)) {
    preview["Verification bundle"] = rows.bundle;
  }
}

function placeholderPreviewValue(value: string): boolean {
  return !value || value === "n/a" || value === "none" || value === "unknown";
}

function setControlPreviewFallback(preview: TabPreview, key: string, value: string): void {
  if (!value || placeholderPreviewValue(value)) {
    return;
  }
  const existing = previewField(preview, key);
  if (!existing || isPlaceholderPreviewValue(key, existing)) {
    preview[key] = value;
  }
}

function controlPreviewFromRepoControl(preview: TabPreview | undefined): TabPreview | undefined {
  const parsed = parseRepoControlPreview(preview);
  if (!parsed) {
    return undefined;
  }

  const bundle = parseVerificationBundle("none", parsed.verificationBundle);
  const verificationRows = buildVerificationSummaryRows(bundle);
  const verificationChecks = bundle.map((entry) => `${entry.name} ${entry.ok ? "ok" : "fail"}`).join("; ");
  const runtimeFreshnessParts = [
    parsed.loopState !== "n/a" ? parsed.loopState : "",
    parsed.updated !== "n/a" ? `updated ${parsed.updated}` : "",
    parsed.verificationBundle !== "n/a" ? `verify ${parsed.verificationBundle}` : "",
  ].filter((part) => part.length > 0);
  const lastResult = [parsed.resultStatus, parsed.acceptance].filter((value) => value !== "n/a").join(" / ");
  const controlPulseParts = [
    parsed.freshness !== "unknown" ? parsed.freshness : "",
    lastResult,
    runtimeFreshnessParts.join(" | "),
  ].filter((part) => part.length > 0);
  const derived: TabPreview = {
    "Repo/control preview": parsed.raw,
  };
  if (!placeholderPreviewValue(parsed.task)) {
    derived["Active task"] = parsed.task;
  }
  if (!placeholderPreviewValue(parsed.taskProgress)) {
    derived["Task progress"] = parsed.taskProgress;
  }
  if (!placeholderPreviewValue(parsed.resultStatus)) {
    derived["Result status"] = parsed.resultStatus;
  }
  if (!placeholderPreviewValue(parsed.acceptance)) {
    derived.Acceptance = parsed.acceptance;
  }
  if (!placeholderPreviewValue(parsed.loopDecision)) {
    derived["Loop decision"] = parsed.loopDecision;
  }
  if (!placeholderPreviewValue(parsed.loopState)) {
    derived["Loop state"] = parsed.loopState;
  }
  if (!placeholderPreviewValue(parsed.updated)) {
    derived.Updated = parsed.updated;
    derived["Verification updated"] = parsed.updated;
  }
  if (!placeholderPreviewValue(parsed.verificationBundle)) {
    derived["Verification summary"] = parsed.verificationBundle;
    derived["Verification bundle"] = bundle.length > 0 ? verificationRows.bundle : parsed.verificationBundle;
  }
  if (verificationChecks) {
    derived["Verification checks"] = verificationChecks;
  }
  if (bundle.length > 0) {
    derived["Verification status"] = verificationRows.status;
    derived["Verification passing"] = verificationRows.passing;
    derived["Verification failing"] = verificationRows.failing;
  }
  if (lastResult) {
    derived["Last result"] = lastResult;
  }
  if (runtimeFreshnessParts.length > 0) {
    derived["Runtime freshness"] = runtimeFreshnessParts.join(" | ");
  }
  if (controlPulseParts.length > 0) {
    derived["Control pulse preview"] = controlPulseParts.join(" | ");
  }
  if (!placeholderPreviewValue(parsed.runtimeDb)) {
    derived["Runtime DB"] = parsed.runtimeDb;
  }
  if (!placeholderPreviewValue(parsed.runtimeActivity)) {
    derived["Runtime activity"] = parsed.runtimeActivity;
  }
  if (!placeholderPreviewValue(parsed.artifactState)) {
    derived["Artifact state"] = parsed.artifactState;
  }
  if (!placeholderPreviewValue(parsed.nextTask)) {
    derived["Next task"] = parsed.nextTask;
  }
  return derived;
}

function hydrateControlPreviewFromRepoControl(preview: TabPreview | undefined): void {
  if (!preview) {
    return;
  }

  const derived = controlPreviewFromRepoControl(preview);
  if (!derived) {
    return;
  }

  for (const [key, value] of Object.entries(derived)) {
    setControlPreviewFallback(preview, key, value);
  }
}

function derivedCompactRuntimeFreshness(preview: TabPreview | undefined): string {
  const explicitFreshness = previewField(preview, "Runtime freshness");
  if (explicitFreshness) {
    return explicitFreshness;
  }
  return parseControlPulsePreview(previewField(preview, "Control pulse preview")).runtimeFreshness ?? "";
}

function derivedCompactLoopState(preview: TabPreview | undefined): string {
  return parseRuntimeFreshness(derivedCompactRuntimeFreshness(preview)).loopState ?? "";
}

function derivedCompactUpdated(preview: TabPreview | undefined): string {
  return parseRuntimeFreshness(derivedCompactRuntimeFreshness(preview)).updated ?? "";
}

function derivedCompactVerificationSummary(preview: TabPreview | undefined): string {
  return parseRuntimeFreshness(derivedCompactRuntimeFreshness(preview)).verificationBundle ?? "";
}

function derivedCompactLastResult(preview: TabPreview | undefined): string {
  return parseControlPulsePreview(previewField(preview, "Control pulse preview")).lastResult ?? "";
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

function repoHotspotPreviewValue(preview: TabPreview | undefined): string {
  const explicitLead = previewField(preview, "Lead hotspot preview");
  if (explicitLead) {
    return explicitLead;
  }

  const primaryChangedHotspot = derivePrimaryChangedHotspot(preview);
  const primaryChangedPath = derivePrimaryChangedPath(preview);
  const primaryDependencyHotspot = derivePrimaryDependencyHotspot(preview);
  const parts = [
    ...(hasPreviewValue(primaryChangedHotspot) && primaryChangedHotspot !== "none"
      ? [`change ${primaryChangedHotspot}`]
      : []),
    ...(hasPreviewValue(primaryChangedPath) && primaryChangedPath !== "none" ? [`path ${primaryChangedPath}`] : []),
    ...(hasPreviewValue(primaryDependencyHotspot) && primaryDependencyHotspot !== "none"
      ? [`dep ${primaryDependencyHotspot}`]
      : []),
  ];
  return parts.join(" | ");
}

function repoTruthPreviewField(preview: TabPreview | undefined): string {
  return previewField(preview, "Repo truth preview");
}

function repoTruthDirtySegment(preview: TabPreview | undefined): string {
  const repoTruth = repoTruthPreviewField(preview);
  if (!hasPreviewValue(repoTruth) || repoTruth === "none") {
    return "";
  }
  return repoTruth.match(/\bdirty\s+(.+?)(?=\s+\|\s+(?:warn|hotspot)\b|$)/i)?.[1]?.trim() ?? "";
}

function repoTruthWarningSegment(preview: TabPreview | undefined): string {
  const repoTruth = repoTruthPreviewField(preview);
  if (!hasPreviewValue(repoTruth) || repoTruth === "none") {
    return "";
  }
  return repoTruth.match(/\bwarn\s+(.+?)(?=\s+\|\s+hotspot\b|$)/i)?.[1]?.trim() ?? "";
}

function repoTruthHotspotSegment(preview: TabPreview | undefined): string {
  const repoTruth = repoTruthPreviewField(preview);
  if (!hasPreviewValue(repoTruth) || repoTruth === "none") {
    return "";
  }
  return repoTruth.match(/\bhotspot\s+(.+)$/i)?.[1]?.trim() ?? "";
}

function repoTruthBranchParts(preview: TabPreview | undefined): {branch: string; head: string} | null {
  const repoTruth = repoTruthPreviewField(preview);
  if (!hasPreviewValue(repoTruth) || repoTruth === "none") {
    return null;
  }
  const match = repoTruth.match(/\bbranch\s+([^\s|@]+)@([^\s|]+)/i);
  if (!match) {
    return null;
  }
  return {branch: match[1]?.trim() ?? "", head: match[2]?.trim() ?? ""};
}

function repoControlBranchParts(preview: TabPreview | undefined): {branch: string; head: string} | null {
  const raw = previewField(preview, "Repo/control preview");
  if (!hasPreviewValue(raw) || raw === "none") {
    return null;
  }
  const match = raw.match(/\bbranch\s+([^\s|@]+)@([^\s|]+)/i);
  if (!match) {
    return null;
  }
  return {branch: match[1]?.trim() ?? "", head: match[2]?.trim() ?? ""};
}

function deriveBranch(preview: TabPreview | undefined): string {
  const explicit = previewField(preview, "Branch");
  if (hasPreviewValue(explicit) && explicit !== "none") {
    return explicit;
  }
  return repoTruthBranchParts(preview)?.branch || repoControlBranchParts(preview)?.branch || explicit;
}

function deriveHead(preview: TabPreview | undefined): string {
  const explicit = previewField(preview, "Head");
  if (hasPreviewValue(explicit) && explicit !== "none") {
    return explicit;
  }
  return repoTruthBranchParts(preview)?.head || repoControlBranchParts(preview)?.head || explicit;
}

function deriveDirtyCountFromRepoTruth(preview: TabPreview | undefined, label: "staged" | "unstaged" | "untracked"): string {
  const explicit = previewField(preview, label.charAt(0).toUpperCase() + label.slice(1));
  if (hasPreviewValue(explicit) && explicit !== "none") {
    return explicit;
  }
  const dirtySegment = repoTruthDirtySegment(preview) || repoControlDirtySegment(preview);
  if (dirtySegment) {
    return dirtySegment.match(new RegExp(`\\b${label}\\s+(\\d+)\\b`, "i"))?.[1] ?? explicit;
  }
  const parsed = parsedRepoControlPreview(preview);
  if (!parsed) {
    return explicit;
  }
  return (
    {
      staged: parsed.staged,
      unstaged: parsed.unstaged,
      untracked: parsed.untracked,
    }[label] ?? explicit
  );
}

function deriveDirty(preview: TabPreview | undefined): string {
  const explicit = previewField(preview, "Dirty");
  if (hasPreviewValue(explicit) && explicit !== "none") {
    return explicit;
  }
  const staged = deriveDirtyCountFromRepoTruth(preview, "staged");
  const unstaged = deriveDirtyCountFromRepoTruth(preview, "unstaged");
  const untracked = deriveDirtyCountFromRepoTruth(preview, "untracked");
  if ([staged, unstaged, untracked].every((value) => value !== "n/a" && value.length > 0)) {
    return `${staged} staged, ${unstaged} unstaged, ${untracked} untracked`;
  }
  return explicit;
}

function repoTruthPreviewValue(preview: TabPreview | undefined): string {
  const explicit = previewField(preview, "Repo truth preview");
  if (explicit) {
    return explicit;
  }
  const branch = deriveBranch(preview) || "n/a";
  const head = deriveHead(preview) || "n/a";
  const staged = deriveDirtyCountFromRepoTruth(preview, "staged");
  const unstaged = deriveDirtyCountFromRepoTruth(preview, "unstaged");
  const untracked = deriveDirtyCountFromRepoTruth(preview, "untracked");
  const dirtyCountsLabel =
    hasPreviewValue(staged) && hasPreviewValue(unstaged) && hasPreviewValue(untracked)
      ? `staged ${staged} | unstaged ${unstaged} | untracked ${untracked}`
      : deriveDirty(preview) || "n/a";
  const warningMembers = topologyWarningMembersValue(preview);
  const hotspotSummary = deriveHotspotSummary(preview) || repoHotspotPreviewValue(preview) || "none";
  return [
    `branch ${branch}@${head}`,
    `dirty ${dirtyCountsLabel}`,
    `warn ${warningMembers.join("; ") || "none"}`,
    `hotspot ${hotspotSummary}`,
  ].join(" | ");
}

function deriveTopologyWarningSeverity(preview: TabPreview): string {
  const explicit = previewField(preview, "Topology warning severity");
  if (explicit) {
    return explicit;
  }
  const primaryWarning = derivePrimaryWarning(preview);
  if (primaryWarning === "none") {
    return "stable";
  }
  const topologyWarnings = previewField(preview, "Topology warnings");
  if (topologyWarnings === "0") {
    return "stable";
  }
  const repoRisk = previewField(preview, "Repo risk");
  const severityMatch = repoRisk.match(/;\s*([a-z]+)\s*(?:\(|$)/i);
  if (severityMatch?.[1]) {
    return severityMatch[1].toLowerCase();
  }
  return explicit;
}

const REPO_CONTROL_SEGMENT_BOUNDARY =
  "(?:warn|peers|peer|drift|markers|divergence|detached|hotspot|path|dep|inbound|dirty|unstaged|untracked|cycle\\s+\\d+|updated\\s+|verify\\s+|db\\s+|activity\\s+|artifacts\\s+|next\\s+)";

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
  const branch = deriveBranch(repoPreview);
  const head = deriveHead(repoPreview);
  const dirtyPressure = previewField(repoPreview, "Dirty pressure");
  const dirtyCompact = deriveDirty(repoPreview);
  const dirtyPreview =
    hasPreviewValue(dirtyPressure) && dirtyPressure !== "clean"
      ? dirtyPressure
      : hasPreviewValue(dirtyCompact) && dirtyCompact !== "none" && dirtyCompact !== "clean"
        ? dirtyCompact
        : "";
  const primaryWarning = derivePrimaryWarning(repoPreview);
  const topologyWarningMembers = topologyWarningMembersValue(repoPreview).join("; ");
  const primaryPeer = derivePrimaryPeer(repoPreview);
  const primaryPeerDrift =
    previewField(repoPreview, "Primary peer drift") || derivePrimaryPeerDrift(primaryPeer, primaryWarning);
  const topologyPressure = previewField(repoPreview, "Topology pressure") || deriveTopologyPressure(repoPreview);
  const topologyPeers = previewField(repoPreview, "Topology peers") || deriveTopologyPeers(repoPreview, primaryPeer);
  const peerDriftMarkers = derivePeerDriftMarkers(repoPreview, primaryPeerDrift, primaryPeer, topologyPressure);
  const branchDivergence = deriveBranchDivergence(
    repoPreview,
    primaryPeerDrift,
  );
  const detachedPeers = deriveDetachedPeers(
    repoPreview,
    topologyPeers,
    primaryPeerDrift,
  );
  const hotspotPreview = repoHotspotPreviewValue(repoPreview);
  const taskProgress = previewField(controlPreview, "Task progress");
  const resultStatus = previewField(controlPreview, "Result status");
  const acceptance = previewField(controlPreview, "Acceptance");
  const loopDecision = previewField(controlPreview, "Loop decision");
  const nextTask = previewField(controlPreview, "Next task");
  const runtimeDb = previewField(controlPreview, "Runtime DB");
  const runtimeActivity = previewField(controlPreview, "Runtime activity");
  const artifactState = previewField(controlPreview, "Artifact state");
  return [
    controlPulsePrefix(controlPreview, now),
    ...(activeTask ? [`task ${activeTask}`] : []),
    ...(hasPreviewValue(taskProgress) && taskProgress !== "none" ? [`progress ${taskProgress}`] : []),
    ...(hasPreviewValue(resultStatus) && hasPreviewValue(acceptance) ? [`outcome ${resultStatus}/${acceptance}`] : []),
    ...(hasPreviewValue(loopDecision) && loopDecision !== "none" ? [`decision ${loopDecision}`] : []),
    ...(hasPreviewValue(branch) && hasPreviewValue(head) ? [`branch ${branch}@${head}`] : []),
    repoRiskPreviewValue(repoPreview),
    ...(dirtyPreview ? [`dirty ${dirtyPreview}`] : []),
    ...(hasPreviewValue(topologyWarningMembers) ? [`warn ${topologyWarningMembers}`] : []),
    ...(hasPreviewValue(primaryPeer) && primaryPeer !== "none" ? [`peer ${primaryPeer}`] : []),
    ...(hasPreviewValue(topologyPeers) && topologyPeers !== "none" ? [`peers ${topologyPeers}`] : []),
    ...(hasPreviewValue(primaryPeerDrift) && primaryPeerDrift !== "none" ? [`drift ${primaryPeerDrift}`] : []),
    ...(hasPreviewValue(peerDriftMarkers) && peerDriftMarkers !== "none" ? [`markers ${peerDriftMarkers}`] : []),
    ...(hasPreviewValue(branchDivergence) && branchDivergence !== "n/a" ? [`divergence ${branchDivergence}`] : []),
    ...(hasPreviewValue(detachedPeers) && detachedPeers !== "none" ? [`detached ${detachedPeers}`] : []),
    ...(hasPreviewValue(hotspotPreview) ? [`hotspot ${hotspotPreview}`] : []),
    runtimeFreshness,
    ...(hasPreviewValue(runtimeDb) ? [`db ${runtimeDb}`] : []),
    ...(hasPreviewValue(runtimeActivity) ? [`activity ${runtimeActivity}`] : []),
    ...(hasPreviewValue(artifactState) ? [`artifacts ${artifactState}`] : []),
    ...(hasPreviewValue(nextTask) && nextTask !== "none" ? [`next ${nextTask}`] : []),
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

function splitPreviewPipes(value: string): string[] {
  return value
    .split("|")
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

function repoControlPreviewValue(preview: TabPreview | undefined): string {
  return previewField(preview, "Repo/control preview");
}

function parsedRepoControlPreview(preview: TabPreview | undefined) {
  return parseRepoControlPreview(repoControlPreviewValue(preview));
}

function repoControlSegment(
  preview: TabPreview | undefined,
  key: "warn" | "peer" | "peers" | "drift" | "markers" | "divergence" | "detached",
): string {
  const raw = repoControlPreviewValue(preview);
  if (!hasPreviewValue(raw) || raw === "none") {
    return "";
  }
  const escapedKey = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = raw.match(
    new RegExp(
      `\\b${escapedKey}\\s+(.+?)(?=\\s+\\|\\s+${REPO_CONTROL_SEGMENT_BOUNDARY}|$)`,
      "i",
    ),
  );
  return match?.[1]?.trim() ?? "";
}

function repoControlDirtySegment(preview: TabPreview | undefined): string {
  return parsedRepoControlPreview(preview)?.dirtyState ?? "";
}

function repoControlHotspotSegment(preview: TabPreview | undefined, key: "hotspot" | "path" | "dep"): string {
  const parsed = parsedRepoControlPreview(preview);
  if (!parsed) {
    return "";
  }
  if (key === "hotspot") {
    return parsed.primaryHotspot === "n/a" ? "" : parsed.primaryHotspot;
  }
  if (key === "path") {
    return parsed.hotspotPath === "n/a" ? "" : parsed.hotspotPath;
  }
  return parsed.hotspotDependency === "n/a" ? "" : parsed.hotspotDependency;
}

function firstDelimitedSegment(value: string): string {
  if (!hasPreviewValue(value) || value === "none") {
    return value;
  }
  return (
    value
      .split(/[;,]/)
      .map((segment) => segment.trim())
      .find((segment) => segment.length > 0) || value
  );
}

function splitWarningMembers(value: string): string[] {
  if (!hasPreviewValue(value) || value === "none") {
    return [];
  }
  const countedMembers = value.match(/^\d+\s*\((.+)\)$/)?.[1]?.trim();
  return (countedMembers || value)
    .split(/[;,]/)
    .map((segment) => segment.trim())
    .filter((segment) => segment.length > 0);
}

function isPeerSummary(value: string): boolean {
  return /\(.+,\s*.+,\s*dirty\s+.+\)$/i.test(value);
}

function deriveWarningFromPreviewSegments(value: string): string {
  if (!hasPreviewValue(value) || value === "none") {
    return "";
  }
  return (
    splitPreviewPipes(value).find((segment) => {
      const normalized = segment.toLowerCase();
      return (
        normalized !== "stable" &&
        normalized !== "none" &&
        !isPeerSummary(segment) &&
        !segment.includes("Δ") &&
        !/\bclean\b/i.test(segment) &&
        !/^\d+\s+warning(?:s)?\b/i.test(segment) &&
        !/^(?:tracking\b|ahead\b|behind\b|local\b|\+\d+\/-\d+)/i.test(segment)
      );
    }) || ""
  );
}

function normalizePrimaryWarning(value: string): string {
  if (!hasPreviewValue(value) || value === "none") {
    return "";
  }
  const members = value.match(/^\d+\s*\((.+)\)$/)?.[1]?.trim();
  return firstDelimitedSegment(members || value);
}

function derivePrimaryWarning(preview: TabPreview): string {
  const explicit = previewField(preview, "Primary warning");
  if (hasPreviewValue(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = normalizePrimaryWarning(repoControlSegment(preview, "warn"));
  if (hasPreviewValue(fromRepoControl) && fromRepoControl !== "none") {
    return fromRepoControl;
  }
  const warningFromTruth = repoTruthWarningSegment(preview);
  if (hasPreviewValue(warningFromTruth) && warningFromTruth !== "none") {
    return firstDelimitedSegment(warningFromTruth);
  }
  const previewWarning = [
    previewField(preview, "Topology preview"),
    previewField(preview, "Risk preview"),
    previewField(preview, "Repo risk preview"),
  ].find((candidate) => {
    const derived = deriveWarningFromPreviewSegments(candidate);
    return hasPreviewValue(derived) && derived !== "none";
  });
  if (previewWarning) {
    return deriveWarningFromPreviewSegments(previewWarning);
  }
  const topologyRisk = previewField(preview, "Topology risk");
  if (hasPreviewValue(topologyRisk) && topologyRisk !== "stable" && topologyRisk !== "none") {
    return topologyRisk;
  }
  return explicit || topologyRisk || "";
}

function topologyWarningMembersValue(preview: TabPreview | undefined): string[] {
  const explicitMembers = splitWarningMembers(previewField(preview, "Topology warning members"));
  if (explicitMembers.length > 0) {
    return explicitMembers;
  }
  const explicitWarnings = splitWarningMembers(previewField(preview, "Topology warnings"));
  if (explicitWarnings.length > 0) {
    return explicitWarnings;
  }
  const repoControlWarnings = splitWarningMembers(repoControlSegment(preview, "warn"));
  if (repoControlWarnings.length > 0) {
    return repoControlWarnings;
  }
  const truthWarnings = splitWarningMembers(repoTruthWarningSegment(preview));
  if (truthWarnings.length > 0) {
    return truthWarnings;
  }
  return [];
}

function deriveTopologyWarnings(preview: TabPreview): string {
  const explicit = previewField(preview, "Topology warnings");
  if (hasPreviewValue(explicit) && explicit !== "none") {
    return explicit;
  }
  const members = topologyWarningMembersValue(preview);
  if (members.length > 0) {
    return `${members.length} (${members.join(", ")})`;
  }
  const primaryWarning = derivePrimaryWarning(preview);
  if (hasPreviewValue(primaryWarning) && primaryWarning !== "none") {
    return `1 (${primaryWarning})`;
  }
  return explicit;
}

function derivePrimaryPeer(preview: TabPreview): string {
  const explicit = previewField(preview, "Primary topology peer");
  if (hasPreviewValue(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = repoControlSegment(preview, "peer");
  if (hasPreviewValue(fromRepoControl) && fromRepoControl !== "none") {
    return fromRepoControl;
  }
  return (
    [
      previewField(preview, "Topology preview"),
      previewField(preview, "Risk preview"),
      previewField(preview, "Repo risk preview"),
    ]
      .flatMap((candidate) => splitPreviewPipes(candidate))
      .find((segment) => isPeerSummary(segment)) || explicit
  );
}

function derivePrimaryPeerDrift(primaryPeer: string, primaryWarning: string): string {
  const match = primaryPeer.match(/^(.+?)\s+\([^,]+,\s*([^,]+),\s*dirty\s+.+\)$/i);
  if (!match) {
    return "none";
  }
  const [, rawName, rawBranch] = match;
  const name = rawName.trim();
  const branch = rawBranch.trim();
  if (!name) {
    return "none";
  }
  if (branch === "n/a") {
    return `${name} n/a`;
  }
  if (/detached/i.test(branch)) {
    return `${name} detached`;
  }
  if (branch.includes("...")) {
    const hasBranchDrift = /peer_branch_diverged/i.test(primaryWarning);
    return `${name} ${hasBranchDrift ? "drift" : "track"} ${branch}`;
  }
  return `${name} branch ${branch}`;
}

function derivePeerNamesFromPressure(pressure: string): string[] {
  if (!hasPreviewValue(pressure) || pressure === "none") {
    return [];
  }
  return pressure
    .split(";")
    .map((part) => part.trim())
    .map((part) => part.match(/^([^;]+?)\s+(?:Δ\d+|\bclean\b)/i)?.[1]?.trim() || "")
    .filter((name) => name.length > 0);
}

function deriveTopologyPeers(preview: TabPreview, primaryPeer: string): string {
  const explicit = previewField(preview, "Topology peers");
  if (hasPreviewValue(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = repoControlSegment(preview, "peers");
  if (hasPreviewValue(fromRepoControl) && fromRepoControl !== "none") {
    return fromRepoControl;
  }
  if (hasPreviewValue(primaryPeer) && primaryPeer !== "none") {
    return primaryPeer;
  }
  return explicit;
}

function deriveTopologyPressure(preview: TabPreview): string {
  const explicit = previewField(preview, "Topology pressure");
  if (hasPreviewValue(explicit) && explicit !== "none") {
    return explicit;
  }
  const candidates = [previewField(preview, "Topology pressure preview"), previewField(preview, "Topology preview")];
  for (const candidate of candidates) {
    const segments = splitPreviewPipes(candidate).filter((segment) => segment.includes("Δ") || /\bclean\b/i.test(segment));
    if (segments.length > 0) {
      return segments.join("; ");
    }
  }
  return explicit;
}

function deriveTopologyPeerCount(preview: TabPreview, topologyPeers: string, topologyPressure: string): string {
  const explicit = previewField(preview, "Topology peer count");
  if (hasPreviewValue(explicit)) {
    return explicit;
  }
  if (/^\d+$/.test(topologyPeers.trim())) {
    return topologyPeers.trim();
  }
  const topologyStatus = previewField(preview, "Topology status");
  const statusCount = topologyStatus.match(/\((?:\d+\s+warning(?:s)?(?:,\s*)?)?(\d+)\s+peer(?:s)?\)/i)?.[1];
  if (statusCount) {
    return statusCount;
  }
  const pressureCount = derivePeerNamesFromPressure(topologyPressure).length;
  if (pressureCount > 0) {
    return String(pressureCount);
  }
  if (hasPreviewValue(topologyPeers) && topologyPeers !== "none") {
    return String(
      topologyPeers
        .split(";")
        .map((part) => part.trim())
        .filter((part) => part.length > 0).length,
    );
  }
  return explicit;
}

function derivePeerDriftMarkers(
  preview: TabPreview,
  primaryPeerDrift: string,
  primaryPeer: string,
  topologyPressure: string,
): string {
  const explicit = previewField(preview, "Peer drift markers");
  if (hasPreviewValue(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = repoControlSegment(preview, "markers");
  if (hasPreviewValue(fromRepoControl) && fromRepoControl !== "none") {
    return fromRepoControl;
  }
  const primaryPeerName = primaryPeer.match(/^(.+?)\s+\(/)?.[1]?.trim() || "";
  const extras = derivePeerNamesFromPressure(topologyPressure)
    .filter((name) => name !== primaryPeerName)
    .map((name) => `${name} n/a`);
  return [primaryPeerDrift, ...extras].filter((value) => hasPreviewValue(value) && value !== "none").join("; ");
}

function deriveBranchDivergence(preview: TabPreview, primaryPeerDrift: string): string {
  const explicit = previewField(preview, "Branch divergence");
  if (explicit) {
    return explicit;
  }
  const fromRepoControl = repoControlSegment(preview, "divergence");
  if (hasPreviewValue(fromRepoControl)) {
    return fromRepoControl;
  }
  const ahead = previewField(preview, "Ahead");
  const behind = previewField(preview, "Behind");
  const parts: string[] = [];
  if (hasPreviewValue(ahead) || hasPreviewValue(behind)) {
    parts.push(`local +${ahead || "n/a"}/-${behind || "n/a"}`);
  }
  if (hasPreviewValue(primaryPeerDrift) && primaryPeerDrift !== "none") {
    parts.push(`peer ${primaryPeerDrift}`);
  }
  return parts.join(" | ") || "n/a";
}

function deriveDetachedPeers(preview: TabPreview, topologyPeers: string, primaryPeerDrift: string): string {
  const explicit = previewField(preview, "Detached peers");
  if (explicit) {
    return explicit;
  }
  const fromRepoControl = repoControlSegment(preview, "detached");
  if (hasPreviewValue(fromRepoControl)) {
    return fromRepoControl;
  }
  const detached = Array.from(
    new Set(
      topologyPeers
        .split(";")
        .map((part) => part.trim())
        .map((peer) => peer.match(/^(.+?)\s+\([^,]+,\s*([^,]+),\s*dirty\s+.+\)$/i))
        .filter((match): match is RegExpMatchArray => Boolean(match))
        .filter((match) => /detached/i.test(match[2] ?? ""))
        .map((match) => `${match[1]?.trim() ?? "peer"} detached`),
    ),
  );
  if (detached.length > 0) {
    return detached.join("; ");
  }
  return /detached/i.test(primaryPeerDrift) ? primaryPeerDrift : "none";
}

function deriveHotspotMatch(value: string, patterns: RegExp[]): string {
  for (const pattern of patterns) {
    const match = value.match(pattern)?.[1]?.trim();
    if (match) {
      return match;
    }
  }
  return "";
}

function normalizeChangedHotspotLabel(value: string): string {
  return value.replace(/^change\s+/i, "").trim();
}

function derivePrimaryChangedHotspot(preview: TabPreview | undefined): string {
  const explicit = previewField(preview, "Primary changed hotspot");
  if (hasPreviewValue(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = repoControlHotspotSegment(preview, "hotspot");
  if (hasPreviewValue(fromRepoControl) && fromRepoControl !== "none") {
    return normalizeChangedHotspotLabel(fromRepoControl);
  }
  const candidates = [
    repoTruthHotspotSegment(preview),
    previewField(preview, "Lead hotspot preview"),
    previewField(preview, "Hotspot pressure preview"),
    previewField(preview, "Hotspot summary"),
  ];
  for (const candidate of candidates) {
    const derived = deriveHotspotMatch(candidate, [/(?:^|\|\s*|;\s*)change\s+([^|;]+?)(?=\s*(?:\||;|$))/i]);
    if (derived) {
      return derived;
    }
  }
  const changedHotspots = firstDelimitedSegment(previewField(preview, "Changed hotspots"));
  if (hasPreviewValue(changedHotspots) && changedHotspots !== "none") {
    return normalizeChangedHotspotLabel(changedHotspots);
  }
  return explicit;
}

function derivePrimaryChangedPath(preview: TabPreview | undefined): string {
  const explicit = previewField(preview, "Primary changed path");
  if (hasPreviewValue(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = repoControlHotspotSegment(preview, "path");
  if (hasPreviewValue(fromRepoControl) && fromRepoControl !== "none") {
    return fromRepoControl;
  }
  const candidates = [
    repoTruthHotspotSegment(preview),
    previewField(preview, "Lead hotspot preview"),
    previewField(preview, "Hotspot summary"),
  ];
  for (const candidate of candidates) {
    const derived = deriveHotspotMatch(candidate, [
      /(?:^|\|\s*)path\s+([^|;]+?)(?=\s*(?:\||;|$))/i,
      /(?:^|\|\s*)paths\s+([^|;]+?)(?=\s*(?:\||;|$))/i,
    ]);
    if (derived) {
      return derived;
    }
  }
  const changedPath = firstDelimitedSegment(previewField(preview, "Changed paths"));
  if (hasPreviewValue(changedPath) && changedPath !== "none") {
    return changedPath;
  }
  return explicit;
}

function derivePrimaryDependencyHotspot(preview: TabPreview | undefined): string {
  const explicit = previewField(preview, "Primary dependency hotspot");
  if (hasPreviewValue(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = repoControlHotspotSegment(preview, "dep");
  if (hasPreviewValue(fromRepoControl) && fromRepoControl !== "none") {
    const inbound = parsedRepoControlPreview(preview)?.hotspotInbound ?? "";
    return inbound && inbound !== "n/a" ? `${fromRepoControl} | inbound ${inbound}` : fromRepoControl;
  }
  const candidates = [
    repoTruthHotspotSegment(preview),
    previewField(preview, "Lead hotspot preview"),
    previewField(preview, "Hotspot pressure preview"),
    previewField(preview, "Hotspot summary"),
  ];
  for (const candidate of candidates) {
    const derived = deriveHotspotMatch(candidate, [
      /(?:^|\|\s*)dep\s+([^|]+?)(?:\s*\|\s*inbound\s+\d+)?(?=\s*(?:\||$))/i,
      /(?:^|\|\s*)deps\s+([^|;]+?)(?:\s*\|\s*inbound\s+\d+)?(?=\s*(?:\||;|$))/i,
    ]);
    if (derived) {
      const inbound = candidate.match(/(?:^|\|\s*)inbound\s+(\d+)(?=\s*(?:\||$))/i)?.[1];
      return inbound && !/\|\s*inbound\s+\d+$/i.test(derived) ? `${derived} | inbound ${inbound}` : derived;
    }
  }
  const inboundHotspot = firstDelimitedSegment(previewField(preview, "Inbound hotspots"));
  if (hasPreviewValue(inboundHotspot) && inboundHotspot !== "none") {
    return inboundHotspot;
  }
  return explicit;
}

function deriveHotspotSummary(preview: TabPreview | undefined): string {
  const explicit = previewField(preview, "Hotspot summary");
  if (hasPreviewValue(explicit) && explicit !== "none") {
    return explicit;
  }
  const truthHotspot = repoTruthHotspotSegment(preview);
  if (hasPreviewValue(truthHotspot) && truthHotspot !== "none") {
    return truthHotspot;
  }
  const candidates = [previewField(preview, "Lead hotspot preview"), previewField(preview, "Hotspot pressure preview")];
  for (const candidate of candidates) {
    if (hasPreviewValue(candidate) && candidate !== "none") {
      return candidate;
    }
  }
  const primaryParts: string[] = [];
  const primaryChange = derivePrimaryChangedHotspot(preview);
  if (hasPreviewValue(primaryChange) && primaryChange !== "none") {
    primaryParts.push(`change ${primaryChange}`);
  }
  const primaryPath = derivePrimaryChangedPath(preview);
  if (hasPreviewValue(primaryPath) && primaryPath !== "none") {
    primaryParts.push(`path ${primaryPath}`);
  }
  const primaryDependency = derivePrimaryDependencyHotspot(preview);
  if (hasPreviewValue(primaryDependency) && primaryDependency !== "none") {
    primaryParts.push(`dep ${primaryDependency}`);
  }
  if (primaryParts.length > 0) {
    return primaryParts.join(" | ");
  }
  return explicit;
}

function deriveRepoPreviewFields(preview: TabPreview, controlPreview?: TabPreview, now: Date = new Date()): TabPreview {
  const branch = deriveBranch(preview);
  const head = deriveHead(preview);
  const dirty = deriveDirty(preview);
  const staged = deriveDirtyCountFromRepoTruth(preview, "staged");
  const unstaged = deriveDirtyCountFromRepoTruth(preview, "unstaged");
  const untracked = deriveDirtyCountFromRepoTruth(preview, "untracked");
  const branchStatus = previewField(preview, "Branch status");
  const ahead = previewField(preview, "Ahead");
  const behind = previewField(preview, "Behind");
  const topologyRisk = previewField(preview, "Topology risk");
  const dirtyPressure = previewField(preview, "Dirty pressure");
  const primaryWarning = derivePrimaryWarning(preview);
  const primaryPeer = derivePrimaryPeer(preview);
  const primaryPeerDrift =
    previewField(preview, "Primary peer drift") || repoControlSegment(preview, "drift") || derivePrimaryPeerDrift(primaryPeer, primaryWarning);
  const topologyPressure = deriveTopologyPressure(preview);
  const topologyPeers = deriveTopologyPeers(preview, primaryPeer);
  const topologyPeerCount = deriveTopologyPeerCount(preview, topologyPeers, topologyPressure);
  const peerDriftMarkers = derivePeerDriftMarkers(preview, primaryPeerDrift, primaryPeer, topologyPressure);
  const branchDivergence = deriveBranchDivergence(preview, primaryPeerDrift);
  const detachedPeers = deriveDetachedPeers(preview, topologyPeers, primaryPeerDrift);
  const primaryChangedHotspot = derivePrimaryChangedHotspot(preview);
  const primaryChangedPath = derivePrimaryChangedPath(preview);
  const primaryDependencyHotspot = derivePrimaryDependencyHotspot(preview);
  const hotspotSummary = deriveHotspotSummary(preview);
  const topologyWarnings = deriveTopologyWarnings(preview);

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

  const topologyWarningSeverity = deriveTopologyWarningSeverity({
    ...preview,
    ...(primaryWarning ? {"Primary warning": primaryWarning} : {}),
    ...(repoRisk ? {"Repo risk": repoRisk} : {}),
  });

  const enrichedPreview = {
    ...preview,
    ...(hasPreviewValue(branch) && branch !== "none" ? {Branch: branch} : {}),
    ...(hasPreviewValue(head) && head !== "none" ? {Head: head} : {}),
    ...(hasPreviewValue(dirty) && dirty !== "none" ? {Dirty: dirty} : {}),
    ...(hasPreviewValue(staged) && staged !== "none" ? {Staged: staged} : {}),
    ...(hasPreviewValue(unstaged) && unstaged !== "none" ? {Unstaged: unstaged} : {}),
    ...(hasPreviewValue(untracked) && untracked !== "none" ? {Untracked: untracked} : {}),
    ...(riskPreview ? {"Risk preview": riskPreview} : {}),
    ...(repoRisk ? {"Repo risk": repoRisk} : {}),
    ...(topologyPreview ? {"Topology preview": topologyPreview} : {}),
    ...(topologyPressurePreview ? {"Topology pressure preview": topologyPressurePreview} : {}),
    ...(hasPreviewValue(topologyWarnings) && topologyWarnings !== "none" ? {"Topology warnings": topologyWarnings} : {}),
    ...(primaryWarning ? {"Primary warning": primaryWarning} : {}),
    ...(hasPreviewValue(primaryPeerDrift) && primaryPeerDrift !== "none" ? {"Primary peer drift": primaryPeerDrift} : {}),
    ...(branchDivergence ? {"Branch divergence": branchDivergence} : {}),
    ...(detachedPeers ? {"Detached peers": detachedPeers} : {}),
    ...(hasPreviewValue(primaryPeer) && primaryPeer !== "none" ? {"Primary topology peer": primaryPeer} : {}),
    ...(topologyPeerCount ? {"Topology peer count": topologyPeerCount} : {}),
    ...(topologyWarningSeverity ? {"Topology warning severity": topologyWarningSeverity} : {}),
    ...(hasPreviewValue(peerDriftMarkers) && peerDriftMarkers !== "none" ? {"Peer drift markers": peerDriftMarkers} : {}),
    ...(hasPreviewValue(topologyPeers) && topologyPeers !== "none" ? {"Topology peers": topologyPeers} : {}),
    ...(hasPreviewValue(topologyPressure) && topologyPressure !== "none" ? {"Topology pressure": topologyPressure} : {}),
    ...(hasPreviewValue(primaryChangedHotspot) && primaryChangedHotspot !== "none"
      ? {"Primary changed hotspot": primaryChangedHotspot}
      : {}),
    ...(hasPreviewValue(primaryChangedPath) && primaryChangedPath !== "none" ? {"Primary changed path": primaryChangedPath} : {}),
    ...(hasPreviewValue(primaryDependencyHotspot) && primaryDependencyHotspot !== "none"
      ? {"Primary dependency hotspot": primaryDependencyHotspot}
      : {}),
    ...(hasPreviewValue(hotspotSummary) && hotspotSummary !== "none" ? {"Hotspot summary": hotspotSummary} : {}),
    ...(leadHotspotPreview ? {"Lead hotspot preview": leadHotspotPreview} : {}),
    ...(hotspotPressurePreview ? {"Hotspot pressure preview": hotspotPressurePreview} : {}),
    ...(repoRiskPreview ? {"Repo risk preview": repoRiskPreview} : {}),
    ...(repoTruthPreviewValue(preview) ? {"Repo truth preview": repoTruthPreviewValue(preview)} : {}),
    ...(branchSyncPreview ? {"Branch sync preview": branchSyncPreview} : {}),
  };

  const repoControlPreview =
    previewField(preview, "Repo/control preview") || buildRepoControlPreview(enrichedPreview, controlPreview, now);

  return {
    ...enrichedPreview,
    ...(repoControlPreview ? {"Repo/control preview": repoControlPreview} : {}),
  };
}

export function normalizeRepoPreview(preview: TabPreview | undefined, controlPreview?: TabPreview, now: Date = new Date()): TabPreview | undefined {
  if (!preview) {
    const controlRepoPreview = previewField(controlPreview, "Repo/control preview");
    if (!controlRepoPreview) {
      return undefined;
    }
    return deriveRepoPreviewFields({"Repo/control preview": controlRepoPreview}, controlPreview, now);
  }
  const controlRepoPreview = previewField(controlPreview, "Repo/control preview");
  const effectivePreview =
    controlRepoPreview && !previewField(preview, "Repo/control preview")
      ? {
          ...preview,
          "Repo/control preview": controlRepoPreview,
        }
      : preview;
  return deriveRepoPreviewFields(effectivePreview, controlPreview, now);
}

function previewStorageKey(key: string): string {
  return `preview_${key.replaceAll(" ", "_")}`;
}

function storedSnapshotPayloadKey(kind: "workspace" | "runtime"): "workspace_payload" | "runtime_payload" {
  return kind === "workspace" ? "workspace_payload" : "runtime_payload";
}

function snapshotPayloadFromRecord(
  record: Record<string, unknown>,
  kind: "workspace" | "runtime",
): WorkspaceSnapshotPayload | RuntimeSnapshotPayload | undefined {
  const key = storedSnapshotPayloadKey(kind);
  const payloadRecord = asRecord(record[key]);
  if (Object.keys(payloadRecord).length === 0) {
    return undefined;
  }
  if (kind === "workspace") {
    return workspaceSnapshotPayloadFromEvent({workspace_payload: payloadRecord});
  }
  return runtimeSnapshotPayloadFromEvent({runtime_payload: payloadRecord});
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

function readStoredSnapshotPayload(
  summaryPath: string,
  kind: "workspace" | "runtime",
): WorkspaceSnapshotPayload | RuntimeSnapshotPayload | undefined {
  return snapshotPayloadFromRecord(readJsonFile(summaryPath), kind);
}

function previewFromRecord(record: Record<string, unknown>, allowedKeys: readonly string[]): TabPreview | null {
  const previewEntries = allowedKeys
    .map((key) => [key, record[key]] as const)
    .filter((entry): entry is [string, string] => typeof entry[1] === "string" && entry[1].trim().length > 0);
  if (previewEntries.length === 0) {
    return null;
  }
  return Object.fromEntries(previewEntries);
}

function previewRecord(preview: TabPreview | undefined, allowedKeys: readonly string[]): Record<string, string> {
  return Object.fromEntries(
    allowedKeys
      .map((key) => [key, previewField(preview, key)] as const)
      .filter((entry): entry is [string, string] => entry[1].length > 0),
  );
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

function writeStoredSnapshotPayload(
  summary: SupervisorControlState,
  kind: "workspace" | "runtime",
  payloadValue: WorkspaceSnapshotPayload | RuntimeSnapshotPayload | undefined,
): void {
  if (!payloadValue) {
    return;
  }
  const summaryPath = path.join(summary.stateDir, CONTROL_SUMMARY_FILENAME);
  const payload = readJsonFile(summaryPath);
  payload[storedSnapshotPayloadKey(kind)] = payloadValue;
  payload.ts = new Date().toISOString();
  mkdirSync(summary.stateDir, {recursive: true});
  writeFileSync(summaryPath, JSON.stringify(payload, null, 2) + "\n");
}

function writeRunSnapshotPayload(
  summary: SupervisorControlState,
  kind: "workspace" | "runtime",
  payloadValue: WorkspaceSnapshotPayload | RuntimeSnapshotPayload | undefined,
): void {
  if (!payloadValue) {
    return;
  }
  const runPath = path.join(summary.stateDir, "run.json");
  const payload = readJsonFile(runPath);
  payload[storedSnapshotPayloadKey(kind)] = payloadValue;
  payload.ts = new Date().toISOString();
  mkdirSync(summary.stateDir, {recursive: true});
  writeFileSync(runPath, JSON.stringify(payload, null, 2) + "\n");
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
  verificationUpdatedAt: string,
  preview?: TabPreview,
): void {
  const verificationPath = path.join(summary.stateDir, "verification.json");
  const existingPayload = readJsonFile(verificationPath);
  const effectiveSummary =
    verificationSummary || (typeof existingPayload.summary === "string" ? String(existingPayload.summary) : "") || "none";
  const verificationRows = buildVerificationSummaryRows(verificationBundle);
  const payload: Record<string, unknown> = {
    ...existingPayload,
    ts: new Date().toISOString(),
    summary: effectiveSummary,
    checks: mergeVerificationChecks(existingPayload.checks, verificationBundle),
    status: verificationRows.status,
    passing: verificationRows.passing,
    failing: verificationRows.failing,
    bundle: verificationRows.bundle,
    ...(preview ? {control_preview: previewRecord(preview, CONTROL_PREVIEW_FIELDS)} : {}),
    ...(verificationUpdatedAt ? {updated_at: verificationUpdatedAt} : {}),
  };

  if (summary.continueRequired !== null) {
    payload.continue_required = summary.continueRequired;
  } else if (typeof existingPayload.continue_required !== "boolean") {
    payload.continue_required = false;
  }

  mkdirSync(summary.stateDir, {recursive: true});
  writeFileSync(verificationPath, JSON.stringify(payload, null, 2) + "\n");
}

function writeRunVerificationSummaryFile(
  summary: SupervisorControlState,
  verificationSummary: string,
  verificationBundle: VerificationEntry[],
  verificationUpdatedAt: string,
  preview?: TabPreview,
  options?: PersistedSnapshotOptions,
): void {
  const runPath = path.join(summary.stateDir, "run.json");
  const existingPayload = readJsonFile(runPath);
  const checks = verificationBundle.map((entry) => ({name: entry.name, ok: entry.ok}));
  const verificationRows = buildVerificationSummaryRows(verificationBundle);
  const nextSummaryFields = {
    ...asRecord(existingPayload.last_summary_fields),
    ...(summary.lastResultStatus ? {status: summary.lastResultStatus} : {}),
    ...(summary.acceptance ? {acceptance: summary.acceptance} : {}),
    ...(summary.nextTask ? {next_task: summary.nextTask} : {}),
  };
  const payload: Record<string, unknown> = {
    ...existingPayload,
    ts: new Date().toISOString(),
    ...(summary.updatedAt ? {updated_at: summary.updatedAt} : {}),
    ...(summary.cycle !== null ? {cycle: summary.cycle} : {}),
    ...(summary.runStatus ? {status: summary.runStatus} : {}),
    ...(summary.tasksTotal !== null ? {tasks_total: summary.tasksTotal} : {}),
    ...(summary.tasksPending !== null ? {tasks_pending: summary.tasksPending} : {}),
    ...(summary.activeTaskId ? {last_task_id: summary.activeTaskId} : {}),
    ...(Object.keys(nextSummaryFields).length > 0 ? {last_summary_fields: nextSummaryFields} : {}),
    ...(summary.continueRequired !== null ? {last_continue_required: summary.continueRequired} : {}),
    ...(preview ? {last_control_preview: previewRecord(preview, CONTROL_PREVIEW_FIELDS)} : {}),
    ...(options?.workspacePayload ? {workspace_payload: options.workspacePayload} : {}),
    ...(options?.runtimePayload ? {runtime_payload: options.runtimePayload} : {}),
    last_verification: {
      ts: new Date().toISOString(),
      summary: verificationSummary || "none",
      checks,
      status: previewField(preview, "Verification status") || verificationRows.status,
      passing: previewField(preview, "Verification passing") || verificationRows.passing,
      failing: previewField(preview, "Verification failing") || verificationRows.failing,
      bundle: previewField(preview, "Verification bundle") || verificationBundleLabel(verificationBundle),
      ...(verificationUpdatedAt ? {updated_at: verificationUpdatedAt} : {}),
      ...(summary.continueRequired !== null ? {continue_required: summary.continueRequired} : {}),
    },
  };

  mkdirSync(summary.stateDir, {recursive: true});
  writeFileSync(runPath, JSON.stringify(payload, null, 2) + "\n");
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
  const verificationUpdatedAt =
    typeof verification.updated_at === "string"
      ? verification.updated_at
      : typeof verification.ts === "string"
        ? verification.ts
      : typeof lastVerification.updated_at === "string"
        ? lastVerification.updated_at
      : typeof lastVerification.ts === "string"
        ? lastVerification.ts
        : "";

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
    verificationStatus: recordField(verification, "status") || recordField(lastVerification, "status"),
    verificationPassing: recordField(verification, "passing") || recordField(lastVerification, "passing"),
    verificationFailing: recordField(verification, "failing") || recordField(lastVerification, "failing"),
    verificationBundle: recordField(verification, "bundle") || recordField(lastVerification, "bundle"),
    verificationUpdatedAt,
    continueRequired:
      typeof run.last_continue_required === "boolean"
        ? run.last_continue_required
        : typeof verification.continue_required === "boolean"
          ? verification.continue_required
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
  const runPayload = readJsonFile(path.join(summary.stateDir, "run.json"));
  const runPreview = previewFromRecord(asRecord(runPayload.last_control_preview), CONTROL_PREVIEW_FIELDS);
  const runRuntimePayload = snapshotPayloadFromRecord(runPayload, "runtime");
  const verificationPayload = readJsonFile(path.join(summary.stateDir, "verification.json"));
  const verificationPreview = previewFromRecord(asRecord(verificationPayload.control_preview), CONTROL_PREVIEW_FIELDS);

  const verificationRows = buildVerificationSummaryRows(
    resolveVerificationEntries({
      checksText: summary.verificationChecks.join("; "),
      summaryText: summary.verificationSummary || "none",
      bundleText: summary.verificationBundle,
      passingText: summary.verificationPassing,
      failingText: summary.verificationFailing,
    }),
  );
  const verificationStatus = summary.verificationStatus || verificationRows.status;
  const verificationPassing = summary.verificationPassing || verificationRows.passing;
  const verificationFailing = summary.verificationFailing || verificationRows.failing;
  const verificationBundle = summary.verificationBundle || verificationBundleLabel(
    summary.verificationChecks.map((entry) => {
      const [name, status = "fail"] = entry.split(/\s+/);
      return {name, ok: status.toLowerCase() === "ok"};
    }),
  );
  const verificationReceiptPath = defaultVerificationReceiptPath(undefined, summary.stateDir);
  const summaryPath = path.join(summary.stateDir, CONTROL_SUMMARY_FILENAME);
  const runtimePayloadPreview = (() => {
    const payload = readStoredSnapshotPayload(summaryPath, "runtime");
    return payload ? runtimePayloadToPreview(payload as RuntimeSnapshotPayload, summary, now) : undefined;
  })();
  const runRuntimePayloadPreview = runRuntimePayload
    ? runtimePayloadToPreview(runRuntimePayload as RuntimeSnapshotPayload, summary, now)
    : undefined;

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
    "Verification status": verificationStatus,
    "Verification passing": verificationPassing,
    "Verification failing": verificationFailing,
    "Verification bundle": verificationBundle,
    "Verification receipt": verificationReceiptPath,
    "Loop decision":
      summary.continueRequired === null ? "unknown" : summary.continueRequired ? "continue required" : "ready to stop",
    "Next task": summary.nextTask || "none",
    "Verification updated": summary.verificationUpdatedAt || summary.updatedAt || "unknown",
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
  fallbackPreview["Control truth preview"] = buildControlTruthPreview(fallbackPreview);
  fallbackPreview["Runtime summary"] = buildRuntimeSummaryPreview(fallbackPreview);

  const storedPreview = readStoredPreview(summaryPath, CONTROL_PREVIEW_FIELDS);
  const repoDerivedPreview = controlPreviewFromRepoControl(storedPreview ?? undefined);
  const effectivePreview =
    mergePreviewSources(
      fallbackPreview,
      repoDerivedPreview,
      verificationPreview ?? undefined,
      runPreview ?? undefined,
      storedPreview ?? undefined,
      runtimePayloadPreview,
      runRuntimePayloadPreview,
    ) ??
    fallbackPreview;
  hydrateControlPreviewFromRepoControl(effectivePreview);
  normalizeVerificationPreview(effectivePreview);
  if (!previewField(effectivePreview, "Verification receipt")) {
    effectivePreview["Verification receipt"] = defaultVerificationReceiptPath(effectivePreview, summary.stateDir);
  }
  const normalizedVerificationBundle = normalizedVerificationBundleFromPreview(effectivePreview);
  const explicitSourcePreview = mergePreviewSources(
    verificationPreview ?? undefined,
    runPreview ?? undefined,
    storedPreview ?? undefined,
    runtimePayloadPreview,
    runRuntimePayloadPreview,
  );
  effectivePreview["Runtime freshness"] =
    previewField(explicitSourcePreview, "Runtime freshness") ||
    [
      previewField(effectivePreview, "Loop state") || `cycle ${summary.cycle ?? "n/a"} ${summary.runStatus}`,
      `updated ${previewField(effectivePreview, "Updated") || summary.updatedAt || "unknown"}`,
      `verify ${normalizedVerificationBundle}`,
    ].join(" | ");
  const explicitRuntimeSummary = previewField(explicitSourcePreview, "Runtime summary");
  effectivePreview["Runtime summary"] =
    explicitRuntimeSummary || buildRuntimeSummaryPreview({...effectivePreview, "Runtime summary": ""});
  effectivePreview["Control pulse preview"] =
    previewField(explicitSourcePreview, "Control pulse preview") ||
    buildControlPulsePreview(
      previewField(effectivePreview, "Last result") || "unknown",
      previewField(effectivePreview, "Runtime freshness") || "unknown",
      previewField(effectivePreview, "Updated") || "unknown",
      now,
    );
  effectivePreview["Control truth preview"] = buildControlTruthPreview(effectivePreview);
  if (storedPreview || runPreview || verificationPreview) {
    return effectivePreview;
  }

  return effectivePreview;
}

export function loadSupervisorRepoPreview(repoRoot = REPO_ROOT): TabPreview | null {
  const summary = loadSupervisorControlState(repoRoot);
  if (!summary) {
    return null;
  }
  const summaryPath = path.join(summary.stateDir, CONTROL_SUMMARY_FILENAME);
  const storedPreview = readStoredPreview(summaryPath, REPO_PREVIEW_FIELDS);
  const workspacePayload = readStoredSnapshotPayload(summaryPath, "workspace");
  const runPayload = readJsonFile(path.join(summary.stateDir, "run.json"));
  const runWorkspacePayload = snapshotPayloadFromRecord(runPayload, "workspace");
  const workspacePreview = workspacePayload
    ? workspacePayloadToPreview(workspacePayload as WorkspaceSnapshotPayload)
    : undefined;
  const runWorkspacePreview = runWorkspacePayload
    ? workspacePayloadToPreview(runWorkspacePayload as WorkspaceSnapshotPayload)
    : undefined;
  const effectiveStoredPreview = (() => {
    if (!storedPreview && !workspacePreview && !runWorkspacePreview) {
      return undefined;
    }
    const merged = {
      ...(storedPreview ?? {}),
      ...(workspacePreview ?? {}),
      ...(runWorkspacePreview ?? {}),
    };
    if (workspacePreview || runWorkspacePreview) {
      delete merged["Repo/control preview"];
    }
    return merged;
  })();
  if (!effectiveStoredPreview) {
    return null;
  }
  const controlPreview = loadSupervisorControlPreview(repoRoot);
  return deriveRepoPreviewFields(effectiveStoredPreview, controlPreview ?? undefined);
}

export function saveSupervisorRepoPreview(
  summary: SupervisorControlState,
  preview?: TabPreview,
  options?: PersistedSnapshotOptions,
): void {
  if (!preview) {
    return;
  }
  const summaryPath = path.join(summary.stateDir, CONTROL_SUMMARY_FILENAME);
  const storedControlPreview = readStoredPreview(summaryPath, CONTROL_PREVIEW_FIELDS);
  const enrichedPreview = normalizeRepoPreview(preview, storedControlPreview ?? undefined);
  if (!enrichedPreview) {
    return;
  }
  if (options?.workspacePayload) {
    writeStoredSnapshotPayload(summary, "workspace", options.workspacePayload);
    writeRunSnapshotPayload(summary, "workspace", options.workspacePayload);
  }
  writeStoredPreview(summary, enrichedPreview, REPO_PREVIEW_FIELDS);
  const synchronizedControlPreview = controlPreviewFromRepoControl(enrichedPreview);
  if (synchronizedControlPreview) {
    saveSupervisorControlSummary(summary, synchronizedControlPreview);
  }
}

export function saveSupervisorControlSummary(
  summary: SupervisorControlState,
  preview?: TabPreview,
  options?: PersistedSnapshotOptions,
): void {
  const summaryPath = path.join(summary.stateDir, CONTROL_SUMMARY_FILENAME);
  const existingPayload = readJsonFile(summaryPath);
  const persistedAt = new Date().toISOString();
  const mergedPreview = mergeStoredPreviewFields(summaryPath, CONTROL_PREVIEW_FIELDS, preview);
  hydrateControlPreviewFromRepoControl(mergedPreview);
  const incomingPreviewBundleEntries = verificationEntriesFromPreview(preview);
  const incomingPreviewBundleLabel = incomingPreviewBundleEntries.length > 0 ? verificationBundleLabel(incomingPreviewBundleEntries) : "";
  const incomingPreviewBundleChecks = incomingPreviewBundleEntries
    .map((entry) => `${entry.name} ${entry.ok ? "ok" : "fail"}`)
    .join("; ");
  const compactVerificationSummary = derivedCompactVerificationSummary(mergedPreview);
  const previewBundleEntries = verificationEntriesFromPreview(mergedPreview);
  const previewBundleLabel = previewBundleEntries.length > 0 ? verificationBundleLabel(previewBundleEntries) : "";
  const previewBundleChecks = previewBundleEntries.map((entry) => `${entry.name} ${entry.ok ? "ok" : "fail"}`).join("; ");
  const previewVerificationSummary =
    incomingPreviewBundleLabel &&
    (!previewField(preview, "Verification summary") || isGenericVerificationLabel(previewField(preview, "Verification summary")))
      ? incomingPreviewBundleLabel
      : previewBundleLabel &&
          (!previewField(mergedPreview, "Verification summary") ||
            isGenericVerificationLabel(previewField(mergedPreview, "Verification summary")))
        ? previewBundleLabel
      : compactVerificationSummary &&
          (!previewField(mergedPreview, "Verification summary") ||
            isGenericVerificationLabel(previewField(mergedPreview, "Verification summary")))
        ? compactVerificationSummary
        : previewField(mergedPreview, "Verification summary");
  const compactVerificationChecks = compactVerificationSummary
    ? parseVerificationBundle("none", compactVerificationSummary)
        .map((entry) => `${entry.name} ${entry.ok ? "ok" : "fail"}`)
        .join("; ")
    : "";
  const previewVerificationChecks =
    incomingPreviewBundleChecks ||
    previewField(mergedPreview, "Verification checks") ||
    previewBundleChecks ||
    compactVerificationChecks ||
    previewBundleChecks;
  const effectiveVerificationSummary =
    previewVerificationSummary || normalizedVerificationBundleFromPreview(mergedPreview) || summary.verificationSummary;
  const effectiveVerificationChecks = previewVerificationChecks || summary.verificationChecks.join("; ");
  const effectiveVerificationBundle = parseVerificationBundle(
    effectiveVerificationChecks || "none",
    effectiveVerificationSummary || normalizedVerificationBundleFromPreview(mergedPreview) || "none",
  );
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
  const effectiveLoopState =
    previewField(mergedPreview, "Loop state") || derivedCompactLoopState(mergedPreview) || `cycle ${summary.cycle ?? "n/a"} ${summary.runStatus}`;
  const effectiveUpdated = previewField(mergedPreview, "Updated") || derivedCompactUpdated(mergedPreview) || summary.updatedAt || "unknown";
  const effectiveVerificationUpdated =
    previewField(mergedPreview, "Verification updated") ||
    derivedCompactUpdated(mergedPreview) ||
    summary.verificationUpdatedAt ||
    effectiveUpdated ||
    persistedAt;
  const effectiveLastResult =
    previewField(mergedPreview, "Last result") ||
    derivedCompactLastResult(mergedPreview) ||
    [summary.lastResultStatus, summary.acceptance].filter((value) => value.length > 0).join(" / ") ||
    "unknown";
  const effectiveRuntimeFreshness =
    previewField(preview, "Runtime freshness") ||
    [effectiveLoopState, `updated ${effectiveUpdated}`, `verify ${verificationBundleLabel(effectiveVerificationBundle)}`].join(" | ");
  const effectiveControlPulse =
    previewField(preview, "Control pulse preview") ||
    buildControlPulsePreview(effectiveLastResult, effectiveRuntimeFreshness, effectiveUpdated);
  const effectiveControlTruth =
    buildControlTruthPreview({
      ...mergedPreview,
      "Loop state": effectiveLoopState,
      "Next task": previewField(mergedPreview, "Next task") || summary.nextTask || "none",
      "Verification bundle": normalizedVerificationBundle,
      "Verification checks": effectiveVerificationChecks,
      "Verification summary": normalizedVerificationSummary,
    });
  const effectiveRuntimeSummary = buildRuntimeSummaryPreview(mergedPreview);
  const fallbackTaskProgress =
    summary.tasksTotal !== null && summary.tasksPending !== null
      ? `${Math.max(summary.tasksTotal - summary.tasksPending, 0)} done, ${summary.tasksPending} pending of ${summary.tasksTotal}`
      : "unknown";
  const fallbackLoopDecision =
    summary.continueRequired === null ? "unknown" : summary.continueRequired ? "continue required" : "ready to stop";
  const verificationReceiptPath = defaultVerificationReceiptPath(mergedPreview, summary.stateDir);
  const durablePreview: TabPreview = {
    ...(mergedPreview ?? {}),
    "Loop state": effectiveLoopState,
    "Task progress": previewField(mergedPreview, "Task progress") || fallbackTaskProgress,
    "Active task": previewField(mergedPreview, "Active task") || summary.activeTaskId || "none",
    "Result status": previewField(mergedPreview, "Result status") || summary.lastResultStatus || "unknown",
    Acceptance: previewField(mergedPreview, "Acceptance") || summary.acceptance || "unknown",
    "Last result": effectiveLastResult,
    "Verification summary": normalizedVerificationSummary,
    "Verification checks": effectiveVerificationChecks,
    "Verification status": normalizedVerificationStatus,
    "Verification passing": normalizedVerificationPassing,
    "Verification failing": normalizedVerificationFailing,
    "Verification bundle": normalizedVerificationBundle,
    "Verification receipt": previewField(mergedPreview, "Verification receipt") || verificationReceiptPath,
    "Verification updated": effectiveVerificationUpdated,
    "Loop decision": previewField(mergedPreview, "Loop decision") || fallbackLoopDecision,
    "Next task": previewField(mergedPreview, "Next task") || summary.nextTask || "none",
    Updated: effectiveUpdated,
    "Durable state": previewField(mergedPreview, "Durable state") || summary.stateDir,
    "Runtime freshness": effectiveRuntimeFreshness,
    "Control pulse preview": effectiveControlPulse,
    "Control truth preview": effectiveControlTruth,
    "Runtime summary": effectiveRuntimeSummary,
  };
  const previewPayload = Object.fromEntries(
    CONTROL_PREVIEW_FIELDS.map((key) => [previewStorageKey(key), previewField(durablePreview, key)]),
  );

  const payload = {
    ...existingPayload,
    ts: persistedAt,
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
    verification_updated_at: effectiveVerificationUpdated,
    continue_required: summary.continueRequired,
    next_task: summary.nextTask,
    updated_at: summary.updatedAt,
    ...previewPayload,
    ...(options?.runtimePayload ? {runtime_payload: options.runtimePayload} : {}),
  };
  mkdirSync(summary.stateDir, {recursive: true});
  writeFileSync(summaryPath, JSON.stringify(payload, null, 2) + "\n");
  writeVerificationSummaryFile(
    summary,
    normalizedVerificationSummary,
    effectiveVerificationBundle,
    effectiveVerificationUpdated,
    durablePreview,
  );
  writeRunVerificationSummaryFile(
    summary,
    normalizedVerificationSummary,
    effectiveVerificationBundle,
    effectiveVerificationUpdated,
    durablePreview,
    options,
  );
}
