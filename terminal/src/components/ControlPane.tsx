import React from "react";
import path from "node:path";
import {Box, Text} from "ink";

import type {TabPreview, TranscriptLine} from "../types";
import {parseControlPulsePreview, parseRuntimeFreshness} from "../freshness";
import {parseRepoControlPreview} from "../repoControlPreview";
import {buildVerificationSummaryRows, isGenericVerificationLabel, resolveVerificationEntries} from "../verification";
import {THEME} from "../theme";

type ControlSection = {
  title: string;
  rows: string[];
};

type DetailRow = {
  value: string;
  tone?: "strong" | "muted";
};

type SignalTone = "strong" | "warning" | "muted";

type SignalRow = {
  value: string;
  tone: SignalTone;
};

type SectionPreviewPreference = {
  title: string;
  prefixes: string[];
};

const STRUCTURED_CONTROL_LABELS = [
  "Repo/control preview",
  "Control pulse preview",
  "Runtime freshness",
  "Loop state",
  "Task progress",
  "Active task",
  "Result status",
  "Acceptance",
  "Loop decision",
  "Updated",
  "Runtime DB",
  "Session state",
  "Run state",
  "Active runs detail",
  "Context state",
  "Recent operator actions",
  "Runtime activity",
  "Artifact state",
  "Toolchain",
  "Alerts",
  "Verification summary",
  "Verification checks",
  "Verification status",
  "Verification passing",
  "Verification failing",
  "Verification bundle",
  "Verification receipt",
  "Verification updated",
  "Last result",
  "Next task",
  "Durable state",
] as const;

type Props = {
  title: string;
  mode?: "control" | "runtime";
  preview?: TabPreview;
  lines: TranscriptLine[];
  scrollOffset?: number;
  windowSize?: number;
  selectedSectionIndex?: number;
};

function clampSectionIndex(index: number, sections: ControlSection[]): number {
  if (sections.length === 0) {
    return 0;
  }
  return Math.min(Math.max(index, 0), sections.length - 1);
}

function previewValue(preview: TabPreview | undefined, lines: TranscriptLine[], label: string): string {
  const value = preview?.[label];
  if (typeof value === "string" && value.length > 0) {
    return value;
  }
  const match = lines.find((line) => line.text.startsWith(`${label}: `));
  if (!match) {
    return repoControlFallbackValue(preview, label);
  }
  return match.text.slice(label.length + 2).trim();
}

function repoControlFallbackValue(preview: TabPreview | undefined, label: string): string {
  const parsed = parseRepoControlPreview(preview);
  if (!parsed) {
    return "n/a";
  }

  switch (label) {
    case "Loop state":
      return parsed.loopState;
    case "Active task":
      return parsed.task;
    case "Task progress":
      return parsed.taskProgress;
    case "Result status":
      return parsed.resultStatus;
    case "Acceptance":
      return parsed.acceptance;
    case "Loop decision":
      return parsed.loopDecision;
    case "Updated":
      return parsed.updated;
    case "Runtime DB":
      return parsed.runtimeDb;
    case "Runtime activity":
      return parsed.runtimeActivity;
    case "Artifact state":
      return parsed.artifactState;
    case "Verification bundle":
    case "Verification summary":
      return parsed.verificationBundle;
    case "Verification checks": {
      const bundle = resolveVerificationEntries({bundleText: parsed.verificationBundle});
      return bundle.length > 0 ? bundle.map((entry) => `${entry.name} ${entry.ok ? "ok" : "fail"}`).join("; ") : "n/a";
    }
    case "Runtime freshness":
      return [parsed.loopState, `updated ${parsed.updated}`, `verify ${parsed.verificationBundle}`]
        .filter((value) => value !== "n/a" && value !== "none")
        .join(" | ") || "n/a";
    case "Last result":
      return [parsed.resultStatus, parsed.acceptance].every((value) => value !== "n/a" && value !== "none")
        ? `${parsed.resultStatus} / ${parsed.acceptance}`
        : "n/a";
    case "Control pulse preview":
      return [
        parsed.freshness,
        repoControlFallbackValue(preview, "Last result"),
        repoControlFallbackValue(preview, "Runtime freshness"),
      ]
        .filter((value) => value !== "n/a" && value !== "none")
        .join(" | ") || "n/a";
    case "Next task":
      return parsed.nextTask;
    default:
      return "n/a";
  }
}

function isPlaceholderValue(value: string): boolean {
  return value === "n/a" || value === "none" || value === "unknown";
}

function derivedRuntimeFreshness(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = previewValue(preview, lines, "Runtime freshness");
  if (!isPlaceholderValue(explicit)) {
    return explicit;
  }

  return parseControlPulsePreview(previewValue(preview, lines, "Control pulse preview")).runtimeFreshness ?? "n/a";
}

function derivedLoopState(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = previewValue(preview, lines, "Loop state");
  if (!isPlaceholderValue(explicit)) {
    return explicit;
  }

  return parseRuntimeFreshness(derivedRuntimeFreshness(preview, lines)).loopState ?? "n/a";
}

function derivedUpdated(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = previewValue(preview, lines, "Updated");
  if (!isPlaceholderValue(explicit)) {
    return explicit;
  }

  return parseRuntimeFreshness(derivedRuntimeFreshness(preview, lines)).updated ?? "n/a";
}

function derivedFreshness(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const freshness = parseControlPulsePreview(previewValue(preview, lines, "Control pulse preview")).freshness;
  return freshness && !isPlaceholderValue(freshness) ? freshness : "n/a";
}

function derivedLastResult(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = previewValue(preview, lines, "Last result");
  if (!isPlaceholderValue(explicit)) {
    return explicit;
  }

  return parseControlPulsePreview(previewValue(preview, lines, "Control pulse preview")).lastResult ?? "n/a";
}

function derivedResultParts(preview: TabPreview | undefined, lines: TranscriptLine[]): {status?: string; acceptance?: string} {
  const lastResult = derivedLastResult(preview, lines);
  if (lastResult === "n/a" || lastResult === "none") {
    return {};
  }
  const [status, acceptance] = lastResult.split("/").map((part) => part.trim());
  return {
    ...(status ? {status} : {}),
    ...(acceptance ? {acceptance} : {}),
  };
}

function derivedResultStatus(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = previewValue(preview, lines, "Result status");
  if (!isPlaceholderValue(explicit)) {
    return explicit;
  }

  return derivedResultParts(preview, lines).status ?? "n/a";
}

function derivedAcceptance(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = previewValue(preview, lines, "Acceptance");
  if (!isPlaceholderValue(explicit)) {
    return explicit;
  }

  return derivedResultParts(preview, lines).acceptance ?? "n/a";
}

function derivedVerificationInputs(preview: TabPreview | undefined, lines: TranscriptLine[]): {
  summary: string;
  checks: string;
  bundleLabel: string;
} {
  const explicitSummary = previewValue(preview, lines, "Verification summary");
  const explicitChecks = previewValue(preview, lines, "Verification checks");
  const explicitBundle = previewValue(preview, lines, "Verification bundle");
  const explicitPassing = previewValue(preview, lines, "Verification passing");
  const explicitFailing = previewValue(preview, lines, "Verification failing");
  const compactBundle = parseRuntimeFreshness(derivedRuntimeFreshness(preview, lines)).verificationBundle ?? "n/a";
  const bundleFallback = !isPlaceholderValue(explicitBundle) ? explicitBundle : compactBundle;
  const derivedEntries = resolveVerificationEntries({
    checksText: !isPlaceholderValue(explicitChecks) ? explicitChecks : "",
    summaryText: !isPlaceholderValue(explicitSummary) ? explicitSummary : "",
    bundleText: !isPlaceholderValue(bundleFallback) ? bundleFallback : "",
    passingText: !isPlaceholderValue(explicitPassing) ? explicitPassing : "",
    failingText: !isPlaceholderValue(explicitFailing) ? explicitFailing : "",
  });
  const derivedChecksFromBundle = derivedEntries
    .map((entry) => `${entry.name} ${entry.ok ? "ok" : "fail"}`)
    .join("; ");

  return {
    summary: !isPlaceholderValue(explicitSummary) ? explicitSummary : bundleFallback,
    checks: !isPlaceholderValue(explicitChecks) ? explicitChecks : derivedChecksFromBundle || "n/a",
    bundleLabel: bundleFallback,
  };
}

function hasSignal(value: string): boolean {
  return value !== "n/a" && value !== "none" && value !== "unknown";
}

function isPlaceholderAuthorityRow(value: string): boolean {
  return /^Authority placeholder\s+\|/i.test(value);
}

function authorityOverviewRows(preview: TabPreview | undefined, lines: TranscriptLine[], bodyRows: string[]): string[] {
  const authority = previewValue(preview, lines, "Authority");
  if (!hasSignal(authority)) {
    return [];
  }
  if (isPlaceholderAuthorityRow(`Authority ${authority}`) && bodyRows.length > 0) {
    return [];
  }
  return [`Authority ${authority}`];
}

const SECTION_PREVIEW_PREFERENCES: SectionPreviewPreference[] = [
  {title: "Overview", prefixes: ["Loop ", "Verification ", "Freshness ", "Outcome ", "Pulse ", "Runtime ", "Context ", "Decision ", "State "]},
  {title: "Loop", prefixes: ["State ", "Task ", "Outcome ", "Freshness ", "Decision ", "Updated "]},
  {title: "Runtime", prefixes: ["DB ", "Sessions ", "Runs ", "Active ", "Context ", "Actions ", "Activity ", "Artifacts ", "Summary "]},
  {title: "Verification", prefixes: ["Verification ", "Receipt ", "Updated ", "Freshness ", "Status ", "Failing ", "Passing ", "Summary ", "Bundle ", "Last "]},
  {title: "Durability", prefixes: ["State ", "Receipt ", "Truth ", "Pulse "]},
  {title: "Tools", prefixes: ["Toolchain ", "Alerts "]},
  {title: "Next", prefixes: ["Decision ", "Freshness ", "Task ", "State "]},
];

function matchingSectionPreviewPreference(title: string): SectionPreviewPreference | undefined {
  return SECTION_PREVIEW_PREFERENCES.find((preference) => preference.title === title);
}

export function sectionCardPreviewRows(section: ControlSection, maxRows = 2): string[] {
  const candidates = section.rows.filter((row) => !isPlaceholderAuthorityRow(row));
  const rows = candidates.length > 0 ? candidates : section.rows;
  if (rows.length <= maxRows) {
    return rows.slice(0, maxRows);
  }

  const preference = matchingSectionPreviewPreference(section.title);
  if (!preference) {
    return rows.slice(0, maxRows);
  }

  const selected: string[] = [];
  for (const prefix of preference.prefixes) {
    const match = rows.find((row) => row.startsWith(prefix) && !selected.includes(row));
    if (match) {
      selected.push(match);
    }
    if (selected.length >= maxRows) {
      return selected;
    }
  }

  for (const row of rows) {
    if (!selected.includes(row)) {
      selected.push(row);
    }
    if (selected.length >= maxRows) {
      break;
    }
  }

  return selected;
}

function runtimeSummaryRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = previewValue(preview, lines, "Runtime summary");
  return hasSignal(explicit) ? `Runtime ${explicit}` : "Runtime unknown";
}

function primaryRuntimeSignalFragment(value: string): string {
  if (!hasSignal(value)) {
    return "";
  }
  return value
    .split("|")
    .map((part) => part.trim())
    .find((part) => part.length > 0) ?? "";
}

function runtimeOverviewRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const runtimeActivity = parseRuntimeMetrics(previewValue(preview, lines, "Runtime activity"));
  if (Object.keys(runtimeActivity).length > 0) {
    return `Runtime ${[
      metricFragment(runtimeActivity, "Sessions", "sessions"),
      metricFragment(runtimeActivity, "Runs", "runs"),
      nonZeroMetricFragment(runtimeActivity, "ActiveRuns", "active runs"),
      nonZeroMetricFragment(runtimeActivity, "ActiveClaims", "active claims"),
    ]
      .filter((value) => value.length > 0)
      .join(" | ")}`;
  }
  const derivedFragments = [
    primaryRuntimeSignalFragment(previewValue(preview, lines, "Session state")),
    primaryRuntimeSignalFragment(previewValue(preview, lines, "Run state")),
    primaryRuntimeSignalFragment(previewValue(preview, lines, "Context state")),
  ].filter((value) => value.length > 0);
  if (derivedFragments.length > 0) {
    return `Runtime ${derivedFragments.join(" | ")}`;
  }
  return runtimeSummaryRow(preview, lines);
}

function signalTaskContextRow(
  mode: "control" | "runtime",
  activeTask: string,
  taskProgress: string,
  nextTask: string,
): string {
  const parts: string[] = [];
  const taskSummary = [activeTask, taskProgress].filter(hasSignal).join(" | ");
  if (taskSummary.length > 0) {
    parts.push(`Task ${taskSummary}`);
  }
  if (hasSignal(nextTask)) {
    parts.push(`${taskSummary.length > 0 || mode === "control" ? "Next" : "Task"} ${nextTask}`);
  }
  return parts.join(" | ");
}

function signalDurabilityRow(verificationReceipt: string, durableState: string): string {
  const parts: string[] = [];
  if (hasSignal(verificationReceipt)) {
    parts.push(`Receipt ${verificationReceipt}`);
  }
  if (hasSignal(durableState)) {
    parts.push(`State ${durableState}`);
  }
  return parts.join(" | ");
}

function buildControlPulseRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = previewValue(preview, lines, "Control pulse preview");
  if (explicit !== "n/a" && explicit !== "none") {
    return `Pulse ${explicit}`;
  }

  const lastResult = derivedLastResult(preview, lines);
  const runtimeFreshness = derivedRuntimeFreshness(preview, lines);
  const parts = [lastResult, runtimeFreshness].filter((value) => value !== "n/a" && value !== "none");
  return parts.length > 0 ? `Pulse ${parts.join(" | ")}` : "Pulse unknown";
}

function parseRuntimeMetrics(value: string): Record<string, string> {
  if (value === "n/a" || value === "none") {
    return {};
  }
  return Object.fromEntries(
    Array.from(value.matchAll(/([A-Za-z][A-Za-z0-9]*)=([^\s]+)/g), (match) => [match[1], match[2]]),
  );
}

function runtimeMetricValue(metrics: Record<string, string>, key: string): string {
  return metrics[key] ?? "n/a";
}

function metricFragment(metrics: Record<string, string>, key: string, label: string): string {
  const value = runtimeMetricValue(metrics, key);
  return value === "n/a" ? "" : `${value} ${label}`;
}

function nonZeroMetricFragment(metrics: Record<string, string>, key: string, label: string): string {
  const value = runtimeMetricValue(metrics, key);
  return value === "n/a" || value === "0" ? "" : `${value} ${label}`;
}

function joinMetricFragments(fragments: string[]): string {
  const filtered = fragments.filter((fragment) => fragment.length > 0);
  return filtered.length > 0 ? filtered.join(" | ") : "n/a";
}

function runtimeRow(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  label: string,
  fallbackLabel: string,
  formatter: (metrics: Record<string, string>) => string,
): string {
  const explicit = previewValue(preview, lines, label);
  if (!isPlaceholderValue(explicit)) {
    return `${fallbackLabel} ${explicit}`;
  }
  const metrics = parseRuntimeMetrics(previewValue(preview, lines, label === "Context state" ? "Artifact state" : "Runtime activity"));
  return `${fallbackLabel} ${Object.keys(metrics).length > 0 ? formatter(metrics) : "n/a"}`;
}

function hasStructuredControlState(preview: TabPreview | undefined, lines: TranscriptLine[]): boolean {
  if (preview) {
    const previewHasStructuredSignal = STRUCTURED_CONTROL_LABELS.some((label) => {
      const value = preview[label];
      return typeof value === "string" && hasSignal(value);
    });
    if (previewHasStructuredSignal || parseRepoControlPreview(preview)) {
      return true;
    }
  }
  return STRUCTURED_CONTROL_LABELS.some((label) => lines.some((line) => line.text.startsWith(`${label}: `)));
}

function verificationStatusRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = previewValue(preview, lines, "Verification status");
  const verification = derivedVerificationInputs(preview, lines);
  const bundle = resolveVerificationEntries({
    checksText: verification.checks,
    summaryText: verification.summary,
    bundleText: verification.bundleLabel,
    passingText: previewValue(preview, lines, "Verification passing"),
    failingText: previewValue(preview, lines, "Verification failing"),
  });
  if (explicit !== "n/a" && explicit !== "none" && (!isGenericVerificationLabel(explicit) || bundle.length === 0)) {
    return `Status ${explicit}`;
  }
  if (bundle.length > 0) {
    return `Status ${buildVerificationSummaryRows(bundle).status}`;
  }

  return "Status unknown";
}

function verificationPassingRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = previewValue(preview, lines, "Verification passing");
  const verification = derivedVerificationInputs(preview, lines);
  const bundle = resolveVerificationEntries({
    checksText: verification.checks,
    summaryText: verification.summary,
    bundleText: verification.bundleLabel,
    passingText: explicit,
    failingText: previewValue(preview, lines, "Verification failing"),
  });
  if (explicit !== "n/a" && explicit !== "none" && (!isGenericVerificationLabel(explicit) || bundle.length === 0)) {
    return `Passing ${explicit}`;
  }
  if (bundle.length === 0) {
    return "Passing unknown";
  }
  return `Passing ${buildVerificationSummaryRows(bundle).passing}`;
}

function verificationFailingRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = previewValue(preview, lines, "Verification failing");
  const verification = derivedVerificationInputs(preview, lines);
  const bundle = resolveVerificationEntries({
    checksText: verification.checks,
    summaryText: verification.summary,
    bundleText: verification.bundleLabel,
    passingText: previewValue(preview, lines, "Verification passing"),
    failingText: explicit,
  });
  if (explicit !== "n/a" && explicit !== "none" && (!isGenericVerificationLabel(explicit) || bundle.length === 0)) {
    return `Failing ${explicit}`;
  }
  if (bundle.length === 0) {
    return "Failing unknown";
  }
  return `Failing ${buildVerificationSummaryRows(bundle).failing}`;
}

function verificationBundleRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const verification = derivedVerificationInputs(preview, lines);
  const explicit = verification.bundleLabel;
  if (explicit !== "n/a" && explicit !== "none" && !isGenericVerificationLabel(explicit)) {
    return `Bundle ${explicit}`;
  }
  const bundle = resolveVerificationEntries({
    checksText: verification.checks,
    summaryText: verification.summary,
    bundleText: explicit,
    passingText: previewValue(preview, lines, "Verification passing"),
    failingText: previewValue(preview, lines, "Verification failing"),
  });
  return `Bundle ${buildVerificationSummaryRows(bundle).bundle}`;
}

function verificationChecksRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const verification = derivedVerificationInputs(preview, lines);
  const explicit = verification.checks;
  if (explicit !== "n/a" && explicit !== "none" && !isGenericVerificationLabel(explicit)) {
    return `Checks ${explicit}`;
  }

  const bundle = resolveVerificationEntries({
    checksText: verification.checks,
    summaryText: verification.summary,
    bundleText: verification.bundleLabel,
    passingText: previewValue(preview, lines, "Verification passing"),
    failingText: previewValue(preview, lines, "Verification failing"),
  });
  if (bundle.length === 0) {
    return "Checks unknown";
  }
  return `Checks ${bundle.map((entry) => `${entry.name} ${entry.ok ? "ok" : "fail"}`).join("; ")}`;
}

function verificationSummaryRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const verification = derivedVerificationInputs(preview, lines);
  const explicit = verification.summary;
  const bundle = resolveVerificationEntries({
    checksText: verification.checks,
    summaryText: explicit,
    bundleText: verification.bundleLabel,
    passingText: previewValue(preview, lines, "Verification passing"),
    failingText: previewValue(preview, lines, "Verification failing"),
  });
  if (explicit !== "n/a" && explicit !== "none" && (!isGenericVerificationLabel(explicit) || bundle.length === 0)) {
    return `Summary ${explicit}`;
  }
  if (bundle.length > 0) {
    return `Summary ${buildVerificationSummaryRows(bundle).bundle}`;
  }
  return "Summary unknown";
}

function verificationUpdatedRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const verification = derivedVerificationInputs(preview, lines);
  const updated = previewValue(preview, lines, "Verification updated");
  const fallbackUpdated = derivedUpdated(preview, lines);
  const effectiveUpdated = hasSignal(updated)
    ? updated
    : resolveVerificationEntries({
          checksText: verification.checks,
          summaryText: verification.summary,
          bundleText: verification.bundleLabel,
          passingText: previewValue(preview, lines, "Verification passing"),
          failingText: previewValue(preview, lines, "Verification failing"),
        }).length > 0
      ? fallbackUpdated
      : "unknown";
  return hasSignal(effectiveUpdated) ? `Updated ${effectiveUpdated}` : "Updated unknown";
}

function derivedVerificationReceipt(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicitReceipt = previewValue(preview, lines, "Verification receipt");
  const durableState = previewValue(preview, lines, "Durable state");
  return hasSignal(explicitReceipt)
    ? explicitReceipt
    : hasSignal(durableState)
      ? path.join(durableState, "verification.json")
      : "unknown";
}

function verificationReceiptRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const receipt = derivedVerificationReceipt(preview, lines);
  const updated = verificationUpdatedRow(preview, lines).replace(/^Updated\s+/, "");
  if (hasSignal(receipt)) {
    return hasSignal(updated) ? `Receipt ${receipt} | updated ${updated}` : `Receipt ${receipt}`;
  }
  return "Receipt unknown";
}

function verificationOverviewRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const status = verificationStatusRow(preview, lines).replace(/^Status\s+/, "");
  if (status === "unknown") {
    return "Verification unknown";
  }
  const failing = verificationFailingRow(preview, lines).replace(/^Failing\s+/, "");
  return failing !== "unknown" && failing !== "none" ? `Verification ${status} | failing ${failing}` : `Verification ${status}`;
}

function verificationSignalRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const overview = verificationOverviewRow(preview, lines);
  if (overview === "Verification unknown") {
    return overview;
  }
  const updated = verificationUpdatedRow(preview, lines).replace(/^Updated\s+/, "");
  return hasSignal(updated) ? `${overview} | updated ${updated}` : overview;
}

function freshnessRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const freshness = derivedFreshness(preview, lines);
  return hasSignal(freshness) ? `Freshness ${freshness}` : "Freshness unknown";
}

function loopVerificationRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const verification = verificationOverviewRow(preview, lines);
  return verification === "Verification unknown" ? "Verify unknown" : verification.replace(/^Verification\s+/, "Verify ");
}

function decisionSummaryRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const loopDecision = previewValue(preview, lines, "Loop decision");
  const nextTask = previewValue(preview, lines, "Next task");
  const parts = [loopDecision, nextTask].filter(hasSignal);
  return parts.length > 0 ? `Decision ${parts.join(" | ")}` : "Decision unknown";
}

function durabilitySectionRows(preview: TabPreview | undefined, lines: TranscriptLine[]): string[] {
  const rows: string[] = [];
  const durableState = previewValue(preview, lines, "Durable state");
  const receipt = verificationReceiptRow(preview, lines);
  const truth = previewValue(preview, lines, "Control truth preview");
  const pulse = buildControlPulseRow(preview, lines);

  if (hasSignal(durableState)) {
    rows.push(`State ${durableState}`);
  }
  if (!/\sunknown$/.test(receipt)) {
    rows.push(receipt);
  }
  if (hasSignal(truth)) {
    rows.push(`Truth ${truth}`);
  }
  if (rows.length > 0 && !/\sunknown$/.test(pulse)) {
    rows.push(pulse);
  }

  return rows;
}

function loopSectionRows(preview: TabPreview | undefined, lines: TranscriptLine[]): string[] {
  const rows: string[] = [];
  const loopState = derivedLoopState(preview, lines);
  const activeTask = previewValue(preview, lines, "Active task");
  const taskProgress = previewValue(preview, lines, "Task progress");
  const resultStatus = derivedResultStatus(preview, lines);
  const acceptance = derivedAcceptance(preview, lines);
  const verification = loopVerificationRow(preview, lines);
  const freshness = derivedFreshness(preview, lines);
  const loopDecision = previewValue(preview, lines, "Loop decision");
  const updated = derivedUpdated(preview, lines);

  if (hasSignal(loopState)) {
    rows.push(`State ${loopState}`);
  }
  if (hasSignal(activeTask) || hasSignal(taskProgress)) {
    rows.push(`Task ${activeTask} | ${taskProgress}`);
  }
  if (hasSignal(resultStatus) || hasSignal(acceptance)) {
    rows.push(`Outcome ${resultStatus} | accept ${acceptance}`);
  }
  if (verification !== "Verify unknown") {
    rows.push(verification);
  }
  if (hasSignal(freshness)) {
    rows.push(`Freshness ${freshness}`);
  }
  if (hasSignal(loopDecision)) {
    rows.push(`Decision ${loopDecision}`);
  }
  if (hasSignal(updated)) {
    rows.push(`Updated ${updated}`);
  }

  return rows;
}

function overviewSectionRows(preview: TabPreview | undefined, lines: TranscriptLine[]): string[] {
  const rows: string[] = [];
  const loopState = derivedLoopState(preview, lines);
  const taskProgress = previewValue(preview, lines, "Task progress");
  const activeTask = previewValue(preview, lines, "Active task");
  const controlPulse = buildControlPulseRow(preview, lines);
  const resultStatus = derivedResultStatus(preview, lines);
  const acceptance = derivedAcceptance(preview, lines);
  const freshness = derivedFreshness(preview, lines);
  const runtimeActivity = parseRuntimeMetrics(previewValue(preview, lines, "Runtime activity"));
  const artifactState = parseRuntimeMetrics(previewValue(preview, lines, "Artifact state"));
  const contextState = previewValue(preview, lines, "Context state");
  const verification = verificationOverviewRow(preview, lines);
  const decisionSummary = decisionSummaryRow(preview, lines);
  const durableState = previewValue(preview, lines, "Durable state");

  if (hasSignal(loopState) || hasSignal(taskProgress) || hasSignal(activeTask)) {
    rows.push(`Loop ${[loopState, taskProgress, activeTask].filter(hasSignal).join(" | ")}`);
  }
  if (hasSignal(resultStatus) || hasSignal(acceptance)) {
    rows.push(`Outcome ${[resultStatus, acceptance].filter(hasSignal).join(" / ")}`);
  }
  if (!/\sunknown$/.test(controlPulse)) {
    rows.push(controlPulse);
  }
  if (verification !== "Verification unknown") {
    rows.push(verification);
  }
  if (hasSignal(freshness)) {
    rows.push(`Freshness ${freshness}`);
  }
  if (Object.keys(runtimeActivity).length > 0) {
    rows.push(
      `Runtime ${[
        metricFragment(runtimeActivity, "Sessions", "sessions"),
        metricFragment(runtimeActivity, "Runs", "runs"),
        nonZeroMetricFragment(runtimeActivity, "ActiveRuns", "active runs"),
        nonZeroMetricFragment(runtimeActivity, "ActiveClaims", "active claims"),
      ]
        .filter((value) => value.length > 0)
        .join(" | ")}`,
    );
  } else {
    const runtimeSummary = runtimeSummaryRow(preview, lines);
    if (runtimeSummary !== "Runtime unknown") {
      rows.push(runtimeSummary);
    }
  }
  if (hasSignal(contextState)) {
    rows.push(`Context ${contextState}`);
  } else if (Object.keys(artifactState).length > 0) {
    rows.push(
      `Context ${[
        metricFragment(artifactState, "Artifacts", "artifacts"),
        nonZeroMetricFragment(artifactState, "PromotedFacts", "promoted facts"),
        nonZeroMetricFragment(artifactState, "ContextBundles", "context bundles"),
        nonZeroMetricFragment(artifactState, "OperatorActions", "operator actions"),
      ]
        .filter((value) => value.length > 0)
        .join(" | ")}`,
    );
  }
  if (decisionSummary !== "Decision unknown") {
    rows.push(decisionSummary);
  }
  if (hasSignal(durableState)) {
    rows.push(`State ${durableState}`);
  }

  return rows;
}

function runtimeSectionRows(preview: TabPreview | undefined, lines: TranscriptLine[]): string[] {
  const rows: string[] = [];
  const runtimeDb = previewValue(preview, lines, "Runtime DB");
  const sessionState = previewValue(preview, lines, "Session state");
  const runState = previewValue(preview, lines, "Run state");
  const activeRunsDetail = previewValue(preview, lines, "Active runs detail");
  const contextState = previewValue(preview, lines, "Context state");
  const recentActions = previewValue(preview, lines, "Recent operator actions");
  const runtimeActivity = previewValue(preview, lines, "Runtime activity");
  const artifactState = previewValue(preview, lines, "Artifact state");

  if (hasSignal(runtimeDb)) {
    rows.push(`DB ${runtimeDb}`);
  }
  if (hasSignal(sessionState) || Object.keys(parseRuntimeMetrics(runtimeActivity)).length > 0) {
    rows.push(
      runtimeRow(
        preview,
        lines,
        "Session state",
        "Sessions",
        (metrics) =>
          joinMetricFragments([
            metricFragment(metrics, "Sessions", "sessions"),
            metricFragment(metrics, "Claims", "claims"),
            metricFragment(metrics, "ActiveClaims", "active claims"),
            metricFragment(metrics, "AckedClaims", "acked claims"),
          ]),
      ),
    );
  }
  if (hasSignal(runState) || Object.keys(parseRuntimeMetrics(runtimeActivity)).length > 0) {
    rows.push(
      runtimeRow(
        preview,
        lines,
        "Run state",
        "Runs",
        (metrics) =>
          joinMetricFragments([
            metricFragment(metrics, "Runs", "runs"),
            metricFragment(metrics, "ActiveRuns", "active runs"),
          ]),
      ),
    );
  }
  if (hasSignal(activeRunsDetail)) {
    rows.push(`Active ${activeRunsDetail}`);
  }
  if (hasSignal(contextState) || Object.keys(parseRuntimeMetrics(artifactState)).length > 0) {
    rows.push(
      runtimeRow(
        preview,
        lines,
        "Context state",
        "Context",
        (metrics) =>
          joinMetricFragments([
            metricFragment(metrics, "Artifacts", "artifacts"),
            metricFragment(metrics, "PromotedFacts", "promoted facts"),
            metricFragment(metrics, "ContextBundles", "context bundles"),
            metricFragment(metrics, "OperatorActions", "operator actions"),
          ]),
      ),
    );
  }
  if (hasSignal(recentActions)) {
    rows.push(`Actions ${recentActions}`);
  }
  if (hasSignal(runtimeActivity)) {
    rows.push(`Activity ${runtimeActivity}`);
  }
  if (hasSignal(artifactState)) {
    rows.push(`Artifacts ${artifactState}`);
  }
  if (
    !hasSignal(sessionState) &&
    !hasSignal(runState) &&
    !hasSignal(contextState) &&
    !hasSignal(runtimeActivity) &&
    !hasSignal(artifactState)
  ) {
    const runtimeSummary = previewValue(preview, lines, "Runtime summary");
    if (hasSignal(runtimeSummary)) {
      rows.push(`Summary ${runtimeSummary}`);
    }
  }

  return rows;
}

export function buildOperatorSignalRows(
  mode: "control" | "runtime",
  preview?: TabPreview,
  lines: TranscriptLine[] = [],
): SignalRow[] {
  const loopParts = [
    derivedLoopState(preview, lines),
    previewValue(preview, lines, "Loop decision"),
    derivedUpdated(preview, lines),
  ].filter(hasSignal);
  const freshness = derivedFreshness(preview, lines);
  const verification = verificationSignalRow(preview, lines);
  const runtime = runtimeOverviewRow(preview, lines);
  const activeTask = previewValue(preview, lines, "Active task");
  const taskProgress = previewValue(preview, lines, "Task progress");
  const verificationReceipt = derivedVerificationReceipt(preview, lines);
  const durableState = previewValue(preview, lines, "Durable state");
  const nextTask = previewValue(preview, lines, "Next task");
  const taskContext = signalTaskContextRow(mode, activeTask, taskProgress, nextTask);
  const durabilityContext = signalDurabilityRow(verificationReceipt, durableState);

  const rows: SignalRow[] = [];
  if (loopParts.length > 0) {
    rows.push({value: `Loop ${loopParts.join(" | ")}`, tone: "strong"});
  }
  if (verification !== "Verification unknown") {
    rows.push({
      value: verification,
      tone: /failing/i.test(verification) ? "warning" : "strong",
    });
  }
  if (hasSignal(freshness) && (mode === "runtime" || freshness === "stale")) {
    rows.push({value: `Freshness ${freshness}`, tone: freshness === "stale" ? "warning" : "muted"});
  }
  if (mode === "control" && taskContext) {
    rows.push({value: taskContext, tone: "muted"});
  }
  if (mode === "control" && durabilityContext) {
    rows.push({value: durabilityContext, tone: "muted"});
  }
  if (runtime !== "Runtime unknown") {
    rows.push({value: runtime, tone: "muted"});
  } else if (mode === "control" && hasSignal(freshness) && freshness !== "stale") {
    rows.push({value: `Freshness ${freshness}`, tone: "muted"});
  }
  if (mode !== "control" && durabilityContext) {
    rows.push({value: durabilityContext, tone: "muted"});
  }
  if (mode !== "control" && taskContext) {
    rows.push({value: taskContext, tone: "muted"});
  }
  return rows.slice(0, mode === "control" ? 4 : 5);
}

export function buildControlPaneSections(preview?: TabPreview, lines: TranscriptLine[] = []): ControlSection[] {
  if (!hasStructuredControlState(preview, lines)) {
    return [
      {
        title: "Control Snapshot",
        rows: lines.length > 0 ? lines.slice(-24).map((line) => line.text) : ["No control snapshot yet."],
      },
    ];
  }

  const toolchain = previewValue(preview, lines, "Toolchain");
  const alerts = previewValue(preview, lines, "Alerts");
  const overviewRows = overviewSectionRows(preview, lines);
  const verificationOverview = verificationOverviewRow(preview, lines);
  const verificationSummary = verificationSummaryRow(preview, lines);
  const verificationBundle = verificationBundleRow(preview, lines);
  const verificationRows = [
    verificationOverview,
    freshnessRow(preview, lines),
    verificationUpdatedRow(preview, lines),
    verificationReceiptRow(preview, lines),
    verificationStatusRow(preview, lines),
    verificationPassingRow(preview, lines),
    verificationFailingRow(preview, lines),
    verificationChecksRow(preview, lines),
    verificationSummary,
    ...(verificationBundle !== verificationSummary.replace(/^Summary\s+/, "Bundle ") ? [verificationBundle] : []),
    `Last ${derivedLastResult(preview, lines)}`,
  ].filter((row) => row !== "Verification unknown" && !/\s(?:n\/a|none|unknown)$/.test(row));
  const decisionSummary = decisionSummaryRow(preview, lines);
  const nextRows = [
    decisionSummary,
    `Task ${previewValue(preview, lines, "Next task")}`,
    `State ${previewValue(preview, lines, "Durable state")}`,
  ].filter((row) => row !== "Decision unknown" && !/\s(?:n\/a|none|unknown)$/.test(row));

  return [
    {
      title: "Overview",
      rows: [
        ...authorityOverviewRows(preview, lines, overviewRows),
        ...overviewRows,
      ],
    },
    {
      title: "Loop",
      rows: loopSectionRows(preview, lines),
    },
    {
      title: "Runtime",
      rows: runtimeSectionRows(preview, lines).concat([
        ...(hasSignal(toolchain) ? [`Tools ${toolchain}`] : []),
        ...(hasSignal(alerts) ? [`Alerts ${alerts}`] : []),
      ]),
    },
    {
      title: "Verification",
      rows: verificationRows,
    },
    {
      title: "Durability",
      rows: durabilitySectionRows(preview, lines),
    },
    {
      title: "Next",
      rows: nextRows.filter((row) => row !== `State ${previewValue(preview, lines, "Durable state")}`),
    },
  ].filter((section) => section.rows.length > 0);
}

export function buildRuntimePaneSections(preview?: TabPreview, lines: TranscriptLine[] = []): ControlSection[] {
  if (!hasStructuredControlState(preview, lines)) {
    return [
      {
        title: "Runtime Snapshot",
        rows: lines.length > 0 ? lines.slice(-24).map((line) => line.text) : ["No runtime snapshot yet."],
      },
    ];
  }

  const toolRows = [
    ...(hasSignal(previewValue(preview, lines, "Toolchain")) ? [`Toolchain ${previewValue(preview, lines, "Toolchain")}`] : []),
    ...(hasSignal(previewValue(preview, lines, "Alerts")) ? [`Alerts ${previewValue(preview, lines, "Alerts")}`] : []),
  ];
  const overviewRows = overviewSectionRows(preview, lines);
  const verificationOverview = verificationOverviewRow(preview, lines);
  const verificationSummary = verificationSummaryRow(preview, lines);
  const verificationBundle = verificationBundleRow(preview, lines);
  const verificationRows = [
    verificationOverview,
    freshnessRow(preview, lines),
    verificationUpdatedRow(preview, lines),
    verificationReceiptRow(preview, lines),
    verificationStatusRow(preview, lines),
    verificationPassingRow(preview, lines),
    verificationFailingRow(preview, lines),
    verificationChecksRow(preview, lines),
    verificationSummary,
    ...(verificationBundle !== verificationSummary.replace(/^Summary\s+/, "Bundle ") ? [verificationBundle] : []),
    `Last ${derivedLastResult(preview, lines)}`,
  ].filter((row) => row !== "Verification unknown" && !/\s(?:n\/a|none|unknown)$/.test(row));
  const decisionSummary = decisionSummaryRow(preview, lines);
  const nextRows = [
    decisionSummary,
    `Task ${previewValue(preview, lines, "Next task")}`,
    `State ${previewValue(preview, lines, "Durable state")}`,
  ].filter((row) => row !== "Decision unknown" && !/\s(?:n\/a|none|unknown)$/.test(row));

  return [
    {
      title: "Overview",
      rows: [
        ...authorityOverviewRows(preview, lines, overviewRows),
        ...overviewRows,
      ],
    },
    {
      title: "Runtime",
      rows: runtimeSectionRows(preview, lines),
    },
    {
      title: "Tools",
      rows: toolRows,
    },
    {
      title: "Loop",
      rows: loopSectionRows(preview, lines),
    },
    {
      title: "Verification",
      rows: verificationRows,
    },
    {
      title: "Durability",
      rows: durabilitySectionRows(preview, lines),
    },
    {
      title: "Next",
      rows: nextRows.filter((row) => row !== `State ${previewValue(preview, lines, "Durable state")}`),
    },
  ].filter((section) => section.rows.length > 0);
}

export function ControlPane({
  title,
  mode = "control",
  preview,
  lines,
  scrollOffset = 0,
  windowSize = 24,
  selectedSectionIndex = 0,
}: Props): React.ReactElement {
  const sections = mode === "runtime" ? buildRuntimePaneSections(preview, lines) : buildControlPaneSections(preview, lines);
  const signalRows = buildOperatorSignalRows(mode, preview, lines);
  const activeSectionIndex = clampSectionIndex(selectedSectionIndex, sections);
  const activeSection = sections[activeSectionIndex];
  const visibleRows = activeSection ? activeSection.rows.slice(scrollOffset, scrollOffset + Math.max(windowSize - 4, 8)) : [];
  const detailRows: DetailRow[] = visibleRows.map((value, index) => ({
    value,
    tone: index === 0 || (activeSection?.title === "Overview" && index < 2) ? "strong" : "muted",
  }));

  return (
    <Box flexGrow={1} flexDirection="column" borderStyle="round" borderColor={THEME.river} paddingX={1}>
      <Text color={THEME.wave} bold>{title}</Text>
      <Text color={THEME.stone}>
        {mode === "runtime"
          ? "runtime pulse, verification, and loop state | j/k or ↑/↓ move between sections"
          : "control summary, loop health, and next action | j/k or ↑/↓ move between sections"}
      </Text>
      {signalRows.length > 0 ? (
        <Box marginTop={1} flexDirection="column" borderStyle="single" borderColor={THEME.ink} paddingX={1}>
          <Text color={THEME.parchment} bold>{mode === "runtime" ? "Runtime Signal" : "Control Signal"}</Text>
          {signalRows.map((row, index) => (
            <Text
              key={`signal-${index}`}
              color={row.tone === "warning" ? THEME.persimmon : row.tone === "strong" ? THEME.foam : THEME.stone}
              bold={row.tone !== "muted"}
            >
              {row.value}
            </Text>
          ))}
        </Box>
      ) : null}
      <Box marginTop={1}>
        <Box width="35%" flexDirection="column" borderStyle="single" borderColor={THEME.ink} paddingX={1}>
          <Text color={THEME.parchment} bold>Sections</Text>
          <Text color={THEME.stone}>{mode === "runtime" ? "runtime state cards" : "control loop cards"}</Text>
          {sections.map((section, index) => {
            const active = index === activeSectionIndex;
            const previewRows = sectionCardPreviewRows(section);
            return (
              <Box key={section.title} flexDirection="column" marginTop={1} borderStyle={active ? "round" : undefined} borderColor={active ? THEME.wave : undefined} paddingX={active ? 1 : 0}>
                <Text color={active ? THEME.wave : THEME.foam} bold={active}>
                  {active ? "▶ " : "• "}
                  {section.title}
                </Text>
                <Text color={active ? THEME.foam : THEME.stone}>
                  {"  "}{section.rows.length} rows
                </Text>
                {previewRows.map((row, rowIndex) => (
                  <Text key={`${section.title}-preview-${rowIndex}`} color={THEME.stone}>  {row}</Text>
                ))}
              </Box>
            );
          })}
        </Box>
        <Box width="65%" marginLeft={1} flexDirection="column" borderStyle="single" borderColor={THEME.ink} paddingX={1}>
          <Text color={THEME.wave} bold>{activeSection?.title ?? "Section"}</Text>
          <Text color={THEME.stone}>{mode === "runtime" ? "selected runtime card" : "selected control card"}</Text>
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
