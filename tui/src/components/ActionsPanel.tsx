import React from "react";
import { Box, Text } from "ink";
import { flattenActions } from "../api/client.js";
import type { AgentState, ActionItem } from "../types.js";

interface ActionsPanelProps {
  state: AgentState | null;
  error?: string | null;
}

export function ActionsPanel({ state, error }: ActionsPanelProps) {
  const actions = flattenActions(state);
  return (
    <Box flexDirection="column" borderStyle="round" paddingX={1} minHeight={8}>
      <Text bold>Actions</Text>
      {error ? <Text color="red">API unavailable: {error}</Text> : null}
      {!error && !state?.ready ? <Text color="yellow">{state?.message ?? "Workspace is not ready."}</Text> : null}
      {!error && state?.ready && actions.length === 0 ? <Text color="gray">No actions yet. Use /task or chat to draft work.</Text> : null}
      {actions.slice(0, 8).map((action) => (
        <ActionRow key={`${action.status}-${action.id}`} action={action} />
      ))}
      {actions.length > 8 ? <Text color="gray">+{actions.length - 8} more</Text> : null}
    </Box>
  );
}

function ActionRow({ action }: { action: ActionItem }) {
  const approval = approvalSummary(action);
  return (
    <Box gap={1} flexWrap="wrap">
      <Text color={statusColor(action.status)}>{action.status ?? "pending"}</Text>
      <Text>{action.id}</Text>
      <Text>{action.robot}.{action.capability}</Text>
      <Text color={approval.includes("required") ? "yellow" : "green"}>{approval}</Text>
      <Text color="gray">{oneLine(action.reason ?? "")}</Text>
    </Box>
  );
}

function approvalSummary(action: ActionItem): string {
  const approval = action.metadata?.approval as Record<string, unknown> | undefined;
  if (!approval) {
    return "approval unknown";
  }
  if (!approval.required) {
    return "not required";
  }
  const status = String(approval.status ?? "required");
  if (status === "approved") {
    return "approved";
  }
  if (status === "rejected") {
    return "rejected";
  }
  return "approval required";
}

function statusColor(status: string | undefined) {
  if (status === "completed") {
    return "green";
  }
  if (status === "cancelled" || status === "failed") {
    return "red";
  }
  return "yellow";
}

function oneLine(value: string): string {
  return value.replace(/\s+/g, " ").slice(0, 80);
}
