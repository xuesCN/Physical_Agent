import React from "react";
import { Box, Text } from "ink";
import type { AgentState, ConfigResponse, HealthState, RuntimeStatus } from "../types.js";
import { buildRobotViewModels } from "../formatters/robot.js";
import { flattenActions } from "../api/client.js";

interface StatusPanelProps {
  status: RuntimeStatus;
  health: HealthState | null;
  state: AgentState | null;
  config: ConfigResponse | null;
}

export function StatusPanel({ status, health, state, config }: StatusPanelProps) {
  const actions = flattenActions(state);
  const robots = buildRobotViewModels(state, config);
  return (
    <Box flexDirection="column" paddingX={1}>
      <Text color="cyan">status</Text>
      <Text>api: {status.apiBase}</Text>
      <Text>backend: {status.backend}</Text>
      <Text>watch: {status.watch}</Text>
      <Text>connection: {status.connected ? "connected" : "disconnected"} via {status.mode}</Text>
      <Text>workspace: {state?.workspace_path ?? health?.workspace_path ?? "-"}</Text>
      <Text>config: {state?.config_path ?? health?.config_path ?? config?.config_path ?? "-"}</Text>
      <Text>robots: {robots.length}</Text>
      <Text>actions: {actions.length}</Text>
      <Text>agent tasks: {agentTaskCount(state)}</Text>
      <Text>uploads: {state?.uploads?.uploads?.length ?? 0}</Text>
      <Text color="gray">{status.message}</Text>
    </Box>
  );
}

function agentTaskCount(state: AgentState | null): number {
  const document = state?.plan;
  if (!document || typeof document !== "object") {
    return 0;
  }
  const plan = "plan" in document && document.plan && typeof document.plan === "object"
    ? document.plan
    : document;
  const output = "agent_output" in plan && plan.agent_output && typeof plan.agent_output === "object"
    ? plan.agent_output
    : null;
  return output && "tasks" in output && Array.isArray(output.tasks) ? output.tasks.length : 0;
}
