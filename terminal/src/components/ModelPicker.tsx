import React from "react";
import {Box, Text} from "ink";
import {THEME} from "../theme";
import type {RouteTarget} from "../types";

type Props = {
  choices: RouteTarget[];
  selectedIndex: number;
  title?: string;
  compact?: boolean;
};

export function ModelPicker({choices, selectedIndex, title = "Model Picker", compact = false}: Props): React.ReactElement {
  const windowSize = compact ? 6 : 10;
  const start = Math.max(0, Math.min(selectedIndex - (compact ? 2 : 4), Math.max(choices.length - windowSize, 0)));
  const visible = choices.slice(start, start + windowSize);
  return (
    <Box flexGrow={1} flexDirection="column" borderStyle="double" borderColor={THEME.wave} paddingX={1}>
      <Text color={THEME.wave} bold>{title}</Text>
      <Text color={THEME.stone}>
        {compact ? "Enter apply | Esc close" : "Enter apply | Esc close | j/k or arrows move | 1-9 direct"} | {choices.length} routes
      </Text>
      {!compact ? <Text color={THEME.stone}> </Text> : null}
      {visible.length === 0 ? (
        <Text color={THEME.stone}>No model targets loaded.</Text>
      ) : (
        visible.map((choice, index) => {
          const actualIndex = start + index;
          const active = actualIndex === selectedIndex;
          const routeState = choice.routeState;
          const stateColor =
            routeState === "ready" ? THEME.moss : routeState === "degraded" || routeState === "slow" ? THEME.parchment : THEME.vermilion;
          return (
            <Box key={`${choice.provider}:${choice.model}`} flexDirection="column" marginBottom={compact ? 0 : 1}>
              <Text color={active ? THEME.wave : THEME.foam} bold={active}>
                {active ? "▶" : "•"} {actualIndex + 1}. {compact ? choice.alias : `${choice.alias} -> ${choice.label}`}
              </Text>
              <Text color={THEME.stone}>
                {"  "}{compact ? choice.provider : `${choice.provider}:${choice.model}`} {"| "}
                <Text color={stateColor}>{routeState}</Text>
              </Text>
              {!compact && choice.availabilityReason ? <Text color={THEME.stone}>  {choice.availabilityReason}</Text> : null}
            </Box>
          );
        })
      )}
    </Box>
  );
}
