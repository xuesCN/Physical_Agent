import React from "react";
import { Box, Text } from "ink";
import Spinner from "ink-spinner";
import type { ChatMessage } from "../types.js";

interface ChatPanelProps {
  messages: ChatMessage[];
  streamingText?: string;
  streaming?: boolean;
  error?: string | null;
}

export function ChatPanel({ messages, streamingText = "", streaming = false, error }: ChatPanelProps) {
  const visible = messages.slice(-6);
  return (
    <Box flexDirection="column" borderStyle="round" paddingX={1} minHeight={10}>
      <Box gap={1}>
        <Text bold>Chat</Text>
        {streaming ? <Text color="yellow"><Spinner type="dots" /> streaming</Text> : null}
      </Box>
      {visible.length === 0 && !streamingText ? <Text color="gray">No chat yet. Type a message or /help.</Text> : null}
      {visible.map((message, index) => (
        <Text key={`${message.created_at ?? index}-${message.role}`}>
          <Text color={message.role === "assistant" ? "cyan" : "green"}>{message.role}: </Text>
          {trim(message.content)}
        </Text>
      ))}
      {streamingText ? (
        <Text>
          <Text color="cyan">assistant: </Text>
          {trim(streamingText)}
        </Text>
      ) : null}
      {error ? <Text color="red">{error}</Text> : null}
    </Box>
  );
}

function trim(value: string): string {
  return value.replace(/\s+/g, " ").slice(0, 160);
}
