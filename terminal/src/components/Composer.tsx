import React from "react";
import {Box, Text} from "ink";

type Props = {
  prompt: string;
};

export function Composer({prompt}: Props): React.ReactElement {
  return (
    <Box marginTop={1} borderStyle="single" borderColor="gray" paddingX={1}>
      <Text color="gray">&gt; </Text>
      <Text>{prompt || " "}</Text>
    </Box>
  );
}
