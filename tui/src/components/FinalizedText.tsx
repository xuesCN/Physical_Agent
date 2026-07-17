import React from "react";
import { Text } from "ink";
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

const unsupportedMarkdownPatterns = [
  /``|~~~/,
  /\*\*\*|__|~~/,
  /\\[!-/:-@[-`{-~]/,
  /<[^>\n]+>/,
  /!\[[^\]\n]*\]\([^)]*\)/,
  /\[[^\]\n]*\]\([^)]*\)/,
  /\[[^\]\n]*\]\[[^\]\n]*\]/,
  /^ {0,3}\[[^\]\n]+\]:/m,
  /^(?: {4}|\t)/m,
  /^\s*>/m,
  /^\s*\|.*\|\s*$/m,
  /^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)+\|?[ \t]*$/m,
  /^\s*(?:-{3,}|={3,})\s*$/m,
  /^\s*(?:\+|\d+\))\s+/m,
  /^[ \t]+(?:#{1,6}|[-*]|\d+\.)\s+/m
];
const unsupportedUnderscoreEmphasis = /(^|[^A-Za-z0-9])_(?=\S)|\S_(?=$|[^A-Za-z0-9])/m;

export function parseFinalizedText(value: string): FormattedLine[] | null {
  const normalized = normalizeTerminalText(value);
  if (
    unsupportedMarkdownPatterns.some((pattern) => pattern.test(normalized)) ||
    unsupportedUnderscoreEmphasis.test(normalized)
  ) {
    return null;
  }

  const lines: FormattedLine[] = [];
  for (const line of normalized.split("\n")) {
    const formatted = parseLine(line);
    if (!formatted) {
      return null;
    }
    lines.push(formatted);
  }
  return lines;
}

export function FinalizedText({ value }: { value: string }): React.JSX.Element {
  const normalized = normalizeTerminalText(value);
  const lines = parseFinalizedText(normalized);
  if (!lines) {
    return <Text>{normalized}</Text>;
  }

  return (
    <Text>
      {lines.map((line, lineIndex) => (
        <React.Fragment
          key={`${lineIndex}:${line.prefix}:${line.segments.map((segment) => segment.text).join("")}`}
        >
          {lineIndex > 0 ? "\n" : null}
          <Text
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
        </React.Fragment>
      ))}
    </Text>
  );
}

function parseLine(line: string): FormattedLine | null {
  const heading = /^(#{1,6})\s+(.+)$/.exec(line);
  if (heading) {
    if (/\s+#{1,6}\s*$/.test(heading[2])) {
      return null;
    }
    return lineWithSegments("heading", "", heading[2]);
  }
  if (/^#{1,6}(?:\s|$)/.test(line)) {
    return null;
  }

  const unordered = /^[-*]\s+(.+)$/.exec(line);
  if (unordered) {
    if (hasNestedBlockMarkup(unordered[1])) {
      return null;
    }
    return lineWithSegments("unordered", "• ", unordered[1]);
  }
  if (/^[-*]\s*$/.test(line)) {
    return null;
  }

  const ordered = /^(\d+)\.\s+(.+)$/.exec(line);
  if (ordered) {
    if (hasNestedBlockMarkup(ordered[2])) {
      return null;
    }
    return lineWithSegments("ordered", `${ordered[1]}. `, ordered[2]);
  }
  if (/^\d+\.\s*$/.test(line)) {
    return null;
  }

  return lineWithSegments("plain", "", line);
}

function hasNestedBlockMarkup(value: string): boolean {
  return /^(?:#{1,6}\s|>|[-*+]\s|\d+[.)]\s|\[[ xX]\]\s)/.test(value);
}

function lineWithSegments(kind: LineKind, prefix: string, value: string): FormattedLine | null {
  const segments = parseInline(value);
  return segments ? { kind, prefix, segments } : null;
}

function parseInline(value: string): FormattedSegment[] | null {
  const segments: FormattedSegment[] = [];
  let cursor = 0;
  let plainStart = 0;

  while (cursor < value.length) {
    if (value.startsWith("**", cursor)) {
      pushPlainSegment(segments, value, plainStart, cursor);
      const close = value.indexOf("**", cursor + 2);
      if (close < 0) {
        return null;
      }
      const content = value.slice(cursor + 2, close);
      if (!content || /^\s|\s$/.test(content) || /[*`]/.test(content)) {
        return null;
      }
      segments.push({ kind: "bold", text: content });
      cursor = close + 2;
      plainStart = cursor;
      continue;
    }

    if (value[cursor] === "`") {
      pushPlainSegment(segments, value, plainStart, cursor);
      const close = value.indexOf("`", cursor + 1);
      if (close < 0) {
        return null;
      }
      const content = value.slice(cursor + 1, close);
      if (!content || content.includes("**")) {
        return null;
      }
      segments.push({ kind: "code", text: content });
      cursor = close + 1;
      plainStart = cursor;
      continue;
    }

    if (value[cursor] === "*") {
      return null;
    }
    cursor += 1;
  }

  pushPlainSegment(segments, value, plainStart, value.length);
  return segments;
}

function pushPlainSegment(
  segments: FormattedSegment[],
  value: string,
  start: number,
  end: number
): void {
  if (end > start) {
    segments.push({ kind: "text", text: value.slice(start, end) });
  }
}
