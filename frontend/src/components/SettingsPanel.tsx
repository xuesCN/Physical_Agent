import { SettingOutlined } from "@ant-design/icons";
import { Card, Descriptions, Space, Tag, Typography } from "antd";
import type { AgentState, HealthState } from "../types";
import { compactJson, oneLine } from "./utils";

interface SettingsPanelProps {
  health: HealthState | null;
  state: AgentState | null;
}

export function SettingsPanel({ health, state }: SettingsPanelProps) {
  const ready = Boolean(state?.ready ?? health?.ready);

  return (
    <Card
      className="panel settings-panel"
      data-testid="settings-panel"
      title={
        <Space>
          <SettingOutlined />
          <Typography.Text strong>Settings</Typography.Text>
        </Space>
      }
    >
      <Descriptions size="small" column={1} className="tight-descriptions">
        <Descriptions.Item label="Backend">
          <Tag>{state?.backend ?? health?.backend ?? "-"}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Workspace">
          <Tag color={ready ? "green" : "gold"}>{ready ? "ready" : "not ready"}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Config">
          {state?.config_path ?? health?.config_path ?? "-"}
        </Descriptions.Item>
        <Descriptions.Item label="Workspace path">
          {state?.workspace_path ?? health?.workspace_path ?? "-"}
        </Descriptions.Item>
        <Descriptions.Item label="Message">
          {state?.message ?? health?.message ?? "-"}
        </Descriptions.Item>
        <Descriptions.Item label="Task">
          {oneLine(state?.task?.body ?? state?.task?.task ?? state?.task, "-")}
        </Descriptions.Item>
      </Descriptions>
      <div className="panel-divider" />
      <Typography.Text strong>Plan</Typography.Text>
      <pre className="pre-block settings-pre">{compactJson(state?.plan, "{}")}</pre>
    </Card>
  );
}
