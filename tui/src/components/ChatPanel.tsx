import React from "react";
import { Box, Text } from "ink";
import { MessageRow, rolePresentation } from "./MessageRow.js";
import { SectionTitle } from "./SectionTitle.js";
import { normalizeTerminalText } from "./textFormat.js";
interface ChatPanelProps {
  hasTranscript: boolean;
  streamingText?: string;
  streaming?: boolean;
  error?: string | null;
}

export function ChatPanel({ hasTranscript, streamingText = "", streaming = false, error }: ChatPanelProps) {
  const assistant = rolePresentation("assistant");

  return (
    <Box flexDirection="column" width="100%" paddingX={1}>
      <SectionTitle title="chat" detail={streaming ? "streaming" : undefined} />
      {!hasTranscript && !streamingText ? <Text color="gray">No chat yet. Type a message or /help.</Text> : null}
      {streamingText ? (
        <MessageRow marker={assistant.marker} color={assistant.color}>
          <Text>{normalizeTerminalText(streamingText)}</Text>
        </MessageRow>
      ) : null}
      {error ? <Text color="red">{error}</Text> : null}
    </Box>
  );
}
