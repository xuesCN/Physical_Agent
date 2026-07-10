import { FileTextOutlined, ReloadOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Descriptions, Empty, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMessages } from "../locales/context";
import type { ConfigResponse } from "../types";
import { JsonSummaryLine } from "./JsonSummary";

interface ConfigPanelProps {
  response: ConfigResponse | null;
  error?: string | null;
  loading?: boolean;
  onRefresh: () => void;
}

interface ConfigRobotRow {
  key: string;
  id: string;
  driver: string;
  executionMode: string;
  config: Record<string, unknown>;
}

export function ConfigPanel({
  response,
  error = null,
  loading = false,
  onRefresh
}: ConfigPanelProps) {
  const labels = useMessages();

  const config = response?.config;
  const watch = config?.watch ?? {};
  const robots: ConfigRobotRow[] = Object.entries(config?.robots ?? {}).map(([id, robot]) => ({
    key: id,
    id,
    driver: robot.driver,
    executionMode: robot.execution_mode ?? "not specified",
    config: robot.config ?? {}
  }));

  const columns: ColumnsType<ConfigRobotRow> = [
    {
      title: labels.config.robot,
      dataIndex: "id",
      width: 140,
      render: (value: string) => <Typography.Text code>{value}</Typography.Text>
    },
    { title: labels.config.driver, dataIndex: "driver", width: 200 },
    {
      title: labels.config.executionMode,
      dataIndex: "executionMode",
      width: 140,
      render: (value: string) => <Tag color={value === "hardware" ? "gold" : "blue"}>{value}</Tag>
    },
    {
      title: labels.config.config,
      dataIndex: "config",
      ellipsis: true,
      render: (value: Record<string, unknown>) => (
        <JsonSummaryLine
          label={labels.config.config}
          value={value}
          fallback={labels.config.noConfig}
        />
      )
    }
  ];

  return (
    <Card
      className="panel"
      data-testid="config-panel"
      title={
        <Space>
          <FileTextOutlined />
          <Typography.Text strong>{labels.panels.config}</Typography.Text>
        </Space>
      }
      extra={
        <Button
          size="small"
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={onRefresh}
          data-testid="config-refresh-button"
        >
          {labels.config.refresh}
        </Button>
      }
    >
      {error ? (
        <Alert type="warning" showIcon message="Config unavailable" description={error} />
      ) : (
        <Space direction="vertical" size={8} className="full-width">
          <Descriptions size="small" column={1} className="tight-descriptions">
            <Descriptions.Item label={labels.config.configFile}>
              <Typography.Text code>{response?.config_path ?? "-"}</Typography.Text>
            </Descriptions.Item>
            <Descriptions.Item label={labels.config.workspace}>
              {config?.workspace?.path ?? "-"}{" "}
              <Tag color="blue">{config?.workspace?.backend ?? "-"}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label={labels.config.watch}>
              tick {String(watch.tick_ms ?? "-")}ms · approval{" "}
              {String(watch.require_human_approval ?? "-")} · heartbeat{" "}
              {String(watch.heartbeat_enabled ?? "-")} · halt-on-failure{" "}
              {String(watch.halt_on_heartbeat_failure ?? "-")}
            </Descriptions.Item>
          </Descriptions>
          {robots.length ? (
            <Table
              size="small"
              pagination={false}
              dataSource={robots}
              columns={columns}
              scroll={{ x: 560 }}
            />
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={labels.panels.noRobotsConfigured} />
          )}
          <Typography.Text type="secondary">
            This is the effective configuration the executor loads at startup. To change
            existing entries, edit physical-agent.yaml and restart the executor.
          </Typography.Text>
        </Space>
      )}
    </Card>
  );
}
