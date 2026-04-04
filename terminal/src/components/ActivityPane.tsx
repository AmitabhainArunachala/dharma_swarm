import React from "react";
import {Box, Text} from "ink";

import type {ActivityEntry, ActivityFeedState, PaneKind} from "../types";
import {THEME} from "../theme";

type Props = {
  title: string;
  paneKind: PaneKind;
  feed: ActivityFeedState;
  scrollOffset?: number;
  windowSize?: number;
};

function visibleWindow<T>(items: T[], scrollOffset: number, windowSize: number): T[] {
  const total = items.length;
  const end = Math.max(total - scrollOffset, 0);
  const start = Math.max(end - windowSize, 0);
  return items.slice(start, end);
}

type ActivityGroup = {
  key: string;
  label: string;
  entries: ActivityEntry[];
};

function activityEntriesForPane(paneKind: PaneKind, entries: ActivityEntry[]): ActivityEntry[] {
  if (paneKind === "thinking") {
    return entries.filter((entry) => entry.kind === "thinking" || entry.kind === "pivot" || entry.kind === "error");
  }
  if (paneKind === "tools") {
    return entries.filter((entry) => entry.kind === "tool" || entry.kind === "approval" || entry.kind === "error");
  }
  if (paneKind === "timeline") {
    return entries.filter((entry) => entry.kind === "task" || entry.kind === "status" || entry.kind === "pivot" || entry.kind === "error");
  }
  return entries;
}

function colorForKind(kind: ActivityEntry["kind"]): string {
  switch (kind) {
    case "thinking":
      return THEME.stone;
    case "pivot":
      return THEME.parchment;
    case "tool":
      return THEME.moss;
    case "approval":
      return THEME.vermilion;
    case "task":
      return THEME.wave;
    case "error":
      return THEME.vermilion;
    default:
      return THEME.pine;
  }
}

function labelForKind(kind: ActivityEntry["kind"]): string {
  switch (kind) {
    case "thinking":
      return "Reasoning";
    case "pivot":
      return "Pivot";
    case "tool":
      return "Tool";
    case "approval":
      return "Approval";
    case "task":
      return "Task";
    case "error":
      return "Error";
    default:
      return "Status";
  }
}

function glyphForEntry(entry: ActivityEntry): string {
  if (entry.kind === "error") {
    return "!";
  }
  if (entry.phase === "failed") {
    return "!";
  }
  if (entry.phase === "complete") {
    return "✓";
  }
  if (entry.phase === "queued") {
    return "○";
  }
  if (entry.phase === "running") {
    return "⠋";
  }
  return "•";
}

function phaseLabel(entry: ActivityEntry): string {
  switch (entry.phase) {
    case "queued":
      return "queued";
    case "running":
      return "running";
    case "failed":
      return "failed";
    default:
      return "complete";
  }
}

function rawLines(entry: ActivityEntry): string[] {
  if (!entry.raw) {
    return [];
  }
  return JSON.stringify(entry.raw, null, 2)
    .split("\n")
    .map((line) => line.trimEnd());
}

function compactDetail(entry: ActivityEntry): string | undefined {
  const line = entry.detail?.find((candidate) => candidate.trim().length > 0);
  return line ? line.replace(/\s+/g, " ").trim() : undefined;
}

function groupLabel(entry: ActivityEntry): string {
  if (!entry.correlationId) {
    return "context";
  }
  if (entry.kind === "tool") {
    return `tool ${entry.correlationId}`;
  }
  if (entry.kind === "approval") {
    return `approval ${entry.correlationId}`;
  }
  if (entry.kind === "task") {
    return `task ${entry.correlationId}`;
  }
  return `thread ${entry.correlationId}`;
}

function groupEntries(entries: ActivityEntry[]): ActivityGroup[] {
  const groups: ActivityGroup[] = [];
  for (const entry of entries) {
    const key = entry.correlationId ? `${entry.kind}:${entry.correlationId}` : entry.id;
    const existing = groups.find((group) => group.key === key);
    if (existing) {
      existing.entries.push(entry);
      continue;
    }
    groups.push({
      key,
      label: groupLabel(entry),
      entries: [entry],
    });
  }
  return groups;
}

export function activityRowCount(paneKind: PaneKind, feed: ActivityFeedState): number {
  const groups = groupEntries(activityEntriesForPane(paneKind, feed.entries));
  return groups.reduce((total, group) => {
    const shownEntries = feed.visibilityMode === "expanded" ? group.entries : group.entries.slice(0, 1);
    const rows = shownEntries.reduce((entryTotal, entry) => {
      const detailCount = feed.visibilityMode === "expanded" ? (entry.detail?.length ?? 0) + 1 : compactDetail(entry) ? 1 : 0;
      const rawCount = feed.showRaw ? rawLines(entry).length : 0;
      return entryTotal + 2 + detailCount + rawCount + 1;
    }, 0);
    return total + 1 + rows;
  }, 0);
}

export function ActivityPane({title, paneKind, feed, scrollOffset = 0, windowSize = 24}: Props): React.ReactElement {
  const entries = activityEntriesForPane(paneKind, feed.entries);
  const groups = groupEntries(entries);
  const visible = visibleWindow(groups, scrollOffset, windowSize);

  return (
    <Box flexGrow={1} flexDirection="column" borderStyle="round" borderColor={THEME.indigo} paddingX={1}>
      <Text color={THEME.wave} bold>{title}</Text>
      <Text color={THEME.stone}>
        {entries.length} items | {groups.length} threads | {feed.visibilityMode} detail | raw {feed.showRaw ? "on" : "off"}
      </Text>
      {visible.length === 0 ? (
        <Text color={THEME.stone}>No activity yet.</Text>
      ) : (
        visible.map((group) => (
          <Box key={group.key} flexDirection="column" marginTop={1}>
            <Text color={THEME.wave} bold>
              ▾ {group.label} <Text color={THEME.stone}>({group.entries.length})</Text>
            </Text>
            {(feed.visibilityMode === "expanded" ? group.entries : group.entries.slice(0, 1)).map((entry) => (
              <Box key={entry.id} flexDirection="column" marginTop={1} borderStyle="round" borderColor={colorForKind(entry.kind)} paddingX={1}>
                <Text color={colorForKind(entry.kind)} bold>
                  {glyphForEntry(entry)} {labelForKind(entry.kind)}
                  <Text color={THEME.foam}> {"  "}{entry.title}</Text>
                </Text>
                <Text color={THEME.stone}>
                  {phaseLabel(entry)}
                  {entry.timestamp ? ` | ${entry.timestamp}` : ""}
                  {entry.summary ? ` | ${entry.summary}` : ""}
                </Text>
                {feed.visibilityMode === "expanded"
                  ? entry.detail?.map((line, index) => (
                      <Text key={`${entry.id}-detail-${index}`} color={THEME.stone}>
                        {"  "}└ {line}
                      </Text>
                    ))
                  : compactDetail(entry) ? (
                      <Text color={THEME.stone}>
                        {"  "}└ {compactDetail(entry)}
                      </Text>
                    ) : null}
                {feed.showRaw && rawLines(entry).map((line, index) => (
                  <Text key={`${entry.id}-raw-${index}`} color={THEME.river}>
                    {"    "}{line}
                  </Text>
                ))}
              </Box>
            ))}
          </Box>
        ))
      )}
    </Box>
  );
}
