# T4.1 MOCE Conversational Transcript Follow-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix terminal-width overflow and deliver a color-distinct `>` / `⏺` conversational activity feed with canonical terminal action records and a read-only execution-approval notice, without changing any approval or safety behavior.

**Architecture:** Keep `Transcript` as the only Ink `Static` owner and constrain it to the root terminal width. Chat and observed terminal actions enter one monotonically appended `TranscriptEntry[]`; action outcomes come only from Action Board buckets plus matching action-result feedback. A dynamic `ExecutionApprovalNotice` reads pending approval metadata and displays the existing `/approve` and `/reject` commands without intercepting input.

**Tech Stack:** TypeScript 5.7, React 18, Ink 5.2.1, Node test runner, `ink-testing-library`, `string-width` 7.2.0, JSON scenario harness.

## Global Constraints

- Production changes are limited to `tui/`; documentation changes are limited to the T4.1 design/plan, SPEC, PLAYBOOK, and REFACTORING records.
- Do not modify FastAPI, SQLite, Action/feedback wire shapes, watch, driver, SafetyGate, `SAFETY.md`, approval endpoints, parser semantics, or command behavior.
- `>` uses `THEME.success`; `⏺` uses `THEME.brandAccent`; `draft ◇` stays `THEME.warning`; `⎿` uses `THEME.muted`.
- Finalized and streaming content must share the same shrinkable row layout. Finalized assistant content alone continues through `FinalizedText`; streaming content remains literal.
- `Static` receives one append-only list. Previously emitted items are never inserted, reordered, replaced, or deleted.
- Initial and never-observed-as-active terminal actions are baseline-only. Only an action ID observed in `pending`/`in_progress` during this tracker generation may emit when it later becomes terminal. `completed` maps to `done`; approval rejection maps to `rejected`; other cancelled actions wait for matching action-result feedback before emitting `failed` or `cancelled`.
- Never display a client-observed action completion time as an execution timestamp.
- Pending approval UI is read-only and must state that watch SafetyGate still runs after approval.
- Preserve the five pre-existing untracked user files reported by `git status`; never stage, edit, or delete them. Work in-place on the already-dedicated `codex/agent-core-refactor` branch so the user's open IDE remains attached to the implementation.

## File Structure

- Create `docs/brief-t4-1-tui-conversational-transcript.zh-CN.md`: temporary round brief required by `AGENTS.md`; delete before closure.
- Create `tui/src/components/MessageRow.tsx`: role marker/color mapping and fixed-marker/shrinkable-body layout.
- Create `tui/src/formatters/action.ts`: deterministic, bounded, redacted action invocation formatting.
- Create `tui/src/activity.ts`: Action Board observation tracker and terminal outcome derivation.
- Create `tui/src/activity.test.ts`: pure transition, feedback-race, deduplication, and reset tests.
- Create `tui/src/components/ActionActivityItem.tsx`: immutable two-line action/result renderer.
- Create `tui/src/components/ExecutionApprovalNotice.tsx`: read-only pending approval box.
- Modify `tui/src/types.ts`: discriminated chat/action transcript entries and outcome type.
- Modify `tui/src/components/Transcript.tsx`: one width-constrained Static feed rendering chat and action entries.
- Modify `tui/src/components/ChatPanel.tsx`: streaming assistant uses `MessageRow`.
- Modify `tui/src/App.tsx`: append chat/action observations to one list, reset tracker generation, and show the approval notice in chat view.
- Modify `tui/src/components/render.test.tsx`: marker/color, action item, and approval notice component contracts.
- Modify `tui/tests/scenario-runner.test.tsx`: display-width helper, width matrix, App activity integration, physical stdout once-only proof, and fixtures.
- Modify `tui/tests/scenarios/chat.scenario` and `tui/tests/scenarios/actions.scenario`: new glyphs and canonical action/approval expectations.
- Modify `tui/package.json` and `tui/package-lock.json`: declare existing `string-width` 7.2.0 as a direct dev dependency.
- Modify `docs/SPEC.zh-CN.md`, `docs/PLAYBOOK.zh-CN.md`, `docs/REFACTORING.zh-CN.md`, and the T4.1 design: close the ledger with exact local/remote evidence.

---

### Task 1: Display-width guard and shared conversational row

**Files:**
- Create: `docs/brief-t4-1-tui-conversational-transcript.zh-CN.md`
- Create: `tui/src/components/MessageRow.tsx`
- Modify: `tui/package.json`
- Modify: `tui/package-lock.json`
- Modify: `tui/src/components/Transcript.tsx`
- Modify: `tui/src/components/ChatPanel.tsx`
- Modify: `tui/src/components/render.test.tsx`
- Modify: `tui/tests/scenario-runner.test.tsx`
- Modify: `tui/tests/scenarios/chat.scenario`

**Interfaces:**
- Produces: `rolePresentation(role: string): { marker: string; color: string }`
- Produces: `MessageRow({ marker, color, children }): React.JSX.Element`
- Preserves: `Transcript({ entries, columns })` and `ChatPanel` public props.

- [ ] **Step 1: Create the required temporary round brief before touching TUI code**

```markdown
# T4.1 轮次 brief：对话式 transcript 与终端宽度修复

## 范围

- 仅修改 Ink TUI 展示与测试。
- 修复 finalized/streaming 的 prefix 宽度预算、display width 与悬挂缩进。
- 角色视觉切换为绿色 `>`、MOCE 蓝 `⏺`，保留 warning `draft ◇`。
- 后续任务从 canonical Action Board 追加本地 terminal activity，并只读提示原审批命令。

## 验收

- 24/48/100 列不产生超宽物理行；emoji/CJK/combining/ZWJ 用 display width 验证。
- finalized 与 streaming 续行对齐正文起点，不丢字、不从终端第 0 列二次硬折。
- 现有命令、审批、SafetyGate、API 与状态语义不变。
- TUI typecheck/test/build、Python safety/full、独立 review 与远端 CI 全绿。

## 范围外

- 不实现 y/n/a 单键审批、session grant、Gate override 或完成时间戳。
- 不改 FastAPI、SQLite、watch、driver、SAFETY.md 或 React Dashboard。
```

- [ ] **Step 2: Declare display-width test support and prove the helper semantics**

Add `"string-width": "7.2.0"` to both root `devDependencies` objects in `tui/package.json` and `tui/package-lock.json`; reuse the existing `node_modules/string-width` lock entry without changing its resolved package.

At the top of `tui/tests/scenario-runner.test.tsx` add:

```tsx
import stringWidth from "string-width";
```

Replace the code-point assertion in `assertMaxLineWidth` with:

```tsx
const width = stringWidth(line);
assert.equal(
  width <= maximum,
  true,
  `frame ${frameIndex + 1} line is ${width} columns, exceeds ${maximum}: ${line}`
);
```

Add this harness contract test:

```tsx
test("display-width guard counts emoji and CJK terminal cells", () => {
  assert.equal([..."👋"].length, 1);
  assert.equal(stringWidth("👋"), 2);
  assert.equal(stringWidth("中"), 2);
  assert.equal(stringWidth("e\u0301"), 1);
  assert.equal(stringWidth("👨‍👩‍👧‍👦"), 2);
});
```

Run:

```powershell
$env:CI='false'; node --import tsx --test tests/scenario-runner.test.tsx
```

Expected: PASS, with the existing scenario count plus the new helper contract.

- [ ] **Step 3: Write failing finalized and streaming row tests**

Import `Transcript` and `ChatPanel` into `tui/tests/scenario-runner.test.tsx`, then add:

```tsx
test("48-column finalized and streaming chat use display-safe hanging indents", () => {
  const content = "Hello! 👋 I can see the arm is idle on the table, with a red block and a tray visible nearby. Please tell me what to do next.";
  const finalized = renderTui(
    <Transcript columns={48} entries={[{ id: "a1", role: "assistant", content }]} />,
    48
  );
  const streaming = renderTui(
    <ChatPanel hasTranscript streamingText={content} streaming />,
    48
  );

  try {
    assertMaxLineWidth(finalized, 48);
    assertMaxLineWidth(streaming, 48);
    assertHangingBody(latestSnapshot(finalized), "⏺", content);
    assertHangingBody(latestSnapshot(streaming), "⏺", content);
  } finally {
    finalized.unmount();
    streaming.unmount();
  }
});
```

Add the exact helper below `assertMaxLineWidth`:

```tsx
function assertHangingBody(output: string, marker: string, expected: string): void {
  const lines = normalizeOutput(output).split("\n");
  const start = lines.findIndex((line) => line.trimStart().startsWith(`${marker} `));
  assert.notEqual(start, -1, `missing ${marker} activity row`);
  const firstLine = lines[start];
  const leadingSpaces = firstLine.length - firstLine.trimStart().length;
  const bodyIndex = leadingSpaces + marker.length + 1;
  const bodyColumn = stringWidth(firstLine.slice(0, bodyIndex));
  const bodyLines: string[] = [];
  for (let index = start; index < lines.length; index += 1) {
    const line = lines[index];
    if (index === start) {
      bodyLines.push(line.slice(bodyIndex));
      continue;
    }
    const continuationSpaces = line.length - line.trimStart().length;
    if (!line.trim() || stringWidth(line.slice(0, continuationSpaces)) !== bodyColumn) {
      break;
    }
    bodyLines.push(line.slice(continuationSpaces));
  }
  assert.equal(bodyLines.join(" ").replace(/\s+/g, " ").trim(), expected);
}
```

Run:

```powershell
$env:CI='false'; node --import tsx --test tests/scenario-runner.test.tsx
```

Expected: FAIL because current finalized output can exceed 48 columns and both paths still render `moce │` instead of `⏺`.

- [ ] **Step 4: Implement the minimal shared row and role presentation**

Create `tui/src/components/MessageRow.tsx`:

```tsx
import React from "react";
import { Box, Text } from "ink";
import { THEME } from "../theme.js";

export interface RolePresentation {
  marker: string;
  color: string;
}

export function rolePresentation(role: string): RolePresentation {
  if (role === "user") return { marker: ">", color: THEME.success };
  if (role === "assistant") return { marker: "⏺", color: THEME.brandAccent };
  if (role === "draft") return { marker: "draft ◇", color: THEME.warning };
  return { marker: `${role} │`, color: THEME.muted };
}

export function MessageRow({
  marker,
  color,
  children
}: {
  marker: string;
  color: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <Box flexDirection="row" width="100%">
      <Box flexShrink={0} marginRight={1}>
        <Text color={color}>{marker}</Text>
      </Box>
      <Box flexDirection="column" flexGrow={1} flexShrink={1} flexBasis={0}>
        {children}
      </Box>
    </Box>
  );
}
```

In `Transcript.tsx`, set `<Static items={items} style={{ width: "100%" }}>`, wrap each chat entry in one width-constrained outer row, call `rolePresentation`, and render its body through `MessageRow`. Keep `FinalizedText` only for role `assistant`; all other roles keep `normalizeTerminalText`. There must be exactly one horizontal-padding owner per row. The physical test must prove that the first-line body and every continuation begin at the same display-cell column even with bare `⏺`; if Ink's marker measurement disagrees with physical output, fix the marker/gap layout without changing the visible glyph or its `THEME.brandAccent` color.

In `ChatPanel.tsx`, add `width="100%"` to the outer box, remove any duplicate horizontal padding around the shared row (retaining one row-level padding owner), and replace the nested streaming `<Text>` with:

```tsx
const assistant = rolePresentation("assistant");

{streamingText ? (
  <MessageRow marker={assistant.marker} color={assistant.color}>
    <Text>{normalizeTerminalText(streamingText)}</Text>
  </MessageRow>
) : null}
```

- [ ] **Step 5: Update marker/color contracts and existing chat expectations**

In `render.test.tsx`, import `rolePresentation` and add:

```tsx
test("conversation markers keep user and MOCE colors distinct", () => {
  assert.deepEqual(rolePresentation("user"), { marker: ">", color: THEME.success });
  assert.deepEqual(rolePresentation("assistant"), { marker: "⏺", color: THEME.brandAccent });
  assert.deepEqual(rolePresentation("draft"), { marker: "draft ◇", color: THEME.warning });
  assert.deepEqual(rolePresentation("system"), { marker: "system │", color: THEME.muted });
});
```

Change component/scenario assertions from `you ›` to `>`, from `moce │` to `⏺`, and keep `draft ◇` unchanged. In `tui/tests/scenarios/chat.scenario`, the successful chat step must contain:

```json
"expectOutput": ["> hello robot", "⏺ Hello from agent"]
```

- [ ] **Step 6: Verify GREEN and commit the width/role slice**

Run:

```powershell
$env:CI='false'; node --import tsx --test src/components/render.test.tsx tests/scenario-runner.test.tsx
npm.cmd run typecheck
```

Expected: both test files PASS; typecheck exits 0; every measured 48-column line is at most 48 display cells.

Commit only Task 1 files:

```powershell
git add -- tui/package.json tui/package-lock.json tui/src/components/MessageRow.tsx tui/src/components/Transcript.tsx tui/src/components/ChatPanel.tsx tui/src/components/render.test.tsx tui/tests/scenario-runner.test.tsx tui/tests/scenarios/chat.scenario
git commit -m "fix(tui): constrain conversational transcript width"
```

Do not stage the temporary brief.

---

### Task 2: Canonical terminal action activity model and renderer

**Files:**
- Create: `tui/src/formatters/action.ts`
- Create: `tui/src/activity.ts`
- Create: `tui/src/activity.test.ts`
- Create: `tui/src/components/ActionActivityItem.tsx`
- Modify: `tui/src/types.ts`
- Modify: `tui/src/components/Transcript.tsx`
- Modify: `tui/src/components/render.test.tsx`
- Modify: `tui/src/App.tsx`

**Interfaces:**
- Produces: `ActionActivityOutcome = "done" | "failed" | "cancelled" | "rejected"`
- Produces: discriminated `ChatTranscriptEntry | ActionTranscriptEntry`
- Produces: `formatActionInvocation(action: ActionItem): string`
- Produces: `createActionActivityTracker()`, `collectActionActivityEntries(state, tracker)`, and `resetActionActivityTracker(tracker)`
- Consumes: Task 1 `MessageRow`.

- [ ] **Step 1: Write failing formatter and transition tests**

Create `tui/src/activity.test.ts` with these contracts:

```tsx
import assert from "node:assert/strict";
import test from "node:test";
import {
  collectActionActivityEntries,
  createActionActivityTracker,
  resetActionActivityTracker
} from "./activity.js";
import { formatActionInvocation } from "./formatters/action.js";
import type { AgentState } from "./types.js";

const pendingState = stateWith({
  pending: [{ id: "act_1", robot: "arm_1", capability: "move_to", params: { z: 0, x: 120, y: 45 }, metadata: {} }]
});

test("action invocation is stable, bounded, and redacts sensitive params", () => {
  assert.equal(
    formatActionInvocation({
      id: "act_1",
      robot: "arm_1",
      capability: "move_to",
      params: { z: 0, token: "secret-value", x: 120, y: 45 }
    }),
    "arm_1.move_to(token=\"[redacted]\", x=120, y=45, z=0)"
  );
});

test("initial and never-active terminal actions are baseline-only", () => {
  const historical = stateWith({
    completed: [{ id: "act_old", robot: "arm_1", capability: "move_to", metadata: {} }]
  });
  const tracker = createActionActivityTracker();
  assert.deepEqual(collectActionActivityEntries(historical, tracker), []);
  const unseen = stateWith({
    completed: [
      ...(historical.actions?.completed ?? []),
      { id: "act_unseen", robot: "arm_1", capability: "grasp", metadata: {} }
    ]
  });
  assert.deepEqual(collectActionActivityEntries(unseen, tracker), []);
});

test("an observed active action emits completed exactly once", () => {
  const tracker = createActionActivityTracker();
  assert.deepEqual(collectActionActivityEntries(pendingState, tracker), []);
  const completed = stateWith({
    completed: [{ id: "act_1", robot: "arm_1", capability: "move_to", params: { x: 120 }, metadata: {} }]
  });
  assert.deepEqual(collectActionActivityEntries(completed, tracker).map((item) => item.outcome), ["done"]);
  assert.deepEqual(collectActionActivityEntries(completed, tracker), []);
});

test("cancelled ignores Gate and expectation feedback, then waits for action-result", () => {
  const tracker = createActionActivityTracker();
  collectActionActivityEntries(pendingState, tracker);
  const cancelled: AgentState = {
    ...stateWith({
      cancelled: [{ id: "act_1", robot: "arm_1", capability: "move_to", metadata: {} }]
    }),
    feedback: {
      history: [
        { event: "safety_gate", action_id: "act_1", status: "failed" },
        { event: "expectation_check", action_id: "act_1", status: "failed" }
      ]
    }
  };
  assert.deepEqual(collectActionActivityEntries(cancelled, tracker), []);
  const withResult: AgentState = {
    ...cancelled,
    feedback: {
      history: [
        ...(cancelled.feedback?.history ?? []),
        { action_id: "act_1", status: "failed", message: "driver failed" }
      ]
    }
  };
  assert.deepEqual(collectActionActivityEntries(withResult, tracker).map((item) => item.outcome), ["failed"]);
  assert.deepEqual(collectActionActivityEntries(withResult, tracker), []);
});

test("approval rejection emits rejected without treating Gate feedback as action result", () => {
  const tracker = createActionActivityTracker();
  collectActionActivityEntries(pendingState, tracker);
  const rejected: AgentState = {
    ...stateWith({
      cancelled: [{
        id: "act_1",
        robot: "arm_1",
        capability: "move_to",
        metadata: { approval: { required: true, status: "rejected" } }
      }]
    }),
    feedback: { history: [{ event: "safety_gate", action_id: "act_1", status: "failed" }] }
  };
  assert.deepEqual(collectActionActivityEntries(rejected, tracker).map((item) => item.outcome), ["rejected"]);
});

test("reset increments generation so a reused action id can emit again", () => {
  const tracker = createActionActivityTracker();
  collectActionActivityEntries(pendingState, tracker);
  const completed = stateWith({ completed: [{ id: "act_1", robot: "arm_1", capability: "move_to", metadata: {} }] });
  const first = collectActionActivityEntries(completed, tracker)[0];
  resetActionActivityTracker(tracker);
  collectActionActivityEntries(pendingState, tracker);
  const second = collectActionActivityEntries(completed, tracker)[0];
  assert.notEqual(first.id, second.id);
});

function stateWith(actions: AgentState["actions"]): AgentState {
  return {
    ready: true,
    actions: {
      pending: actions?.pending ?? [],
      in_progress: actions?.in_progress ?? [],
      completed: actions?.completed ?? [],
      cancelled: actions?.cancelled ?? []
    }
  };
}
```

Run:

```powershell
$env:CI='false'; node --import tsx --test src/activity.test.ts
```

Expected: FAIL because the activity and formatter modules do not exist.

- [ ] **Step 2: Add discriminated activity types**

Replace `TranscriptEntry` in `tui/src/types.ts` with:

```tsx
export type ActionActivityOutcome = "done" | "failed" | "cancelled" | "rejected";

export interface ChatTranscriptEntry {
  kind: "chat";
  id: string;
  role: string;
  content: string;
  created_at?: string;
}

export interface ActionTranscriptEntry {
  kind: "action";
  id: string;
  action: ActionItem;
  outcome: ActionActivityOutcome;
}

export type TranscriptEntry = ChatTranscriptEntry | ActionTranscriptEntry;
```

Add `kind: "chat"` to both `appendLocalChat` and server-message additions in `App.tsx`, and to all direct `Transcript` test fixtures.

- [ ] **Step 3: Implement deterministic action formatting**

Create `tui/src/formatters/action.ts`:

```tsx
import type { ActionItem } from "../types.js";

const SENSITIVE_PARAM = /(?:^|[_-])(api[_-]?key|key|password|secret|token)(?:$|[_-])/i;
const VALUE_LIMIT = 60;

export function formatActionInvocation(action: ActionItem): string {
  const params = Object.entries(action.params ?? {})
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}=${formatParamValue(key, value)}`);
  return `${action.robot}.${action.capability}(${params.join(", ")})`;
}

function formatParamValue(key: string, value: unknown): string {
  if (SENSITIVE_PARAM.test(key)) return "\"[redacted]\"";
  const serialized = typeof value === "string" ? JSON.stringify(value) : JSON.stringify(value) ?? String(value);
  const characters = [...serialized];
  return characters.length <= VALUE_LIMIT
    ? serialized
    : `${characters.slice(0, VALUE_LIMIT - 1).join("")}…`;
}
```

- [ ] **Step 4: Implement the observation tracker with the cancelled/result barrier**

Create `tui/src/activity.ts`:

```tsx
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
      if (action.status === "completed" || action.status === "cancelled") {
        tracker.closed.add(action.id);
      } else {
        tracker.active.add(action.id);
      }
    }
    return [];
  }

  const additions: ActionTranscriptEntry[] = [];
  for (const action of actions) {
    const terminal = action.status === "completed" || action.status === "cancelled";
    if (!terminal) {
      if (!tracker.closed.has(action.id)) tracker.active.add(action.id);
      continue;
    }
    if (tracker.closed.has(action.id)) continue;
    if (!tracker.active.has(action.id)) {
      tracker.closed.add(action.id);
      continue;
    }
    const outcome = terminalOutcome(state, action);
    if (!outcome) continue;
    tracker.active.delete(action.id);
    tracker.closed.add(action.id);
    additions.push({
      kind: "action",
      id: `action-${tracker.generation}-${action.id}`,
      action,
      outcome
    });
  }
  return additions;
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
```

The implementation may factor this reducer differently, but these invariants are binding: the first non-null action snapshot establishes a baseline; only IDs already active in a previous observation can emit; an eligible cancellation without action-result stays active so a later feedback-only snapshot can complete it; a terminal ID never seen active is closed silently so later feedback cannot backfill history.

- [ ] **Step 5: Write the failing action renderer/order test**

In `render.test.tsx`, add a mixed feed test that passes chat → action → chat in that exact array order and asserts the rendered indexes increase:

```tsx
test("Transcript renders immutable action activity in append order", () => {
  const view = render(
    <Transcript
      columns={100}
      entries={[
        { kind: "chat", id: "u1", role: "user", content: "move it" },
        {
          kind: "action",
          id: "action-0-act_1",
          action: { id: "act_1", robot: "arm_1", capability: "move_to", params: { x: 120, y: 45, z: 0 } },
          outcome: "done"
        },
        { kind: "chat", id: "a1", role: "assistant", content: "Finished." }
      ]}
    />
  );
  const frame = view.lastFrame() ?? "";
  const user = frame.indexOf("> move it");
  const action = frame.indexOf("⏺ arm_1.move_to(x=120, y=45, z=0)");
  const result = frame.indexOf("⎿ done");
  const assistant = frame.indexOf("⏺ Finished.");
  assert.ok(user >= 0 && user < action && action < result && result < assistant);
  view.unmount();
});
```

Run:

```powershell
$env:CI='false'; node --import tsx --test src/components/render.test.tsx
```

Expected: FAIL because `Transcript` does not render `kind: "action"` entries.

- [ ] **Step 6: Implement the immutable action renderer and Transcript branch**

Create `tui/src/components/ActionActivityItem.tsx`:

```tsx
import React from "react";
import { Text } from "ink";
import type { ActionTranscriptEntry } from "../types.js";
import { THEME } from "../theme.js";
import { formatActionInvocation } from "../formatters/action.js";
import { MessageRow } from "./MessageRow.js";

export function ActionActivityItem({ entry }: { entry: ActionTranscriptEntry }): React.JSX.Element {
  return (
    <MessageRow marker="⏺" color={THEME.brandAccent}>
      <Text>{formatActionInvocation(entry.action)}</Text>
      <Text color={THEME.muted}>⎿ {entry.outcome}</Text>
    </MessageRow>
  );
}
```

In `Transcript.tsx`, branch on `entry.kind`. Render action entries through `ActionActivityItem`; render chat entries through the Task 1 role row. Keep the outer `Box paddingX={1} width="100%"` common to both branches so action result continuation aligns at the two-cell body indent.

- [ ] **Step 7: Verify GREEN and commit the action model slice**

Run:

```powershell
$env:CI='false'; node --import tsx --test src/activity.test.ts src/components/render.test.tsx
npm.cmd run typecheck
```

Expected: all tests PASS and typecheck exits 0.

Commit:

```powershell
git add -- tui/src/types.ts tui/src/formatters/action.ts tui/src/activity.ts tui/src/activity.test.ts tui/src/components/ActionActivityItem.tsx tui/src/components/Transcript.tsx tui/src/components/render.test.tsx tui/src/App.tsx
git commit -m "feat(tui): render canonical terminal action activity"
```

---

### Task 3: App integration and read-only execution approval notice

**Files:**
- Create: `tui/src/components/ExecutionApprovalNotice.tsx`
- Modify: `tui/src/App.tsx`
- Modify: `tui/src/components/render.test.tsx`
- Modify: `tui/tests/scenario-runner.test.tsx`
- Modify: `tui/tests/scenarios/actions.scenario`

**Interfaces:**
- Consumes: Task 2 activity tracker and discriminated feed entries.
- Produces: `pendingExecutionApprovals(state: AgentState | null): ActionItem[]`
- Produces: `ExecutionApprovalNotice({ state }): React.JSX.Element | null`
- Preserves: `/approve`, `/reject`, `CommandInput`, and `/view actions` behavior.

- [ ] **Step 1: Write failing read-only approval notice tests**

In `render.test.tsx`, add:

```tsx
test("ExecutionApprovalNotice shows existing commands and preserves SafetyGate semantics", () => {
  const state: AgentState = {
    ready: true,
    actions: {
      pending: [
        {
          id: "act_1",
          robot: "arm_1",
          capability: "lift",
          params: { height: 0.2 },
          metadata: { approval: { required: true, status: "pending" } }
        },
        {
          id: "act_2",
          robot: "arm_1",
          capability: "grasp",
          metadata: { approval: { required: true, status: "pending" } }
        }
      ],
      completed: [],
      cancelled: []
    }
  };
  const view = render(<ExecutionApprovalNotice state={state} />);
  const frame = view.lastFrame() ?? "";
  assert.match(frame, /Safety Gate · Execution approval/);
  assert.match(frame, /1\/2/);
  assert.match(frame, /arm_1\.lift\(height=0\.2\)/);
  assert.match(frame, /等待人工批准/);
  assert.match(frame, /批准后仍需 watch SafetyGate 校验/);
  assert.match(frame, /\/approve act_1/);
  assert.match(frame, /\/reject act_1 <reason>/);
  assert.doesNotMatch(frame, /\[y\]|\[n\]|\[a\]/);
  view.unmount();
});

test("ExecutionApprovalNotice ignores approved and not-required actions", () => {
  const view = render(
    <ExecutionApprovalNotice
      state={{
        ready: true,
        actions: {
          pending: [{
            id: "act_1",
            robot: "arm_1",
            capability: "lift",
            metadata: { approval: { required: true, status: "approved" } }
          }]
        }
      }}
    />
  );
  assert.equal(view.lastFrame() ?? "", "");
  view.unmount();
});
```

Run:

```powershell
$env:CI='false'; node --import tsx --test src/components/render.test.tsx
```

Expected: FAIL because `ExecutionApprovalNotice` does not exist.

- [ ] **Step 2: Implement the read-only notice**

Create `tui/src/components/ExecutionApprovalNotice.tsx`:

```tsx
import React from "react";
import { Box, Text } from "ink";
import type { ActionItem, AgentState } from "../types.js";
import { THEME } from "../theme.js";
import { formatActionInvocation } from "../formatters/action.js";

export function pendingExecutionApprovals(state: AgentState | null): ActionItem[] {
  return (state?.actions?.pending ?? []).filter((action) => {
    const approval = action.metadata?.approval;
    return Boolean(
      approval &&
      typeof approval === "object" &&
      (approval as Record<string, unknown>).required === true &&
      (approval as Record<string, unknown>).status === "pending"
    );
  });
}

export function ExecutionApprovalNotice({ state }: { state: AgentState | null }): React.JSX.Element | null {
  const approvals = pendingExecutionApprovals(state);
  const action = approvals[0];
  if (!action) return null;
  return (
    <Box width="100%" paddingX={1} flexDirection="column" borderStyle="round" borderColor={THEME.safety}>
      <Text bold color={THEME.safety}>Safety Gate · Execution approval <Text color={THEME.muted}>1/{approvals.length}</Text></Text>
      <Text>{formatActionInvocation(action)} 等待人工批准</Text>
      <Text color={THEME.muted}>批准后仍需 watch SafetyGate 校验</Text>
      <Text color={THEME.brandAccent}>/approve {action.id}</Text>
      <Text color={THEME.muted}>/reject {action.id} &lt;reason&gt;</Text>
    </Box>
  );
}
```

- [ ] **Step 3: Write failing complete-App activity and once-only physical stdout tests**

Extend `stateFixtures` in `scenario-runner.test.tsx` with `beforeCompleted` and `afterCompleted` snapshots for the same action ID. The test must render `beforeCompleted` first so `act_done` is observed as pending/in-progress before the terminal snapshot:

```tsx
// beforeCompleted
pending: [{
  id: "act_done",
  robot: "arm_1",
  capability: "move_to",
  params: { x: 120, y: 45, z: 0 },
  status: "pending",
  metadata: {}
}]

// afterCompleted
completed: [{
  id: "act_done",
  robot: "arm_1",
  capability: "move_to",
  params: { x: 120, y: 45, z: 0 },
  status: "completed",
  metadata: {}
}]
```

Add scenario/API steps that publish `beforeCompleted`, assert no terminal activity yet, and only then publish `afterCompleted`. A direct never-active completed snapshot must not be used as the positive fixture. The terminal response remains:

```json
{ "message": "Action act_done completed.", "state": "afterCompleted" }
```

Add a step before `/view actions`:

```json
{
  "input": "/task record completed move",
  "expectOutput": ["Action act_done completed.", "⏺ arm_1.move_to(x=120, y=45, z=0)", "⎿ done"],
  "expectCalls": { "submitTask": 2 },
  "expectState": { "actions.completed.0.id": "act_done" }
}
```

Update the earlier action steps so chat view expects the read-only notice, does not expect `approval unknown`, and expects the rejected terminal activity after `/reject act_002 unsafe workspace`:

```json
"expectOutput": ["Action act_002 rejected.", "⏺ arm_1.observe()", "⎿ rejected"]
```

Add a physical stdout test beside the existing Logo once-only tests. It must submit the second task, wait for `arm_1.move_to(x=120, y=45, z=0)`, run `/refresh`, and assert `assertPhysicalMarkerCount(view, "arm_1.move_to(x=120, y=45, z=0)", 1, "terminal action rerender")`.

Run:

```powershell
$env:CI='false'; node --import tsx --test tests/scenario-runner.test.tsx
```

Expected: FAIL because App does not collect action activity and chat view still renders `ActionsPanel` instead of the new notice.

- [ ] **Step 4: Wire the one-list observer into App and keep reset IDs safe**

In `App.tsx` import the tracker helpers and `ExecutionApprovalNotice`, then add:

```tsx
const actionActivityTrackerRef = useRef(createActionActivityTracker());

useEffect(() => {
  if (!state) return;
  const additions = collectActionActivityEntries(state, actionActivityTrackerRef.current);
  if (additions.length > 0) {
    setTranscriptEntries((previous) => [...previous, ...additions]);
  }
}, [state]);
```

Place this effect after the server chat-message effect so a full snapshot appends newly observed chat before its newly terminal action. Every chat append must contain `kind: "chat"`; never create a second action array for render-time concatenation.

In the successful reset branch, reset the generation before publishing the reset state:

```tsx
const response = await client.resetWorkspace(command.confirm);
resetActionActivityTracker(actionActivityTrackerRef.current);
setState(response.state);
setNotice(response.message);
```

Also reset the tracker before applying an SSE event whose `type === "workspace_reset"`; cover both reset paths. Reset only tracker state: never clear, reconstruct, or reorder entries already appended to `Static`.

In chat view replace the non-forced `<ActionsPanel>` with:

```tsx
<ExecutionApprovalNotice state={props.state} />
```

Keep the forced `ActionsPanel` in `/view actions` unchanged.

- [ ] **Step 5: Add responsive width coverage for action and approval components**

In `scenario-runner.test.tsx`, render a `Transcript` containing one action entry and render `ExecutionApprovalNotice` inside an explicitly constrained root at 24, 48, and 100 columns. For each finite width call `assertMaxLineWidth` and verify the action/result body rail remains aligned. At `columns=null`, assert compact Banner/no content loss only; do not compare against a missing numeric limit.

Use this action entry in all finite cases:

```tsx
{
  kind: "action",
  id: "action-0-act_1",
  action: { id: "act_1", robot: "arm_1", capability: "move_to", params: { x: 120, y: 45, z: 0 } },
  outcome: "done"
}
```

- [ ] **Step 6: Verify GREEN and commit the App integration slice**

Run:

```powershell
$env:CI='false'; node --import tsx --test src/activity.test.ts src/components/render.test.tsx tests/scenario-runner.test.tsx
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
```

Expected: targeted tests PASS; full TUI suite PASS; typecheck/build exit 0; physical action and Logo markers each print once.

Commit:

```powershell
git add -- tui/src/App.tsx tui/src/components/ExecutionApprovalNotice.tsx tui/src/components/render.test.tsx tui/tests/scenario-runner.test.tsx tui/tests/scenarios/actions.scenario
git commit -m "feat(tui): add action activity and approval notice"
```

---

### Task 4: Independent review, repository gates, and T4.1 closure

**Files:**
- Modify: `docs/SPEC.zh-CN.md`
- Modify: `docs/PLAYBOOK.zh-CN.md`
- Modify: `docs/REFACTORING.zh-CN.md`
- Modify: `docs/superpowers/specs/2026-07-19-tui-conversational-transcript-followup-design.md`
- Delete: `docs/brief-t4-1-tui-conversational-transcript.zh-CN.md`

**Interfaces:**
- Consumes: all prior task commits and exact test output.
- Produces: closed T4.1 ledger, local verification evidence, independent review result, pushed exact-head CI evidence.

- [ ] **Step 1: Invoke verification-before-completion and run the complete local gate**

Read and follow `superpowers:verification-before-completion`, then run from `tui/`:

```powershell
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
$env:CI='false'; node --import tsx --test src/activity.test.ts src/components/render.test.tsx tests/scenario-runner.test.tsx
```

Run from repository root:

```powershell
pytest tests/test_safety_boundaries.py tests/test_safety.py
pytest
git diff --check
rg -n "driver\.execute|physical_agent\.watch|physical_agent\.drivers|sqlite3" tui/src
```

Expected: all TUI commands exit 0; focused Python safety passes; full Python suite passes with only already-known warnings; `git diff --check` is empty; the TUI safety scan finds no forbidden production access. If `rg` returns no matches with exit code 1, record that as the expected clean scan rather than a test failure.

- [ ] **Step 2: Invoke requesting-code-review and close every actionable finding**

Read and follow `superpowers:requesting-code-review`. Give the reviewer the T4.1 design, this plan, the Task 1–3 commit range, and these explicit questions:

```text
1. Can any rendered physical line exceed stdout.columns after prefix/padding/display-width accounting?
2. Can draft, Gate feedback, expectation feedback, initial history, or duplicate snapshots become a false terminal action item?
3. Does cancelled wait for action-result feedback, including the two-snapshot failed race?
4. Is the Static feed truly monotonically appended and reset-safe?
5. Does the approval notice remain read-only and preserve /approve, /reject, watch, and SafetyGate semantics?
```

For each valid issue, add a failing regression test, observe RED, implement the smallest fix, rerun the affected and full TUI suites, and commit with `fix(tui): ...`. Re-review until Critical=0 and Important=0.

- [ ] **Step 3: Update living docs with actual evidence and delete the temporary brief**

Update the T4 section in `docs/PLAYBOOK.zh-CN.md` with a `T4.1 follow-up` paragraph that states:

```markdown
**T4.1 follow-up（2026-07-19）**：修复 `Static` auto-width 使正文未扣角色轨道而产生的终端二次硬换行；finalized/streaming 共用受约束的 `MessageRow`，用户 `>` 使用 success green，MOCE `⏺` 使用 brand blue，draft 保留 warning `draft ◇`。同一 append-only feed 只从 canonical Action Board 追加本 TUI 会话中新 terminal action；cancelled 在 action-result 到达前不固化。pending approval 仅显示既有 `/approve`、`/reject` 命令，并明确审批后仍过 watch SafetyGate。API、SQLite、watch、driver、SAFETY.md 与审批语义未修改。
```

Add a `T4.1` row to REFACTORING §1 containing the actual Task 1–3 and review-fix commit hashes. Append a `### T4.1：对话式 transcript 与终端宽度修复` subsection to REFACTORING §2 with the root cause, RED→GREEN evidence, output contract, cancelled/result race decision, and exact test counts observed in Step 1.

Change SPEC §4 T4.1 from 🟡 to ✅ only after Step 1 and Step 2 are green. Update the T4.1 design status from “待实现” to “已实现并通过本地验收”. Do not invent remote run IDs before they exist.

Delete the temporary brief:

```powershell
Remove-Item -LiteralPath docs/brief-t4-1-tui-conversational-transcript.zh-CN.md
```

- [ ] **Step 4: Verify the documentation closure and commit it**

Run:

```powershell
pytest tests/test_current_docs.py tests/test_safety_boundaries.py
git diff --check
git status --short
```

Expected: docs/safety tests PASS; diff check is empty; only intended tracked changes plus the five pre-existing untracked user files are visible.

Commit:

```powershell
git add -- docs/SPEC.zh-CN.md docs/PLAYBOOK.zh-CN.md docs/REFACTORING.zh-CN.md docs/superpowers/specs/2026-07-19-tui-conversational-transcript-followup-design.md
git commit -m "docs: close the T4.1 transcript follow-up"
```

- [ ] **Step 5: Push, verify exact-head CI, and record only observed remote facts**

Push the current branch:

```powershell
git push fork codex/agent-core-refactor
```

Verify the Push and draft-PR workflows both target the exact implementation/docs HEAD and complete successfully. Record their real run IDs, head SHA, and per-job conclusions in SPEC T4.1, PLAYBOOK T4.1, and REFACTORING T4.1. Commit only that observed evidence:

```powershell
git add -- docs/SPEC.zh-CN.md docs/PLAYBOOK.zh-CN.md docs/REFACTORING.zh-CN.md
git commit -m "docs: record T4.1 exact-head CI evidence"
git push fork codex/agent-core-refactor
```

Finally confirm:

```powershell
git rev-list --left-right --count fork/codex/agent-core-refactor...HEAD
git status --short --branch
```

Expected: ahead/behind is `0 0`; only the five protected pre-existing untracked user files remain; the PR stays OPEN and draft; no feature-freeze status changes beyond completed T4.1.
