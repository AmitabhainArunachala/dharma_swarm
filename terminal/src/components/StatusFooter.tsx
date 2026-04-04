import React from "react";
import {Box, Text} from "ink";
import {THEME} from "../theme";

type Props = {
  statusLine: string;
  routeSummary?: string;
  footerHint: string;
  focusMode?: string;
  compact?: boolean;
};

export function StatusFooter({statusLine, routeSummary, footerHint, focusMode, compact = false}: Props): React.ReactElement {
  const compactKeys = footerHint
    .split("|")
    .map((part) => part.trim())
    .slice(0, 4)
    .join(" | ");
  return (
    <Box flexDirection="column" marginTop={1} borderStyle="round" borderColor={THEME.ink} paddingX={1}>
      <Text color={THEME.foam}>
        <Text color={THEME.wave}>status</Text>
        <Text color={THEME.stone}>  </Text>
        {statusLine}
      </Text>
      {routeSummary ? (
        <Text color={THEME.parchment}>
          <Text color={THEME.stone}>route</Text>
          <Text color={THEME.stone}>  </Text>
          {routeSummary}
        </Text>
      ) : null}
      {!compact && focusMode ? (
        <Text color={THEME.persimmon}>
          <Text color={THEME.stone}>mode</Text>
          <Text color={THEME.stone}>  </Text>
          {focusMode}
        </Text>
      ) : null}
      <Text color={THEME.stone}>
        <Text color={THEME.foam}>keys</Text>
        <Text color={THEME.stone}>  </Text>
        {compact ? compactKeys : footerHint}
      </Text>
    </Box>
  );
}
