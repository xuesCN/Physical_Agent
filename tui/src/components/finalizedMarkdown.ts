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
const TABLE_DELIMITER = /^[ \t]*\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)+\|?[ \t]*$/;

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
  new RegExp(TABLE_DELIMITER.source, "m"),
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
      if (TABLE_DELIMITER.test(line)) {
        blocks.push({ kind: "literal", lines: [line] });
        index += 1;
        continue;
      }
      let end = index + 1;
      while (end < lines.length && LIST_CANDIDATE.test(lines[end] ?? "")) end += 1;
      blocks.push(parseListRun(lines.slice(index, end)));
      index = end;
      continue;
    }

    if (line.includes("|") && TABLE_DELIMITER.test(lines[index + 1] ?? "")) {
      let end = index + 2;
      while (end < lines.length && isTableContinuation(lines[end] ?? "")) end += 1;
      blocks.push({ kind: "literal", lines: lines.slice(index, end) });
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

function isTableContinuation(line: string): boolean {
  return line.includes("|") && !line.startsWith("```") && !HEADING_CANDIDATE.test(line);
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
  if (close < 0 || !opener || language?.toLowerCase() === "action-draft" || nested) {
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
