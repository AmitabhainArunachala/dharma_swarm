import React from "react";
import {Box, Text} from "ink";

import {freshnessToken} from "../freshness.js";
import type {OutlineItem, SidebarMode, TabPreview, TabSpec} from "../types.js";

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
};

function lineValueFor(tabs: TabSpec[], tabId: string, label: string, preview?: TabPreview): string {
  const previewValue = preview?.[label];
  if (typeof previewValue === "string" && previewValue.length > 0) {
    return previewValue;
  }
  const tab = tabs.find((entry) => entry.id === tabId);
  const tabPreviewValue = tab?.preview?.[label];
  if (typeof tabPreviewValue === "string" && tabPreviewValue.length > 0) {
    return tabPreviewValue;
  }
  const match = tab?.lines.find((line) => line.text.startsWith(`${label}: `));
  if (!match) {
    return "n/a";
  }
  return match.text.slice(label.length + 2).trim();
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

function branchLabel(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return `${lineValueFor(tabs, "repo", "Branch", repoPreview)}@${lineValueFor(tabs, "repo", "Head", repoPreview)}`;
}

function dirtyCountsLabel(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return `staged ${lineValueFor(tabs, "repo", "Staged", repoPreview)} | unstaged ${lineValueFor(tabs, "repo", "Unstaged", repoPreview)} | untracked ${lineValueFor(tabs, "repo", "Untracked", repoPreview)}`;
}

function repoHealthLabel(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return `${lineValueFor(tabs, "repo", "Repo risk", repoPreview)} | ${lineValueFor(tabs, "repo", "Sync", repoPreview)}`;
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

function buildRepoSnapshotLines(
  tabs: TabSpec[],
  repoPreview?: TabPreview,
  controlPreview?: TabPreview,
  now: Date = new Date(),
): string[] {
  const rows = [
    `Snapshot branch ${compact(branchLabel(tabs, repoPreview), 28)} | ${compact(lineValueFor(tabs, "repo", "Branch status", repoPreview), 24)}`,
    `Snapshot dirty ${compact(lineValueFor(tabs, "repo", "Dirty pressure", repoPreview), 24)} | ${compact(dirtyCountsLabel(tabs, repoPreview), 31)}`,
    `Snapshot topology ${compact(lineValueFor(tabs, "repo", "Topology status", repoPreview), 24)} | warnings ${compact(lineValueFor(tabs, "repo", "Topology warnings", repoPreview), 18)}`,
    `Snapshot warnings ${compact(lineValueFor(tabs, "repo", "Primary warning", repoPreview), 28)} | severity ${compact(lineValueFor(tabs, "repo", "Topology warning severity", repoPreview), 18)}`,
    `Snapshot alert ${compact(buildTopologyAlertValue(tabs, repoPreview), 56)}`,
    `Snapshot topology preview ${compact(buildTopologyPreviewValue(tabs, repoPreview), 56)}`,
    `Snapshot pressure ${compact(lineValueFor(tabs, "repo", "Topology pressure preview", repoPreview), 56)}`,
    `Snapshot hotspots ${compact(buildLeadHotspotPreviewLine(tabs, repoPreview), 52)}`,
    `Snapshot hotspot summary ${compact(lineValueFor(tabs, "repo", "Hotspot summary", repoPreview), 56)}`,
    `Snapshot summary ${compact(lineValueFor(tabs, "repo", "Repo risk", repoPreview), 28)} | ${compact(lineValueFor(tabs, "repo", "Hotspot summary", repoPreview), 40)}`,
  ];
  if (controlPreview || tabs.find((tab) => tab.id === "control")) {
    rows.push(`Snapshot repo/control ${compact(buildRepoControlCorrelationValue(tabs, repoPreview, controlPreview, now), 56)}`);
    rows.push(
      `Snapshot task ${compact(lineValueFor(tabs, "control", "Active task", controlPreview), 18)} | ${lineValueFor(tabs, "control", "Result status", controlPreview)}/${lineValueFor(tabs, "control", "Acceptance", controlPreview)} | ${compact(lineValueFor(tabs, "control", "Loop state", controlPreview), 18)} | ${compact(lineValueFor(tabs, "control", "Loop decision", controlPreview), 18)}`,
    );
  }
  const runtimeLine = buildRepoSnapshotRuntimeLine(tabs, controlPreview);
  if (runtimeLine) {
    rows.push(runtimeLine);
  }
  const freshnessLine = buildRepoSnapshotFreshnessLine(tabs, repoPreview, controlPreview, now);
  if (freshnessLine) {
    rows.push(freshnessLine);
  }
  return rows;
}

function buildRepoControlPulseLine(
  tabs: TabSpec[],
  controlPreview?: TabPreview,
  now: Date = new Date(),
): string | null {
  if (!controlPreview && !tabs.find((tab) => tab.id === "control")) {
    return null;
  }
  const updated = lineValueFor(tabs, "control", "Updated", controlPreview);
  const explicit = lineValueFor(tabs, "control", "Control pulse preview", controlPreview);
  if (explicit !== "n/a") {
    return labeledValue("Control pulse", compact(/^(fresh|stale|unknown)\b/.test(explicit) ? explicit : `${freshnessToken(updated, now)} | ${explicit}`, 88));
  }
  return labeledValue(
    "Control pulse",
    compact(
      [
        freshnessToken(updated, now),
        lineValueFor(tabs, "control", "Last result", controlPreview),
        lineValueFor(tabs, "control", "Loop state", controlPreview),
        lineValueFor(tabs, "control", "Loop decision", controlPreview),
      ].join(" | "),
      88,
    ),
  );
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
        lineValueFor(tabs, "control", "Verification bundle", controlPreview),
        `next ${lineValueFor(tabs, "control", "Next task", controlPreview)}`,
      ].join(" | "),
      88,
    ),
  );
}

function buildRepoFocusLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return `Focus ${compact(lineValueFor(tabs, "repo", "Repo root", repoPreview), 24)} | ${compact(lineValueFor(tabs, "repo", "Primary changed path", repoPreview), 24)}`;
}

function buildRepoTopologyPulseLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return `Topo pressure ${compact(lineValueFor(tabs, "repo", "Topology pressure", repoPreview), 48)}`;
}

function buildTopologyAlertValue(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return [
    lineValueFor(tabs, "repo", "Topology warning severity", repoPreview),
    `warning ${lineValueFor(tabs, "repo", "Primary warning", repoPreview)}`,
    `drift ${lineValueFor(tabs, "repo", "Primary peer drift", repoPreview)}`,
  ].join(" | ");
}

function buildTopologyPressurePreviewLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = lineValueFor(tabs, "repo", "Topology pressure preview", repoPreview);
  if (explicit !== "n/a") {
    return labeledValue("Pressure preview", compact(explicit, 88));
  }
  const warnings = lineValueFor(tabs, "repo", "Topology warnings", repoPreview);
  const leadPressure = lineValueFor(tabs, "repo", "Topology pressure", repoPreview).split(";")[0]?.trim() || "none";
  if (warnings === "n/a" && leadPressure === "none") {
    return labeledValue("Pressure preview", "n/a");
  }
  if (leadPressure === "none") {
    return labeledValue("Pressure preview", compact(warnings, 88));
  }
  return labeledValue("Pressure preview", compact(`${warnings} | ${leadPressure}`, 88));
}

function buildRiskPreviewLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = repoPreview?.["Risk preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return labeledValue("Risk preview", compact(explicit, 56));
  }
  const warning = lineValueFor(tabs, "repo", "Primary warning", repoPreview);
  const peer = lineValueFor(tabs, "repo", "Primary topology peer", repoPreview);
  if (warning === "n/a" && peer === "n/a") {
    return labeledValue("Risk preview", "n/a");
  }
  if (peer === "n/a" || peer === "none") {
    return labeledValue("Risk preview", compact(warning, 56));
  }
  return labeledValue("Risk preview", compact(`${warning} | ${peer}`, 56));
}

function buildTopologySignalLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  return labeledValue(
    "Topology signal",
    compact(
      `${lineValueFor(tabs, "repo", "Topology warning severity", repoPreview)} | ${lineValueFor(tabs, "repo", "Primary peer drift", repoPreview)}`,
      88,
    ),
  );
}

function buildRepoRiskPreviewLine(tabs: TabSpec[], repoPreview?: TabPreview): string {
  const explicit = repoPreview?.["Repo risk preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
    return labeledValue("Repo risk preview", compact(explicit, 88));
  }
  const branchStatus = lineValueFor(tabs, "repo", "Branch status", repoPreview);
  const riskPreview = lineValueFor(tabs, "repo", "Risk preview", repoPreview);
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
    labeledValue("Warnings", compact(lineValueFor(tabs, "repo", "Topology warnings", repoPreview), 88)),
    `${labeledValue("Severity", compact(lineValueFor(tabs, "repo", "Topology warning severity", repoPreview), 16))} | warning ${compact(lineValueFor(tabs, "repo", "Primary warning", repoPreview), 44)}`,
    labeledValue("Repo preview", compact(lineValueFor(tabs, "repo", "Repo risk preview", repoPreview), 88)),
    labeledValue("Risk preview", compact(lineValueFor(tabs, "repo", "Risk preview", repoPreview), 88)),
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
  const explicit = repoPreview?.["Repo/control preview"];
  if (typeof explicit === "string" && explicit.length > 0) {
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
  return [
    freshnessToken(updated, now),
    ...(activeTask !== "n/a" && activeTask !== "none" ? [`task ${activeTask}`] : []),
    lineValueFor(tabs, "repo", "Repo risk preview", repoPreview),
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

function buildRepoPreviewLines(
  tabs: TabSpec[],
  repoPreview?: TabPreview,
  controlPreview?: TabPreview,
  includeHotspotPressure = true,
  now: Date = new Date(),
): string[] {
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
  const repoRiskBlockLines = buildRepoRiskBlockLines(tabs, repoPreview);
  return [
    "Repo Preview",
    ...(repoPreview?.Authority ? [labeledValue("Authority", compact(repoPreview.Authority, 88))] : []),
    buildRepoOverviewLine(tabs, repoPreview),
    buildRepoPulseLine(tabs, repoPreview),
    ...buildRepoSnapshotLines(tabs, repoPreview, controlPreview, now),
    ...(includeHotspotPressure ? [] : buildHotspotFocusBlockLines(tabs, repoPreview, true)),
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
    labeledValue("Sync", compact(lineValueFor(tabs, "repo", "Sync", repoPreview))),
    labeledValue("Health", compact(repoHealthLabel(tabs, repoPreview))),
    ...trailingCorrelationLines,
    `${labeledValue("Dirty", compact(lineValueFor(tabs, "repo", "Dirty pressure", repoPreview), 24))} | ${compact(dirtyCountsLabel(tabs, repoPreview), 31)}`,
    ...(includeHotspotPressure ? buildHotspotFocusBlockLines(tabs, repoPreview, false).slice(1) : []),
  ];
}

function buildControlOverviewLine(tabs: TabSpec[], controlPreview?: TabPreview): string {
  return [
    `Task ${lineValueFor(tabs, "control", "Active task", controlPreview)}`,
    `${lineValueFor(tabs, "control", "Result status", controlPreview)}/${lineValueFor(tabs, "control", "Acceptance", controlPreview)}`,
    compact(lineValueFor(tabs, "control", "Verification bundle", controlPreview), 28),
  ].join(" | ");
}

function buildControlPulseLine(tabs: TabSpec[], controlPreview?: TabPreview, now: Date = new Date()): string {
  const updated = lineValueFor(tabs, "control", "Updated", controlPreview);
  const age = freshnessToken(updated, now);
  const explicit = lineValueFor(tabs, "control", "Control pulse preview", controlPreview);
  if (explicit !== "n/a") {
    return labeledValue("Pulse", compact(/^(fresh|stale|unknown)\b/.test(explicit) ? explicit : `${age} | ${explicit}`, 88));
  }
  return labeledValue(
    "Pulse",
    compact(
      [
        age,
        lineValueFor(tabs, "control", "Last result", controlPreview),
        lineValueFor(tabs, "control", "Runtime freshness", controlPreview),
      ].join(" | "),
      88,
    ),
  );
}

function controlHealthLabel(tabs: TabSpec[], controlPreview?: TabPreview): string {
  return `${lineValueFor(tabs, "control", "Verification bundle", controlPreview)} | alerts ${lineValueFor(tabs, "control", "Alerts", controlPreview)}`;
}

function buildControlFreshnessDetails(
  tabs: TabSpec[],
  controlPreview?: TabPreview,
  now: Date = new Date(),
): string {
  const updated = lineValueFor(tabs, "control", "Updated", controlPreview);
  return [
    freshnessToken(updated, now),
    lineValueFor(tabs, "control", "Loop state", controlPreview),
    `updated ${updated}`,
    `verify ${lineValueFor(tabs, "control", "Verification bundle", controlPreview)}`,
  ].join(" | ");
}

function buildControlSnapshotLines(tabs: TabSpec[], controlPreview?: TabPreview, now: Date = new Date()): string[] {
  return [
    `Snapshot task ${compact(lineValueFor(tabs, "control", "Active task", controlPreview), 18)} | ${lineValueFor(tabs, "control", "Result status", controlPreview)}/${lineValueFor(tabs, "control", "Acceptance", controlPreview)}`,
    `Snapshot runtime ${compact(lineValueFor(tabs, "control", "Runtime DB", controlPreview), 24)} | ${compact(lineValueFor(tabs, "control", "Runtime activity", controlPreview), 24)} | ${compact(lineValueFor(tabs, "control", "Artifact state", controlPreview), 24)}`,
    `Snapshot loop ${freshnessToken(lineValueFor(tabs, "control", "Updated", controlPreview), now)} | ${compact(lineValueFor(tabs, "control", "Loop state", controlPreview), 22)} | ${compact(lineValueFor(tabs, "control", "Loop decision", controlPreview), 18)}`,
    `Snapshot verify ${compact(lineValueFor(tabs, "control", "Verification bundle", controlPreview), 42)}`,
    `Snapshot truth ${compact(lineValueFor(tabs, "control", "Verification bundle", controlPreview), 24)} | ${compact(lineValueFor(tabs, "control", "Loop state", controlPreview), 22)} | next ${compact(lineValueFor(tabs, "control", "Next task", controlPreview), 24)}`,
  ];
}

function buildControlFreshnessLine(tabs: TabSpec[], controlPreview?: TabPreview, now: Date = new Date()): string {
  return `Freshness ${compact(buildControlFreshnessDetails(tabs, controlPreview, now), 88)}`;
}

function buildControlRuntimeSummaryLine(tabs: TabSpec[], controlPreview?: TabPreview): string {
  const explicit = lineValueFor(tabs, "control", "Runtime summary", controlPreview);
  if (explicit !== "n/a") {
    return `Runtime summary ${compact(explicit, 88)}`;
  }
  return `Runtime summary ${compact(lineValueFor(tabs, "control", "Runtime DB", controlPreview), 24)} | ${compact(lineValueFor(tabs, "control", "Session state", controlPreview), 24)} | ${compact(lineValueFor(tabs, "control", "Run state", controlPreview), 22)} | ${compact(lineValueFor(tabs, "control", "Context state", controlPreview), 24)}`;
}

function buildControlPreviewLines(
  tabs: TabSpec[],
  controlPreview?: TabPreview,
  includeExtendedRows = false,
  now: Date = new Date(),
): string[] {
  const lines = [
    "Control Preview",
    ...(controlPreview?.Authority ? [labeledValue("Authority", compact(controlPreview.Authority, 88))] : []),
    buildControlOverviewLine(tabs, controlPreview),
    buildControlPulseLine(tabs, controlPreview, now),
    ...buildControlSnapshotLines(tabs, controlPreview, now),
    buildControlFreshnessLine(tabs, controlPreview, now),
    buildControlRuntimeSummaryLine(tabs, controlPreview),
    `${labeledValue("Task", lineValueFor(tabs, "control", "Active task", controlPreview))} | ${lineValueFor(tabs, "control", "Task progress", controlPreview)}`,
    `${labeledValue("Outcome", lineValueFor(tabs, "control", "Result status", controlPreview))} | accept ${lineValueFor(tabs, "control", "Acceptance", controlPreview)}`,
    labeledValue("Runtime", compact(lineValueFor(tabs, "control", "Runtime DB", controlPreview))),
    labeledValue("Sessions", compact(lineValueFor(tabs, "control", "Session state", controlPreview))),
    labeledValue("Runs", compact(lineValueFor(tabs, "control", "Run state", controlPreview))),
    labeledValue("Context", compact(lineValueFor(tabs, "control", "Context state", controlPreview))),
    `${labeledValue("Loop", compact(lineValueFor(tabs, "control", "Loop state", controlPreview), 22))} | ${compact(lineValueFor(tabs, "control", "Loop decision", controlPreview), 18)}`,
    labeledValue("Health", compact(controlHealthLabel(tabs, controlPreview))),
    labeledValue("Updated", lineValueFor(tabs, "control", "Updated", controlPreview)),
    labeledValue("Next", compact(lineValueFor(tabs, "control", "Next task", controlPreview))),
    labeledValue("Result", compact(lineValueFor(tabs, "control", "Last result", controlPreview))),
    labeledValue("Verify", compact(lineValueFor(tabs, "control", "Verification summary", controlPreview))),
    labeledValue("Checks", compact(lineValueFor(tabs, "control", "Verification checks", controlPreview))),
    labeledValue("Bundle", compact(lineValueFor(tabs, "control", "Verification bundle", controlPreview))),
    labeledValue("State", compact(lineValueFor(tabs, "control", "Durable state", controlPreview))),
    `${labeledValue("Tools", compact(lineValueFor(tabs, "control", "Toolchain", controlPreview), 24))} | alerts ${compact(lineValueFor(tabs, "control", "Alerts", controlPreview), 18)}`,
  ];

  if (includeExtendedRows) {
    lines.splice(
      11,
      0,
      `${labeledValue("Activity", compact(lineValueFor(tabs, "control", "Runtime activity", controlPreview), 24))} | ${compact(lineValueFor(tabs, "control", "Artifact state", controlPreview), 24)}`,
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
  const hotspotSummary = lineValueFor(tabs, "repo", "Hotspot summary", repoPreview);
  const lines = [
    "Repo Preview",
    ...(repoPreview?.Authority ? [labeledValue("Authority", compact(repoPreview.Authority, 88))] : []),
    buildRepoOverviewLine(tabs, repoPreview),
    buildRepoPulseLine(tabs, repoPreview),
    `Snapshot branch ${compact(branchLabel(tabs, repoPreview), 28)} | ${compact(lineValueFor(tabs, "repo", "Branch status", repoPreview), 24)}`,
    `Snapshot dirty ${compact(lineValueFor(tabs, "repo", "Dirty pressure", repoPreview), 24)} | ${compact(dirtyCountsLabel(tabs, repoPreview), 31)}`,
    `Snapshot topology ${compact(lineValueFor(tabs, "repo", "Topology status", repoPreview), 24)} | warnings ${compact(lineValueFor(tabs, "repo", "Topology warnings", repoPreview), 18)}`,
    `Snapshot warnings ${compact(lineValueFor(tabs, "repo", "Primary warning", repoPreview), 28)} | severity ${compact(lineValueFor(tabs, "repo", "Topology warning severity", repoPreview), 18)}`,
    `Snapshot alert ${compact(buildTopologyAlertValue(tabs, repoPreview), 56)}`,
    `Snapshot topology preview ${compact(buildTopologyPreviewValue(tabs, repoPreview), 56)}`,
    `Snapshot pressure ${compact(lineValueFor(tabs, "repo", "Topology pressure preview", repoPreview), 56)}`,
    `Snapshot hotspots ${compact(buildLeadHotspotPreviewLine(tabs, repoPreview), 52)}`,
    `Snapshot hotspot summary ${compact(hotspotSummary !== "n/a" ? hotspotSummary : buildLeadHotspotPreviewLine(tabs, repoPreview), 56)}`,
    `Snapshot summary ${compact(lineValueFor(tabs, "repo", "Repo risk", repoPreview), 28)} | ${compact(hotspotSummary !== "n/a" ? hotspotSummary : buildLeadHotspotPreviewLine(tabs, repoPreview), 40)}`,
    buildRepoRiskPreviewLine(tabs, repoPreview),
    buildRepoControlCorrelationLine(tabs, repoPreview, controlPreview, now),
  ];

  const controlPulseLine = buildRepoControlPulseLine(tabs, controlPreview, now);
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
  const snapshotFreshnessLine = buildRepoSnapshotFreshnessLine(tabs, repoPreview, controlPreview, now);
  if (snapshotFreshnessLine) {
    lines.push(snapshotFreshnessLine);
  }
  const controlTaskLine = buildRepoControlTaskLine(tabs, controlPreview);
  if (controlTaskLine) {
    lines.push(controlTaskLine);
  }
  const controlVerificationLine = buildRepoControlVerificationLine(tabs, controlPreview);
  if (controlVerificationLine) {
    lines.push(controlVerificationLine);
  }

  return [
    ...lines,
    "Hotspot Focus",
    labeledValue("Changed", compact(lineValueFor(tabs, "repo", "Changed hotspots", repoPreview))),
    labeledValue("Summary", compact(buildLeadHotspotPreviewLine(tabs, repoPreview))),
    `${labeledValue("Lead change", compact(lineValueFor(tabs, "repo", "Primary changed hotspot", repoPreview), 20))} | ${compact(lineValueFor(tabs, "repo", "Primary changed path", repoPreview), 28)}`,
    labeledValue("Lead file", compact(lineValueFor(tabs, "repo", "Primary file hotspot", repoPreview))),
    labeledValue("Lead dep", compact(lineValueFor(tabs, "repo", "Primary dependency hotspot", repoPreview))),
    "Repo Risk",
    labeledValue("Risk", compact(lineValueFor(tabs, "repo", "Repo risk", repoPreview), 88)),
    labeledValue("Warnings", compact(lineValueFor(tabs, "repo", "Topology warnings", repoPreview), 88)),
    `${labeledValue("Severity", compact(lineValueFor(tabs, "repo", "Topology warning severity", repoPreview), 16))} | warning ${compact(lineValueFor(tabs, "repo", "Primary warning", repoPreview), 44)}`,
    buildTopologySignalLine(tabs, repoPreview),
    labeledValue("Lead peer", compact(lineValueFor(tabs, "repo", "Primary topology peer", repoPreview), 88)),
    labeledValue("Pressure", compact(lineValueFor(tabs, "repo", "Topology pressure", repoPreview), 88)),
  ];
}

function buildVisibleControlPreviewLines(
  tabs: TabSpec[],
  controlPreview?: TabPreview,
  now: Date = new Date(),
): string[] {
  return [
    "Control Preview",
    ...(controlPreview?.Authority ? [labeledValue("Authority", compact(controlPreview.Authority, 88))] : []),
    buildControlOverviewLine(tabs, controlPreview),
    buildControlPulseLine(tabs, controlPreview, now),
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
  return [
    "Active",
    `${activeTabTitle} | bridge ${bridgeStatus}`,
    `Model ${provider} ${model}`,
    ...buildRepoPreviewLines(tabs, repoPreview, controlPreview, true, now),
    labeledValue("Inventory", compact(lineValueFor(tabs, "repo", "Inventory", repoPreview))),
    labeledValue("Mix", compact(lineValueFor(tabs, "repo", "Language mix", repoPreview))),
    "Ontology",
    `Ver ${lineValueFor(tabs, "ontology", "Version")} | concepts ${lineValueFor(tabs, "ontology", "Concept count")}`,
    ...buildControlPreviewLines(tabs, controlPreview, true, now),
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
  return [
    "Active",
    `${activeTabTitle} | bridge ${bridgeStatus}`,
    `Model ${provider} ${model}`,
    ...buildVisibleRepoPreviewLines(tabs, repoPreview, controlPreview, now),
    ...buildVisibleControlPreviewLines(tabs, controlPreview, now),
    "Ontology",
    `Ver ${lineValueFor(tabs, "ontology", "Version")} | concepts ${lineValueFor(tabs, "ontology", "Concept count")}`,
  ];
}

export function Sidebar({mode, outline, activeTabTitle, provider, model, bridgeStatus, tabs, repoPreview, controlPreview}: Props): React.ReactElement {
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
    <Box width={34} flexDirection="column" borderStyle="single" borderColor="gray" paddingX={1} marginRight={1}>
      <Text color="cyan">{mode === "toc" ? "TOC" : mode === "context" ? "Context" : "Help"}</Text>
      <Text color="gray"> </Text>
      {mode === "toc" &&
        outline.slice(0, 16).map((item) => (
          <Text key={item.id} color={item.depth === 1 ? "white" : "gray"}>
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
              color={["Active", "Repo Preview", "Hotspot Focus", "Repo Risk", "Ontology", "Control Preview", "Models", "Agents", "Evolution"].includes(line) ? "white" : "gray"}
            >
              {line}
            </Text>
          ))}
        </>
      )}
      {mode === "help" && (
        <>
          <Text color="white">Controls</Text>
          <Text color="gray">Enter submit</Text>
          <Text color="gray">Ctrl+B sidebar</Text>
          <Text color="gray">[ ] cycle tabs</Text>
          <Text color="gray">1 2 3 switch sidebar</Text>
          <Text color="gray">Ctrl+G/R/O/M/A/P/E/T/Y panes</Text>
          <Text color="gray">Ctrl+L refresh pane</Text>
          <Text color="gray">Ctrl+X/F/V pane actions</Text>
          <Text color="gray">Ctrl+W close tab</Text>
        </>
      )}
    </Box>
  );
}
