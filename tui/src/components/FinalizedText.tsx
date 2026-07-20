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
          {block.language ? <Text><Text color={THEME.muted}>─ {block.language}</Text></Text> : null}
          {block.lines.map((line, index) => (
            <Text key={index}><Text color={THEME.muted}>─ </Text>{line || " "}</Text>
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
