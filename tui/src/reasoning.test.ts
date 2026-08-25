import assert from "node:assert/strict";
import test from "node:test";
import {
  collapsedReasoningSummary,
  reasoningSummaryFromMessage
} from "./reasoning.js";

test("reasoning metadata is assistant-only and renders as a bounded collapsed preview", () => {
  assert.equal(
    reasoningSummaryFromMessage({
      role: "assistant",
      content: "answer",
      metadata: { reasoning_summary: "  checked constraints  " }
    }),
    "checked constraints"
  );
  assert.equal(
    reasoningSummaryFromMessage({
      role: "user",
      content: "question",
      metadata: { reasoning_summary: "must not render" }
    }),
    null
  );

  const collapsed = collapsedReasoningSummary("line one\nline two " + "x".repeat(120));
  assert.match(collapsed, /^模型推理摘要（仅供参考，不是决策依据；默认折叠） · line one line two /);
  assert.match(collapsed, /…$/);
  assert.ok(collapsed.length < 160);
});
