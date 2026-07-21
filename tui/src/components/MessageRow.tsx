import React from "react";
import { Box, Text } from "ink";
import { THEME } from "../theme.js";

export interface RolePresentation {
  marker: string;
  color: string;
}

export function rolePresentation(role: string): RolePresentation {
  if (role === "user") return { marker: ">", color: THEME.success };
  if (role === "assistant") return { marker: "⏺", color: THEME.brandAccent };
  if (role === "draft") return { marker: "draft ◇", color: THEME.warning };
  if (role === "thought") return { marker: "thought ▸", color: THEME.muted };
  return { marker: `${role} │`, color: THEME.muted };
}

export function MessageRow({
  marker,
  color,
  children
}: {
  marker: string;
  color: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <Box flexDirection="row" width="100%">
      <Marker marker={marker} color={color} />
      <Box flexDirection="column" flexGrow={1} flexShrink={1} flexBasis={0}>
        {children}
      </Box>
    </Box>
  );
}

function Marker({ marker, color }: { marker: string; color: string }): React.JSX.Element {
  if (marker !== "⏺") {
    return (
      <Box flexShrink={0} marginRight={1}>
        <Text color={color}>{marker}</Text>
      </Box>
    );
  }

  // Ink 5.2.1 measures this emoji-style glyph as two cells, while its output
  // tokenizer paints one. Prime the second cell, then overlay the bare marker.
  return (
    <Box flexShrink={0} marginRight={1} width={2}>
      <Text color={color}>{"\u3000"}</Text>
      <Box position="absolute">
        <Text color={color}>{marker}</Text>
      </Box>
    </Box>
  );
}
