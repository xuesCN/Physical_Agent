import { CodeOutlined } from "@ant-design/icons";
import { Card, Space, Typography } from "antd";
import { useMessages } from "../locales/context";
import type { AgentState } from "../types";
import { RawJsonFallback } from "./JsonTreeLazy";

interface RawDebugProps {
  state: AgentState | null;
}

export function RawDebug({ state }: RawDebugProps) {
  const labels = useMessages();
  return (
    <Card
      className="panel"
      data-testid="raw-debug-panel"
      title={
        <Space>
          <CodeOutlined />
          <Typography.Text strong>{labels.panels.rawDebug}</Typography.Text>
        </Space>
      }
    >
      <RawJsonFallback label="Full state JSON" value={state ?? {}} />
    </Card>
  );
}
