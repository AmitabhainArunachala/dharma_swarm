import React from "react";
import {Box, Text} from "ink";

type Props = {
  provider: string;
  model: string;
  bridgeStatus: string;
  activeTitle: string;
};

export function ShellHeader({provider, model, bridgeStatus, activeTitle}: Props): React.ReactElement {
  const normalizedModel = model.replace(/:cloud$/, "");
  const routeLabel = `${provider}:${normalizedModel}`;
  const clippedRoute = routeLabel.length > 18 ? `${routeLabel.slice(0, 17)}…` : routeLabel;
  const clippedTitle = activeTitle.length > 10 ? `${activeTitle.slice(0, 9)}…` : activeTitle;
  const statusColor =
    bridgeStatus === "connected" ? "green" : bridgeStatus === "degraded" ? "yellow" : bridgeStatus === "offline" ? "red" : "gray";

  return (
    <Box borderStyle="single" borderColor="gray" paddingX={1}>
      <Text color="cyan">DHARMA</Text>
      <Text color="gray">  </Text>
      <Text color={statusColor}>{bridgeStatus}</Text>
      <Text color="gray">  |  </Text>
      <Text color="white">{clippedRoute}</Text>
      <Text color="gray">  |  </Text>
      <Text color="magenta">{clippedTitle}</Text>
      <Text color="gray">  |  operator shell</Text>
    </Box>
  );
}
