import React from "react";
import {Box, Text} from "ink";

import type {TranscriptLine} from "../types";
import {THEME} from "../theme";

type AgentRouteCard = {
  intent: string;
  provider: string;
  modelAlias: string;
  effort: string;
  role: string;
};

type OpenClawSummary = {
  present: string;
  readable: string;
  agents: string;
  providers: string;
};

type Props = {
  title: string;
  lines: TranscriptLine[];
  selectedRouteIndex?: number;
};

function parseAgentRouteCards(lines: TranscriptLine[]): AgentRouteCard[] {
  return lines
    .map((line) => line.text.trim())
    .filter((line) => line.startsWith("- "))
    .map((line) => line.replace(/^- /, ""))
    .map((line) => {
      const match = line.match(/^(.*?) -> (.*?):(.*?) \| effort (.*?) \| role (.*?)$/);
      if (!match) {
        return null;
      }
      return {
        intent: match[1].trim(),
        provider: match[2].trim(),
        modelAlias: match[3].trim(),
        effort: match[4].trim(),
        role: match[5].trim(),
      };
    })
    .filter((card): card is AgentRouteCard => Boolean(card));
}

function parseOpenClawSummary(lines: TranscriptLine[]): OpenClawSummary {
  const lineValue = (label: string): string => {
    const match = lines.find((line) => line.text.startsWith(`${label}: `));
    return match ? match.text.slice(label.length + 2).trim() : "n/a";
  };
  return {
    present: lineValue("Present"),
    readable: lineValue("Readable"),
    agents: lineValue("Agents"),
    providers: lineValue("Providers"),
  };
}

function clampIndex(index: number, count: number): number {
  if (count <= 0) {
    return 0;
  }
  return Math.min(Math.max(index, 0), count - 1);
}

export function AgentsPane({title, lines, selectedRouteIndex = 0}: Props): React.ReactElement {
  const routes = parseAgentRouteCards(lines);
  const openclaw = parseOpenClawSummary(lines);
  const activeIndex = clampIndex(selectedRouteIndex, routes.length);
  const selected = routes[activeIndex];

  return (
    <Box flexGrow={1} borderStyle="round" borderColor={THEME.pine} paddingX={1} flexDirection="column">
      <Text color={THEME.moss} bold>{title}</Text>
      <Text color={THEME.stone}>route profiles and execution posture | j/k or ↑/↓ select route</Text>
      <Box marginTop={1}>
        <Box width="35%" flexDirection="column" borderStyle="single" borderColor={THEME.ink} paddingX={1}>
          <Text color={THEME.parchment} bold>Routes</Text>
          <Text color={THEME.stone}>typed routing intents</Text>
          {routes.length === 0 ? (
            <Text color={THEME.stone}>No typed agent routes yet.</Text>
          ) : (
            routes.slice(0, 12).map((route, index) => {
              const active = index === activeIndex;
              return (
                <Box key={`${route.intent}-${route.provider}-${route.modelAlias}`} flexDirection="column" marginTop={1} borderStyle={active ? "round" : undefined} borderColor={active ? THEME.moss : undefined} paddingX={active ? 1 : 0}>
                  <Text color={active ? THEME.moss : THEME.foam} bold={active}>
                    {active ? "◆ " : "• "}
                    {route.intent}
                  </Text>
                  <Text color={active ? THEME.foam : THEME.stone}>
                    {"  "}{route.provider}:{route.modelAlias} | {route.effort}
                  </Text>
                </Box>
              );
            })
          )}
        </Box>
        <Box width="65%" marginLeft={1} flexDirection="column" borderStyle="single" borderColor={THEME.ink} paddingX={1}>
          <Text color={THEME.wave} bold>Route brief</Text>
          <Text color={THEME.stone}>selected route plus OpenClaw envelope</Text>
          {!selected ? (
            <Text color={THEME.stone}>No selected route.</Text>
          ) : (
            <>
              <Text color={THEME.foam} bold>{selected.intent}</Text>
              <Text color={THEME.stone}>{selected.provider}:{selected.modelAlias} | effort {selected.effort}</Text>
              <Text color={THEME.stone}>role {selected.role}</Text>
            </>
          )}
          <Text color={THEME.parchment} bold>OpenClaw</Text>
          <Text color={THEME.stone}>present {openclaw.present} | readable {openclaw.readable}</Text>
          <Text color={THEME.stone}>agents {openclaw.agents} | providers {openclaw.providers}</Text>
        </Box>
      </Box>
    </Box>
  );
}
