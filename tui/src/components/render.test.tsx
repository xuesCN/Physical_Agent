import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { render } from "ink-testing-library";
import { ActionActivityItem } from "./ActionActivityItem.js";
import { ActionsPanel } from "./ActionsPanel.js";
import { BrandBanner, FULL_MOCE_LOGO, selectBannerVariant } from "./BrandBanner.js";
import { ChatPanel } from "./ChatPanel.js";
import { CommandInput } from "./CommandInput.js";
import { ConfigPanel } from "./ConfigPanel.js";
import { ExecutionApprovalNotice } from "./ExecutionApprovalNotice.js";
import { FinalizedText } from "./FinalizedText.js";
import { rolePresentation } from "./MessageRow.js";
import { RobotDetailPanel } from "./RobotDetailPanel.js";
import { RobotsPanel } from "./RobotsPanel.js";
import { SectionTitle } from "./SectionTitle.js";
import { StatusBar } from "./StatusBar.js";
import { StatusPanel } from "./StatusPanel.js";
import { Transcript } from "./Transcript.js";
import { UploadsPanel } from "./UploadsPanel.js";
import { normalizeTerminalText } from "./textFormat.js";
import { THEME } from "../theme.js";
import type { AgentState, ConfigResponse } from "../types.js";

test("MOCE theme keeps the approved logo and small-text colors", () => {
  assert.equal(THEME.brandLogo, "#1D4ED8");
  assert.equal(THEME.brandAccent, "#3B82F6");
});

test("conversation markers keep user and MOCE colors distinct", () => {
  assert.deepEqual(rolePresentation("user"), { marker: ">", color: THEME.success });
  assert.deepEqual(rolePresentation("assistant"), { marker: "⏺", color: THEME.brandAccent });
  assert.deepEqual(rolePresentation("draft"), { marker: "draft ◇", color: THEME.warning });
  assert.deepEqual(rolePresentation("system"), { marker: "system │", color: THEME.muted });
});

test("SectionTitle renders a branded title without a fixed divider string", () => {
  const view = render(<SectionTitle title="status" detail="live" />);
  assert.match(view.lastFrame() ?? "", /◆ status/);
  assert.match(view.lastFrame() ?? "", /live/);
  view.unmount();
});

test("BrandBanner selects full and compact variants at the terminal boundary", () => {
  assert.equal(selectBannerVariant(100), "full");
  assert.equal(selectBannerVariant(58), "full");
  assert.equal(selectBannerVariant(57), "compact");
  assert.equal(selectBannerVariant(48), "compact");
  assert.equal(selectBannerVariant(0), "compact");
  assert.equal(selectBannerVariant(Number.NaN), "compact");
  assert.equal(selectBannerVariant(undefined), "compact");
});

test("BrandBanner renders block art only for a wide terminal", () => {
  const wide = render(<BrandBanner columns={100} />);
  assert.match(wide.lastFrame() ?? "", new RegExp(FULL_MOCE_LOGO[0]));
  assert.match(wide.lastFrame() ?? "", /PHYSICAL AGENT · SAFE CONTROL PLANE/);
  wide.unmount();

  const narrow = render(<BrandBanner columns={48} />);
  assert.match(narrow.lastFrame() ?? "", /MOCE · PHYSICAL AGENT/);
  assert.doesNotMatch(narrow.lastFrame() ?? "", new RegExp(FULL_MOCE_LOGO[0]));
  narrow.unmount();

  const unknown = render(<BrandBanner columns={undefined} />);
  assert.match(unknown.lastFrame() ?? "", /MOCE · PHYSICAL AGENT/);
  unknown.unmount();
});

test("Transcript prints the MOCE banner once while finalized entries append", () => {
  const view = render(<Transcript entries={[]} columns={100} />);
  view.rerender(
    <Transcript
      columns={100}
      entries={[
        { kind: "chat", id: "u1", role: "user", content: "hello" },
        { kind: "chat", id: "a1", role: "assistant", content: "ready" },
        { kind: "chat", id: "d1", role: "draft", content: "review only" }
      ]}
    />
  );
  const output = view.lastFrame() ?? "";
  assert.equal(output.split(FULL_MOCE_LOGO[0]).length - 1, 1);
  assert.match(output, />\s+hello/);
  assert.match(output, /⏺\s+ready/);
  assert.match(output, /draft\s+◇\s+review only/);
  view.unmount();
});

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
  view.unmount();
  assert.ok(user >= 0 && user < action && action < result && result < assistant);
});

test("ActionActivityItem renders the canonical invocation and terminal outcome", () => {
  const view = render(
    <ActionActivityItem
      entry={{
        kind: "action",
        id: "action-0-act_2",
        action: { id: "act_2", robot: "arm_1", capability: "grasp", params: { force: 2 } },
        outcome: "failed"
      }}
    />
  );
  const frame = view.lastFrame() ?? "";
  view.unmount();
  assert.match(frame, /⏺\s+arm_1\.grasp\(force=2\)/);
  assert.match(frame, /⎿ failed/);
});

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
  assert.doesNotMatch(frame, /sensor|grant|检测到|传感|本会话|总是允许/i);
  view.unmount();
});

test("ExecutionApprovalNotice ignores approved and not-required actions", () => {
  const view = render(
    <ExecutionApprovalNotice
      state={{
        ready: true,
        actions: {
          pending: [
            {
              id: "act_1",
              robot: "arm_1",
              capability: "lift",
              metadata: { approval: { required: true, status: "approved" } }
            },
            {
              id: "act_2",
              robot: "arm_1",
              capability: "grasp",
              metadata: { approval: { required: false, status: "pending" } }
            }
          ]
        }
      }}
    />
  );
  assert.equal(view.lastFrame() ?? "", "");
  view.unmount();
});

test("FinalizedText formats the supported heading list bold and inline-code subset", () => {
  const value = "## Workspace\n- **arm_1** is `idle`\n1. Inspect tray";
  const view = render(<FinalizedText value={value} />);
  const frame = view.lastFrame() ?? "";
  assert.match(frame, /Workspace/);
  assert.match(frame, /• arm_1 is idle/);
  assert.match(frame, /1\. Inspect tray/);
  assert.doesNotMatch(frame, /##|\*\*|`idle`/);
  view.unmount();
});

test("FinalizedText renders the screenshot-shaped nested reply without supported markers", () => {
  const value = [
    "## Current Workspace",
    "",
    "**Robot state**",
    "- `arm_1` is currently **idle**.",
    "",
    "**Visible objects**",
    "1. **red_block**",
    "   - Type: block",
    "   - Color: red",
    "2. **tray**",
    "   - Type: tray"
  ].join("\n");
  const view = render(<FinalizedText value={value} />);
  const frame = view.lastFrame() ?? "";
  assert.match(frame, /Current Workspace/);
  assert.match(frame, /arm_1 is currently idle\./);
  assert.match(frame, /1\. red_block/);
  assert.match(frame, /Type: block/);
  assert.doesNotMatch(frame, /##|\*\*|`arm_1`/);
  view.unmount();
});

test("FinalizedText limits literal fallback to the unsupported block", () => {
  const value = [
    "## Before",
    "",
    "| Name | State |",
    "| --- | --- |",
    "| arm | **idle** |",
    "",
    "**After**"
  ].join("\n");
  const view = render(<FinalizedText value={value} />);
  const frame = view.lastFrame() ?? "";
  assert.match(frame, /Before/);
  assert.match(frame, /\| arm \| \*\*idle\*\* \|/);
  assert.match(frame, /After/);
  assert.doesNotMatch(frame, /## Before|\*\*After\*\*/);
  view.unmount();
});

test("FinalizedText preserves matching shortcut reference source block-locally", () => {
  const value = [
    "## Before",
    "",
    "[**label**]",
    "",
    "[**label**]: https://example.com",
    "",
    "**After**"
  ].join("\n");
  const view = render(<FinalizedText value={value} />);

  assert.equal(
    view.lastFrame() ?? "",
    ["Before", "", "[**label**]", "", "[**label**]: https://example.com", "", "After"].join("\n")
  );
  view.unmount();
});

test("FinalizedText preserves matching image shortcut source block-locally", () => {
  const value = [
    "## Before",
    "",
    "![**alt**]",
    "",
    "[**alt**]: https://example.com/image.png",
    "",
    "**After**"
  ].join("\n");
  const view = render(<FinalizedText value={value} />);

  assert.equal(
    view.lastFrame() ?? "",
    ["Before", "", "![**alt**]", "", "[**alt**]: https://example.com/image.png", "", "After"].join("\n")
  );
  view.unmount();
});

test("FinalizedText keeps unmatched plain bracket prose in the supported subset", () => {
  const view = render(<FinalizedText value="[plain bracketed prose] and **ready**" />);

  assert.equal(view.lastFrame() ?? "", "[plain bracketed prose] and ready");
  view.unmount();
});

test("FinalizedText renders generic code and preserves reserved action-draft fences", () => {
  const generic = render(<FinalizedText value={"```ts\nconst x = 1;\n```"} />);
  assert.match(generic.lastFrame() ?? "", /^│ ts$/m);
  assert.match(generic.lastFrame() ?? "", /^│ const x = 1;$/m);
  assert.doesNotMatch(generic.lastFrame() ?? "", /```/);
  generic.unmount();

  const reserved = render(<FinalizedText value={'```action-draft\n{"actions":[]}\n```'} />);
  assert.match(reserved.lastFrame() ?? "", /```action-draft/);
  assert.match(reserved.lastFrame() ?? "", /\{"actions":\[\]\}/);
  reserved.unmount();
});

test("FinalizedText gives empty valid fences a visible vertical-rail body row", () => {
  const cases = [
    { value: "```\n```", railRows: 1, adjacent: false },
    { value: "```\n\n```", railRows: 1, adjacent: false },
    { value: "```ts\n```", railRows: 2, adjacent: false },
    { value: "```\n```\n## After", railRows: 1, adjacent: true }
  ];

  for (const { value, railRows, adjacent } of cases) {
    const view = render(<FinalizedText value={value} />);
    const lines = (view.lastFrame() ?? "").split("\n");
    assert.equal(lines.filter((line) => line.startsWith("│")).length, railRows, value);
    assert.equal(lines.some((line) => line.includes("After")), adjacent, value);
    view.unmount();
  }
});

test("FinalizedText preserves source paragraph and trailing blank lines", () => {
  const view = render(<FinalizedText value={"first **line**\nsecond `line`\n\nlast\n"} />);
  assert.match(view.lastFrame() ?? "", /first line\nsecond line\n\nlast\n?$/);
  view.unmount();
});

test("FinalizedText preserves unsupported malformed or nested Markdown literally", () => {
  const values = [
    "```ts\nconst x = 1;",
    "```ts\n```js\nconst x = 1;\n```",
    "unclosed **bold",
    "unclosed `code",
    "**bold with `nested` code**",
    "**outer **inner** outer**",
    "*unsupported emphasis*",
    "\\**escaped bold**",
    "\\`escaped code`",
    "- root\n  - nested\n - bad dedent",
    "- [ ] task item",
    "- > nested quote",
    ">quoted block",
    "## Heading ##",
    "[link](https://example.com)",
    "[outer [**bold**]](https://example.com)",
    "![outer [**bold**]](image.png)",
    "<https://example.com>",
    "```action-draft\n{\"actions\":[]}\n```"
  ];
  for (const value of values) {
    const view = render(<FinalizedText value={value} />);
    assert.match(
      view.lastFrame() ?? "",
      new RegExp(value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\n/g, "\\s*"))
    );
    view.unmount();
  }
});

test("FinalizedText falls back wholly when supported tokens mix with unsupported CommonMark", () => {
  const values = [
    "<b>raw</b> and **bold**",
    "<foo@example.com> and **bold**",
    "<ftp://example.com> and **bold**",
    "[](https://example.com) and **bold**",
    "[ref][id] and **bold**",
    "[id]: https://example.com\n**bold**",
    "    const x = 1;\n**bold**",
    "\\# escaped heading and **bold**",
    "**_nested_**"
  ];

  for (const value of values) {
    const view = render(<FinalizedText value={value} />);
    assert.equal(view.lastFrame() ?? "", normalizeTerminalText(value), value);
    view.unmount();
  }
});

test("FinalizedText preserves GFM tables with optional outer pipes literally", () => {
  const values = [
    "Name | State\n--- | ---\narm | **idle**",
    "Name | State\n- | -\narm | **idle**",
    "| Name | State |\n| :--- | ---: |\n| arm | **idle** |"
  ];

  for (const value of values) {
    const view = render(<FinalizedText value={value} />);
    assert.equal(view.lastFrame() ?? "", normalizeTerminalText(value), value);
    view.unmount();
  }
});

test("FinalizedText preserves a pipe-bearing list-like table row literally", () => {
  const source = "Name | State\n- | -\n- | idle";
  const view = render(<FinalizedText value={source} />);

  assert.equal(view.lastFrame() ?? "", source);
  view.unmount();
});

test("FinalizedText keeps table adjacency and pipe-bearing heading precedence", () => {
  const adjacent = render(<FinalizedText value={"Name | State\n- | -\narm | idle\n- next"} />);
  assert.equal(adjacent.lastFrame() ?? "", "Name | State\n- | -\narm | idle\n• next");
  adjacent.unmount();

  const heading = render(<FinalizedText value={"## Name | State\n- | -\narm | idle"} />);
  assert.equal(heading.lastFrame() ?? "", "Name | State\n- | -\narm | idle");
  heading.unmount();
});

test("FinalizedText keeps an ordinary prose pipe in the supported subset", () => {
  const value = "Name | **idle**";
  const view = render(<FinalizedText value={value} />);
  assert.equal(view.lastFrame() ?? "", "Name | idle");
  view.unmount();
});

test("FinalizedText rejects underscore emphasis containing internal underscores", () => {
  const values = [
    "_foo_bar_ and **bold**",
    "**_foo_bar_**",
    "before _foo_bar_ after\n`code`"
  ];

  for (const value of values) {
    const view = render(<FinalizedText value={value} />);
    assert.equal(view.lastFrame() ?? "", normalizeTerminalText(value), value);
    view.unmount();
  }
});

test("FinalizedText rejects unsupported delimiter runs without losing content", () => {
  const values = [
    "`foo``bar` and **bold**",
    "_foo\nbar_\n**bold**"
  ];

  for (const value of values) {
    const view = render(<FinalizedText value={value} />);
    assert.equal(view.lastFrame() ?? "", normalizeTerminalText(value), value);
    view.unmount();
  }
});

test("FinalizedText preserves blank and trailing normalized lines exactly", () => {
  const value = "plain\n\nlast\n";
  const view = render(<FinalizedText value={value} />);
  assert.equal(view.lastFrame() ?? "", value);
  view.unmount();
});

test("Transcript formats only finalized assistant entries", () => {
  const view = render(
    <Transcript
      columns={48}
      entries={[
        { kind: "chat", id: "a1", role: "assistant", content: "## Assistant heading" },
        { kind: "chat", id: "u1", role: "user", content: "## User literal" },
        { kind: "chat", id: "d1", role: "draft", content: "**Draft literal**" },
        { kind: "chat", id: "s1", role: "system", content: "`System literal`" },
        { kind: "chat", id: "x1", role: "unknown", content: "**Unknown literal**" }
      ]}
    />
  );
  const frame = view.lastFrame() ?? "";
  assert.match(frame, /⏺\s+Assistant heading/);
  assert.doesNotMatch(frame, /## Assistant heading/);
  assert.match(frame, />\s+## User literal/);
  assert.match(frame, /draft\s+◇\s+\*\*Draft literal\*\*/);
  assert.match(frame, /`System literal`/);
  assert.match(frame, /\*\*Unknown literal\*\*/);
  view.unmount();
});

test("StatusBar renders connection state", () => {
  const view = render(
    <StatusBar
      status={{
        apiBase: "http://127.0.0.1:8766",
        connected: true,
        mode: "sse",
        lastRefresh: "12:00:00",
        backend: "sqlite",
        executor: { mode: "embedded", status: "active", lease: { active: true } },
        llm: {
          state: "ok",
          model: "doubao-seed-2-1-pro-260628",
          hasApiKey: true,
          message: "LLM connection test passed."
        },
        message: "Ready."
      }}
    />
  );
  assert.match(view.lastFrame() ?? "", /MOCE/);
  assert.match(view.lastFrame() ?? "", /Physical Agent TUI/);
  assert.match(view.lastFrame() ?? "", /sqlite/);
  assert.match(view.lastFrame() ?? "", /SSE/);
  assert.match(view.lastFrame() ?? "", /Executor: embedded \(active\)/);
  assert.match(view.lastFrame() ?? "", /doubao-seed-2-1-pro-260628/);
  assert.match(view.lastFrame() ?? "", /key set/);
  assert.match(view.lastFrame() ?? "", /LLM connected/);
});

test("StatusBar renders short LLM auth failure without exposing details", () => {
  const view = render(
    <StatusBar
      status={{
        apiBase: "http://127.0.0.1:8766",
        connected: true,
        mode: "sse",
        lastRefresh: "12:00:00",
        backend: "sqlite",
        executor: { mode: "embedded", status: "active" },
        llm: {
          state: "failed",
          model: "doubao",
          hasApiKey: true,
          message: "OpenAI-compatible API request failed (HTTP 401): AuthenticationError: The API key status is not active."
        },
        message: "Ready."
      }}
    />
  );

  assert.match(view.lastFrame() ?? "", /LLM failed: key inactive/);
});

test("StatusBar distinguishes unknown, waiting, and stopped executor states", () => {
  const unknown = render(
    <StatusBar
      status={{
        apiBase: "http://127.0.0.1:8766",
        connected: false,
        mode: "polling",
        lastRefresh: null,
        backend: "-",
        executor: null,
        llm: {
          state: "unknown",
          model: "-",
          hasApiKey: null
        },
        message: "Loading"
      }}
    />
  );
  assert.match(unknown.lastFrame() ?? "", /Executor: status unknown/);
  assert.doesNotMatch(unknown.lastFrame() ?? "", /snapshot/);
  unknown.unmount();

  const waiting = render(
    <StatusBar
      status={{
        apiBase: "http://127.0.0.1:8766",
        connected: true,
        mode: "sse",
        lastRefresh: "12:00:00",
        backend: "sqlite",
        executor: { mode: "waiting_for_init", status: "waiting" },
        llm: {
          state: "checking",
          model: "model-a",
          hasApiKey: false
        },
        message: "Ready."
      }}
    />
  );
  assert.match(waiting.lastFrame() ?? "", /Executor: waiting for initialization/);
  waiting.unmount();

  const stopped = render(
    <StatusBar
      status={{
        apiBase: "http://127.0.0.1:8766",
        connected: true,
        mode: "sse",
        lastRefresh: "12:00:00",
        backend: "sqlite",
        executor: { mode: "none", status: "stopped" },
        llm: {
          state: "checking",
          model: "model-a",
          hasApiKey: false
        },
        message: "Ready."
      }}
    />
  );
  assert.match(stopped.lastFrame() ?? "", /Executor: not running/);
});

test("Transcript content keeps long text and normalizes newlines", () => {
  const longAnswer = `first line ${"x".repeat(230)}\nsecond line survives`;
  const rendered = normalizeTerminalText(`${longAnswer}\r\nthird line survives`);

  assert.match(rendered, /second line survives/);
  assert.match(rendered, /third line survives/);
  assert.equal(rendered.includes("\r"), false);
});

test("ChatPanel renders only live streaming state", () => {
  const view = render(<ChatPanel hasTranscript={true} streamingText="partial reply" streaming={true} />);
  const frame = view.lastFrame() ?? "";
  assert.match(frame, /◆ chat/);
  assert.match(frame, /streaming/);
  assert.match(frame, /⏺\s+partial reply/);
  assert.doesNotMatch(frame, /No chat yet/);
  view.unmount();
});

test("CommandInput renders a round branded prompt and disabled copy", () => {
  const view = render(
    <CommandInput value="" onChange={() => undefined} onSubmit={() => undefined} />
  );
  assert.match(view.lastFrame() ?? "", /╭|╰/);
  assert.match(view.lastFrame() ?? "", /›/);
  assert.match(view.lastFrame() ?? "", /message or \/help/);
  Object.assign(view.stdin, {
    read: () => null,
    ref: () => undefined,
    unref: () => undefined
  });
  view.rerender(
    <CommandInput value="" onChange={() => undefined} onSubmit={() => undefined} disabled />
  );
  assert.match(view.lastFrame() ?? "", /Working\.\.\./);
  view.unmount();
});

test("ChatPanel leaves incomplete streaming Markdown untouched", () => {
  const view = render(<ChatPanel hasTranscript streamingText="**partial" streaming />);
  assert.match(view.lastFrame() ?? "", /\*\*partial/);
  view.unmount();
});

test("ActionsPanel renders approval status", () => {
  const view = render(
    <ActionsPanel
      state={{
        ready: true,
        actions: {
          pending: [
            {
              id: "act_001",
              robot: "arm_1",
              capability: "pick",
              reason: "Pick the block",
              metadata: { approval: { required: true, status: "pending" } }
            }
          ],
          completed: [],
          cancelled: []
        }
      }}
    />
  );
  assert.match(view.lastFrame() ?? "", /◆ actions/);
  assert.match(view.lastFrame() ?? "", /act_001/);
  assert.match(view.lastFrame() ?? "", /approval required/);
});

test("ActionsPanel trusts compiled SafetyGate status over raw feedback", () => {
  const view = render(
    <ActionsPanel
      force
      state={{
        ready: true,
        plan: {
          plan: {
            agent_output: {
              schema: "physical-agent/agent-output/v1",
              status: "failed",
              decision: "propose",
              lifecycle: "submitted",
              tasks: [
                {
                  id: "task:safety_gate:act_001",
                  kind: "safety_gate",
                  owner: "watch",
                  status: "failed",
                  action_id: "act_001",
                  depends_on: [],
                  mandatory: true,
                  policy_source: "SAFETY.md",
                  checks: [{ code: "safety.robot.known" }]
                }
              ]
            }
          }
        },
        feedback: {
          history: [
            {
              event: "safety_gate",
              task_id: "task:safety_gate:act_001",
              action_id: "act_001",
              status: "passed",
              decision: "allow",
              actor: "agent"
            }
          ]
        },
        actions: { pending: [], completed: [], cancelled: [] }
      }}
    />
  );
  const frame = view.lastFrame() ?? "";
  assert.match(frame, /safety_gate/);
  assert.match(frame, /mandatory watch gate/);
  assert.match(frame, /SAFETY.md/);
  assert.match(frame, /failed/);
  assert.doesNotMatch(frame, /passed/);
});

test("ConfigPanel renders configured robots without exposing secrets", () => {
  const view = render(
    <ConfigPanel
      config={sampleConfig()}
      state={sampleState()}
    />
  );
  const frame = view.lastFrame() ?? "";
  assert.match(frame, /◆ config/);
  assert.match(frame, /workspace/);
  assert.match(frame, /backend sqlite/);
  assert.match(frame, /arm_1/);
  assert.match(frame, /mock_arm/);
  assert.match(frame, /mode simulation/);
  assert.match(frame, /capability schemas/);
  assert.doesNotMatch(frame, /super-secret/);
  assert.doesNotMatch(frame, /api_key/);
  assert.doesNotMatch(frame, /token/);
});

test("ConfigPanel keeps its shared title before the snapshot is loaded", () => {
  const view = render(<ConfigPanel config={null} state={null} />);
  assert.match(view.lastFrame() ?? "", /◆ config/);
  assert.match(view.lastFrame() ?? "", /Config snapshot not loaded/);
  view.unmount();
});

test("ConfigPanel renders empty robot config", () => {
  const config = sampleConfig();
  config.config = { ...config.config, robots: {} };
  const view = render(<ConfigPanel config={config} state={{ ready: true }} />);
  assert.match(view.lastFrame() ?? "", /No robots configured/);
});

test("RobotsPanel renders multiple robots, unknown health, approval, and capability counts", () => {
  const state = sampleState();
  state.capabilities = {
    robots: {
      ...state.capabilities?.robots,
      rover_1: {
        driver: "mock_rover",
        status: "unknown",
        capabilities: []
      }
    }
  };
  const config = sampleConfig();
  config.config = {
    ...config.config,
    robots: {
      ...config.config?.robots,
      rover_1: { driver: "mock_rover", config: { transport: "loopback" } }
    }
  };
  const view = render(<RobotsPanel state={state} config={config} />);
  const frame = view.lastFrame() ?? "";
  assert.match(frame, /◆ robots/);
  assert.match(frame, /arm_1/);
  assert.match(frame, /rover_1/);
  assert.match(frame, /health unknown/);
  assert.match(frame, /approval capabilities 1/);
});

test("RobotDetailPanel renders params_schema and constraints summaries", () => {
  const view = render(
    <RobotDetailPanel state={sampleState()} config={sampleConfig()} robotId="arm_1" mode="capabilities" />
  );
  const frame = view.lastFrame() ?? "";
  assert.match(frame, /◆ capabilities arm_1/);
  assert.match(frame, /requires_approval/);
  assert.match(frame, /params_schema: type object; props object_id/);
  assert.match(frame, /constraints: bounds/);
});

test("UploadsPanel renders metadata without full file preview", () => {
  const view = render(
    <UploadsPanel
      state={{
        ready: true,
        uploads: {
          uploads: [
            {
              original_name: "manual.md",
              stored_name: "abc-manual.md",
              sha256: "1234567890abcdef",
              size_bytes: 42,
              suffix: ".md",
              status: "stored",
              preview: "full file content should not be shown"
            }
          ]
        }
      }}
      lastUpload={{
        ok: true,
        message: "uploaded",
        filename: "manual.md",
        size_bytes: 42,
        result: {
          chunks_written: 1,
          metadata: {
            sha256: "1234567890abcdef",
            preview: "another full file content should not be shown"
          }
        },
        state: { ready: true }
      }}
    />
  );
  const frame = view.lastFrame() ?? "";
  assert.match(frame, /◆ uploads/);
  assert.match(frame, /manual.md/);
  assert.match(frame, /untrusted yes/);
  assert.doesNotMatch(frame, /full file content/);
});

test("StatusPanel renders the shared status title", () => {
  const view = render(
    <StatusPanel
      status={{
        apiBase: "http://127.0.0.1:8766",
        connected: true,
        mode: "sse",
        lastRefresh: "12:00:00",
        backend: "sqlite",
        executor: { mode: "embedded", status: "active" },
        llm: { state: "ok", model: "model-a", hasApiKey: true },
        message: "Ready."
      }}
      health={null}
      state={null}
      config={null}
    />
  );
  assert.match(view.lastFrame() ?? "", /◆ status/);
  view.unmount();
});

function sampleConfig(): ConfigResponse {
  return {
    ok: true,
    message: "ok",
    config_path: "physical-agent.yaml",
    config: {
      workspace: { path: "./workspace", backend: "sqlite" },
      watch: { tick_ms: 500, require_human_approval: false },
      agent: { planner: "llm", model: "fake/local", api_key: "super-secret" },
      robots: {
        arm_1: {
          driver: "mock_arm",
          execution_mode: "simulation",
          config: {
            mode: "mock",
            endpoint: "loopback",
            token: "super-secret-token",
            bounds: { x: [-1, 1] }
          }
        }
      }
    }
  };
}

function sampleState(): AgentState {
  return {
    ready: true,
    backend: "sqlite",
    world: {
      robots: {
        arm_1: { status: "idle", endpoint: "loopback", mode: "mock" }
      }
    },
    capabilities: {
      robots: {
        arm_1: {
          kind: "arm",
          driver: "mock_arm",
          execution_mode: "simulation",
          status: "connected",
          capabilities: [
            {
              name: "pick",
              description: "Pick object",
              requires_approval: true,
              params_schema: {
                type: "object",
                properties: { object_id: { type: "string" } },
                required: ["object_id"]
              },
              constraints: { bounds: { x: [-1, 1] } }
            }
          ]
        }
      }
    }
  };
}
