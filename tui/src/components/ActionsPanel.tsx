import React from "react";
import { Box, Text } from "ink";
import { flattenActions } from "../api/client.js";
import type { AgentState, ActionItem, AgentOutput, AgentTask } from "../types.js";
import { SectionTitle } from "./SectionTitle.js";

interface ActionsPanelProps {
  state: AgentState | null;
  error?: string | null;
  force?: boolean;
}

export function ActionsPanel({ state, error, force = false }: ActionsPanelProps) {
  const actions = flattenActions(state);
  const output = agentOutput(state);
  const tasks = currentTasks(output);
  if (!force && !error && state?.ready && actions.length === 0 && tasks.length === 0) {
    return null;
  }
  return (
    <Box flexDirection="column" paddingX={1}>
      <SectionTitle title="actions" />
      {error ? <Text color="red">API unavailable: {error}</Text> : null}
      {!error && !state?.ready ? <Text color="yellow">{state?.message ?? "Workspace is not ready."}</Text> : null}
      {output ? (
        <Text color="cyan">
          agent output: {output.decision ?? "unknown"} / {output.status ?? "unknown"} / {output.lifecycle ?? "unknown"}
        </Text>
      ) : null}
      {tasks.slice(0, 12).map((task) => (
        <AgentTaskRow key={task.id} task={task} />
      ))}
      {tasks.length > 12 ? <Text color="gray">+{tasks.length - 12} more tasks</Text> : null}
      {!error && state?.ready && actions.length === 0 && tasks.length === 0 ? <Text color="gray">No actions.</Text> : null}
      {actions.slice(0, 8).map((action) => (
        <ActionRow key={`${action.status}-${action.id}`} action={action} />
      ))}
      {actions.length > 8 ? <Text color="gray">+{actions.length - 8} more</Text> : null}
    </Box>
  );
}

function AgentTaskRow({ task }: { task: AgentTask }) {
  const safety = task.kind === "safety_gate";
  const dependencies = task.depends_on?.length ? ` <- ${task.depends_on.join(",")}` : "";
  return (
    <Box gap={1} flexWrap="wrap">
      <Text color={taskStatusColor(task.status)}>{task.status}</Text>
      <Text color={safety ? "magenta" : undefined}>{task.kind}</Text>
      <Text>{task.action_id}</Text>
      <Text color={task.owner === "watch" ? "cyan" : "yellow"}>owner={task.owner}</Text>
      {safety ? <Text color="red">mandatory watch gate</Text> : null}
      {safety ? <Text color="gray">{task.policy_source ?? "SAFETY.md"} {task.checks?.length ?? 0} checks</Text> : null}
      <Text color="gray">{dependencies}</Text>
    </Box>
  );
}

function agentOutput(state: AgentState | null): AgentOutput | null {
  const document = state?.plan;
  if (!document || typeof document !== "object") {
    return null;
  }
  const nested = "plan" in document && document.plan && typeof document.plan === "object"
    ? document.plan
    : document;
  const output = "agent_output" in nested ? nested.agent_output : null;
  return output && typeof output === "object" ? output as AgentOutput : null;
}

function currentTasks(output: AgentOutput | null): AgentTask[] {
  return Array.isArray(output?.tasks) ? output.tasks : [];
}

function taskStatusColor(status: string) {
  if (status === "passed" || status === "completed") {
    return "green";
  }
  if (status === "rejected" || status === "failed") {
    return "red";
  }
  return "yellow";
}

function ActionRow({ action }: { action: ActionItem }) {
  const approval = approvalSummary(action);
  return (
    <Box gap={1} flexWrap="wrap">
      <Text color={statusColor(action.status)}>{statusGlyph(action.status)}</Text>
      <Text>{action.id}</Text>
      <Text>{action.robot}.{action.capability}</Text>
      <Text color={approval.includes("required") ? "yellow" : "green"}>{approval}</Text>
      <Text color="gray">{oneLine(action.reason ?? "")}</Text>
    </Box>
  );
}

function statusGlyph(status: string | undefined): string {
  if (status === "completed") {
    return "done";
  }
  if (status === "cancelled" || status === "failed") {
    return "stop";
  }
  return "wait";
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
