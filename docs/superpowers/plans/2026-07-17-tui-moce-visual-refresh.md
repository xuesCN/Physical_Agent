# MOCE TUI Visual Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved MOCE-branded Ink TUI with a one-time dark-blue startup banner, a persistent compact header, readable terminal hierarchy, faithful lightweight finalized Markdown, and unchanged control semantics.

**Architecture:** Keep `App` and the existing HTTP/SSE data flow intact. `Transcript` remains the sole, continuously mounted Ink `Static` owner and emits the banner as its first stable feed item; focused presentation components consume centralized theme tokens. Width selection and Markdown parsing are pure functions, while scenario tests exercise the complete App at 100, 48, and unknown columns.

**Tech Stack:** TypeScript 5.7, React 18, Ink 5, ink-testing-library 3, Node 20 test runner; no new runtime dependency.

## Global Constraints

- `driver.execute` remains reachable only from the watch execution call stack; TUI stays an API/SSE-only client.
- No changes to FastAPI, protocol schemas, SQLite, watch, driver, SafetyGate, Action Board, approvals, commands, or state semantics.
- Logo color is exactly `#1D4ED8`; small brand text uses exactly `#3B82F6`.
- Full banner is selected only for a finite width of at least 58 columns; 48, zero, non-finite, and unknown width use the compact fallback.
- Exactly one continuously mounted `Static` feed owns both the banner and finalized transcript entries.
- Supported finalized assistant syntax is heading, ordered/unordered list, `**bold**`, and inline code; fenced code, malformed/nested markers, unsupported syntax, and legacy `action-draft` fences remain literal text.
- Streaming partial text is never passed through the finalized formatter.
- Preserve `Physical Agent TUI` as secondary status copy so the established scenario startup contract remains backward compatible while `MOCE` becomes the primary wordmark.
- Every production behavior follows RED → verify expected failure → minimal GREEN → full affected test run.
- Do not stage or modify `docs/architecture.excalidraw`, `docs/brief-hardware-connectivity-review.zh-CN.md`, `docs/brief-vnext-review-sync-recovery.zh-CN.md`, or `scripts/ws_connection_smoke.py`.
- Do not modify the protected tracked snapshots `docs/current-architecture-audit.md`, `docs/current-architecture-audit.html`, or `docs/system-summary.zh-CN.md`.

---

### Task 1: Theme tokens and responsive MOCE banner

**Files:**
- Create: `tui/src/theme.ts`
- Create: `tui/src/components/BrandBanner.tsx`
- Modify: `tui/src/components/render.test.tsx`

**Interfaces:**
- Produces: `THEME.brandLogo`, `THEME.brandAccent`, and semantic token strings.
- Produces: `selectBannerVariant(columns?: number): "full" | "compact"`.
- Produces: `BrandBanner({ columns?: number }): React.JSX.Element` and exported `FULL_MOCE_LOGO`.

- [ ] **Step 1: Write the failing banner and token tests**

Add these imports and tests to `render.test.tsx`:

```tsx
import { BrandBanner, FULL_MOCE_LOGO, selectBannerVariant } from "./BrandBanner.js";
import { THEME } from "../theme.js";

test("MOCE theme keeps the approved logo and small-text colors", () => {
  assert.equal(THEME.brandLogo, "#1D4ED8");
  assert.equal(THEME.brandAccent, "#3B82F6");
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
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
Push-Location tui
node --import tsx --test src/components/render.test.tsx
Pop-Location
```

Expected: FAIL because `BrandBanner.js` and `theme.js` do not exist.

- [ ] **Step 3: Add the minimal theme module**

Create `tui/src/theme.ts`:

```ts
export const THEME = {
  brandLogo: "#1D4ED8",
  brandAccent: "#3B82F6",
  muted: "gray",
  success: "green",
  warning: "yellow",
  danger: "red",
  safety: "magenta"
} as const;
```

- [ ] **Step 4: Add the pure responsive banner**

Create `tui/src/components/BrandBanner.tsx`:

```tsx
import React from "react";
import { Box, Text } from "ink";
import { THEME } from "../theme.js";

export const FULL_BANNER_MIN_COLUMNS = 58;

export const FULL_MOCE_LOGO = [
  "███╗   ███╗  ██████╗   ██████╗ ███████╗",
  "████╗ ████║ ██╔═══██╗ ██╔════╝ ██╔════╝",
  "██╔████╔██║ ██║   ██║ ██║      █████╗",
  "██║╚██╔╝██║ ██║   ██║ ██║      ██╔══╝",
  "██║ ╚═╝ ██║ ╚██████╔╝ ╚██████╗ ███████╗",
  "╚═╝     ╚═╝  ╚═════╝   ╚═════╝ ╚══════╝"
] as const;

export function selectBannerVariant(columns?: number): "full" | "compact" {
  return Number.isFinite(columns) && (columns ?? 0) >= FULL_BANNER_MIN_COLUMNS
    ? "full"
    : "compact";
}

export function BrandBanner({ columns }: { columns?: number }) {
  const variant = selectBannerVariant(columns);
  return (
    <Box flexDirection="column" paddingX={1} marginBottom={1}>
      {variant === "full"
        ? FULL_MOCE_LOGO.map((line) => (
            <Text key={line} color={THEME.brandLogo} bold>{line}</Text>
          ))
        : <Text color={THEME.brandAccent} bold>MOCE · PHYSICAL AGENT</Text>}
      {variant === "full" ? (
        <Text color={THEME.brandAccent} bold>PHYSICAL AGENT · SAFE CONTROL PLANE</Text>
      ) : null}
      <Text color={THEME.muted}>type /help to explore</Text>
    </Box>
  );
}
```

- [ ] **Step 5: Verify GREEN and commit**

Run the focused command from Step 2. Expected: all `render.test.tsx` tests pass.

```powershell
git add -- tui/src/theme.ts tui/src/components/BrandBanner.tsx tui/src/components/render.test.tsx
git commit -m "feat(tui): add responsive MOCE banner"
```

---

### Task 2: One persistent Static feed and branded role rails

**Files:**
- Modify: `tui/src/components/Transcript.tsx`
- Modify: `tui/src/App.tsx:1-2,366-389`
- Modify: `tui/src/components/render.test.tsx`
- Modify: `tui/src/safety.test.ts`

**Interfaces:**
- Consumes: `BrandBanner({ columns })` and `THEME` from Task 1.
- Produces: `Transcript({ entries, columns?: number })` as the only `Static` owner.
- Keeps: the existing `TranscriptEntry` schema and all chat/SSE state transitions unchanged.

- [ ] **Step 1: Write failing feed, role, and Static ownership tests**

Add to `render.test.tsx`:

```tsx
import { Transcript } from "./Transcript.js";

test("Transcript prints the MOCE banner once while finalized entries append", () => {
  const view = render(<Transcript entries={[]} columns={100} />);
  view.rerender(
    <Transcript
      columns={100}
      entries={[
        { id: "u1", role: "user", content: "hello" },
        { id: "a1", role: "assistant", content: "ready" },
        { id: "d1", role: "draft", content: "review only" }
      ]}
    />
  );
  const output = view.frames.join("\n");
  assert.equal(output.split(FULL_MOCE_LOGO[0]).length - 1, 1);
  assert.match(output, /you\s+›\s+hello/);
  assert.match(output, /moce\s+│\s+ready/);
  assert.match(output, /draft\s+◇\s+review only/);
  view.unmount();
});
```

Extend the existing safety test after its source scan:

```ts
  const staticOwners: string[] = [];
  for (const file of files) {
    const content = await readFile(file, "utf8");
    if (content.includes("<Static")) {
      staticOwners.push(file);
    }
  }
  assert.equal(staticOwners.length, 1);
  assert.equal(staticOwners[0].endsWith(join("components", "Transcript.tsx")), true);
  const transcriptSource = await readFile(staticOwners[0], "utf8");
  assert.match(transcriptSource, /kind:\s*"brand"/);
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
Push-Location tui
node --import tsx --test src/components/render.test.tsx src/safety.test.ts
Pop-Location
```

Expected: FAIL because `Transcript` has no `columns` prop, emits no brand item, and still uses old role prefixes.

- [ ] **Step 3: Convert Transcript to the sole branded feed**

Replace `Transcript.tsx` with:

```tsx
import React, { useMemo } from "react";
import { Box, Static, Text } from "ink";
import type { TranscriptEntry } from "../types.js";
import { THEME } from "../theme.js";
import { BrandBanner } from "./BrandBanner.js";
import { normalizeTerminalText } from "./textFormat.js";

interface TranscriptProps {
  entries: TranscriptEntry[];
  columns?: number;
}

type FeedItem =
  | { id: "brand:moce"; kind: "brand"; columns?: number }
  | { id: string; kind: "entry"; entry: TranscriptEntry };

export function Transcript({ entries, columns }: TranscriptProps) {
  const items = useMemo<FeedItem[]>(
    () => [
      { id: "brand:moce", kind: "brand", columns },
      ...entries.map((entry) => ({ id: entry.id, kind: "entry" as const, entry }))
    ],
    [columns, entries]
  );

  return (
    <Static items={items}>
      {(item) => item.kind === "brand" ? (
        <BrandBanner key={item.id} columns={item.columns} />
      ) : (
        <Box key={item.id} paddingX={1} flexDirection="row">
          <Text color={roleColor(item.entry.role)}>{rolePrefix(item.entry.role)} </Text>
          <Box flexDirection="column" flexGrow={1}>
            <Text>{normalizeTerminalText(item.entry.content)}</Text>
          </Box>
        </Box>
      )}
    </Static>
  );
}

function rolePrefix(role: string): string {
  if (role === "user") return "you ›";
  if (role === "assistant") return "moce │";
  if (role === "draft") return "draft ◇";
  return `${role} │`;
}

function roleColor(role: string): string {
  if (role === "assistant") return THEME.brandAccent;
  if (role === "user") return THEME.success;
  if (role === "draft") return THEME.warning;
  return THEME.muted;
}
```

- [ ] **Step 4: Keep the feed mounted and pass real terminal width**

In `App.tsx`, import `useStdout`, derive a safe width, and render `Transcript` unconditionally:

```tsx
import { Box, Text, useApp, useStdout } from "ink";

const { stdout } = useStdout();
const stdoutColumns = stdout.columns;
const terminalColumns = Number.isFinite(stdoutColumns) && stdoutColumns > 0
  ? stdoutColumns
  : undefined;

return (
  <>
    <Transcript entries={transcriptEntries} columns={terminalColumns} />
    <Box flexDirection="column" gap={1}>
      <StatusBar status={status} busy={busy || streaming} />
      {renderActiveView({
        activeView,
        status,
        health,
        state,
        configResponse,
        configError,
        selectedRobotId,
        lastUpload,
        transcriptEntries,
        streamingText,
        streaming,
        error
      })}
      {notice ? <Box paddingX={1}><Text color="gray">{notice}</Text></Box> : null}
      <CommandInput value={input} onChange={setInput} onSubmit={handleSubmit} disabled={busy} />
    </Box>
  </>
);
```

- [ ] **Step 5: Verify GREEN and commit**

Run the focused command from Step 2, then:

```powershell
git add -- tui/src/App.tsx tui/src/components/Transcript.tsx tui/src/components/render.test.tsx tui/src/safety.test.ts
git commit -m "feat(tui): unify the branded transcript feed"
```

---

### Task 3: Faithful lightweight finalized Markdown

**Files:**
- Create: `tui/src/components/FinalizedText.tsx`
- Modify: `tui/src/components/Transcript.tsx`
- Modify: `tui/src/components/render.test.tsx`

**Interfaces:**
- Produces: `parseFinalizedText(value: string): FormattedLine[] | null`; `null` means literal fallback.
- Produces: `FinalizedText({ value }): React.JSX.Element`.
- Consumes: only finalized assistant entries; streaming stays in `ChatPanel` and uses `normalizeTerminalText`.

- [ ] **Step 1: Write failing supported and literal-fallback tests**

Add to `render.test.tsx`:

```tsx
import { FinalizedText, parseFinalizedText } from "./FinalizedText.js";

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

test("FinalizedText preserves unsupported or malformed Markdown literally", () => {
  const values = [
    "```ts\nconst x = 1;\n```",
    "unclosed **bold",
    "unclosed `code",
    "**bold with `nested` code**",
    "[link](https://example.com)",
    "```action-draft\n{\"actions\":[]}\n```"
  ];
  for (const value of values) {
    assert.equal(parseFinalizedText(value), null);
    const view = render(<FinalizedText value={value} />);
    assert.match(view.lastFrame() ?? "", new RegExp(value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\n/g, "\\s*")));
    view.unmount();
  }
});

test("ChatPanel leaves incomplete streaming Markdown untouched", () => {
  const view = render(<ChatPanel hasTranscript streamingText="**partial" streaming />);
  assert.match(view.lastFrame() ?? "", /\*\*partial/);
  view.unmount();
});
```

- [ ] **Step 2: Verify RED**

Run `node --import tsx --test src/components/render.test.tsx` from `tui`.

Expected: FAIL because `FinalizedText.js` does not exist.

- [ ] **Step 3: Implement the pure parser and renderer**

Create `FinalizedText.tsx`:

```tsx
import React from "react";
import { Box, Text } from "ink";
import { THEME } from "../theme.js";
import { normalizeTerminalText } from "./textFormat.js";

type SegmentKind = "text" | "bold" | "code";
type LineKind = "plain" | "heading" | "unordered" | "ordered";

interface FormattedSegment {
  kind: SegmentKind;
  text: string;
}

export interface FormattedLine {
  kind: LineKind;
  prefix: string;
  segments: FormattedSegment[];
}

const unsupportedMarkdown = /```|~~~|\*\*\*|__|~~|!\[[^\]]*\]\([^)]*\)|\[[^\]]+\]\([^)]*\)|(^|\n)\s*>\s|(^|\n)\s*\|.*\|\s*($|\n)|(^|\n)\s*-{3,}\s*($|\n)/m;
const nestedInline = /\*\*[^*\n]*`[^`\n]+`[^*\n]*\*\*|`[^`\n]*\*\*[^*\n]+\*\*[^`\n]*`/;

export function parseFinalizedText(value: string): FormattedLine[] | null {
  const normalized = normalizeTerminalText(value);
  if (
    unsupportedMarkdown.test(normalized) ||
    nestedInline.test(normalized) ||
    countToken(normalized, "**") % 2 !== 0 ||
    countToken(normalized, "`") % 2 !== 0
  ) {
    return null;
  }
  return normalized.split("\n").map(parseLine);
}

export function FinalizedText({ value }: { value: string }) {
  const normalized = normalizeTerminalText(value);
  const lines = parseFinalizedText(normalized);
  if (!lines) {
    return <Text>{normalized}</Text>;
  }
  return (
    <Box flexDirection="column">
      {lines.map((line, lineIndex) => (
        <Text
          key={`${lineIndex}:${line.prefix}:${line.segments.map((segment) => segment.text).join("")}`}
          bold={line.kind === "heading"}
          color={line.kind === "heading" ? THEME.brandAccent : undefined}
        >
          {line.prefix ? <Text color={THEME.muted}>{line.prefix}</Text> : null}
          {line.segments.map((segment, segmentIndex) => (
            <Text
              key={`${segmentIndex}:${segment.kind}:${segment.text}`}
              bold={segment.kind === "bold"}
              color={segment.kind === "code" ? "cyan" : undefined}
            >
              {segment.text}
            </Text>
          ))}
        </Text>
      ))}
    </Box>
  );
}

function parseLine(line: string): FormattedLine {
  const heading = /^(#{1,6})\s+(.+)$/.exec(line);
  if (heading) {
    return { kind: "heading", prefix: "", segments: parseInline(heading[2]) };
  }
  const unordered = /^\s*[-*]\s+(.+)$/.exec(line);
  if (unordered) {
    return { kind: "unordered", prefix: "• ", segments: parseInline(unordered[1]) };
  }
  const ordered = /^\s*(\d+)\.\s+(.+)$/.exec(line);
  if (ordered) {
    return { kind: "ordered", prefix: `${ordered[1]}. `, segments: parseInline(ordered[2]) };
  }
  return { kind: "plain", prefix: "", segments: parseInline(line) };
}

function parseInline(value: string): FormattedSegment[] {
  const segments: FormattedSegment[] = [];
  const pattern = /(\*\*[^*\n]+\*\*|`[^`\n]+`)/g;
  let cursor = 0;
  for (const match of value.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > cursor) {
      segments.push({ kind: "text", text: value.slice(cursor, index) });
    }
    const token = match[0];
    segments.push({
      kind: token.startsWith("**") ? "bold" : "code",
      text: token.startsWith("**") ? token.slice(2, -2) : token.slice(1, -1)
    });
    cursor = index + token.length;
  }
  if (cursor < value.length) {
    segments.push({ kind: "text", text: value.slice(cursor) });
  }
  return segments;
}

function countToken(value: string, token: string): number {
  return value.split(token).length - 1;
}
```

- [ ] **Step 4: Route only finalized assistant entries through the formatter**

In `Transcript.tsx`, import `FinalizedText` and replace the body child with:

```tsx
<Box flexDirection="column" flexGrow={1}>
  {item.entry.role === "assistant" ? (
    <FinalizedText value={item.entry.content} />
  ) : (
    <Text>{normalizeTerminalText(item.entry.content)}</Text>
  )}
</Box>
```

- [ ] **Step 5: Verify GREEN, preserve the legacy protocol boundary, and commit**

Run:

```powershell
Push-Location tui
node --import tsx --test src/components/render.test.tsx src/App.test.ts
Pop-Location
```

Expected: PASS, including the existing App test proving legacy `action-draft` remains ordinary reply text.

```powershell
git add -- tui/src/components/FinalizedText.tsx tui/src/components/Transcript.tsx tui/src/components/render.test.tsx
git commit -m "feat(tui): format finalized assistant text"
```

---

### Task 4: Compact status, section hierarchy, and outlined input

**Files:**
- Create: `tui/src/components/SectionTitle.tsx`
- Modify: `tui/src/components/StatusBar.tsx`
- Modify: `tui/src/components/CommandInput.tsx`
- Modify: `tui/src/components/ChatPanel.tsx`
- Modify: `tui/src/components/ActionsPanel.tsx`
- Modify: `tui/src/components/StatusPanel.tsx`
- Modify: `tui/src/components/ConfigPanel.tsx`
- Modify: `tui/src/components/RobotsPanel.tsx`
- Modify: `tui/src/components/RobotDetailPanel.tsx`
- Modify: `tui/src/components/UploadsPanel.tsx`
- Modify: `tui/src/components/render.test.tsx`

**Interfaces:**
- Produces: `SectionTitle({ title, detail? })` with a flexible divider and no fixed-width string.
- Keeps: existing status helper functions and all panel data/command behavior.
- Consumes: `THEME` from Task 1.

- [ ] **Step 1: Write failing hierarchy and input tests**

Add imports and tests to `render.test.tsx`:

```tsx
import { CommandInput } from "./CommandInput.js";
import { SectionTitle } from "./SectionTitle.js";

test("SectionTitle renders a branded title without a fixed divider string", () => {
  const view = render(<SectionTitle title="status" detail="live" />);
  assert.match(view.lastFrame() ?? "", /◆ status/);
  assert.match(view.lastFrame() ?? "", /live/);
  view.unmount();
});

test("CommandInput renders a round branded prompt and disabled copy", () => {
  const view = render(
    <CommandInput value="" onChange={() => undefined} onSubmit={() => undefined} />
  );
  assert.match(view.lastFrame() ?? "", /╭|╰/);
  assert.match(view.lastFrame() ?? "", /›/);
  assert.match(view.lastFrame() ?? "", /message or \/help/);
  view.rerender(
    <CommandInput value="" onChange={() => undefined} onSubmit={() => undefined} disabled />
  );
  assert.match(view.lastFrame() ?? "", /Working\.\.\./);
  view.unmount();
});
```

Update the first StatusBar test to additionally require `/MOCE/` while retaining `/Physical Agent TUI/`.

- [ ] **Step 2: Verify RED**

Run the focused render test. Expected: FAIL because `SectionTitle` is absent, the input has no round border, and StatusBar has no MOCE wordmark.

- [ ] **Step 3: Add SectionTitle and outlined input**

Create `SectionTitle.tsx`:

```tsx
import React from "react";
import { Box, Text } from "ink";
import { THEME } from "../theme.js";

export function SectionTitle({ title, detail }: { title: string; detail?: string }) {
  return (
    <Box alignItems="center" gap={1} width="100%">
      <Text bold color={THEME.brandAccent}>◆ {title}</Text>
      {detail ? <Text color={THEME.muted}>{detail}</Text> : null}
      <Box
        flexGrow={1}
        borderStyle="single"
        borderTop={false}
        borderLeft={false}
        borderRight={false}
        borderBottomColor={THEME.brandAccent}
      />
    </Box>
  );
}
```

Replace `CommandInput.tsx` with:

```tsx
import React from "react";
import { Box, Text } from "ink";
import TextInput from "ink-text-input";
import { THEME } from "../theme.js";

interface CommandInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  disabled?: boolean;
}

export function CommandInput({ value, onChange, onSubmit, disabled = false }: CommandInputProps) {
  return (
    <Box
      marginX={1}
      paddingX={1}
      borderStyle="round"
      borderColor={disabled ? THEME.muted : THEME.brandAccent}
    >
      <Text color={disabled ? THEME.muted : THEME.brandAccent}>› </Text>
      <TextInput
        value={value}
        onChange={onChange}
        onSubmit={onSubmit}
        placeholder={disabled ? "Working..." : "message or /help"}
      />
    </Box>
  );
}
```

- [ ] **Step 4: Make StatusBar MOCE-first while preserving all status labels**

Keep the existing helper functions and replace only the `return` block in `StatusBar.tsx`:

```tsx
return (
  <Box flexDirection="column" paddingX={1}>
    <Box gap={1} flexWrap="wrap">
      <Text bold color={THEME.brandAccent}>MOCE</Text>
      {busy ? <Text color={THEME.warning}><Spinner type="dots" /> busy</Text> : null}
      <Text color={status.connected ? THEME.success : THEME.warning}>● {connection}</Text>
      <Text color={status.mode === "degraded" ? THEME.warning : "blue"}>{modeText}</Text>
      <Text color={executorColor(status.executor)}>Executor: {executor}</Text>
      <Text color={llmStatusColor(status.llm.state)}>{llmStateLabel(status.llm.state, status.llm.message)}</Text>
    </Box>
    <Box gap={1} flexWrap="wrap">
      <Text color={THEME.muted}>Physical Agent TUI</Text>
      <Text color={THEME.muted}>{status.apiBase}</Text>
      <Text color={THEME.muted}>backend {status.backend}</Text>
      <Text color={THEME.muted}>LLM: {status.llm.model}</Text>
      <Text color={status.llm.hasApiKey ? THEME.success : THEME.warning}>{llmKeyLabel(status.llm.hasApiKey)}</Text>
      <Text color={THEME.muted}>last {status.lastRefresh ?? "never"}</Text>
      <Text color={status.message === "Ready." ? THEME.success : THEME.warning}>{status.message}</Text>
    </Box>
    <Box
      width="100%"
      borderStyle="single"
      borderTop={false}
      borderLeft={false}
      borderRight={false}
      borderBottomColor={THEME.brandAccent}
    />
  </Box>
);
```

Add `import { THEME } from "../theme.js";`.

- [ ] **Step 5: Apply SectionTitle consistently and keep streaming literal**

Add `SectionTitle` imports and use these exact main-title replacements:

```tsx
// ChatPanel.tsx
<SectionTitle title="chat" detail={streaming ? "streaming" : undefined} />
// streaming role line
<Text color={THEME.brandAccent}>moce │ </Text>

// ActionsPanel.tsx
<SectionTitle title="actions" />

// StatusPanel.tsx
<SectionTitle title="status" />

// ConfigPanel.tsx, in both loaded and not-loaded branches
<SectionTitle title="config" />

// RobotsPanel.tsx
<SectionTitle title="robots" />

// RobotDetailPanel.tsx
<SectionTitle title={`${mode === "capabilities" ? "capabilities" : "robot"} ${robot.id}`} />

// UploadsPanel.tsx
<SectionTitle title="uploads" />
```

Remove the replaced one-line cyan/gray title `<Text>` nodes. Do not alter row rendering, errors, action semantics, upload metadata, robot data, or the nested Config `robots` label.

- [ ] **Step 6: Verify GREEN and commit**

Run:

```powershell
Push-Location tui
node --import tsx --test src/components/render.test.tsx
npm run typecheck
Pop-Location
```

Expected: both commands pass.

```powershell
git add -- tui/src/components tui/src/theme.ts
git commit -m "feat(tui): add terminal visual hierarchy"
```

---

### Task 5: Full-App width, rerender, and scenario acceptance

**Files:**
- Modify: `tui/tests/scenario-runner.test.tsx`
- Modify: `tui/tests/scenarios/basic.scenario`
- Modify: `tui/tests/scenarios/chat.scenario`

**Interfaces:**
- Extends `ScenarioCase` with `columns?: number | null`, `initialRejectOutput`, `initialOutputCounts`, and `initialMaxLineWidth`.
- Extends `ScenarioStep` with `expectOutputCounts` and `maxLineWidth`.
- Interprets missing columns as 100 and explicit `null` as unknown stdout width.

- [ ] **Step 1: Add an acceptance test that fails with the fixed 100-column stdout**

Add this test near the other top-level scenario-runner tests before changing `renderTui`:

```tsx
test("complete App uses compact branding at 48 and unknown columns", async () => {
  for (const columns of [48, null] as const) {
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
      await waitForOutput(view, ["MOCE · PHYSICAL AGENT", "Physical Agent TUI", "message or /help"]);
      assert.equal(normalizeFrames(view).includes(FULL_MOCE_LOGO[0]), false);
    } finally {
      view.unmount();
    }
  }
});
```

Import `FULL_MOCE_LOGO` from `../src/components/BrandBanner.js`.

- [ ] **Step 2: Verify RED**

Run:

```powershell
Push-Location tui
node --import tsx --test tests/scenario-runner.test.tsx
Pop-Location
```

Expected: FAIL because `renderTui` ignores the requested width and still returns the full 100-column banner.

- [ ] **Step 3: Add width-aware stdout and reusable output assertions**

Apply these runner changes:

```tsx
interface ScenarioCase {
  name: string;
  useSse?: boolean;
  columns?: number | null;
  initialState?: string;
  initialConfig?: string;
  initialExpectOutput?: string[];
  initialRejectOutput?: string[];
  initialOutputCounts?: Record<string, number>;
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
  rejectOutput?: string[];
  expectOutputCounts?: Record<string, number>;
  maxLineWidth?: number;
  expectCalls?: Partial<Record<CallName, number>>;
  expectState?: Record<string, unknown>;
  expectConfig?: Record<string, unknown>;
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

function normalizeFrames(view: TestInkInstance): string {
  return normalizeOutput(view.frames.join("\n"));
}

function assertOutputCounts(view: TestInkInstance, counts: Record<string, number> = {}): void {
  const output = normalizeFrames(view);
  for (const [marker, count] of Object.entries(counts)) {
    assert.equal(output.split(marker).length - 1, count, `expected ${marker} exactly ${count} times`);
  }
}

function assertMaxLineWidth(view: TestInkInstance, maximum?: number): void {
  if (maximum === undefined) return;
  for (const frame of view.frames) {
    for (const line of normalizeOutput(frame).split("\n")) {
      assert.equal([...line].length <= maximum, true, `line exceeds ${maximum} columns: ${line}`);
    }
  }
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

class TestStdout extends EventEmitter {
  readonly frames: string[] = [];
  readonly isTTY = true;
  private frame: string | undefined;

  constructor(private readonly columnCount: number | null = 100) {
    super();
  }

  get columns(): number {
    return this.columnCount === null ? undefined as unknown as number : this.columnCount;
  }

  write = (value: string): boolean => {
    this.frames.push(value);
    this.frame = value;
    return true;
  };

  lastFrame(): string | undefined {
    return this.frame;
  }
}
```

After initial `waitForOutput`, assert `initialRejectOutput`, `initialOutputCounts`, and `initialMaxLineWidth`. In `assertStep`, call `assertOutputCounts(context.view, step.expectOutputCounts)` and `assertMaxLineWidth(context.view, step.maxLineWidth)` after the existing positive/negative text assertions.

- [ ] **Step 4: Encode wide, narrow, unknown, and view-switch acceptance**

In `basic.scenario`, keep the existing case and add these fields:

```json
"columns": 100,
"initialOutputCounts": { "███╗   ███╗": 1 }
```

Add `"expectOutputCounts": { "███╗   ███╗": 1 }` to its `/view status`, `/view chat`, and `/refresh` steps. Add two more cases to the same `cases` array:

```json
{
  "name": "compact layout at 48 columns",
  "columns": 48,
  "useSse": false,
  "initialState": "ready",
  "initialConfig": "default",
  "initialExpectOutput": ["MOCE · PHYSICAL AGENT", "Physical Agent TUI", "message or /help"],
  "initialRejectOutput": ["███╗   ███╗"],
  "initialOutputCounts": { "MOCE · PHYSICAL AGENT": 1 },
  "initialMaxLineWidth": 48,
  "steps": [
    {
      "input": "/view status",
      "expectOutput": ["status", "backend: sqlite"],
      "expectOutputCounts": { "MOCE · PHYSICAL AGENT": 1 },
      "maxLineWidth": 48
    },
    {
      "input": "/view chat",
      "expectOutput": ["View: chat", "message or /help"],
      "expectOutputCounts": { "MOCE · PHYSICAL AGENT": 1 },
      "maxLineWidth": 48
    }
  ]
},
{
  "name": "compact fallback when stdout width is unknown",
  "columns": null,
  "useSse": false,
  "initialState": "ready",
  "initialConfig": "default",
  "initialExpectOutput": ["MOCE · PHYSICAL AGENT", "Physical Agent TUI", "message or /help"],
  "initialRejectOutput": ["███╗   ███╗"],
  "initialOutputCounts": { "MOCE · PHYSICAL AGENT": 1 },
  "steps": []
}
```

In `chat.scenario`, replace the finalized role assertion with:

```json
"expectOutput": ["you › hello robot", "moce │ Hello from agent"]
```

- [ ] **Step 5: Verify the complete TUI contract and commit**

Run:

```powershell
Push-Location tui
node --import tsx --test tests/scenario-runner.test.tsx
npm run typecheck
npm test
npm run build
Pop-Location
```

Expected: scenario tests, all TUI tests, typecheck, and build pass; no new dependency appears in `package.json` or `package-lock.json`.

```powershell
git add -- tui/tests/scenario-runner.test.tsx tui/tests/scenarios/basic.scenario tui/tests/scenarios/chat.scenario
git commit -m "test(tui): cover MOCE width and rerender contracts"
```

---

### Task 6: Verification-backed current-document closure and brief removal

**Files:**
- Modify: `tests/test_current_docs.py`
- Modify: `docs/SPEC.zh-CN.md`
- Modify: `docs/PLAYBOOK.zh-CN.md`
- Modify: `docs/REFACTORING.zh-CN.md`
- Modify: `docs/superpowers/specs/2026-07-17-tui-moce-visual-refresh-design.md`
- Delete: `docs/brief-t4-tui-moce-visual-refresh.zh-CN.md`

**Interfaces:**
- Consumes: actual Task 1-5 commit hashes and observed test results.
- Produces: one consistent T4 completion statement across all current documentation surfaces.

- [ ] **Step 1: Complete local gates, independent review, and real-terminal acceptance before closing docs**

Read and follow `superpowers:verification-before-completion` and `superpowers:requesting-code-review`, then run:

```powershell
Push-Location tui
npm run typecheck
node --import tsx --test src/components/render.test.tsx
node --import tsx --test tests/scenario-runner.test.tsx
node --import tsx --test src/safety.test.ts
npm test
npm run build
Pop-Location

.\.venv\Scripts\python.exe -m pytest -q tests/test_safety_boundaries.py
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

Dispatch one spec-compliance reviewer and one code-quality reviewer. Require Critical/Important/Minor findings for single-Static ownership, width fallbacks, color readability, literal Markdown fallback, API-only safety, dependency discipline, and test quality. Resolve every Critical or Important finding through a new failing regression test.

Restart only the old TUI process chain after verifying its command line, then launch the new visible process with a child-owned title assignment:

```powershell
$childScript = '$Host.UI.RawUI.WindowTitle = ''MOCE TUI''; Set-Location ''C:\Users\17003\Desktop\Physical_agent\tui''; npm start -- --api http://127.0.0.1:8766'
Start-Process powershell.exe -ArgumentList @('-NoProfile', '-NoExit', '-Command', $childScript)
```

Manually verify full and compact banners, one-time output across `/view status`, `/view chat`, and `/refresh`, readable colors, outlined prompt, finalized Markdown, literal malformed/streaming text, and absence of the external `WindowTitle` error. Do not close docs until all automated and manual checks pass.

- [ ] **Step 2: Write the failing documentation consistency test**

Add to `tests/test_current_docs.py`:

```python
def test_t4_moce_tui_visual_refresh_closure_is_consistent() -> None:
    spec = (ROOT / "docs" / "SPEC.zh-CN.md").read_text(encoding="utf-8")
    playbook = (ROOT / "docs" / "PLAYBOOK.zh-CN.md").read_text(encoding="utf-8")
    refactoring = (ROOT / "docs" / "REFACTORING.zh-CN.md").read_text(encoding="utf-8")
    design = (
        ROOT
        / "docs"
        / "superpowers"
        / "specs"
        / "2026-07-17-tui-moce-visual-refresh-design.md"
    ).read_text(encoding="utf-8")

    t4_line = next(line for line in spec.splitlines() if line.startswith("| T4 |"))
    assert "MOCE TUI 品牌与终端视觉刷新" in t4_line
    assert "| ✅ 2026-07-17" in t4_line
    assert "**实现口径（2026-07-17 T4）**" in playbook
    assert "### T4：MOCE TUI 品牌与终端视觉刷新" in refactoring
    assert "状态：已完成并通过本地验收" in design
    assert not (ROOT / "docs" / "brief-t4-tui-moce-visual-refresh.zh-CN.md").exists()
```

- [ ] **Step 3: Verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_current_docs.py
```

Expected: FAIL because T4 is still yellow/in progress, closure sections are absent, and the round brief still exists.

- [ ] **Step 4: Gather only real implementation evidence**

Run:

```powershell
git log --oneline 17949c9..HEAD
Push-Location tui
npm run typecheck
npm test
npm run build
Pop-Location
```

Copy the returned Task 1-5 hashes and exact pass counts into the closure text. Do not record remote run IDs before push and exact-head completion.

- [ ] **Step 5: Close the four documentation surfaces**

Make these factual changes:

```text
SPEC §2: mark T4 completed and keep “other Phase F expansion frozen”.
SPEC §4 T4: change 🟡 to ✅ 2026-07-17 and record the actual local TUI commands/results and implementation commit hashes.
PLAYBOOK T4: append “实现口径（2026-07-17 T4）” and “验证” with single-Static, width, formatter, safety, and exact test evidence.
REFACTORING §1: add one T4 row with the actual implementation commits.
REFACTORING §2: append “### T4：MOCE TUI 品牌与终端视觉刷新” after R8.1, including boundaries and observed evidence.
Design status: replace the current status line with “状态：已完成并通过本地验收”.
```

Delete the round brief with `apply_patch`; do not touch the two protected user briefs.

- [ ] **Step 6: Verify GREEN and commit documentation closure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_current_docs.py
git diff --check
```

Expected: current-doc tests pass and diff check is clean.

```powershell
git add -- tests/test_current_docs.py docs/SPEC.zh-CN.md docs/PLAYBOOK.zh-CN.md docs/REFACTORING.zh-CN.md docs/superpowers/specs/2026-07-17-tui-moce-visual-refresh-design.md
git commit -m "docs: close the T4 MOCE TUI refresh"
```

---

### Task 7: Fresh final verification, visible restart, and push

**Files:**
- Verify only unless a failing test produces a new TDD cycle.

**Interfaces:**
- Produces: fresh post-documentation evidence, a visible refreshed TUI process, and the pushed branch.

- [ ] **Step 1: Invoke completion skills before making any success claim**

Read and follow `superpowers:verification-before-completion` and `superpowers:requesting-code-review`. Any review finding requires a focused failing regression test before a production fix.

- [ ] **Step 2: Run complete TUI and safety verification**

```powershell
Push-Location tui
npm run typecheck
node --import tsx --test src/components/render.test.tsx
node --import tsx --test tests/scenario-runner.test.tsx
node --import tsx --test src/safety.test.ts
npm test
npm run build
Pop-Location

.\.venv\Scripts\python.exe -m pytest -q tests/test_current_docs.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_safety_boundaries.py
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
git status --short
```

Expected: every command succeeds; status lists only the four pre-existing protected untracked files.

- [ ] **Step 3: Run independent code and spec reviews**

Dispatch one reviewer for spec compliance and one for code quality. Require Critical/Important/Minor classification and confirm:

```text
single continuously mounted Static feed
100/48/unknown width behavior
dark logo and readable small-text token separation
literal fallback and no action-draft protocol resurrection
unchanged API/SSE/control/safety boundary
no fixed-width divider or new runtime dependency
```

Resolve every Critical or Important issue through RED/GREEN and rerun Step 2.

- [ ] **Step 4: Restart the visible TUI with correctly quoted PowerShell**

Stop only the old TUI npm/node process chain after verifying each target command line. Leave backend `127.0.0.1:8766` and frontend `127.0.0.1:5173` running, then launch a visible PowerShell whose script sets the title through `$Host.UI.RawUI.WindowTitle` inside the child process:

```powershell
$childScript = '$Host.UI.RawUI.WindowTitle = ''MOCE TUI''; Set-Location ''C:\Users\17003\Desktop\Physical_agent\tui''; npm start -- --api http://127.0.0.1:8766'
Start-Process powershell.exe -ArgumentList @('-NoProfile', '-NoExit', '-Command', $childScript)
```

Manually confirm in Windows Terminal: full banner at normal width, compact fallback near 48 columns, one banner after `/view status`, `/view chat`, and `/refresh`, readable colors, outlined prompt, formatted finalized reply, literal streaming/malformed Markdown, and no external `WindowTitle` error.

- [ ] **Step 5: Commit any evidence-only correction, push, and inspect exact-head CI**

If Step 2-4 changed tracked documentation with real evidence, commit only those exact files. Then:

```powershell
git push fork codex/agent-core-refactor
git status --short
git rev-parse HEAD
```

Inspect the fork Push/PR checks for that exact head. Record remote run IDs only in a later evidence commit after they have completed successfully; keep PR #1 OPEN and draft unless the user explicitly changes that decision.
