import type { ChatMessage } from "./types.js";

const REASONING_LABEL = "模型推理摘要（仅供参考，不是决策依据；默认折叠）";
const REASONING_PREVIEW_CHARS = 96;

export function reasoningSummaryFromMessage(message: ChatMessage): string | null {
  if (message.role !== "assistant") {
    return null;
  }
  const value = message.metadata?.reasoning_summary;
  if (typeof value !== "string") {
    return null;
  }
  const normalized = value.trim();
  return normalized || null;
}

export function collapsedReasoningSummary(value: string): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  const preview = normalized.length > REASONING_PREVIEW_CHARS
    ? `${normalized.slice(0, REASONING_PREVIEW_CHARS - 1)}…`
    : normalized;
  return preview ? `${REASONING_LABEL} · ${preview}` : REASONING_LABEL;
}
