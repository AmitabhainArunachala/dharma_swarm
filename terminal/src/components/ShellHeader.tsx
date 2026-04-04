import React from "react";
import {Box, Text} from "ink";
import {THEME} from "../theme";
import type {RoutePolicyState} from "../types";
import {routeLabel} from "../routePolicy";

type Props = {
  routePolicy: RoutePolicyState;
  bridgeStatus: string;
  activeTitle: string;
  focusMode?: string;
  activeCount?: number;
  compact?: boolean;
};

export function ShellHeader({routePolicy, bridgeStatus, activeTitle, focusMode, activeCount, compact = false}: Props): React.ReactElement {
  const activeRouteLabel = routeLabel(routePolicy);
  const clippedRoute = activeRouteLabel.length > (compact ? 14 : 24) ? `${activeRouteLabel.slice(0, compact ? 13 : 23)}…` : activeRouteLabel;
  const clippedTitle = activeTitle.length > (compact ? 8 : 18) ? `${activeTitle.slice(0, compact ? 7 : 17)}…` : activeTitle;
  const statusColor =
    bridgeStatus === "connected" ? THEME.moss : bridgeStatus === "degraded" ? THEME.parchment : bridgeStatus === "offline" ? THEME.vermilion : THEME.stone;
  const statusLabel =
    compact
      ? bridgeStatus === "connected" ? "UP" : bridgeStatus === "degraded" ? "DEG" : bridgeStatus === "offline" ? "OFF" : "BOOT"
      : bridgeStatus === "connected" ? "LIVE" : bridgeStatus === "degraded" ? "DEGRADED" : bridgeStatus === "offline" ? "OFFLINE" : "BOOT";

  return (
    <Box borderStyle="round" borderColor={THEME.indigo} paddingX={1} flexDirection="column">
      <Box>
        <Text color={THEME.wave} bold>{compact ? "DHARMA" : "DHARMA TERMINAL"}</Text>
        <Text color={THEME.stone}>  </Text>
        <Text color={statusColor} bold>{statusLabel}</Text>
        <Text color={THEME.stone}>{compact ? " | " : "  |  route "}</Text>
        <Text color={THEME.foam} bold>{clippedRoute}</Text>
        <Text color={THEME.stone}>{compact ? " | " : "  |  state "}</Text>
        <Text color={routePolicy.routeState === "ready" ? THEME.moss : routePolicy.routeState === "degraded" || routePolicy.routeState === "slow" ? THEME.parchment : THEME.vermilion} bold>
          {compact ? routePolicy.routeState.slice(0, 3).toUpperCase() : routePolicy.routeState.toUpperCase()}
        </Text>
        <Text color={THEME.stone}>{compact ? " | " : "  |  focus "}</Text>
        <Text color={THEME.parchment} bold>{clippedTitle}</Text>
        {!compact && focusMode ? (
          <>
            <Text color={THEME.stone}>  |  mode </Text>
            <Text color={THEME.persimmon} bold>{focusMode}</Text>
          </>
        ) : null}
        {!compact && typeof activeCount === "number" ? (
          <>
            <Text color={THEME.stone}>  |  panes </Text>
            <Text color={THEME.foam} bold>{activeCount}</Text>
          </>
        ) : null}
      </Box>
      <Text color={THEME.stone}>
        {compact
          ? routePolicy.availabilityReason || `${focusMode || "tab"} | ${routePolicy.strategy}`
          : routePolicy.availabilityReason || "operator shell | route truth | execution trace"}
      </Text>
    </Box>
  );
}
