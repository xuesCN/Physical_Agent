import React, { useMemo } from "react";
import { Box, Static, Text } from "ink";
import type { TranscriptEntry } from "../types.js";
import { BrandBanner } from "./BrandBanner.js";
import { FinalizedText } from "./FinalizedText.js";
import { MessageRow, rolePresentation } from "./MessageRow.js";
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
    <Static items={items} style={{ width: "100%" }}>
      {(item) => {
        if (item.kind === "brand") {
          return <BrandBanner key={item.id} columns={item.columns} />;
        }

        const presentation = rolePresentation(item.entry.role);
        return (
          <Box key={item.id} width="100%" paddingX={1}>
            <MessageRow marker={presentation.marker} color={presentation.color}>
              {item.entry.role === "assistant" ? (
                <FinalizedText value={item.entry.content} />
              ) : (
                <Text>{normalizeTerminalText(item.entry.content)}</Text>
              )}
            </MessageRow>
          </Box>
        );
      }}
    </Static>
  );
}
