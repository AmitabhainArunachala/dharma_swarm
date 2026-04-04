import React from "react";
import {Box, Text} from "ink";

import {buildRepoPaneSections, sectionCardSummaries} from "./RepoPane";
import {freshnessToken, parseControlPulsePreview, parseRuntimeFreshness} from "../freshness";
import {
  REPO_CONTROL_SEGMENT_BOUNDARY,
  classifyTopologyWarningSeverity,
  deriveWarningFromPreviewSegments,
  extractRepoControlSegment,
  firstDelimitedSegment,
  hasPreviewSignal,
  isBranchStatusSegment,
  isPeerSummary,
  normalizeChangedHotspotLabel,
  normalizePrimaryWarning,
  parseBranchSyncPreview as parseBranchSyncPreviewValue,
  parseBranchTrackingCounts,
  parseRepoControlBranchPreview as parseRepoControlBranchPreviewValue,
  parseTrackedUpstream,
  parseRepoControlPreview,
  parseRepoTruthPreview,
  splitWarningMembers,
  splitPreviewPipes,
} from "../repoControlPreview";
import type {OutlineItem, SidebarMode, TabPreview, TabSpec} from "../types";
import {THEME} from "../theme";
import {isGenericVerificationLabel, parseVerificationBundle, verificationBundleLabel} from "../verification";

type Props = {
  mode: SidebarMode;
  outline: OutlineItem[];
  activeTabTitle: string;
  provider: string;
  model: string;
  bridgeStatus: string;
  tabs: TabSpec[];
  repoPreview?: TabPreview;
  controlPreview?: TabPreview;
  compact?: boolean;
};

function normalizedPreviewValue(value: unknown): string {
  if (typeof value !== "string") {
    return "n/a";
  }
  const trimmed = value.trim();
  if (trimmed.length === 0 || trimmed === "undefined" || trimmed === "null") {
    return "n/a";
  }
  return trimmed;
}

function normalizedContextValue(value: unknown): string {
  return normalizedPreviewValue(value);
}

function withRepoControlPreviewFallback(
  tabs: TabSpec[],
  repoPreview?: TabPreview,
  controlPreview?: TabPreview,
): TabPreview | undefined {
  const existingRepoControlPreview = normalizedPreviewValue(repoPreview?.["Repo/control preview"]);
  if (existingRepoControlPreview !== "n/a") {
    return repoPreview;
  }
  const controlRepoControlPreview = rawLineValueFor(tabs, "control", "Repo/control preview", controlPreview);
  if (controlRepoControlPreview === "n/a") {
    return repoPreview;
  }
  return {
    ...(repoPreview ?? {}),
    "Repo/control preview": controlRepoControlPreview,
  };
}

function rawLineValueFor(tabs: TabSpec[], tabId: string, label: string, preview?: TabPreview): string {
  const previewValue = normalizedPreviewValue(preview?.[label]);
  if (previewValue !== "n/a") {
    return previewValue;
  }
  const tab = tabs.find((entry) => entry.id === tabId);
  const tabPreviewValue = normalizedPreviewValue(tab?.preview?.[label]);
  if (tabPreviewValue !== "n/a") {
    return tabPreviewValue;
  }
  const match = tab?.lines.find((line) => line.text.startsWith(`${label}: `));
  if (!match) {
    return "n/a";
  }
  return normalizedPreviewValue(match.text.slice(label.length + 2));
}

function repoControlPreviewValue(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const value = rawLineValueFor(tabs, "repo", "Repo/control preview", repoPreview);
  return value === "n/a" ? "" : value;
}

function repoControlSegment(
  tabs: TabSpec[],
  repoPreview: TabPreview | undefined,
  key: "warn" | "peer" | "peers" | "drift" | "markers" | "divergence" | "detached" | "hotspot" | "path" | "dep" | "inbound",
): string {
  return extractRepoControlSegment(repoControlPreviewValue(tabs, repoPreview), key);
}

function repoControlDirtySegment(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const parsed = parseRepoControlPreview(repoControlPreviewValue(tabs, repoPreview));
  if (parsed?.dirtyState && parsed.dirtyState !== "n/a") {
    return parsed.dirtyState;
  }
  const raw = repoControlPreviewValue(tabs, repoPreview);
  if (!hasPreviewSignal(raw) || raw === "none") {
    return "";
  }
  return raw.match(new RegExp(`\\bdirty\\s+(.+?)(?=\\s+\\|\\s+${REPO_CONTROL_SEGMENT_BOUNDARY}|$)`, "i"))?.[1]?.trim() ?? "";
}

function repoTruthDirtySegment(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return parseRepoTruthPreview(rawLineValueFor(tabs, "repo", "Repo truth preview", repoPreview))?.dirtyState ?? "";
}

function repoTruthWarningSegment(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return parseRepoTruthPreview(rawLineValueFor(tabs, "repo", "Repo truth preview", repoPreview))?.warning ?? "";
}

function repoTruthHotspotSegment(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return parseRepoTruthPreview(rawLineValueFor(tabs, "repo", "Repo truth preview", repoPreview))?.hotspot ?? "";
}

function repoTruthBranchParts(tabs: TabSpec[], repoPreview?: TabPreview): {branch: string; head: string} | null {
  const parsed = parseRepoTruthPreview(rawLineValueFor(tabs, "repo", "Repo truth preview", repoPreview));
  if (!parsed) {
    return null;
  }
  return {branch: parsed.branch, head: parsed.head};
}

function repoControlBranchParts(tabs: TabSpec[], repoPreview?: TabPreview): {branch: string; head: string} | null {
  const parsed = parseRepoControlPreview(repoControlPreviewValue(tabs, repoPreview));
  if (!parsed) {
    return null;
  }
  return {branch: parsed.branchName, head: parsed.head};
}

function parseBranchSyncPreview(
  tabs: TabSpec[],
  repoPreview?: TabPreview,
): {branchStatus: string; ahead: string; behind: string} | null {
  return parseBranchSyncPreviewValue(rawLineValueFor(tabs, "repo", "Branch sync preview", repoPreview));
}

function parseRepoControlBranchPreview(
  tabs: TabSpec[],
  repoPreview?: TabPreview,
): {branchStatus: string; ahead: string; behind: string} | null {
  return parseRepoControlBranchPreviewValue(repoControlPreviewValue(tabs, repoPreview));
}

function deriveBranchValue(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", "Branch", repoPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  return repoTruthBranchParts(tabs, repoPreview)?.branch || repoControlBranchParts(tabs, repoPreview)?.branch || explicit;
}

function deriveHeadValue(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", "Head", repoPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  return repoTruthBranchParts(tabs, repoPreview)?.head || repoControlBranchParts(tabs, repoPreview)?.head || explicit;
}

function deriveBranchStatusValue(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", "Branch status", repoPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  return parseBranchSyncPreview(tabs, repoPreview)?.branchStatus || parseRepoControlBranchPreview(tabs, repoPreview)?.branchStatus || explicit;
}

function deriveBranchCountValue(tabs: TabSpec[], label: "Ahead" | "Behind", repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", label, repoPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const parsed = parseBranchSyncPreview(tabs, repoPreview);
  if (parsed) {
    return label === "Ahead" ? parsed.ahead || explicit : parsed.behind || explicit;
  }
  const repoControlParsed = parseRepoControlBranchPreview(tabs, repoPreview);
  return label === "Ahead" ? repoControlParsed?.ahead || explicit : repoControlParsed?.behind || explicit;
}

function deriveDirtyCountFromRepoTruth(
  tabs: TabSpec[],
  label: "staged" | "unstaged" | "untracked",
  repoPreview?: TabPreview,
): string {
  const explicitLabel = label.charAt(0).toUpperCase() + label.slice(1);
  const explicit = rawLineValueFor(tabs, "repo", explicitLabel, repoPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const dirtySegment = repoTruthDirtySegment(tabs, repoPreview);
  const candidate = dirtySegment || repoControlDirtySegment(tabs, repoPreview);
  if (!candidate) {
    const parsed = parseRepoControlPreview(repoControlPreviewValue(tabs, repoPreview));
    if (!parsed) {
      return explicit;
    }
    return (
      {
        staged: parsed.staged,
        unstaged: parsed.unstaged,
        untracked: parsed.untracked,
      }[label] || explicit
    );
  }
  return candidate.match(new RegExp(`\\b${label}\\s+(\\d+)\\b`, "i"))?.[1] ?? explicit;
}

function deriveDirtyLabel(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", "Dirty", repoPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const staged = deriveDirtyCountFromRepoTruth(tabs, "staged", repoPreview);
  const unstaged = deriveDirtyCountFromRepoTruth(tabs, "unstaged", repoPreview);
  const untracked = deriveDirtyCountFromRepoTruth(tabs, "untracked", repoPreview);
  if ([staged, unstaged, untracked].every((value) => value !== "n/a")) {
    return `${staged} staged, ${unstaged} unstaged, ${untracked} untracked`;
  }
  return explicit;
}

function controlRuntimeFreshness(tabs: TabSpec[], controlPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "control", "Runtime freshness", controlPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  return parseControlPulsePreview(rawLineValueFor(tabs, "control", "Control pulse preview", controlPreview)).runtimeFreshness ?? "n/a";
}

function controlLoopState(tabs: TabSpec[], controlPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "control", "Loop state", controlPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  return parseRuntimeFreshness(controlRuntimeFreshness(tabs, controlPreview)).loopState ?? "n/a";
}

function controlUpdated(tabs: TabSpec[], controlPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "control", "Updated", controlPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  return parseRuntimeFreshness(controlRuntimeFreshness(tabs, controlPreview)).updated ?? "n/a";
}

function controlLastResult(tabs: TabSpec[], controlPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "control", "Last result", controlPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  return parseControlPulsePreview(rawLineValueFor(tabs, "control", "Control pulse preview", controlPreview)).lastResult ?? "n/a";
}

function controlPulseDisplayValue(
  tabs: TabSpec[],
  controlPreview?: TabPreview,
  now: Date = new Date(),
  recomputeFreshness = false,
  deriveUpdated = true,
): string {
  const updated = deriveUpdated ? controlUpdated(tabs, controlPreview) : rawLineValueFor(tabs, "control", "Updated", controlPreview);
  const age = freshnessToken(updated, now);
  const explicit = rawLineValueFor(tabs, "control", "Control pulse preview", controlPreview);
  if (explicit !== "n/a") {
    if (!recomputeFreshness) {
      return /^(fresh|stale|unknown)\b/.test(explicit) ? explicit : `${age} | ${explicit}`;
    }
    const parsed = parseControlPulsePreview(explicit);
    if (parsed.lastResult || parsed.runtimeFreshness) {
      return [age, parsed.lastResult ?? "unknown", parsed.runtimeFreshness ?? "unknown"].join(" | ");
    }
    return /^(fresh|stale|unknown)\b/.test(explicit) ? explicit.replace(/^(fresh|stale|unknown)\b/, age) : `${age} | ${explicit}`;
  }
  return [age, controlLastResult(tabs, controlPreview), controlRuntimeFreshness(tabs, controlPreview)].join(" | ");
}

function parseControlOutcome(value: string): {resultStatus: string; acceptance: string} | null {
  if (!hasPreviewSignal(value) || value === "none") {
    return null;
  }
  const match = value.match(/^([^|/]+?)\s*\/\s*([^|]+?)$/);
  if (!match) {
    return null;
  }
  return {
    resultStatus: match[1]?.trim() ?? "n/a",
    acceptance: match[2]?.trim() ?? "n/a",
  };
}

function controlResultStatus(tabs: TabSpec[], controlPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "control", "Result status", controlPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  return parseControlOutcome(controlLastResult(tabs, controlPreview))?.resultStatus ?? explicit;
}

function controlAcceptance(tabs: TabSpec[], controlPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "control", "Acceptance", controlPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  return parseControlOutcome(controlLastResult(tabs, controlPreview))?.acceptance ?? explicit;
}

function controlVerificationBundle(tabs: TabSpec[], controlPreview?: TabPreview): string {
  const explicitBundle = rawLineValueFor(tabs, "control", "Verification bundle", controlPreview);
  if (hasPreviewSignal(explicitBundle) && explicitBundle !== "none" && !isGenericVerificationLabel(explicitBundle)) {
    return explicitBundle;
  }
  const summary = rawLineValueFor(tabs, "control", "Verification summary", controlPreview);
  const checks = rawLineValueFor(tabs, "control", "Verification checks", controlPreview);
  const parsed = parseVerificationBundle(checks, summary);
  if (parsed.length > 0) {
    return verificationBundleLabel(parsed);
  }
  const compactBundle = parseRuntimeFreshness(controlRuntimeFreshness(tabs, controlPreview)).verificationBundle ?? "";
  if (hasPreviewSignal(compactBundle) && compactBundle !== "none") {
    return compactBundle;
  }
  if (hasPreviewSignal(summary) && summary !== "none" && !isGenericVerificationLabel(summary)) {
    return summary;
  }
  return explicitBundle;
}

function controlRuntimeActivity(tabs: TabSpec[], controlPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "control", "Runtime activity", controlPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const sessionState = rawLineValueFor(tabs, "control", "Session state", controlPreview);
  const runState = rawLineValueFor(tabs, "control", "Run state", controlPreview);
  const sessions = sessionState.match(/\b(\d+)\s+sessions\b/i)?.[1];
  const runs = runState.match(/\b(\d+)\s+runs\b/i)?.[1];
  if (sessions || runs) {
    return [`Sessions=${sessions ?? "n/a"}`, runs ? `Runs=${runs}` : ""].filter((part) => part.length > 0).join("  ");
  }
  const runtimeSummary = rawLineValueFor(tabs, "control", "Runtime summary", controlPreview);
  const summarySessions = runtimeSummary.match(/\b(\d+)\s+sessions\b/i)?.[1];
  const summaryRuns = runtimeSummary.match(/\b(\d+)\s+runs\b/i)?.[1];
  if (summarySessions || summaryRuns) {
    return [`Sessions=${summarySessions ?? "n/a"}`, summaryRuns ? `Runs=${summaryRuns}` : ""]
      .filter((part) => part.length > 0)
      .join("  ");
  }
  return explicit;
}

function controlArtifactState(tabs: TabSpec[], controlPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "control", "Artifact state", controlPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const contextState = rawLineValueFor(tabs, "control", "Context state", controlPreview);
  const artifacts = contextState.match(/\b(\d+)\s+artifacts\b/i)?.[1];
  const contextBundles = contextState.match(/\b(\d+)\s+context bundles\b/i)?.[1];
  if (artifacts || contextBundles) {
    return [`Artifacts=${artifacts ?? "n/a"}`, contextBundles ? `ContextBundles=${contextBundles}` : ""]
      .filter((part) => part.length > 0)
      .join("  ");
  }
  const runtimeSummary = rawLineValueFor(tabs, "control", "Runtime summary", controlPreview);
  const summaryArtifacts = runtimeSummary.match(/\b(\d+)\s+artifacts\b/i)?.[1];
  const summaryContextBundles = runtimeSummary.match(/\b(\d+)\s+context bundles\b/i)?.[1];
  if (summaryArtifacts || summaryContextBundles) {
    return [`Artifacts=${summaryArtifacts ?? "n/a"}`, summaryContextBundles ? `ContextBundles=${summaryContextBundles}` : ""]
      .filter((part) => part.length > 0)
      .join("  ");
  }
  return explicit;
}

function firstRuntimeMetricValue(candidates: string[], patterns: RegExp[]): string {
  for (const candidate of candidates) {
    if (!hasPreviewSignal(candidate) || candidate === "none") {
      continue;
    }
    for (const pattern of patterns) {
      const match = candidate.match(pattern)?.[1];
      if (match) {
        return match;
      }
    }
  }
  return "";
}

function runtimeInventoryValue(
  runtimeActivity: string,
  artifactState: string,
  sessionState: string,
  contextState: string,
  runtimeSummary: string,
): string {
  const candidates = [runtimeActivity, artifactState, sessionState, contextState, runtimeSummary];
  const claims = firstRuntimeMetricValue(candidates, [/\bClaims=(\d+)\b/i, /\b(\d+)\s+claims\b/i]);
  const activeClaims = firstRuntimeMetricValue(candidates, [/\bActiveClaims=(\d+)\b/i, /\b(\d+)\s+active claims\b/i]);
  const ackedClaims = firstRuntimeMetricValue(candidates, [/\bAckedClaims=(\d+)\b/i, /\b(\d+)\s+acked claims\b/i]);
  const promotedFacts = firstRuntimeMetricValue(candidates, [/\bPromotedFacts=(\d+)\b/i, /\b(\d+)\s+promoted facts\b/i]);
  const operatorActions = firstRuntimeMetricValue(candidates, [/\bOperatorActions=(\d+)\b/i, /\b(\d+)\s+operator actions\b/i]);
  const parts = [
    claims ? `${claims} claims` : "",
    activeClaims ? `${activeClaims} active claims` : "",
    ackedClaims ? `${ackedClaims} acked claims` : "",
    promotedFacts ? `${promotedFacts} promoted facts` : "",
    operatorActions ? `${operatorActions} operator actions` : "",
  ].filter((part) => part.length > 0);
  return parts.join(" | ") || "n/a";
}

function controlRuntimeInventory(tabs: TabSpec[], controlPreview?: TabPreview): string {
  return runtimeInventoryValue(
    rawLineValueFor(tabs, "control", "Runtime activity", controlPreview),
    rawLineValueFor(tabs, "control", "Artifact state", controlPreview),
    rawLineValueFor(tabs, "control", "Session state", controlPreview),
    rawLineValueFor(tabs, "control", "Context state", controlPreview),
    rawLineValueFor(tabs, "control", "Runtime summary", controlPreview),
  );
}

function fallbackRuntimeInventoryValue(tabs: TabSpec[], repoPreview?: TabPreview, controlPreview?: TabPreview): string {
  return runtimeInventoryValue(
    buildFallbackRuntimeStateValue(tabs, repoPreview, controlPreview),
    buildFallbackRuntimeStateValue(tabs, repoPreview, controlPreview),
    "n/a",
    "n/a",
    buildFallbackRuntimeStateValue(tabs, repoPreview, controlPreview),
  );
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

function derivePrimaryChangedHotspot(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", "Primary changed hotspot", repoPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return normalizeChangedHotspotLabel(explicit);
  }
  const repoControlHotspot = repoControlSegment(tabs, repoPreview, "hotspot");
  if (hasPreviewSignal(repoControlHotspot) && repoControlHotspot !== "none") {
    return normalizeChangedHotspotLabel(repoControlHotspot);
  }
  const candidates = [
    repoTruthHotspotSegment(tabs, repoPreview),
    rawLineValueFor(tabs, "repo", "Lead hotspot preview", repoPreview),
    rawLineValueFor(tabs, "repo", "Hotspot pressure preview", repoPreview),
    rawLineValueFor(tabs, "repo", "Hotspot summary", repoPreview),
  ];
  for (const candidate of candidates) {
    const derived = deriveHotspotMatch(candidate, [/(?:^|\|\s*|;\s*)change\s+([^|;]+?)(?=\s*(?:\||;|$))/i]);
    if (derived) {
      return derived;
    }
  }
  const changedHotspots = firstDelimitedSegment(rawLineValueFor(tabs, "repo", "Changed hotspots", repoPreview));
  if (hasPreviewSignal(changedHotspots) && changedHotspots !== "none") {
    return normalizeChangedHotspotLabel(changedHotspots);
  }
  return explicit;
}

function derivePrimaryChangedPath(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", "Primary changed path", repoPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const repoControlPath = repoControlSegment(tabs, repoPreview, "path");
  if (hasPreviewSignal(repoControlPath) && repoControlPath !== "none") {
    return repoControlPath;
  }
  const candidates = [
    repoTruthHotspotSegment(tabs, repoPreview),
    rawLineValueFor(tabs, "repo", "Lead hotspot preview", repoPreview),
    rawLineValueFor(tabs, "repo", "Hotspot summary", repoPreview),
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
  const changedPath = firstDelimitedSegment(rawLineValueFor(tabs, "repo", "Changed paths", repoPreview));
  if (hasPreviewSignal(changedPath) && changedPath !== "none") {
    return changedPath;
  }
  return explicit;
}

function derivePrimaryDependencyHotspot(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", "Primary dependency hotspot", repoPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const repoControlDependency = repoControlSegment(tabs, repoPreview, "dep");
  if (hasPreviewSignal(repoControlDependency) && repoControlDependency !== "none") {
    const inbound = repoControlSegment(tabs, repoPreview, "inbound");
    return hasPreviewSignal(inbound) && inbound !== "none"
      ? `${repoControlDependency} | inbound ${inbound}`
      : repoControlDependency;
  }
  const candidates = [
    repoTruthHotspotSegment(tabs, repoPreview),
    rawLineValueFor(tabs, "repo", "Lead hotspot preview", repoPreview),
    rawLineValueFor(tabs, "repo", "Hotspot pressure preview", repoPreview),
    rawLineValueFor(tabs, "repo", "Hotspot summary", repoPreview),
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
  const inboundHotspot = firstDelimitedSegment(rawLineValueFor(tabs, "repo", "Inbound hotspots", repoPreview));
  if (hasPreviewSignal(inboundHotspot) && inboundHotspot !== "none") {
    return inboundHotspot;
  }
  return explicit;
}

function deriveHotspotSummary(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", "Hotspot summary", repoPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const truthHotspot = repoTruthHotspotSegment(tabs, repoPreview);
  if (hasPreviewSignal(truthHotspot) && truthHotspot !== "none") {
    return truthHotspot;
  }
  const candidates = [
    rawLineValueFor(tabs, "repo", "Lead hotspot preview", repoPreview),
    rawLineValueFor(tabs, "repo", "Hotspot pressure preview", repoPreview),
  ];
  for (const candidate of candidates) {
    if (hasPreviewSignal(candidate) && candidate !== "none") {
      return candidate;
    }
  }
  const primaryParts: string[] = [];
  const primaryChange = derivePrimaryChangedHotspot(tabs, repoPreview);
  if (hasPreviewSignal(primaryChange) && primaryChange !== "none") {
    primaryParts.push(`change ${primaryChange}`);
  }
  const primaryPath = derivePrimaryChangedPath(tabs, repoPreview);
  if (hasPreviewSignal(primaryPath) && primaryPath !== "none") {
    primaryParts.push(`path ${primaryPath}`);
  }
  const primaryDependency = derivePrimaryDependencyHotspot(tabs, repoPreview);
  if (hasPreviewSignal(primaryDependency) && primaryDependency !== "none") {
    primaryParts.push(`dep ${primaryDependency}`);
  }
  if (primaryParts.length > 0) {
    return primaryParts.join(" | ");
  }
  const changedHotspots = rawLineValueFor(tabs, "repo", "Changed hotspots", repoPreview);
  if (hasPreviewSignal(changedHotspots) && changedHotspots !== "none") {
    const parts = [`change ${changedHotspots}`];
    const primaryFile = rawLineValueFor(tabs, "repo", "Primary file hotspot", repoPreview);
    if (hasPreviewSignal(primaryFile) && primaryFile !== "none") {
      parts.push(`files ${primaryFile}`);
    }
    const primaryDependency = derivePrimaryDependencyHotspot(tabs, repoPreview);
    if (hasPreviewSignal(primaryDependency) && primaryDependency !== "none") {
      parts.push(`deps ${primaryDependency}`);
    }
    const primaryPath = derivePrimaryChangedPath(tabs, repoPreview);
    if (hasPreviewSignal(primaryPath) && primaryPath !== "none") {
      parts.push(`paths ${primaryPath}`);
    }
    return parts.join(" | ");
  }
  return explicit;
}

function derivePrimaryWarning(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", "Primary warning", repoPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = normalizePrimaryWarning(repoControlSegment(tabs, repoPreview, "warn"));
  if (hasPreviewSignal(fromRepoControl) && fromRepoControl !== "none") {
    return fromRepoControl;
  }
  const warningFromTruth = repoTruthWarningSegment(tabs, repoPreview);
  if (hasPreviewSignal(warningFromTruth) && warningFromTruth !== "none") {
    return firstDelimitedSegment(warningFromTruth);
  }
  const previewWarning = [
    rawLineValueFor(tabs, "repo", "Topology preview", repoPreview),
    rawLineValueFor(tabs, "repo", "Risk preview", repoPreview),
    rawLineValueFor(tabs, "repo", "Repo risk preview", repoPreview),
  ]
    .map((candidate) => deriveWarningFromPreviewSegments(candidate))
    .find((candidate) => hasPreviewSignal(candidate) && candidate !== "none");
  if (previewWarning) {
    return previewWarning;
  }
  const topologyRisk = rawLineValueFor(tabs, "repo", "Topology risk", repoPreview);
  if (hasPreviewSignal(topologyRisk) && topologyRisk !== "stable" && topologyRisk !== "none") {
    return topologyRisk;
  }
  return explicit || topologyRisk || "n/a";
}

function deriveTopologyWarnings(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", "Topology warnings", repoPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = repoControlSegment(tabs, repoPreview, "warn");
  if (hasPreviewSignal(fromRepoControl) && fromRepoControl !== "none") {
    if (/^\d+\s*\(.+\)$/.test(fromRepoControl)) {
      return fromRepoControl;
    }
    const parsed = parseRepoControlPreview(repoControlPreviewValue(tabs, repoPreview));
    if (parsed && parsed.topologyWarningCount !== "0" && parsed.topologyWarningMembers !== "none") {
      return `${parsed.topologyWarningCount} (${parsed.topologyWarningMembers.replace(/\s*;\s*/g, ", ")})`;
    }
    return `1 (${normalizePrimaryWarning(fromRepoControl)})`;
  }
  const warningFromTruth = repoTruthWarningSegment(tabs, repoPreview);
  if (!hasPreviewSignal(warningFromTruth) || warningFromTruth === "none") {
    const primaryWarning = derivePrimaryWarning(tabs, repoPreview);
    if (hasPreviewSignal(primaryWarning) && primaryWarning !== "none") {
      return `1 (${primaryWarning})`;
    }
    return explicit;
  }
  const members = splitWarningMembers(warningFromTruth);
  if (members.length === 0) {
    return explicit;
  }
  return `${members.length} (${members.join(", ")})`;
}

function derivePrimaryTopologyPeer(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", "Primary topology peer", repoPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = repoControlSegment(tabs, repoPreview, "peer");
  if (hasPreviewSignal(fromRepoControl) && fromRepoControl !== "none") {
    return fromRepoControl;
  }
  return (
    [
      rawLineValueFor(tabs, "repo", "Topology preview", repoPreview),
      rawLineValueFor(tabs, "repo", "Risk preview", repoPreview),
      rawLineValueFor(tabs, "repo", "Repo risk preview", repoPreview),
    ]
      .flatMap((candidate) => splitPreviewPipes(candidate))
      .find((segment) => isPeerSummary(segment)) || explicit
  );
}

function derivePeerNamesFromPressure(pressure: string): string[] {
  if (!hasPreviewSignal(pressure) || pressure === "none") {
    return [];
  }
  return pressure
    .split(";")
    .map((part) => part.trim())
    .map((part) => part.match(/^([^;]+?)\s+(?:Δ\d+|\bclean\b)/i)?.[1]?.trim() || "")
    .filter((name) => name.length > 0);
}

function deriveNumericPeerCount(value: string): string {
  if (!hasPreviewSignal(value) || value === "none") {
    return "";
  }
  const normalized = value.replace(/^peers\s+/i, "").trim();
  return /^\d+$/.test(normalized) ? normalized : "";
}

function derivePrimaryPeerDrift(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", "Primary peer drift", repoPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = repoControlSegment(tabs, repoPreview, "drift");
  if (hasPreviewSignal(fromRepoControl) && fromRepoControl !== "none") {
    return fromRepoControl;
  }
  const primaryPeer = derivePrimaryTopologyPeer(tabs, repoPreview);
  const primaryWarning = derivePrimaryWarning(tabs, repoPreview);
  const match = primaryPeer.match(/^(.+?)\s+\([^,]+,\s*([^,]+),\s*dirty\s+.+\)$/i);
  if (!match) {
    return explicit || "n/a";
  }
  const [, rawName, rawBranch] = match;
  const name = rawName.trim();
  const branch = rawBranch.trim();
  if (!name) {
    return explicit || "n/a";
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

function deriveTopologyPeers(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", "Topology peers", repoPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = repoControlSegment(tabs, repoPreview, "peers");
  if (hasPreviewSignal(fromRepoControl) && fromRepoControl !== "none") {
    return fromRepoControl;
  }
  const primaryPeer = derivePrimaryTopologyPeer(tabs, repoPreview);
  if (hasPreviewSignal(primaryPeer) && primaryPeer !== "none") {
    return primaryPeer;
  }
  return explicit;
}

function deriveTopologyPeerCount(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", "Topology peer count", repoPreview);
  if (hasPreviewSignal(explicit)) {
    return explicit;
  }
  const topologyStatus = rawLineValueFor(tabs, "repo", "Topology status", repoPreview);
  const statusCount = topologyStatus.match(/\((?:\d+\s+warning(?:s)?(?:,\s*)?)?(\d+)\s+peer(?:s)?\)/i)?.[1];
  if (statusCount) {
    return statusCount;
  }
  const compactRepoControlCount = deriveNumericPeerCount(repoControlSegment(tabs, repoPreview, "peers"));
  if (compactRepoControlCount) {
    return compactRepoControlCount;
  }
  const pressureCount = derivePeerNamesFromPressure(rawLineValueFor(tabs, "repo", "Topology pressure", repoPreview)).length;
  if (pressureCount > 0) {
    return String(pressureCount);
  }
  const topologyPeers = deriveTopologyPeers(tabs, repoPreview);
  if (hasPreviewSignal(topologyPeers) && topologyPeers !== "none") {
    const numericTopologyPeers = deriveNumericPeerCount(topologyPeers);
    if (numericTopologyPeers) {
      return numericTopologyPeers;
    }
    return String(
      topologyPeers
        .split(";")
        .map((part) => part.trim())
        .filter((part) => part.length > 0).length,
    );
  }
  return explicit || "n/a";
}

function deriveTopologyStatus(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", "Topology status", repoPreview);
  if (hasPreviewSignal(explicit)) {
    return explicit;
  }
  const peerCount = deriveTopologyPeerCount(tabs, repoPreview);
  const warningCount = deriveTopologyWarnings(tabs, repoPreview).match(/^(\d+)/)?.[1];
  if (warningCount) {
    if (peerCount === "n/a") {
      return `degraded (${warningCount} warning${warningCount === "1" ? "" : "s"})`;
    }
    return `degraded (${warningCount} warning${warningCount === "1" ? "" : "s"}, ${peerCount} peer${peerCount === "1" ? "" : "s"})`;
  }
  if (peerCount !== "n/a") {
    const peerCountNumber = Number.parseInt(peerCount, 10);
    if (!Number.isNaN(peerCountNumber) && peerCountNumber > 0) {
      return `connected (${peerCountNumber} peer${peerCountNumber === 1 ? "" : "s"})`;
    }
  }
  return explicit || "n/a";
}

function deriveTopologyWarningMembers(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const warnings = deriveTopologyWarnings(tabs, repoPreview);
  if (warnings === "0") {
    return "none";
  }
  const members = warnings.match(/^\d+\s*\((.+)\)$/)?.[1]?.trim();
  if (members && members.length > 0) {
    return members;
  }
  return warnings;
}

function derivePeerDriftMarkers(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", "Peer drift markers", repoPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = repoControlSegment(tabs, repoPreview, "markers");
  if (hasPreviewSignal(fromRepoControl) && fromRepoControl !== "none") {
    return fromRepoControl;
  }
  const primaryPeer = derivePrimaryTopologyPeer(tabs, repoPreview);
  const primaryPeerName = primaryPeer.match(/^(.+?)\s+\(/)?.[1]?.trim() || "";
  const primaryPeerDrift = derivePrimaryPeerDrift(tabs, repoPreview);
  const extras = derivePeerNamesFromPressure(rawLineValueFor(tabs, "repo", "Topology pressure", repoPreview))
    .filter((name) => name !== primaryPeerName)
    .map((name) => `${name} n/a`);
  const derived = [primaryPeerDrift, ...extras]
    .filter((value) => hasPreviewSignal(value) && value !== "none")
    .join("; ");
  return derived || explicit || "n/a";
}

function parsePeerSummary(summary: string): {name: string; branch: string} | null {
  const match = summary.match(/^(.+?)\s+\([^,]+,\s*([^,]+),\s*dirty\s+.+\)$/i);
  if (!match) {
    return null;
  }
  return {name: match[1].trim(), branch: match[2].trim()};
}

function deriveDetachedPeers(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", "Detached peers", repoPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = repoControlSegment(tabs, repoPreview, "detached");
  if (hasPreviewSignal(fromRepoControl)) {
    return fromRepoControl;
  }
  const summaries = [
    ...deriveTopologyPeers(tabs, repoPreview)
      .split(";")
      .map((part) => part.trim())
      .filter((part) => part.length > 0),
    derivePrimaryTopologyPeer(tabs, repoPreview),
  ];
  const detached = Array.from(
    new Set(
      summaries
        .map((summary) => parsePeerSummary(summary))
        .filter((peer): peer is {name: string; branch: string} => Boolean(peer))
        .filter((peer) => /detached/i.test(peer.branch))
        .map((peer) => `${peer.name} detached`),
    ),
  );
  if (detached.length > 0) {
    return detached.join("; ");
  }
  const primaryPeerDrift = derivePrimaryPeerDrift(tabs, repoPreview);
  return /detached/i.test(primaryPeerDrift) ? primaryPeerDrift : "none";
}

function deriveRepoRisk(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", "Repo risk", repoPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const parsedPreview = parseRepoControlPreview(repoControlPreviewValue(tabs, repoPreview));
  const warning = derivePrimaryWarning(tabs, repoPreview);
  const dirtyState = parsedPreview?.dirtyState ?? "";
  if (hasPreviewSignal(warning) && warning !== "none" && warning !== "stable") {
    if (hasPreviewSignal(dirtyState) && dirtyState !== "none") {
      return `topology ${warning}; ${dirtyState}`;
    }
    return `topology ${warning}; ${classifyTopologyWarningSeverity(warning)}`;
  }
  if (hasPreviewSignal(dirtyState) && dirtyState !== "none") {
    return dirtyState;
  }
  return explicit;
}

function lineValueFor(tabs: TabSpec[], tabId: string, label: string, preview?: TabPreview): string {
  if (tabId === "repo") {
    switch (label) {
      case "Branch":
        return deriveBranchValue(tabs, preview);
      case "Head":
        return deriveHeadValue(tabs, preview);
      case "Branch status":
        return deriveBranchStatusValue(tabs, preview);
      case "Ahead":
        return deriveBranchCountValue(tabs, "Ahead", preview);
      case "Behind":
        return deriveBranchCountValue(tabs, "Behind", preview);
      case "Dirty":
        return deriveDirtyLabel(tabs, preview);
      case "Staged":
        return deriveDirtyCountFromRepoTruth(tabs, "staged", preview);
      case "Unstaged":
        return deriveDirtyCountFromRepoTruth(tabs, "unstaged", preview);
      case "Untracked":
        return deriveDirtyCountFromRepoTruth(tabs, "untracked", preview);
      case "Primary changed hotspot":
        return derivePrimaryChangedHotspot(tabs, preview);
      case "Primary changed path":
        return derivePrimaryChangedPath(tabs, preview);
      case "Primary dependency hotspot":
        return derivePrimaryDependencyHotspot(tabs, preview);
      case "Hotspot summary":
        return deriveHotspotSummary(tabs, preview);
      case "Primary warning":
        return derivePrimaryWarning(tabs, preview);
      case "Topology warnings":
        return deriveTopologyWarnings(tabs, preview);
      case "Risk preview": {
        const explicit = rawLineValueFor(tabs, "repo", "Risk preview", preview);
        if (hasPreviewSignal(explicit) && explicit !== "none") {
          return explicit;
        }
        const warning = derivePrimaryWarning(tabs, preview);
        const peer = derivePrimaryTopologyPeer(tabs, preview);
        if (warning === "n/a" && peer === "n/a") {
          return parseRepoControlPreview(repoControlPreviewValue(tabs, preview))?.dirtyState ?? "n/a";
        }
        if (peer === "n/a" || peer === "none") {
          return warning;
        }
        return `${warning} | ${peer}`;
      }
      case "Repo risk preview": {
        const explicit = rawLineValueFor(tabs, "repo", "Repo risk preview", preview);
        if (hasPreviewSignal(explicit) && explicit !== "none") {
          return explicit;
        }
        const branchStatus = deriveBranchStatusValue(tabs, preview);
        const riskPreview = lineValueFor(tabs, "repo", "Risk preview", preview);
        const compactFallback = parseRepoControlPreview(repoControlPreviewValue(tabs, preview))?.dirtyState ?? "";
        if (riskPreview === compactFallback && compactFallback !== "" && compactFallback !== "n/a") {
          return riskPreview;
        }
        if (riskPreview === "n/a" || riskPreview === "stable") {
          return branchStatus;
        }
        return `${branchStatus} | ${riskPreview}`;
      }
      case "Primary topology peer":
        return derivePrimaryTopologyPeer(tabs, preview);
      case "Topology risk": {
        const explicit = rawLineValueFor(tabs, "repo", "Topology risk", preview);
        if (hasPreviewSignal(explicit) && explicit !== "none") {
          return explicit;
        }
        const warning = derivePrimaryWarning(tabs, preview);
        return hasPreviewSignal(warning) && warning !== "none" ? warning : explicit;
      }
      case "Primary peer drift":
        return derivePrimaryPeerDrift(tabs, preview);
      case "Topology peers":
        return deriveTopologyPeers(tabs, preview);
      case "Topology peer count":
        return deriveTopologyPeerCount(tabs, preview);
      case "Topology status":
        return deriveTopologyStatus(tabs, preview);
      case "Topology warning members":
        return deriveTopologyWarningMembers(tabs, preview);
      case "Peer drift markers":
        return derivePeerDriftMarkers(tabs, preview);
      case "Repo risk":
        return deriveRepoRisk(tabs, preview);
      default:
        break;
    }
  }
  if (tabId === "control") {
    switch (label) {
      case "Result status":
        return controlResultStatus(tabs, preview);
      case "Acceptance":
        return controlAcceptance(tabs, preview);
      case "Runtime freshness":
        return controlRuntimeFreshness(tabs, preview);
      case "Updated":
        return controlUpdated(tabs, preview);
      case "Last result":
        return controlLastResult(tabs, preview);
      case "Verification bundle":
        return controlVerificationBundle(tabs, preview);
      case "Runtime activity":
        return controlRuntimeActivity(tabs, preview);
      case "Artifact state":
        return controlArtifactState(tabs, preview);
      default:
        break;
    }
  }
  return rawLineValueFor(tabs, tabId, label, preview);
}

function topologySeverityValue(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = lineValueFor(tabs, "repo", "Topology warning severity", repoPreview);
  if (explicit !== "n/a") {
    return explicit;
  }
  const primaryWarning = lineValueFor(tabs, "repo", "Primary warning", repoPreview);
  if (primaryWarning === "none") {
    return "stable";
  }
  const topologyWarnings = lineValueFor(tabs, "repo", "Topology warnings", repoPreview);
  if (topologyWarnings === "0") {
    return "stable";
  }
  const repoRisk = lineValueFor(tabs, "repo", "Repo risk", repoPreview);
  const severityMatch = repoRisk.match(/;\s*([a-z]+)\s*(?:\(|$)/i);
  if (severityMatch?.[1]) {
    return severityMatch[1].toLowerCase();
  }
  if (primaryWarning !== "n/a") {
    return classifyTopologyWarningSeverity(primaryWarning);
  }
  return "n/a";
}

function labeledValue(label: string, value: string): string {
  return `${label} ${value}`;
}

function compact(value: string, max = 56): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= max) {
    return normalized;
  }
  return `${normalized.slice(0, max - 1).trimEnd()}…`;
}

const CONTROL_SIGNAL_LABELS = [
  "Active task",
  "Loop state",
  "Runtime freshness",
  "Updated",
  "Verification bundle",
  "Runtime DB",
  "Control pulse preview",
  "Control truth preview",
];

const CONTROL_RUNTIME_SIGNAL_LABELS = [
  "Runtime DB",
  "Runtime activity",
  "Artifact state",
  "Runtime summary",
  "Session state",
  "Run state",
  "Context state",
];

function hasControlSnapshotSignal(tabs: TabSpec[], controlPreview?: TabPreview): boolean {
  if (controlPreview) {
    return CONTROL_SIGNAL_LABELS.some((label) => hasPreviewSignal(controlPreview[label] ?? ""));
  }
  const controlTab = tabs.find((tab) => tab.id === "control");
  if (controlTab?.preview) {
    const hasPreviewSignalInTab = CONTROL_SIGNAL_LABELS.some((label) => hasPreviewSignal(controlTab.preview?.[label] ?? ""));
    if (hasPreviewSignalInTab) {
      return true;
    }
  }
  return (
    controlTab?.lines.some((line) =>
      /^(Active task|Loop state|Runtime freshness|Updated|Verification bundle|Runtime DB|Control pulse preview|Control truth preview):\s+/.test(
        line.text,
      ),
    ) ?? false
  );
}

function hasControlRuntimeStateSignal(tabs: TabSpec[], controlPreview?: TabPreview): boolean {
  if (controlPreview) {
    return CONTROL_RUNTIME_SIGNAL_LABELS.some((label) => hasPreviewSignal(controlPreview[label] ?? ""));
  }
  const controlTab = tabs.find((tab) => tab.id === "control");
  if (controlTab?.preview) {
    const hasPreviewSignalInTab = CONTROL_RUNTIME_SIGNAL_LABELS.some((label) => hasPreviewSignal(controlTab.preview?.[label] ?? ""));
    if (hasPreviewSignalInTab) {
      return true;
    }
  }
  return (
    controlTab?.lines.some((line) =>
      /^(Runtime DB|Runtime activity|Artifact state|Runtime summary|Session state|Run state|Context state):\s+/.test(line.text),
    ) ?? false
  );
}

function branchLabel(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return `${lineValueFor(tabs, "repo", "Branch", repoPreview)}@${lineValueFor(tabs, "repo", "Head", repoPreview)}`;
}

function upstreamLabel(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = lineValueFor(tabs, "repo", "Upstream", repoPreview);
  if (hasPreviewSignal(explicit)) {
    return explicit;
  }
  const sync = lineValueFor(tabs, "repo", "Sync", repoPreview);
  const syncUpstream =
    sync
      .split("|")
      .map((part) => part.trim())
      .find((part) => part.length > 0 && !/^ahead\b/i.test(part) && !/^behind\b/i.test(part)) || "";
  if (hasPreviewSignal(syncUpstream)) {
    return syncUpstream;
  }
  const branchStatus = lineValueFor(tabs, "repo", "Branch status", repoPreview);
  const trackedUpstream = parseTrackedUpstream(branchStatus);
  if (trackedUpstream && hasPreviewSignal(trackedUpstream)) {
    return trackedUpstream;
  }
  return explicit;
}

function syncLabel(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", "Sync", repoPreview);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const upstream = upstreamLabel(tabs, repoPreview);
  const ahead = lineValueFor(tabs, "repo", "Ahead", repoPreview);
  const behind = lineValueFor(tabs, "repo", "Behind", repoPreview);
  if (hasPreviewSignal(upstream) && ((ahead !== "n/a" && ahead !== "unknown") || (behind !== "n/a" && behind !== "unknown"))) {
    return `${upstream} | ahead ${ahead} | behind ${behind}`;
  }
  return explicit;
}

function dirtyCountsLabel(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return `staged ${lineValueFor(tabs, "repo", "Staged", repoPreview)} | unstaged ${lineValueFor(tabs, "repo", "Unstaged", repoPreview)} | untracked ${lineValueFor(tabs, "repo", "Untracked", repoPreview)}`;
}

function repoHealthLabel(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return `${lineValueFor(tabs, "repo", "Repo risk", repoPreview)} | ${syncLabel(tabs, repoPreview)}`;
}

function branchSyncPreviewLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = repoPreview?.["Branch sync preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return explicit;
  }
  return [
    lineValueFor(tabs, "repo", "Branch status", repoPreview),
    `+${lineValueFor(tabs, "repo", "Ahead", repoPreview)}/-${lineValueFor(tabs, "repo", "Behind", repoPreview)}`,
    lineValueFor(tabs, "repo", "Repo risk", repoPreview),
  ].join(" | ");
}

function buildRepoOverviewLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return [
    `Git ${branchLabel(tabs, repoPreview)}`,
    compact(lineValueFor(tabs, "repo", "Dirty pressure", repoPreview), 24),
    `sync ${compact(lineValueFor(tabs, "repo", "Branch status", repoPreview), 18)}`,
  ].join(" | ");
}

function buildRepoPulseLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return [
    `Dirty ${compact(dirtyCountsLabel(tabs, repoPreview), 31)}`,
    `topo ${compact(lineValueFor(tabs, "repo", "Topology warnings", repoPreview), 18)}`,
    `lead ${compact(lineValueFor(tabs, "repo", "Primary changed hotspot", repoPreview), 20)}`,
  ].join(" | ");
}

function buildLeadHotspotPreviewLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = repoPreview?.["Lead hotspot preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return explicit;
  }
  const parts: string[] = [];
  const change = lineValueFor(tabs, "repo", "Primary changed hotspot", repoPreview);
  const path = lineValueFor(tabs, "repo", "Primary changed path", repoPreview);
  const dep = lineValueFor(tabs, "repo", "Primary dependency hotspot", repoPreview);
  if (change !== "n/a" && change !== "none") {
    parts.push(`change ${change}`);
  }
  if (path !== "n/a" && path !== "none") {
    parts.push(`path ${path}`);
  }
  if (dep !== "n/a" && dep !== "none") {
    parts.push(`dep ${dep}`);
  }
  return parts.join(" | ") || "n/a";
}

function buildHotspotPressurePreviewLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = lineValueFor(tabs, "repo", "Hotspot pressure preview", repoPreview);
  if (explicit !== "n/a") {
    return labeledValue("Hotspot pressure", compact(explicit, 88));
  }
  const parts: string[] = [];
  const change = lineValueFor(tabs, "repo", "Primary changed hotspot", repoPreview);
  const dep = lineValueFor(tabs, "repo", "Primary dependency hotspot", repoPreview);
  if (change !== "n/a" && change !== "none") {
    parts.push(`change ${change}`);
  }
  if (dep !== "n/a" && dep !== "none") {
    parts.push(`dep ${dep}`);
  }
  return labeledValue("Hotspot pressure", compact(parts.join(" | ") || "n/a", 88));
}

function buildSnapshotHotspotPressureLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = lineValueFor(tabs, "repo", "Hotspot pressure preview", repoPreview);
  if (explicit !== "n/a") {
    return `Snapshot hotspot pressure ${compact(explicit, 56)}`;
  }
  const parts: string[] = [];
  const change = lineValueFor(tabs, "repo", "Primary changed hotspot", repoPreview);
  const dep = lineValueFor(tabs, "repo", "Primary dependency hotspot", repoPreview);
  if (change !== "n/a" && change !== "none") {
    parts.push(`change ${change}`);
  }
  if (dep !== "n/a" && dep !== "none") {
    parts.push(`dep ${dep}`);
  }
  return `Snapshot hotspot pressure ${compact(parts.join(" | ") || "n/a", 56)}`;
}

function buildTopologyPressurePreviewValue(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = lineValueFor(tabs, "repo", "Topology pressure preview", repoPreview);
  if (explicit !== "n/a") {
    return explicit;
  }
  const warnings = lineValueFor(tabs, "repo", "Topology warnings", repoPreview);
  const leadPressure = lineValueFor(tabs, "repo", "Topology pressure", repoPreview).split(";")[0]?.trim() || "none";
  if (warnings === "n/a" && leadPressure === "none") {
    return "n/a";
  }
  if (leadPressure === "none") {
    return warnings;
  }
  return `${warnings} | ${leadPressure}`;
}

function buildRepoSnapshotFreshnessLine(
  tabs: TabSpec[],
  repoPreview?: TabPreview,
  controlPreview?: TabPreview,
  now: Date = new Date(),
): string | null {
  if (!controlPreview && !tabs.find((tab) => tab.id === "control")) {
    return null;
  }
  const updated = lineValueFor(tabs, "control", "Updated", controlPreview);
  const activeTask = lineValueFor(tabs, "control", "Active task", controlPreview);
  const runtimeFreshness =
    lineValueFor(tabs, "control", "Runtime freshness", controlPreview) !== "n/a"
      ? lineValueFor(tabs, "control", "Runtime freshness", controlPreview)
      : [
          lineValueFor(tabs, "control", "Loop state", controlPreview),
          `updated ${updated}`,
          `verify ${lineValueFor(tabs, "control", "Verification bundle", controlPreview)}`,
        ].join(" | ");
  return [
    "Snapshot freshness",
    compact(
      [
        freshnessToken(updated, now),
        ...(activeTask !== "n/a" && activeTask !== "none" ? [`task ${activeTask}`] : []),
        lineValueFor(tabs, "repo", "Repo risk preview", repoPreview),
        runtimeFreshness,
      ].join(" | "),
      88,
    ),
  ].join(" ");
}

function buildRepoSnapshotRuntimeLine(tabs: TabSpec[], controlPreview?: TabPreview): string | null {
  if (!controlPreview && !tabs.find((tab) => tab.id === "control")) {
    return null;
  }
  return [
    "Snapshot runtime",
    compact(lineValueFor(tabs, "control", "Runtime DB", controlPreview), 24),
    "|",
    compact(lineValueFor(tabs, "control", "Runtime activity", controlPreview), 24),
    "|",
    compact(lineValueFor(tabs, "control", "Artifact state", controlPreview), 24),
  ].join(" ");
}

function buildRepoSnapshotTaskLine(tabs: TabSpec[], controlPreview?: TabPreview): string | null {
  if (!controlPreview && !tabs.find((tab) => tab.id === "control")) {
    return null;
  }
  return [
    "Snapshot task",
    compact(lineValueFor(tabs, "control", "Active task", controlPreview), 18),
    "|",
    `${lineValueFor(tabs, "control", "Result status", controlPreview)}/${lineValueFor(tabs, "control", "Acceptance", controlPreview)}`,
    "|",
    compact(lineValueFor(tabs, "control", "Loop state", controlPreview), 18),
    "|",
    compact(lineValueFor(tabs, "control", "Loop decision", controlPreview), 18),
  ].join(" ");
}

function buildRepoSnapshotVerificationLine(tabs: TabSpec[], controlPreview?: TabPreview): string | null {
  if (!controlPreview && !tabs.find((tab) => tab.id === "control")) {
    return null;
  }
  return [
    "Snapshot repo/control verify",
    compact(lineValueFor(tabs, "control", "Verification bundle", controlPreview), 42),
    "|",
    `next ${compact(lineValueFor(tabs, "control", "Next task", controlPreview), 24)}`,
  ].join(" ");
}

function buildRepoSnapshotControlPreviewLine(
  tabs: TabSpec[],
  controlPreview?: TabPreview,
  now: Date = new Date(),
  recomputeFreshness = false,
  deriveUpdated = true,
): string | null {
  if (!controlPreview && !tabs.find((tab) => tab.id === "control")) {
    return null;
  }
  return [
    "Snapshot control preview",
    compact(controlPulseDisplayValue(tabs, controlPreview, now, recomputeFreshness, deriveUpdated), 28),
    "|",
    compact(lineValueFor(tabs, "control", "Runtime activity", controlPreview), 18),
    "|",
    compact(lineValueFor(tabs, "control", "Artifact state", controlPreview), 24),
  ].join(" ");
}

function buildRepoSnapshotTruthLine(tabs: TabSpec[], controlPreview?: TabPreview): string | null {
  if (!controlPreview && !tabs.find((tab) => tab.id === "control")) {
    return null;
  }
  const explicit = lineValueFor(tabs, "control", "Control truth preview", controlPreview);
  if (explicit !== "n/a") {
    return `Snapshot truth ${compact(explicit, 56)}`;
  }
  return [
    "Snapshot truth",
    compact(lineValueFor(tabs, "control", "Verification bundle", controlPreview), 24),
    "|",
    compact(lineValueFor(tabs, "control", "Loop state", controlPreview), 22),
    "|",
    `next ${compact(lineValueFor(tabs, "control", "Next task", controlPreview), 24)}`,
  ].join(" ");
}

function buildRepoSnapshotRepoTruthLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = repoPreview?.["Repo truth preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return `Snapshot truth ${compact(explicit, 56)}`;
  }
  return [
    "Snapshot truth",
    `branch ${compact(branchLabel(tabs, repoPreview), 24)}`,
    "|",
    `dirty ${compact(dirtyCountsLabel(tabs, repoPreview), 34)}`,
    "|",
    `warn ${compact(lineValueFor(tabs, "repo", "Primary warning", repoPreview), 24)}`,
    "|",
    `hotspot ${compact(lineValueFor(tabs, "repo", "Hotspot summary", repoPreview), 36)}`,
  ].join(" ");
}

function repoSnapshotStableTopology(tabs: TabSpec[], repoPreview?: TabPreview): boolean {
  const topologyWarnings = lineValueFor(tabs, "repo", "Topology warnings", repoPreview).trim().toLowerCase();
  const detachedPeers = deriveDetachedPeers(tabs, repoPreview).trim().toLowerCase();
  return (topologyWarnings === "0" || topologyWarnings.startsWith("0 ")) && detachedPeers === "none";
}

function buildVisibleRepoSnapshotRows(
  tabs: TabSpec[],
  repoPreview?: TabPreview,
  controlPreview?: TabPreview,
  now: Date = new Date(),
): string[] {
  const hotspotSummary = lineValueFor(tabs, "repo", "Hotspot summary", repoPreview);
  const hasControlSignal = hasControlSnapshotSignal(tabs, controlPreview);
  const hasRepoControlPreview =
    typeof repoPreview?.["Repo/control preview"] === "string" && repoPreview["Repo/control preview"].length > 0;
  const rowsByKey: Array<[string, string]> = [
    [
      "branch",
      `Snapshot branch ${compact(branchLabel(tabs, repoPreview), 28)} | ${compact(lineValueFor(tabs, "repo", "Branch status", repoPreview), 24)}`,
    ],
    [
      "sync",
      `Snapshot sync ${compact(upstreamLabel(tabs, repoPreview), 18)} | +${lineValueFor(tabs, "repo", "Ahead", repoPreview)}/-${lineValueFor(tabs, "repo", "Behind", repoPreview)} | ${compact(syncLabel(tabs, repoPreview), 24)}`,
    ],
    ["branchSync", `Snapshot branch sync ${compact(branchSyncPreviewLine(tabs, repoPreview), 56)}`],
    ["dirty", `Snapshot dirty ${compact(lineValueFor(tabs, "repo", "Dirty pressure", repoPreview), 24)} | ${compact(dirtyCountsLabel(tabs, repoPreview), 31)}`],
    [
      "topology",
      `Snapshot topology ${compact(lineValueFor(tabs, "repo", "Topology status", repoPreview), 24)} | warnings ${compact(lineValueFor(tabs, "repo", "Topology warnings", repoPreview), 18)}`,
    ],
    ["topologySignal", `Snapshot topology signal ${compact(buildTopologySignalValue(tabs, repoPreview), 56)}`],
    ["warningMembers", `Snapshot warning members ${compact(lineValueFor(tabs, "repo", "Topology warning members", repoPreview), 56)}`],
    [
      "warnings",
      `Snapshot warnings ${compact(lineValueFor(tabs, "repo", "Primary warning", repoPreview), 28)} | severity ${compact(topologySeverityValue(tabs, repoPreview), 18)}`,
    ],
    ["alert", `Snapshot alert ${compact(buildTopologyAlertValue(tabs, repoPreview), 56)}`],
    ["branchDivergence", `Snapshot branch divergence ${compact(buildBranchDivergenceValue(tabs, repoPreview), 56)}`],
    ["detachedPeers", `Snapshot detached peers ${compact(deriveDetachedPeers(tabs, repoPreview), 56)}`],
    ["topologyPreview", `Snapshot topology preview ${compact(buildTopologyPreviewValue(tabs, repoPreview), 56)}`],
    ["topologyPressure", `Snapshot topology pressure ${compact(buildTopologyPressurePreviewValue(tabs, repoPreview), 56)}`],
    ["hotspots", `Snapshot hotspots ${compact(buildLeadHotspotPreviewLine(tabs, repoPreview), 52)}`],
    ["hotspotSummary", `Snapshot hotspot summary ${compact(hotspotSummary, 56)}`],
    [
      "summary",
      `Snapshot summary ${compact(lineValueFor(tabs, "repo", "Repo risk", repoPreview), 28)} | ${compact(hotspotSummary, 40)}`,
    ],
    ["truth", buildRepoSnapshotRepoTruthLine(tabs, repoPreview)],
    ["repoRisk", `Snapshot repo risk ${compact(lineValueFor(tabs, "repo", "Repo risk preview", repoPreview), 56)}`],
    [
      "focus",
      `Snapshot focus Root ${compact(lineValueFor(tabs, "repo", "Repo root", repoPreview), 24)} | lead ${compact(lineValueFor(tabs, "repo", "Primary changed path", repoPreview), 28)}`,
    ],
  ];

  if (hasControlSignal || hasRepoControlPreview) {
    rowsByKey.push([
      "repoControl",
      `Snapshot repo/control ${compact(buildRepoControlCorrelationValue(tabs, repoPreview, controlPreview, now), 56)}`,
    ]);
  }

  const rows = new Map(rowsByKey);
  const stable = repoSnapshotStableTopology(tabs, repoPreview);
  const orderedKeys = stable
    ? [
        "branch",
        "sync",
        "branchSync",
        "dirty",
        "topologySignal",
        "hotspotSummary",
        "focus",
        "repoControl",
        "repoRisk",
        "branchDivergence",
        "topology",
        "topologyPressure",
        "hotspots",
        "summary",
        "truth",
        "topologyPreview",
        "detachedPeers",
        "warningMembers",
        "warnings",
        "alert",
      ]
    : [
        "branch",
        "sync",
        "branchSync",
        "dirty",
        "topology",
        "warningMembers",
        "warnings",
        "alert",
        "topologySignal",
        "branchDivergence",
        "detachedPeers",
        "topologyPreview",
        "topologyPressure",
        "hotspots",
        "hotspotSummary",
        "summary",
        "truth",
        "repoControl",
        "repoRisk",
        "focus",
      ];

  const prioritizeControlRows = prioritizeLiveControlPreviewRows(tabs, controlPreview);
  const snapshotKeys = prioritizeControlRows ? orderedKeys.filter((key) => key !== "repoControl") : orderedKeys;
  return snapshotKeys.map((key) => rows.get(key)).filter((row): row is string => typeof row === "string" && row.length > 0);
}

function buildRepoSnapshotLines(
  tabs: TabSpec[],
  repoPreview?: TabPreview,
  controlPreview?: TabPreview,
  now: Date = new Date(),
): string[] {
  const prioritizeControlRows = prioritizeLiveControlPreviewRows(tabs, controlPreview);
  const rows = [
    `Snapshot branch ${compact(branchLabel(tabs, repoPreview), 28)} | ${compact(lineValueFor(tabs, "repo", "Branch status", repoPreview), 24)}`,
    `Snapshot sync ${compact(upstreamLabel(tabs, repoPreview), 18)} | +${lineValueFor(tabs, "repo", "Ahead", repoPreview)}/-${lineValueFor(tabs, "repo", "Behind", repoPreview)} | ${compact(syncLabel(tabs, repoPreview), 24)}`,
    `Snapshot branch sync ${compact(branchSyncPreviewLine(tabs, repoPreview), 56)}`,
    `Snapshot dirty ${compact(lineValueFor(tabs, "repo", "Dirty pressure", repoPreview), 24)} | ${compact(dirtyCountsLabel(tabs, repoPreview), 31)}`,
    `Snapshot topology ${compact(lineValueFor(tabs, "repo", "Topology status", repoPreview), 24)} | warnings ${compact(lineValueFor(tabs, "repo", "Topology warnings", repoPreview), 18)}`,
    `Snapshot warning members ${compact(lineValueFor(tabs, "repo", "Topology warning members", repoPreview), 56)}`,
    `Snapshot warnings ${compact(lineValueFor(tabs, "repo", "Primary warning", repoPreview), 28)} | severity ${compact(topologySeverityValue(tabs, repoPreview), 18)}`,
    `Snapshot alert ${compact(buildTopologyAlertValue(tabs, repoPreview), 56)}`,
    `Snapshot branch divergence ${compact(buildBranchDivergenceValue(tabs, repoPreview), 56)}`,
    `Snapshot detached peers ${compact(deriveDetachedPeers(tabs, repoPreview), 56)}`,
    `Snapshot topology preview ${compact(buildTopologyPreviewValue(tabs, repoPreview), 56)}`,
    `Snapshot topology pressure ${compact(buildTopologyPressurePreviewValue(tabs, repoPreview), 56)}`,
    `Snapshot hotspots ${compact(buildLeadHotspotPreviewLine(tabs, repoPreview), 52)}`,
    `Snapshot hotspot summary ${compact(lineValueFor(tabs, "repo", "Hotspot summary", repoPreview), 56)}`,
    `Snapshot summary ${compact(lineValueFor(tabs, "repo", "Repo risk", repoPreview), 28)} | ${compact(lineValueFor(tabs, "repo", "Hotspot summary", repoPreview), 40)}`,
    buildRepoSnapshotRepoTruthLine(tabs, repoPreview),
    `Snapshot repo risk ${compact(lineValueFor(tabs, "repo", "Repo risk preview", repoPreview), 56)}`,
    `Snapshot focus Root ${compact(lineValueFor(tabs, "repo", "Repo root", repoPreview), 24)} | lead ${compact(lineValueFor(tabs, "repo", "Primary changed path", repoPreview), 28)}`,
  ];
  if (controlPreview || tabs.find((tab) => tab.id === "control")) {
    const repoControlLine = `Snapshot repo/control ${compact(buildRepoControlCorrelationValue(tabs, repoPreview, controlPreview, now), 56)}`;
    const taskLine = `Snapshot task ${compact(lineValueFor(tabs, "control", "Active task", controlPreview), 18)} | ${lineValueFor(tabs, "control", "Result status", controlPreview)}/${lineValueFor(tabs, "control", "Acceptance", controlPreview)} | ${compact(lineValueFor(tabs, "control", "Loop state", controlPreview), 18)} | ${compact(lineValueFor(tabs, "control", "Loop decision", controlPreview), 18)}`;
    const runtimeLine = buildRepoSnapshotRuntimeLine(tabs, controlPreview);
    const controlPreviewLine = buildRepoSnapshotControlPreviewLine(tabs, controlPreview, now);
    const freshnessLine = buildRepoSnapshotFreshnessLine(tabs, repoPreview, controlPreview, now);
    const verificationLine = buildRepoSnapshotVerificationLine(tabs, controlPreview);

    rows.push(taskLine);
    if (runtimeLine) {
      rows.push(runtimeLine);
    }
    if (prioritizeControlRows) {
      rows.push(repoControlLine);
      if (verificationLine) {
        rows.push(verificationLine);
      }
      if (controlPreviewLine) {
        rows.push(controlPreviewLine);
      }
      if (freshnessLine) {
        rows.push(freshnessLine);
      }
    } else {
      rows.push(repoControlLine);
      if (controlPreviewLine) {
        rows.push(controlPreviewLine);
      }
      if (freshnessLine) {
        rows.push(freshnessLine);
      }
      if (verificationLine) {
        rows.push(verificationLine);
      }
    }
  }
  const truthLine = buildRepoSnapshotTruthLine(tabs, controlPreview);
  if (truthLine) {
    rows.push(truthLine);
  }
  return rows;
}

function buildRepoControlPulseLine(
  tabs: TabSpec[],
  controlPreview?: TabPreview,
  now: Date = new Date(),
  recomputeFreshness = false,
  deriveUpdated = true,
): string | null {
  if (!controlPreview && !tabs.find((tab) => tab.id === "control")) {
    return null;
  }
  return labeledValue("Control pulse", compact(controlPulseDisplayValue(tabs, controlPreview, now, recomputeFreshness, deriveUpdated), 88));
}

function buildRepoRuntimeStateLine(tabs: TabSpec[], controlPreview?: TabPreview): string | null {
  if (!controlPreview && !tabs.find((tab) => tab.id === "control")) {
    return null;
  }
  const runtimeDb = lineValueFor(tabs, "control", "Runtime DB", controlPreview);
  const runtimeActivity = lineValueFor(tabs, "control", "Runtime activity", controlPreview);
  const artifactState = lineValueFor(tabs, "control", "Artifact state", controlPreview);
  return labeledValue(
    "Runtime state",
    compact([runtimeDb, runtimeActivity, artifactState].join(" | "), 88),
  );
}

function buildRepoControlTaskLine(tabs: TabSpec[], controlPreview?: TabPreview): string | null {
  if (!controlPreview && !tabs.find((tab) => tab.id === "control")) {
    return null;
  }
  return labeledValue(
    "Control task",
    compact(
      [
        lineValueFor(tabs, "control", "Active task", controlPreview),
        lineValueFor(tabs, "control", "Task progress", controlPreview),
        `${lineValueFor(tabs, "control", "Result status", controlPreview)}/${lineValueFor(tabs, "control", "Acceptance", controlPreview)}`,
      ].join(" | "),
      88,
    ),
  );
}

function buildRepoControlVerificationLine(tabs: TabSpec[], controlPreview?: TabPreview): string | null {
  if (!controlPreview && !tabs.find((tab) => tab.id === "control")) {
    return null;
  }
  return labeledValue(
    "Control verify",
    compact(
      [
        controlVerificationBundle(tabs, controlPreview),
        `next ${lineValueFor(tabs, "control", "Next task", controlPreview)}`,
      ].join(" | "),
      88,
    ),
  );
}

function prioritizeLiveControlPreviewRows(tabs: TabSpec[], controlPreview?: TabPreview): boolean {
  if (!hasControlSnapshotSignal(tabs, controlPreview)) {
    return false;
  }
  const loopState = lineValueFor(tabs, "control", "Loop state", controlPreview).toLowerCase();
  const resultStatus = lineValueFor(tabs, "control", "Result status", controlPreview).toLowerCase();
  return resultStatus === "in_progress" || /\b(waiting_for_verification|refresh(?:ing)?)\b/.test(loopState);
}

function buildRepoFocusLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return `Focus ${compact(lineValueFor(tabs, "repo", "Repo root", repoPreview), 24)} | ${compact(lineValueFor(tabs, "repo", "Primary changed path", repoPreview), 24)}`;
}

function buildRepoTopologyPulseLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return `Topo pressure ${compact(lineValueFor(tabs, "repo", "Topology pressure", repoPreview), 48)}`;
}

function buildTopologyAlertValue(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return [
    topologySeverityValue(tabs, repoPreview),
    `warning ${lineValueFor(tabs, "repo", "Primary warning", repoPreview)}`,
    `drift ${lineValueFor(tabs, "repo", "Primary peer drift", repoPreview)}`,
  ].join(" | ");
}

function buildBranchDivergenceValue(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "repo", "Branch divergence", repoPreview);
  if (hasPreviewSignal(explicit)) {
    return explicit;
  }
  const fromRepoControl = repoControlSegment(tabs, repoPreview, "divergence");
  if (hasPreviewSignal(fromRepoControl)) {
    return fromRepoControl;
  }
  const ahead = lineValueFor(tabs, "repo", "Ahead", repoPreview);
  const behind = lineValueFor(tabs, "repo", "Behind", repoPreview);
  const drift = lineValueFor(tabs, "repo", "Primary peer drift", repoPreview);
  const parts: string[] = [];
  if ((ahead !== "n/a" && ahead !== "unknown") || (behind !== "n/a" && behind !== "unknown")) {
    parts.push(`local +${ahead}/-${behind}`);
  }
  if (drift !== "n/a" && drift !== "none") {
    parts.push(`peer ${drift}`);
  }
  return parts.join(" | ") || "n/a";
}

function buildBranchDivergenceLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return labeledValue("Branch divergence", compact(buildBranchDivergenceValue(tabs, repoPreview), 88));
}

function buildDetachedPeersLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return labeledValue("Detached peers", compact(deriveDetachedPeers(tabs, repoPreview), 88));
}

function buildTopologyPressurePreviewLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return labeledValue("Pressure preview", compact(buildTopologyPressurePreviewValue(tabs, repoPreview), 88));
}

function buildTopologyCountLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const parsed = parseRepoControlPreview(repoControlPreviewValue(tabs, repoPreview));
  const explicitPeerCount = rawLineValueFor(tabs, "repo", "Topology peer count", repoPreview);
  const explicitWarningCount = rawLineValueFor(tabs, "repo", "Topology warnings", repoPreview);
  const peerCount =
    hasPreviewSignal(explicitPeerCount) && explicitPeerCount !== "none"
      ? explicitPeerCount
      : parsed?.topologyPeerCount ?? lineValueFor(tabs, "repo", "Topology peer count", repoPreview);
  const warningCount =
    hasPreviewSignal(explicitWarningCount) && explicitWarningCount !== "none"
      ? explicitWarningCount
      : parsed && parsed.topologyWarningCount !== "0"
        ? `${parsed.topologyWarningCount} (${parsed.topologyWarningMembers})`
        : parsed?.topologyWarningCount ?? lineValueFor(tabs, "repo", "Topology warnings", repoPreview);
  return labeledValue("Count", compact(`${peerCount} peer${peerCount === "1" ? "" : "s"} | warnings ${warningCount}`, 88));
}

function buildRiskPreviewLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = repoPreview?.["Risk preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return labeledValue("Risk preview", compact(explicit, 56));
  }
  const warning = lineValueFor(tabs, "repo", "Primary warning", repoPreview);
  const peer = lineValueFor(tabs, "repo", "Primary topology peer", repoPreview);
  if (warning === "n/a" && peer === "n/a") {
    return labeledValue(
      "Risk preview",
      compact(parseRepoControlPreview(repoControlPreviewValue(tabs, repoPreview))?.dirtyState ?? "n/a", 56),
    );
  }
  if (peer === "n/a" || peer === "none") {
    return labeledValue("Risk preview", compact(warning, 56));
  }
  return labeledValue("Risk preview", compact(`${warning} | ${peer}`, 56));
}

function buildTopologySignalValue(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const severity = topologySeverityValue(tabs, repoPreview);
  const primaryPeerDrift = lineValueFor(tabs, "repo", "Primary peer drift", repoPreview);
  const topologyPressure = lineValueFor(tabs, "repo", "Topology pressure", repoPreview);
  const primaryPeer = lineValueFor(tabs, "repo", "Primary topology peer", repoPreview);
  const signal =
    primaryPeerDrift !== "n/a" && primaryPeerDrift !== "none"
      ? primaryPeerDrift
      : topologyPressure !== "n/a" && topologyPressure !== "none"
        ? firstDelimitedSegment(topologyPressure)
        : primaryPeer !== "n/a" && primaryPeer !== "none"
          ? primaryPeer
          : "none";
  return `${severity === "none" ? "stable" : severity} | ${signal}`;
}

function buildTopologySignalLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return labeledValue(
    "Topology signal",
    compact(buildTopologySignalValue(tabs, repoPreview), 88),
  );
}

function buildRepoRiskPreviewLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = repoPreview?.["Repo risk preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return labeledValue("Repo risk preview", compact(explicit, 88));
  }
  const branchStatus = lineValueFor(tabs, "repo", "Branch status", repoPreview);
  const riskPreview = lineValueFor(tabs, "repo", "Risk preview", repoPreview);
  const compactFallback = parseRepoControlPreview(repoControlPreviewValue(tabs, repoPreview))?.dirtyState ?? "";
  if (riskPreview === compactFallback && compactFallback !== "" && compactFallback !== "n/a") {
    return labeledValue("Repo risk preview", compact(riskPreview, 88));
  }
  if (riskPreview === "n/a" || riskPreview === "stable") {
    return labeledValue("Repo risk preview", compact(branchStatus, 88));
  }
  return labeledValue("Repo risk preview", compact(`${branchStatus} | ${riskPreview}`, 88));
}

function buildRepoRiskBlockLines(tabs: TabSpec[], repoPreview?: TabPreview): string[] {
  return [
    "Repo Risk",
    labeledValue("Risk", compact(lineValueFor(tabs, "repo", "Repo risk", repoPreview), 88)),
    `${labeledValue("Pressure", compact(lineValueFor(tabs, "repo", "Dirty pressure", repoPreview), 24))} | peers ${compact(lineValueFor(tabs, "repo", "Topology peer count", repoPreview), 16)}`,
    buildTopologyCountLine(tabs, repoPreview),
    labeledValue("Warnings", compact(lineValueFor(tabs, "repo", "Topology warnings", repoPreview), 88)),
    labeledValue("Members", compact(lineValueFor(tabs, "repo", "Topology warning members", repoPreview), 88)),
    `${labeledValue("Severity", compact(topologySeverityValue(tabs, repoPreview), 16))} | warning ${compact(lineValueFor(tabs, "repo", "Primary warning", repoPreview), 44)}`,
    labeledValue("Repo preview", compact(lineValueFor(tabs, "repo", "Repo risk preview", repoPreview), 88)),
    labeledValue("Risk preview", compact(lineValueFor(tabs, "repo", "Risk preview", repoPreview), 88)),
    buildBranchDivergenceLine(tabs, repoPreview),
    buildDetachedPeersLine(tabs, repoPreview),
    labeledValue("Peer drift", compact(lineValueFor(tabs, "repo", "Primary peer drift", repoPreview), 88)),
    labeledValue("Lead peer", compact(lineValueFor(tabs, "repo", "Primary topology peer", repoPreview), 88)),
    labeledValue("State", compact(lineValueFor(tabs, "repo", "Dirty", repoPreview), 88)),
    `${labeledValue("Topo", compact(lineValueFor(tabs, "repo", "Topology status", repoPreview), 24))} | risk ${compact(lineValueFor(tabs, "repo", "Topology risk", repoPreview), 18)}`,
    buildTopologySignalLine(tabs, repoPreview),
    buildTopologyPreviewLine(tabs, repoPreview),
    labeledValue("Lead warn", compact(lineValueFor(tabs, "repo", "Primary warning", repoPreview))),
    labeledValue("Peers", compact(lineValueFor(tabs, "repo", "Topology peers", repoPreview))),
    labeledValue("Pressure", compact(lineValueFor(tabs, "repo", "Topology pressure", repoPreview), 88)),
  ];
}

function buildTopologyPreviewLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = repoPreview?.["Topology preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return labeledValue("Topology preview", compact(explicit, 88));
  }
  const warning = lineValueFor(tabs, "repo", "Primary warning", repoPreview);
  const peer = lineValueFor(tabs, "repo", "Primary topology peer", repoPreview);
  const pressure = lineValueFor(tabs, "repo", "Topology pressure", repoPreview);
  const parts = [warning === "n/a" || warning === "none" ? "stable" : warning];
  if (peer !== "n/a" && peer !== "none") {
    parts.push(peer);
  }
  if (pressure !== "n/a" && pressure !== "none") {
    parts.push(pressure);
  }
  return labeledValue("Topology preview", compact(parts.join(" | "), 88));
}

function buildTopologyPreviewValue(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = repoPreview?.["Topology preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return explicit;
  }
  const warning = lineValueFor(tabs, "repo", "Primary warning", repoPreview);
  const peer = lineValueFor(tabs, "repo", "Primary topology peer", repoPreview);
  const pressure = lineValueFor(tabs, "repo", "Topology pressure", repoPreview);
  const parts = [warning === "n/a" || warning === "none" ? "stable" : warning];
  if (peer !== "n/a" && peer !== "none") {
    parts.push(peer);
  }
  if (pressure !== "n/a" && pressure !== "none") {
    parts.push(pressure);
  }
  return parts.join(" | ");
}

function buildRepoControlCorrelationValue(
  tabs: TabSpec[],
  repoPreview?: TabPreview,
  controlPreview?: TabPreview,
  now: Date = new Date(),
): string {
  const explicit = repoControlPreviewValue(tabs, repoPreview);
  if (!hasControlSnapshotSignal(tabs, controlPreview) && explicit.length > 0) {
    return explicit;
  }
  const updated = lineValueFor(tabs, "control", "Updated", controlPreview);
  const runtimeFreshness =
    lineValueFor(tabs, "control", "Runtime freshness", controlPreview) !== "n/a"
      ? lineValueFor(tabs, "control", "Runtime freshness", controlPreview)
      : [
          lineValueFor(tabs, "control", "Loop state", controlPreview),
          `updated ${lineValueFor(tabs, "control", "Updated", controlPreview)}`,
          `verify ${lineValueFor(tabs, "control", "Verification bundle", controlPreview)}`,
        ].join(" | ");
  const activeTask = lineValueFor(tabs, "control", "Active task", controlPreview);
  const branchStatus = lineValueFor(tabs, "repo", "Branch status", repoPreview);
  const dirtyCounts = dirtyCountsLabel(tabs, repoPreview);
  const topologyWarnings = deriveTopologyWarnings(tabs, repoPreview);
  const primaryWarning = derivePrimaryWarning(tabs, repoPreview);
  const primaryPeer = derivePrimaryTopologyPeer(tabs, repoPreview);
  const topologyPeers = deriveTopologyPeers(tabs, repoPreview);
  const topologyPeerCount = deriveTopologyPeerCount(tabs, repoPreview);
  const primaryPeerDrift = derivePrimaryPeerDrift(tabs, repoPreview);
  const peerDriftMarkers = derivePeerDriftMarkers(tabs, repoPreview);
  const branchDivergence = buildBranchDivergenceValue(tabs, repoPreview);
  const detachedPeers = deriveDetachedPeers(tabs, repoPreview);
  const primaryHotspot = lineValueFor(tabs, "repo", "Primary changed hotspot", repoPreview);
  const hotspotSummary = lineValueFor(tabs, "repo", "Hotspot summary", repoPreview);
  const primaryPath = lineValueFor(tabs, "repo", "Primary changed path", repoPreview);
  const primaryDependency = lineValueFor(tabs, "repo", "Primary dependency hotspot", repoPreview);
  const hotspotSummaryLabel =
    hotspotSummary !== "n/a" &&
    hotspotSummary !== "none" &&
    hotspotSummary !== primaryHotspot &&
    hotspotSummary !== `change ${primaryHotspot}`
      ? hotspotSummary
      : "";
  const summaryCarriesPath = /\bpaths?\b/i.test(hotspotSummaryLabel);
  const summaryCarriesDependency = /\bdeps?\b/i.test(hotspotSummaryLabel) || /\binbound\b/i.test(hotspotSummaryLabel);
  return [
    freshnessToken(updated, now),
    ...(activeTask !== "n/a" && activeTask !== "none" ? [`task ${activeTask}`] : []),
    ...(lineValueFor(tabs, "repo", "Branch", repoPreview) !== "n/a" &&
    lineValueFor(tabs, "repo", "Head", repoPreview) !== "n/a"
      ? [`branch ${branchLabel(tabs, repoPreview)}`]
      : []),
    ...(branchStatus !== "n/a" && branchStatus !== "none" ? [branchStatus] : []),
    ...(dirtyCounts !== "n/a" && !dirtyCounts.includes("n/a") ? [`dirty ${dirtyCounts}`] : []),
    ...(topologyWarnings !== "n/a" && topologyWarnings !== "none" && topologyWarnings !== "0"
      ? [`warn ${topologyWarnings}`]
      : primaryWarning !== "n/a" && primaryWarning !== "none"
        ? [`warn ${primaryWarning}`]
        : []),
    ...(primaryPeer !== "n/a" && primaryPeer !== "none" ? [`peer ${primaryPeer}`] : []),
    ...(topologyPeers !== "n/a" && topologyPeers !== "none"
      ? [`peers ${topologyPeers}`]
      : topologyPeerCount !== "n/a" && topologyPeerCount !== "0"
        ? [`peers ${topologyPeerCount}`]
        : []),
    ...(primaryPeerDrift !== "n/a" && primaryPeerDrift !== "none" ? [`drift ${primaryPeerDrift}`] : []),
    ...(peerDriftMarkers !== "n/a" && peerDriftMarkers !== "none" ? [`markers ${peerDriftMarkers}`] : []),
    ...(branchDivergence !== "n/a" ? [`divergence ${branchDivergence}`] : []),
    ...(detachedPeers !== "none" ? [`detached ${detachedPeers}`] : []),
    ...(primaryHotspot !== "n/a" && primaryHotspot !== "none" ? [`hotspot ${primaryHotspot}`] : []),
    ...(hotspotSummaryLabel ? [`summary ${hotspotSummaryLabel}`] : []),
    ...(primaryPath !== "n/a" && primaryPath !== "none" && !summaryCarriesPath ? [`path ${primaryPath}`] : []),
    ...(primaryDependency !== "n/a" && primaryDependency !== "none" && !summaryCarriesDependency
      ? [`dep ${primaryDependency}`]
      : []),
    runtimeFreshness,
  ].join(" | ");
}

function buildRepoControlCorrelationLine(
  tabs: TabSpec[],
  repoPreview?: TabPreview,
  controlPreview?: TabPreview,
  now: Date = new Date(),
): string {
  return labeledValue("Repo/control", compact(buildRepoControlCorrelationValue(tabs, repoPreview, controlPreview, now), 88));
}

function buildControlRepoAlignmentLines(tabs: TabSpec[], repoPreview?: TabPreview, max = 88): string[] {
  const primaryWarning = lineValueFor(tabs, "repo", "Primary warning", repoPreview);
  const severity = topologySeverityValue(tabs, repoPreview);
  const topologyPressure = buildTopologyPressurePreviewValue(tabs, repoPreview);
  const hotspotSummary = buildLeadHotspotPreviewLine(tabs, repoPreview);
  const warningParts = [
    ...(primaryWarning !== "n/a" && primaryWarning !== "none" ? [primaryWarning] : []),
    ...(severity !== "n/a" && severity !== "none" ? [`severity ${severity}`] : []),
    ...(topologyPressure !== "n/a" && topologyPressure !== "none" ? [`pressure ${topologyPressure}`] : []),
  ];

  return [
    ...(warningParts.length > 0 ? [labeledValue("Repo warn", compact(warningParts.join(" | "), max))] : []),
    ...(hotspotSummary !== "n/a" && hotspotSummary !== "none"
      ? [labeledValue("Repo hotspot", compact(hotspotSummary, max))]
      : []),
  ];
}

function buildHotspotFocusBlockLines(tabs: TabSpec[], repoPreview?: TabPreview, includePressure = true): string[] {
  const lines = [
    "Hotspot Focus",
    labeledValue("Changed", compact(lineValueFor(tabs, "repo", "Changed hotspots", repoPreview))),
    labeledValue("Summary", compact(buildLeadHotspotPreviewLine(tabs, repoPreview))),
    `${labeledValue("Lead change", compact(lineValueFor(tabs, "repo", "Primary changed hotspot", repoPreview), 20))} | ${compact(lineValueFor(tabs, "repo", "Primary changed path", repoPreview), 28)}`,
    labeledValue("Lead path", compact(lineValueFor(tabs, "repo", "Primary changed path", repoPreview))),
    labeledValue("Lead file", compact(lineValueFor(tabs, "repo", "Primary file hotspot", repoPreview))),
    labeledValue("Lead dep", compact(lineValueFor(tabs, "repo", "Primary dependency hotspot", repoPreview))),
    labeledValue("Paths", compact(lineValueFor(tabs, "repo", "Changed paths", repoPreview))),
    labeledValue("Hotspots", compact(lineValueFor(tabs, "repo", "Hotspots", repoPreview))),
    labeledValue("Deps", compact(lineValueFor(tabs, "repo", "Inbound hotspots", repoPreview))),
  ];
  if (includePressure) {
    lines.splice(3, 0, buildHotspotPressurePreviewLine(tabs, repoPreview));
  }
  return lines;
}

function uniqueSidebarLines(lines: string[]): string[] {
  return Array.from(
    new Set(
      lines.map((line) =>
        line
          .replace(/\bundefined\b/g, "n/a")
          .replace(/\bnull\b/g, "n/a"),
      ),
    ),
  );
}

function repoPaneSectionSummaries(
  tabs: TabSpec[],
  repoPreview?: TabPreview,
  controlPreview?: TabPreview,
  now: Date = new Date(),
): {repoRiskSummary: string[]; hotspotSummary: string[]} {
  const repoTab = tabs.find((tab) => tab.id === "repo");
  const controlTab = tabs.find((tab) => tab.id === "control");
  const repoSections = buildRepoPaneSections(
    repoPreview ?? repoTab?.preview,
    repoTab?.lines ?? [],
    controlPreview ?? controlTab?.preview,
    controlTab?.lines ?? [],
    now,
  );
  return {
    repoRiskSummary: sectionCardSummaries(repoSections.find((section) => section.title === "Repo Risk") ?? {title: "Repo Risk", rows: []}),
    hotspotSummary: sectionCardSummaries(repoSections.find((section) => section.title === "Hotspots") ?? {title: "Hotspots", rows: []}),
  };
}

function buildSummaryFirstSidebarBlock(title: string, summaryLines: string[], detailLines: string[]): string[] {
  return [title, ...uniqueSidebarLines([...summaryLines, ...detailLines])];
}

function buildRepoPreviewLines(
  tabs: TabSpec[],
  repoPreview?: TabPreview,
  controlPreview?: TabPreview,
  includeHotspotPressure = true,
  now: Date = new Date(),
): string[] {
  const {repoRiskSummary, hotspotSummary} = repoPaneSectionSummaries(tabs, repoPreview, controlPreview, now);
  const repoRiskPreviewLine = buildRepoRiskPreviewLine(tabs, repoPreview);
  const repoControlCorrelationLine = buildRepoControlCorrelationLine(tabs, repoPreview, controlPreview, now);
  const repoControlPulseLine = buildRepoControlPulseLine(tabs, controlPreview, now);
  const repoRuntimeStateLine = buildRepoRuntimeStateLine(tabs, controlPreview);
  const repoControlTaskLine = buildRepoControlTaskLine(tabs, controlPreview);
  const repoControlVerificationLine = buildRepoControlVerificationLine(tabs, controlPreview);
  const repoControlPreviewLines = [
    repoRiskPreviewLine,
    repoControlCorrelationLine,
    repoControlPulseLine,
    repoRuntimeStateLine,
    repoControlTaskLine,
    repoControlVerificationLine,
  ].filter((line): line is string => Boolean(line));
  const prioritizedCorrelationLines = includeHotspotPressure ? [] : repoControlPreviewLines;
  const trailingCorrelationLines = includeHotspotPressure ? repoControlPreviewLines : [];
  const repoRiskBlockLines = buildSummaryFirstSidebarBlock(
    "Repo Risk",
    repoRiskSummary,
    buildRepoRiskBlockLines(tabs, repoPreview).slice(1),
  );
  const hotspotFocusBlockLines = buildSummaryFirstSidebarBlock(
    "Hotspot Focus",
    hotspotSummary,
    buildHotspotFocusBlockLines(tabs, repoPreview, false).slice(1),
  );
  return [
    "Repo Preview",
    ...(repoPreview?.Authority ? [labeledValue("Authority", compact(repoPreview.Authority, 88))] : []),
    buildRepoOverviewLine(tabs, repoPreview),
    buildRepoPulseLine(tabs, repoPreview),
    ...buildRepoSnapshotLines(tabs, repoPreview, controlPreview, now),
    ...(includeHotspotPressure ? [] : hotspotFocusBlockLines),
    ...prioritizedCorrelationLines,
    ...repoRiskBlockLines,
    buildRepoFocusLine(tabs, repoPreview),
    buildRepoTopologyPulseLine(tabs, repoPreview),
    buildTopologyPressurePreviewLine(tabs, repoPreview),
    ...(includeHotspotPressure ? [buildHotspotPressurePreviewLine(tabs, repoPreview)] : []),
    labeledValue("Root", compact(lineValueFor(tabs, "repo", "Repo root", repoPreview), 56)),
    labeledValue("Branch", branchLabel(tabs, repoPreview)),
    labeledValue("Branch preview", compact(branchSyncPreviewLine(tabs, repoPreview), 88)),
    `${labeledValue("Track", compact(lineValueFor(tabs, "repo", "Branch status", repoPreview), 28))} | +${lineValueFor(tabs, "repo", "Ahead", repoPreview)}/-${lineValueFor(tabs, "repo", "Behind", repoPreview)}`,
    labeledValue("Sync", compact(syncLabel(tabs, repoPreview))),
    labeledValue("Health", compact(repoHealthLabel(tabs, repoPreview))),
    ...trailingCorrelationLines,
    `${labeledValue("Dirty", compact(lineValueFor(tabs, "repo", "Dirty pressure", repoPreview), 24))} | ${compact(dirtyCountsLabel(tabs, repoPreview), 31)}`,
    ...(includeHotspotPressure ? hotspotFocusBlockLines.slice(1) : []),
  ];
}

function buildControlOverviewLine(tabs: TabSpec[], controlPreview?: TabPreview): string {
  return [
    `Task ${lineValueFor(tabs, "control", "Active task", controlPreview)}`,
    `${lineValueFor(tabs, "control", "Result status", controlPreview)}/${lineValueFor(tabs, "control", "Acceptance", controlPreview)}`,
    compact(controlVerificationBundle(tabs, controlPreview), 28),
  ].join(" | ");
}

function buildControlPulseLine(
  tabs: TabSpec[],
  controlPreview?: TabPreview,
  now: Date = new Date(),
  recomputeFreshness = false,
  deriveUpdated = true,
): string {
  return labeledValue("Pulse", compact(controlPulseDisplayValue(tabs, controlPreview, now, recomputeFreshness, deriveUpdated), 88));
}

function controlHealthLabel(tabs: TabSpec[], controlPreview?: TabPreview): string {
  return `${controlVerificationBundle(tabs, controlPreview)} | alerts ${lineValueFor(tabs, "control", "Alerts", controlPreview)}`;
}

function buildControlFreshnessDetails(
  tabs: TabSpec[],
  controlPreview?: TabPreview,
  now: Date = new Date(),
): string {
  const updated = controlUpdated(tabs, controlPreview);
  return [
    freshnessToken(updated, now),
    controlLoopState(tabs, controlPreview),
    `updated ${updated}`,
    `verify ${controlVerificationBundle(tabs, controlPreview)}`,
  ].join(" | ");
}

function buildControlSnapshotLines(tabs: TabSpec[], controlPreview?: TabPreview, now: Date = new Date()): string[] {
  const explicitTruth = rawLineValueFor(tabs, "control", "Control truth preview", controlPreview);
  return [
    `Snapshot task ${compact(lineValueFor(tabs, "control", "Active task", controlPreview), 18)} | ${controlResultStatus(tabs, controlPreview)}/${controlAcceptance(tabs, controlPreview)}`,
    `Snapshot runtime ${compact(lineValueFor(tabs, "control", "Runtime DB", controlPreview), 24)} | ${compact(controlRuntimeActivity(tabs, controlPreview), 24)} | ${compact(controlArtifactState(tabs, controlPreview), 24)}`,
    `Snapshot loop ${freshnessToken(controlUpdated(tabs, controlPreview), now)} | ${compact(controlLoopState(tabs, controlPreview), 22)} | ${compact(lineValueFor(tabs, "control", "Loop decision", controlPreview), 18)}`,
    `Snapshot verify ${compact(controlVerificationBundle(tabs, controlPreview), 42)}`,
    explicitTruth !== "n/a"
      ? `Snapshot truth ${compact(explicitTruth, 56)}`
      : `Snapshot truth ${compact(controlVerificationBundle(tabs, controlPreview), 24)} | ${compact(controlLoopState(tabs, controlPreview), 22)} | next ${compact(lineValueFor(tabs, "control", "Next task", controlPreview), 24)}`,
  ];
}

function buildControlFreshnessLine(tabs: TabSpec[], controlPreview?: TabPreview, now: Date = new Date()): string {
  return `Freshness ${compact(buildControlFreshnessDetails(tabs, controlPreview, now), 88)}`;
}

function buildControlRuntimeSummaryLine(tabs: TabSpec[], controlPreview?: TabPreview): string {
  const explicit = rawLineValueFor(tabs, "control", "Runtime summary", controlPreview);
  if (explicit !== "n/a") {
    return `Runtime summary ${compact(explicit, 88)}`;
  }
  return `Runtime summary ${compact(lineValueFor(tabs, "control", "Runtime DB", controlPreview), 24)} | ${compact(lineValueFor(tabs, "control", "Session state", controlPreview), 24)} | ${compact(lineValueFor(tabs, "control", "Run state", controlPreview), 22)} | ${compact(lineValueFor(tabs, "control", "Context state", controlPreview), 24)}`;
}

function buildFallbackRuntimeStateValue(tabs: TabSpec[], repoPreview?: TabPreview, controlPreview?: TabPreview): string {
  if (hasControlRuntimeStateSignal(tabs, controlPreview)) {
    const liveRuntimeState = [
      rawLineValueFor(tabs, "control", "Runtime DB", controlPreview),
      lineValueFor(tabs, "control", "Runtime activity", controlPreview),
      lineValueFor(tabs, "control", "Artifact state", controlPreview),
    ]
      .filter((value) => value !== "n/a" && value !== "none")
      .join(" | ");
    if (liveRuntimeState.length > 0) {
      return liveRuntimeState;
    }
  }
  const parsed = parseRepoControlPreview(repoControlPreviewValue(tabs, repoPreview));
  if (!parsed) {
    return "";
  }
  return parsed.runtimeSummary !== "n/a" ? parsed.runtimeSummary : "";
}

function buildControlPreviewFallbackLines(tabs: TabSpec[], repoPreview?: TabPreview, controlPreview?: TabPreview): string[] {
  const parsed = parseRepoControlPreview(repoControlPreviewValue(tabs, repoPreview));
  if (!parsed) {
    return [];
  }
  const runtimeState = buildFallbackRuntimeStateValue(tabs, repoPreview, controlPreview);
  const snapshotTask =
    parsed.task !== "n/a" &&
    parsed.resultStatus !== "n/a" &&
    parsed.acceptance !== "n/a" &&
    parsed.loopState !== "n/a" &&
    parsed.loopDecision !== "n/a"
      ? `Snapshot task ${parsed.task} | ${parsed.resultStatus}/${parsed.acceptance} | ${parsed.loopState} | ${parsed.loopDecision}`
      : null;
  return [
    labeledValue("Repo/control", compact(parsed.raw, 88)),
    labeledValue(
      "Control pulse",
      compact([parsed.freshness, parsed.loopState, `updated ${parsed.updated}`, `verify ${parsed.verificationBundle}`].join(" | "), 88),
    ),
    ...buildControlRepoAlignmentLines(tabs, repoPreview),
    ...(snapshotTask ? [snapshotTask] : []),
    ...(parsed.verificationBundle !== "n/a" && parsed.loopState !== "n/a"
      ? [`Snapshot truth ${compact(parsed.truthPreview, 56)}`]
      : []),
    ...(fallbackRuntimeInventoryValue(tabs, repoPreview, controlPreview) !== "n/a"
      ? [labeledValue("Inventory", compact(fallbackRuntimeInventoryValue(tabs, repoPreview, controlPreview), 88))]
      : []),
    ...(runtimeState
      ? [
          labeledValue("Runtime state", compact(runtimeState, 88)),
          labeledValue("Runtime summary", compact(runtimeState, 88)),
        ]
      : []),
    ...(parsed.task !== "n/a"
      ? [
          labeledValue(
            "Control task",
            compact(
              [
                parsed.task,
                ...(parsed.taskProgress !== "n/a" ? [parsed.taskProgress] : []),
                ...(parsed.resultStatus !== "n/a" && parsed.acceptance !== "n/a"
                  ? [`${parsed.resultStatus}/${parsed.acceptance}`]
                  : []),
              ].join(" | "),
              88,
            ),
          ),
        ]
      : []),
    labeledValue("Control verify", compact(`${parsed.verificationBundle} | next ${parsed.nextTask}`, 88)),
  ];
}

function buildControlPreviewLines(
  tabs: TabSpec[],
  repoPreview?: TabPreview,
  controlPreview?: TabPreview,
  includeExtendedRows = false,
  now: Date = new Date(),
): string[] {
  const hasControlSignal = hasControlSnapshotSignal(tabs, controlPreview);
  if (!hasControlSignal) {
    return [
      "Control Preview",
      ...(controlPreview?.Authority ? [labeledValue("Authority", compact(controlPreview.Authority, 88))] : []),
      ...buildControlPreviewFallbackLines(tabs, repoPreview, controlPreview),
    ];
  }

  const lines = [
    "Control Preview",
    ...(controlPreview?.Authority ? [labeledValue("Authority", compact(controlPreview.Authority, 88))] : []),
    buildControlOverviewLine(tabs, controlPreview),
    buildControlPulseLine(tabs, controlPreview, now),
    ...buildControlRepoAlignmentLines(tabs, repoPreview),
    ...buildControlSnapshotLines(tabs, controlPreview, now),
    buildControlFreshnessLine(tabs, controlPreview, now),
    buildControlRuntimeSummaryLine(tabs, controlPreview),
    `${labeledValue("Task", lineValueFor(tabs, "control", "Active task", controlPreview))} | ${lineValueFor(tabs, "control", "Task progress", controlPreview)}`,
    `${labeledValue("Outcome", controlResultStatus(tabs, controlPreview))} | accept ${controlAcceptance(tabs, controlPreview)}`,
    labeledValue("Runtime", compact(lineValueFor(tabs, "control", "Runtime DB", controlPreview))),
    labeledValue("Sessions", compact(lineValueFor(tabs, "control", "Session state", controlPreview))),
    labeledValue("Runs", compact(lineValueFor(tabs, "control", "Run state", controlPreview))),
    labeledValue("Context", compact(lineValueFor(tabs, "control", "Context state", controlPreview))),
    ...(controlRuntimeInventory(tabs, controlPreview) !== "n/a"
      ? [labeledValue("Inventory", compact(controlRuntimeInventory(tabs, controlPreview), 88))]
      : []),
    `${labeledValue("Loop", compact(controlLoopState(tabs, controlPreview), 22))} | ${compact(lineValueFor(tabs, "control", "Loop decision", controlPreview), 18)}`,
    labeledValue("Health", compact(controlHealthLabel(tabs, controlPreview))),
    labeledValue("Updated", controlUpdated(tabs, controlPreview)),
    labeledValue("Next", compact(lineValueFor(tabs, "control", "Next task", controlPreview))),
    labeledValue("Result", compact(controlLastResult(tabs, controlPreview))),
    labeledValue("Verify", compact(controlVerificationBundle(tabs, controlPreview))),
    labeledValue("Checks", compact(rawLineValueFor(tabs, "control", "Verification checks", controlPreview))),
    labeledValue("Bundle", compact(controlVerificationBundle(tabs, controlPreview))),
    labeledValue("State", compact(lineValueFor(tabs, "control", "Durable state", controlPreview))),
    `${labeledValue("Tools", compact(lineValueFor(tabs, "control", "Toolchain", controlPreview), 24))} | alerts ${compact(lineValueFor(tabs, "control", "Alerts", controlPreview), 18)}`,
  ];

  if (includeExtendedRows) {
    lines.splice(
      11,
      0,
      `${labeledValue("Activity", compact(controlRuntimeActivity(tabs, controlPreview), 24))} | ${compact(controlArtifactState(tabs, controlPreview), 24)}`,
    );
  }

  return lines;
}

function buildVisibleRepoPreviewLines(
  tabs: TabSpec[],
  repoPreview?: TabPreview,
  controlPreview?: TabPreview,
  now: Date = new Date(),
): string[] {
  const hasControlSignal = hasControlSnapshotSignal(tabs, controlPreview);
  const fallbackControlPreview = !hasControlSignal ? parseRepoControlPreview(repoControlPreviewValue(tabs, repoPreview)) : null;
  const prioritizeControlRows = prioritizeLiveControlPreviewRows(tabs, controlPreview);
  const fallbackRuntimeState = !hasControlSignal ? buildFallbackRuntimeStateValue(tabs, repoPreview, controlPreview) : "";
  const repoRiskPreviewLine = buildRepoRiskPreviewLine(tabs, repoPreview);
  const lines = [
    "Repo Preview",
    ...(repoPreview?.Authority ? [labeledValue("Authority", compact(repoPreview.Authority, 88))] : []),
    buildRepoOverviewLine(tabs, repoPreview),
    buildRepoPulseLine(tabs, repoPreview),
    ...buildVisibleRepoSnapshotRows(tabs, repoPreview, controlPreview, now),
    ...(prioritizeControlRows ? [] : [repoRiskPreviewLine]),
    buildRepoControlCorrelationLine(tabs, repoPreview, controlPreview, now),
  ];

  if (hasControlSignal) {
    const snapshotRepoControlLine = `Snapshot repo/control ${compact(buildRepoControlCorrelationValue(tabs, repoPreview, controlPreview, now), 56)}`;
    const controlPulseLine = buildRepoControlPulseLine(tabs, controlPreview, now, Boolean(controlPreview));
    if (controlPulseLine) {
      lines.push(controlPulseLine);
    }
    const runtimeStateLine = buildRepoRuntimeStateLine(tabs, controlPreview);
    if (runtimeStateLine) {
      lines.push(runtimeStateLine);
    }
    const snapshotTaskLine = buildRepoSnapshotTaskLine(tabs, controlPreview);
    if (snapshotTaskLine) {
      lines.push(snapshotTaskLine);
    }
    const snapshotRuntimeLine = buildRepoSnapshotRuntimeLine(tabs, controlPreview);
    if (snapshotRuntimeLine) {
      lines.push(snapshotRuntimeLine);
    }
    const snapshotControlPreviewLine = buildRepoSnapshotControlPreviewLine(tabs, controlPreview, now, Boolean(controlPreview));
    const snapshotFreshnessLine = buildRepoSnapshotFreshnessLine(tabs, repoPreview, controlPreview, now);
    const snapshotVerificationLine = buildRepoSnapshotVerificationLine(tabs, controlPreview);
    if (prioritizeControlRows) {
      lines.push(snapshotRepoControlLine);
      if (snapshotVerificationLine) {
        lines.push(snapshotVerificationLine);
      }
      if (snapshotControlPreviewLine) {
        lines.push(snapshotControlPreviewLine);
      }
      if (snapshotFreshnessLine) {
        lines.push(snapshotFreshnessLine);
      }
    } else {
      if (snapshotControlPreviewLine) {
        lines.push(snapshotControlPreviewLine);
      }
      if (snapshotFreshnessLine) {
        lines.push(snapshotFreshnessLine);
      }
      if (snapshotVerificationLine) {
        lines.push(snapshotVerificationLine);
      }
    }
    const snapshotTruthLine = buildRepoSnapshotTruthLine(tabs, controlPreview);
    if (snapshotTruthLine) {
      lines.push(snapshotTruthLine);
    }
    const controlTaskLine = buildRepoControlTaskLine(tabs, controlPreview);
    if (controlTaskLine) {
      lines.push(controlTaskLine);
    }
    const controlVerificationLine = buildRepoControlVerificationLine(tabs, controlPreview);
    if (controlVerificationLine) {
      lines.push(controlVerificationLine);
    }
  } else if (fallbackRuntimeState) {
    lines.push(labeledValue("Runtime state", compact(fallbackRuntimeState, 88)));
    if (fallbackControlPreview) {
      const fallbackControlPreviewLine = compact(
        [
          fallbackControlPreview.freshness,
          fallbackControlPreview.loopState,
          `updated ${fallbackControlPreview.updated}`,
          `verify ${fallbackControlPreview.verificationBundle}`,
        ].join(" | "),
        56,
      );
      lines.push(
        `Snapshot control preview ${fallbackControlPreviewLine}`,
      );
    }
    lines.push(`Snapshot runtime ${compact(fallbackRuntimeState, 88)}`);
    const fallbackVerificationLine =
      fallbackControlPreview && fallbackControlPreview.verificationBundle !== "n/a"
        ? `Snapshot repo/control verify ${compact(
            `${fallbackControlPreview.verificationBundle} | next ${fallbackControlPreview.nextTask}`,
            56,
          )}`
        : null;
    if (fallbackVerificationLine) {
      lines.push(
        fallbackVerificationLine,
      );
    }
    lines.push(`Runtime summary ${compact(fallbackRuntimeState, 88)}`);
  }

  if (!hasControlSignal && fallbackControlPreview) {
    const fallbackControlPreviewLine = compact(
      [
        fallbackControlPreview.freshness,
        fallbackControlPreview.loopState,
        `updated ${fallbackControlPreview.updated}`,
        `verify ${fallbackControlPreview.verificationBundle}`,
      ].join(" | "),
      56,
    );
    if (!lines.includes(`Snapshot control preview ${fallbackControlPreviewLine}`)) {
      lines.push(`Snapshot control preview ${fallbackControlPreviewLine}`);
    }
    if (fallbackControlPreview.verificationBundle !== "n/a") {
      const fallbackVerificationLine = `Snapshot repo/control verify ${compact(
        `${fallbackControlPreview.verificationBundle} | next ${fallbackControlPreview.nextTask}`,
        56,
      )}`;
      if (!lines.includes(fallbackVerificationLine)) {
        lines.push(fallbackVerificationLine);
      }
    }
  }

  if (!hasControlSignal && fallbackControlPreview && fallbackControlPreview.verificationBundle !== "n/a" && fallbackControlPreview.loopState !== "n/a") {
    lines.push(`Snapshot truth ${compact(fallbackControlPreview.truthPreview, 56)}`);
  }

  if (prioritizeControlRows) {
    lines.push(repoRiskPreviewLine);
  }

  const {repoRiskSummary, hotspotSummary} = repoPaneSectionSummaries(tabs, repoPreview, controlPreview, now);
  const visibleHotspotLines = prioritizeControlRows
    ? hotspotSummary
    : [
        labeledValue("Changed", compact(lineValueFor(tabs, "repo", "Changed hotspots", repoPreview))),
        labeledValue("Summary", compact(buildLeadHotspotPreviewLine(tabs, repoPreview))),
        `${labeledValue("Lead change", compact(lineValueFor(tabs, "repo", "Primary changed hotspot", repoPreview), 20))} | ${compact(lineValueFor(tabs, "repo", "Primary changed path", repoPreview), 28)}`,
        labeledValue("Lead file", compact(lineValueFor(tabs, "repo", "Primary file hotspot", repoPreview))),
        labeledValue("Lead dep", compact(lineValueFor(tabs, "repo", "Primary dependency hotspot", repoPreview))),
      ];
  const visibleRepoRiskLines = prioritizeControlRows
    ? [
        ...repoRiskSummary,
        ...[
          buildBranchDivergenceLine(tabs, repoPreview),
          buildDetachedPeersLine(tabs, repoPreview),
        ].filter((line) => !line.endsWith("n/a") && !line.endsWith("none")),
      ]
    : [
        labeledValue("Risk", compact(lineValueFor(tabs, "repo", "Repo risk", repoPreview), 88)),
        buildTopologyCountLine(tabs, repoPreview),
        labeledValue("Warnings", compact(lineValueFor(tabs, "repo", "Topology warnings", repoPreview), 88)),
        labeledValue("Members", compact(lineValueFor(tabs, "repo", "Topology warning members", repoPreview), 88)),
        `${labeledValue("Severity", compact(topologySeverityValue(tabs, repoPreview), 16))} | warning ${compact(lineValueFor(tabs, "repo", "Primary warning", repoPreview), 44)}`,
        buildTopologySignalLine(tabs, repoPreview),
        buildBranchDivergenceLine(tabs, repoPreview),
        buildDetachedPeersLine(tabs, repoPreview),
        labeledValue("Lead peer", compact(lineValueFor(tabs, "repo", "Primary topology peer", repoPreview), 88)),
        labeledValue("Pressure", compact(lineValueFor(tabs, "repo", "Topology pressure", repoPreview), 88)),
      ];

  return [
    ...lines,
    buildTopologyPressurePreviewLine(tabs, repoPreview),
    buildSnapshotHotspotPressureLine(tabs, repoPreview),
    "Hotspot Focus",
    ...uniqueSidebarLines(visibleHotspotLines),
    "Repo Risk",
    ...uniqueSidebarLines(visibleRepoRiskLines),
  ];
}

function buildVisibleControlPreviewLines(
  tabs: TabSpec[],
  repoPreview?: TabPreview,
  controlPreview?: TabPreview,
  now: Date = new Date(),
): string[] {
  const hasControlSignal = hasControlSnapshotSignal(tabs, controlPreview);
  if (!hasControlSignal) {
    return [
      "Control Preview",
      ...(controlPreview?.Authority ? [labeledValue("Authority", compact(controlPreview.Authority, 88))] : []),
      ...buildControlPreviewFallbackLines(tabs, repoPreview),
    ];
  }

  return [
    "Control Preview",
    ...(controlPreview?.Authority ? [labeledValue("Authority", compact(controlPreview.Authority, 88))] : []),
    buildControlOverviewLine(tabs, controlPreview),
    buildControlPulseLine(tabs, controlPreview, now, Boolean(controlPreview)),
    ...buildControlRepoAlignmentLines(tabs, repoPreview, 56),
    buildControlRuntimeSummaryLine(tabs, controlPreview),
    `${labeledValue("Loop", compact(lineValueFor(tabs, "control", "Loop state", controlPreview), 22))} | ${compact(lineValueFor(tabs, "control", "Loop decision", controlPreview), 18)}`,
    labeledValue("Verify", compact(lineValueFor(tabs, "control", "Verification bundle", controlPreview))),
    labeledValue("Next", compact(lineValueFor(tabs, "control", "Next task", controlPreview))),
  ];
}

export function buildContextSidebarLines(
  tabs: TabSpec[],
  activeTabTitle: string,
  provider: string,
  model: string,
  bridgeStatus: string,
  repoPreview?: TabPreview,
  controlPreview?: TabPreview,
  now: Date = new Date(),
): string[] {
  const activeLabel = normalizedContextValue(activeTabTitle);
  const bridgeLabel = normalizedContextValue(bridgeStatus);
  const providerLabel = normalizedContextValue(provider);
  const modelLabel = normalizedContextValue(model);
  const effectiveRepoPreview = withRepoControlPreviewFallback(tabs, repoPreview, controlPreview);
  return [
    "Active",
    `${activeLabel} | bridge ${bridgeLabel}`,
    `Model ${providerLabel} ${modelLabel}`,
    ...buildRepoPreviewLines(tabs, effectiveRepoPreview, controlPreview, true, now),
    labeledValue("Inventory", compact(lineValueFor(tabs, "repo", "Inventory", effectiveRepoPreview))),
    labeledValue("Mix", compact(lineValueFor(tabs, "repo", "Language mix", effectiveRepoPreview))),
    "Ontology",
    `Ver ${lineValueFor(tabs, "ontology", "Version")} | concepts ${lineValueFor(tabs, "ontology", "Concept count")}`,
    ...buildControlPreviewLines(tabs, effectiveRepoPreview, controlPreview, true, now),
    "Models",
    `${labeledValue("Active", lineValueFor(tabs, "models", "Active"))} | ${lineValueFor(tabs, "models", "Strategy")}`,
    `${labeledValue("Route", lineValueFor(tabs, "models", "Route"))} | fallback ${lineValueFor(tabs, "models", "Fallbacks")}`,
    "Agents",
    `${labeledValue("Runs", lineValueFor(tabs, "agents", "Active runs"))} | ${lineValueFor(tabs, "agents", "Recent actions")}`,
    `${labeledValue("Routes", lineValueFor(tabs, "agents", "Routes"))} | ${lineValueFor(tabs, "agents", "Primary route")}`,
    "Evolution",
    `${labeledValue("Domains", lineValueFor(tabs, "evolution", "Domains"))} | ${lineValueFor(tabs, "evolution", "Primary domain")}`,
  ];
}

export function buildVisibleContextSidebarLines(
  tabs: TabSpec[],
  activeTabTitle: string,
  provider: string,
  model: string,
  bridgeStatus: string,
  repoPreview?: TabPreview,
  controlPreview?: TabPreview,
  now: Date = new Date(),
): string[] {
  const activeLabel = normalizedContextValue(activeTabTitle);
  const bridgeLabel = normalizedContextValue(bridgeStatus);
  const providerLabel = normalizedContextValue(provider);
  const modelLabel = normalizedContextValue(model);
  const effectiveRepoPreview = withRepoControlPreviewFallback(tabs, repoPreview, controlPreview);
  return [
    "Active",
    `${activeLabel} | bridge ${bridgeLabel}`,
    `Model ${providerLabel} ${modelLabel}`,
    ...buildVisibleRepoPreviewLines(tabs, effectiveRepoPreview, controlPreview, now),
    ...buildVisibleControlPreviewLines(tabs, effectiveRepoPreview, controlPreview, now),
    "Ontology",
    `Ver ${lineValueFor(tabs, "ontology", "Version")} | concepts ${lineValueFor(tabs, "ontology", "Concept count")}`,
  ];
}

function SidebarInner({mode, outline, activeTabTitle, provider, model, bridgeStatus, tabs, repoPreview, controlPreview, compact = false}: Props): React.ReactElement {
  const contextLines = buildVisibleContextSidebarLines(
    tabs,
    activeTabTitle,
    provider,
    model,
    bridgeStatus,
    repoPreview,
    controlPreview,
  );
  return (
    <Box width={compact ? 22 : 34} flexDirection="column" borderStyle="round" borderColor={THEME.ink} paddingX={1} marginRight={1}>
      <Text color={THEME.wave} bold>{mode === "toc" ? "TOC" : mode === "context" ? "Context" : "Help"}</Text>
      <Text color={THEME.stone}> </Text>
      {mode === "toc" &&
        outline.slice(0, compact ? 8 : 16).map((item) => (
          <Text key={item.id} color={item.depth === 1 ? THEME.foam : THEME.stone}>
            {" ".repeat((item.depth - 1) * 2)}
            {item.depth === 1 ? "• " : "· "}
            {item.label}
          </Text>
        ))}
      {mode === "context" && (
        <>
          {contextLines.map((line, index) => (
            <Text
              key={`context-${index}`}
              color={["Active", "Repo Preview", "Hotspot Focus", "Repo Risk", "Ontology", "Control Preview", "Models", "Agents", "Evolution"].includes(line) ? THEME.foam : THEME.stone}
            >
              {line}
            </Text>
          ))}
        </>
      )}
      {mode === "help" && (
        <>
          <Text color={THEME.parchment} bold>Controls</Text>
          <Text color={THEME.stone}>Enter send prompt</Text>
          <Text color={THEME.stone}>Tab or [ ] move tabs</Text>
          <Text color={THEME.stone}>Ctrl+P route picker</Text>
          <Text color={THEME.stone}>Ctrl+K pane switcher</Text>
          <Text color={THEME.stone}>Ctrl+B sidebar</Text>
          <Text color={THEME.stone}>1/2/3 toc context help</Text>
          <Text color={THEME.stone}>Ctrl+L refresh current pane</Text>
          <Text color={THEME.stone}>Ctrl+X/F/V pane actions</Text>
          <Text color={THEME.stone}>Ctrl+W close closable tab</Text>
        </>
      )}
    </Box>
  );
}

export const Sidebar = React.memo(SidebarInner);
