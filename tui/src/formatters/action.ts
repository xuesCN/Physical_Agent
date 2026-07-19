import type { ActionItem } from "../types.js";

const SENSITIVE_PARAM = /token|secret|password|key/i;
const VALUE_LIMIT = 60;
const REDACTED = "[redacted]";
const CIRCULAR = "[circular]";

export function formatActionInvocation(action: ActionItem): string {
  const params = Object.entries(action.params ?? {})
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}=${formatParamValue(key, value)}`);
  return `${action.robot}.${action.capability}(${params.join(", ")})`;
}

function formatParamValue(key: string, value: unknown): string {
  if (SENSITIVE_PARAM.test(key)) return JSON.stringify(REDACTED);
  const serialized = serializeParamValue(value);
  const characters = [...serialized];
  return characters.length <= VALUE_LIMIT
    ? serialized
    : `${characters.slice(0, VALUE_LIMIT - 1).join("")}…`;
}

function serializeParamValue(value: unknown): string {
  try {
    return JSON.stringify(redactSensitiveFields(value, new WeakSet<object>())) ?? String(value);
  } catch {
    return String(value);
  }
}

function redactSensitiveFields(value: unknown, ancestors: WeakSet<object>): unknown {
  if (!value || typeof value !== "object") return value;
  if (ancestors.has(value)) return CIRCULAR;

  ancestors.add(value);
  try {
    if (Array.isArray(value)) {
      return value.map((item) => redactSensitiveFields(item, ancestors));
    }

    const sanitized: Record<string, unknown> = Object.create(null) as Record<string, unknown>;
    for (const [key, nestedValue] of Object.entries(value).sort(([left], [right]) => left.localeCompare(right))) {
      sanitized[key] = SENSITIVE_PARAM.test(key)
        ? REDACTED
        : redactSensitiveFields(nestedValue, ancestors);
    }
    return sanitized;
  } finally {
    ancestors.delete(value);
  }
}
