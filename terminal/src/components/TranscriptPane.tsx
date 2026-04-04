import React from "react";
import {Box, Text} from "ink";

import type {TranscriptLine} from "../types";
import {formatTranscriptLine} from "../transcriptFormatting";
import {THEME} from "../theme";

type Props = {
  title: string;
  lines: TranscriptLine[];
  scrollOffset?: number;
  windowSize?: number;
  subtitle?: string;
  emptyState?: string;
  accentColor?: string;
};

function visibleWindow<T>(items: T[], scrollOffset: number, windowSize: number): T[] {
  const total = items.length;
  const end = Math.max(total - scrollOffset, 0);
  const start = Math.max(end - windowSize, 0);
  return items.slice(start, end);
}

export function TranscriptPane({
  title,
  lines,
  scrollOffset = 0,
  windowSize = 24,
  subtitle,
  emptyState = "No content yet.",
  accentColor = THEME.ink,
}: Props): React.ReactElement {
  const visible = visibleWindow(lines, scrollOffset, windowSize);
  return (
    <Box flexGrow={1} flexDirection="column" borderStyle="round" borderColor={accentColor} paddingX={1}>
      <Text color={accentColor} bold>{title}</Text>
      {subtitle ? <Text color={THEME.stone}>{subtitle}</Text> : <Text color={THEME.stone}> </Text>}
      {subtitle ? <Text color={THEME.stone}> </Text> : null}
      {visible.length === 0 ? (
        <Text color={THEME.stone}>{emptyState}</Text>
      ) : (
        visible.map((line) => {
          const formatted = formatTranscriptLine(line);
          return (
            <Text key={line.id} color={formatted.color} bold={formatted.bold}>
              {formatted.prefix ? (
                <Text color={formatted.prefix.color} bold={formatted.prefix.bold} dimColor={formatted.prefix.dimColor}>
                  {formatted.prefix.text}
                </Text>
              ) : null}
              {formatted.segments.map((segment, index) => (
                <Text key={`${line.id}-${index}`} color={segment.color} bold={segment.bold} dimColor={segment.dimColor}>
                  {segment.text}
                </Text>
              ))}
            </Text>
          );
        })
      )}
    </Box>
  );
}
