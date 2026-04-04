import React from "react";
import {Box, Text} from "ink";

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
import type {TabPreview, TranscriptLine} from "../types";
import {THEME} from "../theme";
import {isGenericVerificationLabel, parseVerificationBundle, verificationBundleLabel} from "../verification";

type RepoSection = {
  title: string;
  rows: string[];
};

type DetailRow = {
  value: string;
  tone?: "strong" | "muted";
};

type Props = {
  title: string;
  preview?: TabPreview;
  controlPreview?: TabPreview;
  lines: TranscriptLine[];
  controlLines?: TranscriptLine[];
  scrollOffset?: number;
  windowSize?: number;
  selectedSectionIndex?: number;
};

export function sectionCardSummaries(section: RepoSection): string[] {
  const multiWarningPrefixes = ["Warnings ", "Snapshot topology "];
  const multiWarningCount = section.rows
    .filter((row) => multiWarningPrefixes.some((prefix) => row.startsWith(prefix)))
    .map((row) => row.match(/\b(\d+)\s+warning(?:s)?\b/i)?.[1] ?? row.match(/\bwarnings\s+(\d+)/i)?.[1] ?? "")
    .find((count) => Number.parseInt(count, 10) > 1);
  const includeWarningMembers = Boolean(multiWarningCount);
  const operatorSnapshotHasTopologyPressure = section.rows.some((row) => row.startsWith("Snapshot topology pressure "));
  const operatorSnapshotHasDetachedPeers = section.rows.some(
    (row) => row.startsWith("Snapshot detached peers ") && row !== "Snapshot detached peers none",
  );
  const operatorSnapshotHasBranchDivergence = section.rows.some(
    (row) => row.startsWith("Snapshot branch divergence ") && !row.endsWith("n/a"),
  );
  const operatorSnapshotHasControlPreview = section.rows.some((row) => row.startsWith("Snapshot control preview "));
  const operatorSnapshotHasRuntime = section.rows.some((row) => row.startsWith("Snapshot runtime "));
  const operatorSnapshotHasVerification = section.rows.some(
    (row) => row.startsWith("Snapshot repo/control verify ") || row.startsWith("Snapshot verify "),
  );
  const snapshotHasDetachedPeers = section.rows.some(
    (row) => row.startsWith("Detached peers ") && row !== "Detached peers none",
  );
  const snapshotHasBranchDivergence = section.rows.some(
    (row) => row.startsWith("Branch divergence ") && !row.endsWith("n/a"),
  );
  const snapshotHasRuntime = section.rows.some((row) => row.startsWith("Snapshot runtime "));
  const snapshotHasVerification = section.rows.some(
    (row) => row.startsWith("Snapshot repo/control verify ") || row.startsWith("Snapshot verify "),
  );
  const sectionHasRuntime = section.rows.some((row) => row.startsWith("Runtime "));
  const sectionHasVerification = section.rows.some((row) => row.startsWith("Verify "));
  const sectionHasControl = section.rows.some((row) => row.startsWith("Control "));
  const snapshotHasTopologyWarnings = section.rows.some((row) => {
    if (!row.startsWith("Warnings ")) {
      return false;
    }
    const warningSummary = row.slice("Warnings ".length).trim().toLowerCase();
    return !(warningSummary === "none" || warningSummary.startsWith("none |") || warningSummary.startsWith("0"));
  });
  const snapshotTopologyStable = !snapshotHasTopologyWarnings && !snapshotHasDetachedPeers;
  const priorityPrefixesBySection: Record<string, string[]> = {
    "Operator Snapshot": [
      "Snapshot branch ",
      "Snapshot dirty ",
      "Snapshot topology ",
      ...(includeWarningMembers ? ["Snapshot warning members "] : []),
      ...(operatorSnapshotHasDetachedPeers || operatorSnapshotHasBranchDivergence ? ["Snapshot branch divergence "] : []),
      ...(operatorSnapshotHasTopologyPressure ? ["Snapshot topology pressure "] : []),
      ...(operatorSnapshotHasRuntime || operatorSnapshotHasVerification
        ? [
            ...(operatorSnapshotHasControlPreview ? ["Snapshot control preview "] : []),
            ...(operatorSnapshotHasRuntime ? ["Snapshot runtime "] : []),
            "Snapshot hotspot summary ",
            "Snapshot repo risk ",
            ...(operatorSnapshotHasVerification ? ["Snapshot repo/control verify ", "Snapshot verify "] : []),
            "Snapshot repo/control ",
          ]
        : ["Snapshot repo risk ", "Snapshot repo/control ", "Snapshot hotspot summary "]),
    ],
    Snapshot: snapshotTopologyStable
      ? [
          "Branch ",
          "Dirty ",
          ...(snapshotHasRuntime || snapshotHasVerification
            ? [
                ...(snapshotHasRuntime ? ["Snapshot runtime "] : []),
                ...(snapshotHasVerification ? ["Snapshot repo/control verify ", "Snapshot verify "] : []),
                "Snapshot hotspot summary ",
                "Snapshot repo/control ",
              ]
            : ["Snapshot hotspot summary ", "Snapshot repo/control ", "Snapshot repo risk "]),
          ...(snapshotHasBranchDivergence ? ["Branch divergence "] : []),
        ]
      : [
          "Branch ",
          "Dirty ",
          ...(snapshotHasRuntime || snapshotHasVerification
            ? [
                ...(snapshotHasRuntime ? ["Snapshot runtime "] : []),
                ...(snapshotHasVerification ? ["Snapshot repo/control verify ", "Snapshot verify "] : []),
              ]
            : ["Snapshot repo risk "]),
          ...(snapshotHasBranchDivergence ? ["Branch divergence "] : []),
          ...(snapshotHasDetachedPeers ? ["Detached peers "] : []),
          "Warnings ",
          ...(includeWarningMembers ? ["Warning members "] : []),
          "Snapshot hotspot summary ",
          "Snapshot repo/control ",
          ...(snapshotHasRuntime || snapshotHasVerification ? [] : []),
        ],
    "Repo Risk": [
      "Repo ",
      ...(sectionHasControl || sectionHasRuntime || sectionHasVerification
        ? [
            ...(sectionHasControl ? ["Control "] : []),
            ...(sectionHasRuntime ? ["Runtime "] : []),
            ...(sectionHasVerification ? ["Verify "] : []),
          ]
        : []),
      ...(includeWarningMembers ? ["Warning members ", "Warnings "] : []),
      "Topology signal ",
      "Lead peer ",
      "Branch divergence ",
      "Detached peers ",
      ...(includeWarningMembers ? [] : ["Warnings "]),
    ],
    Git: ["Branch ", "Counts ", "Pressure ", "Risk "],
    Topology: ["Status ", "Signal ", "Lead peer ", "Branch divergence ", "Detached peers ", "Warnings "],
    Hotspots: [
      "Summary ",
      ...(sectionHasControl || sectionHasRuntime || sectionHasVerification
        ? [
            ...(sectionHasControl ? ["Control "] : []),
            ...(sectionHasRuntime ? ["Runtime "] : []),
            ...(sectionHasVerification ? ["Verify "] : []),
          ]
        : []),
      "Pressure ",
      "Lead dep ",
      "Lead path ",
      "Lead file ",
    ],
    Control: ["Task ", "Outcome ", "Health ", "Verify ", "Next "],
    Inventory: ["Inventory ", "Mix "],
  };
  const guaranteedPrefixesBySection: Record<string, string[]> = {
    "Operator Snapshot": [
      "Snapshot branch ",
      "Snapshot dirty ",
      "Snapshot topology ",
      ...(includeWarningMembers ? ["Snapshot warning members "] : []),
      "Snapshot hotspot summary ",
    ],
    Snapshot: ["Branch ", "Dirty ", ...(includeWarningMembers ? ["Warning members "] : []), "Snapshot hotspot summary "],
  };
  const maxSummariesBySection: Record<string, number> = {
    "Operator Snapshot":
      operatorSnapshotHasRuntime && operatorSnapshotHasControlPreview
        ? includeWarningMembers
          ? 12
          : 11
        : operatorSnapshotHasRuntime
          ? includeWarningMembers
            ? 11
            : 10
          : operatorSnapshotHasVerification
            ? includeWarningMembers
              ? 10
              : 9
            : includeWarningMembers
              ? 7
              : 6,
    Snapshot: snapshotHasRuntime || snapshotHasVerification ? (includeWarningMembers ? 9 : 8) : includeWarningMembers ? 7 : 6,
    "Repo Risk": sectionHasRuntime || sectionHasVerification ? (includeWarningMembers ? 7 : 6) : includeWarningMembers ? 5 : 4,
    Git: 4,
    Topology: 4,
    Hotspots: sectionHasRuntime || sectionHasVerification ? 6 : 4,
    Control: 4,
    Inventory: 2,
  };
  const priorityPrefixes = priorityPrefixesBySection[section.title] ?? [];
  const guaranteedPrefixes = guaranteedPrefixesBySection[section.title] ?? [];
  const guaranteed = guaranteedPrefixes
    .map((prefix) => section.rows.find((row) => row.startsWith(prefix)))
    .filter((row): row is string => Boolean(row));
  const selected = priorityPrefixes
    .map((prefix) => section.rows.find((row) => row.startsWith(prefix)))
    .filter((row): row is string => Boolean(row));
  const unique = Array.from(new Set([...guaranteed, ...selected]));
  if (unique.length > 0) {
    return unique.slice(0, maxSummariesBySection[section.title] ?? 4);
  }
  return section.rows[0] ? [section.rows[0]] : [];
}

function clampSectionIndex(index: number, sections: RepoSection[]): number {
  if (sections.length === 0) {
    return 0;
  }
  return Math.min(Math.max(index, 0), sections.length - 1);
}

function uniqueRows(rows: string[]): string[] {
  return Array.from(new Set(rows));
}

function rawPreviewValue(preview: TabPreview | undefined, lines: TranscriptLine[], label: string): string {
  const value = preview?.[label];
  if (typeof value === "string" && value.length > 0) {
    return value;
  }
  const match = lines.find((line) => line.text.startsWith(`${label}: `));
  if (!match) {
    return "n/a";
  }
  return match.text.slice(label.length + 2).trim();
}

function repoControlPreviewValue(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const value = rawPreviewValue(preview, lines, "Repo/control preview");
  return value === "n/a" ? "" : value;
}

function repoControlSegment(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  key: "warn" | "peer" | "peers" | "drift" | "markers" | "divergence" | "detached" | "hotspot" | "path" | "dep" | "inbound",
): string {
  return extractRepoControlSegment(repoControlPreviewValue(preview, lines), key);
}

function repoControlDirtySegment(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const parsed = parseRepoControlPreview(repoControlPreviewValue(preview, lines));
  if (parsed?.dirtyState && parsed.dirtyState !== "n/a") {
    return parsed.dirtyState;
  }
  const raw = repoControlPreviewValue(preview, lines);
  if (!hasPreviewSignal(raw) || raw === "none") {
    return "";
  }
  return raw.match(new RegExp(`\\bdirty\\s+(.+?)(?=\\s+\\|\\s+${REPO_CONTROL_SEGMENT_BOUNDARY}|$)`, "i"))?.[1]?.trim() ?? "";
}

function repoTruthDirtySegment(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return parseRepoTruthPreview(rawPreviewValue(preview, lines, "Repo truth preview"))?.dirtyState ?? "";
}

function repoTruthWarningSegment(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return parseRepoTruthPreview(rawPreviewValue(preview, lines, "Repo truth preview"))?.warning ?? "";
}

function repoTruthHotspotSegment(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return parseRepoTruthPreview(rawPreviewValue(preview, lines, "Repo truth preview"))?.hotspot ?? "";
}

function repoTruthBranchParts(preview: TabPreview | undefined, lines: TranscriptLine[]): {branch: string; head: string} | null {
  const parsed = parseRepoTruthPreview(rawPreviewValue(preview, lines, "Repo truth preview"));
  if (!parsed) {
    return null;
  }
  return {branch: parsed.branch, head: parsed.head};
}

function repoControlBranchParts(preview: TabPreview | undefined, lines: TranscriptLine[]): {branch: string; head: string} | null {
  const parsed = parseRepoControlPreview(repoControlPreviewValue(preview, lines));
  if (!parsed) {
    return null;
  }
  return {branch: parsed.branchName, head: parsed.head};
}

function parseBranchSyncPreview(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
): {branchStatus: string; ahead: string; behind: string} | null {
  return parseBranchSyncPreviewValue(rawPreviewValue(preview, lines, "Branch sync preview"));
}

function parseRepoControlBranchPreview(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
): {branchStatus: string; ahead: string; behind: string} | null {
  return parseRepoControlBranchPreviewValue(repoControlPreviewValue(preview, lines));
}

function deriveBranchValue(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Branch");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  return repoTruthBranchParts(preview, lines)?.branch || repoControlBranchParts(preview, lines)?.branch || explicit;
}

function deriveHeadValue(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Head");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  return repoTruthBranchParts(preview, lines)?.head || repoControlBranchParts(preview, lines)?.head || explicit;
}

function deriveBranchStatusValue(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Branch status");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  return parseBranchSyncPreview(preview, lines)?.branchStatus || parseRepoControlBranchPreview(preview, lines)?.branchStatus || explicit;
}

function deriveBranchCountValue(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  label: "Ahead" | "Behind",
): string {
  const explicit = rawPreviewValue(preview, lines, label);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const parsed = parseBranchSyncPreview(preview, lines);
  if (parsed) {
    return label === "Ahead" ? parsed.ahead || explicit : parsed.behind || explicit;
  }
  const repoControlParsed = parseRepoControlBranchPreview(preview, lines);
  return label === "Ahead" ? repoControlParsed?.ahead || explicit : repoControlParsed?.behind || explicit;
}

function deriveDirtyCountFromRepoTruth(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  label: "staged" | "unstaged" | "untracked",
): string {
  const explicitLabel = label.charAt(0).toUpperCase() + label.slice(1);
  const explicit = rawPreviewValue(preview, lines, explicitLabel);
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const dirtySegment = repoTruthDirtySegment(preview, lines);
  const candidate = dirtySegment || repoControlDirtySegment(preview, lines);
  if (!candidate) {
    const parsed = parseRepoControlPreview(repoControlPreviewValue(preview, lines));
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

function deriveDirtyLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Dirty");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const staged = deriveDirtyCountFromRepoTruth(preview, lines, "staged");
  const unstaged = deriveDirtyCountFromRepoTruth(preview, lines, "unstaged");
  const untracked = deriveDirtyCountFromRepoTruth(preview, lines, "untracked");
  if ([staged, unstaged, untracked].every((value) => value !== "n/a")) {
    return `${staged} staged, ${unstaged} unstaged, ${untracked} untracked`;
  }
  return explicit;
}

function deriveControlRuntimeFreshness(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Runtime freshness");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  return parseControlPulsePreview(rawPreviewValue(preview, lines, "Control pulse preview")).runtimeFreshness ?? "n/a";
}

function deriveControlLoopState(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Loop state");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  return parseRuntimeFreshness(deriveControlRuntimeFreshness(preview, lines)).loopState ?? "n/a";
}

function deriveControlUpdated(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Updated");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  return parseRuntimeFreshness(deriveControlRuntimeFreshness(preview, lines)).updated ?? "n/a";
}

function deriveControlLastResult(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Last result");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  return parseControlPulsePreview(rawPreviewValue(preview, lines, "Control pulse preview")).lastResult ?? "n/a";
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

function deriveControlResultStatus(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Result status");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  return parseControlOutcome(deriveControlLastResult(preview, lines))?.resultStatus ?? explicit;
}

function deriveControlAcceptance(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Acceptance");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  return parseControlOutcome(deriveControlLastResult(preview, lines))?.acceptance ?? explicit;
}

function deriveControlVerificationBundle(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicitBundle = rawPreviewValue(preview, lines, "Verification bundle");
  if (hasPreviewSignal(explicitBundle) && explicitBundle !== "none" && !isGenericVerificationLabel(explicitBundle)) {
    return explicitBundle;
  }
  const summary = rawPreviewValue(preview, lines, "Verification summary");
  const checks = rawPreviewValue(preview, lines, "Verification checks");
  const parsed = parseVerificationBundle(checks, summary);
  if (parsed.length > 0) {
    return verificationBundleLabel(parsed);
  }
  const compactBundle = parseRuntimeFreshness(deriveControlRuntimeFreshness(preview, lines)).verificationBundle ?? "";
  if (hasPreviewSignal(compactBundle) && compactBundle !== "none") {
    return compactBundle;
  }
  if (hasPreviewSignal(summary) && summary !== "none" && !isGenericVerificationLabel(summary)) {
    return summary;
  }
  return explicitBundle;
}

function deriveRuntimeActivity(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Runtime activity");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const sessionState = rawPreviewValue(preview, lines, "Session state");
  const runState = rawPreviewValue(preview, lines, "Run state");
  const sessions = sessionState.match(/\b(\d+)\s+sessions\b/i)?.[1];
  const runs = runState.match(/\b(\d+)\s+runs\b/i)?.[1];
  if (sessions || runs) {
    return [`Sessions=${sessions ?? "n/a"}`, runs ? `Runs=${runs}` : ""].filter((part) => part.length > 0).join("  ");
  }
  const runtimeSummary = rawPreviewValue(preview, lines, "Runtime summary");
  const summarySessions = runtimeSummary.match(/\b(\d+)\s+sessions\b/i)?.[1];
  const summaryRuns = runtimeSummary.match(/\b(\d+)\s+runs\b/i)?.[1];
  if (summarySessions || summaryRuns) {
    return [`Sessions=${summarySessions ?? "n/a"}`, summaryRuns ? `Runs=${summaryRuns}` : ""]
      .filter((part) => part.length > 0)
      .join("  ");
  }
  return explicit;
}

function deriveArtifactState(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Artifact state");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const contextState = rawPreviewValue(preview, lines, "Context state");
  const artifacts = contextState.match(/\b(\d+)\s+artifacts\b/i)?.[1];
  const contextBundles = contextState.match(/\b(\d+)\s+context bundles\b/i)?.[1];
  if (artifacts || contextBundles) {
    return [`Artifacts=${artifacts ?? "n/a"}`, contextBundles ? `ContextBundles=${contextBundles}` : ""]
      .filter((part) => part.length > 0)
      .join("  ");
  }
  const runtimeSummary = rawPreviewValue(preview, lines, "Runtime summary");
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

function buildRuntimeInventoryFromCandidates(candidates: string[]): string {
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

function deriveRuntimeInventoryLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return buildRuntimeInventoryFromCandidates([
    rawPreviewValue(preview, lines, "Runtime activity"),
    rawPreviewValue(preview, lines, "Artifact state"),
    rawPreviewValue(preview, lines, "Session state"),
    rawPreviewValue(preview, lines, "Context state"),
    rawPreviewValue(preview, lines, "Runtime summary"),
  ]);
}

function firstPressureSegment(value: string): string {
  return value
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.length > 0) ?? value.trim();
}

function derivePrimaryWarning(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Primary warning");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = normalizePrimaryWarning(repoControlSegment(preview, lines, "warn"));
  if (hasPreviewSignal(fromRepoControl) && fromRepoControl !== "none") {
    return fromRepoControl;
  }
  const warningFromTruth = repoTruthWarningSegment(preview, lines);
  if (hasPreviewSignal(warningFromTruth) && warningFromTruth !== "none") {
    return firstDelimitedSegment(warningFromTruth);
  }
  const previewWarning = [
    rawPreviewValue(preview, lines, "Topology preview"),
    rawPreviewValue(preview, lines, "Risk preview"),
    rawPreviewValue(preview, lines, "Repo risk preview"),
  ]
    .map((candidate) => deriveWarningFromPreviewSegments(candidate))
    .find((candidate) => hasPreviewSignal(candidate) && candidate !== "none");
  if (previewWarning) {
    return previewWarning;
  }
  const topologyRisk = rawPreviewValue(preview, lines, "Topology risk");
  if (hasPreviewSignal(topologyRisk) && topologyRisk !== "stable" && topologyRisk !== "none") {
    return topologyRisk;
  }
  return explicit || topologyRisk || "n/a";
}

function deriveTopologyWarnings(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Topology warnings");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = repoControlSegment(preview, lines, "warn");
  if (hasPreviewSignal(fromRepoControl) && fromRepoControl !== "none") {
    if (/^\d+\s*\(.+\)$/.test(fromRepoControl)) {
      return fromRepoControl;
    }
    const parsed = parseRepoControlPreview(repoControlPreviewValue(preview, lines));
    if (parsed && parsed.topologyWarningCount !== "0" && parsed.topologyWarningMembers !== "none") {
      return `${parsed.topologyWarningCount} (${parsed.topologyWarningMembers.replace(/\s*;\s*/g, ", ")})`;
    }
    return `1 (${normalizePrimaryWarning(fromRepoControl)})`;
  }
  const warningFromTruth = repoTruthWarningSegment(preview, lines);
  if (!hasPreviewSignal(warningFromTruth) || warningFromTruth === "none") {
    const primaryWarning = derivePrimaryWarning(preview, lines);
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

function derivePrimaryTopologyPeer(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Primary topology peer");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = repoControlSegment(preview, lines, "peer");
  if (hasPreviewSignal(fromRepoControl) && fromRepoControl !== "none") {
    return fromRepoControl;
  }
  return (
    [
      rawPreviewValue(preview, lines, "Topology preview"),
      rawPreviewValue(preview, lines, "Risk preview"),
      rawPreviewValue(preview, lines, "Repo risk preview"),
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

function derivePrimaryPeerDrift(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Primary peer drift");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = repoControlSegment(preview, lines, "drift");
  if (hasPreviewSignal(fromRepoControl) && fromRepoControl !== "none") {
    return fromRepoControl;
  }
  const primaryPeer = derivePrimaryTopologyPeer(preview, lines);
  const primaryWarning = derivePrimaryWarning(preview, lines);
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

function deriveTopologyPeers(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Topology peers");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = repoControlSegment(preview, lines, "peers");
  if (hasPreviewSignal(fromRepoControl) && fromRepoControl !== "none") {
    return fromRepoControl;
  }
  const primaryPeer = derivePrimaryTopologyPeer(preview, lines);
  if (hasPreviewSignal(primaryPeer) && primaryPeer !== "none") {
    return primaryPeer;
  }
  return explicit;
}

function deriveTopologyPeerCount(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Topology peer count");
  if (hasPreviewSignal(explicit)) {
    return explicit;
  }
  const topologyStatus = rawPreviewValue(preview, lines, "Topology status");
  const statusCount = topologyStatus.match(/\((?:\d+\s+warning(?:s)?(?:,\s*)?)?(\d+)\s+peer(?:s)?\)/i)?.[1];
  if (statusCount) {
    return statusCount;
  }
  const compactRepoControlCount = deriveNumericPeerCount(repoControlSegment(preview, lines, "peers"));
  if (compactRepoControlCount) {
    return compactRepoControlCount;
  }
  const pressureCount = derivePeerNamesFromPressure(rawPreviewValue(preview, lines, "Topology pressure")).length;
  if (pressureCount > 0) {
    return String(pressureCount);
  }
  const topologyPeers = deriveTopologyPeers(preview, lines);
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

function deriveTopologyStatus(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Topology status");
  if (hasPreviewSignal(explicit)) {
    return explicit;
  }
  const peerCount = deriveTopologyPeerCount(preview, lines);
  const warningCount = previewValue(preview, lines, "Topology warnings").match(/^(\d+)/)?.[1];
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

function deriveTopologyWarningMembers(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const warnings = previewValue(preview, lines, "Topology warnings");
  if (warnings === "0") {
    return "none";
  }
  const members = warnings.match(/^\d+\s*\((.+)\)$/)?.[1]?.trim();
  if (members && members.length > 0) {
    return members;
  }
  return warnings;
}

function derivePeerDriftMarkers(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Peer drift markers");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = repoControlSegment(preview, lines, "markers");
  if (hasPreviewSignal(fromRepoControl) && fromRepoControl !== "none") {
    return fromRepoControl;
  }
  const primaryPeer = derivePrimaryTopologyPeer(preview, lines);
  const primaryPeerName = primaryPeer.match(/^(.+?)\s+\(/)?.[1]?.trim() || "";
  const primaryPeerDrift = derivePrimaryPeerDrift(preview, lines);
  const extras = derivePeerNamesFromPressure(rawPreviewValue(preview, lines, "Topology pressure"))
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

function deriveDetachedPeers(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Detached peers");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const fromRepoControl = repoControlSegment(preview, lines, "detached");
  if (hasPreviewSignal(fromRepoControl)) {
    return fromRepoControl;
  }
  const summaries = [
    ...deriveTopologyPeers(preview, lines)
      .split(";")
      .map((part) => part.trim())
      .filter((part) => part.length > 0),
    derivePrimaryTopologyPeer(preview, lines),
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
  const primaryPeerDrift = derivePrimaryPeerDrift(preview, lines);
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

function derivePrimaryChangedHotspot(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Primary changed hotspot");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return normalizeChangedHotspotLabel(explicit);
  }
  const repoControlHotspot = repoControlSegment(preview, lines, "hotspot");
  if (hasPreviewSignal(repoControlHotspot) && repoControlHotspot !== "none") {
    return normalizeChangedHotspotLabel(repoControlHotspot);
  }
  const candidates = [
    repoTruthHotspotSegment(preview, lines),
    rawPreviewValue(preview, lines, "Lead hotspot preview"),
    rawPreviewValue(preview, lines, "Hotspot pressure preview"),
    rawPreviewValue(preview, lines, "Hotspot summary"),
  ];
  for (const candidate of candidates) {
    const derived = deriveHotspotMatch(candidate, [/(?:^|\|\s*|;\s*)change\s+([^|;]+?)(?=\s*(?:\||;|$))/i]);
    if (derived) {
      return derived;
    }
  }
  const changedHotspots = firstDelimitedSegment(rawPreviewValue(preview, lines, "Changed hotspots"));
  if (hasPreviewSignal(changedHotspots) && changedHotspots !== "none") {
    return normalizeChangedHotspotLabel(changedHotspots);
  }
  return explicit;
}

function derivePrimaryChangedPath(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Primary changed path");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const repoControlPath = repoControlSegment(preview, lines, "path");
  if (hasPreviewSignal(repoControlPath) && repoControlPath !== "none") {
    return repoControlPath;
  }
  const candidates = [
    repoTruthHotspotSegment(preview, lines),
    rawPreviewValue(preview, lines, "Lead hotspot preview"),
    rawPreviewValue(preview, lines, "Hotspot summary"),
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
  const changedPath = firstDelimitedSegment(rawPreviewValue(preview, lines, "Changed paths"));
  if (hasPreviewSignal(changedPath) && changedPath !== "none") {
    return changedPath;
  }
  return explicit;
}

function derivePrimaryDependencyHotspot(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Primary dependency hotspot");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const repoControlDependency = repoControlSegment(preview, lines, "dep");
  if (hasPreviewSignal(repoControlDependency) && repoControlDependency !== "none") {
    const inbound = repoControlSegment(preview, lines, "inbound");
    return hasPreviewSignal(inbound) && inbound !== "none"
      ? `${repoControlDependency} | inbound ${inbound}`
      : repoControlDependency;
  }
  const candidates = [
    repoTruthHotspotSegment(preview, lines),
    rawPreviewValue(preview, lines, "Lead hotspot preview"),
    rawPreviewValue(preview, lines, "Hotspot pressure preview"),
    rawPreviewValue(preview, lines, "Hotspot summary"),
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
  const inboundHotspot = firstDelimitedSegment(rawPreviewValue(preview, lines, "Inbound hotspots"));
  if (hasPreviewSignal(inboundHotspot) && inboundHotspot !== "none") {
    return inboundHotspot;
  }
  return explicit;
}

function deriveHotspotSummary(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Hotspot summary");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const truthHotspot = repoTruthHotspotSegment(preview, lines);
  if (hasPreviewSignal(truthHotspot) && truthHotspot !== "none") {
    return truthHotspot;
  }
  const candidates = [
    rawPreviewValue(preview, lines, "Lead hotspot preview"),
    rawPreviewValue(preview, lines, "Hotspot pressure preview"),
  ];
  for (const candidate of candidates) {
    if (hasPreviewSignal(candidate) && candidate !== "none") {
      return candidate;
    }
  }
  const primaryParts: string[] = [];
  const primaryChange = derivePrimaryChangedHotspot(preview, lines);
  if (hasPreviewSignal(primaryChange) && primaryChange !== "none") {
    primaryParts.push(`change ${primaryChange}`);
  }
  const primaryPath = derivePrimaryChangedPath(preview, lines);
  if (hasPreviewSignal(primaryPath) && primaryPath !== "none") {
    primaryParts.push(`path ${primaryPath}`);
  }
  const primaryDependency = derivePrimaryDependencyHotspot(preview, lines);
  if (hasPreviewSignal(primaryDependency) && primaryDependency !== "none") {
    primaryParts.push(`dep ${primaryDependency}`);
  }
  if (primaryParts.length > 0) {
    return primaryParts.join(" | ");
  }
  const changedHotspots = rawPreviewValue(preview, lines, "Changed hotspots");
  if (hasPreviewSignal(changedHotspots) && changedHotspots !== "none") {
    const parts = [`change ${changedHotspots}`];
    const primaryFile = rawPreviewValue(preview, lines, "Primary file hotspot");
    if (hasPreviewSignal(primaryFile) && primaryFile !== "none") {
      parts.push(`files ${primaryFile}`);
    }
    const primaryDependency = derivePrimaryDependencyHotspot(preview, lines);
    if (hasPreviewSignal(primaryDependency) && primaryDependency !== "none") {
      parts.push(`deps ${primaryDependency}`);
    }
    const primaryPath = derivePrimaryChangedPath(preview, lines);
    if (hasPreviewSignal(primaryPath) && primaryPath !== "none") {
      parts.push(`paths ${primaryPath}`);
    }
    return parts.join(" | ");
  }
  return explicit;
}

function previewValue(preview: TabPreview | undefined, lines: TranscriptLine[], label: string): string {
  switch (label) {
    case "Dirty":
      return deriveDirtyLabel(preview, lines);
    case "Branch":
      return deriveBranchValue(preview, lines);
    case "Head":
      return deriveHeadValue(preview, lines);
    case "Branch status":
      return deriveBranchStatusValue(preview, lines);
    case "Ahead":
      return deriveBranchCountValue(preview, lines, "Ahead");
    case "Behind":
      return deriveBranchCountValue(preview, lines, "Behind");
    case "Staged":
      return deriveDirtyCountFromRepoTruth(preview, lines, "staged");
    case "Unstaged":
      return deriveDirtyCountFromRepoTruth(preview, lines, "unstaged");
    case "Untracked":
      return deriveDirtyCountFromRepoTruth(preview, lines, "untracked");
    case "Runtime activity":
      return deriveRuntimeActivity(preview, lines);
    case "Artifact state":
      return deriveArtifactState(preview, lines);
    case "Result status":
      return deriveControlResultStatus(preview, lines);
    case "Acceptance":
      return deriveControlAcceptance(preview, lines);
    case "Runtime freshness":
      return deriveControlRuntimeFreshness(preview, lines);
    case "Updated":
      return deriveControlUpdated(preview, lines);
    case "Last result":
      return deriveControlLastResult(preview, lines);
    case "Verification bundle":
      return deriveControlVerificationBundle(preview, lines);
    case "Primary changed hotspot":
      return derivePrimaryChangedHotspot(preview, lines);
    case "Primary changed path":
      return derivePrimaryChangedPath(preview, lines);
    case "Primary dependency hotspot":
      return derivePrimaryDependencyHotspot(preview, lines);
    case "Hotspot summary":
      return deriveHotspotSummary(preview, lines);
    case "Primary warning":
      return derivePrimaryWarning(preview, lines);
    case "Topology warnings":
      return deriveTopologyWarnings(preview, lines);
    case "Primary topology peer":
      return derivePrimaryTopologyPeer(preview, lines);
    case "Topology risk": {
      const explicit = rawPreviewValue(preview, lines, "Topology risk");
      if (hasPreviewSignal(explicit) && explicit !== "none") {
        return explicit;
      }
      const warning = derivePrimaryWarning(preview, lines);
      return hasPreviewSignal(warning) && warning !== "none" ? warning : explicit;
    }
    case "Primary peer drift":
      return derivePrimaryPeerDrift(preview, lines);
    case "Topology peers":
      return deriveTopologyPeers(preview, lines);
    case "Topology peer count":
      return deriveTopologyPeerCount(preview, lines);
    case "Topology status":
      return deriveTopologyStatus(preview, lines);
    case "Topology warning members":
      return deriveTopologyWarningMembers(preview, lines);
    case "Peer drift markers":
      return derivePeerDriftMarkers(preview, lines);
    default:
      return rawPreviewValue(preview, lines, label);
  }
}

function topologySeverityValue(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = previewValue(preview, lines, "Topology warning severity");
  if (explicit !== "n/a") {
    return explicit;
  }
  const primaryWarning = previewValue(preview, lines, "Primary warning");
  if (primaryWarning === "none") {
    return "stable";
  }
  const topologyWarnings = previewValue(preview, lines, "Topology warnings");
  if (topologyWarnings === "0") {
    return "stable";
  }
  const repoRisk = previewValue(preview, lines, "Repo risk");
  const severityMatch = repoRisk.match(/;\s*([a-z]+)\s*(?:\(|$)/i);
  if (severityMatch?.[1]) {
    return severityMatch[1].toLowerCase();
  }
  if (primaryWarning !== "n/a") {
    return classifyTopologyWarningSeverity(primaryWarning);
  }
  return "n/a";
}

function buildBranchLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return `${previewValue(preview, lines, "Branch")}@${previewValue(preview, lines, "Head")}`;
}

function buildUpstreamLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = previewValue(preview, lines, "Upstream");
  if (hasPreviewSignal(explicit)) {
    return explicit;
  }
  const sync = previewValue(preview, lines, "Sync");
  const syncUpstream =
    sync
      .split("|")
      .map((part) => part.trim())
      .find((part) => part.length > 0 && !/^ahead\b/i.test(part) && !/^behind\b/i.test(part)) || "";
  if (hasPreviewSignal(syncUpstream)) {
    return syncUpstream;
  }
  const branchStatus = previewValue(preview, lines, "Branch status");
  const trackedUpstream = parseTrackedUpstream(branchStatus);
  if (trackedUpstream && hasPreviewSignal(trackedUpstream)) {
    return trackedUpstream;
  }
  return explicit;
}

function buildSyncLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Sync");
  if (hasPreviewSignal(explicit) && explicit !== "none") {
    return explicit;
  }
  const upstream = buildUpstreamLabel(preview, lines);
  const ahead = previewValue(preview, lines, "Ahead");
  const behind = previewValue(preview, lines, "Behind");
  if (hasPreviewSignal(upstream) && ((ahead !== "n/a" && ahead !== "unknown") || (behind !== "n/a" && behind !== "unknown"))) {
    return `${upstream} | ahead ${ahead} | behind ${behind}`;
  }
  return explicit;
}

function buildDirtyCountsLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return `staged ${previewValue(preview, lines, "Staged")} | unstaged ${previewValue(preview, lines, "Unstaged")} | untracked ${previewValue(preview, lines, "Untracked")}`;
}

function buildRuntimeActivityLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return `${previewValue(preview, lines, "Runtime activity")} | ${previewValue(preview, lines, "Artifact state")}`;
}

function buildRepoHealthLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return `${previewValue(preview, lines, "Repo risk")} | ${buildSyncLabel(preview, lines)}`;
}

function buildTopologySignalLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return `${topologySeverityValue(preview, lines)} | ${previewValue(preview, lines, "Primary peer drift")}`;
}

function buildTopologyAlertLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const severity = topologySeverityValue(preview, lines);
  const warning = previewValue(preview, lines, "Primary warning");
  const drift = previewValue(preview, lines, "Primary peer drift");
  return `${severity} | warning ${warning} | drift ${drift}`;
}

function buildBranchDivergenceLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = rawPreviewValue(preview, lines, "Branch divergence");
  if (hasPreviewSignal(explicit)) {
    return explicit;
  }
  const fromRepoControl = repoControlSegment(preview, lines, "divergence");
  if (hasPreviewSignal(fromRepoControl)) {
    return fromRepoControl;
  }
  const ahead = previewValue(preview, lines, "Ahead");
  const behind = previewValue(preview, lines, "Behind");
  const drift = previewValue(preview, lines, "Primary peer drift");
  const parts: string[] = [];
  if ((ahead !== "n/a" && ahead !== "unknown") || (behind !== "n/a" && behind !== "unknown")) {
    parts.push(`local +${ahead}/-${behind}`);
  }
  if (drift !== "n/a" && drift !== "none") {
    parts.push(`peer ${drift}`);
  }
  return parts.join(" | ") || "n/a";
}

function buildBranchSyncPreviewLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = preview?.["Branch sync preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return explicit;
  }
  return [
    previewValue(preview, lines, "Branch status"),
    `+${previewValue(preview, lines, "Ahead")}/-${previewValue(preview, lines, "Behind")}`,
    previewValue(preview, lines, "Repo risk"),
  ].join(" | ");
}

function buildRepoOverviewLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return [
    `Git ${buildBranchLabel(preview, lines)}`,
    previewValue(preview, lines, "Dirty pressure"),
    `sync ${previewValue(preview, lines, "Branch status")}`,
  ].join(" | ");
}

function buildRepoPulseLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return [
    `Dirty ${buildDirtyCountsLabel(preview, lines)}`,
    `topo ${previewValue(preview, lines, "Topology warnings")}`,
    `lead ${previewValue(preview, lines, "Primary changed hotspot")}`,
  ].join(" | ");
}

function buildRepoTruthLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = preview?.["Repo truth preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return explicit;
  }
  return [
    `branch ${buildBranchLabel(preview, lines)}`,
    `dirty ${buildDirtyCountsLabel(preview, lines)}`,
    `warn ${previewValue(preview, lines, "Primary warning")}`,
    `hotspot ${previewValue(preview, lines, "Hotspot summary")}`,
  ].join(" | ");
}

function buildLeadHotspotPreviewLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = preview?.["Lead hotspot preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return explicit;
  }
  const parts: string[] = [];
  const change = previewValue(preview, lines, "Primary changed hotspot");
  const path = previewValue(preview, lines, "Primary changed path");
  const dep = previewValue(preview, lines, "Primary dependency hotspot");
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

function deriveHotspotSegment(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  label: string,
  prefix: string,
): string {
  const explicit = previewValue(preview, lines, label);
  if (explicit !== "n/a" && explicit !== "none") {
    return `${prefix} ${explicit}`;
  }

  const candidates = [
    rawPreviewValue(preview, lines, "Hotspot pressure preview"),
    rawPreviewValue(preview, lines, "Lead hotspot preview"),
    rawPreviewValue(preview, lines, "Hotspot summary"),
  ];
  for (const candidate of candidates) {
    const pressureMatch =
      prefix === "dep"
        ? candidate.match(/(?:^|\|\s*)dep\s+([^|]+?)(?:\s*\|\s*(inbound\s+\d+))?(?:\s*\||$)/i)
        : candidate.match(/(?:^|\|\s*)change\s+([^|]+?)(?:\s*\||$)/i);
    if (pressureMatch?.[1]) {
      return prefix === "dep" && pressureMatch[2]
        ? `dep ${pressureMatch[1].trim()} | ${pressureMatch[2].trim()}`
        : `${prefix} ${pressureMatch[1].trim()}`;
    }
  }
  return "";
}

function buildHotspotPressurePreviewLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = preview?.["Hotspot pressure preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return explicit;
  }
  const parts: string[] = [];
  const change = deriveHotspotSegment(preview, lines, "Primary changed hotspot", "change");
  const dep = deriveHotspotSegment(preview, lines, "Primary dependency hotspot", "dep");
  if (change) {
    parts.push(change);
  }
  if (dep) {
    parts.push(dep);
  }
  return parts.join(" | ") || "n/a";
}

function buildRepoSnapshotRows(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  controlPreview?: TabPreview,
  controlLines: TranscriptLine[] = [],
  now: Date = new Date(),
): string[] {
  const hasControlSignal = hasControlSnapshotSignal(controlPreview, controlLines);
  const prioritizeControlRows = hasControlSignal && prioritizeLiveControlSnapshotRows(controlPreview, controlLines);
  const hasRepoControlPreview = repoControlPreviewValue(preview, lines).length > 0;
  const fallbackControlPulse = !hasControlSignal ? buildFallbackRepoControlPulseLabel(preview, lines) : null;
  const fallbackControlVerification = !hasControlSignal ? buildFallbackRepoControlVerificationLabel(preview, lines) : null;
  const fallbackSnapshotTruth = !hasControlSignal ? buildFallbackRepoSnapshotTruthLabel(preview, lines) : null;
  const fallbackControlRuntimeState = !hasControlSignal
    ? buildFallbackRepoControlRuntimeStateLabel(preview, lines, controlPreview, controlLines)
    : null;
  const rows = [
    `Snapshot branch ${buildBranchLabel(preview, lines)} | ${previewValue(preview, lines, "Branch status")}`,
    `Snapshot sync ${buildUpstreamLabel(preview, lines)} | +${previewValue(preview, lines, "Ahead")}/-${previewValue(preview, lines, "Behind")} | ${buildSyncLabel(preview, lines)}`,
    `Snapshot branch sync ${buildBranchSyncPreviewLabel(preview, lines)}`,
    `Snapshot dirty ${previewValue(preview, lines, "Dirty pressure")} | ${buildDirtyCountsLabel(preview, lines)}`,
    `Snapshot topology ${previewValue(preview, lines, "Topology status")} | warnings ${previewValue(preview, lines, "Topology warnings")}`,
    `Snapshot warning members ${previewValue(preview, lines, "Topology warning members")}`,
    `Snapshot warnings ${previewValue(preview, lines, "Primary warning")} | severity ${topologySeverityValue(preview, lines)}`,
    `Snapshot alert ${buildTopologyAlertLabel(preview, lines)}`,
    `Snapshot branch divergence ${buildBranchDivergenceLabel(preview, lines)}`,
    `Snapshot detached peers ${deriveDetachedPeers(preview, lines)}`,
    `Snapshot topology preview ${buildTopologyPreviewLabel(preview, lines)}`,
    `Snapshot topology pressure ${buildTopologyPressurePreviewLabel(preview, lines)}`,
    `Snapshot hotspots ${buildLeadHotspotPreviewLabel(preview, lines)}`,
    `Snapshot hotspot summary ${previewValue(preview, lines, "Hotspot summary")}`,
    `Snapshot summary ${previewValue(preview, lines, "Repo risk")} | hotspots ${previewValue(preview, lines, "Hotspot summary")}`,
    `Snapshot truth ${buildRepoTruthLabel(preview, lines)}`,
  ];

  if (hasControlSignal) {
    const repoControlRow = `Snapshot repo/control ${buildRepoControlCorrelationLabel(preview, lines, controlPreview, controlLines, now)}`;
    const verificationRow = buildRepoSnapshotVerificationRow(controlPreview, controlLines);
    const taskRow = buildRepoSnapshotTaskRow(controlPreview, controlLines);
    const runtimeRow = `Snapshot runtime ${buildRepoRuntimeStateLabel(controlPreview, controlLines)}`;
    if (prioritizeControlRows) {
      rows.push(taskRow);
      rows.push(runtimeRow);
      rows.push(repoControlRow);
      rows.push(verificationRow);
    } else {
      rows.push(repoControlRow);
      rows.push(verificationRow);
      rows.push(taskRow);
      rows.push(runtimeRow);
    }
    rows.push(`Snapshot freshness ${buildRepoControlCorrelationDetails(preview, lines, controlPreview, controlLines, now)}`);
    rows.push(buildRepoSnapshotTruthRow(controlPreview, controlLines));
  } else {
    if (hasRepoControlPreview) {
      rows.push(`Snapshot repo/control ${buildRepoControlCorrelationLabel(preview, lines, controlPreview, controlLines, now)}`);
    }
    if (fallbackControlPulse) {
      rows.push(`Snapshot control preview ${fallbackControlPulse}`);
    }
    if (fallbackControlRuntimeState) {
      rows.push(`Snapshot runtime ${fallbackControlRuntimeState}`);
    }
    if (fallbackControlVerification) {
      rows.push(`Snapshot repo/control verify ${fallbackControlVerification}`);
    }
    if (fallbackSnapshotTruth) {
      rows.push(`Snapshot truth ${fallbackSnapshotTruth}`);
    }
  }

  return rows;
}

function buildRepoSnapshotControlRows(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  controlPreview?: TabPreview,
  controlLines: TranscriptLine[] = [],
  now: Date = new Date(),
): string[] {
  const hasControlSignal = hasControlSnapshotSignal(controlPreview, controlLines);
  const prioritizeControlRows = hasControlSignal && prioritizeLiveControlSnapshotRows(controlPreview, controlLines);
  const hasRepoControlPreview = repoControlPreviewValue(preview, lines).length > 0;
  if (!hasControlSignal && !hasRepoControlPreview) {
    return [];
  }

  const repoControlRow = `Snapshot repo/control ${buildRepoControlCorrelationLabel(preview, lines, controlPreview, controlLines, now)}`;
  const rows = [repoControlRow];
  if (!hasControlSignal) {
    const fallbackControlPulse = buildFallbackRepoControlPulseLabel(preview, lines);
    const fallbackSnapshotTask = buildFallbackRepoSnapshotTaskLabel(preview, lines);
    const fallbackControlVerification = buildFallbackRepoControlVerificationLabel(preview, lines);
    const fallbackSnapshotTruth = buildFallbackRepoSnapshotTruthLabel(preview, lines);
    const fallbackControlRuntimeState = buildFallbackRepoControlRuntimeStateLabel(preview, lines, controlPreview, controlLines);
    if (fallbackControlPulse) {
      rows.push(`Snapshot control preview ${fallbackControlPulse}`);
    }
    if (fallbackSnapshotTask) {
      rows.push(`Snapshot task ${fallbackSnapshotTask}`);
    }
    if (fallbackControlRuntimeState) {
      rows.push(`Snapshot runtime ${fallbackControlRuntimeState}`);
    }
    if (fallbackControlVerification) {
      rows.push(`Snapshot repo/control verify ${fallbackControlVerification}`);
    }
    if (fallbackSnapshotTruth) {
      rows.push(`Snapshot truth ${fallbackSnapshotTruth}`);
    }
    return rows;
  }

  const verificationRow = buildRepoSnapshotVerificationRow(controlPreview, controlLines);
  const taskRow = buildRepoSnapshotTaskRow(controlPreview, controlLines);
  const runtimeRow = `Snapshot runtime ${buildRepoRuntimeStateLabel(controlPreview, controlLines)}`;
  const controlPreviewRow = buildRepoSnapshotControlPreviewRow(controlPreview, controlLines, now);
  const freshnessRow = `Snapshot freshness ${buildRepoControlCorrelationDetails(preview, lines, controlPreview, controlLines, now)}`;
  if (prioritizeControlRows) {
    rows.length = 0;
    rows.push(taskRow, runtimeRow, repoControlRow, verificationRow, controlPreviewRow, freshnessRow);
  } else {
    rows.push(verificationRow);
    rows.push(taskRow);
    rows.push(runtimeRow);
    rows.push(controlPreviewRow);
    rows.push(freshnessRow);
  }
  rows.push(buildRepoSnapshotTruthRow(controlPreview, controlLines));
  return rows;
}

function prioritizeLiveControlSnapshotRows(preview?: TabPreview, lines: TranscriptLine[] = []): boolean {
  if (!hasControlSnapshotSignal(preview, lines)) {
    return false;
  }
  const loopState = deriveControlLoopState(preview, lines).toLowerCase();
  const resultStatus = deriveControlResultStatus(preview, lines).toLowerCase();
  return resultStatus === "in_progress" || /\b(waiting_for_verification|refresh(?:ing)?)\b/.test(loopState);
}

function buildRepoFocusLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return `Root ${previewValue(preview, lines, "Repo root")} | lead ${previewValue(preview, lines, "Primary changed path")}`;
}

function buildRepoTopologyPulseLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return `Topology pressure ${previewValue(preview, lines, "Topology pressure")} | peers ${previewValue(preview, lines, "Topology peer count")}`;
}

function buildTopologyPressurePreviewLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = preview?.["Topology pressure preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return explicit;
  }
  const warnings = previewValue(preview, lines, "Topology warnings");
  const leadPressure = firstPressureSegment(previewValue(preview, lines, "Topology pressure")) || "none";
  if (warnings === "n/a" && leadPressure === "none") {
    return "n/a";
  }
  if (leadPressure === "none") {
    return warnings;
  }
  return `${warnings} | ${leadPressure}`;
}

function buildTopologyCountLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const parsed = parseRepoControlPreview(repoControlPreviewValue(preview, lines));
  const explicitPeerCount = rawPreviewValue(preview, lines, "Topology peer count");
  const explicitWarningCount = rawPreviewValue(preview, lines, "Topology warnings");
  const peerCount =
    hasPreviewSignal(explicitPeerCount) && explicitPeerCount !== "none"
      ? explicitPeerCount
      : parsed?.topologyPeerCount ?? previewValue(preview, lines, "Topology peer count");
  const warningCount =
    hasPreviewSignal(explicitWarningCount) && explicitWarningCount !== "none"
      ? explicitWarningCount
      : parsed && parsed.topologyWarningCount !== "0"
        ? `${parsed.topologyWarningCount} (${parsed.topologyWarningMembers})`
        : parsed?.topologyWarningCount ?? previewValue(preview, lines, "Topology warnings");
  return `${peerCount} peer${peerCount === "1" ? "" : "s"} | warnings ${warningCount}`;
}

function buildRiskPreviewLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = preview?.["Risk preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return explicit;
  }
  const warning = previewValue(preview, lines, "Primary warning");
  const peer = previewValue(preview, lines, "Primary topology peer");
  if (warning === "n/a" && peer === "n/a") {
    return parseRepoControlPreview(repoControlPreviewValue(preview, lines))?.dirtyState ?? "n/a";
  }
  if (peer === "n/a" || peer === "none") {
    return warning;
  }
  return `${warning} | ${peer}`;
}

function buildRepoRiskPreviewLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = preview?.["Repo risk preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return explicit;
  }
  const branchStatus = previewValue(preview, lines, "Branch status");
  const riskPreview = buildRiskPreviewLabel(preview, lines);
  const compactFallback = parseRepoControlPreview(repoControlPreviewValue(preview, lines))?.dirtyState ?? "";
  if (riskPreview === compactFallback && compactFallback !== "" && compactFallback !== "n/a") {
    return riskPreview;
  }
  if (riskPreview === "n/a" || riskPreview === "stable") {
    return branchStatus;
  }
  return `${branchStatus} | ${riskPreview}`;
}

function buildRepoRiskRows(preview: TabPreview | undefined, lines: TranscriptLine[]): string[] {
  const warningMembers = previewValue(preview, lines, "Topology warning members");
  const hasMultipleWarningMembers =
    warningMembers !== "n/a" &&
    warningMembers !== "none" &&
    warningMembers
      .split(",")
      .map((member) => member.trim())
      .filter((member) => member.length > 0).length > 1;
  return [
    `Severity ${topologySeverityValue(preview, lines)} | warning ${previewValue(preview, lines, "Primary warning")}`,
    ...(hasMultipleWarningMembers ? [`Warning members ${warningMembers}`] : []),
    `Branch divergence ${buildBranchDivergenceLabel(preview, lines)}`,
    `Detached peers ${deriveDetachedPeers(preview, lines)}`,
    `Peer drift ${previewValue(preview, lines, "Primary peer drift")}`,
    `Lead peer ${previewValue(preview, lines, "Primary topology peer")}`,
    `Pressure ${previewValue(preview, lines, "Topology pressure")}`,
  ];
}

function buildRepoSectionControlRows(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  controlPreview?: TabPreview,
  controlLines: TranscriptLine[] = [],
  now: Date = new Date(),
): string[] {
  const hasControlSignal = hasControlSnapshotSignal(controlPreview, controlLines);
  const hasRepoControlPreview = repoControlPreviewValue(preview, lines).length > 0;
  if (!hasControlSignal && !hasRepoControlPreview) {
    return [];
  }

  const rows = [`Control ${buildRepoControlCorrelationLabel(preview, lines, controlPreview, controlLines, now)}`];
  if (hasControlSignal) {
    rows.push(`Runtime ${buildRepoRuntimeStateLabel(controlPreview, controlLines)}`);
    rows.push(`Verify ${buildRepoControlVerificationLabel(controlPreview, controlLines)}`);
    return rows;
  }

  const fallbackControlRuntimeState = buildFallbackRepoControlRuntimeStateLabel(preview, lines, controlPreview, controlLines);
  const fallbackControlVerification = buildFallbackRepoControlVerificationLabel(preview, lines);
  if (fallbackControlRuntimeState) {
    rows.push(`Runtime ${fallbackControlRuntimeState}`);
  }
  if (fallbackControlVerification) {
    rows.push(`Verify ${fallbackControlVerification}`);
  }
  return rows;
}

function buildRepoRiskSectionRows(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  controlPreview?: TabPreview,
  controlLines: TranscriptLine[] = [],
  now: Date = new Date(),
): string[] {
  return [
    `Repo ${previewValue(preview, lines, "Repo risk")}`,
    `Pressure ${previewValue(preview, lines, "Dirty pressure")} | peers ${previewValue(preview, lines, "Topology peer count")}`,
    `Warnings ${previewValue(preview, lines, "Topology warnings")}`,
    ...buildRepoRiskRows(preview, lines),
    `Repo preview ${buildRepoRiskPreviewLabel(preview, lines)}`,
    `Risk ${previewValue(preview, lines, "Topology risk")}`,
    `State ${previewValue(preview, lines, "Dirty")}`,
    `Topology ${previewValue(preview, lines, "Topology status")} | warnings ${previewValue(preview, lines, "Topology warnings")}`,
    `Topology signal ${buildTopologySignalLabel(preview, lines)}`,
    `Topology preview ${buildTopologyPreviewLabel(preview, lines)}`,
    `Preview ${buildRiskPreviewLabel(preview, lines)}`,
    `Lead warning ${previewValue(preview, lines, "Primary warning")}`,
    `Peer drift ${previewValue(preview, lines, "Peer drift markers")}`,
    `Lead peer ${previewValue(preview, lines, "Primary topology peer")}`,
    `Peers ${previewValue(preview, lines, "Topology peers")}`,
    `Topology ${previewValue(preview, lines, "Topology pressure")}`,
    ...buildRepoSectionControlRows(preview, lines, controlPreview, controlLines, now),
  ];
}

function buildFallbackRepoControlPulseLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string | null {
  const parsed = parseRepoControlPreview(repoControlPreviewValue(preview, lines));
  if (!parsed) {
    return null;
  }
  return [parsed.freshness, parsed.loopState, `updated ${parsed.updated}`, `verify ${parsed.verificationBundle}`].join(" | ");
}

function buildFallbackRepoControlTaskLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string | null {
  const parsed = parseRepoControlPreview(repoControlPreviewValue(preview, lines));
  if (!parsed || parsed.task === "n/a") {
    return null;
  }
  return [
    parsed.task,
    ...(parsed.taskProgress !== "n/a" ? [parsed.taskProgress] : []),
    ...(parsed.resultStatus !== "n/a" && parsed.acceptance !== "n/a" ? [`${parsed.resultStatus}/${parsed.acceptance}`] : []),
  ].join(" | ");
}

function buildFallbackRepoSnapshotTaskLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string | null {
  const parsed = parseRepoControlPreview(repoControlPreviewValue(preview, lines));
  if (
    !parsed ||
    parsed.task === "n/a" ||
    parsed.resultStatus === "n/a" ||
    parsed.acceptance === "n/a" ||
    parsed.loopState === "n/a" ||
    parsed.loopDecision === "n/a"
  ) {
    return null;
  }
  return `${parsed.task} | ${parsed.resultStatus}/${parsed.acceptance} | ${parsed.loopState} | ${parsed.loopDecision}`;
}

function buildFallbackRepoControlVerificationLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string | null {
  const parsed = parseRepoControlPreview(repoControlPreviewValue(preview, lines));
  if (!parsed) {
    return null;
  }
  return `${parsed.verificationBundle} | next ${parsed.nextTask}`;
}

function buildFallbackRepoSnapshotTruthLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string | null {
  const parsed = parseRepoControlPreview(repoControlPreviewValue(preview, lines));
  if (!parsed || parsed.verificationBundle === "n/a" || parsed.loopState === "n/a") {
    return null;
  }
  return parsed.truthPreview;
}

function buildFallbackRepoControlRuntimeStateLabel(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  controlPreview?: TabPreview,
  controlLines: TranscriptLine[] = [],
): string | null {
  const liveRuntimeParts = hasControlRuntimeStateSignal(controlPreview, controlLines)
    ? [
        rawPreviewValue(controlPreview, controlLines, "Runtime DB"),
        previewValue(controlPreview, controlLines, "Runtime activity"),
        previewValue(controlPreview, controlLines, "Artifact state"),
      ].filter((value) => value !== "n/a" && value !== "none")
    : [];
  if (liveRuntimeParts.length > 0) {
    return liveRuntimeParts.join(" | ");
  }
  const parsed = parseRepoControlPreview(repoControlPreviewValue(preview, lines));
  if (!parsed) {
    return null;
  }
  return parsed.runtimeSummary !== "n/a" ? parsed.runtimeSummary : null;
}

function buildFallbackRepoControlRuntimeSummaryLabel(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  controlPreview?: TabPreview,
  controlLines: TranscriptLine[] = [],
): string | null {
  return buildFallbackRepoControlRuntimeStateLabel(preview, lines, controlPreview, controlLines);
}

function buildFallbackControlSectionRows(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  controlPreview?: TabPreview,
  controlLines: TranscriptLine[] = [],
): string[] {
  const parsed = parseRepoControlPreview(repoControlPreviewValue(preview, lines));
  if (!parsed) {
    return [];
  }

  const runtimeSummary = buildFallbackRepoControlRuntimeSummaryLabel(preview, lines, controlPreview, controlLines);
  const activitySummary = hasControlRuntimeStateSignal(controlPreview, controlLines)
    ? [
        previewValue(controlPreview, controlLines, "Runtime activity"),
        previewValue(controlPreview, controlLines, "Artifact state"),
      ]
        .filter((value) => value !== "n/a" && value !== "none")
        .join(" | ")
    : [parsed.runtimeActivity, parsed.artifactState].filter((value) => value !== "n/a" && value !== "none").join(" | ");
  const runtimeDb =
    hasControlRuntimeStateSignal(controlPreview, controlLines) && hasPreviewSignal(rawPreviewValue(controlPreview, controlLines, "Runtime DB"))
      ? rawPreviewValue(controlPreview, controlLines, "Runtime DB")
      : parsed.runtimeDb;

  return uniqueRows([
    ...(buildRuntimeInventoryFromCandidates([runtimeSummary ?? "", parsed.runtimeActivity, parsed.artifactState]) !== "n/a"
      ? [`Inventory ${buildRuntimeInventoryFromCandidates([runtimeSummary ?? "", parsed.runtimeActivity, parsed.artifactState])}`]
      : []),
    ...(parsed.task !== "n/a"
      ? [`Task ${[parsed.task, parsed.taskProgress !== "n/a" ? parsed.taskProgress : ""].filter(Boolean).join(" | ")}`]
      : []),
    ...(parsed.resultStatus !== "n/a" || parsed.acceptance !== "n/a"
      ? [`Outcome ${parsed.resultStatus} | accept ${parsed.acceptance}`]
      : []),
    ...(runtimeSummary ? [`Runtime summary ${runtimeSummary}`] : []),
    ...(runtimeDb !== "n/a" && runtimeDb !== "none" ? [`Runtime ${runtimeDb}`] : []),
    ...(activitySummary ? [`Activity ${activitySummary}`] : []),
    ...(parsed.loopState !== "n/a" || parsed.loopDecision !== "n/a"
      ? [`Loop ${[parsed.loopState, parsed.loopDecision !== "n/a" ? parsed.loopDecision : ""].filter(Boolean).join(" | ")}`]
      : []),
    ...(parsed.resultStatus !== "n/a" && parsed.acceptance !== "n/a"
      ? [`Result ${parsed.resultStatus} / ${parsed.acceptance}`]
      : []),
    ...(parsed.verificationBundle !== "n/a" ? [`Health ${parsed.verificationBundle}`, `Verify ${parsed.verificationBundle}`] : []),
    ...(parsed.nextTask !== "n/a" ? [`Next ${parsed.nextTask}`] : []),
    ...(parsed.updated !== "n/a" ? [`Updated ${parsed.updated}`] : []),
  ]);
}

function buildRepoControlCorrelationDetails(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  controlPreview?: TabPreview,
  controlLines: TranscriptLine[] = [],
  now: Date = new Date(),
): string {
  const updated = previewValue(controlPreview, controlLines, "Updated");
  const runtimeFreshness =
    previewValue(controlPreview, controlLines, "Runtime freshness") !== "n/a"
      ? previewValue(controlPreview, controlLines, "Runtime freshness")
      : [
          previewValue(controlPreview, controlLines, "Loop state"),
          `updated ${updated}`,
          `verify ${previewValue(controlPreview, controlLines, "Verification bundle")}`,
        ].join(" | ");
  const activeTask = previewValue(controlPreview, controlLines, "Active task");
  const branchStatus = previewValue(preview, lines, "Branch status");
  const dirtyCounts = buildDirtyCountsLabel(preview, lines);
  const topologyWarnings = deriveTopologyWarnings(preview, lines);
  const primaryWarning = derivePrimaryWarning(preview, lines);
  const primaryPeer = derivePrimaryTopologyPeer(preview, lines);
  const topologyPeers = deriveTopologyPeers(preview, lines);
  const topologyPeerCount = deriveTopologyPeerCount(preview, lines);
  const primaryPeerDrift = derivePrimaryPeerDrift(preview, lines);
  const peerDriftMarkers = derivePeerDriftMarkers(preview, lines);
  const branchDivergence = buildBranchDivergenceLabel(preview, lines);
  const detachedPeers = deriveDetachedPeers(preview, lines);
  const primaryHotspot = previewValue(preview, lines, "Primary changed hotspot");
  const hotspotSummary = previewValue(preview, lines, "Hotspot summary");
  const primaryPath = previewValue(preview, lines, "Primary changed path");
  const primaryDependency = previewValue(preview, lines, "Primary dependency hotspot");
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
    ...(previewValue(preview, lines, "Branch") !== "n/a" && previewValue(preview, lines, "Head") !== "n/a"
      ? [`branch ${buildBranchLabel(preview, lines)}`]
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

function hasControlSnapshotSignal(controlPreview?: TabPreview, controlLines: TranscriptLine[] = []): boolean {
  if (controlPreview) {
    return CONTROL_SIGNAL_LABELS.some((label) => hasPreviewSignal(controlPreview[label] ?? ""));
  }
  return controlLines.some((line) =>
    /^(Active task|Loop state|Runtime freshness|Updated|Verification bundle|Runtime DB|Control pulse preview|Control truth preview):\s+/.test(
      line.text,
    ),
  );
}

function hasControlRuntimeStateSignal(controlPreview?: TabPreview, controlLines: TranscriptLine[] = []): boolean {
  if (controlPreview) {
    return CONTROL_RUNTIME_SIGNAL_LABELS.some((label) => hasPreviewSignal(controlPreview[label] ?? ""));
  }
  return controlLines.some((line) =>
    /^(Runtime DB|Runtime activity|Artifact state|Runtime summary|Session state|Run state|Context state):\s+/.test(line.text),
  );
}

function buildRepoControlCorrelationLabel(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  controlPreview?: TabPreview,
  controlLines: TranscriptLine[] = [],
  now: Date = new Date(),
): string {
  const explicit = repoControlPreviewValue(preview, lines);
  if (!hasControlSnapshotSignal(controlPreview, controlLines) && explicit.length > 0) {
    return explicit;
  }
  return buildRepoControlCorrelationDetails(preview, lines, controlPreview, controlLines, now);
}

function buildTopologyPreviewLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = preview?.["Topology preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return explicit;
  }
  const warning = previewValue(preview, lines, "Primary warning");
  const peer = previewValue(preview, lines, "Primary topology peer");
  const pressure = previewValue(preview, lines, "Topology pressure");
  const parts = [warning === "n/a" || warning === "none" ? "stable" : warning];
  if (peer !== "n/a" && peer !== "none") {
    parts.push(peer);
  }
  if (pressure !== "n/a" && pressure !== "none") {
    parts.push(pressure);
  }
  return parts.join(" | ");
}

function buildControlOverviewLabel(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
): string {
  return [
    `Task ${previewValue(preview, lines, "Active task")}`,
    `${previewValue(preview, lines, "Result status")}/${previewValue(preview, lines, "Acceptance")}`,
    deriveControlVerificationBundle(preview, lines),
  ].join(" | ");
}

function buildControlPulseLabel(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  now: Date = new Date(),
): string {
  const updated = deriveControlUpdated(preview, lines);
  const age = freshnessToken(updated, now);
  const explicit = preview?.["Control pulse preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return /^(fresh|stale|unknown)\b/.test(explicit) ? explicit : `${age} | ${explicit}`;
  }
  return [
    age,
    deriveControlLastResult(preview, lines),
    deriveControlRuntimeFreshness(preview, lines),
  ].join(" | ");
}

function buildControlHealthLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return `${deriveControlVerificationBundle(preview, lines)} | alerts ${previewValue(preview, lines, "Alerts")}`;
}

function buildRepoRuntimeStateLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return [
    previewValue(preview, lines, "Runtime DB"),
    previewValue(preview, lines, "Runtime activity"),
    previewValue(preview, lines, "Artifact state"),
  ].join(" | ");
}

function buildRepoControlTaskLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return [
    previewValue(preview, lines, "Active task"),
    previewValue(preview, lines, "Task progress"),
    `${previewValue(preview, lines, "Result status")}/${previewValue(preview, lines, "Acceptance")}`,
  ].join(" | ");
}

function buildRepoControlVerificationLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return [
    deriveControlVerificationBundle(preview, lines),
    `next ${previewValue(preview, lines, "Next task")}`,
  ].join(" | ");
}

function buildRepoSnapshotVerificationRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return `Snapshot repo/control verify ${buildRepoControlVerificationLabel(preview, lines)}`;
}

function buildRepoSnapshotControlPreviewRow(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  now: Date = new Date(),
): string {
  return `Snapshot control preview ${[
    buildControlPulseLabel(preview, lines, now),
    previewValue(preview, lines, "Runtime activity"),
    previewValue(preview, lines, "Artifact state"),
  ].join(" | ")}`;
}

function buildControlFreshnessDetails(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  now: Date = new Date(),
): string {
  const updated = deriveControlUpdated(preview, lines);
  return [
    freshnessToken(updated, now),
    deriveControlLoopState(preview, lines),
    `updated ${updated}`,
    `verify ${deriveControlVerificationBundle(preview, lines)}`,
  ].join(" | ");
}

function buildControlFreshnessLabel(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  now: Date = new Date(),
): string {
  return `Freshness ${buildControlFreshnessDetails(preview, lines, now)}`;
}

function buildControlRuntimeSummaryLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = preview?.["Runtime summary"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return `Runtime summary ${explicit}`;
  }
  return `Runtime summary ${previewValue(preview, lines, "Runtime DB")} | ${previewValue(preview, lines, "Session state")} | ${previewValue(preview, lines, "Run state")} | ${previewValue(preview, lines, "Context state")}`;
}

function buildControlSnapshotRows(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  now: Date = new Date(),
): string[] {
  return [
    `Snapshot task ${previewValue(preview, lines, "Active task")} | ${previewValue(preview, lines, "Result status")}/${previewValue(preview, lines, "Acceptance")}`,
    `Snapshot runtime ${previewValue(preview, lines, "Runtime DB")} | ${buildRuntimeActivityLabel(preview, lines)}`,
    `Snapshot loop ${freshnessToken(deriveControlUpdated(preview, lines), now)} | ${deriveControlLoopState(preview, lines)} | ${previewValue(preview, lines, "Loop decision")}`,
    `Snapshot verify ${deriveControlVerificationBundle(preview, lines)}`,
    `Snapshot truth ${deriveControlVerificationBundle(preview, lines)} | ${deriveControlLoopState(preview, lines)} | next ${previewValue(preview, lines, "Next task")}`,
  ];
}

function buildRepoSnapshotTaskRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return `Snapshot task ${previewValue(preview, lines, "Active task")} | ${previewValue(preview, lines, "Result status")}/${previewValue(preview, lines, "Acceptance")} | ${deriveControlLoopState(preview, lines)} | ${previewValue(preview, lines, "Loop decision")}`;
}

function buildRepoSnapshotTruthRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = previewValue(preview, lines, "Control truth preview");
  if (explicit !== "n/a") {
    return `Snapshot truth ${explicit}`;
  }
  return `Snapshot truth ${deriveControlVerificationBundle(preview, lines)} | ${deriveControlLoopState(preview, lines)} | next ${previewValue(preview, lines, "Next task")}`;
}

function buildOperatorSnapshotRows(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  controlPreview?: TabPreview,
  controlLines: TranscriptLine[] = [],
  now: Date = new Date(),
): string[] {
  const hasControlSignal = hasControlSnapshotSignal(controlPreview, controlLines);
  const hasRepoControlPreview = repoControlPreviewValue(preview, lines).length > 0;
  const fallbackControlPulse = !hasControlSignal ? buildFallbackRepoControlPulseLabel(preview, lines) : null;
  const fallbackSnapshotTask = !hasControlSignal ? buildFallbackRepoSnapshotTaskLabel(preview, lines) : null;
  const fallbackControlTask = !hasControlSignal ? buildFallbackRepoControlTaskLabel(preview, lines) : null;
  const fallbackControlVerification = !hasControlSignal ? buildFallbackRepoControlVerificationLabel(preview, lines) : null;
  const fallbackSnapshotTruth = !hasControlSignal ? buildFallbackRepoSnapshotTruthLabel(preview, lines) : null;
  const fallbackControlRuntimeState = !hasControlSignal
    ? buildFallbackRepoControlRuntimeStateLabel(preview, lines, controlPreview, controlLines)
    : null;
  const fallbackControlRuntimeSummary = !hasControlSignal
    ? buildFallbackRepoControlRuntimeSummaryLabel(preview, lines, controlPreview, controlLines)
    : null;
  const rows = [
    buildRepoOverviewLabel(preview, lines),
    buildRepoPulseLabel(preview, lines),
    `Snapshot branch ${buildBranchLabel(preview, lines)} | ${previewValue(preview, lines, "Branch status")}`,
    `Snapshot sync ${buildUpstreamLabel(preview, lines)} | +${previewValue(preview, lines, "Ahead")}/-${previewValue(preview, lines, "Behind")} | ${buildSyncLabel(preview, lines)}`,
    `Snapshot branch sync ${buildBranchSyncPreviewLabel(preview, lines)}`,
    `Snapshot dirty ${previewValue(preview, lines, "Dirty pressure")} | ${buildDirtyCountsLabel(preview, lines)}`,
    `Snapshot topology ${previewValue(preview, lines, "Topology status")} | warnings ${previewValue(preview, lines, "Topology warnings")}`,
    `Snapshot warning members ${previewValue(preview, lines, "Topology warning members")}`,
    `Snapshot warnings ${previewValue(preview, lines, "Primary warning")} | severity ${topologySeverityValue(preview, lines)}`,
    `Snapshot alert ${buildTopologyAlertLabel(preview, lines)}`,
    `Snapshot branch divergence ${buildBranchDivergenceLabel(preview, lines)}`,
    `Snapshot detached peers ${deriveDetachedPeers(preview, lines)}`,
    `Snapshot topology preview ${buildTopologyPreviewLabel(preview, lines)}`,
    `Snapshot hotspots ${buildLeadHotspotPreviewLabel(preview, lines)}`,
    `Snapshot hotspot summary ${previewValue(preview, lines, "Hotspot summary")}`,
    `Snapshot summary ${previewValue(preview, lines, "Repo risk")} | hotspots ${previewValue(preview, lines, "Hotspot summary")}`,
    `Snapshot truth ${buildRepoTruthLabel(preview, lines)}`,
    `Snapshot repo risk ${buildRepoRiskPreviewLabel(preview, lines)}`,
    `Snapshot focus ${buildRepoFocusLabel(preview, lines)}`,
    `Snapshot topology pulse ${buildRepoTopologyPulseLabel(preview, lines)}`,
    `Snapshot topology pressure ${buildTopologyPressurePreviewLabel(preview, lines)}`,
    `Snapshot hotspot pressure ${buildHotspotPressurePreviewLabel(preview, lines)}`,
  ];

  if (hasControlSignal || hasRepoControlPreview) {
    rows.push(`Snapshot repo/control ${buildRepoControlCorrelationLabel(preview, lines, controlPreview, controlLines, now)}`);
    if (hasControlSignal) {
      rows.push(buildRepoSnapshotControlPreviewRow(controlPreview, controlLines, now));
      rows.push(buildRepoSnapshotVerificationRow(controlPreview, controlLines));
      rows.push(buildControlOverviewLabel(controlPreview, controlLines));
      rows.push(`Control pulse ${buildControlPulseLabel(controlPreview, controlLines, now)}`);
      rows.push(`Runtime state ${buildRepoRuntimeStateLabel(controlPreview, controlLines)}`);
      rows.push(`Control task ${buildRepoControlTaskLabel(controlPreview, controlLines)}`);
      rows.push(`Control verify ${buildRepoControlVerificationLabel(controlPreview, controlLines)}`);
      rows.push(buildControlFreshnessLabel(controlPreview, controlLines, now));
      rows.push(buildRepoSnapshotTruthRow(controlPreview, controlLines));
    } else {
      if (fallbackControlPulse) {
        rows.push(`Snapshot control preview ${fallbackControlPulse}`);
        rows.push(`Control pulse ${fallbackControlPulse}`);
      }
      if (fallbackSnapshotTask) {
        rows.push(`Snapshot task ${fallbackSnapshotTask}`);
      }
      if (fallbackControlRuntimeState) {
        rows.push(`Snapshot runtime ${fallbackControlRuntimeState}`);
        rows.push(`Runtime state ${fallbackControlRuntimeState}`);
      }
      if (fallbackControlRuntimeSummary) {
        rows.push(`Runtime summary ${fallbackControlRuntimeSummary}`);
      }
      if (fallbackControlTask) {
        rows.push(`Control task ${fallbackControlTask}`);
      }
      if (fallbackControlVerification) {
        rows.push(`Snapshot repo/control verify ${fallbackControlVerification}`);
        rows.push(`Control verify ${fallbackControlVerification}`);
      }
      if (fallbackSnapshotTruth) {
        rows.push(`Snapshot truth ${fallbackSnapshotTruth}`);
      }
    }
  }

  return rows;
}

export function buildRepoPaneSections(
  preview?: TabPreview,
  lines: TranscriptLine[] = [],
  controlPreview?: TabPreview,
  controlLines: TranscriptLine[] = [],
  now: Date = new Date(),
): RepoSection[] {
  if (!preview) {
    return [
      {
        title: "Repo Snapshot",
        rows:
          lines.length > 0 ? lines.slice(-24).map((line) => line.text) : ["No repo snapshot yet."],
      },
    ];
  }

  const hasControlSignal = hasControlSnapshotSignal(controlPreview, controlLines);
  const fallbackControlRows = !hasControlSignal
    ? buildFallbackControlSectionRows(preview, lines, controlPreview, controlLines)
    : [];
  const snapshotRows = buildRepoSnapshotRows(preview, lines, controlPreview, controlLines, now);
  const snapshotControlRows = buildRepoSnapshotControlRows(preview, lines, controlPreview, controlLines, now);

  const sections: RepoSection[] = [
    {
      title: "Operator Snapshot",
      rows: [
        ...(preview?.Authority ? [`Authority ${preview.Authority}`] : []),
        ...buildOperatorSnapshotRows(preview, lines, controlPreview, controlLines, now),
      ],
    },
    {
      title: "Snapshot",
      rows: uniqueRows([
        ...(preview?.Authority ? [`Authority ${preview.Authority}`] : []),
        ...snapshotRows,
        `Root ${previewValue(preview, lines, "Repo root")}`,
        `Branch ${buildBranchLabel(preview, lines)}`,
        `Track ${previewValue(preview, lines, "Branch status")} | upstream ${buildUpstreamLabel(preview, lines)}`,
        `Branch preview ${buildBranchSyncPreviewLabel(preview, lines)}`,
        `Sync ${buildSyncLabel(preview, lines)} | +${previewValue(preview, lines, "Ahead")}/-${previewValue(preview, lines, "Behind")}`,
        `Health ${buildRepoHealthLabel(preview, lines)}`,
        `Repo risk preview ${buildRepoRiskPreviewLabel(preview, lines)}`,
        `Snapshot repo risk ${buildRepoRiskPreviewLabel(preview, lines)}`,
        ...snapshotControlRows,
        `Dirty ${previewValue(preview, lines, "Dirty pressure")} | ${buildDirtyCountsLabel(preview, lines)}`,
        `Hotspots ${previewValue(preview, lines, "Hotspot summary")}`,
        `Snapshot hotspot summary ${previewValue(preview, lines, "Hotspot summary")}`,
        `Warning members ${previewValue(preview, lines, "Topology warning members")}`,
        `Warnings ${previewValue(preview, lines, "Primary warning")} | severity ${topologySeverityValue(preview, lines)}`,
        `Branch divergence ${buildBranchDivergenceLabel(preview, lines)}`,
        `Detached peers ${deriveDetachedPeers(preview, lines)}`,
        `Lead change ${previewValue(preview, lines, "Primary changed hotspot")} | path ${previewValue(preview, lines, "Primary changed path")}`,
        `Lead file ${previewValue(preview, lines, "Primary file hotspot")}`,
        `Lead dep ${previewValue(preview, lines, "Primary dependency hotspot")}`,
      ]),
    },
    {
      title: "Repo Risk",
      rows: buildRepoRiskSectionRows(preview, lines, controlPreview, controlLines, now),
    },
    {
      title: "Git",
      rows: [
        `Branch ${buildBranchLabel(preview, lines)}`,
        `Upstream ${buildUpstreamLabel(preview, lines)} | +${previewValue(preview, lines, "Ahead")}/-${previewValue(preview, lines, "Behind")}`,
        `Track ${previewValue(preview, lines, "Branch status")}`,
        `Preview ${buildBranchSyncPreviewLabel(preview, lines)}`,
        `Sync ${buildSyncLabel(preview, lines)}`,
        `Risk ${previewValue(preview, lines, "Repo risk")}`,
        `Pressure ${previewValue(preview, lines, "Dirty pressure")}`,
        `Dirty ${previewValue(preview, lines, "Dirty")}`,
        `Counts ${buildDirtyCountsLabel(preview, lines)}`,
      ],
    },
    {
      title: "Topology",
      rows: [
        `Status ${previewValue(preview, lines, "Topology status")} | peers ${previewValue(preview, lines, "Topology peer count")}`,
        `Count ${buildTopologyCountLabel(preview, lines)}`,
        `Pressure ${previewValue(preview, lines, "Topology pressure")} | peers ${previewValue(preview, lines, "Topology peer count")}`,
        `Pressure preview ${buildTopologyPressurePreviewLabel(preview, lines)}`,
        `Warnings ${previewValue(preview, lines, "Topology warnings")}`,
        `Members ${previewValue(preview, lines, "Topology warning members")}`,
        `Severity ${topologySeverityValue(preview, lines)}`,
        `Risk ${previewValue(preview, lines, "Topology risk")}`,
        `Signal ${buildTopologySignalLabel(preview, lines)}`,
        `Branch divergence ${buildBranchDivergenceLabel(preview, lines)}`,
        `Detached peers ${deriveDetachedPeers(preview, lines)}`,
        `Topology preview ${buildTopologyPreviewLabel(preview, lines)}`,
        `Preview ${buildRiskPreviewLabel(preview, lines)}`,
        `Lead ${previewValue(preview, lines, "Primary warning")}`,
        `Drift ${previewValue(preview, lines, "Peer drift markers")}`,
        `Lead peer ${previewValue(preview, lines, "Primary topology peer")}`,
        `Peers ${previewValue(preview, lines, "Topology peers")}`,
        `Hotspot summary ${previewValue(preview, lines, "Hotspot summary")}`,
        `Hotspot pressure ${buildHotspotPressurePreviewLabel(preview, lines)}`,
      ],
    },
    {
      title: "Hotspots",
      rows: [
        `Changed ${previewValue(preview, lines, "Changed hotspots")}`,
        `Summary ${previewValue(preview, lines, "Hotspot summary")}`,
        `Pressure ${buildHotspotPressurePreviewLabel(preview, lines)}`,
        `Paths ${previewValue(preview, lines, "Changed paths")}`,
        `Lead path ${previewValue(preview, lines, "Primary changed path")}`,
        `Files ${previewValue(preview, lines, "Hotspots")}`,
        `Lead file ${previewValue(preview, lines, "Primary file hotspot")}`,
        `Deps ${previewValue(preview, lines, "Inbound hotspots")}`,
        `Lead dep ${previewValue(preview, lines, "Primary dependency hotspot")}`,
        ...buildRepoSectionControlRows(preview, lines, controlPreview, controlLines, now),
      ],
    },
    {
      title: "Inventory",
      rows: [
        `Inventory ${previewValue(preview, lines, "Inventory")}`,
        `Mix ${previewValue(preview, lines, "Language mix")}`,
      ],
    },
  ];

  if (hasControlSignal) {
    sections.push({
      title: "Control",
      rows: [
        `Task ${previewValue(controlPreview, controlLines, "Active task")} | ${previewValue(controlPreview, controlLines, "Task progress")}`,
        `Outcome ${previewValue(controlPreview, controlLines, "Result status")} | accept ${previewValue(controlPreview, controlLines, "Acceptance")}`,
        buildControlRuntimeSummaryLabel(controlPreview, controlLines),
        `Runtime ${previewValue(controlPreview, controlLines, "Runtime DB")}`,
        `Sessions ${previewValue(controlPreview, controlLines, "Session state")}`,
        `Runs ${previewValue(controlPreview, controlLines, "Run state")}`,
        `Context ${previewValue(controlPreview, controlLines, "Context state")}`,
        `Inventory ${deriveRuntimeInventoryLabel(controlPreview, controlLines)}`,
        `Activity ${buildRuntimeActivityLabel(controlPreview, controlLines)}`,
        `Health ${buildControlHealthLabel(controlPreview, controlLines)}`,
        `Loop ${previewValue(controlPreview, controlLines, "Loop state")} | ${previewValue(controlPreview, controlLines, "Loop decision")}`,
        `Result ${previewValue(controlPreview, controlLines, "Last result")}`,
        `Verify ${previewValue(controlPreview, controlLines, "Verification summary")}`,
        `Checks ${previewValue(controlPreview, controlLines, "Verification checks")}`,
        `Bundle ${previewValue(controlPreview, controlLines, "Verification bundle")}`,
        `Tools ${previewValue(controlPreview, controlLines, "Toolchain")} | alerts ${previewValue(controlPreview, controlLines, "Alerts")}`,
        `State ${previewValue(controlPreview, controlLines, "Durable state")}`,
        `Next ${previewValue(controlPreview, controlLines, "Next task")}`,
        `Updated ${previewValue(controlPreview, controlLines, "Updated")}`,
      ],
    });
  } else if (fallbackControlRows.length > 0) {
    sections.push({
      title: "Control",
      rows: fallbackControlRows,
    });
  }

  return sections;
}

export function RepoPane({
  title,
  preview,
  controlPreview,
  lines,
  controlLines = [],
  scrollOffset = 0,
  windowSize = 24,
  selectedSectionIndex = 0,
}: Props): React.ReactElement {
  const sections = buildRepoPaneSections(preview, lines, controlPreview, controlLines);
  const activeSectionIndex = clampSectionIndex(selectedSectionIndex, sections);
  const activeSection = sections[activeSectionIndex];
  const visibleRows = activeSection ? activeSection.rows.slice(scrollOffset, scrollOffset + Math.max(windowSize - 4, 8)) : [];
  const detailRows: DetailRow[] = visibleRows.map((value, index) => ({
    value,
    tone: index === 0 || (activeSection?.title === "Overview" && index < 2) ? "strong" : "muted",
  }));

  return (
    <Box flexGrow={1} flexDirection="column" borderStyle="round" borderColor={THEME.parchment} paddingX={1}>
      <Text color={THEME.parchment} bold>{title}</Text>
      <Text color={THEME.stone}>section focus active | j/k or ↑/↓ move between repo sections</Text>
      <Box marginTop={1}>
        <Box width="35%" flexDirection="column" borderStyle="single" borderColor={THEME.ink} paddingX={1}>
          <Text color={THEME.parchment} bold>Sections</Text>
          <Text color={THEME.stone}>repo posture and live risk</Text>
          {sections.map((section, index) => {
            const active = index === activeSectionIndex;
            const summaries = sectionCardSummaries(section);
            return (
              <Box key={section.title} flexDirection="column" marginTop={1} borderStyle={active ? "round" : undefined} borderColor={active ? THEME.parchment : undefined} paddingX={active ? 1 : 0}>
                <Text color={active ? THEME.parchment : THEME.foam} bold={active}>
                  {active ? "▶ " : "• "}
                  {section.title}
                </Text>
                <Text color={active ? THEME.foam : THEME.stone}>
                  {"  "}{section.rows.length} rows
                </Text>
                {summaries.map((summary, summaryIndex) => (
                  <Text key={`${section.title}-summary-${summaryIndex}`} color={THEME.stone}>
                    {"  "}{summary}
                  </Text>
                ))}
              </Box>
            );
          })}
        </Box>
        <Box width="65%" marginLeft={1} flexDirection="column" borderStyle="single" borderColor={THEME.ink} paddingX={1}>
          <Text color={THEME.wave} bold>{activeSection?.title ?? "Section"}</Text>
          <Text color={THEME.stone}>selected repo card</Text>
          {visibleRows.length === 0 ? (
            <Text color={THEME.stone}>No section detail.</Text>
          ) : (
            detailRows.map((row, index) => (
              <Text
                key={`${activeSection?.title ?? "section"}-${index}`}
                color={row.tone === "strong" ? THEME.foam : THEME.stone}
                bold={row.tone === "strong"}
              >
                {row.value}
              </Text>
            ))
          )}
        </Box>
      </Box>
    </Box>
  );
}
