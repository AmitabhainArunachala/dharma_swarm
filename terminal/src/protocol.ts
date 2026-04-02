import {freshnessToken} from "./freshness.js";
import type {
  ApprovalEntryStatus,
  PermissionHistoryPayload,
  ApprovalQueueState,
  CanonicalPermissionDecision,
  CanonicalPermissionOutcome,
  CanonicalPermissionResolution,
  CanonicalEventEnvelope,
  CanonicalRoutingDecision,
  CanonicalRuntimeSnapshot,
  CanonicalSession,
  AgentRoutesPayload,
  OutlineItem,
  RoutingDecisionPayload,
  RuntimeSnapshotPayload,
  SessionCatalogEntry,
  SessionCatalogPayload,
  SessionCompactionPreview,
  SessionDetailPayload,
  SessionPaneState,
  SupervisorControlState,
  TabPreview,
  TabSpec,
  TranscriptLine,
  WorkspaceSnapshotPayload,
} from "./types.js";
import {buildVerificationSummaryRows, parseVerificationBundle, verificationBundleLabel} from "./verification.js";

const RUNTIME_SUPERVISOR_AUTHORITATIVE_FIELDS = new Set([
  "Loop state",
  "Task progress",
  "Active task",
  "Result status",
  "Acceptance",
  "Last result",
  "Loop decision",
  "Next task",
  "Updated",
  "Durable state",
]);

function makeLine(kind: TranscriptLine["kind"], text: string): TranscriptLine {
  return {
    id: `${kind}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    kind,
    text,
  };
}

function toLines(kind: TranscriptLine["kind"], text: string): TranscriptLine[] {
  return text
    .split("\n")
    .map((line) => line.trimEnd())
    .filter((line, index, lines) => line.length > 0 || (index > 0 && index < lines.length - 1))
    .map((line) => makeLine(kind, line));
}

function findLine(content: string, pattern: RegExp): string {
  const match = content.match(pattern);
  return match?.[1]?.trim() ?? "";
}

function collectSectionLines(content: string, heading: string): string[] {
  const lines = content.split("\n");
  const start = lines.findIndex((line) => line.trim() === heading);
  if (start === -1) {
    return [];
  }
  const section: string[] = [];
  for (let index = start + 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (line.startsWith("## ")) {
      break;
    }
    if (line.trim().length > 0) {
      section.push(line);
    }
  }
  return section;
}

function trimBullet(line: string): string {
  return line.replace(/^\s*-\s*/, "").trim();
}

function firstSemicolonSegment(value: string): string {
  if (!value || value === "none") {
    return "none";
  }
  return value
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.length > 0) ?? value;
}

function basename(value: string): string {
  const parts = value.split("/");
  return parts[parts.length - 1] || value;
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter((item) => item.length > 0) : [];
}

function asNumberRecord(value: unknown): Record<string, number> {
  if (typeof value !== "object" || value === null) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value).map(([key, entry]) => [key, typeof entry === "number" ? entry : Number(entry ?? 0)]),
  );
}

function parseGitLine(content: string): {
  branch: string;
  head: string;
  counts: {
    staged: number | null;
    unstaged: number | null;
    untracked: number | null;
  };
  dirty: string;
} {
  const git = findLine(content, /^Git:\s*(.+)$/m);
  const match = git.match(
    /^(?<branch>.+?)@\S+\s+\|\s+staged\s+(?<staged>\d+)\s+\|\s+unstaged\s+(?<unstaged>\d+)\s+\|\s+untracked\s+(?<untracked>\d+)$/,
  );
  if (!match?.groups) {
    return {
      branch: git || "unavailable",
      head: "unavailable",
      counts: {
        staged: null,
        unstaged: null,
        untracked: null,
      },
      dirty: "unavailable",
    };
  }
  const branchWithHead = git.split(" | ")[0]?.trim() || "unavailable";
  const [branch = "unavailable", head = "unavailable"] = branchWithHead.split("@");
  return {
    branch,
    head,
    counts: {
      staged: Number.parseInt(match.groups.staged, 10),
      unstaged: Number.parseInt(match.groups.unstaged, 10),
      untracked: Number.parseInt(match.groups.untracked, 10),
    },
    dirty: `staged ${match.groups.staged} | unstaged ${match.groups.unstaged} | untracked ${match.groups.untracked}`,
  };
}

function parseGitSyncLine(content: string): string {
  const sync = findLine(content, /^Git sync:\s*(.+)$/m);
  return sync || "unavailable";
}

function parseGitSyncSummary(content: string): {
  sync: string;
  upstream: string;
  ahead: string;
  behind: string;
} {
  const sync = parseGitSyncLine(content);
  const match = sync.match(/^(?<upstream>.+?)\s+\|\s+ahead\s+(?<ahead>\d+)\s+\|\s+behind\s+(?<behind>\d+)$/);
  if (!match?.groups) {
    return {
      sync,
      upstream: sync,
      ahead: "n/a",
      behind: "n/a",
    };
  }
  return {
    sync,
    upstream: match.groups.upstream.trim(),
    ahead: match.groups.ahead,
    behind: match.groups.behind,
  };
}

function summarizeBranchStatus(sync: ReturnType<typeof parseGitSyncSummary>): string {
  if (sync.ahead === "n/a" || sync.behind === "n/a") {
    return sync.sync;
  }
  const ahead = Number.parseInt(sync.ahead, 10);
  const behind = Number.parseInt(sync.behind, 10);
  if (ahead > 0 && behind > 0) {
    return `diverged from ${sync.upstream} (+${ahead}/-${behind})`;
  }
  if (ahead > 0) {
    return `ahead of ${sync.upstream} by ${ahead}`;
  }
  if (behind > 0) {
    return `behind ${sync.upstream} by ${behind}`;
  }
  return `tracking ${sync.upstream} in sync`;
}

function summarizeBranchSyncPreview(
  sync: ReturnType<typeof parseGitSyncSummary>,
  branchStatus: string,
  repoRisk: string,
): string {
  const drift =
    sync.ahead === "n/a" || sync.behind === "n/a" ? "+n/a/-n/a" : `+${sync.ahead}/-${sync.behind}`;
  return `${branchStatus} | ${drift} | ${repoRisk}`;
}

function totalDirtyCount(git: ReturnType<typeof parseGitLine>): number | null {
  const {staged, unstaged, untracked} = git.counts;
  if (staged === null || unstaged === null || untracked === null) {
    return null;
  }
  return staged + unstaged + untracked;
}

function summarizeDirtyPressure(git: ReturnType<typeof parseGitLine>): string {
  const total = totalDirtyCount(git);
  if (total === null) {
    return "unknown";
  }
  if (total === 0) {
    return "clean";
  }
  if (total >= 250) {
    return `high (${total} local changes)`;
  }
  if (total >= 50) {
    return `elevated (${total} local changes)`;
  }
  return `contained (${total} local changes)`;
}

function summarizeRepoRisk(
  git: ReturnType<typeof parseGitLine>,
  sync: ReturnType<typeof parseGitSyncSummary>,
  topology: ReturnType<typeof summarizeTopology>,
): string {
  const signals: string[] = [];
  if (topology.warnings.length > 0) {
    signals.push(`topology ${topology.warnings[0]}`);
  }
  if (sync.behind !== "n/a" && Number.parseInt(sync.behind, 10) > 0) {
    signals.push(`behind upstream by ${sync.behind}`);
  }
  if (sync.ahead !== "n/a" && Number.parseInt(sync.ahead, 10) > 0) {
    signals.push(`ahead of upstream by ${sync.ahead}`);
  }
  const dirtyPressure = summarizeDirtyPressure(git);
  if (dirtyPressure !== "clean" && dirtyPressure !== "unknown") {
    signals.push(dirtyPressure);
  }
  return signals.length > 0 ? signals.join("; ") : "stable";
}

function parseGitHotspotsLine(content: string): string {
  const hotspots = findLine(content, /^Git hotspots:\s*(.+)$/m);
  return hotspots || "none";
}

function parseGitChangedPathsLine(content: string): string {
  const changedPaths = findLine(content, /^Git changed paths:\s*(.+)$/m);
  return changedPaths || "none";
}

type TopologyPeer = {
  name: string;
  role: string;
  branch: string;
  dirty: string;
  modified: number | null;
  untracked: number | null;
};

function classifyTopologyWarningSeverity(warnings: string[]): string {
  const leadWarning = warnings[0]?.toLowerCase() ?? "";
  if (!leadWarning) {
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

function summarizePeerDriftMarker(peer: TopologyPeer, warnings: string[]): string {
  const branch = peer.branch || "n/a";
  if (branch === "n/a") {
    return `${peer.name} n/a`;
  }
  if (/detached/i.test(branch)) {
    return `${peer.name} detached`;
  }
  if (branch.includes("...")) {
    const hasBranchDrift = warnings.some((warning) => warning.toLowerCase().includes("peer_branch_diverged"));
    return `${peer.name} ${hasBranchDrift ? "drift" : "track"} ${branch}`;
  }
  return `${peer.name} branch ${branch}`;
}

function summarizePeerPressure(peers: TopologyPeer[]): string {
  if (peers.length === 0) {
    return "none";
  }

  return peers
    .slice()
    .sort((left, right) => {
      const leftTotal = (left.modified ?? 0) + (left.untracked ?? 0);
      const rightTotal = (right.modified ?? 0) + (right.untracked ?? 0);
      return rightTotal - leftTotal;
    })
    .slice(0, 3)
    .map((peer) => {
      const total = (peer.modified ?? 0) + (peer.untracked ?? 0);
      if (total === 0) {
        return `${peer.name} clean`;
      }
      const modified = peer.modified ?? 0;
      const untracked = peer.untracked ?? 0;
      return `${peer.name} Δ${total} (${modified} modified, ${untracked} untracked)`;
    })
    .join("; ");
}

function summarizeTopologyFromPeers(
  warnings: string[],
  peerRecords: TopologyPeer[],
): {
  warnings: string[];
  peers: string[];
  pressure: string;
  peerCount: number;
  primaryPeer: string;
  warningSeverity: string;
  peerDriftMarkers: string;
  primaryPeerDrift: string;
} {
  const peers = peerRecords.slice(0, 3).map((peer) => `${peer.name} (${peer.role}, ${peer.branch}, dirty ${peer.dirty})`);
  const peerDriftMarkers = peerRecords
    .slice(0, 3)
    .map((peer) => summarizePeerDriftMarker(peer, warnings))
    .join("; ");
  return {
    warnings,
    peers,
    pressure: summarizePeerPressure(peerRecords),
    peerCount: peerRecords.length,
    primaryPeer: peers[0] ?? "none",
    warningSeverity: classifyTopologyWarningSeverity(warnings),
    peerDriftMarkers: peerDriftMarkers || "none",
    primaryPeerDrift: peerDriftMarkers.split(";")[0]?.trim() || "none",
  };
}

function summarizeTopology(content: string): {
  warnings: string[];
  peers: string[];
  pressure: string;
  peerCount: number;
  primaryPeer: string;
  warningSeverity: string;
  peerDriftMarkers: string;
  primaryPeerDrift: string;
} {
  const topologyLines = collectSectionLines(content, "## Topology");
  const warnings = topologyLines
    .filter((line) => line.trim().startsWith("- warning:"))
    .map((line) => line.replace(/^\s*-\s*warning:\s*/i, "").trim());
  const peerRecords = topologyLines
    .filter((line) => line.trim().startsWith("- ") && !line.includes("warning:"))
    .map((line) => trimBullet(line))
    .map((line) => {
      const [
        name = "repo",
        rolePart = "role unknown",
        branchPart = "branch n/a",
        dirtyPart = "dirty n/a",
        modifiedPart = "modified n/a",
        untrackedPart = "untracked n/a",
      ] = line.split(" | ").map((part) => part.trim());
      const modified = modifiedPart.replace(/^modified\s+/i, "");
      const untracked = untrackedPart.replace(/^untracked\s+/i, "");
      return {
        name,
        role: rolePart.replace(/^role\s+/i, ""),
        branch: branchPart.replace(/^branch\s+/i, ""),
        dirty: dirtyPart.replace(/^dirty\s+/i, ""),
        modified: /^\d+$/.test(modified) ? Number.parseInt(modified, 10) : null,
        untracked: /^\d+$/.test(untracked) ? Number.parseInt(untracked, 10) : null,
      };
    });
  return summarizeTopologyFromPeers(warnings, peerRecords);
}

function summarizeTopologyStatus(topology: ReturnType<typeof summarizeTopology>): string {
  const peerLabel = `${topology.peerCount} peer${topology.peerCount === 1 ? "" : "s"}`;
  if (topology.warnings.length > 0) {
    return `degraded (${topology.warnings.length} warning${topology.warnings.length === 1 ? "" : "s"}, ${peerLabel})`;
  }
  if (topology.peerCount > 0) {
    return `connected (${peerLabel})`;
  }
  return "isolated";
}

function summarizeHotspots(content: string): string[] {
  return collectSectionLines(content, "## Largest Python files")
    .filter((line) => line.trim().startsWith("- "))
    .slice(0, 3)
    .map((line) => trimBullet(line))
    .map((line) => {
      const [file = "unknown", lines = "n/a"] = line.split(" | ").map((part) => part.trim());
      return `${basename(file)} (${lines})`;
    });
}

function summarizeHotspotPreview(
  changedHotspots: string,
  fileHotspots: string,
  inboundHotspots: string,
  changedPaths: string,
): string {
  const parts: string[] = [];
  if (changedHotspots !== "none") {
    parts.push(`change ${changedHotspots}`);
  }
  if (fileHotspots !== "none") {
    parts.push(`files ${fileHotspots}`);
  }
  if (inboundHotspots !== "none") {
    parts.push(`deps ${inboundHotspots}`);
  }
  if (changedPaths !== "none") {
    const [firstPath = changedPaths] = changedPaths.split(";").map((part) => part.trim());
    parts.push(`paths ${firstPath}`);
  }
  return parts.join(" | ") || "none";
}

function summarizeLeadHotspotPreview(
  primaryChangedHotspot: string,
  primaryChangedPath: string,
  primaryDependencyHotspot: string,
): string {
  const parts: string[] = [];
  if (primaryChangedHotspot !== "none") {
    parts.push(`change ${primaryChangedHotspot}`);
  }
  if (primaryChangedPath !== "none") {
    parts.push(`path ${primaryChangedPath}`);
  }
  if (primaryDependencyHotspot !== "none") {
    parts.push(`dep ${primaryDependencyHotspot}`);
  }
  return parts.join(" | ") || "none";
}

function summarizeHotspotPressurePreview(
  primaryChangedHotspot: string,
  primaryDependencyHotspot: string,
): string {
  const parts: string[] = [];
  if (primaryChangedHotspot !== "none") {
    parts.push(`change ${primaryChangedHotspot}`);
  }
  if (primaryDependencyHotspot !== "none") {
    parts.push(`dep ${primaryDependencyHotspot}`);
  }
  return parts.join(" | ") || "none";
}

function previewField(preview: TabPreview, key: string): string {
  const value = preview[key];
  return typeof value === "string" && value.length > 0 ? value : "none";
}

function leadHotspotPreviewFromPreview(preview: TabPreview): string {
  return summarizeLeadHotspotPreview(
    previewField(preview, "Primary changed hotspot"),
    previewField(preview, "Primary changed path"),
    previewField(preview, "Primary dependency hotspot"),
  );
}

function summarizeRiskPreview(topology: ReturnType<typeof summarizeTopology>): string {
  const leadRisk = topology.warnings[0] ?? "stable";
  const leadPeer = topology.primaryPeer;
  if (leadRisk === "stable" && leadPeer === "none") {
    return "stable";
  }
  if (leadPeer === "none") {
    return leadRisk;
  }
  return `${leadRisk} | ${leadPeer}`;
}

function summarizeRepoRiskPreview(branchStatus: string, riskPreview: string): string {
  const normalizedBranch = branchStatus.trim() || "unknown";
  const normalizedRisk = riskPreview.trim() || "stable";
  if (normalizedRisk === "stable") {
    return normalizedBranch;
  }
  return `${normalizedBranch} | ${normalizedRisk}`;
}

function summarizeTopologyPreview(
  warning: string,
  peer: string,
  pressure: string,
): string {
  const parts: string[] = [];
  if (warning && warning !== "none" && warning !== "n/a") {
    parts.push(warning);
  } else {
    parts.push("stable");
  }
  if (peer && peer !== "none" && peer !== "n/a") {
    parts.push(peer);
  }
  if (pressure && pressure !== "none" && pressure !== "n/a") {
    parts.push(pressure);
  }
  return parts.join(" | ");
}

function summarizeTopologyPressurePreview(topology: ReturnType<typeof summarizeTopology>): string {
  const warningCount = topology.warnings.length;
  const warningLabel = warningCount === 0 ? "stable" : `${warningCount} warning${warningCount === 1 ? "" : "s"}`;
  const leadPressure = firstSemicolonSegment(topology.pressure);
  if (leadPressure === "none") {
    return warningLabel;
  }
  return `${warningLabel} | ${leadPressure}`;
}

function buildWorkspaceSnapshotPreludeFromPreview(preview: TabPreview): string[] {
  return [
    "# Repo Snapshot",
    "## Git status",
    `Repo root: ${preview["Repo root"]}`,
    `Branch: ${preview.Branch}`,
    `Head: ${preview.Head}`,
    `Sync: ${preview.Sync}`,
    `Branch status: ${preview["Branch status"]}`,
    `Upstream: ${preview.Upstream}`,
    `Ahead: ${preview.Ahead}`,
    `Behind: ${preview.Behind}`,
    `Branch sync preview: ${preview["Branch sync preview"]}`,
    `Repo risk preview: ${preview["Repo risk preview"]}`,
    `Repo risk: ${preview["Repo risk"]}`,
    `Dirty: ${preview.Dirty}`,
    `Dirty pressure: ${preview["Dirty pressure"]}`,
    `Staged: ${preview.Staged}`,
    `Unstaged: ${preview.Unstaged}`,
    `Untracked: ${preview.Untracked}`,
    "## Topology risk",
    `Topology warnings: ${preview["Topology warnings"]}`,
    `Topology warning severity: ${preview["Topology warning severity"]}`,
    `Topology risk: ${preview["Topology risk"]}`,
    `Risk preview: ${preview["Risk preview"]}`,
    `Topology preview: ${preview["Topology preview"]}`,
    `Topology pressure preview: ${preview["Topology pressure preview"]}`,
    `Topology status: ${preview["Topology status"]}`,
    `Primary warning: ${preview["Primary warning"]}`,
    `Primary peer drift: ${preview["Primary peer drift"]}`,
    `Primary topology peer: ${preview["Primary topology peer"]}`,
    `Peer drift markers: ${preview["Peer drift markers"]}`,
    `Topology peers: ${preview["Topology peers"]}`,
    `Topology pressure: ${preview["Topology pressure"]}`,
    "## Hotspots",
    `Changed hotspots: ${preview["Changed hotspots"]}`,
    `Changed paths: ${preview["Changed paths"]}`,
    `Hotspot summary: ${preview["Hotspot summary"]}`,
    `Lead hotspot preview: ${previewField(preview, "Lead hotspot preview") !== "none" ? previewField(preview, "Lead hotspot preview") : leadHotspotPreviewFromPreview(preview)}`,
    `Hotspot pressure preview: ${preview["Hotspot pressure preview"]}`,
    `Primary changed hotspot: ${preview["Primary changed hotspot"]}`,
    `Primary changed path: ${preview["Primary changed path"]}`,
    `Primary file hotspot: ${preview["Primary file hotspot"]}`,
    `Primary dependency hotspot: ${preview["Primary dependency hotspot"]}`,
    `File hotspots: ${preview.Hotspots}`,
    `Dependency hotspots: ${preview["Inbound hotspots"]}`,
    "## Inventory",
    `Inventory: ${preview.Inventory}`,
    `Language mix: ${preview["Language mix"]}`,
  ];
}

function buildWorkspaceSnapshotPrelude(content: string): string[] {
  return buildWorkspaceSnapshotPreludeFromPreview(workspaceSnapshotToPreview(content));
}

export function isWorkspaceSnapshotContent(output: string): boolean {
  return /^Repo root:\s*.+$/m.test(output) && /^Git:\s*.+$/m.test(output);
}

function extractRepoRoot(content: string): string {
  return findLine(content, /^Repo root:\s*(.+)$/m) || "unavailable";
}

function extractWorkspaceMetric(content: string, prefix: string): string {
  return findLine(content, new RegExp(`^${prefix}:\\s*(.+)$`, "m")) || "n/a";
}

function summarizeLanguageMix(content: string): string {
  return collectSectionLines(content, "## Language mix")
    .filter((line) => line.trim().startsWith("- "))
    .slice(0, 4)
    .map((line) => trimBullet(line))
    .join("; ") || "none";
}

function summarizeImportedModules(content: string): string {
  return collectSectionLines(content, "## Most imported local modules")
    .filter((line) => line.trim().startsWith("- "))
    .slice(0, 3)
    .map((line) => trimBullet(line))
    .join("; ") || "none";
}

function summarizeImportedModulesFromPayload(modules: WorkspaceSnapshotPayload["most_imported_modules"]): string {
  return modules
    .slice(0, 3)
    .map((item) => `${item.module} | inbound ${item.count}`)
    .join("; ") || "none";
}

function summarizeHotspotsFromPayload(files: WorkspaceSnapshotPayload["largest_python_files"]): string[] {
  return files.slice(0, 3).map((item) => `${basename(item.path)} (${item.lines} lines)`);
}

function workspaceTopologySummaryFromPayload(payload: WorkspaceSnapshotPayload): ReturnType<typeof summarizeTopology> {
  const peerRecords: TopologyPeer[] = payload.topology.repos
    .filter((repo) => repo.exists)
    .slice(0, 4)
    .map((repo) => ({
      name: repo.name,
      role: repo.role,
      branch: String(repo.branch ?? "n/a"),
      dirty: repo.dirty === null || repo.dirty === undefined ? "None" : String(repo.dirty),
      modified: typeof repo.modified_count === "number" ? repo.modified_count : null,
      untracked: typeof repo.untracked_count === "number" ? repo.untracked_count : null,
    }));
  return summarizeTopologyFromPeers(payload.topology.warnings, peerRecords);
}

function inventoryFieldLabel(value: number | null | undefined, suffix: string): string {
  return value === null || value === undefined ? `n/a ${suffix}` : `${value} ${suffix}`;
}

export function workspaceSnapshotPayloadFromEvent(event: Record<string, unknown>): WorkspaceSnapshotPayload | undefined {
  const payload = asRecord(event.payload);
  if (stringField(payload, "domain") !== "workspace_snapshot" || stringField(payload, "version") !== "v1") {
    return undefined;
  }
  const git = asRecord(payload.git);
  const sync = asRecord(git.sync);
  const topology = asRecord(payload.topology);
  const inventory = asRecord(payload.inventory);
  const changedHotspots = Array.isArray(git.changed_hotspots)
    ? git.changed_hotspots
        .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
        .map((item) => ({name: stringField(item, "name"), count: numberField(item, "count") ?? 0}))
        .filter((item) => item.name.length > 0)
    : [];
  const topologyRepos = Array.isArray(topology.repos)
    ? topology.repos
        .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
        .map((item) => ({
          domain: stringField(item, "domain"),
          name: stringField(item, "name"),
          role: stringField(item, "role", "unknown"),
          canonical: boolField(item, "canonical"),
          path: stringField(item, "path"),
          exists: boolField(item, "exists"),
          is_git: boolField(item, "is_git"),
          branch: stringField(item, "branch") || undefined,
          head: stringField(item, "head") || undefined,
          dirty:
            typeof item.dirty === "boolean"
              ? item.dirty
              : item.dirty === null || item.dirty === undefined
                ? null
                : String(item.dirty).toLowerCase() === "true",
          modified_count: numberField(item, "modified_count") ?? 0,
          untracked_count: numberField(item, "untracked_count") ?? 0,
        }))
        .filter((item) => item.name.length > 0)
    : [];
  return {
    version: "v1",
    domain: "workspace_snapshot",
    repo_root: stringField(payload, "repo_root", "unavailable"),
    git: {
      branch: stringField(git, "branch", "unavailable"),
      head: stringField(git, "head", "unavailable"),
      staged: numberField(git, "staged"),
      unstaged: numberField(git, "unstaged"),
      untracked: numberField(git, "untracked"),
      changed_hotspots: changedHotspots,
      changed_paths: asStringArray(git.changed_paths),
      sync: {
        summary: stringField(sync, "summary", "unavailable"),
        status: stringField(sync, "status", "unavailable"),
        upstream: stringField(sync, "upstream") || undefined,
        ahead: numberField(sync, "ahead"),
        behind: numberField(sync, "behind"),
      },
    },
    topology: {
      warnings: asStringArray(topology.warnings),
      repos: topologyRepos,
    },
    inventory: {
      python_modules: numberField(inventory, "python_modules"),
      python_tests: numberField(inventory, "python_tests"),
      scripts: numberField(inventory, "scripts"),
      docs: numberField(inventory, "docs"),
      workflows: numberField(inventory, "workflows"),
    },
    language_mix: Array.isArray(payload.language_mix)
      ? payload.language_mix
          .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
          .map((item) => ({suffix: stringField(item, "suffix"), count: numberField(item, "count") ?? 0}))
          .filter((item) => item.suffix.length > 0)
      : [],
    largest_python_files: Array.isArray(payload.largest_python_files)
      ? payload.largest_python_files
          .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
          .map((item) => ({
            path: stringField(item, "path"),
            lines: numberField(item, "lines") ?? 0,
            defs: numberField(item, "defs") ?? 0,
            classes: numberField(item, "classes") ?? 0,
            imports: numberField(item, "imports") ?? 0,
          }))
          .filter((item) => item.path.length > 0)
      : [],
    most_imported_modules: Array.isArray(payload.most_imported_modules)
      ? payload.most_imported_modules
          .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
          .map((item) => ({module: stringField(item, "module"), count: numberField(item, "count") ?? 0}))
          .filter((item) => item.module.length > 0)
      : [],
  };
}

export function workspaceSnapshotToPreview(content: string): TabPreview {
  const git = parseGitLine(content);
  const sync = parseGitSyncSummary(content);
  const topology = summarizeTopology(content);
  const hotspots = summarizeHotspots(content);
  const changedHotspots = parseGitHotspotsLine(content);
  const changedPaths = parseGitChangedPathsLine(content);
  const warningSummary =
    topology.warnings.length > 0 ? `${topology.warnings.length} (${topology.warnings.join(", ")})` : "0";
  const hotspotSummary = hotspots.length > 0 ? hotspots.join("; ") : "none";
  const inboundHotspots = summarizeImportedModules(content);
  const branchStatus = summarizeBranchStatus(sync);
  const topologyStatus = summarizeTopologyStatus(topology);
  const topologyRisk = topology.warnings.length > 0 ? topology.warnings[0] ?? "warning" : "stable";
  const riskPreview = summarizeRiskPreview(topology);
  const topologyPreview = summarizeTopologyPreview(
    topology.warnings[0] ?? "none",
    topology.primaryPeer,
    topology.pressure,
  );
  const topologyPressurePreview = summarizeTopologyPressurePreview(topology);
  const dirtyPressure = summarizeDirtyPressure(git);
  const repoRisk = summarizeRepoRisk(git, sync, topology);
  const branchSyncPreview = summarizeBranchSyncPreview(sync, branchStatus, repoRisk);
  const repoRiskPreview = summarizeRepoRiskPreview(branchStatus, riskPreview);
  const primaryChangedPath = firstSemicolonSegment(changedPaths);
  const primaryChangedHotspot = firstSemicolonSegment(changedHotspots);
  const primaryFileHotspot = firstSemicolonSegment(hotspotSummary);
  const primaryDependencyHotspot = firstSemicolonSegment(inboundHotspots);
  const leadHotspotPreview = summarizeLeadHotspotPreview(
    primaryChangedHotspot,
    primaryChangedPath,
    primaryDependencyHotspot,
  );
  const hotspotPressurePreview = summarizeHotspotPressurePreview(
    primaryChangedHotspot,
    primaryDependencyHotspot,
  );
  const dirtySummary =
    git.counts.staged === null || git.counts.unstaged === null || git.counts.untracked === null
      ? git.dirty
      : `${git.counts.staged} staged, ${git.counts.unstaged} unstaged, ${git.counts.untracked} untracked`;

  return {
    "Repo root": extractRepoRoot(content),
    Branch: git.branch,
    Head: git.head,
    Sync: sync.sync,
    "Branch status": branchStatus,
    Upstream: sync.upstream,
    Ahead: sync.ahead,
    Behind: sync.behind,
    "Branch sync preview": branchSyncPreview,
    "Repo risk preview": repoRiskPreview,
    "Repo risk": repoRisk,
    Dirty: dirtySummary,
    "Dirty pressure": dirtyPressure,
    Staged: git.counts.staged === null ? "n/a" : String(git.counts.staged),
    Unstaged: git.counts.unstaged === null ? "n/a" : String(git.counts.unstaged),
    Untracked: git.counts.untracked === null ? "n/a" : String(git.counts.untracked),
    "Changed hotspots": changedHotspots,
    "Changed paths": changedPaths,
    "Hotspot summary": summarizeHotspotPreview(changedHotspots, hotspotSummary, inboundHotspots, changedPaths),
    "Lead hotspot preview": leadHotspotPreview,
    "Hotspot pressure preview": hotspotPressurePreview,
    "Topology warnings": warningSummary,
    "Topology warning severity": topology.warningSeverity,
    "Topology status": topologyStatus,
    "Topology risk": topologyRisk,
    "Risk preview": riskPreview,
    "Topology preview": topologyPreview,
    "Topology pressure preview": topologyPressurePreview,
    "Primary warning": topology.warnings[0] ?? "none",
    "Primary peer drift": topology.primaryPeerDrift,
    "Primary topology peer": topology.primaryPeer,
    "Topology peer count": String(topology.peerCount),
    "Peer drift markers": topology.peerDriftMarkers,
    "Topology peers": topology.peers.length > 0 ? topology.peers.join("; ") : "none",
    "Topology pressure": topology.pressure,
    "Primary changed hotspot": primaryChangedHotspot,
    "Primary changed path": primaryChangedPath,
    "Primary file hotspot": primaryFileHotspot,
    "Primary dependency hotspot": primaryDependencyHotspot,
    Hotspots: hotspotSummary,
    Inventory: [
      `${extractWorkspaceMetric(content, "Python modules")} modules`,
      `${extractWorkspaceMetric(content, "Python tests")} tests`,
      `${extractWorkspaceMetric(content, "Scripts")} scripts`,
      `${extractWorkspaceMetric(content, "Docs")} docs`,
      `${extractWorkspaceMetric(content, "Workflows")} workflows`,
    ].join(" | "),
    "Language mix": summarizeLanguageMix(content),
    "Inbound hotspots": inboundHotspots,
  };
}

export function workspacePayloadToPreview(payload: WorkspaceSnapshotPayload): TabPreview {
  const git = payload.git;
  const topology = workspaceTopologySummaryFromPayload(payload);
  const changedHotspots =
    git.changed_hotspots.map((item) => `${item.name} (${item.count})`).join("; ") || "none";
  const changedPaths = git.changed_paths.join("; ") || "none";
  const hotspotSummary = summarizeHotspotsFromPayload(payload.largest_python_files);
  const inboundHotspots = summarizeImportedModulesFromPayload(payload.most_imported_modules);
  const sync = {
    sync: git.sync.summary || "unavailable",
    upstream:
      git.sync.status === "detached"
        ? "detached HEAD"
        : git.sync.upstream && git.sync.upstream.length > 0
          ? git.sync.upstream
          : git.sync.summary || "unavailable",
    ahead: git.sync.ahead === null || git.sync.ahead === undefined ? "n/a" : String(git.sync.ahead),
    behind: git.sync.behind === null || git.sync.behind === undefined ? "n/a" : String(git.sync.behind),
  };
  const branchStatus = summarizeBranchStatus(sync);
  const topologyStatus = summarizeTopologyStatus(topology);
  const topologyRisk = topology.warnings.length > 0 ? topology.warnings[0] ?? "warning" : "stable";
  const riskPreview = summarizeRiskPreview(topology);
  const topologyPreview = summarizeTopologyPreview(
    topology.warnings[0] ?? "none",
    topology.primaryPeer,
    topology.pressure,
  );
  const topologyPressurePreview = summarizeTopologyPressurePreview(topology);
  const dirtySummary =
    git.staged === null || git.staged === undefined || git.unstaged === null || git.unstaged === undefined || git.untracked === null || git.untracked === undefined
      ? `${git.branch} (${git.sync.summary || "unavailable"})`
      : `${git.staged} staged, ${git.unstaged} unstaged, ${git.untracked} untracked`;
  const dirtyCounts = {
    branch: git.branch,
    head: git.head,
    counts: {
      staged: git.staged ?? null,
      unstaged: git.unstaged ?? null,
      untracked: git.untracked ?? null,
    },
    dirty: dirtySummary,
  };
  const dirtyPressure = summarizeDirtyPressure(dirtyCounts);
  const repoRisk = summarizeRepoRisk(dirtyCounts, sync, topology);
  const branchSyncPreview = summarizeBranchSyncPreview(sync, branchStatus, repoRisk);
  const repoRiskPreview = summarizeRepoRiskPreview(branchStatus, riskPreview);
  const primaryChangedPath = firstSemicolonSegment(changedPaths);
  const primaryChangedHotspot = firstSemicolonSegment(changedHotspots);
  const primaryFileHotspot = firstSemicolonSegment(hotspotSummary.join("; ") || "none");
  const primaryDependencyHotspot = firstSemicolonSegment(inboundHotspots);
  const leadHotspotPreview = summarizeLeadHotspotPreview(
    primaryChangedHotspot,
    primaryChangedPath,
    primaryDependencyHotspot,
  );
  const hotspotPressurePreview = summarizeHotspotPressurePreview(
    primaryChangedHotspot,
    primaryDependencyHotspot,
  );

  return {
    "Repo root": payload.repo_root,
    Branch: git.branch,
    Head: git.head,
    Sync: sync.sync,
    "Branch status": branchStatus,
    Upstream: sync.upstream,
    Ahead: sync.ahead,
    Behind: sync.behind,
    "Branch sync preview": branchSyncPreview,
    "Repo risk preview": repoRiskPreview,
    "Repo risk": repoRisk,
    Dirty: dirtySummary,
    "Dirty pressure": dirtyPressure,
    Staged: git.staged === null || git.staged === undefined ? "n/a" : String(git.staged),
    Unstaged: git.unstaged === null || git.unstaged === undefined ? "n/a" : String(git.unstaged),
    Untracked: git.untracked === null || git.untracked === undefined ? "n/a" : String(git.untracked),
    "Changed hotspots": changedHotspots,
    "Changed paths": changedPaths,
    "Hotspot summary": summarizeHotspotPreview(changedHotspots, hotspotSummary.join("; ") || "none", inboundHotspots, changedPaths),
    "Lead hotspot preview": leadHotspotPreview,
    "Hotspot pressure preview": hotspotPressurePreview,
    "Topology warnings": topology.warnings.length > 0 ? `${topology.warnings.length} (${topology.warnings.join(", ")})` : "0",
    "Topology warning severity": topology.warningSeverity,
    "Topology status": topologyStatus,
    "Topology risk": topologyRisk,
    "Risk preview": riskPreview,
    "Topology preview": topologyPreview,
    "Topology pressure preview": topologyPressurePreview,
    "Primary warning": topology.warnings[0] ?? "none",
    "Primary peer drift": topology.primaryPeerDrift,
    "Primary topology peer": topology.primaryPeer,
    "Topology peer count": String(topology.peerCount),
    "Peer drift markers": topology.peerDriftMarkers,
    "Topology peers": topology.peers.length > 0 ? topology.peers.join("; ") : "none",
    "Topology pressure": topology.pressure,
    "Primary changed hotspot": primaryChangedHotspot,
    "Primary changed path": primaryChangedPath,
    "Primary file hotspot": primaryFileHotspot,
    "Primary dependency hotspot": primaryDependencyHotspot,
    Hotspots: hotspotSummary.join("; ") || "none",
    Inventory: [
      inventoryFieldLabel(payload.inventory.python_modules, "modules"),
      inventoryFieldLabel(payload.inventory.python_tests, "tests"),
      inventoryFieldLabel(payload.inventory.scripts, "scripts"),
      inventoryFieldLabel(payload.inventory.docs, "docs"),
      inventoryFieldLabel(payload.inventory.workflows, "workflows"),
    ].join(" | "),
    "Language mix": payload.language_mix
      .slice(0, 4)
      .map((item) => `${item.suffix}: ${item.count}`)
      .join("; ") || "none",
    "Inbound hotspots": inboundHotspots,
  };
}

function extractRuntimeDb(content: string): string {
  const lines = content.split("\n");
  const runtimeDb = lines.find((line) => line.includes("runtime.db"));
  if (!runtimeDb) {
    return "runtime db not reported";
  }
  return runtimeDb.replace(/^\s*Runtime DB:\s*/i, "").trim();
}

function extractToolchain(content: string): string[] {
  const lines = content.split("\n");
  const start = lines.findIndex((line) => line.trim() === "Toolchain");
  if (start === -1) {
    return [];
  }

  const toolchain: string[] = [];
  for (let index = start + 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line.trim()) {
      continue;
    }
    if (!/^\s{4,}[a-z0-9._-]+:/i.test(line)) {
      break;
    }
    const name = line.trim().split(":")[0]?.trim();
    if (name) {
      toolchain.push(name);
    }
  }
  return toolchain;
}

function extractRuntimeMetricLine(content: string, prefix: string): string {
  return (
    content
      .split("\n")
      .map((line) => line.trim())
      .find((line) => line.startsWith(prefix)) ?? ""
  );
}

function parseRuntimeMetrics(line: string): Record<string, string> {
  return Object.fromEntries(
    Array.from(line.matchAll(/([A-Za-z][A-Za-z0-9]*)=([^\s]+)/g), (match) => [match[1], match[2]]),
  );
}

function runtimeMetricValue(metrics: Record<string, string>, key: string): string {
  return metrics[key] ?? "n/a";
}

function runtimeMetricFragment(metrics: Record<string, string>, key: string, label: string): string {
  const value = runtimeMetricValue(metrics, key);
  return value === "n/a" ? "" : `${value} ${label}`;
}

function joinRuntimeMetricFragments(fragments: string[]): string {
  const filtered = fragments.filter((fragment) => fragment.length > 0);
  return filtered.length > 0 ? filtered.join(" | ") : "none";
}

function summarizeSessionState(line: string): string {
  if (!line) {
    return "none";
  }
  const metrics = parseRuntimeMetrics(line);
  if (Object.keys(metrics).length === 0) {
    return "none";
  }
  return joinRuntimeMetricFragments([
    runtimeMetricFragment(metrics, "Sessions", "sessions"),
    runtimeMetricFragment(metrics, "Claims", "claims"),
    runtimeMetricFragment(metrics, "ActiveClaims", "active claims"),
    runtimeMetricFragment(metrics, "AckedClaims", "acked claims"),
  ]);
}

function summarizeRunState(line: string): string {
  if (!line) {
    return "none";
  }
  const metrics = parseRuntimeMetrics(line);
  if (Object.keys(metrics).length === 0) {
    return "none";
  }
  return joinRuntimeMetricFragments([
    runtimeMetricFragment(metrics, "Runs", "runs"),
    runtimeMetricFragment(metrics, "ActiveRuns", "active runs"),
  ]);
}

function summarizeContextState(line: string): string {
  if (!line) {
    return "none";
  }
  const metrics = parseRuntimeMetrics(line);
  if (Object.keys(metrics).length === 0) {
    return "none";
  }
  return joinRuntimeMetricFragments([
    runtimeMetricFragment(metrics, "Artifacts", "artifacts"),
    runtimeMetricFragment(metrics, "PromotedFacts", "promoted facts"),
    runtimeMetricFragment(metrics, "ContextBundles", "context bundles"),
    runtimeMetricFragment(metrics, "OperatorActions", "operator actions"),
  ]);
}

function summarizeRuntimeFreshness(loopState: string, updatedAt: string, verificationBundle: string): string {
  return [
    loopState || "unknown",
    `updated ${updatedAt || "unknown"}`,
    `verify ${verificationBundle || "none"}`,
  ].join(" | ");
}

function summarizeControlPulsePreview(lastResult: string, runtimeFreshness: string, updatedAt: string, now: Date = new Date()): string {
  return [
    freshnessToken(updatedAt, now),
    (lastResult || "unknown").trim() || "unknown",
    (runtimeFreshness || "unknown").trim() || "unknown",
  ].join(" | ");
}

function previewControlPulse(preview: TabPreview, now: Date = new Date()): string | null {
  const explicit = preview["Control pulse preview"];
  if (typeof explicit === "string" && explicit.length > 0 && explicit !== "none" && explicit !== "unknown") {
    return explicit;
  }

  const lastResult = (preview["Last result"] ?? "").trim();
  const verificationBundle =
    preview["Verification bundle"] ??
    verificationBundleLabel(
      parseVerificationBundle(preview["Verification checks"] ?? "none", preview["Verification summary"] ?? "none"),
    );
  const runtimeFreshness = (
    preview["Runtime freshness"] ??
    summarizeRuntimeFreshness(preview["Loop state"] ?? "unknown", preview.Updated ?? "unknown", verificationBundle)
  ).trim();
  if (lastResult.length === 0 && runtimeFreshness.length === 0) {
    return null;
  }

  return summarizeControlPulsePreview(lastResult || "unknown", runtimeFreshness || "unknown", preview.Updated ?? "unknown", now);
}

function summarizeRuntimeSummary(
  runtimeDb: string,
  sessionState: string,
  runState: string,
  contextState: string,
): string {
  return [
    runtimeDb || "runtime db not reported",
    sessionState || "none",
    runState || "none",
    contextState || "none",
  ].join(" | ");
}

function normalizeCanonicalRuntimeSnapshot(value: unknown): CanonicalRuntimeSnapshot | undefined {
  const snapshot = asRecord(value);
  const snapshotId = stringField(snapshot, "snapshot_id");
  if (!snapshotId) {
    return undefined;
  }
  return {
    snapshot_id: snapshotId,
    created_at: stringField(snapshot, "created_at"),
    repo_root: stringField(snapshot, "repo_root"),
    runtime_db: stringField(snapshot, "runtime_db") || undefined,
    health: stringField(snapshot, "health", "unknown"),
    bridge_status: stringField(snapshot, "bridge_status", "unknown"),
    active_session_count: numberField(snapshot, "active_session_count") ?? 0,
    active_run_count: numberField(snapshot, "active_run_count") ?? 0,
    artifact_count: numberField(snapshot, "artifact_count") ?? 0,
    context_bundle_count: numberField(snapshot, "context_bundle_count") ?? 0,
    anomaly_count: numberField(snapshot, "anomaly_count") ?? 0,
    verification_status: stringField(snapshot, "verification_status", "unknown"),
    next_task: stringField(snapshot, "next_task") || undefined,
    active_task: stringField(snapshot, "active_task") || undefined,
    worktree_count: numberField(snapshot, "worktree_count"),
    summary: stringField(snapshot, "summary") || undefined,
    warnings: asStringArray(snapshot.warnings),
    metrics: Object.fromEntries(
      Object.entries(asRecord(snapshot.metrics)).map(([key, value]) => [key, String(value)]),
    ),
    metadata: asRecord(snapshot.metadata),
  };
}

export function runtimeSnapshotPayloadFromEvent(event: Record<string, unknown>): RuntimeSnapshotPayload | undefined {
  const payload = asRecord(event.payload);
  if (stringField(payload, "domain") !== "runtime_snapshot" || stringField(payload, "version") !== "v1") {
    return undefined;
  }
  const snapshot = normalizeCanonicalRuntimeSnapshot(payload.snapshot);
  if (!snapshot) {
    return undefined;
  }
  return {
    version: "v1",
    domain: "runtime_snapshot",
    snapshot,
  };
}

function runtimeSnapshotStateFromPayload(payload: RuntimeSnapshotPayload): {
  runtimeDb: string;
  sessionState: string;
  runState: string;
  contextState: string;
  runtimeActivity: string;
  artifactState: string;
  alerts: string;
} {
  const metrics = payload.snapshot.metrics ?? {};
  const claims = String(metrics.claims ?? "0");
  const activeClaims = String(metrics.active_claims ?? "0");
  const acknowledgedClaims = String(metrics.acknowledged_claims ?? "0");
  const promotedFacts = String(metrics.promoted_facts ?? "0");
  const operatorActions = String(metrics.operator_actions ?? "0");
  return {
    runtimeDb: payload.snapshot.runtime_db ?? "unknown",
    sessionState: `${payload.snapshot.active_session_count} sessions | ${claims} claims | ${activeClaims} active claims | ${acknowledgedClaims} acked claims`,
    runState: `${payload.snapshot.active_run_count === 1 ? "1 active run" : `${payload.snapshot.active_run_count} active runs`} | ${String((asRecord(payload.snapshot.metadata.overview).runs ?? payload.snapshot.active_run_count))} runs total`,
    contextState: `${payload.snapshot.artifact_count} artifacts | ${promotedFacts} promoted facts | ${payload.snapshot.context_bundle_count} context bundles | ${operatorActions} operator actions`,
    runtimeActivity:
      `Sessions=${payload.snapshot.active_session_count} Runs=${payload.snapshot.active_run_count} Claims=${claims} ActiveClaims=${activeClaims} AckedClaims=${acknowledgedClaims}`,
    artifactState: `Artifacts=${payload.snapshot.artifact_count} PromotedFacts=${promotedFacts} ContextBundles=${payload.snapshot.context_bundle_count} OperatorActions=${operatorActions}`,
    alerts: payload.snapshot.warnings.length > 0 ? payload.snapshot.warnings.join("; ") : "none",
  };
}

function hasPreviewSignal(value: string | undefined): boolean {
  return Boolean(value && value !== "none" && value !== "unknown" && value !== "n/a");
}

function normalizeVerificationPreview(preview: TabPreview): void {
  const bundle = parseVerificationBundle(preview["Verification checks"] ?? "none", preview["Verification summary"] ?? "none");
  if (bundle.length === 0) {
    return;
  }
  const rows = buildVerificationSummaryRows(bundle);
  preview["Verification summary"] = verificationBundleLabel(bundle);
  preview["Verification bundle"] = rows.bundle;
  preview["Verification status"] = rows.status;
  preview["Verification passing"] = rows.passing;
  preview["Verification failing"] = rows.failing;
}

function runtimeSupervisorPreviewFromPayload(payload: RuntimeSnapshotPayload): TabPreview {
  const preview = asRecord(payload.snapshot.metadata.supervisor_preview);
  const stringEntries = Object.entries(preview).filter(([, value]) => typeof value === "string");
  return Object.fromEntries(stringEntries) as TabPreview;
}

export function runtimePayloadToPreview(payload: RuntimeSnapshotPayload, summary: SupervisorControlState | null = null, now: Date = new Date()): TabPreview {
  const state = runtimeSnapshotStateFromPayload(payload);
  const supervisorPreview = runtimeSupervisorPreviewFromPayload(payload);
  const preview: TabPreview = {
    "Runtime DB": state.runtimeDb,
    "Session state": state.sessionState,
    "Run state": state.runState,
    "Context state": state.contextState,
    "Runtime activity": state.runtimeActivity,
    "Artifact state": state.artifactState,
    Toolchain: "none",
    Alerts: state.alerts,
  };
  preview["Runtime summary"] = summarizeRuntimeSummary(preview["Runtime DB"], preview["Session state"], preview["Run state"], preview["Context state"]);

  const mergedPreview = summary
    ? {
        ...preview,
        ...runtimeSnapshotToPreview("", summary, now),
        "Runtime DB": preview["Runtime DB"],
        "Session state": preview["Session state"],
        "Run state": preview["Run state"],
        "Context state": preview["Context state"],
        "Runtime activity": preview["Runtime activity"],
        "Artifact state": preview["Artifact state"],
        Alerts: preview.Alerts,
      }
    : preview;

  const fallbackFields: TabPreview = {
    ...supervisorPreview,
    ...(hasPreviewSignal(payload.snapshot.active_task ?? undefined) ? {"Active task": payload.snapshot.active_task ?? ""} : {}),
    ...(hasPreviewSignal(payload.snapshot.next_task ?? undefined) ? {"Next task": payload.snapshot.next_task ?? ""} : {}),
    ...(hasPreviewSignal(payload.snapshot.verification_status)
      ? {"Verification status": payload.snapshot.verification_status}
      : {}),
    ...(hasPreviewSignal(payload.snapshot.created_at) ? {Updated: payload.snapshot.created_at} : {}),
  };

  Object.entries(supervisorPreview).forEach(([key, value]) => {
    if (RUNTIME_SUPERVISOR_AUTHORITATIVE_FIELDS.has(key) && hasPreviewSignal(value)) {
      mergedPreview[key] = value;
    }
  });

  Object.entries(fallbackFields).forEach(([key, value]) => {
    if (!hasPreviewSignal(mergedPreview[key])) {
      mergedPreview[key] = value;
    }
  });

  mergedPreview["Runtime summary"] = summarizeRuntimeSummary(
    mergedPreview["Runtime DB"] ?? "runtime db not reported",
    mergedPreview["Session state"] ?? "none",
    mergedPreview["Run state"] ?? "none",
    mergedPreview["Context state"] ?? "none",
  );

  if (!hasPreviewSignal(mergedPreview["Verification summary"]) && hasPreviewSignal(mergedPreview["Verification status"])) {
    mergedPreview["Verification summary"] = mergedPreview["Verification status"];
  }
  normalizeVerificationPreview(mergedPreview);
  if (!hasPreviewSignal(mergedPreview["Last result"])) {
    const resultParts = [mergedPreview["Result status"], mergedPreview.Acceptance].filter((value) => hasPreviewSignal(value));
    if (resultParts.length > 0) {
      mergedPreview["Last result"] = resultParts.join(" / ");
    }
  }
  if (!hasPreviewSignal(mergedPreview["Runtime freshness"])) {
    mergedPreview["Runtime freshness"] = summarizeRuntimeFreshness(
      mergedPreview["Loop state"] ?? "unknown",
      mergedPreview.Updated ?? "unknown",
      mergedPreview["Verification bundle"] ??
        verificationBundleLabel(
          parseVerificationBundle(mergedPreview["Verification checks"] ?? "none", mergedPreview["Verification summary"] ?? "none"),
        ),
    );
  }
  if (!hasPreviewSignal(mergedPreview["Control pulse preview"])) {
    mergedPreview["Control pulse preview"] = summarizeControlPulsePreview(
      mergedPreview["Last result"] ?? "unknown",
      mergedPreview["Runtime freshness"] ?? "unknown",
      mergedPreview.Updated ?? "unknown",
      now,
    );
  }

  return mergedPreview;
}

function extractRuntimeAlerts(content: string): string[] {
  return content
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .filter((line) => /^no\b/i.test(line) || /not found|missing|error|failed|degraded|unavailable/i.test(line))
    .slice(0, 2);
}

function buildRuntimeSnapshotPrelude(content: string, summary: SupervisorControlState | null = null, now: Date = new Date()): string[] {
  const preview = runtimeSnapshotToPreview(content, summary, now);
  return buildRuntimeSnapshotPreludeFromPreview(preview, now);
}

function buildRuntimeSnapshotPreludeFromPreview(preview: TabPreview, now: Date = new Date()): string[] {
  const runtimeActivity = preview["Runtime activity"] ?? "none";
  const artifactState = preview["Artifact state"] ?? "none";
  const controlPulse = previewControlPulse(preview, now);
  return [
    "# Control Preview",
    `Runtime DB: ${preview["Runtime DB"] ?? "unknown"}`,
    `Session state: ${preview["Session state"] ?? summarizeSessionState(runtimeActivity)}`,
    `Run state: ${preview["Run state"] ?? summarizeRunState(runtimeActivity)}`,
    `Active runs detail: ${preview["Active runs detail"] ?? "none"}`,
    `Context state: ${preview["Context state"] ?? summarizeContextState(artifactState)}`,
    `Recent operator actions: ${preview["Recent operator actions"] ?? "none"}`,
    `Runtime activity: ${runtimeActivity}`,
    `Artifact state: ${artifactState}`,
    `Toolchain: ${preview.Toolchain ?? "none"}`,
    `Alerts: ${preview.Alerts ?? "none"}`,
    ...(controlPulse ? [`Control pulse preview: ${controlPulse}`] : []),
    "",
  ];
}

export function runtimeSnapshotToPreview(content: string, summary: SupervisorControlState | null = null, now: Date = new Date()): TabPreview {
  const runtimeDb = extractRuntimeDb(content);
  const toolchain = extractToolchain(content);
  const alerts = extractRuntimeAlerts(content);
  const sessions = extractRuntimeMetricLine(content, "Sessions=");
  const artifacts = extractRuntimeMetricLine(content, "Artifacts=");
  const preview: TabPreview = {
    "Runtime DB": runtimeDb,
    "Session state": summarizeSessionState(sessions),
    "Run state": summarizeRunState(sessions),
    "Context state": summarizeContextState(artifacts),
    "Runtime activity": sessions || "none",
    "Artifact state": artifacts || "none",
    Toolchain: toolchain.length > 0 ? toolchain.join(", ") : "none",
    Alerts: alerts.length > 0 ? alerts.join("; ") : "none",
  };
  preview["Runtime summary"] = summarizeRuntimeSummary(
    preview["Runtime DB"],
    preview["Session state"],
    preview["Run state"],
    preview["Context state"],
  );
  if (!summary) {
    return preview;
  }

  const completedTasks =
    summary.tasksTotal !== null && summary.tasksPending !== null ? Math.max(summary.tasksTotal - summary.tasksPending, 0) : null;
  preview["Loop state"] = `cycle ${summary.cycle ?? "n/a"} ${summary.runStatus}`;
  preview["Task progress"] =
    summary.tasksTotal !== null && summary.tasksPending !== null
      ? `${completedTasks} done, ${summary.tasksPending} pending of ${summary.tasksTotal}`
      : "unknown";
  preview["Active task"] = summary.activeTaskId || "none";
  preview["Result status"] = summary.lastResultStatus || "unknown";
  preview.Acceptance = summary.acceptance || "unknown";
  preview["Last result"] = [summary.lastResultStatus, summary.acceptance].filter((value) => value.length > 0).join(" / ") || "unknown";
  preview["Verification summary"] = summary.verificationSummary || "none";
  preview["Verification checks"] = summary.verificationChecks.length > 0 ? summary.verificationChecks.join("; ") : "none";
  normalizeVerificationPreview(preview);
  preview["Loop decision"] =
    summary.continueRequired === null ? "unknown" : summary.continueRequired ? "continue required" : "ready to stop";
  preview["Next task"] = summary.nextTask || "none";
  preview["Durable state"] = summary.stateDir;
  preview.Updated = summary.updatedAt || "unknown";
  preview["Runtime freshness"] = summarizeRuntimeFreshness(
    preview["Loop state"],
    preview.Updated,
    preview["Verification bundle"],
  );
  preview["Control pulse preview"] = summarizeControlPulsePreview(preview["Last result"], preview["Runtime freshness"], preview.Updated, now);
  return preview;
}

function buildSupervisorPrelude(summary: SupervisorControlState | null): string[] {
  if (!summary) {
    return [];
  }

  const completedTasks =
    summary.tasksTotal !== null && summary.tasksPending !== null ? Math.max(summary.tasksTotal - summary.tasksPending, 0) : null;
  const taskProgress =
    summary.tasksTotal !== null && summary.tasksPending !== null
      ? `${completedTasks} done, ${summary.tasksPending} pending of ${summary.tasksTotal}`
      : "unknown";
  const lastResult = [summary.lastResultStatus, summary.acceptance].filter((value) => value.length > 0).join(" / ") || "unknown";
  const checks = summary.verificationChecks.length > 0 ? summary.verificationChecks.join("; ") : "none";
  const verificationRows = buildVerificationSummaryRows(parseVerificationBundle(checks, summary.verificationSummary || "none"));
  const bundle = verificationRows.bundle;
  const continueState =
    summary.continueRequired === null ? "unknown" : summary.continueRequired ? "continue required" : "ready to stop";

  return [
    `Loop state: cycle ${summary.cycle ?? "n/a"} ${summary.runStatus}`,
    `Task progress: ${taskProgress}`,
    `Active task: ${summary.activeTaskId || "none"}`,
    `Last result: ${lastResult}`,
    `Verification summary: ${summary.verificationSummary || "none"}`,
    `Verification checks: ${checks}`,
    `Verification status: ${verificationRows.status}`,
    `Verification passing: ${verificationRows.passing}`,
    `Verification failing: ${verificationRows.failing}`,
    `Verification bundle: ${bundle}`,
    `Loop decision: ${continueState}`,
    `Next task: ${summary.nextTask || "none"}`,
    `Durable state: ${summary.stateDir}`,
    "",
  ];
}

function buildSupervisorPreludeFromPreview(preview: TabPreview): string[] {
  const bundle =
    preview["Verification bundle"] ??
    verificationBundleLabel(
      parseVerificationBundle(preview["Verification checks"] ?? "none", preview["Verification summary"] ?? "none"),
    );
  const lines = [
    `Loop state: ${preview["Loop state"] ?? "n/a"}`,
    `Task progress: ${preview["Task progress"] ?? "n/a"}`,
    `Active task: ${preview["Active task"] ?? "none"}`,
    `Result status: ${preview["Result status"] ?? "unknown"}`,
    `Acceptance: ${preview.Acceptance ?? "unknown"}`,
    `Last result: ${preview["Last result"] ?? "unknown"}`,
    `Verification summary: ${preview["Verification summary"] ?? "none"}`,
    `Verification checks: ${preview["Verification checks"] ?? "none"}`,
    `Verification status: ${preview["Verification status"] ?? "unknown"}`,
    `Verification passing: ${preview["Verification passing"] ?? "unknown"}`,
    `Verification failing: ${preview["Verification failing"] ?? "unknown"}`,
    `Verification bundle: ${bundle}`,
    `Loop decision: ${preview["Loop decision"] ?? "unknown"}`,
    `Next task: ${preview["Next task"] ?? "none"}`,
    `Updated: ${preview.Updated ?? "unknown"}`,
    `Durable state: ${preview["Durable state"] ?? "unknown"}`,
  ];

  return lines.every((line) => /:\s+(n\/a|none|unknown)$/.test(line)) ? [] : lines;
}

function summarizeTool(argumentsText: string, toolName: string): string {
  const trimmed = argumentsText.trim();
  if (!trimmed) {
    return toolName;
  }
  try {
    const parsed = JSON.parse(trimmed) as Record<string, unknown>;
    const description = parsed.description;
    const command = parsed.command;
    const query = parsed.q;
    return String(description ?? command ?? query ?? toolName);
  } catch {
    return toolName;
  }
}

export function isSlashCommandPrompt(prompt: string): boolean {
  return prompt.trim().startsWith("/");
}

export function normalizeCommandName(command: string): string {
  const trimmed = command.trim().replace(/^\//, "");
  const [name = ""] = trimmed.split(/\s+/, 1);
  return name.toLowerCase();
}

export function inferSlashCommand(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }
  const match = trimmed.match(/(?:^|[\s`"(['“‘])(\/[a-z0-9._-]+)(?=$|[\s`"')\].,:;!?])/);
  return match?.[1] ?? "";
}

function nestedCommandString(value: unknown): string {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed.startsWith("/") ? trimmed : "";
  }

  const record = asRecord(value);
  const directCommand = String(record.command ?? "").trim();
  if (directCommand) {
    return directCommand;
  }

  const argsCommand = String(asRecord(record.arguments).command ?? "").trim();
  if (argsCommand) {
    return argsCommand;
  }

  return "";
}

function nestedEnvelopeRecords(value: unknown): Record<string, unknown>[] {
  const record = asRecord(value);
  if (Object.keys(record).length === 0) {
    return [];
  }

  return [
    record,
    asRecord(record.payload),
    asRecord(record.request),
    asRecord(record.action),
    asRecord(record.arguments),
    asRecord(asRecord(record.payload).request),
    asRecord(asRecord(record.payload).action),
    asRecord(asRecord(record.payload).arguments),
    asRecord(asRecord(record.request).arguments),
    asRecord(asRecord(record.action).arguments),
  ].filter((entry, index, entries) => Object.keys(entry).length > 0 && entries.indexOf(entry) === index);
}

function nestedTargetPane(event: Record<string, unknown>): string {
  for (const entry of nestedEnvelopeRecords(event)) {
    const candidate = entry.target_pane;
    const normalized = normalizeTargetPaneId(String(candidate ?? ""));
    if (normalized) {
      return normalized;
    }
  }

  return "";
}

export function resolveEventCommand(event: Record<string, unknown>): string {
  for (const entry of nestedEnvelopeRecords(event)) {
    const explicitCommand = String(entry.command ?? "").trim();
    if (explicitCommand) {
      return explicitCommand;
    }

    const nestedCommand = nestedCommandString(entry.command);
    if (nestedCommand) {
      return nestedCommand;
    }
  }

  return inferSlashCommand(String(event.summary ?? ""));
}

export function commandTargetTab(command: string): string {
  const normalized = normalizeCommandName(command);

  if (["chat", "clear", "reset", "cancel", "paste", "copy", "copylast", "thread"].includes(normalized)) {
    return "chat";
  }

  if (normalized === "runtime") {
    return "runtime";
  }

  if (normalized === "git") {
    return "repo";
  }

  if (normalized === "model") {
    return "models";
  }

  if (["swarm", "agni", "gates", "witness", "openclaw", "hum"].includes(normalized)) {
    return "agents";
  }

  if (["evolve", "loops", "cascade"].includes(normalized)) {
    return "evolution";
  }

  if (
    ["context", "foundations", "telos", "dharma", "corpus", "evidence", "moltbook"].includes(
      normalized,
    )
  ) {
    return "ontology";
  }

  if (normalized === "trishula") {
    return "agents";
  }

  if (["sessions", "session", "notes", "memory", "archive", "darwin", "logs", "truth", "stigmergy"].includes(normalized)) {
    return "sessions";
  }

  if (["status", "help", "dashboard"].includes(normalized)) {
    return "control";
  }

  if (!normalized) {
    return "chat";
  }

  return "control";
}

const VALID_TARGET_PANES = new Set([
  "chat",
  "commands",
  "agents",
  "models",
  "evolution",
  "thinking",
  "tools",
  "timeline",
  "sessions",
  "approvals",
  "mission",
  "runtime",
  "repo",
  "ontology",
  "control",
]);

const TARGET_PANE_ALIASES: Record<string, string> = {
  workspace: "repo",
  dashboard: "control",
  command: "commands",
  registry: "commands",
  agent: "agents",
  model: "models",
  evolve: "evolution",
  notes: "sessions",
  session: "sessions",
  approval: "approvals",
  permissions: "approvals",
};

function normalizeTargetPaneId(targetPane: string): string {
  const normalized = targetPane.trim().toLowerCase();
  if (!normalized) {
    return "";
  }
  const canonical = TARGET_PANE_ALIASES[normalized] ?? normalized;
  return VALID_TARGET_PANES.has(canonical) ? canonical : "";
}

function isLauncherPaneTarget(targetPane: string): boolean {
  return targetPane === "commands";
}

export function resolveCommandTargetPane(event: Record<string, unknown>, fallback = "control"): string {
  const explicitTargetPane = nestedTargetPane(event);
  const command = resolveEventCommand(event);
  const inferredTargetPane = command ? commandTargetTab(command) : "";
  if (explicitTargetPane) {
    if (inferredTargetPane === "chat") {
      return "chat";
    }

    if (command && isLauncherPaneTarget(explicitTargetPane)) {
      return inferredTargetPane === "chat" ? explicitTargetPane : inferredTargetPane;
    }

    if (explicitTargetPane !== "chat") {
      return explicitTargetPane;
    }

    if (!command) {
      return explicitTargetPane;
    }

    return inferredTargetPane === "chat" ? explicitTargetPane : inferredTargetPane;
  }

  if (command) {
    return inferredTargetPane;
  }

  return fallback;
}

function summarizeIntent(intent: Record<string, unknown>): string {
  const kind = String(intent.kind ?? "chat");
  const reason = String(intent.reason ?? "").trim();
  const suffix = reason ? ` (${reason})` : "";
  if (kind === "command") {
    return `command -> /${String(intent.command ?? "")}${suffix}`;
  }
  if (kind === "model_switch") {
    const route = [String(intent.provider ?? ""), String(intent.model ?? "")]
      .filter((value) => value.length > 0)
      .join(":");
    const strategy = String(intent.strategy ?? "").trim();
    return [route ? `model switch -> ${route}` : "model switch", strategy ? `strategy ${strategy}` : "", suffix]
      .filter((value) => value.length > 0)
      .join(" ");
  }
  return `${kind}${suffix}`;
}

function previewValue(preview: Record<string, unknown>, key: string, fallback = "unavailable"): string {
  const value = preview[key];
  return typeof value === "string" && value.trim().length > 0 ? value : fallback;
}

function asRecordList(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null) : [];
}

function stringField(record: Record<string, unknown>, key: string, fallback = ""): string {
  const value = record[key];
  return typeof value === "string" ? value.trim() || fallback : fallback;
}

function numberField(record: Record<string, unknown>, key: string): number | null {
  const value = record[key];
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function boolField(record: Record<string, unknown>, key: string, fallback = false): boolean {
  const value = record[key];
  return typeof value === "boolean" ? value : fallback;
}

function formatUsd(value: number | null): string {
  return value === null ? "n/a" : `$${value.toFixed(2)}`;
}

function formatPercent(value: number | null): string {
  return value === null ? "n/a" : `${Math.round(value * 100)}%`;
}

function summarizeReplayState(replayOk: boolean, replayIssues: string[]): string {
  if (replayOk) {
    return "ok";
  }
  if (replayIssues.length === 0) {
    return "issues";
  }
  return `issues: ${replayIssues.join("; ")}`;
}

function sessionRouteLabel(session: Record<string, unknown>): string {
  const provider = stringField(session, "provider_id", "unknown");
  const model = stringField(session, "model_id", "unknown");
  return `${provider}:${model}`;
}

function sessionSummaryLine(session: Record<string, unknown>, fallback = "no summary"): string {
  return stringField(session, "summary", fallback);
}

function sessionBranchLabel(session: Record<string, unknown>): string {
  return stringField(session, "branch_label", "none");
}

function compactableRatioLabel(value: number | null): string {
  return formatPercent(value);
}

function normalizeCanonicalRoutingDecision(value: unknown): CanonicalRoutingDecision | undefined {
  const decision = asRecord(value);
  const routeId = stringField(decision, "route_id");
  if (!routeId) {
    return undefined;
  }
  return {
    route_id: routeId,
    provider_id: stringField(decision, "provider_id"),
    model_id: stringField(decision, "model_id"),
    strategy: stringField(decision, "strategy", "responsive"),
    reason: stringField(decision, "reason"),
    fallback_chain: asStringArray(decision.fallback_chain),
    degraded: boolField(decision, "degraded"),
    metadata: asRecord(decision.metadata),
  };
}

export function routingDecisionPayloadFromEvent(event: Record<string, unknown>): RoutingDecisionPayload | undefined {
  const payload = asRecord(event.payload);
  if (stringField(payload, "domain") !== "routing_decision" || stringField(payload, "version") !== "v1") {
    return undefined;
  }
  const decision = normalizeCanonicalRoutingDecision(payload.decision);
  if (!decision) {
    return undefined;
  }
  return {
    version: "v1",
    domain: "routing_decision",
    decision,
    strategies: asStringArray(payload.strategies),
    targets: asRecordList(payload.targets),
    fallback_targets: asRecordList(payload.fallback_targets),
  };
}

export function agentRoutesPayloadFromEvent(event: Record<string, unknown>): AgentRoutesPayload | undefined {
  const payload = asRecord(event.payload);
  if (stringField(payload, "domain") !== "agent_routes" || stringField(payload, "version") !== "v1") {
    return undefined;
  }
  return {
    version: "v1",
    domain: "agent_routes",
    routes: asRecordList(payload.routes),
    openclaw: asRecord(payload.openclaw),
    subagent_capabilities: asStringArray(payload.subagent_capabilities),
  };
}

function normalizeCanonicalSession(value: unknown): CanonicalSession | undefined {
  const session = asRecord(value);
  const sessionId = stringField(session, "session_id");
  if (!sessionId) {
    return undefined;
  }
  return {
    session_id: sessionId,
    provider_id: stringField(session, "provider_id"),
    model_id: stringField(session, "model_id"),
    cwd: stringField(session, "cwd"),
    created_at: stringField(session, "created_at"),
    updated_at: stringField(session, "updated_at"),
    status: stringField(session, "status", "unknown"),
    parent_session_id: stringField(session, "parent_session_id") || undefined,
    branch_label: stringField(session, "branch_label") || undefined,
    worktree_path: stringField(session, "worktree_path") || undefined,
    summary: stringField(session, "summary") || undefined,
    pinned_context: asStringArray(session.pinned_context),
    compacted_from_session_ids: asStringArray(session.compacted_from_session_ids),
    metadata: asRecord(session.metadata),
  };
}

function normalizeCanonicalEventEnvelope(value: unknown): CanonicalEventEnvelope | undefined {
  const event = asRecord(value);
  const eventId = stringField(event, "event_id");
  const eventType = stringField(event, "event_type");
  const createdAt = stringField(event, "created_at");
  if (!eventId || !eventType || !createdAt) {
    return undefined;
  }
  return {
    event_id: eventId,
    event_type: eventType,
    source: stringField(event, "source"),
    audience: stringField(event, "audience"),
    transport: stringField(event, "transport"),
    session_id: stringField(event, "session_id") || undefined,
    created_at: createdAt,
    payload: asRecord(event.payload),
    entity_refs: Array.isArray(event.entity_refs)
      ? event.entity_refs.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
      : [],
    correlation_id: stringField(event, "correlation_id") || undefined,
    raw: Object.keys(asRecord(event.raw)).length > 0 ? asRecord(event.raw) : undefined,
  };
}

function normalizeSessionCatalogEntry(value: unknown): SessionCatalogEntry | undefined {
  const entry = asRecord(value);
  const session = normalizeCanonicalSession(entry.session);
  if (!session) {
    return undefined;
  }
  return {
    session,
    replay_ok: boolField(entry, "replay_ok"),
    replay_issues: asStringArray(entry.replay_issues),
    provider_session_id: stringField(entry, "provider_session_id") || undefined,
    total_turns: numberField(entry, "total_turns") ?? 0,
    total_cost_usd: numberField(entry, "total_cost_usd") ?? 0,
  };
}

function normalizeSessionCompactionPreview(value: unknown): SessionCompactionPreview {
  const preview = asRecord(value);
  return {
    event_count: numberField(preview, "event_count") ?? 0,
    by_type: asNumberRecord(preview.by_type),
    compactable_ratio: numberField(preview, "compactable_ratio") ?? 0,
    protected_event_types: asStringArray(preview.protected_event_types),
    recent_event_types: asStringArray(preview.recent_event_types),
  };
}

function sessionCatalogPayloadRecord(payload: Record<string, unknown>): Record<string, unknown> {
  if (payload.domain === "session_catalog") {
    return payload;
  }
  return asRecord(payload.payload);
}

function sessionDetailPayloadRecord(payload: Record<string, unknown>): Record<string, unknown> {
  if (payload.domain === "session_detail") {
    return payload;
  }
  return asRecord(payload.payload);
}

export function sessionCatalogToLines(payload: Record<string, unknown>): TranscriptLine[] {
  const catalog = sessionCatalogPayloadRecord(payload);
  const sessions = asRecordList(catalog.sessions);
  const lines = [
    "# Session Catalog",
    `Sessions: ${String(numberField(catalog, "count") ?? sessions.length)}`,
    "",
    "## Recent sessions",
  ];

  if (sessions.length === 0) {
    lines.push("none");
  } else {
    for (const entry of sessions.slice(0, 12)) {
      const session = asRecord(entry.session);
      const replayIssues = Array.isArray(entry.replay_issues) ? entry.replay_issues.map(String) : [];
      lines.push(
        `- ${stringField(session, "session_id", "unknown")} | ${sessionRouteLabel(session)} | ${stringField(session, "status", "unknown")} | branch ${sessionBranchLabel(session)} | ${numberField(entry, "total_turns") ?? 0} turns | ${formatUsd(numberField(entry, "total_cost_usd"))} | replay ${summarizeReplayState(boolField(entry, "replay_ok"), replayIssues)}`,
      );
      lines.push(`  ${sessionSummaryLine(session)}`);
    }
  }

  return toLines("system", lines.join("\n"));
}

export function sessionCatalogToPreview(payload: Record<string, unknown>): TabPreview {
  const catalog = sessionCatalogPayloadRecord(payload);
  const sessions = asRecordList(catalog.sessions);
  const latest = sessions[0] ?? {};
  const latestSession = asRecord(latest.session);
  const latestReplayIssues = Array.isArray(latest.replay_issues) ? latest.replay_issues.map(String) : [];

  return {
    Sessions: String(numberField(catalog, "count") ?? sessions.length),
    "Latest session": stringField(latestSession, "session_id", "none"),
    "Latest route": Object.keys(latestSession).length > 0 ? sessionRouteLabel(latestSession) : "none",
    "Latest summary": sessionSummaryLine(latestSession, "none"),
    "Replay state": summarizeReplayState(boolField(latest, "replay_ok"), latestReplayIssues),
  };
}

export function sessionCatalogFromEvent(event: Record<string, unknown>): SessionCatalogPayload | undefined {
  const catalog = sessionCatalogPayloadRecord(event);
  if (!Array.isArray(catalog.sessions)) {
    return undefined;
  }
  const sessions = catalog.sessions.map(normalizeSessionCatalogEntry).filter((entry): entry is SessionCatalogEntry => Boolean(entry));
  return {
    count: numberField(catalog, "count") ?? sessions.length,
    sessions,
  };
}

export function sessionDetailToLines(payload: Record<string, unknown>): TranscriptLine[] {
  const detail = sessionDetailPayloadRecord(payload);
  const session = asRecord(detail.session);
  const replayIssues = Array.isArray(detail.replay_issues) ? detail.replay_issues.map(String) : [];
  const compaction = asRecord(detail.compaction_preview);
  const recentEvents = asRecordList(detail.recent_events);
  const approvalHistory = permissionHistoryFromEvent({payload: detail.approval_history});
  const protectedTypes = Array.isArray(compaction.protected_event_types) ? compaction.protected_event_types.map(String) : [];

  const lines = [
    "# Session Detail",
    `Session: ${stringField(session, "session_id", "unknown")}`,
    `Route: ${sessionRouteLabel(session)}`,
    `Status: ${stringField(session, "status", "unknown")}`,
    `Summary: ${sessionSummaryLine(session)}`,
    `Branch: ${sessionBranchLabel(session)}`,
    `Working tree: ${stringField(session, "cwd", "unknown")}`,
    `Replay: ${summarizeReplayState(boolField(detail, "replay_ok"), replayIssues)}`,
    `Compaction: ${numberField(compaction, "event_count") ?? 0} events | compactable ${compactableRatioLabel(numberField(compaction, "compactable_ratio"))}`,
    `Protected events: ${protectedTypes.join(", ") || "none"}`,
    "",
    "## Recent events",
  ];

  if (recentEvents.length === 0) {
    lines.push("none");
  } else {
    for (const event of recentEvents.slice(0, 12)) {
      lines.push(
        `- ${stringField(event, "event_type", "unknown")} | ${stringField(event, "created_at", "unknown")} | ${stringField(event, "event_id", "n/a")}`,
      );
    }
  }

  if (approvalHistory && approvalHistory.entries.length > 0) {
    lines.push("", "## Approval history");
    for (const entry of approvalHistory.entries.slice(0, 12)) {
      lines.push(`- ${entry.action_id} | ${entry.decision.tool_name} | ${entry.status}`);
      if (entry.resolution) {
        lines.push(`  ${entry.resolution.resolution} by ${entry.resolution.actor} | ${entry.resolution.enforcement_state}`);
      } else {
        lines.push(`  ${entry.decision.rationale}`);
      }
      if (entry.outcome) {
        const runtimeActionId = stringField(entry.outcome.metadata, "runtime_action_id");
        const runtimeEventId = stringField(entry.outcome.metadata, "runtime_event_id");
        const traceBits = [runtimeActionId, runtimeEventId].filter((value) => value.length > 0).join(" | ");
        lines.push(
          `  outcome ${entry.outcome.outcome} | ${entry.outcome.source} | ${entry.outcome.outcome_at}${
            traceBits ? ` | ${traceBits}` : ""
          }`,
        );
      }
    }
  }

  return toLines("system", lines.join("\n"));
}

export function sessionDetailToPreview(payload: Record<string, unknown>): TabPreview {
  const detail = sessionDetailPayloadRecord(payload);
  const session = asRecord(detail.session);
  const replayIssues = Array.isArray(detail.replay_issues) ? detail.replay_issues.map(String) : [];
  const compaction = asRecord(detail.compaction_preview);
  const recentEvents = asRecordList(detail.recent_events);

  return {
    "Session id": stringField(session, "session_id", "unknown"),
    Route: sessionRouteLabel(session),
    Status: stringField(session, "status", "unknown"),
    Summary: sessionSummaryLine(session),
    Replay: summarizeReplayState(boolField(detail, "replay_ok"), replayIssues),
    "Compaction ratio": compactableRatioLabel(numberField(compaction, "compactable_ratio")),
    "Recent events": String(recentEvents.length),
  };
}

export function permissionDecisionFromEvent(event: Record<string, unknown>): CanonicalPermissionDecision | undefined {
  const payload = asRecord(event.payload);
  if (stringField(payload, "domain") !== "permission_decision") {
    return undefined;
  }
  const actionId = stringField(payload, "action_id");
  const toolName = stringField(payload, "tool_name");
  if (!actionId || !toolName) {
    return undefined;
  }
  return {
    version: "v1",
    domain: "permission_decision",
    action_id: actionId,
    tool_name: toolName,
    risk: stringField(payload, "risk", "unknown"),
    decision: stringField(payload, "decision", "unknown"),
    rationale: stringField(payload, "rationale", "none"),
    policy_source: stringField(payload, "policy_source", "unknown"),
    requires_confirmation: boolField(payload, "requires_confirmation"),
    command_prefix: stringField(payload, "command_prefix") || null,
    metadata: asRecord(payload.metadata),
  };
}

export function permissionResolutionFromEvent(event: Record<string, unknown>): CanonicalPermissionResolution | undefined {
  const payload = asRecord(event.payload);
  if (stringField(payload, "domain") !== "permission_resolution") {
    return undefined;
  }
  const actionId = stringField(payload, "action_id");
  const resolution = stringField(payload, "resolution");
  if (!actionId || !resolution) {
    return undefined;
  }
  if (!["approved", "denied", "dismissed", "resolved"].includes(resolution)) {
    return undefined;
  }
  return {
    version: "v1",
    domain: "permission_resolution",
    action_id: actionId,
    resolution: resolution as CanonicalPermissionResolution["resolution"],
    resolved_at: stringField(payload, "resolved_at", new Date().toISOString()),
    actor: stringField(payload, "actor", "operator"),
    summary: stringField(payload, "summary", `${resolution} ${actionId}`),
    note: stringField(payload, "note") || null,
    enforcement_state: stringField(payload, "enforcement_state", "recorded_only"),
    metadata: asRecord(payload.metadata),
  };
}

export function permissionOutcomeFromEvent(event: Record<string, unknown>): CanonicalPermissionOutcome | undefined {
  const payload = asRecord(event.payload);
  if (stringField(payload, "domain") !== "permission_outcome") {
    return undefined;
  }
  const actionId = stringField(payload, "action_id");
  const outcome = stringField(payload, "outcome");
  if (
    !actionId ||
    !["runtime_recorded", "runtime_record_failed", "runtime_applied", "runtime_rejected", "runtime_expired"].includes(
      outcome,
    )
  ) {
    return undefined;
  }
  return {
    version: "v1",
    domain: "permission_outcome",
    action_id: actionId,
    outcome: outcome as CanonicalPermissionOutcome["outcome"],
    outcome_at: stringField(payload, "outcome_at", new Date().toISOString()),
    source: stringField(payload, "source", "runtime"),
    summary: stringField(payload, "summary", `${outcome} ${actionId}`),
    metadata: asRecord(payload.metadata),
  };
}

export function permissionHistoryFromEvent(event: Record<string, unknown>): PermissionHistoryPayload | undefined {
  const payload = asRecord(event.payload);
  if (stringField(payload, "domain") !== "permission_history" || stringField(payload, "version") !== "v1") {
    return undefined;
  }
  const entries: PermissionHistoryPayload["entries"] = [];
  for (const entry of asRecordList(payload.entries)) {
    const decision = permissionDecisionFromEvent({payload: entry.decision});
    if (!decision) {
      continue;
    }
    const resolutionRecord = asRecord(entry.resolution);
    const resolution =
      Object.keys(resolutionRecord).length > 0
        ? permissionResolutionFromEvent({payload: resolutionRecord})
        : undefined;
    const outcomeRecord = asRecord(entry.outcome);
    const outcome =
      Object.keys(outcomeRecord).length > 0
        ? permissionOutcomeFromEvent({payload: outcomeRecord})
        : undefined;
    const status = stringField(
      entry,
      "status",
      outcome?.outcome ?? resolution?.resolution ?? (boolField(entry, "pending") ? "pending" : "observed"),
    );
    if (
      ![
        "pending",
        "approved",
        "denied",
        "dismissed",
        "resolved",
        "runtime_recorded",
        "runtime_record_failed",
        "runtime_applied",
        "runtime_rejected",
        "runtime_expired",
        "observed",
      ].includes(status)
    ) {
      continue;
    }
    entries.push({
      action_id: stringField(entry, "action_id", decision.action_id),
      decision,
      resolution,
      outcome,
      first_seen_at: stringField(entry, "first_seen_at", stringField(entry, "last_seen_at", new Date().toISOString())),
      last_seen_at: stringField(entry, "last_seen_at", stringField(entry, "first_seen_at", new Date().toISOString())),
      seen_count: numberField(entry, "seen_count") || 0,
      pending: boolField(entry, "pending"),
      status: status as PermissionHistoryPayload["entries"][number]["status"],
    });
  }
  return {
    version: "v1",
    domain: "permission_history",
    count: numberField(payload, "count") || entries.length,
    entries,
  };
}

function approvalLabel(decision: CanonicalPermissionDecision): string {
  const sessionId = stringField(decision.metadata, "session_id", "none");
  const providerId = stringField(decision.metadata, "provider_id", "unknown");
  const toolCallId = stringField(decision.metadata, "tool_call_id", "none");
  return [
    `${decision.tool_name}`,
    decision.risk,
    decision.decision,
    `session ${sessionId}`,
    `provider ${providerId}`,
    `tool ${toolCallId}`,
  ].join(" | ");
}

function approvalEntries(approvalPane: ApprovalQueueState) {
  return approvalPane.order
    .map((actionId) => approvalPane.entriesByActionId[actionId])
    .filter((entry): entry is NonNullable<typeof entry> => Boolean(entry));
}

function selectedApprovalEntry(approvalPane: ApprovalQueueState) {
  const entries = approvalEntries(approvalPane);
  const pending = entries.filter((entry) => entry.pending);
  return approvalPane.selectedActionId ? approvalPane.entriesByActionId[approvalPane.selectedActionId] : pending[0] ?? entries[0];
}

function approvalStatusLabel(status: ApprovalEntryStatus): string {
  return status.replace(/_/g, " ");
}

export function approvalPaneToLines(approvalPane: ApprovalQueueState): TranscriptLine[] {
  const entries = approvalEntries(approvalPane);
  const pending = entries.filter((entry) => entry.pending);
  const resolved = entries.filter((entry) => !entry.pending && entry.resolution);
  const selected = selectedApprovalEntry(approvalPane);
  const bySession = new Map<string, number>();
  const byRisk = new Map<string, number>();
  for (const entry of pending) {
    const sessionId = stringField(entry.decision.metadata, "session_id", "none");
    bySession.set(sessionId, (bySession.get(sessionId) ?? 0) + 1);
    byRisk.set(entry.decision.risk, (byRisk.get(entry.decision.risk) ?? 0) + 1);
  }
  const lines = [
    "# Approval Queue",
    `Authority: ${approvalPane.historyBacked ? "history" : "provisional_live"}`,
    `Pending: ${pending.length}`,
    `Resolved: ${resolved.length}`,
    `Tracked: ${entries.length}`,
    "",
    "## Pending approvals",
  ];

  if (pending.length === 0) {
    lines.push("none");
  } else {
    for (const entry of pending.slice(0, 12)) {
      lines.push(`- ${entry.decision.action_id} | ${approvalLabel(entry.decision)}`);
      lines.push(`  ${entry.decision.rationale}`);
    }
  }

  lines.push("", "## Pending by session");
  if (bySession.size === 0) {
    lines.push("none");
  } else {
    for (const [sessionId, count] of Array.from(bySession.entries()).slice(0, 8)) {
      lines.push(`- ${sessionId}: ${count}`);
    }
  }

  lines.push("", "## Pending by risk");
  if (byRisk.size === 0) {
    lines.push("none");
  } else {
    for (const [risk, count] of Array.from(byRisk.entries()).slice(0, 8)) {
      lines.push(`- ${risk}: ${count}`);
    }
  }

  lines.push("", "## Selected");
  if (!selected) {
    lines.push("none");
    return toLines("system", lines.join("\n"));
  }

  const sessionId = stringField(selected.decision.metadata, "session_id", "none");
  const providerId = stringField(selected.decision.metadata, "provider_id", "unknown");
  const toolCallId = stringField(selected.decision.metadata, "tool_call_id", "none");
  lines.push(
    `Action: ${selected.decision.action_id}`,
    `Tool: ${selected.decision.tool_name}`,
    `Risk: ${selected.decision.risk}`,
    `Decision: ${selected.decision.decision}`,
    `Status: ${approvalStatusLabel(selected.status)}`,
    `Policy: ${selected.decision.policy_source}`,
    `Requires confirmation: ${selected.decision.requires_confirmation ? "yes" : "no"}`,
    `Command: ${selected.decision.command_prefix ?? "n/a"}`,
    `Session: ${sessionId}`,
    `Provider: ${providerId}`,
    `Tool call: ${toolCallId}`,
    `Seen: ${selected.seenCount} | first ${selected.firstSeenAt} | last ${selected.lastSeenAt}`,
    `Rationale: ${selected.decision.rationale}`,
  );
  if (selected.outcome) {
    const runtimeActionId = stringField(selected.outcome.metadata, "runtime_action_id");
    const runtimeEventId = stringField(selected.outcome.metadata, "runtime_event_id");
    lines.push(
      `Runtime outcome: ${selected.outcome.outcome}`,
      `Outcome at: ${selected.outcome.outcome_at}`,
      `Outcome source: ${selected.outcome.source}`,
    );
    if (runtimeActionId) {
      lines.push(`Runtime action id: ${runtimeActionId}`);
    }
    if (runtimeEventId) {
      lines.push(`Runtime event id: ${runtimeEventId}`);
    }
  }
  if (selected.resolution) {
    lines.push(
      `Resolution: ${selected.resolution.resolution}`,
      `Resolved at: ${selected.resolution.resolved_at}`,
      `Actor: ${selected.resolution.actor}`,
      `Enforcement: ${selected.resolution.enforcement_state}`,
      `Resolution note: ${selected.resolution.note ?? "none"}`,
    );
  }

  return toLines("system", lines.join("\n"));
}

export function approvalPaneToPreview(approvalPane: ApprovalQueueState): TabPreview | undefined {
  const entries = approvalEntries(approvalPane);
  if (entries.length === 0) {
    return undefined;
  }
  const pending = entries.filter((entry) => entry.pending);
  const resolved = entries.filter((entry) => !entry.pending && entry.resolution);
  const selected = selectedApprovalEntry(approvalPane);
  if (!selected) {
    return undefined;
  }
  return {
    Authority: approvalPane.historyBacked ? "history" : "provisional_live",
    Pending: String(pending.length),
    Resolved: String(resolved.length),
    Tracked: String(entries.length),
    Status: approvalStatusLabel(selected.status),
    Outcome: selected.outcome?.outcome ?? "none",
    Tool: selected.decision.tool_name,
    Risk: selected.decision.risk,
    Session: stringField(selected.decision.metadata, "session_id", "none"),
    Provider: stringField(selected.decision.metadata, "provider_id", "unknown"),
  };
}

export function sessionDetailFromEvent(event: Record<string, unknown>): SessionDetailPayload | undefined {
  const detail = sessionDetailPayloadRecord(event);
  const session = normalizeCanonicalSession(detail.session);
  if (!session) {
    return undefined;
  }
  return {
    session,
    replay_ok: boolField(detail, "replay_ok"),
    replay_issues: asStringArray(detail.replay_issues),
    compaction_preview: normalizeSessionCompactionPreview(detail.compaction_preview),
    recent_events: asRecordList(detail.recent_events)
      .map(normalizeCanonicalEventEnvelope)
      .filter((entry): entry is CanonicalEventEnvelope => Boolean(entry)),
    approval_history: permissionHistoryFromEvent({payload: detail.approval_history}),
  };
}

function sessionStatePayload(sessionPane: SessionPaneState): Record<string, unknown> {
  const catalog = sessionPane.catalog;
  if (!catalog) {
    return {payload: {count: 0, sessions: []}};
  }
  return {
    payload: {
      count: catalog.count,
      sessions: catalog.sessions,
    },
  };
}

function summarizeEventEnvelope(event: CanonicalEventEnvelope): string {
  const payload = event.payload ?? {};
  if (event.event_type === "text_delta" || event.event_type === "thinking_delta") {
    return stringField(payload, "content", event.event_type);
  }
  if (event.event_type === "tool_call_complete") {
    return `${stringField(payload, "tool_name", "tool")} ${stringField(payload, "arguments")}`.trim();
  }
  if (event.event_type === "tool_result") {
    return `${stringField(payload, "tool_name", "tool")}: ${stringField(payload, "content")}`.trim();
  }
  if (event.event_type === "session_end") {
    return boolField(payload, "success") ? "completed" : stringField(payload, "error_message", "failed");
  }
  if (event.event_type === "session_start") {
    return `${stringField(payload, "provider_id")}:${stringField(payload, "model", stringField(payload, "model_id"))}`.replace(/^:/, "");
  }
  return JSON.stringify(payload).slice(0, 120) || event.event_type;
}

export function sessionPaneToLines(sessionPane: SessionPaneState): TranscriptLine[] {
  const catalog = sessionPane.catalog;
  if (!catalog) {
    return toLines("system", "# Sessions\n\nCatalog loading...\nTyped session catalog has not arrived yet.");
  }

  const selectedSessionId = sessionPane.selectedSessionId ?? catalog.sessions[0]?.session.session_id;
  const selectedDetail = selectedSessionId ? sessionPane.detailsBySessionId[selectedSessionId] : undefined;
  const catalogLines = sessionCatalogToLines(sessionStatePayload(sessionPane)).map((line) => line.text);
  if (!selectedSessionId) {
    return toLines("system", catalogLines.join("\n"));
  }

  const selected = catalog.sessions.find((entry) => entry.session.session_id === selectedSessionId) ?? catalog.sessions[0];
  const lines = catalogLines.concat([
    "",
    "## Drilldown",
    `Selected: ${selectedSessionId}`,
    `Summary: ${selected ? sessionSummaryLine(selected.session as unknown as Record<string, unknown>, "none") : "none"}`,
  ]);

  if (!selectedDetail) {
    lines.push("Detail: pending");
    return toLines("system", lines.join("\n"));
  }

  lines.push(...sessionDetailToLines({payload: selectedDetail}).map((line) => line.text));
  if (selectedDetail.recent_events.length > 0) {
    lines.push("", "## Recent envelopes");
    for (const event of selectedDetail.recent_events.slice(-12)) {
      lines.push(`- ${event.event_type} | ${event.created_at} | ${summarizeEventEnvelope(event)}`);
    }
  }
  if (selectedDetail.approval_history && selectedDetail.approval_history.entries.length > 0) {
    lines.push("", "## Approval history");
    for (const entry of selectedDetail.approval_history.entries.slice(0, 12)) {
      lines.push(`- ${entry.action_id} | ${entry.decision.tool_name} | ${entry.status}`);
      if (entry.resolution) {
        lines.push(`  ${entry.resolution.resolution} by ${entry.resolution.actor} | ${entry.resolution.enforcement_state}`);
      } else {
        lines.push(`  ${entry.decision.rationale}`);
      }
      if (entry.outcome) {
        const runtimeActionId = stringField(entry.outcome.metadata, "runtime_action_id");
        const runtimeEventId = stringField(entry.outcome.metadata, "runtime_event_id");
        const traceBits = [runtimeActionId, runtimeEventId].filter((value) => value.length > 0).join(" | ");
        lines.push(
          `  outcome ${entry.outcome.outcome} | ${entry.outcome.source} | ${entry.outcome.outcome_at}${
            traceBits ? ` | ${traceBits}` : ""
          }`,
        );
      }
    }
  }
  return toLines("system", lines.join("\n"));
}

export function sessionPaneToPreview(sessionPane: SessionPaneState): TabPreview | undefined {
  const catalog = sessionPane.catalog;
  if (!catalog) {
    return undefined;
  }
  const preview = sessionCatalogToPreview(sessionStatePayload(sessionPane));
  const selectedSessionId = sessionPane.selectedSessionId ?? catalog.sessions[0]?.session.session_id;
  const selectedDetail = selectedSessionId ? sessionPane.detailsBySessionId[selectedSessionId] : undefined;
  if (!selectedDetail) {
    return preview;
  }
  return {
    ...preview,
    Selected: selectedDetail.session.session_id,
    Replay: selectedDetail.replay_ok ? "ok" : summarizeReplayState(false, selectedDetail.replay_issues),
    Compaction: `${selectedDetail.compaction_preview.event_count} events | ${compactableRatioLabel(selectedDetail.compaction_preview.compactable_ratio)}`,
    "Recent envelopes": String(selectedDetail.recent_events.length),
    Approvals: String(selectedDetail.approval_history?.count ?? 0),
  };
}

export function sessionBootstrapToLines(payload: Record<string, unknown>): TranscriptLine[] {
  const prompt = String(payload.prompt ?? "");
  const activeTab = String(payload.active_tab ?? "chat");
  const selectedProvider = String(payload.selected_provider ?? "codex");
  const selectedModel = String(payload.selected_model ?? "gpt-5.4");
  const routingStrategy = String(payload.routing_strategy ?? "responsive");
  const intent =
    typeof payload.intent === "object" && payload.intent !== null ? (payload.intent as Record<string, unknown>) : {};
  const workspacePreview =
    typeof payload.workspace_preview === "object" && payload.workspace_preview !== null
      ? (payload.workspace_preview as Record<string, unknown>)
      : {};
  const runtimePreview =
    typeof payload.runtime_preview === "object" && payload.runtime_preview !== null
      ? (payload.runtime_preview as Record<string, unknown>)
      : {};
  const repoGuidance = String(payload.repo_guidance ?? "").trim();
  const sessionContextHint = String(payload.session_context_hint ?? "").trim();
  const workingMemory = String(payload.working_memory ?? "").trim();

  return toLines(
    "system",
    [
      "# Session Bootstrap",
      `Prompt: ${prompt}`,
      `Intent: ${summarizeIntent(intent)}`,
      `Active tab: ${activeTab}`,
      `Route: ${selectedProvider}:${selectedModel}`,
      `Strategy: ${routingStrategy}`,
      `Repo root: ${previewValue(workspacePreview, "Repo root")}`,
      `Branch: ${previewValue(workspacePreview, "Branch")}`,
      `Repo risk: ${previewValue(workspacePreview, "Repo risk")}`,
      `Dirty: ${previewValue(workspacePreview, "Dirty")}`,
      `Runtime activity: ${previewValue(runtimePreview, "Runtime activity", "none")}`,
      `Artifact state: ${previewValue(runtimePreview, "Artifact state", "none")}`,
      `Repo guidance: ${repoGuidance ? "loaded" : "missing"}`,
      `Session hint: ${sessionContextHint ? sessionContextHint : "none"}`,
      `Working memory: ${workingMemory ? "loaded" : "none"}`,
    ].join("\n"),
  );
}

export function sessionBootstrapToPreview(payload: Record<string, unknown>): TabPreview {
  const intent =
    typeof payload.intent === "object" && payload.intent !== null ? (payload.intent as Record<string, unknown>) : {};
  const workspacePreview =
    typeof payload.workspace_preview === "object" && payload.workspace_preview !== null
      ? (payload.workspace_preview as Record<string, unknown>)
      : {};
  const runtimePreview =
    typeof payload.runtime_preview === "object" && payload.runtime_preview !== null
      ? (payload.runtime_preview as Record<string, unknown>)
      : {};
  return {
    Intent: summarizeIntent(intent),
    Route: `${String(payload.selected_provider ?? "codex")}:${String(payload.selected_model ?? "gpt-5.4")}`,
    Strategy: String(payload.routing_strategy ?? "responsive"),
    "Repo root": previewValue(workspacePreview, "Repo root"),
    Branch: previewValue(workspacePreview, "Branch"),
    "Repo risk": previewValue(workspacePreview, "Repo risk"),
    Dirty: previewValue(workspacePreview, "Dirty"),
    "Runtime activity": previewValue(runtimePreview, "Runtime activity", "none"),
    "Artifact state": previewValue(runtimePreview, "Artifact state", "none"),
    "Repo guidance": String(payload.repo_guidance ?? "").trim() ? "loaded" : "missing",
    "Session hint": String(payload.session_context_hint ?? "").trim() || "none",
    "Working memory": String(payload.working_memory ?? "").trim() ? "loaded" : "none",
  };
}

export function commandGraphToLines(payload: Record<string, unknown>): TranscriptLine[] {
  const graph =
    typeof payload.graph === "object" && payload.graph !== null ? (payload.graph as Record<string, unknown>) : payload;
  const categories = (typeof graph.categories === "object" && graph.categories !== null
    ? (graph.categories as Record<string, unknown>)
    : {}) as Record<string, unknown>;
  const lines = [
    "# Command Graph",
    `Command count: ${String(graph.count ?? "0")}`,
    `Async commands: ${String(graph.async_count ?? "0")}`,
    "",
    "## Categories",
  ];
  for (const [name, value] of Object.entries(categories)) {
    const commands = Array.isArray(value) ? value.map(String) : [];
    lines.push(`- ${name}: ${commands.join(", ") || "none"}`);
  }
  const asyncCommands = Array.isArray(graph.async_commands) ? graph.async_commands.map(String) : [];
  lines.push("", "## Async lanes", asyncCommands.join(", ") || "none");
  return toLines("system", lines.join("\n"));
}

export function commandGraphToPreview(payload: Record<string, unknown>): TabPreview {
  const graph =
    typeof payload.graph === "object" && payload.graph !== null ? (payload.graph as Record<string, unknown>) : payload;
  const categories = (typeof graph.categories === "object" && graph.categories !== null
    ? (graph.categories as Record<string, unknown>)
    : {}) as Record<string, unknown>;
  const commandCategories = Object.keys(categories);
  return {
    Commands: String(graph.count ?? "0"),
    "Async lanes": String(graph.async_count ?? "0"),
    Categories: commandCategories.join(", ") || "none",
    "Chat commands": Array.isArray(categories.chat) ? categories.chat.map(String).join(", ") : "none",
  };
}

export function operatorSnapshotToLines(payload: Record<string, unknown>): TranscriptLine[] {
  const snapshot =
    typeof payload.snapshot === "object" && payload.snapshot !== null ? (payload.snapshot as Record<string, unknown>) : payload;
  const overview =
    typeof snapshot.overview === "object" && snapshot.overview !== null
      ? (snapshot.overview as Record<string, unknown>)
      : {};
  const runs = Array.isArray(snapshot.runs) ? snapshot.runs : [];
  const actions = Array.isArray(snapshot.actions) ? snapshot.actions : [];
  const lines = [
    "# Operator Snapshot",
    `Runtime DB: ${String(snapshot.runtime_db ?? "unavailable")}`,
  ];
  const error = String(snapshot.error ?? "").trim();
  if (error) {
    lines.push(`Error: ${error}`);
    return toLines("error", lines.join("\n"));
  }
  lines.push(
    `Sessions: ${String(overview.sessions ?? 0)}`,
    `Claims: ${String(overview.claims ?? 0)} | active ${String(overview.active_claims ?? 0)} | acked ${String(overview.acknowledged_claims ?? 0)}`,
    `Runs: ${String(overview.runs ?? 0)} | active ${String(overview.active_runs ?? 0)}`,
    `Artifacts: ${String(overview.artifacts ?? 0)} | promoted facts ${String(overview.promoted_facts ?? 0)}`,
    `Context bundles: ${String(overview.context_bundles ?? 0)} | operator actions ${String(overview.operator_actions ?? 0)}`,
    "",
    "## Active runs",
  );
  if (runs.length === 0) {
    lines.push("none");
  } else {
    for (const run of runs.slice(0, 8)) {
      const record = typeof run === "object" && run !== null ? (run as Record<string, unknown>) : {};
      lines.push(
        `- ${String(record.assigned_to ?? "?")} | ${String(record.status ?? "?")} | task ${String(record.task_id ?? "").slice(0, 18)} | run ${String(record.run_id ?? "").slice(0, 12)}`,
      );
    }
  }
  lines.push("", "## Recent operator actions");
  if (actions.length === 0) {
    lines.push("none");
  } else {
    for (const action of actions.slice(0, 8)) {
      const record = typeof action === "object" && action !== null ? (action as Record<string, unknown>) : {};
      lines.push(
        `- ${String(record.action_name ?? "?")} by ${String(record.actor ?? "?")} | task ${String(record.task_id ?? "-").slice(0, 18)} | ${String(record.reason ?? "no reason")}`,
      );
    }
  }
  return toLines("system", lines.join("\n"));
}

export function operatorSnapshotToPreview(payload: Record<string, unknown>): TabPreview {
  const snapshot =
    typeof payload.snapshot === "object" && payload.snapshot !== null ? (payload.snapshot as Record<string, unknown>) : payload;
  const overview =
    typeof snapshot.overview === "object" && snapshot.overview !== null
      ? (snapshot.overview as Record<string, unknown>)
      : {};
  const runs = Array.isArray(snapshot.runs) ? snapshot.runs : [];
  const actions = Array.isArray(snapshot.actions) ? snapshot.actions : [];
  const runtimeActivity = [
    `Sessions=${String(overview.sessions ?? 0)}`,
    `Claims=${String(overview.claims ?? 0)}`,
    `ActiveClaims=${String(overview.active_claims ?? 0)}`,
    `AckedClaims=${String(overview.acknowledged_claims ?? 0)}`,
    `Runs=${String(overview.runs ?? 0)}`,
    `ActiveRuns=${String(overview.active_runs ?? 0)}`,
  ].join("  ");
  const artifactState = [
    `Artifacts=${String(overview.artifacts ?? 0)}`,
    `PromotedFacts=${String(overview.promoted_facts ?? 0)}`,
    `ContextBundles=${String(overview.context_bundles ?? 0)}`,
    `OperatorActions=${String(overview.operator_actions ?? 0)}`,
  ].join("  ");
  const activeRunsDetail =
    runs
      .slice(0, 3)
      .map((run) => {
        const record = typeof run === "object" && run !== null ? (run as Record<string, unknown>) : {};
        return `${String(record.assigned_to ?? "?")} (${String(record.status ?? "?")}) task ${String(record.task_id ?? "-").slice(0, 18)}`;
      })
      .join("; ") || "none";
  const recentOperatorActions =
    actions
      .slice(0, 3)
      .map((action) => {
        const record = typeof action === "object" && action !== null ? (action as Record<string, unknown>) : {};
        return `${String(record.action_name ?? "?")} by ${String(record.actor ?? "?")} (${String(record.reason ?? "no reason")})`;
      })
      .join("; ") || "none";
  return {
    "Runtime DB": String(snapshot.runtime_db ?? "unavailable"),
    "Session state": [
      `${String(overview.sessions ?? 0)} sessions`,
      `${String(overview.claims ?? 0)} claims`,
      `${String(overview.active_claims ?? 0)} active claims`,
      `${String(overview.acknowledged_claims ?? 0)} acked claims`,
    ].join(" | "),
    "Run state": [`${String(overview.runs ?? 0)} runs`, `${String(overview.active_runs ?? 0)} active runs`].join(" | "),
    "Active runs detail": activeRunsDetail,
    "Context state": [
      `${String(overview.artifacts ?? 0)} artifacts`,
      `${String(overview.promoted_facts ?? 0)} promoted facts`,
      `${String(overview.context_bundles ?? 0)} context bundles`,
      `${String(overview.operator_actions ?? 0)} operator actions`,
    ].join(" | "),
    "Recent operator actions": recentOperatorActions,
    "Runtime activity": runtimeActivity,
    "Artifact state": artifactState,
    Sessions: String(overview.sessions ?? 0),
    "Active claims": String(overview.active_claims ?? 0),
    "Active runs": String(overview.active_runs ?? 0),
    Artifacts: String(overview.artifacts ?? 0),
    "Recent actions": String(actions.length),
    Agents: runs
      .slice(0, 3)
      .map((run) => {
        const record = typeof run === "object" && run !== null ? (run as Record<string, unknown>) : {};
        return `${String(record.assigned_to ?? "?")} (${String(record.status ?? "?")})`;
      })
      .join("; ") || "none",
    "Runtime summary": summarizeRuntimeSummary(
      String(snapshot.runtime_db ?? "unavailable"),
      [
        `${String(overview.sessions ?? 0)} sessions`,
        `${String(overview.claims ?? 0)} claims`,
        `${String(overview.active_claims ?? 0)} active claims`,
        `${String(overview.acknowledged_claims ?? 0)} acked claims`,
      ].join(" | "),
      [`${String(overview.runs ?? 0)} runs`, `${String(overview.active_runs ?? 0)} active runs`].join(" | "),
      [
        `${String(overview.artifacts ?? 0)} artifacts`,
        `${String(overview.promoted_facts ?? 0)} promoted facts`,
        `${String(overview.context_bundles ?? 0)} context bundles`,
        `${String(overview.operator_actions ?? 0)} operator actions`,
      ].join(" | "),
    ),
  };
}

export function modelPolicyToLines(payload: Record<string, unknown>): TranscriptLine[] {
  const routingPayload = routingDecisionPayloadFromEvent(payload);
  if (routingPayload) {
    const decision = routingPayload.decision;
    const metadata = asRecord(decision.metadata);
    const lines = [
      "# Model Policy",
      `Active: ${stringField(metadata, "active_label", decision.model_id || "unknown")}`,
      `Route: ${decision.route_id}`,
      `Strategy: ${decision.strategy}`,
      `Default route: ${stringField(metadata, "default_route", "unknown")}`,
      "",
      "## Fallback chain",
    ];
    if (routingPayload.fallback_targets.length === 0) {
      lines.push("none");
    } else {
      for (const entry of routingPayload.fallback_targets.slice(0, 6)) {
        lines.push(`- ${stringField(entry, "label", stringField(entry, "alias", "?"))} [${stringField(entry, "provider", "?")}]`);
      }
    }
    lines.push("", "## Targets");
    for (const entry of routingPayload.targets) {
      lines.push(`- ${stringField(entry, "alias", "?")} -> ${stringField(entry, "label", "?")} (${stringField(entry, "provider", "?")}:${stringField(entry, "model", "?")})`);
    }
    return toLines("system", lines.join("\n"));
  }
  const policy =
    typeof payload.policy === "object" && payload.policy !== null ? (payload.policy as Record<string, unknown>) : payload;
  const lines = [
    "# Model Policy",
    `Active: ${String(policy.active_label ?? policy.selected_model ?? "unknown")}`,
    `Route: ${String(policy.selected_route ?? "unknown")}`,
    `Strategy: ${String(policy.strategy ?? "responsive")}`,
    `Default route: ${String(policy.default_route ?? "unknown")}`,
    "",
    "## Fallback chain",
  ];
  const chain = Array.isArray(policy.fallback_chain) ? policy.fallback_chain : [];
  if (chain.length === 0) {
    lines.push("none");
  } else {
    for (const entry of chain.slice(0, 6)) {
      const record = typeof entry === "object" && entry !== null ? (entry as Record<string, unknown>) : {};
      lines.push(`- ${String(record.label ?? record.alias ?? "?")} [${String(record.provider ?? "?")}]`);
    }
  }
  lines.push("", "## Targets");
  const targets = Array.isArray(policy.targets) ? policy.targets : [];
  for (const entry of targets) {
    const record = typeof entry === "object" && entry !== null ? (entry as Record<string, unknown>) : {};
    lines.push(
      `- ${String(record.alias ?? "?")} -> ${String(record.label ?? "?")} (${String(record.provider ?? "?")}:${String(record.model ?? "?")})`,
    );
  }
  return toLines("system", lines.join("\n"));
}

export function modelPolicyToPreview(payload: Record<string, unknown>): TabPreview {
  const routingPayload = routingDecisionPayloadFromEvent(payload);
  if (routingPayload) {
    const decision = routingPayload.decision;
    const metadata = asRecord(decision.metadata);
    return {
      Active: stringField(metadata, "active_label", decision.model_id || "unknown"),
      Route: decision.route_id,
      Strategy: decision.strategy,
      "Default route": stringField(metadata, "default_route", "unknown"),
      Fallbacks: String(routingPayload.fallback_targets.length),
      Targets: String(routingPayload.targets.length),
    };
  }
  const policy =
    typeof payload.policy === "object" && payload.policy !== null ? (payload.policy as Record<string, unknown>) : payload;
  const chain = Array.isArray(policy.fallback_chain) ? policy.fallback_chain : [];
  return {
    Active: String(policy.active_label ?? policy.selected_model ?? "unknown"),
    Route: String(policy.selected_route ?? "unknown"),
    Strategy: String(policy.strategy ?? "responsive"),
    "Default route": String(policy.default_route ?? "unknown"),
    Fallbacks: String(chain.length),
    Targets: String(Array.isArray(policy.targets) ? policy.targets.length : 0),
  };
}

export function agentRoutesToLines(payload: Record<string, unknown>): TranscriptLine[] {
  const typedPayload = agentRoutesPayloadFromEvent(payload);
  const routes = typedPayload ?? (
    typeof payload.routes === "object" && payload.routes !== null ? (payload.routes as Record<string, unknown>) : payload
  );
  const routeItems = Array.isArray(routes.routes) ? routes.routes : [];
  const openclaw =
    typeof routes.openclaw === "object" && routes.openclaw !== null ? (routes.openclaw as Record<string, unknown>) : {};
  const lines = ["# Agent Routes", "", "## Route profiles"];
  for (const entry of routeItems) {
    const record = typeof entry === "object" && entry !== null ? (entry as Record<string, unknown>) : {};
    lines.push(
      `- ${String(record.intent ?? "?")} -> ${String(record.provider ?? "?")}:${String(record.model_alias ?? "?")} | effort ${String(record.reasoning ?? "?")} | role ${String(record.role ?? "?")}`,
    );
  }
  lines.push(
    "",
    "## OpenClaw",
    `Present: ${String(openclaw.present ?? false)}`,
    `Readable: ${String(openclaw.readable ?? false)}`,
    `Agents: ${String(openclaw.agents_count ?? 0)}`,
    `Providers: ${Array.isArray(openclaw.providers) ? openclaw.providers.map(String).join(", ") || "none" : "none"}`,
  );
  return toLines("system", lines.join("\n"));
}

export function agentRoutesToPreview(payload: Record<string, unknown>): TabPreview {
  const typedPayload = agentRoutesPayloadFromEvent(payload);
  const routes = typedPayload ?? (
    typeof payload.routes === "object" && payload.routes !== null ? (payload.routes as Record<string, unknown>) : payload
  );
  const routeItems = Array.isArray(routes.routes) ? routes.routes : [];
  const openclaw =
    typeof routes.openclaw === "object" && routes.openclaw !== null ? (routes.openclaw as Record<string, unknown>) : {};
  return {
    Routes: String(routeItems.length),
    "OpenClaw agents": String(openclaw.agents_count ?? 0),
    Providers: Array.isArray(openclaw.providers) ? openclaw.providers.map(String).join(", ") || "none" : "none",
    "Primary route": routeItems.length > 0 ? String((routeItems[0] as Record<string, unknown>).intent ?? "none") : "none",
  };
}

export function evolutionSurfaceToLines(payload: Record<string, unknown>): TranscriptLine[] {
  const surface =
    typeof payload.surface === "object" && payload.surface !== null ? (payload.surface as Record<string, unknown>) : payload;
  const domains = Array.isArray(surface.domains) ? surface.domains : [];
  const entries = Array.isArray(surface.entry_commands) ? surface.entry_commands : [];
  const principles = Array.isArray(surface.principles) ? surface.principles : [];
  const lines = ["# Evolution Surface", "", "## Cascade domains"];
  for (const entry of domains) {
    const record = typeof entry === "object" && entry !== null ? (entry as Record<string, unknown>) : {};
    lines.push(
      `- ${String(record.name ?? "?")} | threshold ${String(record.fitness_threshold ?? "?")} | max_iter ${String(record.max_iterations ?? "?")} | max_duration ${String(record.max_duration_seconds ?? "?")}s`,
    );
  }
  lines.push("", "## Entry commands");
  for (const entry of entries) {
    lines.push(`- ${String(entry)}`);
  }
  lines.push("", "## Principles");
  for (const principle of principles) {
    lines.push(`- ${String(principle)}`);
  }
  return toLines("system", lines.join("\n"));
}

export function evolutionSurfaceToPreview(payload: Record<string, unknown>): TabPreview {
  const surface =
    typeof payload.surface === "object" && payload.surface !== null ? (payload.surface as Record<string, unknown>) : payload;
  const domains = Array.isArray(surface.domains) ? surface.domains : [];
  const entries = Array.isArray(surface.entry_commands) ? surface.entry_commands : [];
  return {
    Domains: String(domains.length),
    "Entry commands": entries.map(String).join(", ") || "none",
    "Primary domain": domains.length > 0 ? String((domains[0] as Record<string, unknown>).name ?? "none") : "none",
  };
}

export function eventToTabPatch(event: Record<string, unknown>): {tabId: string; lines: TranscriptLine[]}[] {
  const type = String(event.type ?? "");

  if (type === "bridge.ready") {
    return [{tabId: "runtime", lines: [makeLine("system", "bridge process ready")]}];
  }
  if (type === "handshake.result") {
    return [
      {tabId: "runtime", lines: [makeLine("system", "bridge handshake complete")]},
    ];
  }
  if (type === "command.result" || (type === "action.result" && String(event.action_type ?? "") === "command.run")) {
    const output = String(event.output ?? "").trim();
    const targetPane = resolveCommandTargetPane(event, "control");
    if (!output) {
      return [];
    }
    if (targetPane === "repo" && isWorkspaceSnapshotContent(output)) {
      return [];
    }
    if ((targetPane === "control" || targetPane === "runtime") && (output.includes("# Runtime") || /^(Runtime DB|Durable state):\s+/m.test(output))) {
      return [];
    }
    return [{tabId: targetPane, lines: [makeLine("system", output)]}];
  }
  if (type === "workspace.snapshot.result") {
    return [];
  }
  if (type === "session.catalog.result") {
    return sessionCatalogFromEvent(event) ? [] : String(event.content ?? "").trim() ? [{tabId: "sessions", lines: [makeLine("system", String(event.content ?? "").trim())]}] : [];
  }
  if (type === "session.detail.result") {
    return sessionDetailFromEvent(event) ? [] : String(event.content ?? "").trim() ? [{tabId: "sessions", lines: [makeLine("system", String(event.content ?? "").trim())]}] : [];
  }
  if (type === "session.ack") {
    return [
      {
        tabId: "runtime",
        lines: [
          makeLine(
            "system",
            `session ${String(event.session_id ?? "")} via ${String(event.provider ?? "")}:${String(event.model ?? "")}`,
          ),
        ],
      },
    ];
  }
  if (type === "text_delta" || type === "text_complete") {
    return [{tabId: "chat", lines: [makeLine("assistant", String(event.content ?? ""))]}];
  }
  if (type === "thinking_delta" || type === "thinking_complete") {
    return [{tabId: "thinking", lines: [makeLine("thinking", String(event.content ?? ""))]}];
  }
  if (type === "permission.decision") {
    const decision = permissionDecisionFromEvent(event);
    if (!decision) {
      return [];
    }
    return [
      {
        tabId: "tools",
        lines: [
          makeLine(
            decision.decision === "require_approval" ? "tool" : "system",
            `approval ${decision.action_id} | ${decision.tool_name} | ${decision.risk} | ${decision.rationale}`,
          ),
        ],
      },
    ];
  }
  if (type === "permission.resolution") {
    const resolution = permissionResolutionFromEvent(event);
    if (!resolution) {
      return [];
    }
    return [
      {
        tabId: "tools",
        lines: [
          makeLine(
            "system",
            `resolution ${resolution.action_id} | ${resolution.resolution} | ${resolution.enforcement_state}`,
          ),
        ],
      },
    ];
  }
  if (type === "tool_call_complete") {
    return [
      {
        tabId: "tools",
        lines: [
          makeLine(
            "tool",
            `⠋ ${summarizeTool(String(event.arguments ?? ""), String(event.tool_name ?? "tool"))}`,
          ),
        ],
      },
    ];
  }
  if (type === "tool_result") {
    return [
      {
        tabId: "tools",
        lines: [makeLine("tool", `✓ ${String(event.tool_name ?? "tool")}: ${String(event.content ?? "").trim()}`)],
      },
    ];
  }
  if (type === "task_started" || type === "task_progress" || type === "task_complete") {
    return [{tabId: "timeline", lines: [makeLine("system", JSON.stringify(event))]}];
  }
  if (type === "session_end") {
    const ok = Boolean(event.success);
    return [
      {
        tabId: "runtime",
        lines: [makeLine(ok ? "system" : "error", ok ? "session complete" : `session failed: ${String(event.error_message ?? "unknown error")}`)],
      },
    ];
  }
  if (type === "error" || type === "bridge.error") {
    return [
      {tabId: "runtime", lines: [makeLine("error", String(event.message ?? event.code ?? "error"))]},
    ];
  }
  return [];
}

export function workspaceSnapshotToLines(content: string): TranscriptLine[] {
  return workspacePreviewToLines(workspaceSnapshotToPreview(content));
}

export function workspacePreviewToLines(preview: TabPreview): TranscriptLine[] {
  return toLines("system", buildWorkspaceSnapshotPreludeFromPreview(preview).join("\n"));
}

export function runtimeSnapshotToLines(
  content: string,
  summary: SupervisorControlState | null = null,
  now: Date = new Date(),
): TranscriptLine[] {
  return toLines(
    "system",
    [...buildRuntimeSnapshotPrelude(content, summary, now), ...buildSupervisorPrelude(summary), ...content.split("\n")].join("\n"),
  );
}

export function runtimePreviewToLines(
  preview: TabPreview,
  summary: SupervisorControlState | null = null,
  now: Date = new Date(),
): TranscriptLine[] {
  const supervisorPrelude = summary ? buildSupervisorPrelude(summary) : buildSupervisorPreludeFromPreview(preview);
  return toLines("system", [...buildRuntimeSnapshotPreludeFromPreview(preview, now), ...supervisorPrelude].join("\n"));
}

export function buildBridgeTabs(): TabSpec[] {
  return [
    {id: "repo", title: "Repo", kind: "repo", closable: false, lines: []},
    {id: "commands", title: "Commands", kind: "commands", closable: false, lines: []},
    {id: "models", title: "Models", kind: "models", closable: false, lines: []},
    {id: "ontology", title: "Ontology", kind: "ontology", closable: false, lines: []},
    {id: "control", title: "Control", kind: "control", closable: false, lines: []},
    {id: "sessions", title: "Sessions", kind: "sessions", closable: false, lines: []},
    {id: "approvals", title: "Approvals", kind: "approvals", closable: false, lines: []},
    {id: "agents", title: "Agents", kind: "agents", closable: false, lines: []},
    {id: "evolution", title: "Evolution", kind: "evolution", closable: false, lines: []},
    {id: "thinking", title: "Thinking", kind: "thinking", closable: false, lines: []},
    {id: "tools", title: "Tools", kind: "tools", closable: false, lines: []},
    {id: "timeline", title: "Timeline", kind: "timeline", closable: false, lines: []},
  ];
}

export function buildBridgeOutline(): OutlineItem[] {
  return [
    {id: "toc-repo", label: "Repo", depth: 1, targetTabId: "repo"},
    {id: "toc-commands", label: "Commands", depth: 1, targetTabId: "commands"},
    {id: "toc-models", label: "Models", depth: 1, targetTabId: "models"},
    {id: "toc-ontology", label: "Ontology", depth: 1, targetTabId: "ontology"},
    {id: "toc-control", label: "Control", depth: 1, targetTabId: "control"},
    {id: "toc-sessions", label: "Sessions", depth: 1, targetTabId: "sessions"},
    {id: "toc-approvals", label: "Approvals", depth: 1, targetTabId: "approvals"},
    {id: "toc-agents", label: "Agents", depth: 1, targetTabId: "agents"},
    {id: "toc-evolution", label: "Evolution", depth: 1, targetTabId: "evolution"},
    {id: "toc-thinking", label: "Thinking", depth: 1, targetTabId: "thinking"},
    {id: "toc-tools", label: "Tools", depth: 1, targetTabId: "tools"},
    {id: "toc-timeline", label: "Timeline", depth: 1, targetTabId: "timeline"},
  ];
}

export function outlineFromTabs(tabs: TabSpec[]): OutlineItem[] {
  return tabs.map((tab, index) => ({
    id: `outline-${tab.id}-${index}`,
    label: tab.title,
    depth: 1,
    targetTabId: tab.id,
  }));
}
