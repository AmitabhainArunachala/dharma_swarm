import React from "react";
import {Box, Text} from "ink";

import type {TabSpec} from "../types.js";

type Props = {
  tabs: TabSpec[];
  activeTabId: string;
};

export function TabBar({tabs, activeTabId}: Props): React.ReactElement {
  return (
    <Box marginTop={1} flexWrap="wrap">
      {tabs.map((tab) => {
        const active = tab.id === activeTabId;
        return (
          <Box key={tab.id} marginRight={1} borderStyle="round" borderColor={active ? "cyan" : "gray"} paddingX={1}>
            <Text color={active ? "cyan" : "gray"}>{tab.title}</Text>
          </Box>
        );
      })}
    </Box>
  );
}
