import type {TabPreview} from "./types";

export type RepoControlSegmentKey =
  | "warn"
  | "peer"
  | "peers"
  | "drift"
  | "markers"
  | "divergence"
  | "detached"
  | "hotspot"
  | "path"
  | "dep"
  | "inbound";

export type ParsedRepoTruthPreview = {
  raw: string;
  branch: string;
  head: string;
  dirtyState: string;
  warning: string;
  hotspot: string;
};

export type ParsedRepoControlPreview = {
  raw: string;
  freshness: string;
  task: string;
  taskProgress: string;
  resultStatus: string;
  acceptance: string;
  loopDecision: string;
  loopState: string;
  updated: string;
  verificationBundle: string;
  nextTask: string;
  truthPreview: string;
  branch: string;
  branchName: string;
  head: string;
  branchStatus: string;
  upstream: string;
  ahead: string;
  behind: string;
  warning: string;
  topologyWarningCount: string;
  topologyWarningMembers: string;
  topologyPeer: string;
  topologyPeers: string;
  topologyPeerCount: string;
  peerDrift: string;
  peerMarkers: string;
  branchDivergence: string;
  detachedPeers: string;
  dirtyState: string;
  staged: string;
  unstaged: string;
  untracked: string;
  hotspot: string;
  hotspotSummary: string;
  primaryHotspot: string;
  hotspotPath: string;
  hotspotDependency: string;
  hotspotInbound: string;
  runtimeDb: string;
  runtimeActivity: string;
  artifactState: string;
  runtimeSummary: string;
  runtimeSessions: string;
  runtimeRuns: string;
  runtimeActiveRuns: string;
  runtimeArtifacts: string;
  runtimeContextBundles: string;
};

export const REPO_CONTROL_SEGMENT_BOUNDARY =
  "(?:warn|peers|peer|drift|markers|divergence|detached|hotspot|path|dep|inbound|staged|unstaged|untracked|cycle\\s+\\d+|updated\\s+|verify\\s+|db\\s+|activity\\s+|artifacts\\s+|next\\s+)";

const KNOWN_SEGMENT_PREFIXES = [
  "task ",
  "progress ",
  "outcome ",
  "decision ",
  "branch ",
  "tracking ",
  "dirty ",
  "warn ",
  "peer ",
  "peers ",
  "drift ",
  "markers ",
  "divergence ",
  "detached ",
  "hotspot ",
  "path ",
  "dep ",
  "inbound ",
  "cycle ",
  "updated ",
  "verify ",
  "db ",
  "activity ",
  "artifacts ",
  "next ",
];

function findBranchStatus(segments: string[]): string {
  return (
    segments.find(
      (segment) =>
        /^tracking\b/i.test(segment) || /\b(in sync|ahead|behind|diverged)\b/i.test(segment),
    ) ?? "n/a"
  );
}

function findWarning(segments: string[]): string {
  const explicit = segments.find((segment) => /^warn\s+/i.test(segment))?.replace(/^warn\s+/i, "").trim();
  if (explicit && explicit.length > 0) {
    return explicit;
  }
  const bareWarning = segments.find((segment, index) => {
    const normalized = segment.toLowerCase();
    if (/^(fresh|stale|unknown)$/i.test(segment)) {
      return false;
    }
    if (segment.includes("=") || index === 0) {
      return false;
    }
    const priorSegments = segments.slice(0, index).map((entry) => entry.toLowerCase());
    if (
      priorSegments.some((entry) =>
        entry.startsWith("dirty ") || entry.startsWith("verify ") || entry.startsWith("cycle ") || entry.startsWith("updated "),
      )
    ) {
      return false;
    }
    return !KNOWN_SEGMENT_PREFIXES.some((prefix) => normalized.startsWith(prefix));
  });
  return bareWarning?.trim() || "n/a";
}

function joinPrefixedSegments(segments: string[], prefixes: string[]): string {
  const parts = segments.filter((segment) =>
    prefixes.some((prefix) => segment.toLowerCase().startsWith(prefix)),
  );
  return parts.length > 0 ? parts.join(" | ") : "n/a";
}

function firstPrefixedSegment(segments: string[], prefixes: string[]): string {
  return (
    segments.find((segment) => prefixes.some((prefix) => segment.toLowerCase().startsWith(prefix))) ??
    "n/a"
  );
}

function parseBranchParts(branch: string): {branchName: string; head: string} {
  const match = branch.match(/^(.+?)@([^\s|]+)$/);
  if (!match) {
    return {branchName: branch, head: "n/a"};
  }
  return {
    branchName: match[1]?.trim() ?? branch,
    head: match[2]?.trim() ?? "n/a",
  };
}

function parseBranchDivergenceCounts(value: string): {ahead: string; behind: string} | null {
  const match = value.match(/\blocal\s+\+(\d+)\/-(\d+)\b/i);
  if (!match) {
    return null;
  }
  return {
    ahead: match[1] ?? "n/a",
    behind: match[2] ?? "n/a",
  };
}

function countSemicolonSegments(value: string): string {
  const normalized = value.trim();
  if (normalized.length === 0 || normalized === "n/a" || normalized === "none") {
    return "0";
  }
  if (/^\d+$/.test(normalized)) {
    return normalized;
  }
  return String(
    normalized
      .split(/\s*;\s*/)
      .map((entry) => entry.trim())
      .filter((entry) => entry.length > 0).length,
  );
}

function parseDirtyCount(value: string, label: "staged" | "unstaged" | "untracked"): string {
  return value.match(new RegExp(`\\b${label}\\s+(\\d+)\\b`, "i"))?.[1] ?? "n/a";
}

function parseHotspotSegment(value: string, key: "path" | "dep" | "inbound"): string {
  return value.match(new RegExp(`\\b${key}\\s+(.+?)(?=\\s+\\|\\s+(?:path|dep|inbound)\\b|$)`, "i"))?.[1]?.trim() ?? "n/a";
}

function parseMetric(value: string, label: string): string {
  return value.match(new RegExp(`\\b${label}=(\\d+)\\b`, "i"))?.[1] ?? "n/a";
}

function collectDirtyState(segments: string[]): string {
  const dirtyIndex = segments.findIndex((segment) => /^dirty\s+/i.test(segment));
  if (dirtyIndex === -1) {
    return "n/a";
  }
  const dirtyParts = [segments[dirtyIndex].replace(/^dirty\s+/i, "").trim()];
  for (const segment of segments.slice(dirtyIndex + 1)) {
    if (/^(unstaged|untracked)\s+/i.test(segment)) {
      dirtyParts.push(segment.trim());
      continue;
    }
    break;
  }
  return dirtyParts.join(" | ");
}

export function hasPreviewSignal(value: string): boolean {
  return value.length > 0 && value !== "n/a" && value !== "unknown";
}

export function splitPreviewPipes(value: string): string[] {
  return value
    .split("|")
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

export function extractRepoControlSegment(raw: string, key: RepoControlSegmentKey): string {
  if (!hasPreviewSignal(raw) || raw === "none") {
    return "";
  }
  const escapedKey = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return (
    raw.match(
      new RegExp(`\\b${escapedKey}\\s+(.+?)(?=\\s+\\|\\s+${REPO_CONTROL_SEGMENT_BOUNDARY}|$)`, "i"),
    )?.[1]?.trim() ?? ""
  );
}

export function parseRepoTruthPreview(raw: string): ParsedRepoTruthPreview | null {
  if (!hasPreviewSignal(raw) || raw === "none") {
    return null;
  }
  const branchMatch = raw.match(/\bbranch\s+([^\s|@]+)@([^\s|]+)/i);
  return {
    raw,
    branch: branchMatch?.[1]?.trim() ?? "n/a",
    head: branchMatch?.[2]?.trim() ?? "n/a",
    dirtyState: raw.match(/\bdirty\s+(.+?)(?=\s+\|\s+(?:warn|hotspot)\b|$)/i)?.[1]?.trim() ?? "n/a",
    warning: raw.match(/\bwarn\s+(.+?)(?=\s+\|\s+hotspot\b|$)/i)?.[1]?.trim() ?? "n/a",
    hotspot: raw.match(/\bhotspot\s+(.+)$/i)?.[1]?.trim() ?? "n/a",
  };
}

export function parseBranchSyncPreview(raw: string): {branchStatus: string; ahead: string; behind: string} | null {
  if (!hasPreviewSignal(raw) || raw === "none") {
    return null;
  }
  const segments = splitPreviewPipes(raw);
  const branchStatus =
    segments.find((segment) => /^tracking\b/i.test(segment) || /\bin sync\b/i.test(segment) || /\bahead\b/i.test(segment) || /\bbehind\b/i.test(segment)) ??
    "n/a";
  const divergence = segments.find((segment) => /^[+-]\d+\/-[+-]?\d+$/i.test(segment) || /^\+\d+\/-\d+$/i.test(segment)) ?? "";
  const countsMatch = divergence.match(/^\+(\d+)\/-(\d+)$/i);
  const trackingCounts = parseBranchTrackingCounts(branchStatus);
  const branchStatusLower = branchStatus.toLowerCase();
  return {
    branchStatus,
    ahead: countsMatch?.[1] ?? trackingCounts?.ahead ?? (branchStatusLower.includes("in sync") ? "0" : "n/a"),
    behind:
      countsMatch?.[2] ??
      trackingCounts?.behind ??
      (branchStatusLower.includes("in sync") || trackingCounts?.ahead !== "n/a" ? "0" : "n/a"),
  };
}

export function parseRepoControlBranchPreview(raw: string): {branchStatus: string; ahead: string; behind: string} | null {
  if (!hasPreviewSignal(raw) || raw === "none") {
    return null;
  }
  const segments = splitPreviewPipes(raw);
  const branchStatus =
    segments.find((segment) => /^tracking\b/i.test(segment) || /\bin sync\b/i.test(segment) || /\bahead\b/i.test(segment) || /\bbehind\b/i.test(segment)) ??
    "";
  const divergence = segments.find((segment) => /^divergence\s+/i.test(segment))?.replace(/^divergence\s+/i, "").trim() ?? "";
  const divergenceCounts = divergence.match(/\blocal\s+\+(\d+)\/-(\d+)\b/i);
  const trackingCounts = parseBranchTrackingCounts(branchStatus);
  if (!branchStatus && !divergenceCounts) {
    return null;
  }
  const branchStatusLower = branchStatus.toLowerCase();
  return {
    branchStatus: branchStatus || "n/a",
    ahead: divergenceCounts?.[1] ?? trackingCounts?.ahead ?? (branchStatusLower.includes("in sync") ? "0" : "n/a"),
    behind:
      divergenceCounts?.[2] ??
      trackingCounts?.behind ??
      (branchStatusLower.includes("in sync") || trackingCounts?.ahead !== "n/a" ? "0" : "n/a"),
  };
}

export function firstDelimitedSegment(value: string): string {
  if (!hasPreviewSignal(value) || value === "none") {
    return value;
  }
  return (
    value
      .split(/[;,]/)
      .map((segment) => segment.trim())
      .find((segment) => segment.length > 0) || value
  );
}

export function splitWarningMembers(value: string): string[] {
  if (!hasPreviewSignal(value) || value === "none") {
    return [];
  }
  return value
    .split(/[;,]/)
    .map((segment) => segment.trim())
    .filter((segment) => segment.length > 0);
}

export function normalizePrimaryWarning(value: string): string {
  if (!hasPreviewSignal(value) || value === "none") {
    return "";
  }
  const members = value.match(/^\d+\s*\((.+)\)$/)?.[1]?.trim();
  return firstDelimitedSegment(members || value);
}

export function isPeerSummary(value: string): boolean {
  return /\(.+,\s*.+,\s*dirty\s+.+\)$/i.test(value);
}

export function isBranchStatusSegment(value: string): boolean {
  return /^tracking\b/i.test(value) || /\b(in sync|ahead|behind|diverged)\b/i.test(value);
}

export function deriveWarningFromPreviewSegments(value: string): string {
  return (
    splitPreviewPipes(value).find(
      (segment) =>
        !isPeerSummary(segment) &&
        !segment.includes("Δ") &&
        !/\bclean\b/i.test(segment) &&
        !isBranchStatusSegment(segment),
    ) || ""
  );
}

export function parseBranchTrackingCounts(branchStatus: string): {ahead: string; behind: string} | null {
  const normalized = branchStatus.trim();
  if (normalized.length === 0) {
    return null;
  }

  const bracketed = normalized.match(/\[(.+)\]$/);
  if (bracketed) {
    const counts = {ahead: "n/a", behind: "n/a"};
    for (const segment of bracketed[1].split(",")) {
      const trimmed = segment.trim();
      const ahead = trimmed.match(/^ahead\s+(\d+)$/i)?.[1];
      if (ahead) {
        counts.ahead = ahead;
      }
      const behind = trimmed.match(/^behind\s+(\d+)$/i)?.[1];
      if (behind) {
        counts.behind = behind;
      }
    }
    if (counts.ahead !== "n/a" || counts.behind !== "n/a") {
      if (counts.ahead !== "n/a" && counts.behind === "n/a") {
        counts.behind = "0";
      }
      if (counts.behind !== "n/a" && counts.ahead === "n/a") {
        counts.ahead = "0";
      }
      return counts;
    }
  }

  const ahead =
    normalized.match(/\bahead\s+(\d+)\b/i)?.[1] ??
    normalized.match(/\bahead(?:\s+of\s+[^\s|]+)?\s+by\s+(\d+)\b/i)?.[1];
  const behind =
    normalized.match(/\bbehind\s+(\d+)\b/i)?.[1] ??
    normalized.match(/\bbehind(?:\s+[^\s|]+)?\s+by\s+(\d+)\b/i)?.[1];
  if (!ahead && !behind) {
    return null;
  }
  return {
    ahead: ahead ?? (normalized.toLowerCase().includes("in sync") ? "0" : "n/a"),
    behind: behind ?? (normalized.toLowerCase().includes("in sync") || ahead ? "0" : "n/a"),
  };
}

export function parseTrackedUpstream(branchStatus: string): string | null {
  const normalized = branchStatus.trim();
  if (normalized.length === 0) {
    return null;
  }

  const trackingMatch = normalized.match(/\btracking\s+([^\s|]+)/i)?.[1];
  if (trackingMatch) {
    return trackingMatch.trim();
  }

  const aheadBehindMatch = normalized.match(/\b(?:ahead|behind)\s+of\s+([^\s|]+)\s+by\s+\d+\b/i)?.[1];
  if (aheadBehindMatch) {
    return aheadBehindMatch.trim();
  }

  const branchRangeMatch = normalized.match(/\b[^\s|.]+\.\.\.([^\s|\]]+)/)?.[1];
  if (branchRangeMatch) {
    return branchRangeMatch.trim();
  }

  return null;
}

export function normalizeChangedHotspotLabel(value: string): string {
  if (value.length === 0) {
    return value;
  }
  return value
    .replace(/^hotspot\s+/i, "")
    .replace(/^change\s+/i, "")
    .trim();
}

export function classifyTopologyWarningSeverity(value: string): string {
  const leadWarning = value.toLowerCase().trim();
  if (!leadWarning || leadWarning === "none" || leadWarning === "0" || leadWarning === "stable") {
    return "stable";
  }
  if (leadWarning.includes("diverged") || leadWarning.includes("missing")) {
    return "high";
  }
  if (leadWarning.includes("detached") || leadWarning.includes("drift")) {
    return "elevated";
  }
  return "elevated";
}

export function parseRepoControlPreview(previewOrRaw?: TabPreview | string): ParsedRepoControlPreview | null {
  const raw =
    typeof previewOrRaw === "string"
      ? previewOrRaw
      : previewOrRaw?.["Repo/control preview"];
  if (typeof raw !== "string" || raw.length === 0) {
    return null;
  }

  const segments = raw
    .split("|")
    .map((part) => part.trim())
    .filter((part) => part.length > 0);

  const verificationIndex = segments.findIndex((segment) => /^verify\s+/i.test(segment));
  const verificationSegments: string[] = [];
  if (verificationIndex >= 0) {
    for (const [index, segment] of segments.slice(verificationIndex).entries()) {
      if (index > 0 && /^(next|db|activity|artifacts)\s+/i.test(segment)) {
        break;
      }
      verificationSegments.push(index === 0 ? segment.replace(/^verify\s+/i, "").trim() : segment);
    }
  }

  const verificationBundle = verificationSegments.join(" | ") || "n/a";
  const outcome = segments.find((segment) => /^outcome\s+/i.test(segment))?.replace(/^outcome\s+/i, "").trim() ?? "";
  const outcomeMatch = outcome.match(/^([^|/]+?)\s*\/\s*([^|]+?)$/);
  const nextTask = segments.find((segment) => /^next\s+/i.test(segment))?.replace(/^next\s+/i, "").trim() ?? "n/a";
  const loopState = segments.find((segment) => /^cycle\s+/i.test(segment)) ?? "n/a";
  const branch = segments.find((segment) => /^branch\s+/i.test(segment))?.replace(/^branch\s+/i, "").trim() ?? "n/a";
  const branchParts = parseBranchParts(branch);
  const branchStatus = findBranchStatus(segments);
  const branchTrackingCounts = parseBranchTrackingCounts(branchStatus);
  const warning = findWarning(segments);
  const topologyWarningMembers = warning === "n/a" ? "none" : warning;
  const topologyPeer = firstPrefixedSegment(segments, ["peer "]);
  const topologyPeers = firstPrefixedSegment(segments, ["peers "]);
  const topologyPeerCount =
    topologyPeers === "n/a" ? (topologyPeer === "n/a" ? "0" : "1") : countSemicolonSegments(topologyPeers.replace(/^peers\s+/i, ""));
  const peerDrift = firstPrefixedSegment(segments, ["drift "]);
  const peerMarkers = firstPrefixedSegment(segments, ["markers "]);
  const branchDivergence = firstPrefixedSegment(segments, ["divergence "]);
  const branchDivergenceCounts = branchDivergence === "n/a" ? null : parseBranchDivergenceCounts(branchDivergence);
  const detachedPeers = firstPrefixedSegment(segments, ["detached "]);
  const dirtyState = collectDirtyState(segments);
  const hotspot = joinPrefixedSegments(segments, ["hotspot ", "path ", "dep ", "inbound "]);
  const runtimeDb = segments.find((segment) => /^db\s+/i.test(segment))?.replace(/^db\s+/i, "").trim() ?? "n/a";
  const runtimeActivity = segments.find((segment) => /^activity\s+/i.test(segment))?.replace(/^activity\s+/i, "").trim() ?? "n/a";
  const artifactState = segments.find((segment) => /^artifacts\s+/i.test(segment))?.replace(/^artifacts\s+/i, "").trim() ?? "n/a";
  const runtimeSummary =
    [runtimeDb, runtimeActivity, artifactState].filter((value) => value !== "n/a" && value !== "none").join(" | ") || "n/a";
  const truthPreview = [
    branch !== "n/a" ? `branch ${branch}` : "",
    branchStatus !== "n/a" ? branchStatus : "",
    warning !== "n/a" ? `warn ${warning}` : "",
    topologyPeer !== "n/a" ? topologyPeer : "",
    topologyPeers !== "n/a" ? topologyPeers : "",
    peerDrift !== "n/a" ? peerDrift : "",
    peerMarkers !== "n/a" ? peerMarkers : "",
    branchDivergence !== "n/a" ? branchDivergence : "",
    detachedPeers !== "n/a" ? detachedPeers : "",
    dirtyState !== "n/a" ? `dirty ${dirtyState}` : "",
    hotspot,
    verificationBundle !== "n/a" ? verificationBundle : "",
    loopState !== "n/a" ? loopState : "",
    `next ${nextTask}`,
  ]
    .filter((part) => part.length > 0)
    .join(" | ");

  return {
    raw,
    freshness: /^(fresh|stale|unknown)\b/i.test(segments[0] ?? "") ? (segments[0] ?? "unknown") : "unknown",
    task: segments.find((segment) => /^task\s+/i.test(segment))?.replace(/^task\s+/i, "").trim() ?? "n/a",
    taskProgress: segments.find((segment) => /^progress\s+/i.test(segment))?.replace(/^progress\s+/i, "").trim() ?? "n/a",
    resultStatus: outcomeMatch?.[1]?.trim() ?? "n/a",
    acceptance: outcomeMatch?.[2]?.trim() ?? "n/a",
    loopDecision: segments.find((segment) => /^decision\s+/i.test(segment))?.replace(/^decision\s+/i, "").trim() ?? "n/a",
    loopState,
    updated: segments.find((segment) => /^updated\s+/i.test(segment))?.replace(/^updated\s+/i, "").trim() ?? "n/a",
    verificationBundle,
    nextTask,
    truthPreview,
    branch,
    branchName: branchParts.branchName,
    head: branchParts.head,
    branchStatus,
    upstream: parseTrackedUpstream(branchStatus) ?? "n/a",
    ahead: branchDivergenceCounts?.ahead ?? branchTrackingCounts?.ahead ?? "n/a",
    behind: branchDivergenceCounts?.behind ?? branchTrackingCounts?.behind ?? "n/a",
    warning,
    topologyWarningCount: countSemicolonSegments(warning),
    topologyWarningMembers,
    topologyPeer,
    topologyPeers,
    topologyPeerCount,
    peerDrift,
    peerMarkers,
    branchDivergence,
    detachedPeers,
    dirtyState,
    staged: parseDirtyCount(dirtyState, "staged"),
    unstaged: parseDirtyCount(dirtyState, "unstaged"),
    untracked: parseDirtyCount(dirtyState, "untracked"),
    hotspot,
    hotspotSummary: hotspot.replace(/^hotspot\s+/i, "").trim(),
    primaryHotspot: hotspot.match(/\bhotspot\s+(.+?)(?=\s+\|\s+(?:path|dep|inbound)\b|$)/i)?.[1]?.trim() ?? "n/a",
    hotspotPath: parseHotspotSegment(hotspot, "path"),
    hotspotDependency: parseHotspotSegment(hotspot, "dep"),
    hotspotInbound: parseHotspotSegment(hotspot, "inbound"),
    runtimeDb,
    runtimeActivity,
    artifactState,
    runtimeSummary,
    runtimeSessions: parseMetric(runtimeActivity, "Sessions"),
    runtimeRuns: parseMetric(runtimeActivity, "Runs"),
    runtimeActiveRuns: parseMetric(runtimeActivity, "ActiveRuns"),
    runtimeArtifacts: parseMetric(artifactState, "Artifacts"),
    runtimeContextBundles: parseMetric(artifactState, "ContextBundles"),
  };
}
