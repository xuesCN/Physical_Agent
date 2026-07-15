import type { ActionItem } from "./types";

/** Accept only the compiler-owned draft envelope, never reply text or a lookalike. */
export function structuredDraftActions(value: unknown): ActionItem[] | null {
  if (!isRecord(value)) {
    return null;
  }
  if (
    value.schema !== "physical-agent/agent-output/v1" ||
    value.lifecycle !== "draft" ||
    value.decision !== "propose" ||
    !Array.isArray(value.actions)
  ) {
    return null;
  }

  const actions: ActionItem[] = [];
  for (const item of value.actions) {
    const action = coerceStructuredAction(item);
    if (!action) {
      return null;
    }
    actions.push(action);
  }
  return actions;
}

function coerceStructuredAction(value: unknown): ActionItem | null {
  if (!isRecord(value)) {
    return null;
  }
  const id = stringField(value.id);
  const robot = stringField(value.robot);
  const capability = stringField(value.capability);
  if (!id || !robot || !capability || !isRecord(value.params)) {
    return null;
  }
  if (
    !Array.isArray(value.depends_on) ||
    value.depends_on.some((dependency) => typeof dependency !== "string")
  ) {
    return null;
  }
  if (value.metadata !== undefined && !isRecord(value.metadata)) {
    return null;
  }
  return {
    id,
    robot,
    capability,
    params: value.params,
    reason: typeof value.reason === "string" ? value.reason : null,
    depends_on: [...value.depends_on],
    metadata: isRecord(value.metadata) ? value.metadata : undefined
  };
}

function stringField(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
