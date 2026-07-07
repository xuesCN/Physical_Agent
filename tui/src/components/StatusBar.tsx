import React from "react";
import { Box, Text } from "ink";
import Spinner from "ink-spinner";
import type { RuntimeStatus } from "../types.js";

interface StatusBarProps {
  status: RuntimeStatus;
  busy?: boolean;
}

export function StatusBar({ status, busy = false }: StatusBarProps) {
  const connection = status.connected ? "connected" : "disconnected";
  const modeText =
    status.mode === "sse" ? "SSE" : status.mode === "polling" ? "polling" : "degraded";

  return (
    <Box flexDirection="column" borderStyle="single" paddingX={1}>
      <Box gap={1} flexWrap="wrap">
        <Text bold color="cyan">Physical Agent TUI</Text>
        {busy ? <Text color="yellow"><Spinner type="dots" /> busy</Text> : null}
        <Text>api {status.apiBase}</Text>
        <Text color={status.connected ? "green" : "yellow"}>{connection}</Text>
        <Text color={status.mode === "degraded" ? "yellow" : "blue"}>{modeText}</Text>
      </Box>
      <Box gap={1} flexWrap="wrap">
        <Text>backend {status.backend}</Text>
        <Text>watch {status.watch}</Text>
        <Text>last {status.lastRefresh ?? "never"}</Text>
        <Text color={status.message === "Ready." ? "green" : "yellow"}>{status.message}</Text>
      </Box>
    </Box>
  );
}
