import type { ActionItem } from "./types";

const ACTION_DRAFT_FENCE = /```action-draft\s*([\s\S]*?)```/gi;

export interface ParsedActionDrafts {
  markdown: string;
  drafts: ActionItem[];
}

export function parseActionDrafts(content: string): ParsedActionDrafts {
  const drafts: ActionItem[] = [];
  let invalid = false;
  const markdown = content.replace(ACTION_DRAFT_FENCE, (_match, body: string) => {
    const parsed = parseDraftJson(body);
    if (!parsed.length) {
      invalid = true;
      return _match;
    }
    drafts.push(...parsed);
    return "";
  });

  if (invalid) {
    return { markdown: content, drafts: [] };
  }
  return { markdown: markdown.trim() || content, drafts };
}

export function resolveActionDrafts(
  content: string,
  agentOutput: unknown,
  options: { allowFenceFallback?: boolean } = {}
): ParsedActionDrafts {
  const compatibility = parseActionDrafts(content);
  const structured = structuredDraftActions(agentOutput);
  if (structured === null) {
    return options.allowFenceFallback === false
      ? { markdown: content, drafts: [] }
      : compatibility;
  }
  return {
    markdown: compatibility.drafts.length ? compatibility.markdown : content,
    drafts: structured
  };
}

/** Accept only the compiler-owned draft envelope, never a convenient lookalike. */
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

function parseDraftJson(body: string): ActionItem[] {
  let value: unknown;
  try {
    value = JSON.parse(body.trim());
  } catch {
    return [];
  }
  const items = Array.isArray(value) ? value : [value];
  const drafts: ActionItem[] = [];
  for (const [index, item] of items.entries()) {
    const draft = coerceDraft(item, index);
    if (!draft) {
      return [];
    }
    drafts.push(draft);
  }
  return drafts;
}

function coerceDraft(value: unknown, index: number): ActionItem | null {
  if (!isRecord(value)) {
    return null;
  }
  const robot = stringField(value.robot);
  const capability = stringField(value.capability);
  if (!robot || !capability) {
    return null;
  }
  const params = isRecord(value.params) ? value.params : {};
  const dependsOn = Array.isArray(value.depends_on)
    ? value.depends_on.map((item) => String(item)).filter(Boolean)
    : [];
  const draft: ActionItem = {
    id: stringField(value.id) || `act_chat_${Date.now()}_${index + 1}`,
    robot,
    capability,
    params,
    reason: stringField(value.reason) || "Drafted from chat.",
    depends_on: dependsOn
  };
  if (isRecord(value.metadata)) {
    draft.metadata = value.metadata;
  }
  return draft;
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
