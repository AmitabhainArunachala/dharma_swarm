import React from "react";
import {Box, Text} from "ink";

import type {TranscriptLine} from "../types.js";
import {formatTranscriptLine} from "../transcriptFormatting.js";

type Props = {
  title: string;
  lines: TranscriptLine[];
};

export function TranscriptPane({title, lines}: Props): React.ReactElement {
  const visible = lines.slice(-24);
  return (
    <Box flexGrow={1} flexDirection="column" borderStyle="single" borderColor="gray" paddingX={1}>
      <Text color="cyan">{title}</Text>
      <Text color="gray"> </Text>
      {visible.length === 0 ? (
        <Text color="gray">No content yet.</Text>
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
