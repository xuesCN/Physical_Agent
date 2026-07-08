import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { render } from "ink-testing-library";
import { ActionsPanel } from "./ActionsPanel.js";
import { ChatPanel } from "./ChatPanel.js";
import { StatusBar } from "./StatusBar.js";

test("StatusBar renders connection state", () => {
  const view = render(
    <StatusBar
      status={{
        apiBase: "http://127.0.0.1:8766",
        connected: true,
        mode: "sse",
        lastRefresh: "12:00:00",
        backend: "sqlite",
        watch: "enabled",
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
  assert.match(view.lastFrame() ?? "", /Watch: enabled/);
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
        watch: "enabled",
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

test("StatusBar renders unknown and disabled watch states without snapshot wording", () => {
  const unknown = render(
    <StatusBar
      status={{
        apiBase: "http://127.0.0.1:8766",
        connected: false,
        mode: "polling",
        lastRefresh: null,
        backend: "-",
        watch: "unknown",
        llm: {
          state: "unknown",
          model: "-",
          hasApiKey: null
        },
        message: "Loading"
      }}
    />
  );
  assert.match(unknown.lastFrame() ?? "", /Watch: unknown/);
  assert.doesNotMatch(unknown.lastFrame() ?? "", /snapshot/);
  unknown.unmount();

  const disabled = render(
    <StatusBar
      status={{
        apiBase: "http://127.0.0.1:8766",
        connected: true,
        mode: "sse",
        lastRefresh: "12:00:00",
        backend: "sqlite",
        watch: "disabled",
        llm: {
          state: "checking",
          model: "model-a",
          hasApiKey: false
        },
        message: "Ready."
      }}
    />
  );
  assert.match(disabled.lastFrame() ?? "", /Watch: disabled/);
});

test("ChatPanel renders long content without hard truncation", () => {
  const longAnswer = `first line ${"x".repeat(230)}\nsecond line survives`;
  const view = render(
    <ChatPanel
      messages={[
        {
          role: "assistant",
          content: longAnswer,
          created_at: "2026-07-08T12:00:00Z"
        }
      ]}
    />
  );

  const frame = view.lastFrame() ?? "";
  assert.match(frame, /second line survives/);
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
