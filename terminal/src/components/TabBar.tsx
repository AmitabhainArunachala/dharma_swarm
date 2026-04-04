import React from "react";
import {Box, Text} from "ink";

import type {TabSpec} from "../types";
import {THEME} from "../theme";

type Props = {
  tabs: TabSpec[];
  activeTabId: string;
  compact?: boolean;
};

export function TabBar({tabs, activeTabId, compact = false}: Props): React.ReactElement {
  const limit = compact ? 6 : tabs.length;
  const activeIndex = Math.max(0, tabs.findIndex((tab) => tab.id === activeTabId));
  const startIndex = compact ? Math.max(0, Math.min(activeIndex - 2, Math.max(tabs.length - limit, 0))) : 0;
  const visibleTabs = tabs.slice(startIndex, startIndex + limit);
  const hasOverflowLeft = startIndex > 0;
  const hasOverflowRight = startIndex + limit < tabs.length;

  return (
    <Box marginTop={1} flexWrap={compact ? "nowrap" : "wrap"}>
      {hasOverflowLeft ? <Text color={THEME.stone}>◂ </Text> : null}
      {visibleTabs.map((tab) => {
        const active = tab.id === activeTabId;
        const compactTitle = tab.title.length > 8 ? `${tab.title.slice(0, 7)}…` : tab.title;
        if (compact) {
          return (
            <Box key={tab.id} marginRight={1}>
              <Text color={active ? THEME.wave : THEME.stone} bold={active}>
                {active ? `[${compactTitle}]` : compactTitle}
              </Text>
            </Box>
          );
        }
        return (
          <Box
            key={tab.id}
            marginRight={1}
            marginBottom={1}
            borderStyle="round"
            borderColor={active ? THEME.wave : THEME.ink}
            paddingX={1}
          >
            <Text color={active ? THEME.wave : THEME.stone} bold={active}>
              {active ? "◆ " : ""}
              {tab.title}
            </Text>
          </Box>
        );
      })}
      {hasOverflowRight ? <Text color={THEME.stone}>▸</Text> : null}
    </Box>
  );
}
