import React from "react";
import { Box, Text } from "ink";
import { THEME } from "../theme.js";
import { SectionTitle } from "./SectionTitle.js";
import { normalizeTerminalText } from "./textFormat.js";
interface ChatPanelProps {
  hasTranscript: boolean;
  streamingText?: string;
  streaming?: boolean;
  error?: string | null;
}

export function ChatPanel({ hasTranscript, streamingText = "", streaming = false, error }: ChatPanelProps) {
  return (
    <Box flexDirection="column" paddingX={1}>
      <SectionTitle title="chat" detail={streaming ? "streaming" : undefined} />
      {!hasTranscript && !streamingText ? <Text color="gray">No chat yet. Type a message or /help.</Text> : null}
      {streamingText ? (
        <Text>
          <Text color={THEME.brandAccent}>moce │ </Text>
          {normalizeTerminalText(streamingText)}
        </Text>
      ) : null}
      {error ? <Text color="red">{error}</Text> : null}
    </Box>
  );
}
