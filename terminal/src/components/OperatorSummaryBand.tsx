import React from "react";
import {Box, Text} from "ink";
import {THEME} from "../theme";

type SummaryItem = {
  label: string;
  value: string;
  tone?: "live" | "warn" | "critical" | "neutral";
};

type Props = {
  items: SummaryItem[];
  compact?: boolean;
};

function compactSummaryItems(items: SummaryItem[]): SummaryItem[] {
  const lookup = Object.fromEntries(items.map((item) => [item.label, item]));
  return [lookup.loop, lookup.verify, lookup.runtime ?? lookup.sessions, lookup.approvals].filter(Boolean) as SummaryItem[];
}

function toneColor(tone: SummaryItem["tone"]): string {
  switch (tone) {
    case "live":
      return THEME.moss;
    case "warn":
      return THEME.parchment;
    case "critical":
      return THEME.vermilion;
    default:
      return THEME.foam;
  }
}

export function OperatorSummaryBand({items, compact = false}: Props): React.ReactElement {
  if (compact) {
    const compactItems = compactSummaryItems(items);
    return (
      <Box marginTop={1} borderStyle="round" borderColor={THEME.river} paddingX={1} flexWrap="wrap">
        {compactItems.map((item, index) => (
          <Box key={`${item.label}-${index}`} marginRight={2}>
            <Text color={THEME.stone}>{item.label}</Text>
            <Text color={THEME.stone}> </Text>
            <Text color={toneColor(item.tone)} bold>{item.value}</Text>
          </Box>
        ))}
      </Box>
    );
  }
  return (
    <Box marginTop={1} borderStyle="round" borderColor={THEME.river} paddingX={1} flexDirection="column">
      <Text color={THEME.river} bold>Operator Summary</Text>
      <Box flexWrap="wrap">
        {items.map((item, index) => (
          <Box key={`${item.label}-${index}`} marginRight={2}>
            <Text color={THEME.stone}>{item.label}</Text>
            <Text color={THEME.stone}> </Text>
            <Text color={toneColor(item.tone)} bold>{item.value}</Text>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
