import { SafetyCertificateOutlined, ToolOutlined } from "@ant-design/icons";
import { Card, Empty, Space, Tag, Typography } from "antd";
import type { AgentState, RobotInfo } from "../types";
import { RawJsonFallback } from "./JsonTreeLazy";
import {
  asRecord,
  compactSchemaSummary,
  formatObjectValue,
  isNonEmptyRecord
} from "./readableFormatters";

interface CapabilitiesGridProps {
  capabilities: AgentState["capabilities"] | undefined;
}

export function CapabilitiesGrid({ capabilities }: CapabilitiesGridProps) {
  const robots = capabilities?.robots ?? {};
  const entries = Object.entries(robots);
  if (!entries.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No capabilities" />;
  }
  return (
    <div className="capability-grid">
      {entries.map(([robotId, robot]) => (
        <RobotCapabilityGroup key={robotId} robotId={robotId} robot={robot} />
      ))}
      {unknownCapabilities(capabilities).length > 0 && (
        <RawJsonFallback
          label="Capabilities raw fields"
          value={Object.fromEntries(unknownCapabilities(capabilities))}
        />
      )}
    </div>
  );
}

function RobotCapabilityGroup({ robotId, robot }: { robotId: string; robot: RobotInfo }) {
  return (
    <Space direction="vertical" size={8} className="full-width">
      <Space size={6} wrap>
        <Typography.Text code>{robotId}</Typography.Text>
        <Tag>{robot.kind ?? "robot"}</Tag>
        <Tag>{robot.driver ?? "driver unknown"}</Tag>
        <Tag color={robot.status === "connected" ? "green" : "default"}>
          {robot.status ?? "unknown"}
        </Tag>
      </Space>
      <div className="capability-card-list">
        {(robot.capabilities ?? []).map((capability) => (
          <Card
            key={`${robotId}-${capability.name ?? "capability"}`}
            size="small"
            className="capability-card"
          >
            <Space direction="vertical" size={6} className="full-width">
              <Space size={6} wrap>
                <ToolOutlined />
                <Typography.Text strong>{capability.name ?? "Unnamed capability"}</Typography.Text>
                {capability.requires_approval ? (
                  <Tag color="gold" icon={<SafetyCertificateOutlined />}>
                    approval required
                  </Tag>
                ) : (
                  <Tag>no approval</Tag>
                )}
              </Space>
              <Typography.Text type="secondary">
                {capability.description || "No description"}
              </Typography.Text>
              <Typography.Text className="schema-summary">
                Params: {compactSchemaSummary(capability.params_schema)}
              </Typography.Text>
              {isNonEmptyRecord(asRecord(capability).constraints) && (
                <Typography.Text className="schema-summary">
                  Constraints: {formatObjectValue(asRecord(capability).constraints)}
                </Typography.Text>
              )}
              <RawJsonFallback label="Capability schema" value={capability} />
            </Space>
          </Card>
        ))}
      </div>
    </Space>
  );
}

function unknownCapabilities(capabilities: AgentState["capabilities"] | undefined) {
  return Object.entries(capabilities ?? {}).filter(([key]) => key !== "robots");
}
