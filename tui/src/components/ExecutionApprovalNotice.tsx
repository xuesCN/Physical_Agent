import React from "react";
import { Box, Text } from "ink";
import { formatActionInvocation } from "../formatters/action.js";
import { THEME } from "../theme.js";
import type { ActionItem, AgentState } from "../types.js";

export function pendingExecutionApprovals(state: AgentState | null): ActionItem[] {
  return (state?.actions?.pending ?? []).filter((action) => {
    const approval = action.metadata?.approval;
    return Boolean(
      approval &&
      typeof approval === "object" &&
      (approval as Record<string, unknown>).required === true &&
      (approval as Record<string, unknown>).status === "pending"
    );
  });
}

export function ExecutionApprovalNotice({
  state
}: {
  state: AgentState | null;
}): React.JSX.Element | null {
  const approvals = pendingExecutionApprovals(state);
  const action = approvals[0];
  if (!action) return null;

  return (
    <Box width="100%" paddingX={1} flexDirection="column" borderStyle="round" borderColor={THEME.safety}>
      <Text bold color={THEME.safety}>
        Safety Gate · Execution approval <Text color={THEME.muted}>1/{approvals.length}</Text>
      </Text>
      <Text>{formatActionInvocation(action)} 等待人工批准</Text>
      <Text color={THEME.muted}>批准后仍需 watch SafetyGate 校验</Text>
      <Text color={THEME.brandAccent}>/approve {action.id}</Text>
      <Text color={THEME.muted}>/reject {action.id} &lt;reason&gt;</Text>
    </Box>
  );
}
