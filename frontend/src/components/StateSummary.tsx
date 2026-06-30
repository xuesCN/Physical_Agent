import { AlertOutlined, CompassOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { Card, Descriptions, Empty, Space, Tag, Typography } from "antd";
import type { AgentState, RobotInfo } from "../types";
import { compactJson, oneLine } from "./utils";

interface StateSummaryProps {
  state: AgentState | null;
}

export function StateSummary({ state }: StateSummaryProps) {
  const robots = state?.capabilities?.robots ?? {};
  const robotEntries = Object.entries(robots);
  const latest = (state?.feedback?.latest ?? {}) as Record<string, unknown>;

  return (
    <>
      <Card
        className="panel"
        title={
          <Space>
            <CompassOutlined />
            <Typography.Text strong>World</Typography.Text>
          </Space>
        }
      >
        <Typography.Paragraph className="summary-text">
          {oneLine(state?.world?.summary, "No world summary")}
        </Typography.Paragraph>
        {robotEntries.length ? (
          <Descriptions size="small" column={1} className="tight-descriptions">
            {robotEntries.map(([robotId, robot]) => (
              <Descriptions.Item key={robotId} label={robotId}>
                <RobotLine robot={robot} />
              </Descriptions.Item>
            ))}
          </Descriptions>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No robots" />
        )}
      </Card>

      <Card
        className="panel"
        title={
          <Space>
            <AlertOutlined />
            <Typography.Text strong>Feedback</Typography.Text>
          </Space>
        }
      >
        {Object.keys(latest).length ? (
          <Descriptions size="small" column={1} className="tight-descriptions">
            <Descriptions.Item label="Status">
              <Tag color={latest.status === "completed" ? "green" : "default"}>
                {String(latest.status ?? "-")}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Action">
              {String(latest.action_id ?? "-")}
            </Descriptions.Item>
            <Descriptions.Item label="Message">
              {String(latest.message ?? "-")}
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No feedback" />
        )}
      </Card>

      <Card
        className="panel"
        title={
          <Space>
            <SafetyCertificateOutlined />
            <Typography.Text strong>Safety</Typography.Text>
          </Space>
        }
      >
        <pre className="pre-block">{compactJson(state?.safety, "{}")}</pre>
      </Card>
    </>
  );
}

function RobotLine({ robot }: { robot: RobotInfo }) {
  const capabilities = robot.capabilities?.map((capability) => capability.name).filter(Boolean);
  return (
    <Space size={6} wrap>
      <Tag>{robot.kind ?? "robot"}</Tag>
      <Tag color={robot.status === "connected" ? "green" : "default"}>
        {robot.status ?? "unknown"}
      </Tag>
      <Typography.Text type="secondary">
        {robot.driver ?? "-"} / {capabilities?.join(", ") || "no capabilities"}
      </Typography.Text>
    </Space>
  );
}
