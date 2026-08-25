import React from "react";
import { Text } from "ink";
import type { ActionTranscriptEntry } from "../types.js";
import { THEME } from "../theme.js";
import { formatActionInvocation } from "../formatters/action.js";
import { MessageRow } from "./MessageRow.js";

export function ActionActivityItem({ entry }: { entry: ActionTranscriptEntry }): React.JSX.Element {
  return (
    <MessageRow marker="⏺" color={THEME.brandAccent}>
      <Text>{formatActionInvocation(entry.action)}</Text>
      <Text color={THEME.muted}>⎿ {entry.outcome}</Text>
    </MessageRow>
  );
}
