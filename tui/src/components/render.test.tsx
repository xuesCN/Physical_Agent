import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { render } from "ink-testing-library";
import { ActionsPanel } from "./ActionsPanel.js";
import { ChatPanel } from "./ChatPanel.js";
import { ConfigPanel } from "./ConfigPanel.js";
import { RobotDetailPanel } from "./RobotDetailPanel.js";
import { RobotsPanel } from "./RobotsPanel.js";
import { StatusBar } from "./StatusBar.js";
import { UploadsPanel } from "./UploadsPanel.js";
import { normalizeTerminalText } from "./textFormat.js";
import type { AgentState, ConfigResponse } from "../types.js";

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
  assert.match(view.lastFrame() ?? "", /streaming/);
  assert.match(view.lastFrame() ?? "", /partial reply/);
  assert.doesNotMatch(view.lastFrame() ?? "", /No chat yet/);
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
  assert.match(view.lastFrame() ?? "", /act_001/);
  assert.match(view.lastFrame() ?? "", /approval required/);
});

test("ActionsPanel renders compiled mandatory SafetyGate tasks and feedback status", () => {
  const view = render(
    <ActionsPanel
      force
      state={{
        ready: true,
        plan: {
          plan: {
            agent_output: {
              schema: "physical-agent/agent-output/v1",
              status: "waiting_execution",
              decision: "propose",
              lifecycle: "submitted",
              tasks: [
                {
                  id: "task:safety_gate:act_001",
                  kind: "safety_gate",
                  owner: "watch",
                  status: "queued",
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
              status: "passed"
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
  assert.match(frame, /passed/);
});

test("ConfigPanel renders configured robots without exposing secrets", () => {
  const view = render(
    <ConfigPanel
      config={sampleConfig()}
      state={sampleState()}
    />
  );
  const frame = view.lastFrame() ?? "";
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
  assert.match(frame, /manual.md/);
  assert.match(frame, /untrusted yes/);
  assert.doesNotMatch(frame, /full file content/);
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
