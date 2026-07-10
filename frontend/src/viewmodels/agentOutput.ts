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

interface IndexedSafetyGateStatus {
  index: number;
  status: "passed" | "rejected";
}

interface SafetyGateStatusIndex {
  byTaskId: Map<string, IndexedSafetyGateStatus>;
  byActionId: Map<string, IndexedSafetyGateStatus>;
}

interface TerminalActionIndex {
  inProgress: Set<string>;
  completed: Set<string>;
  cancelled: Set<string>;
}

export function formatAgentOutput(
  state: AgentState | null | undefined
): AgentOutputOverview | null {
  const output = readAgentOutput(state?.plan);
  if (!Object.keys(output).length) {
    return null;
  }

  const safetyGateStatuses = indexSafetyGateStatuses(state?.feedback);
  const terminalActions = indexTerminalActions(state?.actions);
  const approvalTaskStatuses = indexApprovalTaskStatuses(state?.actions);
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
        status: resolveTaskStatus(
          id,
          kind,
          actionId,
          status as AgentTaskStatus,
          safetyGateStatuses,
          terminalActions,
          approvalTaskStatuses
        ),
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

function resolveTaskStatus(
  taskId: string,
  kind: string,
  actionId: string,
  plannedStatus: AgentTaskStatus,
  safetyGateStatuses: SafetyGateStatusIndex,
  terminalActions: TerminalActionIndex,
  approvalTaskStatuses: Map<string, AgentTaskStatus>
): AgentTaskStatus {
  const gateByTaskId = safetyGateStatuses.byTaskId.get(
    `task:safety_gate:${actionId}`
  );
  const gateByActionId = safetyGateStatuses.byActionId.get(actionId);
  const latestGateStatus =
    !gateByTaskId
      ? gateByActionId?.status
      : !gateByActionId || gateByTaskId.index >= gateByActionId.index
        ? gateByTaskId.status
        : gateByActionId.status;
  if (kind === "approval") {
    return approvalTaskStatuses.get(actionId) ?? plannedStatus;
  }

  if (kind === "safety_gate") {
    const byTaskId = safetyGateStatuses.byTaskId.get(taskId);
    const byActionId = safetyGateStatuses.byActionId.get(actionId);
    if (byTaskId || byActionId) {
      if (!byTaskId) {
        return byActionId!.status;
      }
      if (!byActionId || byTaskId.index >= byActionId.index) {
        return byTaskId.status;
      }
      return byActionId.status;
    }
  }

  if (kind === "physical_action") {
    if (terminalActions.cancelled.has(actionId)) {
      return latestGateStatus === "rejected" || approvalTaskStatuses.get(actionId) === "rejected"
        ? "skipped"
        : "failed";
    }
    if (terminalActions.completed.has(actionId)) {
      return "completed";
    }
    if (terminalActions.inProgress.has(actionId)) {
      return "checking";
    }
  }

  return plannedStatus;
}

function indexSafetyGateStatuses(feedback: unknown): SafetyGateStatusIndex {
  const byTaskId = new Map<string, IndexedSafetyGateStatus>();
  const byActionId = new Map<string, IndexedSafetyGateStatus>();

  feedbackEvents(feedback).forEach((value, index) => {
    const event = asRecord(value);
    if (readString(event.event) !== "safety_gate") {
      return;
    }
    const rawStatus = readString(event.status);
    if (rawStatus !== "passed" && rawStatus !== "rejected") {
      return;
    }
    const status: IndexedSafetyGateStatus = { index, status: rawStatus };
    const taskId = readString(event.task_id);
    const actionId = readString(event.action_id);
    if (taskId) {
      byTaskId.set(taskId, status);
    }
    if (actionId) {
      byActionId.set(actionId, status);
    }
  });

  return { byTaskId, byActionId };
}

function feedbackEvents(feedback: unknown): unknown[] {
  const document = asRecord(feedback);
  if (Array.isArray(document.history) && document.history.length) {
    return document.history;
  }
  const latest = asRecord(document.latest);
  return Object.keys(latest).length ? [latest] : [];
}

function indexTerminalActions(actions: AgentState["actions"] | undefined): TerminalActionIndex {
  return {
    inProgress: actionIds(actions?.in_progress),
    completed: actionIds(actions?.completed),
    cancelled: actionIds(actions?.cancelled)
  };
}

function indexApprovalTaskStatuses(
  actions: AgentState["actions"] | undefined
): Map<string, AgentTaskStatus> {
  const statuses = new Map<string, AgentTaskStatus>();
  for (const value of allActions(actions)) {
    const action = asRecord(value);
    const actionId = readString(action.id);
    const approval = asRecord(asRecord(action.metadata).approval);
    const status = readString(approval.status).toLowerCase();
    if (!actionId) {
      continue;
    }
    if (status === "approved") {
      statuses.set(actionId, "completed");
    } else if (status === "rejected") {
      statuses.set(actionId, "rejected");
    } else if (status === "pending") {
      statuses.set(actionId, "requested");
    }
  }
  return statuses;
}

function allActions(actions: AgentState["actions"] | undefined): unknown[] {
  return [
    ...(Array.isArray(actions?.pending) ? actions.pending : []),
    ...(Array.isArray(actions?.in_progress) ? actions.in_progress : []),
    ...(Array.isArray(actions?.completed) ? actions.completed : []),
    ...(Array.isArray(actions?.cancelled) ? actions.cancelled : [])
  ];
}

function actionIds(actions: unknown): Set<string> {
  if (!Array.isArray(actions)) {
    return new Set();
  }
  return new Set(
    actions
      .map((action) => readString(asRecord(action).id))
      .filter((id) => Boolean(id))
  );
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
