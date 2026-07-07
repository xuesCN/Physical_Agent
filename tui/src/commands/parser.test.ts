import assert from "node:assert/strict";
import test from "node:test";
import { parseCommand } from "./parser.js";

test("parses chat text", () => {
  assert.deepEqual(parseCommand("hello"), { type: "chat", text: "hello" });
});

test("parses task", () => {
  assert.deepEqual(parseCommand("/task pick block"), { type: "task", text: "pick block" });
});

test("parses approve", () => {
  assert.deepEqual(parseCommand("/approve act_001"), { type: "approve", actionId: "act_001" });
});

test("parses reject", () => {
  assert.deepEqual(parseCommand("/reject act_001 unsafe"), {
    type: "reject",
    actionId: "act_001",
    reason: "unsafe"
  });
});

test("parses reset refresh help quit", () => {
  assert.deepEqual(parseCommand("/reset true"), { type: "reset", confirm: "true" });
  assert.deepEqual(parseCommand("/refresh"), { type: "refresh" });
  assert.deepEqual(parseCommand("/help"), { type: "help" });
  assert.deepEqual(parseCommand("/quit"), { type: "quit" });
});

test("rejects unknown and direct hardware commands", () => {
  assert.equal(parseCommand("/wat").type, "unknown");
  const command = parseCommand("/execute act_001");
  assert.equal(command.type, "unknown");
  assert.match(command.message, /watch remains the only executor/);
});
