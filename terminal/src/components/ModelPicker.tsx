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
  const visible = choices.slice(0, 10);
  return (
    <Box flexGrow={1} flexDirection="column" borderStyle="double" borderColor="cyan" paddingX={1}>
      <Text color="cyan">Model Picker</Text>
      <Text color="gray">Enter apply | Esc close | j/k or arrows move | 1-9 direct</Text>
      <Text color="gray"> </Text>
      {visible.length === 0 ? (
        <Text color="gray">No model targets loaded.</Text>
      ) : (
        visible.map((choice, index) => {
          const active = index === selectedIndex;
          return (
            <Text key={`${choice.provider}:${choice.model}`} color={active ? "cyan" : "white"}>
              {active ? "›" : " "} {index + 1}. {choice.alias} {"->"} {choice.label}
            </Text>
          );
        })
      )}
    </Box>
  );
}
