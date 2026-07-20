import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { EventEmitter } from "node:events";
import React from "react";
import { Box, render as inkRender } from "ink";
import stringWidth from "string-width";
import { App, type TuiClient } from "../src/App.js";
import { FULL_MOCE_LOGO } from "../src/components/BrandBanner.js";
import { ChatPanel } from "../src/components/ChatPanel.js";
import { ExecutionApprovalNotice } from "../src/components/ExecutionApprovalNotice.js";
import { Transcript } from "../src/components/Transcript.js";
import type {
  AgentOutput,
  AgentState,
  ApiEvent,
  ConfigResponse,
  HealthState,
  LLMSettingsResponse,
  RegisterRobotPayload,
  RegisterRobotResponse,
  UploadResponse
} from "../src/types.js";

type EventBehavior = "idle" | "clean-eof" | "error";

interface ScenarioFile {
  name: string;
  cases: ScenarioCase[];
}

interface ScenarioCase {
  name: string;
  useSse?: boolean;
  responseDelayMs?: number;
  columns?: number | null;
  initialState?: string;
  initialConfig?: string;
  initialExpectOutput?: string[];
  initialRejectOutput?: string[];
  initialMaxLineWidth?: number;
  fail?: Partial<Record<CallName, string>>;
  events?: {
    behavior?: EventBehavior;
    error?: string;
    items?: ScenarioEvent[];
  };
  responses?: Partial<Record<QueuedCallName, ScenarioResponse[]>>;
  steps: ScenarioStep[];
}

interface ScenarioStep {
  input: string;
  covers?: string[];
  expectOutput?: string[];
  expectLatestOutput?: string[];
  rejectOutput?: string[];
  maxLineWidth?: number;
  expectCalls?: Partial<Record<CallName, number>>;
  expectState?: Record<string, unknown>;
  expectConfig?: Record<string, unknown>;
}

interface ScenarioEvent {
  type: string;
  payload?: Record<string, unknown>;
  state?: string;
}

type ScenarioResponse =
  | {
      error: string;
    }
  | {
      ok?: boolean;
      message?: string;
      state?: string;
      config?: string;
      robot_id?: string;
      filename?: string;
      size_bytes?: number;
      sha256?: string;
      chunks_written?: number;
      events?: ApiEvent[];
    };

type CallName =
  | "health"
  | "state"
  | "config"
  | "llmSettings"
  | "testLlmSettings"
  | "submitTask"
  | "approveAction"
  | "rejectAction"
  | "resetWorkspace"
  | "registerRobot"
  | "uploadFile"
  | "sendChatStream"
  | "events";

type QueuedCallName =
  | "submitTask"
  | "approveAction"
  | "rejectAction"
  | "resetWorkspace"
  | "registerRobot"
  | "uploadFile"
  | "sendChatStream";

interface ScenarioCaseContext {
  scenario: ScenarioFile;
  scenarioCase: ScenarioCase;
  client: ScenarioClient;
  view: TestInkInstance;
}

interface TestInkInstance {
  stdin: TestStdin;
  frames: string[];
  lastFrame(): string | undefined;
  unmount(): void;
  cleanup(): void;
}

interface PhysicalTestInkInstance extends TestInkInstance {
  physicalOutput(): string;
  physicalWriteCount(): number;
}

const scenarioRoot = path.resolve("tests", "scenarios");

const requiredCoverage = [
  "/help",
  "/view status",
  "/view chat",
  "/view actions",
  "/view config",
  "/view robots",
  "/view uploads",
  "/task",
  "/approve",
  "/reject",
  "/reset",
  "/config",
  "/robots",
  "/robot",
  "/capabilities",
  "/upload",
  "/refresh",
  "/quit",
  "API offline",
  "SSE error",
  "SSE clean EOF",
  "polling fallback",
  "missing arguments",
  "invalid command",
  "upload failure",
  "reset confirmation failure"
];

const scenarioFiles = await loadScenarios();

for (const scenario of scenarioFiles) {
  for (const scenarioCase of scenario.cases) {
    test(`${scenario.name}: ${scenarioCase.name}`, async () => {
      const context = renderScenarioCase(scenario, scenarioCase);
      try {
        if (scenarioCase.initialExpectOutput?.length) {
          await waitForOutput(context.view, scenarioCase.initialExpectOutput);
        } else {
          await waitForOutput(context.view, ["Physical Agent TUI"]);
        }
        assertLatestRejectOutput(context.view, scenarioCase.initialRejectOutput);
        assertMaxLineWidth(context.view, scenarioCase.initialMaxLineWidth);

        for (const step of scenarioCase.steps) {
          await submitCommand(context.view, step.input);
          await assertStep(context, step);
        }
      } finally {
        context.view.unmount();
      }
    });
  }
}

test("scenario coverage includes every documented TUI command and failure mode", () => {
  const covered = new Set<string>();
  for (const scenario of scenarioFiles) {
    for (const scenarioCase of scenario.cases) {
      for (const step of scenarioCase.steps) {
        for (const item of step.covers ?? []) {
          covered.add(item);
        }
      }
    }
  }

  for (const command of requiredCoverage) {
    assert.equal(covered.has(command), true, `${command} is not covered by tui/tests/scenarios`);
  }
});

test("display-width guard counts emoji and CJK terminal cells", () => {
  assert.equal([..."👋"].length, 1);
  assert.equal(stringWidth("👋"), 2);
  assert.equal(stringWidth("中"), 2);
  assert.equal(stringWidth("e\u0301"), 1);
  assert.equal(stringWidth("👨‍👩‍👧‍👦"), 2);
});

test("48-column finalized and streaming chat use display-safe hanging indents", () => {
  const content = "Hello! 👋 I can see the arm is idle on the table, with a red block and a tray visible nearby. Please tell me what to do next.";
  const finalized = renderPhysicalTui(
    <Transcript columns={48} entries={[{ kind: "chat", id: "a1", role: "assistant", content }]} />,
    48
  );
  const streaming = renderPhysicalTui(
    <ChatPanel hasTranscript streamingText={content} streaming />,
    48
  );

  try {
    assertMaxLineWidth(finalized, 48);
    assertMaxLineWidth(streaming, 48);
    assertHangingBody(finalized.physicalOutput(), "⏺", content);
    assertHangingBody(streaming.physicalOutput(), "⏺", content);
  } finally {
    finalized.unmount();
    streaming.unmount();
  }
});

test("nested Markdown list and code rows stay display-safe at finite widths", () => {
  const content = [
    "## Current Workspace",
    "10. **red_block** has a deliberately long two-digit ordered body whose continuation-check stays aligned",
    "   - Description: 👋 中 e\u0301 👨‍👩‍👧‍👦 remains visible near the collaborative workspace boundary",
    "      * Detail: third-level bullet needs a stable physical rail for alignment-check",
    "2. **tray**",
    "   - Type: tray",
    "",
    "```ts",
    "const description = 'a deliberately long code line that must wrap under the code rail';",
    "```"
  ].join("\n");

  for (const columns of [24, 48, 100]) {
    const view = renderPhysicalTui(
      <Box width={columns} flexDirection="column">
        <Transcript
          columns={columns}
          entries={[{ kind: "chat", id: `markdown-${columns}`, role: "assistant", content }]}
        />
      </Box>,
      columns
    );
    try {
      assertMaxLineWidth(view, columns);
      const output = view.physicalOutput();
      assertLogicalText(output, [
        "Current Workspace", "red_block", "Description:", "collaborative workspace boundary",
        "Detail:", "alignment-check", "tray", "Type: tray", "const description", "code rail"
      ]);
      for (const token of ["👋", "中", "e\u0301", "👨‍👩‍👧‍👦"]) {
        const normalized = normalizeOutput(output).normalize("NFD");
        assert.equal(normalized.split(token.normalize("NFD")).length - 1, 1, `${columns}: ${token}`);
      }
      assert.equal(normalizeOutput(output).includes("## Current Workspace"), false);
      assert.equal(normalizeOutput(output).includes("**red_block**"), false);
      if (columns < 100) {
        assertInnerHangingBody(
          output,
          "10.",
          "red_block",
          columns === 24 ? "two-digit" : "continuation-check"
        );
        assertInnerHangingBody(output, "◦", "Description:", "boundary");
        assertInnerHangingBody(output, "▪", "Detail:", columns === 24 ? "third-level" : "alignment-check");
        assertInnerHangingBody(output, "│", "const description", "rail");
      }
    } finally {
      view.unmount();
    }
  }
});

test("action activity and execution approval stay display-safe at finite widths", () => {
  const actionEntry = {
    kind: "action" as const,
    id: "action-0-act_1",
    action: {
      id: "act_1",
      robot: "arm_1",
      capability: "move_to",
      params: { x: 120, y: 45, z: 0 }
    },
    outcome: "done" as const
  };
  const approvalState: AgentState = {
    ready: true,
    actions: {
      pending: [
        {
          id: "act_1",
          robot: "arm_1",
          capability: "move_to",
          params: { x: 120, y: 45, z: 0 },
          metadata: { approval: { required: true, status: "pending" } }
        }
      ]
    }
  };
  const invocation = "arm_1.move_to(x=120, y=45, z=0)";

  for (const columns of [24, 48, 100]) {
    const action = renderPhysicalTui(
      <Box width={columns} flexDirection="column">
        <Transcript columns={columns} entries={[actionEntry]} />
      </Box>,
      columns
    );
    const approval = renderPhysicalTui(
      <Box width={columns} flexDirection="column">
        <ExecutionApprovalNotice state={approvalState} />
      </Box>,
      columns
    );

    try {
      assertMaxLineWidth(action, columns);
      assertMaxLineWidth(approval, columns);
      assertHangingBody(action.physicalOutput(), "⏺", `${invocation} ⎿ done`, true);
      assertLogicalText(approval.physicalOutput(), [
        "Safety Gate · Execution approval",
        "1/1",
        invocation,
        "等待人工批准",
        "批准后仍需 watch SafetyGate 校验",
        "/approve act_1",
        "/reject act_1 <reason>"
      ]);
    } finally {
      action.unmount();
      approval.unmount();
    }
  }
});

test("unknown width keeps compact branding and action approval content", () => {
  const state: AgentState = {
    ready: true,
    actions: {
      pending: [
        {
          id: "act_1",
          robot: "arm_1",
          capability: "move_to",
          params: { x: 120, y: 45, z: 0 },
          metadata: { approval: { required: true, status: "pending" } }
        }
      ]
    }
  };
  const action = renderPhysicalTui(
    <Box width="100%" flexDirection="column">
      <Transcript
        columns={undefined}
        entries={[
          {
            kind: "action",
            id: "action-0-act_1",
            action: {
              id: "act_1",
              robot: "arm_1",
              capability: "move_to",
              params: { x: 120, y: 45, z: 0 }
            },
            outcome: "done"
          }
        ]}
      />
    </Box>,
    null
  );
  const approval = renderPhysicalTui(
    <Box width="100%" flexDirection="column">
      <ExecutionApprovalNotice state={state} />
    </Box>,
    null
  );

  try {
    assertPhysicalOutputIncludes(action, "MOCE · PHYSICAL AGENT", "unknown width banner");
    assertLogicalText(action.physicalOutput(), ["arm_1.move_to(x=120, y=45, z=0)", "⎿ done"]);
    assertLogicalText(approval.physicalOutput(), [
      "Safety Gate · Execution approval",
      "1/1",
      "arm_1.move_to(x=120, y=45, z=0)",
      "act_1",
      "等待人工批准",
      "批准后仍需 watch SafetyGate 校验",
      "/approve act_1",
      "/reject act_1 <reason>"
    ]);
  } finally {
    action.unmount();
    approval.unmount();
  }
});

test("complete App selects branding at default, 100, 48, and unknown columns", async () => {
  const selections: string[] = [];

  for (const columns of [undefined, 100, 48, null] as const) {
    const client = new ScenarioClient({
      name: `width ${String(columns)}`,
      useSse: false,
      initialState: "ready",
      initialConfig: "default",
      steps: []
    });
    const view = renderTui(
      <App apiBase="http://mock.local" pollIntervalMs={60_000} useSse={false} client={client} />,
      columns
    );
    try {
      await waitForOutput(view, ["Physical Agent TUI", "message or /help"]);
      const output = latestSnapshot(view);
      selections.push(
        output.includes(FULL_MOCE_LOGO[0])
          ? "full"
          : output.includes("MOCE · PHYSICAL AGENT")
            ? "compact"
            : "missing"
      );
    } finally {
      view.unmount();
    }
  }

  assert.deepEqual(selections, ["full", "full", "compact", "compact"]);
});

for (const { label, columns, marker } of [
  { label: "full", columns: 100, marker: FULL_MOCE_LOGO[0] },
  { label: "compact", columns: 48, marker: "MOCE · PHYSICAL AGENT" }
] as const) {
  test(`complete App physically prints ${label} branding once across rerenders`, async () => {
    const client = new ScenarioClient({
      name: `physical ${label}-brand rerenders`,
      useSse: false,
      initialState: "ready",
      initialConfig: "default",
      responseDelayMs: 250,
      steps: []
    });
    const view = renderPhysicalTui(
      <App apiBase="http://mock.local" pollIntervalMs={60_000} useSse={false} client={client} />,
      columns
    );

    try {
      await waitForCallCounts(client, {
        health: 1,
        state: 1,
        config: 1,
        llmSettings: 1,
        testLlmSettings: 1
      });
      await waitForPhysicalTextAfter(view, 0, marker);
      assertPhysicalMarkerCount(view, marker, 1, "initial render");

      await submitPhysicalCommand(view, "/view status", "View: status");
      await waitForCallCounts(client, { health: 2, state: 2, config: 2 });
      assertPhysicalOutputIncludes(view, "View: status", "/view status");
      assertPhysicalMarkerCount(view, marker, 1, "/view status");

      await submitPhysicalCommand(view, "/view chat", "View: chat");
      assertPhysicalOutputIncludes(view, "View: chat", "/view chat");
      assertPhysicalMarkerCount(view, marker, 1, "/view chat");

      await submitPhysicalCommand(view, "/refresh", "Snapshot refreshed.");
      await waitForCallCounts(client, {
        health: 3,
        state: 3,
        config: 3,
        llmSettings: 2,
        testLlmSettings: 2
      });
      assertPhysicalOutputIncludes(view, "Snapshot refreshed.", "/refresh");
      assertPhysicalMarkerCount(view, marker, 1, "/refresh");
    } finally {
      view.unmount();
    }
  });
}

test("complete App physically prints terminal action once across mutation and refresh", async () => {
  const invocation = "arm_1.move_to(x=120, y=45, z=0)";
  const client = new ScenarioClient({
    name: "physical terminal action rerender",
    useSse: false,
    initialState: "actionsReady",
    initialConfig: "default",
    responses: {
      submitTask: [
        { message: "Action act_done pending.", state: "beforeCompleted" },
        { message: "Action act_done completed.", state: "afterCompleted" }
      ]
    },
    steps: []
  });
  const view = renderPhysicalTui(
    <App apiBase="http://mock.local" pollIntervalMs={60_000} useSse={false} client={client} />,
    100
  );

  try {
    await waitForCallCounts(client, {
      health: 1,
      state: 1,
      config: 1,
      llmSettings: 1,
      testLlmSettings: 1
    });
    await waitForOutput(view, ["/approve act_001"]);
    await waitForPhysicalSettled(view);

    await submitPhysicalCommand(view, "/task stage completed move", "Action act_done pending.");
    assertPhysicalMarkerCount(view, invocation, 0, "pending action");

    await submitPhysicalCommand(view, "/task record completed move", "Action act_done completed.");
    await waitForOutput(view, ["Server recorded completion.", invocation, "⎿ done"]);
    const beforeRefresh = normalizeOutput(view.physicalOutput());
    assert.equal(
      beforeRefresh.indexOf("Server recorded completion.") < beforeRefresh.indexOf(invocation),
      true,
      "server chat must physically append before terminal action from the same snapshot"
    );

    await submitPhysicalCommand(view, "/refresh", "Snapshot refreshed.");
    await waitForCallCounts(client, {
      health: 2,
      state: 2,
      config: 2,
      llmSettings: 2,
      testLlmSettings: 2
    });
    await waitForPhysicalSettled(view);
    assertPhysicalMarkerCount(view, invocation, 1, "terminal action rerender");
  } finally {
    view.unmount();
  }
});

test("only a successful reset response opens a new action activity generation", async () => {
  const invocation = "arm_1.move_to(x=120, y=45, z=0)";
  const client = new ScenarioClient({
    name: "reset response action generation",
    useSse: false,
    initialState: "actionsReady",
    initialConfig: "default",
    responses: {
      submitTask: [
        { message: "Cycle one pending.", state: "beforeCompleted" },
        { message: "Cycle one completed.", state: "afterCompleted" },
        { message: "Refused cycle pending.", state: "beforeCompleted" },
        { message: "Refused cycle completed.", state: "afterCompleted" },
        { message: "Cycle two pending.", state: "beforeCompleted" },
        { message: "Cycle two completed.", state: "afterCompleted" }
      ],
      resetWorkspace: [
        { ok: false, message: "Workspace reset refused.", state: "afterReset" },
        { ok: true, message: "Workspace reset.", state: "afterReset" }
      ]
    },
    steps: []
  });
  const view = renderPhysicalTui(
    <App apiBase="http://mock.local" pollIntervalMs={60_000} useSse={false} client={client} />,
    100
  );

  try {
    await waitForOutput(view, ["/approve act_001"]);
    await waitForPhysicalSettled(view);
    await submitPhysicalCommand(view, "/task cycle-one-pending", "Cycle one pending.");
    await submitPhysicalCommand(view, "/task cycle-one-completed", "Cycle one completed.");
    await waitForPhysicalMarkerCount(view, invocation, 1, "first generation");

    await submitPhysicalCommand(view, "/reset false", "Workspace reset refused.");
    await submitPhysicalCommand(view, "/task refused-cycle-pending", "Refused cycle pending.");
    await submitPhysicalCommand(view, "/task refused-cycle-completed", "Refused cycle completed.");
    await waitForPhysicalSettled(view);
    assertPhysicalMarkerCount(view, invocation, 1, "refused reset");

    await submitPhysicalCommand(view, "/reset true", "Workspace reset.");
    await submitPhysicalCommand(view, "/task cycle-two-pending", "Cycle two pending.");
    await submitPhysicalCommand(view, "/task cycle-two-completed", "Cycle two completed.");
    await waitForPhysicalMarkerCount(view, invocation, 2, "successful reset");
    assert.equal(client.callCount("resetWorkspace"), 2);
  } finally {
    view.unmount();
  }
});

test("workspace_reset SSE resets the tracker and duplicate state sources append once", async () => {
  const invocation = "arm_1.move_to(x=120, y=45, z=0)";
  const client = new ScenarioClient({
    name: "SSE reset action generation",
    useSse: true,
    initialState: "beforeCompleted",
    initialConfig: "default",
    events: { behavior: "idle" },
    steps: []
  });
  const view = renderPhysicalTui(
    <App apiBase="http://mock.local" pollIntervalMs={60_000} useSse client={client} />,
    100
  );

  try {
    await waitForCallCounts(client, { state: 1, events: 1 });
    await waitForOutput(view, ["/approve act_001"]);
    await waitForPhysicalSettled(view);

    client.publishEvent({ type: "state", state: "afterCompleted" });
    await waitForPhysicalMarkerCount(view, invocation, 1, "first SSE terminal");

    client.publishEvent({ type: "state", state: "afterCompleted" });
    await waitForPhysicalSettled(view);
    assertPhysicalMarkerCount(view, invocation, 1, "duplicate full SSE");

    const stateCallsBeforeSummary = client.callCount("state");
    client.publishEvent({ type: "state", payload: { state: { ready: true, completed_count: 1 } } });
    await waitForCallCounts(client, { state: stateCallsBeforeSummary + 1 });
    await waitForPhysicalSettled(view);
    assertPhysicalMarkerCount(view, invocation, 1, "summary refresh");

    client.publishEvent({ type: "workspace_reset", state: "afterReset" });
    await waitForPhysicalSettled(view);
    client.publishEvent({ type: "state", state: "beforeCompleted" });
    await waitForPhysicalSettled(view);
    client.publishEvent({ type: "state", state: "afterCompleted" });
    await waitForPhysicalMarkerCount(view, invocation, 2, "SSE reset reuse");
  } finally {
    view.unmount();
  }
});

async function loadScenarios(): Promise<ScenarioFile[]> {
  const files = (await readdir(scenarioRoot))
    .filter((file) => file.endsWith(".scenario"))
    .sort();
  assert.deepEqual(files, [
    "actions.scenario",
    "basic.scenario",
    "chat.scenario",
    "config.scenario",
    "error.scenario",
    "robots.scenario",
    "upload.scenario"
  ]);

  const parsed: ScenarioFile[] = [];
  for (const file of files) {
    const fullPath = path.join(scenarioRoot, file);
    parsed.push(JSON.parse(await readFile(fullPath, "utf8")) as ScenarioFile);
  }
  return parsed;
}

function renderScenarioCase(scenario: ScenarioFile, scenarioCase: ScenarioCase): ScenarioCaseContext {
  const client = new ScenarioClient(scenarioCase);
  const columns = scenarioCase.columns === undefined ? 100 : scenarioCase.columns;
  const view = renderTui(
    <App
      apiBase="http://mock.local"
      pollIntervalMs={60_000}
      useSse={scenarioCase.useSse ?? true}
      client={client}
    />,
    columns
  );
  return { scenario, scenarioCase, client, view };
}

async function submitCommand(view: TestInkInstance, input: string): Promise<void> {
  view.stdin.write(input);
  await delay(100);
  view.stdin.write("\r");
  await delay(0);
}

async function submitPhysicalCommand(
  view: PhysicalTestInkInstance,
  input: string,
  completionText: string
): Promise<void> {
  const consumedChunksBeforeInput = view.stdin.consumedChunkCount();
  view.stdin.write(input);
  await waitForStdinConsumption(view.stdin, consumedChunksBeforeInput);
  const writeCountBeforeEnter = view.physicalWriteCount();
  view.stdin.write("\r");
  await waitForPhysicalTextAfter(view, writeCountBeforeEnter, completionText);
}

async function assertStep(context: ScenarioCaseContext, step: ScenarioStep): Promise<void> {
  if (step.expectOutput?.length) {
    await waitForOutput(context.view, step.expectOutput);
  } else {
    await delay(0);
  }

  const output = terminalOutput(context.view);
  for (const expected of step.rejectOutput ?? []) {
    assert.equal(output.includes(expected), false, `${context.scenario.name}/${step.input} unexpectedly rendered ${expected}`);
  }
  const latest = latestSnapshot(context.view);
  for (const expected of step.expectLatestOutput ?? []) {
    assert.equal(
      latest.includes(expected),
      true,
      `${context.scenario.name}/${step.input} latest snapshot did not render ${expected}`
    );
  }
  assertMaxLineWidth(context.view, step.maxLineWidth);

  for (const [name, expectedCount] of Object.entries(step.expectCalls ?? {})) {
    assert.equal(
      context.client.callCount(name as CallName) >= expectedCount,
      true,
      `${context.scenario.name}/${step.input} expected ${name} >= ${expectedCount}, got ${context.client.callCount(name as CallName)}`
    );
  }

  for (const [pathExpression, expected] of Object.entries(step.expectState ?? {})) {
    assert.deepEqual(
      readPath(context.client.currentState, pathExpression),
      expected,
      `${context.scenario.name}/${step.input} state ${pathExpression}`
    );
  }

  for (const [pathExpression, expected] of Object.entries(step.expectConfig ?? {})) {
    assert.deepEqual(
      readPath(context.client.currentConfig, pathExpression),
      expected,
      `${context.scenario.name}/${step.input} config ${pathExpression}`
    );
  }
}

async function waitForOutput(view: TestInkInstance, expected: string[], timeoutMs = 2500): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const output = terminalOutput(view);
    if (expected.every((item) => output.includes(item))) {
      return;
    }
    await delay(10);
  }
  assert.fail(`Timed out waiting for ${expected.join(", ")}.\n\nOutput:\n${terminalOutput(view)}`);
}

async function waitForCallCounts(
  client: ScenarioClient,
  expected: Partial<Record<CallName, number>>,
  timeoutMs = 2500
): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (
      Object.entries(expected).every(
        ([name, count]) => client.callCount(name as CallName) >= count
      )
    ) {
      return;
    }
    await delay(10);
  }
  assert.fail(
    `Timed out waiting for calls: ${Object.entries(expected)
      .map(([name, count]) => `${name} >= ${count}`)
      .join(", ")}`
  );
}

async function waitForPhysicalTextAfter(
  view: PhysicalTestInkInstance,
  previousWriteCount: number,
  expected: string,
  timeoutMs = 2500
): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    await delay(10);
    const output = normalizeOutput(view.frames.slice(previousWriteCount).join(""));
    if (output.includes(expected)) {
      return;
    }
  }
  assert.fail(
    `Timed out waiting for physical stdout after write ${previousWriteCount} to include ${expected}; ` +
      `got ${normalizeOutput(view.frames.slice(previousWriteCount).join(""))}`
  );
}

async function waitForPhysicalMarkerCount(
  view: PhysicalTestInkInstance,
  marker: string,
  expected: number,
  stage: string,
  timeoutMs = 2500
): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const output = normalizeOutput(view.physicalOutput());
    const actual = output.split(marker).length - 1;
    if (actual === expected) {
      return;
    }
    await delay(10);
  }
  assertPhysicalMarkerCount(view, marker, expected, stage);
}

async function waitForPhysicalSettled(
  view: PhysicalTestInkInstance,
  stableMs = 50,
  timeoutMs = 2500
): Promise<void> {
  const start = Date.now();
  let stableSince = start;
  let previousWriteCount = view.physicalWriteCount();
  while (Date.now() - start < timeoutMs) {
    await delay(10);
    const currentWriteCount = view.physicalWriteCount();
    if (currentWriteCount !== previousWriteCount) {
      previousWriteCount = currentWriteCount;
      stableSince = Date.now();
      continue;
    }
    if (Date.now() - stableSince >= stableMs) {
      return;
    }
  }
  assert.fail(`Physical output did not settle after ${timeoutMs}ms`);
}

async function waitForStdinConsumption(
  stdin: TestStdin,
  previousConsumedChunks: number,
  timeoutMs = 2500
): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    await delay(10);
    if (stdin.consumedChunkCount() > previousConsumedChunks) {
      return;
    }
  }
  assert.fail(
    `Timed out waiting for stdin consumption to exceed ${previousConsumedChunks}; ` +
      `got ${stdin.consumedChunkCount()}`
  );
}

function terminalOutput(view: TestInkInstance): string {
  const frames = view.frames.length > 0 ? view.frames : [view.lastFrame() ?? ""];
  return normalizeOutput(frames.join("\n"));
}

function latestSnapshot(view: TestInkInstance): string {
  for (let index = view.frames.length - 1; index >= 0; index -= 1) {
    const output = normalizeOutput(view.frames[index]);
    if (output.trim()) {
      return output;
    }
  }
  return normalizeOutput(view.lastFrame() ?? "");
}

function assertLatestRejectOutput(view: TestInkInstance, rejected: string[] = []): void {
  const output = latestSnapshot(view);
  for (const marker of rejected) {
    assert.equal(output.includes(marker), false, `latest snapshot unexpectedly rendered ${marker}`);
  }
}

function assertMaxLineWidth(view: TestInkInstance, maximum?: number): void {
  if (maximum === undefined) {
    return;
  }
  for (const [frameIndex, frame] of view.frames.entries()) {
    for (const line of normalizeOutput(frame).split("\n")) {
      const width = stringWidth(line);
      assert.equal(
        width <= maximum,
        true,
        `frame ${frameIndex + 1} line is ${width} columns, exceeds ${maximum}: ${line}`
      );
    }
  }
}

function assertHangingBody(
  output: string,
  marker: string,
  expected: string,
  ignoreWrapWhitespace = false
): void {
  const lines = normalizeOutput(output).split("\n");
  const start = lines.findIndex((line) => line.trimStart().startsWith(`${marker} `));
  assert.notEqual(start, -1, `missing ${marker} activity row`);
  const firstLine = lines[start];
  const leadingSpaces = firstLine.length - firstLine.trimStart().length;
  const bodyIndex = leadingSpaces + marker.length + 1;
  const bodyColumn = stringWidth(firstLine.slice(0, bodyIndex));
  assert.notEqual(firstLine[bodyIndex], " ", `${marker} must have exactly one raw marker gap`);
  const bodyLines: string[] = [];
  for (let index = start; index < lines.length; index += 1) {
    const line = lines[index];
    if (index === start) {
      bodyLines.push(line.slice(bodyIndex));
      continue;
    }
    const continuationSpaces = line.length - line.trimStart().length;
    if (!line.trim()) {
      break;
    }
    const continuationColumn = stringWidth(line.slice(0, continuationSpaces));
    assert.equal(
      continuationColumn,
      bodyColumn,
      `${marker} continuation body starts at ${continuationColumn}, expected ${bodyColumn}`
    );
    bodyLines.push(line.slice(continuationSpaces));
  }
  const actual = bodyLines.join(" ").replace(/\s+/g, " ").trim();
  assert.equal(
    ignoreWrapWhitespace ? actual.replace(/\s/g, "") : actual,
    ignoreWrapWhitespace ? expected.replace(/\s/g, "") : expected
  );
}

function assertInnerHangingBody(
  output: string,
  prefix: string,
  firstToken: string,
  continuationToken: string
): void {
  const lines = normalizeOutput(output).split("\n");
  const start = lines.findIndex((line) => line.includes(`${prefix} ${firstToken}`));
  assert.notEqual(start, -1, `missing ${prefix} ${firstToken}`);
  const first = lines[start] ?? "";
  const bodyIndex = first.indexOf(firstToken);
  assert.notEqual(bodyIndex, -1);
  const bodyColumn = stringWidth(first.slice(0, bodyIndex));
  const continuation = lines.slice(start + 1).find((line) => line.includes(continuationToken));
  assert.ok(continuation, `missing wrapped token ${continuationToken}`);
  const leading = (continuation ?? "").length - (continuation ?? "").trimStart().length;
  assert.equal(stringWidth((continuation ?? "").slice(0, leading)), bodyColumn);
}

function assertLogicalText(output: string, expected: string[]): void {
  const compact = normalizeOutput(output).replace(/[╭╮╰╯│─\s]/g, "");
  for (const item of expected) {
    const expectedCompact = item.replace(/\s/g, "");
    assert.equal(compact.includes(expectedCompact), true, `missing logical text: ${item}`);
  }
}

function assertPhysicalMarkerCount(
  view: PhysicalTestInkInstance,
  marker: string,
  expected: number,
  stage: string
): void {
  const output = normalizeOutput(view.physicalOutput());
  const actual = output.split(marker).length - 1;
  assert.equal(actual, expected, `${stage} physically printed ${marker} ${actual} times`);
}

function assertPhysicalOutputIncludes(
  view: PhysicalTestInkInstance,
  expected: string,
  stage: string
): void {
  assert.ok(normalizeOutput(view.physicalOutput()).includes(expected), stage);
}

function normalizeOutput(value: string): string {
  return value
    .replace(/\u001B\[[0-?]*[ -/]*[@-~]/g, "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n");
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function readPath(value: unknown, pathExpression: string): unknown {
  const parts = pathExpression.split(".");
  let current: unknown = value;
  for (const part of parts) {
    if (part === "length") {
      return Array.isArray(current) || typeof current === "string" ? current.length : undefined;
    }
    if (Array.isArray(current) && /^\d+$/.test(part)) {
      current = current[Number(part)];
      continue;
    }
    if (current && typeof current === "object") {
      current = (current as Record<string, unknown>)[part];
      continue;
    }
    return undefined;
  }
  return current;
}

class ScenarioClient implements TuiClient {
  readonly calls: Record<CallName, unknown[][]> = {
    health: [],
    state: [],
    config: [],
    llmSettings: [],
    testLlmSettings: [],
    submitTask: [],
    approveAction: [],
    rejectAction: [],
    resetWorkspace: [],
    registerRobot: [],
    uploadFile: [],
    sendChatStream: [],
    events: []
  };

  currentState: AgentState;
  currentConfig: ConfigResponse;

  private readonly fail: Partial<Record<CallName, string>>;
  private readonly responses: Partial<Record<QueuedCallName, ScenarioResponse[]>>;
  private readonly eventBehavior: EventBehavior;
  private readonly eventError: string;
  private readonly eventItems: ScenarioEvent[];
  private eventHandler: ((event: ApiEvent) => void) | null = null;

  constructor(private readonly scenarioCase: ScenarioCase) {
    this.currentState = clone(stateFixtures[scenarioCase.initialState ?? "ready"]);
    this.currentConfig = clone(configFixtures[scenarioCase.initialConfig ?? "default"]);
    this.fail = scenarioCase.fail ?? {};
    this.responses = clone(scenarioCase.responses ?? {});
    this.eventBehavior = scenarioCase.events?.behavior ?? "idle";
    this.eventError = scenarioCase.events?.error ?? "SSE failed";
    this.eventItems = scenarioCase.events?.items ?? [];
  }

  callCount(name: CallName): number {
    return this.calls[name].length;
  }

  publishEvent(event: ScenarioEvent): void {
    assert.ok(this.eventHandler, "SSE event handler is not active");
    if (event.state) {
      this.currentState = clone(stateFixtures[event.state]);
    }
    this.eventHandler(expandScenarioEvent(event));
  }

  async health(): Promise<HealthState> {
    this.record("health");
    await this.delayResponse();
    this.throwIfFailed("health");
    return {
      ok: true,
      ready: this.currentState.ready,
      backend: this.currentState.backend,
      message: this.currentState.message,
      workspace_path: this.currentState.workspace_path,
      config_path: this.currentState.config_path
    };
  }

  async state(): Promise<AgentState> {
    this.record("state");
    await this.delayResponse();
    this.throwIfFailed("state");
    return clone(this.currentState);
  }

  async config(): Promise<ConfigResponse> {
    this.record("config");
    await this.delayResponse();
    this.throwIfFailed("config");
    return clone(this.currentConfig);
  }

  async llmSettings(): Promise<LLMSettingsResponse> {
    this.record("llmSettings");
    await this.delayResponse();
    this.throwIfFailed("llmSettings");
    return clone(llmOk);
  }

  async testLlmSettings(): Promise<LLMSettingsResponse> {
    this.record("testLlmSettings");
    await this.delayResponse();
    this.throwIfFailed("testLlmSettings");
    return { ...clone(llmOk), message: "LLM connection test passed." };
  }

  async submitTask(task: string): Promise<{
    ok: boolean;
    message: string;
    agent_output: AgentOutput;
    state: AgentState;
  }> {
    this.record("submitTask", task);
    const response = this.nextResponse("submitTask");
    const state = this.applyState(response.state ?? "afterTask");
    return {
      ok: true,
      message: response.message ?? "Task submitted.",
      agent_output: state.plan?.plan?.agent_output ?? {},
      state
    };
  }

  async approveAction(actionId: string): Promise<{ ok: boolean; message: string; state: AgentState }> {
    this.record("approveAction", actionId);
    const response = this.nextResponse("approveAction");
    const state = this.applyState(response.state ?? "afterApprove");
    return { ok: true, message: response.message ?? `Action ${actionId} approved.`, state };
  }

  async rejectAction(actionId: string, reason: string): Promise<{ ok: boolean; message: string; state: AgentState }> {
    this.record("rejectAction", actionId, reason);
    const response = this.nextResponse("rejectAction");
    const state = this.applyState(response.state ?? "afterReject");
    return { ok: true, message: response.message ?? `Action ${actionId} rejected.`, state };
  }

  async resetWorkspace(confirm: string): Promise<{ ok: boolean; message: string; state: AgentState }> {
    this.record("resetWorkspace", confirm);
    const response = this.nextResponse("resetWorkspace");
    const state = this.applyState(response.state ?? "afterReset");
    return { ok: response.ok ?? true, message: response.message ?? "Workspace reset.", state };
  }

  async registerRobot(payload: RegisterRobotPayload): Promise<RegisterRobotResponse> {
    this.record("registerRobot", payload);
    const response = this.nextResponse("registerRobot");
    if (response.config) {
      this.currentConfig = clone(configFixtures[response.config]);
    }
    return {
      ok: true,
      message: response.message ?? "Robot registered.",
      robot_id: response.robot_id ?? payload.robot_id,
      config_path: this.currentConfig.config_path,
      config: clone(this.currentConfig.config)
    };
  }

  async uploadFile(filePath: string): Promise<UploadResponse> {
    this.record("uploadFile", filePath);
    const response = this.nextResponse("uploadFile");
    const state = this.applyState(response.state ?? "afterUpload");
    return {
      ok: true,
      message: response.message ?? "Uploaded.",
      filename: response.filename ?? path.basename(filePath),
      size_bytes: response.size_bytes ?? 0,
      result: {
        chunks_written: response.chunks_written ?? 1,
        metadata: {
          original_name: response.filename ?? path.basename(filePath),
          sha256: response.sha256 ?? "upload-sha"
        }
      },
      state
    };
  }

  async sendChatStream(
    message: string,
    onEvent: (event: ApiEvent) => void,
    _signal?: AbortSignal
  ): Promise<void> {
    this.record("sendChatStream", message);
    const response = this.nextResponse("sendChatStream");
    for (const event of response.events ?? []) {
      onEvent(expandApiEvent(event));
    }
    if (response.state) {
      this.currentState = clone(stateFixtures[response.state]);
    }
  }

  async events(onEvent: (event: ApiEvent) => void, signal?: AbortSignal): Promise<void> {
    this.record("events");
    this.eventHandler = onEvent;
    try {
      for (const event of this.eventItems) {
        onEvent(expandScenarioEvent(event));
      }

      if (this.eventBehavior === "error") {
        throw new Error(this.eventError);
      }
      if (this.eventBehavior === "clean-eof") {
        return;
      }
      await waitForAbort(signal);
    } finally {
      if (this.eventHandler === onEvent) {
        this.eventHandler = null;
      }
    }
  }

  private record(name: CallName, ...args: unknown[]): void {
    this.calls[name].push(args);
  }

  private async delayResponse(): Promise<void> {
    const responseDelayMs = this.scenarioCase.responseDelayMs ?? 0;
    if (responseDelayMs > 0) {
      await delay(responseDelayMs);
    }
  }

  private throwIfFailed(name: CallName): void {
    const message = this.fail[name];
    if (message) {
      throw new Error(message);
    }
  }

  private nextResponse(name: QueuedCallName): Exclude<ScenarioResponse, { error: string }> {
    const queue = this.responses[name] ?? [];
    const response = queue.shift() ?? {};
    if ("error" in response) {
      throw new Error(response.error);
    }
    return response;
  }

  private applyState(name: string): AgentState {
    this.currentState = clone(stateFixtures[name]);
    return clone(this.currentState);
  }
}

function expandScenarioEvent(event: ScenarioEvent): ApiEvent {
  const payload = { ...(event.payload ?? {}) };
  if (event.state) {
    payload.state = clone(stateFixtures[event.state]);
  }
  return { type: event.type, payload };
}

function expandApiEvent(event: ApiEvent): ApiEvent {
  const payload = { ...(event.payload ?? {}) };
  if (typeof payload.state === "string") {
    payload.state = clone(stateFixtures[payload.state]);
  }
  return { ...event, payload };
}

async function waitForAbort(signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  await new Promise<void>((resolve) => {
    signal?.addEventListener("abort", () => resolve(), { once: true });
  });
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function renderTui(tree: React.ReactElement, columns: number | null = 100): TestInkInstance {
  const stdout = new TestStdout(columns);
  const stderr = new TestStdout(columns);
  const stdin = new TestStdin();
  const instance = inkRender(tree, {
    stdout: stdout as NodeJS.WriteStream,
    stderr: stderr as NodeJS.WriteStream,
    stdin: stdin as NodeJS.ReadStream,
    debug: true,
    exitOnCtrlC: false,
    patchConsole: false
  });

  return {
    stdin,
    frames: stdout.frames,
    lastFrame: () => stdout.lastFrame(),
    unmount: () => instance.unmount(),
    cleanup: () => instance.cleanup()
  };
}

function renderPhysicalTui(tree: React.ReactElement, columns: number | null): PhysicalTestInkInstance {
  const stdout = new TestStdout(columns);
  const stderr = new TestStdout(columns);
  const stdin = new TestStdin();
  const instance = inkRender(tree, {
    stdout: stdout as NodeJS.WriteStream,
    stderr: stderr as NodeJS.WriteStream,
    stdin: stdin as NodeJS.ReadStream,
    debug: false,
    exitOnCtrlC: false,
    patchConsole: false
  });

  return {
    stdin,
    frames: stdout.frames,
    lastFrame: () => stdout.lastFrame(),
    physicalOutput: () => stdout.physicalOutput(),
    physicalWriteCount: () => stdout.physicalWriteCount(),
    unmount: () => instance.unmount(),
    cleanup: () => instance.cleanup()
  };
}

class TestStdout extends EventEmitter {
  readonly frames: string[] = [];
  readonly isTTY = true;
  readonly rows = 10_000;
  private frame: string | undefined;
  private output = "";

  constructor(private readonly columnCount: number | null = 100) {
    super();
  }

  get columns(): number {
    return this.columnCount === null ? undefined as unknown as number : this.columnCount;
  }

  write = (value: string): boolean => {
    this.frames.push(value);
    this.frame = value;
    this.output += value;
    return true;
  };

  lastFrame(): string | undefined {
    return this.frame;
  }

  physicalOutput(): string {
    return this.output;
  }

  physicalWriteCount(): number {
    return this.frames.length;
  }
}

class TestStdin extends EventEmitter {
  isTTY = true;
  private readonly chunks: string[] = [];
  private consumedChunks = 0;

  write = (value: string): boolean => {
    this.chunks.push(value);
    this.emit("readable");
    return true;
  };

  read(): string | null {
    const chunk = this.chunks.shift();
    if (chunk === undefined) {
      return null;
    }
    this.consumedChunks += 1;
    return chunk;
  }

  consumedChunkCount(): number {
    return this.consumedChunks;
  }

  setEncoding(): void {
    // Ink expects terminal stream methods; the test stream only emits data.
  }

  setRawMode(): void {
    // Ink expects terminal stream methods; the test stream only emits data.
  }

  resume(): void {
    // Ink expects terminal stream methods; the test stream only emits data.
  }

  pause(): void {
    // Ink expects terminal stream methods; the test stream only emits data.
  }

  ref(): void {
    // Keep Node's test runner free to exit.
  }

  unref(): void {
    // Keep Node's test runner free to exit.
  }
}

const llmOk: LLMSettingsResponse = {
  ok: true,
  settings: {
    model: "mock-llm",
    has_api_key: true
  }
};

const configFixtures: Record<string, ConfigResponse> = {
  default: {
    ok: true,
    message: "ok",
    config_path: "physical-agent.yaml",
    config: {
      workspace: { path: "./workspace", backend: "sqlite" },
      watch: { tick_ms: 500, require_human_approval: false },
      agent: { planner: "llm", model: "mock-llm", api_key: "super-secret" },
      robots: {
        arm_1: {
          driver: "mock_arm",
          execution_mode: "simulation",
          config: {
            mode: "mock",
            endpoint: "loopback",
            token: "super-secret-token",
            bounds: { x: [-1, 1], y: [-1, 1], z: [0, 1] }
          }
        }
      }
    }
  },
  registeredRobot: {
    ok: true,
    message: "ok",
    config_path: "physical-agent.yaml",
    config: {
      workspace: { path: "./workspace", backend: "sqlite" },
      watch: { tick_ms: 500, require_human_approval: false },
      agent: { planner: "llm", model: "mock-llm", api_key: "super-secret" },
      robots: {
        arm_1: {
          driver: "mock_arm",
          execution_mode: "simulation",
          config: { mode: "mock", endpoint: "loopback", token: "super-secret-token" }
        },
        sim_1: {
          driver: "mock_arm",
          execution_mode: "simulation",
          config: { mode: "sim" }
        }
      }
    }
  }
};

const baseActionState: AgentState = {
  ready: true,
  backend: "sqlite",
  message: "Ready.",
  workspace_path: "C:/workspace",
  config_path: "physical-agent.yaml",
  chat: { messages: [] },
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
        status: "idle",
        capabilities: [
          {
            name: "pick",
            description: "Pick an object by object_id.",
            requires_approval: true,
            params_schema: {
              type: "object",
              properties: { object_id: { type: "string" } },
              required: ["object_id"]
            },
            constraints: { bounds: { x: [-1, 1] } }
          },
          {
            name: "observe",
            description: "Observe the workspace.",
            requires_approval: false,
            params_schema: { type: "object", properties: {} },
            constraints: {}
          }
        ]
      }
    }
  },
  actions: {
    pending: [
      {
        id: "act_001",
        robot: "arm_1",
        capability: "pick",
        reason: "Pick the red block.",
        metadata: { approval: { required: true, status: "pending" } }
      },
      {
        id: "act_002",
        robot: "arm_1",
        capability: "observe",
        reason: "Observe before moving.",
        metadata: { approval: { required: true, status: "pending" } }
      }
    ],
    completed: [],
    cancelled: []
  },
  uploads: { uploads: [] }
};

const formattedChatReply = [
  "## Current Workspace",
  "",
  "**Robot state**",
  "- `arm_1` is currently **idle**.",
  "",
  "**Visible objects**",
  "1. **red_block**",
  "   - Type: block",
  "   - Color: red"
].join("\n");

const stateFixtures: Record<string, AgentState> = {
  ready: {
    ...baseActionState,
    actions: { pending: [], completed: [], cancelled: [] }
  },
  chatReady: baseActionState,
  chatAfterReply: {
    ...baseActionState,
    chat: {
      messages: [
        { role: "assistant", content: "Previous context", created_at: "2026-07-08T00:00:00Z" },
        { role: "user", content: "hello robot", created_at: "2026-07-08T00:01:00Z" },
        { role: "assistant", content: formattedChatReply, created_at: "2026-07-08T00:01:01Z" }
      ]
    }
  },
  actionsReady: baseActionState,
  afterTask: {
    ...baseActionState,
    actions: {
      pending: [
        ...(baseActionState.actions?.pending ?? []),
        {
          id: "act_task",
          robot: "arm_1",
          capability: "pick",
          reason: "Task-created action.",
          metadata: {}
        }
      ],
      completed: [],
      cancelled: []
    }
  },
  beforeCompleted: {
    ...baseActionState,
    actions: {
      pending: [
        ...(baseActionState.actions?.pending ?? []),
        {
          id: "act_task",
          robot: "arm_1",
          capability: "pick",
          reason: "Task-created action.",
          metadata: {}
        },
        {
          id: "act_done",
          robot: "arm_1",
          capability: "move_to",
          params: { x: 120, y: 45, z: 0 },
          status: "pending",
          metadata: {}
        }
      ],
      completed: [],
      cancelled: []
    }
  },
  afterCompleted: {
    ...baseActionState,
    plan: {
      plan: {
        agent_output: {
          schema: "physical-agent/agent-output/v1",
          status: "failed",
          decision: "propose",
          lifecycle: "submitted",
          tasks: [
            {
              id: "task:safety_gate:act_done",
              kind: "safety_gate",
              owner: "watch",
              status: "failed",
              action_id: "act_done",
              depends_on: [],
              mandatory: true,
              policy_source: "SAFETY.md",
              checks: [{ code: "safety.robot.known" }]
            }
          ]
        }
      }
    },
    chat: {
      messages: [
        {
          role: "assistant",
          content: "Server recorded completion.",
          created_at: "2026-07-19T12:00:00Z"
        }
      ]
    },
    actions: {
      pending: [
        {
          id: "act_001",
          robot: "arm_1",
          capability: "pick",
          reason: "Pick the red block.",
          metadata: { approval: { required: true, status: "approved" } }
        },
        {
          id: "act_task",
          robot: "arm_1",
          capability: "pick",
          reason: "Task-created action.",
          metadata: {}
        }
      ],
      completed: [
        {
          id: "act_done",
          robot: "arm_1",
          capability: "move_to",
          params: { x: 120, y: 45, z: 0 },
          status: "completed",
          metadata: {}
        }
      ],
      cancelled: [
        {
          id: "act_002",
          robot: "arm_1",
          capability: "observe",
          reason: "Observe before moving.",
          status: "cancelled",
          metadata: { approval: { required: true, status: "rejected" } }
        }
      ]
    }
  },
  afterApprove: {
    ...baseActionState,
    actions: {
      pending: [
        {
          id: "act_001",
          robot: "arm_1",
          capability: "pick",
          reason: "Pick the red block.",
          metadata: { approval: { required: true, status: "approved" } }
        },
        ...(baseActionState.actions?.pending ?? []).slice(1),
        {
          id: "act_task",
          robot: "arm_1",
          capability: "pick",
          reason: "Task-created action.",
          metadata: {}
        }
      ],
      completed: [],
      cancelled: []
    }
  },
  afterReject: {
    ...baseActionState,
    actions: {
      pending: [
        {
          id: "act_001",
          robot: "arm_1",
          capability: "pick",
          reason: "Pick the red block.",
          metadata: { approval: { required: true, status: "approved" } }
        },
        {
          id: "act_task",
          robot: "arm_1",
          capability: "pick",
          reason: "Task-created action.",
          metadata: {}
        }
      ],
      completed: [],
      cancelled: [
        {
          id: "act_002",
          robot: "arm_1",
          capability: "observe",
          reason: "Observe before moving.",
          status: "cancelled",
          metadata: { approval: { required: true, status: "rejected" } }
        }
      ]
    }
  },
  afterReset: {
    ...baseActionState,
    actions: { pending: [], completed: [], cancelled: [] },
    chat: { messages: [] },
    uploads: { uploads: [] }
  },
  robotsReady: baseActionState,
  uploadReady: {
    ...baseActionState,
    actions: { pending: [], completed: [], cancelled: [] },
    uploads: { uploads: [] }
  },
  afterUpload: {
    ...baseActionState,
    actions: { pending: [], completed: [], cancelled: [] },
    uploads: {
      uploads: [
        {
          original_name: "manual.md",
          stored_name: "abc-manual.md",
          sha256: "abc123def4567890",
          size_bytes: 128,
          suffix: ".md",
          status: "stored",
          memory_note_created: true
        }
      ]
    }
  },
  afterIngest: {
    ...baseActionState,
    actions: { pending: [], completed: [], cancelled: [] },
    uploads: {
      uploads: [
        {
          original_name: "manual.md",
          stored_name: "abc-manual.md",
          sha256: "abc123def4567890",
          size_bytes: 128,
          suffix: ".md",
          status: "stored",
          memory_note_created: true
        },
        {
          original_name: "notes.txt",
          stored_name: "def-notes.txt",
          sha256: "def456abc1237890",
          size_bytes: 64,
          suffix: ".txt",
          status: "stored",
          memory_note_created: true
        }
      ]
    }
  }
};
