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
