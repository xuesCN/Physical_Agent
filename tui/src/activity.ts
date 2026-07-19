import { flattenActions } from "./api/client.js";
import type {
  ActionActivityOutcome,
  ActionItem,
  ActionTranscriptEntry,
  AgentState
} from "./types.js";

export interface ActionActivityTracker {
  initialized: boolean;
  generation: number;
  active: Set<string>;
  closed: Set<string>;
}

export function createActionActivityTracker(): ActionActivityTracker {
  return {
    initialized: false,
    generation: 0,
    active: new Set<string>(),
    closed: new Set<string>()
  };
}

export function resetActionActivityTracker(tracker: ActionActivityTracker): void {
  tracker.initialized = false;
  tracker.generation += 1;
  tracker.active.clear();
  tracker.closed.clear();
}

export function collectActionActivityEntries(
  state: AgentState | null,
  tracker: ActionActivityTracker
): ActionTranscriptEntry[] {
  if (!state?.actions) return [];
  const actions = flattenActions(state);
  if (!tracker.initialized) {
    tracker.initialized = true;
    for (const action of actions) {
      if (isTerminal(action)) {
        tracker.active.delete(action.id);
        tracker.closed.add(action.id);
      } else if (!tracker.closed.has(action.id)) {
        tracker.active.add(action.id);
      }
    }
    return [];
  }

  const previouslyActive = new Set(tracker.active);
  const additions: ActionTranscriptEntry[] = [];
  for (const action of actions) {
    if (!isTerminal(action)) {
      if (!tracker.closed.has(action.id)) tracker.active.add(action.id);
      continue;
    }
    if (tracker.closed.has(action.id)) continue;
    if (!previouslyActive.has(action.id)) {
      tracker.active.delete(action.id);
      tracker.closed.add(action.id);
      continue;
    }
    const outcome = terminalOutcome(state, action);
    if (!outcome) continue;
    let actionSnapshot: ActionItem;
    try {
      actionSnapshot = structuredClone(action);
    } catch {
      continue;
    }
    tracker.active.delete(action.id);
    tracker.closed.add(action.id);
    additions.push({
      kind: "action",
      id: `action-${tracker.generation}-${action.id}`,
      action: actionSnapshot,
      outcome
    });
  }
  return additions;
}

function isTerminal(action: ActionItem): boolean {
  return action.status === "completed" || action.status === "cancelled";
}

function terminalOutcome(state: AgentState | null, action: ActionItem): ActionActivityOutcome | null {
  if (action.status === "completed") return "done";
  if (action.status !== "cancelled") return null;
  const approval = action.metadata?.approval;
  if (isRecord(approval) && approval.status === "rejected") return "rejected";
  return matchingActionResult(state, action.id);
}

function matchingActionResult(state: AgentState | null, actionId: string): ActionActivityOutcome | null {
  const history = state?.feedback?.history ?? [];
  for (let index = history.length - 1; index >= 0; index -= 1) {
    const item = history[index];
    if (item.action_id !== actionId || item.event !== undefined) continue;
    if (item.status === "failed") return "failed";
    if (item.status === "cancelled") return "cancelled";
  }
  return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object");
}
