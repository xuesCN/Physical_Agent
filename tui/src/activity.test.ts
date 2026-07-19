import assert from "node:assert/strict";
import test from "node:test";
import {
  collectActionActivityEntries,
  createActionActivityTracker,
  resetActionActivityTracker
} from "./activity.js";
import { formatActionInvocation } from "./formatters/action.js";
import type { ActionItem, AgentState } from "./types.js";

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

  const bounded = formatActionInvocation({
    id: "act_2",
    robot: "arm_1",
    capability: "inspect",
    params: { note: "x".repeat(100) }
  });
  assert.equal(bounded, `arm_1.inspect(note=\"${"x".repeat(58)}…)`);

  assert.equal(
    formatActionInvocation({
      id: "act_3",
      robot: "arm_1",
      capability: "configure",
      params: {
        API_KEY: "one",
        client_secret: "two",
        password: "three",
        "session-token": "four",
        payload: { enabled: true }
      }
    }),
    "arm_1.configure(API_KEY=\"[redacted]\", client_secret=\"[redacted]\", password=\"[redacted]\", payload={\"enabled\":true}, session-token=\"[redacted]\")"
  );
});

test("action invocation recursively redacts camelCase sensitive fields and safely bounds cycles", () => {
  assert.equal(
    formatActionInvocation({
      id: "act_nested",
      robot: "arm_1",
      capability: "configure",
      params: {
        accessToken: "top-secret",
        config: { credentials: { apiKey: "nested-secret" }, enabled: true },
        items: [{ label: "safe", clientPassword: "array-secret" }]
      }
    }),
    "arm_1.configure(accessToken=\"[redacted]\", config={\"credentials\":{\"apiKey\":\"[redacted]\"},\"enabled\":true}, items=[{\"clientPassword\":\"[redacted]\",\"label\":\"safe\"}])"
  );

  const cyclic: Record<string, unknown> = { label: "safe" };
  cyclic.self = cyclic;
  assert.equal(
    formatActionInvocation({
      id: "act_cycle",
      robot: "arm_1",
      capability: "inspect",
      params: { payload: cyclic }
    }),
    "arm_1.inspect(payload={\"label\":\"safe\",\"self\":\"[circular]\"})"
  );
});

test("null and missing-action snapshots do not establish the baseline", () => {
  const tracker = createActionActivityTracker();
  assert.deepEqual(collectActionActivityEntries(null, tracker), []);
  assert.deepEqual(collectActionActivityEntries({ ready: true }, tracker), []);
  assert.equal(tracker.initialized, false);

  assert.deepEqual(collectActionActivityEntries(pendingState, tracker), []);
  assert.equal(tracker.initialized, true);
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

test("an action must be active in a prior observation before terminal emission", () => {
  const tracker = createActionActivityTracker();
  collectActionActivityEntries(stateWith({}), tracker);
  const contradictory = stateWith({
    pending: [{ id: "act_same", robot: "arm_1", capability: "move_to", metadata: {} }],
    completed: [{ id: "act_same", robot: "arm_1", capability: "move_to", metadata: {} }]
  });
  assert.deepEqual(collectActionActivityEntries(contradictory, tracker), []);

  const feedbackOnly: AgentState = {
    ...contradictory,
    feedback: { history: [{ action_id: "act_same", status: "failed" }] }
  };
  assert.deepEqual(collectActionActivityEntries(feedbackOnly, tracker), []);
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

test("emitted action activity owns an immutable nested action snapshot", () => {
  const tracker = createActionActivityTracker();
  collectActionActivityEntries(pendingState, tracker);
  const sourceAction: ActionItem = {
    id: "act_1",
    robot: "arm_1",
    capability: "move_to",
    params: { target: { pose: [120, 45, 0] } },
    metadata: { approval: { required: true, status: "approved" } },
    depends_on: ["act_parent"]
  };
  const entry = collectActionActivityEntries(stateWith({ completed: [sourceAction] }), tracker)[0];

  ((sourceAction.params?.target as { pose: number[] }).pose)[0] = 999;
  ((sourceAction.metadata?.approval as Record<string, unknown>)).status = "mutated";
  sourceAction.depends_on?.push("act_late");

  assert.deepEqual(entry.action, {
    id: "act_1",
    robot: "arm_1",
    capability: "move_to",
    params: { target: { pose: [120, 45, 0] } },
    metadata: { approval: { required: true, status: "approved" } },
    depends_on: ["act_parent"],
    status: "completed"
  });
});

test("an uncloneable terminal action does not discard valid batch entries or close itself", () => {
  const tracker = createActionActivityTracker();
  collectActionActivityEntries(stateWith({
    pending: [
      { id: "act_good", robot: "arm_1", capability: "move_to", metadata: {} },
      { id: "act_bad", robot: "arm_1", capability: "inspect", metadata: {} }
    ]
  }), tracker);
  const goodTerminal: ActionItem = {
    id: "act_good",
    robot: "arm_1",
    capability: "move_to",
    params: { target: { x: 120 } },
    metadata: {}
  };
  const badTerminal: ActionItem = {
    id: "act_bad",
    robot: "arm_1",
    capability: "inspect",
    params: { injected: () => "not cloneable" },
    metadata: {}
  };

  let firstBatch: ReturnType<typeof collectActionActivityEntries> = [];
  let failure: unknown = null;
  try {
    firstBatch = collectActionActivityEntries(
      stateWith({ completed: [goodTerminal, badTerminal] }),
      tracker
    );
  } catch (error) {
    failure = error;
  }
  const afterFirst = {
    active: [...tracker.active],
    closed: [...tracker.closed]
  };

  const recovered = collectActionActivityEntries(stateWith({
    completed: [{
      id: "act_bad",
      robot: "arm_1",
      capability: "inspect",
      params: { injected: "cloneable" },
      metadata: {}
    }]
  }), tracker);
  const duplicate = collectActionActivityEntries(stateWith({
    completed: [{
      id: "act_bad",
      robot: "arm_1",
      capability: "inspect",
      params: { injected: "cloneable" },
      metadata: {}
    }]
  }), tracker);

  assert.deepEqual({
    failure: failure instanceof Error ? failure.name : failure,
    first: firstBatch.map((entry) => entry.id),
    afterFirst,
    recovered: recovered.map((entry) => entry.id),
    duplicate: duplicate.map((entry) => entry.id)
  }, {
    failure: null,
    first: ["action-0-act_good"],
    afterFirst: { active: ["act_bad"], closed: ["act_good"] },
    recovered: ["action-0-act_bad"],
    duplicate: []
  });
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

test("cancelled uses the newest untagged failed or cancelled action-result", () => {
  const tracker = createActionActivityTracker();
  collectActionActivityEntries(pendingState, tracker);
  const cancelled: AgentState = {
    ...stateWith({
      cancelled: [{ id: "act_1", robot: "arm_1", capability: "move_to", metadata: {} }]
    }),
    feedback: {
      history: [
        { action_id: "act_1", status: "failed" },
        { action_id: "another", status: "cancelled" },
        { action_id: "act_1", status: "cancelled" },
        { event: "driver_result", action_id: "act_1", status: "failed" }
      ]
    }
  };
  assert.deepEqual(collectActionActivityEntries(cancelled, tracker).map((item) => item.outcome), ["cancelled"]);
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
  assert.equal(tracker.generation, 1);
  assert.equal(tracker.initialized, false);
  assert.equal(tracker.active.size, 0);
  assert.equal(tracker.closed.size, 0);
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
