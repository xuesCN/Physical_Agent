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
  const visible = messages.slice(-10);
  return (
    <Box flexDirection="column" paddingX={1}>
      <Box gap={1}>
        <Text color="gray">chat</Text>
        {streaming ? <Text color="yellow"><Spinner type="dots" /> streaming</Text> : null}
      </Box>
      {visible.length === 0 && !streamingText ? <Text color="gray">No chat yet. Type a message or /help.</Text> : null}
      {visible.map((message, index) => (
        <Text key={`${message.created_at ?? index}-${message.role}`}>
          <Text color={roleColor(message.role)}>{rolePrefix(message.role)} </Text>
          {renderContent(message.content)}
        </Text>
      ))}
      {streamingText ? (
        <Text>
          <Text color="cyan">assistant </Text>
          {renderContent(streamingText)}
        </Text>
      ) : null}
      {error ? <Text color="red">{error}</Text> : null}
    </Box>
  );
}

function rolePrefix(role: string): string {
  if (role === "user") {
    return ">";
  }
  if (role === "assistant") {
    return "assistant";
  }
  return role;
}

function roleColor(role: string): "cyan" | "green" | "gray" {
  if (role === "assistant") {
    return "cyan";
  }
  if (role === "user") {
    return "green";
  }
  return "gray";
}

function renderContent(value: string): string {
  return value.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
}
