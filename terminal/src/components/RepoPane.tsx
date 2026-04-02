import React from "react";
import {Box, Text} from "ink";

import {freshnessToken} from "../freshness.js";
import type {TabPreview, TranscriptLine} from "../types.js";

type RepoSection = {
  title: string;
  rows: string[];
};

type Props = {
  title: string;
  preview?: TabPreview;
  controlPreview?: TabPreview;
  lines: TranscriptLine[];
  controlLines?: TranscriptLine[];
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

function buildBranchLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return `${previewValue(preview, lines, "Branch")}@${previewValue(preview, lines, "Head")}`;
}

function buildDirtyCountsLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return `staged ${previewValue(preview, lines, "Staged")} | unstaged ${previewValue(preview, lines, "Unstaged")} | untracked ${previewValue(preview, lines, "Untracked")}`;
}

function buildRuntimeActivityLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return `${previewValue(preview, lines, "Runtime activity")} | ${previewValue(preview, lines, "Artifact state")}`;
}

function buildRepoHealthLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return `${previewValue(preview, lines, "Repo risk")} | ${previewValue(preview, lines, "Sync")}`;
}

function buildTopologySignalLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return `${previewValue(preview, lines, "Topology warning severity")} | ${previewValue(preview, lines, "Primary peer drift")}`;
}

function buildTopologyAlertLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const severity = previewValue(preview, lines, "Topology warning severity");
  const warning = previewValue(preview, lines, "Primary warning");
  const drift = previewValue(preview, lines, "Primary peer drift");
  return `${severity} | warning ${warning} | drift ${drift}`;
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

function buildHotspotPressurePreviewLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = preview?.["Hotspot pressure preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return explicit;
  }
  const parts: string[] = [];
  const change = previewValue(preview, lines, "Primary changed hotspot");
  const dep = previewValue(preview, lines, "Primary dependency hotspot");
  if (change !== "n/a" && change !== "none") {
    parts.push(`change ${change}`);
  }
  if (dep !== "n/a" && dep !== "none") {
    parts.push(`dep ${dep}`);
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
  const rows = [
    `Snapshot branch ${buildBranchLabel(preview, lines)} | ${previewValue(preview, lines, "Branch status")}`,
    `Snapshot dirty ${previewValue(preview, lines, "Dirty pressure")} | ${buildDirtyCountsLabel(preview, lines)}`,
    `Snapshot topology ${previewValue(preview, lines, "Topology status")} | warnings ${previewValue(preview, lines, "Topology warnings")}`,
    `Snapshot warnings ${previewValue(preview, lines, "Primary warning")} | severity ${previewValue(preview, lines, "Topology warning severity")}`,
    `Snapshot alert ${buildTopologyAlertLabel(preview, lines)}`,
    `Snapshot topology preview ${buildTopologyPreviewLabel(preview, lines)}`,
    `Snapshot pressure ${buildTopologyPressurePreviewLabel(preview, lines)}`,
    `Snapshot hotspots ${buildLeadHotspotPreviewLabel(preview, lines)}`,
    `Snapshot hotspot summary ${previewValue(preview, lines, "Hotspot summary")}`,
    `Snapshot summary ${previewValue(preview, lines, "Repo risk")} | hotspots ${previewValue(preview, lines, "Hotspot summary")}`,
  ];

  if (controlPreview || controlLines.length > 0) {
    rows.push(`Snapshot repo/control ${buildRepoControlCorrelationLabel(preview, lines, controlPreview, controlLines, now)}`);
    rows.push(buildRepoSnapshotTaskRow(controlPreview, controlLines));
    rows.push(`Snapshot runtime ${buildRepoRuntimeStateLabel(controlPreview, controlLines)}`);
    rows.push(`Snapshot freshness ${buildRepoControlCorrelationDetails(preview, lines, controlPreview, controlLines, now)}`);
  }

  return rows;
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
  const leadPressure = previewValue(preview, lines, "Topology pressure").split(";")[0]?.trim() || "none";
  if (warnings === "n/a" && leadPressure === "none") {
    return "n/a";
  }
  if (leadPressure === "none") {
    return warnings;
  }
  return `${warnings} | ${leadPressure}`;
}

function buildRiskPreviewLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  const explicit = preview?.["Risk preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return explicit;
  }
  const warning = previewValue(preview, lines, "Primary warning");
  const peer = previewValue(preview, lines, "Primary topology peer");
  if (warning === "n/a" && peer === "n/a") {
    return "n/a";
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
  if (riskPreview === "n/a" || riskPreview === "stable") {
    return branchStatus;
  }
  return `${branchStatus} | ${riskPreview}`;
}

function buildRepoRiskRows(preview: TabPreview | undefined, lines: TranscriptLine[]): string[] {
  return [
    `Severity ${previewValue(preview, lines, "Topology warning severity")} | warning ${previewValue(preview, lines, "Primary warning")}`,
    `Peer drift ${previewValue(preview, lines, "Primary peer drift")}`,
    `Lead peer ${previewValue(preview, lines, "Primary topology peer")}`,
    `Pressure ${previewValue(preview, lines, "Topology pressure")}`,
  ];
}

function buildRepoRiskSectionRows(preview: TabPreview | undefined, lines: TranscriptLine[]): string[] {
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
  ];
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
  return [
    freshnessToken(updated, now),
    ...(activeTask !== "n/a" && activeTask !== "none" ? [`task ${activeTask}`] : []),
    buildRepoRiskPreviewLabel(preview, lines),
    runtimeFreshness,
  ].join(" | ");
}

function hasControlSnapshotSignal(controlPreview?: TabPreview, controlLines: TranscriptLine[] = []): boolean {
  if (controlPreview) {
    return true;
  }
  return controlLines.some((line) =>
    /^(Active task|Loop state|Runtime freshness|Updated|Verification bundle):\s+/.test(line.text),
  );
}

function buildRepoControlCorrelationLabel(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  controlPreview?: TabPreview,
  controlLines: TranscriptLine[] = [],
  now: Date = new Date(),
): string {
  const explicit = preview?.["Repo/control preview"];
  if (!hasControlSnapshotSignal(controlPreview, controlLines) && typeof explicit === "string" && explicit.length > 0) {
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
    previewValue(preview, lines, "Verification bundle"),
  ].join(" | ");
}

function buildControlPulseLabel(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  now: Date = new Date(),
): string {
  const updated = previewValue(preview, lines, "Updated");
  const age = freshnessToken(updated, now);
  const explicit = preview?.["Control pulse preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return /^(fresh|stale|unknown)\b/.test(explicit) ? explicit : `${age} | ${explicit}`;
  }
  return [
    age,
    previewValue(preview, lines, "Last result"),
    previewValue(preview, lines, "Runtime freshness"),
  ].join(" | ");
}

function buildControlHealthLabel(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return `${previewValue(preview, lines, "Verification bundle")} | alerts ${previewValue(preview, lines, "Alerts")}`;
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
    previewValue(preview, lines, "Verification bundle"),
    `next ${previewValue(preview, lines, "Next task")}`,
  ].join(" | ");
}

function buildControlFreshnessDetails(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  now: Date = new Date(),
): string {
  const updated = previewValue(preview, lines, "Updated");
  return [
    freshnessToken(updated, now),
    previewValue(preview, lines, "Loop state"),
    `updated ${updated}`,
    `verify ${previewValue(preview, lines, "Verification bundle")}`,
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
    `Snapshot loop ${freshnessToken(previewValue(preview, lines, "Updated"), now)} | ${previewValue(preview, lines, "Loop state")} | ${previewValue(preview, lines, "Loop decision")}`,
    `Snapshot verify ${previewValue(preview, lines, "Verification bundle")}`,
    `Snapshot truth ${previewValue(preview, lines, "Verification bundle")} | ${previewValue(preview, lines, "Loop state")} | next ${previewValue(preview, lines, "Next task")}`,
  ];
}

function buildRepoSnapshotTaskRow(preview: TabPreview | undefined, lines: TranscriptLine[]): string {
  return `Snapshot task ${previewValue(preview, lines, "Active task")} | ${previewValue(preview, lines, "Result status")}/${previewValue(preview, lines, "Acceptance")} | ${previewValue(preview, lines, "Loop state")} | ${previewValue(preview, lines, "Loop decision")}`;
}

function buildOperatorSnapshotRows(
  preview: TabPreview | undefined,
  lines: TranscriptLine[],
  controlPreview?: TabPreview,
  controlLines: TranscriptLine[] = [],
  now: Date = new Date(),
): string[] {
  const rows = [
    buildRepoOverviewLabel(preview, lines),
    buildRepoPulseLabel(preview, lines),
    `Snapshot branch ${buildBranchLabel(preview, lines)} | ${previewValue(preview, lines, "Branch status")}`,
    `Snapshot dirty ${previewValue(preview, lines, "Dirty pressure")} | ${buildDirtyCountsLabel(preview, lines)}`,
    `Snapshot topology ${previewValue(preview, lines, "Topology status")} | warnings ${previewValue(preview, lines, "Topology warnings")}`,
    `Snapshot warnings ${previewValue(preview, lines, "Primary warning")} | severity ${previewValue(preview, lines, "Topology warning severity")}`,
    `Snapshot topology preview ${buildTopologyPreviewLabel(preview, lines)}`,
    `Snapshot hotspots ${buildLeadHotspotPreviewLabel(preview, lines)}`,
    `Snapshot hotspot summary ${previewValue(preview, lines, "Hotspot summary")}`,
    `Snapshot summary ${previewValue(preview, lines, "Repo risk")} | hotspots ${previewValue(preview, lines, "Hotspot summary")}`,
    `Snapshot repo risk ${buildRepoRiskPreviewLabel(preview, lines)}`,
    `Snapshot focus ${buildRepoFocusLabel(preview, lines)}`,
    `Snapshot pressure ${buildRepoTopologyPulseLabel(preview, lines)}`,
    `Snapshot topology pressure ${buildTopologyPressurePreviewLabel(preview, lines)}`,
    `Snapshot hotspot pressure ${buildHotspotPressurePreviewLabel(preview, lines)}`,
  ];

  if (controlPreview || controlLines.length > 0) {
    rows.push(`Snapshot repo/control ${buildRepoControlCorrelationLabel(preview, lines, controlPreview, controlLines, now)}`);
    rows.push(buildControlOverviewLabel(controlPreview, controlLines));
    rows.push(`Control pulse ${buildControlPulseLabel(controlPreview, controlLines, now)}`);
    rows.push(`Runtime state ${buildRepoRuntimeStateLabel(controlPreview, controlLines)}`);
    rows.push(`Control task ${buildRepoControlTaskLabel(controlPreview, controlLines)}`);
    rows.push(`Control verify ${buildRepoControlVerificationLabel(controlPreview, controlLines)}`);
    rows.push(buildControlFreshnessLabel(controlPreview, controlLines, now));
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
      rows: [
        ...(preview?.Authority ? [`Authority ${preview.Authority}`] : []),
        `Root ${previewValue(preview, lines, "Repo root")}`,
        `Branch ${buildBranchLabel(preview, lines)}`,
        `Track ${previewValue(preview, lines, "Branch status")} | upstream ${previewValue(preview, lines, "Upstream")}`,
        `Branch preview ${buildBranchSyncPreviewLabel(preview, lines)}`,
        `Sync ${previewValue(preview, lines, "Sync")} | +${previewValue(preview, lines, "Ahead")}/-${previewValue(preview, lines, "Behind")}`,
        `Health ${buildRepoHealthLabel(preview, lines)}`,
        `Repo risk preview ${buildRepoRiskPreviewLabel(preview, lines)}`,
        ...(controlPreview || controlLines.length > 0 ? [buildRepoSnapshotTaskRow(controlPreview, controlLines)] : []),
        ...(controlPreview || controlLines.length > 0
          ? [`Snapshot runtime ${buildRepoRuntimeStateLabel(controlPreview, controlLines)}`]
          : []),
        ...(controlPreview || controlLines.length > 0
          ? [`Snapshot freshness ${buildRepoControlCorrelationDetails(preview, lines, controlPreview, controlLines, now)}`]
          : []),
        ...(controlPreview || controlLines.length > 0
          ? [
              `Snapshot truth ${previewValue(controlPreview, controlLines, "Verification bundle")} | ${previewValue(controlPreview, controlLines, "Loop state")} | next ${previewValue(controlPreview, controlLines, "Next task")}`,
            ]
          : []),
        `Dirty ${previewValue(preview, lines, "Dirty pressure")} | ${buildDirtyCountsLabel(preview, lines)}`,
        `Hotspots ${previewValue(preview, lines, "Hotspot summary")}`,
        `Warnings ${previewValue(preview, lines, "Primary warning")} | severity ${previewValue(preview, lines, "Topology warning severity")}`,
        `Lead change ${previewValue(preview, lines, "Primary changed hotspot")} | path ${previewValue(preview, lines, "Primary changed path")}`,
        `Lead file ${previewValue(preview, lines, "Primary file hotspot")}`,
        `Lead dep ${previewValue(preview, lines, "Primary dependency hotspot")}`,
      ],
    },
    {
      title: "Repo Risk",
      rows: buildRepoRiskSectionRows(preview, lines),
    },
    {
      title: "Git",
      rows: [
        `Branch ${buildBranchLabel(preview, lines)}`,
        `Upstream ${previewValue(preview, lines, "Upstream")} | +${previewValue(preview, lines, "Ahead")}/-${previewValue(preview, lines, "Behind")}`,
        `Track ${previewValue(preview, lines, "Branch status")}`,
        `Preview ${buildBranchSyncPreviewLabel(preview, lines)}`,
        `Sync ${previewValue(preview, lines, "Sync")}`,
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
        `Warnings ${previewValue(preview, lines, "Topology warnings")}`,
        `Severity ${previewValue(preview, lines, "Topology warning severity")}`,
        `Risk ${previewValue(preview, lines, "Topology risk")}`,
        `Signal ${buildTopologySignalLabel(preview, lines)}`,
        `Topology preview ${buildTopologyPreviewLabel(preview, lines)}`,
        `Preview ${buildRiskPreviewLabel(preview, lines)}`,
        `Lead ${previewValue(preview, lines, "Primary warning")}`,
        `Drift ${previewValue(preview, lines, "Peer drift markers")}`,
        `Lead peer ${previewValue(preview, lines, "Primary topology peer")}`,
        `Peers ${previewValue(preview, lines, "Topology peers")}`,
        `Pressure ${previewValue(preview, lines, "Topology pressure")}`,
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

  if (controlPreview || controlLines.length > 0) {
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
}: Props): React.ReactElement {
  const sections = buildRepoPaneSections(preview, lines, controlPreview, controlLines);
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
