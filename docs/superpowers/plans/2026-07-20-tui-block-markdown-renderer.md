# T4.2 TUI Block Markdown Renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace finalized assistant whole-message Markdown fallback with a display-safe block renderer that supports headings, paragraphs, three-level mixed lists, bold, inline code, and ordinary closed code fences while preserving every unsupported block literally.

**Architecture:** Move deterministic Markdown recognition into a React-free `finalizedMarkdown.ts` parser that always returns a complete ordered block list. Keep `FinalizedText.tsx` as an Ink-only renderer, then introduce a small `HangingRow` layout primitive for list/code prefixes so terminal wrapping is measured by Ink inside the existing `MessageRow` width budget. Streaming and all non-assistant roles stay on their current literal paths.

**Tech Stack:** TypeScript 5.7, React 18, Ink 5.2, Node 20 test runner, `ink-testing-library`, existing `string-width` test dependency, Python 3.12 repository gates.

## Global Constraints

- `driver.execute` remains reachable only from the watch execution call stack; TUI code must not import backend/watch/driver/sqlite modules.
- Every physical action still passes SafetyGate with `SAFETY.md` as file truth; this plan changes presentation only.
- Do not add a Markdown runtime dependency or modify `tui/package.json` / `tui/package-lock.json`.
- Format only finalized assistant entries. Streaming assistant, user, draft, system, and unknown roles remain literal.
- Generic top-level closed triple-backtick fences are presentation-only; case-folded `action-draft` fences remain fully literal and never become Draft/actions.
- Preserve normalized source line breaks. Unsupported content must end as visible literal text, never an empty block or render exception.
- Support list depth 0..2 only. A fourth distinct indentation column, tab candidate, empty item, task-list body, or bad dedent makes that complete list-like run literal.
- Validate finite terminal widths at exactly 24, 48, and 100 columns with `string-width`; unknown-width behavior must not invent a numeric terminal limit.
- Keep PR #1 OPEN + draft. Do not merge, mark ready, or unfreeze unrelated features.
- Preserve the five pre-existing untracked user files; never stage them.

---

## File Structure

- Create `tui/src/components/finalizedMarkdown.ts`: pure normalized block/inline model and deterministic scanner; no React or Ink imports.
- Create `tui/src/components/finalizedMarkdown.test.ts`: parser grammar, block-local fallback, exact fence/list consumption, and source-line preservation.
- Create `tui/src/components/HangingRow.tsx`: presentation-only fixed prefix + shrinkable body row used inside finalized Markdown.
- Modify `tui/src/components/FinalizedText.tsx`: render parser blocks and inline segments; no scanner logic remains here.
- Modify `tui/src/components/render.test.tsx`: logical Ink output, role boundary, code/list styling, literal fallback, and blank-line coverage.
- Modify `tui/tests/scenario-runner.test.tsx`: physical stdout width/hanging assertions and nested-Markdown chat state fixture.
- Modify `tui/tests/scenarios/chat.scenario`: real chat round-trip with nested Markdown, positive clean-output assertions, and raw-marker rejection.
- Create/delete `docs/brief-t4-2-block-markdown-renderer.zh-CN.md`: temporary round brief required before code and removed at closure.
- Modify `docs/SPEC.zh-CN.md`, `docs/PLAYBOOK.zh-CN.md`, `docs/REFACTORING.zh-CN.md`, and the T4.2 design status only during final closure.

---

### Task 1: Pure block parser and block-local fallback

**Files:**
- Create: `docs/brief-t4-2-block-markdown-renderer.zh-CN.md`
- Create: `tui/src/components/finalizedMarkdown.ts`
- Create: `tui/src/components/finalizedMarkdown.test.ts`
- Reference: `tui/src/components/FinalizedText.tsx:1-185`
- Reference: `docs/superpowers/specs/2026-07-20-tui-block-markdown-renderer-design.md`

**Interfaces:**
- Consumes: `normalizeTerminalText(value: string): string` from `tui/src/components/textFormat.ts`.
- Produces: `parseFinalizedBlocks(value: string): FinalizedBlock[]` and exported discriminated types `InlineSegment`, `ListItem`, and `FinalizedBlock`.
- Invariant: every normalized input line belongs to exactly one returned block; the function does not return `null` and does not throw for user content.

- [ ] **Step 1: Create the required temporary round brief before code**

Create `docs/brief-t4-2-block-markdown-renderer.zh-CN.md` with exactly this scope:

```markdown
# T4.2 轮次 brief：finalized assistant 块级 Markdown

日期：2026-07-20

## 范围

- 只修改 TUI finalized assistant 的 presentation parser/renderer。
- whole-message fallback 收窄为 block-local fallback。
- 支持 heading、paragraph、最多三层 mixed list、bold、inline code 和普通闭合 fenced code。
- 保持 streaming/user/draft/unknown literal 与 `action-draft` 逐字边界。

## 验收

- 用户截图等价回复不暴露合法 `##`、`**` 和 inline-code 标记。
- 24/48/100 列 nested list/code 不超宽，续行悬挂到正文起点。
- unsupported block 不拖累相邻合法 block，畸形输入不丢内容。
- TUI typecheck/full/build、Python safety/full、独立 review 与 exact-head CI 全绿。

## 范围外

- 不实现完整 CommonMark/GFM、表格、链接、HTML、引用、task list 或语法高亮。
- 不修改 prompt、API、SQLite、watch、driver、SafetyGate、SAFETY.md、审批或 action wire。
- 不解冻其他功能，不合并或 mark-ready draft PR。
```

Do not stage this brief in Tasks 1–3; it remains a visible temporary guard and is deleted in Task 4.

- [ ] **Step 2: Record the clean baseline**

Run from `tui/`:

```powershell
npm.cmd run typecheck
npm.cmd test
```

Expected before new tests: typecheck exits 0 and the existing suite reports `108/108` passing.

Run from repository root:

```powershell
git status --short --branch
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) { throw 'execution baseline index is not clean' }
```

Expected: design commit `5384f5d` and this implementation-plan commit are the only local committed deltas; the index is empty; the temporary T4.2 brief plus the five protected user files are untracked, with no unrelated tracked modifications.

- [ ] **Step 3: Write parser RED tests**

Create `tui/src/components/finalizedMarkdown.test.ts` with concrete parser contracts:

```ts
import assert from "node:assert/strict";
import test from "node:test";
import { parseFinalizedBlocks } from "./finalizedMarkdown.js";

test("parses the screenshot-shaped nested workspace reply by block", () => {
  const blocks = parseFinalizedBlocks([
    "Here's a detailed rundown.",
    "",
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
  ].join("\n"));

  assert.deepEqual(blocks.map((block) => block.kind), [
    "paragraph", "blank", "heading", "blank", "paragraph", "list",
    "blank", "paragraph", "list"
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
    "## Before",
    "",
    "| Name | State |",
    "| --- | --- |",
    "| arm | **idle** |",
    "",
    "**After**"
  ].join("\n"));

  assert.deepEqual(blocks.map((block) => block.kind), [
    "heading", "blank", "literal", "blank", "paragraph"
  ]);
  const literal = blocks[2];
  assert.equal(literal.kind, "literal");
  if (literal.kind !== "literal") throw new Error("expected literal table");
  assert.deepEqual(literal.lines, [
    "| Name | State |", "| --- | --- |", "| arm | **idle** |"
  ]);
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
    "10. **root**",
    "   - child",
    "      7. `grandchild`",
    "10. repeated"
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
  assert.deepEqual(
    unclosed[0]?.kind === "literal" ? unclosed[0].lines : null,
    ["```ts", "const x = 1;", "## Still code"]
  );
});

test("malformed heading inline falls back only for that heading line", () => {
  const blocks = parseFinalizedBlocks("## Broken **bold\nplain **safe**");
  assert.deepEqual(blocks.map((block) => block.kind), ["literal", "paragraph"]);
  assert.deepEqual(blocks[0]?.kind === "literal" ? blocks[0].lines : null, ["## Broken **bold"]);
  assert.deepEqual(
    blocks[1]?.kind === "paragraph"
      ? blocks[1].lines[0]?.map((segment) => segment.text).join("")
      : null,
    "plain safe"
  );
});

test("paragraph grouping preserves every source line break", () => {
  const blocks = parseFinalizedBlocks("first **line**\nsecond `line`\nthird");
  assert.equal(blocks[0]?.kind, "paragraph");
  if (blocks[0]?.kind !== "paragraph") throw new Error("expected paragraph");
  assert.equal(blocks[0].lines.length, 3);
  assert.deepEqual(
    blocks[0].lines.map((line) => line.map((segment) => segment.text).join("")),
    ["first line", "second line", "third"]
  );
});
```

- [ ] **Step 4: Run the new parser test to observe RED**

Run from `tui/`:

```powershell
node --import tsx --test src/components/finalizedMarkdown.test.ts
```

Expected: FAIL before test execution with `ERR_MODULE_NOT_FOUND` for `./finalizedMarkdown.js`.

- [ ] **Step 5: Implement the pure parser model**

Create `tui/src/components/finalizedMarkdown.ts`. Use these exact exported contracts and scanner constants:

```ts
import { normalizeTerminalText } from "./textFormat.js";

export type InlineSegment = {
  kind: "text" | "bold" | "code";
  text: string;
};

export type ListItem = {
  depth: 0 | 1 | 2;
  marker: string;
  ordered: boolean;
  segments: InlineSegment[];
};

export type FinalizedBlock =
  | { kind: "blank" }
  | { kind: "heading"; level: number; segments: InlineSegment[] }
  | { kind: "paragraph"; lines: InlineSegment[][] }
  | { kind: "list"; items: ListItem[] }
  | { kind: "code"; language?: string; lines: string[] }
  | { kind: "literal"; lines: string[] };

const LIST_CANDIDATE = /^[ \t]*(?:[-*]|\d+\.)[ \t]+.*$/;
const STRICT_LIST_ITEM = /^( *)([-*]|\d+\.) +(.+)$/;
const HEADING_CANDIDATE = /^#{1,6}(?:\s|$)/;
const HEADING = /^(#{1,6})\s+(.+)$/;
const FENCE_OPENER = /^```([A-Za-z0-9][A-Za-z0-9_+-]{0,31})? *$/;
const FENCE_CLOSER = /^``` *$/;

const INLINE_UNSUPPORTED = [
  /``|~~~/,
  /\*\*\*|__|~~/,
  /\\[!-/:-@[-`{-~]/,
  /<[^>\n]+>/
];
const BLOCK_UNSUPPORTED = [
  /^ {0,3}\[[^\]\n]+\]:/m,
  /^(?: {4}|\t)/m,
  /^\s*>/m,
  /^\s*\|.*\|\s*$/m,
  /^[ \t]*\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)+\|?[ \t]*$/m,
  /^\s*(?:-{3,}|={3,})\s*$/m,
  /^\s*(?:\+|\d+\))\s+/m,
  /^[ \t]+(?:#{1,6}|[-*]|\d+\.)\s+/m
];
const UNSUPPORTED_UNDERSCORE = /(^|[^A-Za-z0-9])_(?=\S)|\S_(?=$|[^A-Za-z0-9])/m;

export function parseFinalizedBlocks(value: string): FinalizedBlock[] {
  const lines = normalizeTerminalText(value).split("\n");
  const blocks: FinalizedBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index] ?? "";
    if (line === "") {
      blocks.push({ kind: "blank" });
      index += 1;
      continue;
    }

    if (line.startsWith("```")) {
      const parsed = parseFence(lines, index);
      blocks.push(parsed.block);
      index = parsed.next;
      continue;
    }

    if (HEADING_CANDIDATE.test(line)) {
      blocks.push(parseHeading(line));
      index += 1;
      continue;
    }

    if (LIST_CANDIDATE.test(line)) {
      let end = index + 1;
      while (end < lines.length && LIST_CANDIDATE.test(lines[end] ?? "")) end += 1;
      blocks.push(parseListRun(lines.slice(index, end)));
      index = end;
      continue;
    }

    let end = index + 1;
    while (end < lines.length && !startsNewBlock(lines[end] ?? "")) end += 1;
    blocks.push(parseParagraph(lines.slice(index, end)));
    index = end;
  }

  return blocks;
}

function startsNewBlock(line: string): boolean {
  return line === "" || line.startsWith("```") || HEADING_CANDIDATE.test(line) || LIST_CANDIDATE.test(line);
}

function parseFence(lines: string[], start: number): { block: FinalizedBlock; next: number } {
  let close = -1;
  for (let index = start + 1; index < lines.length; index += 1) {
    if (FENCE_CLOSER.test(lines[index] ?? "")) {
      close = index;
      break;
    }
  }
  const next = close >= 0 ? close + 1 : lines.length;
  const source = lines.slice(start, next);
  const opener = FENCE_OPENER.exec(lines[start] ?? "");
  const language = opener?.[1];
  const nested = close >= 0 && lines.slice(start + 1, close).some((line) => line.startsWith("```"));
  if (
    close < 0 ||
    !opener ||
    language?.toLowerCase() === "action-draft" ||
    nested
  ) {
    return { block: { kind: "literal", lines: source }, next };
  }
  return {
    block: {
      kind: "code",
      ...(language ? { language } : {}),
      lines: lines.slice(start + 1, close)
    },
    next
  };
}

function parseHeading(line: string): FinalizedBlock {
  const match = HEADING.exec(line);
  if (!match || /\s+#{1,6}\s*$/.test(match[2] ?? "")) {
    return { kind: "literal", lines: [line] };
  }
  const segments = parseSupportedInline(match[2] ?? "");
  return segments
    ? { kind: "heading", level: (match[1] ?? "").length, segments }
    : { kind: "literal", lines: [line] };
}

function parseListRun(lines: string[]): FinalizedBlock {
  const columns: number[] = [];
  const items: ListItem[] = [];

  for (const line of lines) {
    if (line.includes("\t")) return { kind: "literal", lines };
    const match = STRICT_LIST_ITEM.exec(line);
    if (!match) return { kind: "literal", lines };
    const indent = (match[1] ?? "").length;
    const marker = match[2] ?? "";
    const body = match[3] ?? "";
    if (hasNestedBlockMarkup(body)) return { kind: "literal", lines };

    if (columns.length === 0) {
      columns.push(indent);
    } else {
      const current = columns.at(-1) ?? 0;
      if (indent > current) {
        if (columns.length === 3) return { kind: "literal", lines };
        columns.push(indent);
      } else if (indent < current) {
        const target = columns.lastIndexOf(indent);
        if (target < 0) return { kind: "literal", lines };
        columns.splice(target + 1);
      }
    }

    const segments = parseSupportedInline(body);
    if (!segments) return { kind: "literal", lines };
    items.push({
      depth: (columns.length - 1) as 0 | 1 | 2,
      marker,
      ordered: /^\d+\.$/.test(marker),
      segments
    });
  }

  return { kind: "list", items };
}

function parseParagraph(lines: string[]): FinalizedBlock {
  const source = lines.join("\n");
  if (BLOCK_UNSUPPORTED.some((pattern) => pattern.test(source))) {
    return { kind: "literal", lines };
  }
  const parsed = lines.map(parseSupportedInline);
  if (parsed.some((line) => line === null)) return { kind: "literal", lines };
  return { kind: "paragraph", lines: parsed as InlineSegment[][] };
}

function hasNestedBlockMarkup(value: string): boolean {
  return /^(?:#{1,6}\s|>|[-*+]\s|\d+[.)]\s|\[[ xX]\]\s)/.test(value);
}

function parseSupportedInline(value: string): InlineSegment[] | null {
  if (
    containsUnsupportedLinkMarkup(value) ||
    INLINE_UNSUPPORTED.some((pattern) => pattern.test(value)) ||
    UNSUPPORTED_UNDERSCORE.test(value)
  ) {
    return null;
  }
  return parseInline(value);
}

function containsUnsupportedLinkMarkup(value: string): boolean {
  let depth = 0;
  for (let cursor = 0; cursor < value.length; cursor += 1) {
    if (value[cursor] === "[") depth += 1;
    else if (value[cursor] === "]" && depth > 0) {
      depth -= 1;
      if (value[cursor + 1] === "(" || value[cursor + 1] === "[") return true;
    }
  }
  return false;
}

function parseInline(value: string): InlineSegment[] | null {
  const segments: InlineSegment[] = [];
  let cursor = 0;
  let plainStart = 0;

  while (cursor < value.length) {
    if (value.startsWith("**", cursor)) {
      pushPlain(segments, value, plainStart, cursor);
      const close = value.indexOf("**", cursor + 2);
      if (close < 0) return null;
      const content = value.slice(cursor + 2, close);
      if (!content || /^\s|\s$/.test(content) || /[*`]/.test(content)) return null;
      segments.push({ kind: "bold", text: content });
      cursor = close + 2;
      plainStart = cursor;
      continue;
    }
    if (value[cursor] === "`") {
      pushPlain(segments, value, plainStart, cursor);
      const close = value.indexOf("`", cursor + 1);
      if (close < 0) return null;
      const content = value.slice(cursor + 1, close);
      if (!content || content.includes("**")) return null;
      segments.push({ kind: "code", text: content });
      cursor = close + 1;
      plainStart = cursor;
      continue;
    }
    if (value[cursor] === "*") return null;
    cursor += 1;
  }
  pushPlain(segments, value, plainStart, value.length);
  return segments;
}

function pushPlain(segments: InlineSegment[], value: string, start: number, end: number): void {
  if (end > start) segments.push({ kind: "text", text: value.slice(start, end) });
}
```

During implementation, keep regex literals exactly aligned with the approved design. Do not loosen them to accept tabs, HTML, links, alternate fence markers, or deeper lists.

- [ ] **Step 6: Run parser GREEN and the full TUI suite**

Run from `tui/`:

```powershell
node --import tsx --test src/components/finalizedMarkdown.test.ts
npm.cmd run typecheck
npm.cmd test
```

Expected: the new parser file passes, typecheck exits 0, and all existing TUI tests still pass because `FinalizedText.tsx` has not yet switched consumers.

- [ ] **Step 7: Commit Task 1 without the temporary brief**

```powershell
git add -- tui/src/components/finalizedMarkdown.ts tui/src/components/finalizedMarkdown.test.ts
git diff --cached --check
git commit -m "feat(tui): parse finalized markdown by block"
```

Expected: only the parser and its test are committed; protected untracked files and `docs/brief-t4-2-block-markdown-renderer.zh-CN.md` remain unstaged.

---

### Task 2: Logical Ink block renderer

**Files:**
- Modify: `tui/src/components/FinalizedText.tsx:1-185`
- Modify: `tui/src/components/render.test.tsx:12,197-317`
- Consume: `tui/src/components/finalizedMarkdown.ts`

**Interfaces:**
- Consumes: `FinalizedBlock[]`, `InlineSegment[]`, and `parseFinalizedBlocks()` from Task 1.
- Produces: unchanged public React API `FinalizedText({ value }: { value: string }): React.JSX.Element`.
- Temporary Task 2 layout: logical indentation/prefix Text is acceptable; Task 3 replaces list/code lines with `HangingRow` before closure.

- [ ] **Step 1: Replace whole-message formatter tests with renderer RED cases**

Update the import in `tui/src/components/render.test.tsx`:

```ts
import { FinalizedText } from "./FinalizedText.js";
```

Remove direct `parseFinalizedText()` assertions; pure parser assertions now belong to `finalizedMarkdown.test.ts`. Replace the old whole-message/nested/fence cases with these logical renderer tests:

```tsx
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
  assert.match(frame, /• arm_1 is currently idle\./);
  assert.match(frame, /1\. red_block/);
  assert.match(frame, /◦ Type: block/);
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

test("FinalizedText renders generic code and preserves reserved action-draft fences", () => {
  const generic = render(<FinalizedText value={"```ts\nconst x = 1;\n```"} />);
  const genericFrame = generic.lastFrame() ?? "";
  assert.match(genericFrame, /│ ts/);
  assert.match(genericFrame, /│ const x = 1;/);
  assert.doesNotMatch(genericFrame, /```/);
  generic.unmount();

  const reservedValue = "```action-draft\n{\"actions\":[]}\n```";
  const reserved = render(<FinalizedText value={reservedValue} />);
  assert.match(reserved.lastFrame() ?? "", /```action-draft/);
  assert.match(reserved.lastFrame() ?? "", /\{"actions":\[\]\}/);
  reserved.unmount();
});

test("FinalizedText preserves source paragraph and trailing blank lines", () => {
  const value = "first **line**\nsecond `line`\n\nlast\n";
  const view = render(<FinalizedText value={value} />);
  const frame = view.lastFrame() ?? "";
  assert.match(frame, /first line\nsecond line\n\nlast\n?$/);
  view.unmount();
});
```

Keep explicit negative cases for malformed inline, HTML, links, tables, blockquotes, task lists, bad list dedent, unclosed/nested fence, and `action-draft`; update their expectations from `parseFinalizedText(value) === null` to exact literal frame content. Expand `Transcript formats only finalized assistant entries` with `system` and an arbitrary unknown role, both containing Markdown markers that must remain literal; retain the existing `ChatPanel leaves incomplete streaming Markdown untouched` assertion.

- [ ] **Step 2: Run the renderer tests to observe RED**

Run from `tui/`:

```powershell
node --import tsx --test src/components/render.test.tsx
```

Expected: FAIL because the old `FinalizedText` still applies whole-message fallback, treats nested lists/fences literally, and does not render block types.

- [ ] **Step 3: Replace `FinalizedText.tsx` with a block renderer**

Replace scanner logic in `tui/src/components/FinalizedText.tsx` with this component structure. Task 2 intentionally uses logical Text prefixes; Task 3 supplies the final display-safe row primitive.

```tsx
import React from "react";
import { Box, Text } from "ink";
import { THEME } from "../theme.js";
import {
  parseFinalizedBlocks,
  type FinalizedBlock,
  type InlineSegment
} from "./finalizedMarkdown.js";

const BULLETS = ["•", "◦", "▪"] as const;

export function FinalizedText({ value }: { value: string }): React.JSX.Element {
  const blocks = parseFinalizedBlocks(value);
  return (
    <Box flexDirection="column" width="100%">
      {blocks.map((block, index) => (
        <Block key={`${index}:${block.kind}`} block={block} />
      ))}
    </Box>
  );
}

function Block({ block }: { block: FinalizedBlock }): React.JSX.Element {
  switch (block.kind) {
    case "blank":
      return <Box height={1}><Text>{" "}</Text></Box>;
    case "heading":
      return <InlineText segments={block.segments} bold color={THEME.brandAccent} />;
    case "paragraph":
      return (
        <Box flexDirection="column">
          {block.lines.map((line, index) => <InlineText key={index} segments={line} />)}
        </Box>
      );
    case "list":
      return (
        <Box flexDirection="column">
          {block.items.map((item, index) => (
            <Text key={index}>
              {"  ".repeat(item.depth)}
              <Text color={THEME.muted}>{item.ordered ? item.marker : BULLETS[item.depth]} </Text>
              <InlineFragments segments={item.segments} />
            </Text>
          ))}
        </Box>
      );
    case "code":
      return (
        <Box flexDirection="column">
          {block.language ? <Text><Text color={THEME.muted}>│ {block.language}</Text></Text> : null}
          {block.lines.map((line, index) => (
            <Text key={index}><Text color={THEME.muted}>│ </Text>{line || " "}</Text>
          ))}
        </Box>
      );
    case "literal":
      return (
        <Box flexDirection="column">
          {block.lines.map((line, index) => <Text key={index}>{line || " "}</Text>)}
        </Box>
      );
  }
}

function InlineText({
  segments,
  bold = false,
  color
}: {
  segments: InlineSegment[];
  bold?: boolean;
  color?: string;
}): React.JSX.Element {
  return (
    <Text bold={bold} color={color}>
      <InlineFragments segments={segments} />
    </Text>
  );
}

function InlineFragments({ segments }: { segments: InlineSegment[] }): React.JSX.Element {
  return (
    <>
      {segments.map((segment, index) => (
        <Text
          key={`${index}:${segment.kind}:${segment.text}`}
          bold={segment.kind === "bold"}
          color={segment.kind === "code" ? "cyan" : undefined}
        >
          {segment.text}
        </Text>
      ))}
    </>
  );
}
```

Do not move role filtering: `Transcript.tsx` must remain the only caller that selects `FinalizedText` for `entry.role === "assistant"`.

- [ ] **Step 4: Run logical renderer GREEN, typecheck, and full TUI**

```powershell
node --import tsx --test src/components/finalizedMarkdown.test.ts src/components/render.test.tsx
npm.cmd run typecheck
npm.cmd test
```

Expected: parser/render tests and the full suite pass; physical nested-list hanging behavior is not claimed until Task 3.

- [ ] **Step 5: Commit Task 2 without the temporary brief**

```powershell
git add -- tui/src/components/FinalizedText.tsx tui/src/components/render.test.tsx
git diff --cached --check
git commit -m "feat(tui): render finalized markdown blocks"
```

---

### Task 3: Display-safe hanging rows and App chat integration

**Files:**
- Create: `tui/src/components/HangingRow.tsx`
- Modify: `tui/src/components/FinalizedText.tsx`
- Modify: `tui/src/components/render.test.tsx`
- Modify: `tui/tests/scenario-runner.test.tsx:206-234,840-895,1467-1482`
- Modify: `tui/tests/scenarios/chat.scenario`

**Interfaces:**
- Produces: `HangingRow({ indent, prefix, prefixColor, children })` using Ink-measured prefix width and a shrinkable body.
- Consumes: Task 2 `FinalizedText` block renderer; replaces only list/code row layout.
- Preserves: `MessageRow` remains responsible for the outer `⏺` role marker and total body width.

- [ ] **Step 1: Add physical-width RED tests**

In `tui/tests/scenario-runner.test.tsx`, add a finalized Markdown physical test after the existing finalized/streaming width test:

```tsx
test("nested Markdown list and code rows stay display-safe at finite widths", () => {
  const content = [
    "## Current Workspace",
    "1. **red_block**",
    "   - Description: 👋 中 é 👨‍👩‍👧‍👦 remains visible near the collaborative workspace boundary",
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
      assert.equal(normalizeOutput(output).includes("## Current Workspace"), false);
      assert.equal(normalizeOutput(output).includes("**red_block**"), false);
      if (columns < 100) {
        assertInnerHangingBody(output, "◦", "Description:", "boundary");
        assertInnerHangingBody(output, "▪", "Detail:", "alignment-check");
        assertInnerHangingBody(output, "│", "const description", "rail");
      }
    } finally {
      view.unmount();
    }
  }
});
```

Add this helper next to `assertHangingBody()`:

```ts
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
```

- [ ] **Step 2: Run the physical test to observe RED**

```powershell
node --import tsx --test --test-name-pattern "nested Markdown list and code rows" tests/scenario-runner.test.tsx
```

Expected: FAIL because Task 2 combines indentation/prefix/body in one Text node, so wrapped lines do not retain the inner list/code content column.

- [ ] **Step 3: Add the final hanging-row primitive**

Create `tui/src/components/HangingRow.tsx`:

```tsx
import React from "react";
import { Box, Text } from "ink";

export function HangingRow({
  indent = 0,
  prefix,
  prefixColor,
  children
}: {
  indent?: number;
  prefix: string;
  prefixColor?: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <Box flexDirection="row" width="100%" paddingLeft={indent * 2}>
      <Box flexShrink={0} marginRight={1}>
        <StablePrefix prefix={prefix} color={prefixColor} />
      </Box>
      <Box flexDirection="column" flexGrow={1} flexShrink={1} flexBasis={0}>
        {children}
      </Box>
    </Box>
  );
}

function StablePrefix({ prefix, color }: { prefix: string; color?: string }): React.JSX.Element {
  if (prefix !== "▪") return <Text color={color}>{prefix}</Text>;

  // Ink 5.2 measures this glyph as two cells while the Windows output tokenizer
  // paints one. Prime the measured two-cell slot, then overlay the visible glyph.
  return (
    <Box width={2}>
      <Text color={color}>{"\u3000"}</Text>
      <Box position="absolute">
        <Text color={color}>{prefix}</Text>
      </Box>
    </Box>
  );
}
```

This intentionally relies on Ink/Yoga's display-cell measurement for ordinary prefixes. The fixed third-level `▪` glyph receives the same two-cell priming pattern already proven for the outer `⏺` marker because Ink 5.2 measures it as two cells while the Windows output tokenizer paints one. The physical tests prove both paths against `string-width`; do not calculate prefix width using JS `.length`.

Modify list/code branches in `FinalizedText.tsx`:

```tsx
import { HangingRow } from "./HangingRow.js";

// list branch
case "list":
  return (
    <Box flexDirection="column">
      {block.items.map((item, index) => (
        <HangingRow
          key={index}
          indent={item.depth}
          prefix={item.ordered ? item.marker : BULLETS[item.depth]}
          prefixColor={THEME.muted}
        >
          <InlineText segments={item.segments} />
        </HangingRow>
      ))}
    </Box>
  );

// code branch
case "code":
  return (
    <Box flexDirection="column">
      {block.language ? (
        <HangingRow prefix="│" prefixColor={THEME.muted}>
          <Text color={THEME.muted}>{block.language}</Text>
        </HangingRow>
      ) : null}
      {block.lines.map((line, index) => (
        <HangingRow key={index} prefix="│" prefixColor={THEME.muted}>
          <Text>{line || " "}</Text>
        </HangingRow>
      ))}
    </Box>
  );
```

- [ ] **Step 4: Run physical GREEN before changing the scenario fixture**

```powershell
node --import tsx --test --test-name-pattern "display-width|nested Markdown|FinalizedText|Transcript" src/components/render.test.tsx tests/scenario-runner.test.tsx
npm.cmd run typecheck
```

Expected: focused physical/render tests pass at 24/48/100 columns and typecheck exits 0.

- [ ] **Step 5: Upgrade the real chat scenario to a nested finalized reply**

In `tui/tests/scenario-runner.test.tsx`, define one fixture string near `stateFixtures` and use it as `chatAfterReply.messages[2].content`:

```ts
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
```

Update `tui/tests/scenarios/chat.scenario` so the stream done `reply`, expected persisted state, and output use the same literal JSON string:

```json
{
  "type": "done",
  "payload": {
    "reply": "## Current Workspace\n\n**Robot state**\n- `arm_1` is currently **idle**.\n\n**Visible objects**\n1. **red_block**\n   - Type: block\n   - Color: red",
    "state": { "ready": true, "chat_messages": 3 }
  }
}
```

Set the chat step checks to:

```json
"expectOutput": [
  "> hello robot",
  "⏺ Current Workspace",
  "Robot state",
  "• arm_1 is currently idle.",
  "1. red_block",
  "◦ Type: block"
],
"rejectOutput": [
  "## Current Workspace",
  "**Robot state**",
  "`arm_1`",
  "**red_block**"
],
"expectState": {
  "chat.messages.2.content": "## Current Workspace\n\n**Robot state**\n- `arm_1` is currently **idle**.\n\n**Visible objects**\n1. **red_block**\n   - Type: block\n   - Color: red"
}
```

- [ ] **Step 6: Run scenario, full TUI, and build GREEN**

```powershell
node --import tsx --test --test-name-pattern "chat|display-width|nested Markdown|FinalizedText|Transcript" src/components/render.test.tsx tests/scenario-runner.test.tsx
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
```

Expected: focused tests, every scenario, full TUI, typecheck, and build pass. Record exact counts in the SDD progress ledger; do not pre-write them into living docs.

- [ ] **Step 7: Run the TUI execution-boundary scan**

From repository root:

```powershell
rg -n "driver\.execute|physical_agent\.watch|physical_agent\.drivers|sqlite3" tui/src
```

Expected: no matches and `rg` exit code 1. Treat any match as a blocker, not an allowlist update.

- [ ] **Step 8: Commit Task 3 without the temporary brief**

```powershell
git add -- tui/src/components/HangingRow.tsx tui/src/components/FinalizedText.tsx tui/src/components/render.test.tsx tui/tests/scenario-runner.test.tsx tui/tests/scenarios/chat.scenario
git diff --cached --check
git commit -m "fix(tui): preserve markdown block hanging indents"
```

---

### Task 4: Independent review, complete gates, and T4.2 closure

**Files:**
- Modify: implementation/test files only for reviewer-proven fixes.
- Modify: `docs/SPEC.zh-CN.md`
- Modify: `docs/PLAYBOOK.zh-CN.md`
- Modify: `docs/REFACTORING.zh-CN.md`
- Modify: `docs/superpowers/specs/2026-07-20-tui-block-markdown-renderer-design.md`
- Delete: `docs/brief-t4-2-block-markdown-renderer.zh-CN.md`
- Update ignored ledger: `.superpowers/sdd/progress.md`

**Interfaces:**
- Consumes: Task 1 parser commit, Task 2 logical renderer commit, Task 3 physical/App commit, and exact command output.
- Produces: reviewed T4.2 implementation, closed living-doc ledger, real local/remote evidence, and an updated draft PR without readiness/merge changes.

- [ ] **Step 1: Request two-stage independent implementation review**

Use `superpowers:requesting-code-review` with the approved design and all Task 1–3 commits. Require reviewers to verify:

```text
Spec: block-local fallback; exact list/fence grammar; paragraph line preservation;
      finalized-assistant-only formatting; action-draft literal; no new dependency.
Quality: parser totality/no content loss; stable block keys; Ink nested Text/Box validity;
         24/48/100 physical display width; no Static duplication; scenario truth.
Safety: no backend/watch/driver/sqlite import; no proposal/action/Gate interpretation;
        API/approval/SafetyGate/freeze untouched.
```

For every valid finding, first add a focused failing regression and observe RED, then implement the minimum fix and rerun focused + full TUI gates. Commit each coherent repair as `fix(tui): ...`. Repeat review until Critical=0 and Important=0; record Minor findings and disposition rather than silently ignoring them.

- [ ] **Step 2: Run the fresh complete local gate**

From `tui/`:

```powershell
npm.cmd run typecheck
node --import tsx --test src/components/finalizedMarkdown.test.ts src/components/render.test.tsx
node --import tsx --test tests/scenario-runner.test.tsx
npm.cmd test
npm.cmd run build
```

From repository root:

```powershell
$env:TEMP=(Resolve-Path '.superpowers\sdd\pytest-tmp').Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_safety_boundaries.py tests/test_safety.py
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
git diff --check
```

Expected: every TUI gate passes, Python safety and full suites pass with only already-known warnings, and diff check is clean. Capture exact counts and warning text from this fresh run.

- [ ] **Step 3: Perform a real Windows Terminal smoke check**

Use the existing mock-only `physical-agent.yaml`; before enabling watch, verify the configured driver is `mock_arm` and the SQLite board has no pending/in-progress action. Start API+watch, Vite, and TUI using the documented commands, then send the long-answer prompt used for the original screenshot. This is a non-blocking visual smoke check because the configured LLM response is nondeterministic; the checked-in scenario fixture and 24/48/100 physical-width tests remain the authoritative acceptance evidence.

If the live reply contains the relevant constructs, verify visually:

```text
- no visible ##, **, or inline-code backticks in supported blocks;
- Current Workspace and section headings retain MOCE hierarchy;
- ordered object items and nested bullets align;
- long nested bullet/code continuation stays under its body start;
- unsupported table or action-draft sample remains readable literal;
- no repeated Logo or terminal activity item.
```

Stop only the mock development processes started for this smoke check after evidence is captured; never stop unrelated user processes by broad process name.

- [ ] **Step 4: Record local closure evidence without claiming remote completion**

After Steps 1–2 are green and Step 3 has been performed, keep SPEC §4 T4.2 at 🟡 and state `实现/review/本地门禁完成，待 exact-head CI`; do not claim remote completion yet. Record actual implementation/review-fix commit hashes and exact local counts. In PLAYBOOK, append implementation and local-validation paragraphs without rewriting historical T4/T4.1 evidence. In REFACTORING:

```text
- add one T4.2 row to §1 with parser/renderer/width/review commits;
- add `### T4.2：finalized assistant 块级 Markdown` to §2;
- record whole-message→block-local rationale, exact list/fence grammar,
  physical width evidence, review outcome, and unchanged safety/freeze boundary.
```

Change the design status to `已实现并通过本地验收`. Delete the temporary brief with `apply_patch`; do not create a separate handoff document.

- [ ] **Step 5: Verify and commit local documentation closure**

```powershell
$env:TEMP=(Resolve-Path '.superpowers\sdd\pytest-tmp').Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_current_docs.py tests/test_safety_boundaries.py
git diff --check
git status --short --branch
```

Expected: docs/safety tests pass; only the intended tracked living docs are changed; the temporary brief is absent; the five protected user files remain untracked and unstaged.

```powershell
if (Test-Path 'docs/brief-t4-2-block-markdown-renderer.zh-CN.md') {
  throw 'temporary T4.2 brief must be deleted before closure commit'
}
```

```powershell
git add -- docs/SPEC.zh-CN.md docs/PLAYBOOK.zh-CN.md docs/REFACTORING.zh-CN.md docs/superpowers/specs/2026-07-20-tui-block-markdown-renderer-design.md
git diff --cached --check
git commit -m "docs: record T4.2 local closure evidence"
```

The temporary brief is intentionally never committed, so its deletion creates no Git delta. Never use `git add -A`.

- [ ] **Step 6: Push implementation/docs head and observe exact-head CI**

```powershell
git push fork codex/agent-core-refactor
```

Observe both Push and draft-PR workflows. Verify their `head_sha` exactly equals the pushed implementation/docs HEAD, attempt is known, and every applicable job has a terminal conclusion. Do not copy prior T4/T4.1 run IDs.

If either workflow fails, inspect the failing job logs, reproduce locally, add RED, fix, rerun gates, commit, push, and observe the new exact head. Do not record a failed or superseded head as closure evidence.

- [ ] **Step 7: Record only the successful observed remote facts**

After both exact-head workflows are completed/success, update SPEC T4.2 from 🟡 to ✅ and update PLAYBOOK T4.2 and REFACTORING T4.2 with the real full head SHA, run IDs, attempt numbers, and applicable/skipped job conclusions. The completion claim must point to this exact successful implementation/docs head, never to an older run.

```powershell
git add -- docs/SPEC.zh-CN.md docs/PLAYBOOK.zh-CN.md docs/REFACTORING.zh-CN.md
git diff --cached --check
git commit -m "docs: record T4.2 exact-head CI evidence"
git push fork codex/agent-core-refactor
```

Observe the final evidence-only head's Push/PR workflows for delivery confidence, but do not create an infinite self-referential evidence commit. Record those final-head run IDs in PR metadata and the local SDD ledger only.

- [ ] **Step 8: Synchronize draft PR metadata without changing state**

Update PR #1 title/body to include T4.2 behavior, local TUI/Python counts, implementation/docs exact-head evidence, and final evidence-head runs. Preserve these exact statements:

```text
PR state: OPEN
draft: true
merged: false
No merge, readiness transition, backend feature unfreeze, or SafetyGate/approval change.
```

Do not pass a PR state/base/ready/merge mutation when updating title/body.

- [ ] **Step 9: Final verification and branch handoff**

```powershell
git rev-list --left-right --count fork/codex/agent-core-refactor...HEAD
git status --short --branch
git log -5 --oneline
```

Expected: ahead/behind `0 0`; no tracked modification; only the five protected pre-existing untracked user files remain. PR #1 is OPEN + draft and points to final HEAD. Mark `.superpowers/sdd/progress.md` T4.2 complete with local counts, review outcome, closure hashes, and both generations of run IDs.

Use `superpowers:finishing-a-development-branch` and select the existing-PR/keep-worktree outcome. Do not merge or clean up the user's workspace.
