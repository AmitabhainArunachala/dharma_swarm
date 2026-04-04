import React from "react";
import {Box, Text} from "ink";
import {THEME} from "../theme";

type Props = {
  prompt: string;
  compact?: boolean;
};

export function Composer({prompt, compact = false}: Props): React.ReactElement {
  return (
    <Box marginTop={1} borderStyle="round" borderColor={THEME.indigo} paddingX={1} flexDirection="column">
      {!compact ? <Text color={THEME.wave} bold>Operator Prompt</Text> : null}
      <Box>
        <Text color={THEME.stone}>&gt; </Text>
        <Text color={THEME.foam}>{prompt || " "}</Text>
      </Box>
    </Box>
  );
}
