import { CodeOutlined } from "@ant-design/icons";
import { Card, Empty, Space, Typography } from "antd";
import { useMessages } from "../locales/context";
import type { AgentState } from "../types";
import { formatRawDebugFields } from "../viewmodels/overview";
import { RawJsonFallback } from "./JsonTreeLazy";

interface RawDebugProps {
  state?: AgentState | null;
  raw?: Record<string, unknown>;
}

export function RawDebug({ state, raw }: RawDebugProps) {
  const labels = useMessages();
  const debugValue = raw ?? formatRawDebugFields(state);
  const hasRawFields = Object.keys(debugValue).length > 0;
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
      {hasRawFields ? (
        <RawJsonFallback
          label="Unknown/raw fields"
          value={debugValue}
          testId="raw-debug-fallback"
        />
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No raw debug fields" />
      )}
    </Card>
  );
}
