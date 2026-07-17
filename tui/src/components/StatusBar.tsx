import React from "react";
import { Box, Text } from "ink";
import Spinner from "ink-spinner";
import type { RuntimeStatus } from "../types.js";
import { THEME } from "../theme.js";

interface StatusBarProps {
  status: RuntimeStatus;
  busy?: boolean;
}

export function StatusBar({ status, busy = false }: StatusBarProps) {
  const connection = status.connected ? "connected" : "disconnected";
  const modeText =
    status.mode === "sse" ? "SSE" : status.mode === "polling" ? "polling" : "degraded";
  const executor = executorLabel(status.executor);

  return (
    <Box flexDirection="column" paddingX={1}>
      <Box gap={1} flexWrap="wrap">
        <Text bold color={THEME.brandAccent}>MOCE</Text>
        {busy ? <Text color={THEME.warning}><Spinner type="dots" /> busy</Text> : null}
        <Text color={status.connected ? THEME.success : THEME.warning}>● {connection}</Text>
        <Text color={status.mode === "degraded" ? THEME.warning : "blue"}>{modeText}</Text>
        <Text color={executorColor(status.executor)}>Executor: {executor}</Text>
        <Text color={llmStatusColor(status.llm.state)}>{llmStateLabel(status.llm.state, status.llm.message)}</Text>
      </Box>
      <Box gap={1} flexWrap="wrap">
        <Text color={THEME.muted}>Physical Agent TUI</Text>
        <Text color={THEME.muted}>{status.apiBase}</Text>
        <Text color={THEME.muted}>backend {status.backend}</Text>
        <Text color={THEME.muted}>LLM: {status.llm.model}</Text>
        <Text color={status.llm.hasApiKey ? THEME.success : THEME.warning}>{llmKeyLabel(status.llm.hasApiKey)}</Text>
        <Text color={THEME.muted}>last {status.lastRefresh ?? "never"}</Text>
        <Text color={status.message === "Ready." ? THEME.success : THEME.warning}>{status.message}</Text>
      </Box>
      <Box
        width="100%"
        borderStyle="single"
        borderTop={false}
        borderLeft={false}
        borderRight={false}
        borderBottomColor={THEME.brandAccent}
      />
    </Box>
  );
}

function executorLabel(executor: RuntimeStatus["executor"]): string {
  if (!executor) {
    return "status unknown";
  }
  if (executor.mode === "waiting_for_init") {
    return "waiting for initialization";
  }
  if (executor.mode === "none" && executor.legacy_watch_configured) {
    return "status unknown (configured by legacy server)";
  }
  const mode =
    executor.mode === "embedded"
      ? "embedded"
      : executor.mode === "external"
        ? "external"
        : "not running";
  const state = (executor.status ?? "").trim();
  if (!state || (executor.mode === "none" && ["stopped", "disabled", "inactive"].includes(state))) {
    return mode;
  }
  return `${mode} (${state})`;
}

function executorColor(executor: RuntimeStatus["executor"]): "green" | "yellow" | "red" | "gray" {
  if (!executor || executor.mode === "waiting_for_init") {
    return "yellow";
  }
  if (["degraded", "error", "failed", "fatal"].includes(executor.status ?? "")) {
    return "red";
  }
  if (
    (executor.mode === "embedded" || executor.mode === "external") &&
    executor.lease?.active === true &&
    ["active", "running", "ready"].includes(executor.status ?? "")
  ) {
    return "green";
  }
  if (["starting", "standby"].includes(executor.status ?? "")) {
    return "yellow";
  }
  return "gray";
}

function llmKeyLabel(hasApiKey: boolean | null): string {
  if (hasApiKey === true) {
    return "key set";
  }
  if (hasApiKey === false) {
    return "key missing";
  }
  return "key unknown";
}

function llmStateLabel(state: string, message?: string): string {
  if (state === "ok") {
    return "LLM connected";
  }
  if (state === "checking") {
    return "LLM checking";
  }
  if (state === "failed") {
    return `LLM failed: ${shortLlmFailure(message)}`;
  }
  if (state === "unavailable") {
    return `LLM unavailable: ${shortLlmFailure(message)}`;
  }
  return "LLM unknown";
}

function llmStatusColor(state: string): "green" | "yellow" | "red" | "gray" {
  if (state === "ok") {
    return "green";
  }
  if (state === "failed" || state === "unavailable") {
    return "red";
  }
  if (state === "checking") {
    return "yellow";
  }
  return "gray";
}

function shortLlmFailure(message?: string): string {
  const value = (message ?? "").trim();
  if (!value) {
    return "unknown";
  }
  if (/key status is not active/i.test(value)) {
    return "key inactive";
  }
  if (/401|unauthorized|authentication/i.test(value)) {
    return "auth failed";
  }
  return value.replace(/\s+/g, " ").slice(0, 80);
}
