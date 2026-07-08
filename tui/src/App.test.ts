import assert from "node:assert/strict";
import test from "node:test";
import {
  runTuiChatStream,
  shouldFallbackAfterSseClose,
  sseClosedFallbackMessage,
  sseErrorFallbackMessage,
  watchStatusFromEvent
} from "./App.js";
import type { AgentState } from "./types.js";

test("chat stream rejection clears streaming state and reports readable error", async () => {
  const calls = createChatCalls();
  await runTuiChatStream(
    {
      sendChatStream: async () => {
        throw new Error("network gone");
      }
    },
    "hello",
    calls.handlers
  );

  assert.deepEqual(calls.streaming, [true, false]);
  assert.deepEqual(calls.streamingText, [""]);
  assert.equal(calls.notices.length, 1);
  assert.match(calls.notices[0], /Streaming chat failed/);
  assert.match(calls.notices[0], /network gone/);
});

test("chat stream abort clears streaming state without noisy failure", async () => {
  const calls = createChatCalls();
  const abortError = new Error("The operation was aborted");
  abortError.name = "AbortError";

  await runTuiChatStream(
    {
      sendChatStream: async () => {
        throw abortError;
      }
    },
    "hello",
    calls.handlers
  );

  assert.deepEqual(calls.streaming, [true, false]);
  assert.deepEqual(calls.notices, []);
});

test("chat stream done updates state and clears streaming", async () => {
  const calls = createChatCalls();
  const readyState = createReadyState();

  await runTuiChatStream(
    {
      sendChatStream: async (_message, onEvent) => {
        onEvent({ type: "delta", payload: { delta: "hi" } });
        onEvent({ type: "done", payload: { state: readyState } });
      }
    },
    "hello",
    calls.handlers
  );

  assert.deepEqual(calls.streaming, [true, false]);
  assert.deepEqual(calls.streamingText, ["", "hi", ""]);
  assert.deepEqual(calls.states, [readyState]);
});

test("SSE clean EOF fallback ignores only intentional abort", () => {
  const controller = new AbortController();
  assert.equal(shouldFallbackAfterSseClose(controller.signal), true);
  assert.equal(sseClosedFallbackMessage(), "SSE stream closed; using polling fallback.");

  controller.abort();
  assert.equal(shouldFallbackAfterSseClose(controller.signal), false);
});

test("SSE thrown error fallback is readable", () => {
  assert.equal(
    sseErrorFallbackMessage(new Error("socket broke")),
    "SSE disconnected; polling fallback active. socket broke"
  );
});

test("watch_enabled hello event maps to real watch status", () => {
  assert.equal(watchStatusFromEvent({ type: "hello", payload: { watch_enabled: true } }), "enabled");
  assert.equal(watchStatusFromEvent({ type: "hello", payload: { watch_enabled: false } }), "disabled");
  assert.equal(watchStatusFromEvent({ type: "hello", payload: { watch_enabled: "true" } }), null);
  assert.equal(watchStatusFromEvent({ type: "state", payload: {} }), null);
});

function createChatCalls() {
  const streaming: boolean[] = [];
  const streamingText: string[] = [];
  const states: AgentState[] = [];
  const notices: string[] = [];
  return {
    streaming,
    streamingText,
    states,
    notices,
    handlers: {
      setStreaming(value: boolean) {
        streaming.push(value);
      },
      setStreamingText(value: string) {
        streamingText.push(value);
      },
      setState(state: AgentState) {
        states.push(state);
      },
      setNotice(message: string) {
        notices.push(message);
      }
    }
  };
}

function createReadyState(): AgentState {
  return {
    ready: true,
    backend: "sqlite",
    message: "Ready.",
    actions: { pending: [], completed: [], cancelled: [] },
    chat: { messages: [] }
  };
}
