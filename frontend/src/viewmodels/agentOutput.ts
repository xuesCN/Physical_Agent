import type {
  AgentState,
  AgentTaskKind,
  AgentTaskOwner,
  AgentTaskStatus
} from "../types";

export interface AgentTaskOverview {
  key: string;
  id: string;
  label: string;
  kind: AgentTaskKind;
  owner: AgentTaskOwner;
  status: AgentTaskStatus;
  actionId: string;
  dependsOn: string[];
  mandatory: boolean;
  policySource: string;
  checkCount: number;
}

export interface AgentOutputOverview {
  schema: string;
  status: string;
  decision: string;
  lifecycle: string;
  message: string;
  proposalId: string;
  tasks: AgentTaskOverview[];
}

export function formatAgentOutput(
  state: AgentState | null | undefined
): AgentOutputOverview | null {
  const output = readAgentOutput(state?.plan);
  if (!Object.keys(output).length) {
    return null;
  }

  const rawTasks = Array.isArray(output.tasks) ? output.tasks : [];
  const tasks = rawTasks.flatMap((value) => {
    const task = asRecord(value);
    const id = readString(task.id);
    const kind = readString(task.kind);
    const owner = readString(task.owner);
    const status = readString(task.status);
    const actionId = readString(task.action_id);
    if (!id || !kind || !owner || !status || !actionId) {
      return [];
    }

    return [
      {
        key: id,
        id,
        label: readString(task.label) || id,
        kind: kind as AgentTaskKind,
        owner: owner as AgentTaskOwner,
        status: status as AgentTaskStatus,
        actionId,
        dependsOn: readStringArray(task.depends_on),
        mandatory: task.mandatory === true,
        policySource: readString(task.policy_source),
        checkCount: Array.isArray(task.checks) ? task.checks.length : 0
      }
    ];
  });

  return {
    schema: readString(output.schema),
    status: readString(output.status) || "unknown",
    decision: readString(output.decision) || "unknown",
    lifecycle: readString(output.lifecycle) || "unknown",
    message: readString(output.message),
    proposalId: readString(output.proposal_id),
    tasks
  };
}

function readAgentOutput(plan: unknown): Record<string, unknown> {
  const root = asRecord(plan);
  const direct = asRecord(root.agent_output);
  if (Object.keys(direct).length) {
    return direct;
  }
  return asRecord(asRecord(root.plan).agent_output);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function readString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function readStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}
