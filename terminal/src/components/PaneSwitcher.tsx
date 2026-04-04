import React from "react";
import {Box, Text} from "ink";

import type {TabSpec} from "../types";
import {THEME} from "../theme";

type Props = {
  tabs: TabSpec[];
  selectedIndex: number;
};

export function PaneSwitcher({tabs, selectedIndex}: Props): React.ReactElement {
  const start = Math.max(0, Math.min(selectedIndex - 4, Math.max(tabs.length - 10, 0)));
  const visible = tabs.slice(start, start + 10);
  return (
    <Box flexGrow={1} flexDirection="column" borderStyle="double" borderColor={THEME.parchment} paddingX={1}>
      <Text color={THEME.parchment} bold>Pane Switcher</Text>
      <Text color={THEME.stone}>Enter jump | Esc close | j/k or arrows move | {tabs.length} panes</Text>
      <Text color={THEME.stone}> </Text>
      {visible.map((tab, index) => {
        const actualIndex = start + index;
        const active = actualIndex === selectedIndex;
        return (
          <Box key={tab.id} flexDirection="column" marginBottom={1}>
            <Text color={active ? THEME.parchment : THEME.foam} bold={active}>
              {active ? "▶" : "•"} {actualIndex + 1}. {tab.title}
            </Text>
            <Text color={THEME.stone}>  {tab.kind}{tab.closable ? " | closable" : ""}</Text>
          </Box>
        );
      })}
    </Box>
  );
}
