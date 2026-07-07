import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { render } from "ink-testing-library";
import { ActionsPanel } from "./ActionsPanel.js";
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
        message: "Ready."
      }}
    />
  );
  assert.match(view.lastFrame() ?? "", /Physical Agent TUI/);
  assert.match(view.lastFrame() ?? "", /sqlite/);
  assert.match(view.lastFrame() ?? "", /SSE/);
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
