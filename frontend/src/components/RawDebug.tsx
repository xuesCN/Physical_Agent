import { CodeOutlined } from "@ant-design/icons";
import { Card, Space, Typography } from "antd";
import type { AgentState } from "../types";
import { RawJsonFallback } from "./JsonTreeLazy";

interface RawDebugProps {
  state: AgentState | null;
}

export function RawDebug({ state }: RawDebugProps) {
  return (
    <Card
      className="panel"
      data-testid="raw-debug-panel"
      title={
        <Space>
          <CodeOutlined />
          <Typography.Text strong>Raw Debug</Typography.Text>
        </Space>
      }
    >
      <RawJsonFallback label="Full state JSON" value={state ?? {}} />
    </Card>
  );
}
