import { CodeOutlined } from "@ant-design/icons";
import { Card, Collapse, Space, Typography } from "antd";
import type { AgentState } from "../types";
import { compactJson } from "./utils";

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
      <Collapse
        ghost
        items={[
          {
            key: "state",
            label: "JSON state",
            children: <pre className="pre-block">{compactJson(state, "{}")}</pre>
          }
        ]}
      />
    </Card>
  );
}
