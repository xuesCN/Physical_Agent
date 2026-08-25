import React from "react";
import { Box, Text } from "ink";
import { THEME } from "../theme.js";

export function SectionTitle({ title, detail }: { title: string; detail?: string }) {
  return (
    <Box alignItems="center" gap={1} width="100%">
      <Text bold color={THEME.brandAccent}>◆ {title}</Text>
      {detail ? <Text color={THEME.muted}>{detail}</Text> : null}
      <Box
        flexGrow={1}
        borderStyle="single"
        borderTop={false}
        borderLeft={false}
        borderRight={false}
        borderBottomColor={THEME.brandAccent}
      />
    </Box>
  );
}
