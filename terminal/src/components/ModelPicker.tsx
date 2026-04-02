import React from "react";
import {Box, Text} from "ink";

type ModelChoice = {
  alias: string;
  label: string;
  provider: string;
  model: string;
};

type Props = {
  choices: ModelChoice[];
  selectedIndex: number;
};

export function ModelPicker({choices, selectedIndex}: Props): React.ReactElement {
  const start = Math.max(0, Math.min(selectedIndex - 4, Math.max(choices.length - 10, 0)));
  const visible = choices.slice(start, start + 10);
  return (
    <Box flexGrow={1} flexDirection="column" borderStyle="double" borderColor="cyan" paddingX={1}>
      <Text color="cyan">Model Picker</Text>
      <Text color="gray">Enter apply | Esc close | j/k or arrows move | 1-9 direct | {choices.length} routes</Text>
      <Text color="gray"> </Text>
      {visible.length === 0 ? (
        <Text color="gray">No model targets loaded.</Text>
      ) : (
        visible.map((choice, index) => {
          const actualIndex = start + index;
          const active = actualIndex === selectedIndex;
          return (
            <Text key={`${choice.provider}:${choice.model}`} color={active ? "cyan" : "white"}>
              {active ? "›" : " "} {actualIndex + 1}. {choice.alias} {"->"} {choice.label}
            </Text>
          );
        })
      )}
    </Box>
  );
}
