import React from "react";
import {Box, Text} from "ink";

type Props = {
  statusLine: string;
  footerHint: string;
};

export function StatusFooter({statusLine, footerHint}: Props): React.ReactElement {
  return (
    <Box flexDirection="column" marginTop={1}>
      <Text color="gray">{statusLine}</Text>
      <Text color="gray">{footerHint}</Text>
    </Box>
  );
}
