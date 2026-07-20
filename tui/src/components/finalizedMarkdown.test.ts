import assert from "node:assert/strict";
import test from "node:test";
import { parseFinalizedBlocks } from "./finalizedMarkdown.js";

test("parses the screenshot-shaped nested workspace reply by block", () => {
  const blocks = parseFinalizedBlocks([
    "Here's a detailed rundown.", "", "## Current Workspace", "", "**Robot state**",
    "- `arm_1` is currently **idle**.", "", "**Visible objects**", "1. **red_block**",
    "   - Type: block", "   - Color: red", "2. **tray**", "   - Type: tray"
  ].join("\n"));

  assert.deepEqual(blocks.map((block) => block.kind), [
    "paragraph", "blank", "heading", "blank", "paragraph", "list", "blank", "paragraph", "list"
  ]);
  const objectList = blocks.at(-1);
  assert.equal(objectList?.kind, "list");
  if (objectList?.kind !== "list") throw new Error("expected object list");
  assert.deepEqual(objectList.items.map((item) => [item.depth, item.marker]), [
    [0, "1."], [1, "-"], [1, "-"], [0, "2."], [1, "-"]
  ]);
});

test("unsupported paragraph is local while adjacent supported blocks survive", () => {
  const blocks = parseFinalizedBlocks([
    "## Before", "", "| Name | State |", "| --- | --- |", "| arm | **idle** |", "", "**After**"
  ].join("\n"));

  assert.deepEqual(blocks.map((block) => block.kind), ["heading", "blank", "literal", "blank", "paragraph"]);
  const literal = blocks[2];
  assert.equal(literal.kind, "literal");
  if (literal.kind !== "literal") throw new Error("expected literal table");
  assert.deepEqual(literal.lines, ["| Name | State |", "| --- | --- |", "| arm | **idle** |"]);
});

test("list indentation stack accepts common deltas and rejects invalid runs", () => {
  for (const spaces of [2, 3, 4, 8]) {
    const parsed = parseFinalizedBlocks(`1. root\n${" ".repeat(spaces)}- child`);
    assert.equal(parsed[0]?.kind, "list");
    if (parsed[0]?.kind !== "list") throw new Error("expected list");
    assert.deepEqual(parsed[0].items.map((item) => item.depth), [0, 1]);
  }

  for (const value of [
    "- root\n  - child\n    - grandchild\n      - too deep",
    "  - root\n    - child\n   - unknown dedent",
    "- root\n\t- tab child",
    "- root\n- ",
    "- [ ] task item"
  ]) {
    assert.equal(parseFinalizedBlocks(value)[0]?.kind, "literal", value);
  }
});

test("preserves mixed three-level list markers including repeated two-digit numbers", () => {
  const blocks = parseFinalizedBlocks([
    "10. **root**", "   - child", "      7. `grandchild`", "10. repeated"
  ].join("\n"));
  assert.equal(blocks[0]?.kind, "list");
  if (blocks[0]?.kind !== "list") throw new Error("expected mixed list");
  assert.deepEqual(
    blocks[0].items.map((item) => [item.depth, item.marker, item.ordered]),
    [[0, "10.", true], [1, "-", false], [2, "7.", true], [0, "10.", true]]
  );
});

test("fence grammar has exact closed reserved nested and EOF behavior", () => {
  const code = parseFinalizedBlocks("```ts\nconst x = 1;\n\n```\n## After");
  assert.deepEqual(code.map((block) => block.kind), ["code", "heading"]);
  assert.equal(code[0]?.kind === "code" ? code[0].language : null, "ts");
  assert.deepEqual(code[0]?.kind === "code" ? code[0].lines : null, ["const x = 1;", ""]);

  for (const value of [
    "```Action-Draft\n{\"actions\":[]}\n```\n## After",
    "```python!\nprint(1)\n```\n## After",
    "```ts\n```js\nvalue\n```\n## After"
  ]) {
    const parsed = parseFinalizedBlocks(value);
    assert.equal(parsed[0]?.kind, "literal", value);
    if (parsed[0]?.kind !== "literal") throw new Error(`expected literal fence: ${value}`);
    assert.deepEqual(parsed[0].lines, value.split("\n").slice(0, -1), value);
    assert.equal(parsed.at(-1)?.kind, "heading", value);
  }

  const unclosed = parseFinalizedBlocks("```ts\nconst x = 1;\n## Still code");
  assert.equal(unclosed.length, 1);
  assert.equal(unclosed[0]?.kind, "literal");
  assert.deepEqual(unclosed[0]?.kind === "literal" ? unclosed[0].lines : null, ["```ts", "const x = 1;", "## Still code"]);
});

test("malformed heading inline falls back only for that heading line", () => {
  const blocks = parseFinalizedBlocks("## Broken **bold\nplain **safe**");
  assert.deepEqual(blocks.map((block) => block.kind), ["literal", "paragraph"]);
  assert.deepEqual(blocks[0]?.kind === "literal" ? blocks[0].lines : null, ["## Broken **bold"]);
  assert.deepEqual(
    blocks[1]?.kind === "paragraph" ? blocks[1].lines[0]?.map((segment) => segment.text).join("") : null,
    "plain safe"
  );
});

test("paragraph grouping preserves every source line break", () => {
  const blocks = parseFinalizedBlocks("first **line**\nsecond `line`\nthird");
  assert.equal(blocks[0]?.kind, "paragraph");
  if (blocks[0]?.kind !== "paragraph") throw new Error("expected paragraph");
  assert.equal(blocks[0].lines.length, 3);
  assert.deepEqual(blocks[0].lines.map((line) => line.map((segment) => segment.text).join("")), ["first line", "second line", "third"]);
});
