import React from "react";
import {Box, Text} from "ink";

import type {TabPreview, TranscriptLine} from "../types.js";
import {buildVerificationSummaryRows, isGenericVerificationLabel, parseVerificationBundle} from "../verification.js";

type ControlSection = {
  title: string;
  rows: string[];
};

const STRUCTURED_CONTROL_LABELS = [
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
};

function previewValue(preview: TabPreview | undefined, lines: TranscriptLine[], label: string): string {
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

function hasSignal(value: string): boolean {
  return value !== "n/a" && value !== "none" && value !== "unknown";
}

function runtimeSummaryRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = previewValue(preview, lines, "Runtime summary");
  return hasSignal(explicit) ? `Runtime ${explicit}` : "Runtime unknown";
}

function buildControlPulseRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = previewValue(preview, lines, "Control pulse preview");
  if (explicit !== "n/a" && explicit !== "none") {
    return `Pulse ${explicit}`;
  }

  const lastResult = previewValue(preview, lines, "Last result");
  const runtimeFreshness = previewValue(preview, lines, "Runtime freshness");
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
  if (explicit !== "n/a" && explicit !== "none") {
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
    if (previewHasStructuredSignal) {
      return true;
    }
  }
  return STRUCTURED_CONTROL_LABELS.some((label) => lines.some((line) => line.text.startsWith(`${label}: `)));
}

function verificationStatusRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = previewValue(preview, lines, "Verification status");
  const bundle = parseVerificationBundle(
    previewValue(preview, lines, "Verification checks"),
    previewValue(preview, lines, "Verification summary"),
  );
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
  const bundle = parseVerificationBundle(
    previewValue(preview, lines, "Verification checks"),
    previewValue(preview, lines, "Verification summary"),
  );
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
  const bundle = parseVerificationBundle(
    previewValue(preview, lines, "Verification checks"),
    previewValue(preview, lines, "Verification summary"),
  );
  if (explicit !== "n/a" && explicit !== "none" && (!isGenericVerificationLabel(explicit) || bundle.length === 0)) {
    return `Failing ${explicit}`;
  }
  if (bundle.length === 0) {
    return "Failing unknown";
  }
  return `Failing ${buildVerificationSummaryRows(bundle).failing}`;
}

function verificationBundleRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = previewValue(preview, lines, "Verification bundle");
  if (explicit !== "n/a" && explicit !== "none" && !isGenericVerificationLabel(explicit)) {
    return `Bundle ${explicit}`;
  }
  const bundle = parseVerificationBundle(
    previewValue(preview, lines, "Verification checks"),
    previewValue(preview, lines, "Verification summary"),
  );
  return `Bundle ${buildVerificationSummaryRows(bundle).bundle}`;
}

function verificationSummaryRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = previewValue(preview, lines, "Verification summary");
  const bundle = parseVerificationBundle(
    previewValue(preview, lines, "Verification checks"),
    explicit,
  );
  if (explicit !== "n/a" && explicit !== "none" && (!isGenericVerificationLabel(explicit) || bundle.length === 0)) {
    return `Summary ${explicit}`;
  }
  if (bundle.length > 0) {
    return `Summary ${buildVerificationSummaryRows(bundle).bundle}`;
  }
  return "Summary unknown";
}

function verificationOverviewRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const status = verificationStatusRow(preview, lines).replace(/^Status\s+/, "");
  if (status === "unknown") {
    return "Verification unknown";
  }
  const failing = verificationFailingRow(preview, lines).replace(/^Failing\s+/, "");
  return failing !== "unknown" && failing !== "none" ? `Verification ${status} | failing ${failing}` : `Verification ${status}`;
}

function loopSectionRows(preview: TabPreview | undefined, lines: TranscriptLine[]): string[] {
  const rows: string[] = [];
  const loopState = previewValue(preview, lines, "Loop state");
  const activeTask = previewValue(preview, lines, "Active task");
  const taskProgress = previewValue(preview, lines, "Task progress");
  const resultStatus = previewValue(preview, lines, "Result status");
  const acceptance = previewValue(preview, lines, "Acceptance");
  const loopDecision = previewValue(preview, lines, "Loop decision");
  const updated = previewValue(preview, lines, "Updated");

  if (hasSignal(loopState)) {
    rows.push(`State ${loopState}`);
  }
  if (hasSignal(activeTask) || hasSignal(taskProgress)) {
    rows.push(`Task ${activeTask} | ${taskProgress}`);
  }
  if (hasSignal(resultStatus) || hasSignal(acceptance)) {
    rows.push(`Outcome ${resultStatus} | accept ${acceptance}`);
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
  const loopState = previewValue(preview, lines, "Loop state");
  const taskProgress = previewValue(preview, lines, "Task progress");
  const activeTask = previewValue(preview, lines, "Active task");
  const controlPulse = buildControlPulseRow(preview, lines);
  const resultStatus = previewValue(preview, lines, "Result status");
  const acceptance = previewValue(preview, lines, "Acceptance");
  const runtimeActivity = parseRuntimeMetrics(previewValue(preview, lines, "Runtime activity"));
  const artifactState = parseRuntimeMetrics(previewValue(preview, lines, "Artifact state"));
  const contextState = previewValue(preview, lines, "Context state");
  const verification = verificationOverviewRow(preview, lines);
  const loopDecision = previewValue(preview, lines, "Loop decision");
  const nextTask = previewValue(preview, lines, "Next task");
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
  if (hasSignal(loopDecision) || hasSignal(nextTask)) {
    rows.push(`Decision ${[loopDecision, nextTask].filter(hasSignal).join(" | ")}`);
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
  const verificationRows = [
    verificationStatusRow(preview, lines),
    verificationPassingRow(preview, lines),
    verificationFailingRow(preview, lines),
    verificationSummaryRow(preview, lines),
    verificationBundleRow(preview, lines),
    `Last ${previewValue(preview, lines, "Last result")}`,
  ].filter((row) => !/\s(?:n\/a|none|unknown)$/.test(row));
  const nextRows = [
    `Task ${previewValue(preview, lines, "Next task")}`,
    `State ${previewValue(preview, lines, "Durable state")}`,
  ].filter((row) => !/\s(?:n\/a|none|unknown)$/.test(row));

  return [
    {
      title: "Overview",
      rows: [
        ...(hasSignal(previewValue(preview, lines, "Authority")) ? [`Authority ${previewValue(preview, lines, "Authority")}`] : []),
        ...overviewSectionRows(preview, lines),
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
  const verificationRows = [
    verificationStatusRow(preview, lines),
    verificationPassingRow(preview, lines),
    verificationFailingRow(preview, lines),
    verificationBundleRow(preview, lines),
    verificationSummaryRow(preview, lines),
    `Last ${previewValue(preview, lines, "Last result")}`,
  ].filter((row) => !/\s(?:n\/a|none|unknown)$/.test(row));
  const nextRows = [
    `Task ${previewValue(preview, lines, "Next task")}`,
    `State ${previewValue(preview, lines, "Durable state")}`,
  ].filter((row) => !/\s(?:n\/a|none|unknown)$/.test(row));

  return [
    {
      title: "Overview",
      rows: [
        ...(hasSignal(previewValue(preview, lines, "Authority")) ? [`Authority ${previewValue(preview, lines, "Authority")}`] : []),
        ...overviewSectionRows(preview, lines),
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
      title: "Next",
      rows: nextRows,
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
}: Props): React.ReactElement {
  const sections = mode === "runtime" ? buildRuntimePaneSections(preview, lines) : buildControlPaneSections(preview, lines);
  const flattened = sections.flatMap((section) => [
    {kind: "section" as const, id: section.title, text: section.title},
    ...section.rows.map((row, index) => ({kind: "row" as const, id: `${section.title}-${index}`, text: row})),
    {kind: "spacer" as const, id: `${section.title}-spacer`, text: ""},
  ]);
  const visible = flattened.slice(scrollOffset, scrollOffset + windowSize);

  return (
    <Box flexGrow={1} flexDirection="column" borderStyle="single" borderColor="gray" paddingX={1}>
      <Text color="cyan">{title}</Text>
      <Text color="gray"> </Text>
      {visible.map((entry) => (
        <Text key={entry.id} color={entry.kind === "section" ? "white" : "gray"}>
          {entry.text}
        </Text>
      ))}
    </Box>
  );
}
