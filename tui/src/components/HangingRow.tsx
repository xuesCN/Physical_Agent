import React from "react";
import { Box, Text } from "ink";

export function HangingRow({
  indent = 0,
  prefix,
  prefixColor,
  children
}: {
  indent?: number;
  prefix: string;
  prefixColor?: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <Box flexDirection="row" width="100%" paddingLeft={indent * 2}>
      <Box flexShrink={0} marginRight={1}>
        <StablePrefix prefix={prefix} color={prefixColor} />
      </Box>
      <Box flexDirection="column" flexGrow={1} flexShrink={1} flexBasis={0}>
        {children}
      </Box>
    </Box>
  );
}

function StablePrefix({ prefix, color }: { prefix: string; color?: string }): React.JSX.Element {
  if (prefix !== "▪") return <Text color={color}>{prefix}</Text>;

  // Ink 5.2 measures this glyph as two cells while the Windows output tokenizer
  // paints one. Prime the measured two-cell slot, then overlay the visible glyph.
  return (
    <Box width={2}>
      <Text color={color}>{"\u3000"}</Text>
      <Box position="absolute">
        <Text color={color}>{prefix}</Text>
      </Box>
    </Box>
  );
}
