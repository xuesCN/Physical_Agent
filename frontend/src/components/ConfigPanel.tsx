import { FileTextOutlined, ReloadOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Descriptions, Empty, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import { fetchConfig } from "../api";
import type { ConfigResponse } from "../types";
import { RawJsonFallback } from "./JsonTreeLazy";
import { formatObjectValue } from "./readableFormatters";

interface ConfigPanelProps {
  refreshToken?: number;
}

interface ConfigRobotRow {
  key: string;
  id: string;
  driver: string;
  config: Record<string, unknown>;
}

export function ConfigPanel({ refreshToken = 0 }: ConfigPanelProps) {
  const [response, setResponse] = useState<ConfigResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const next = await fetchConfig();
      setResponse(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshToken]);

  const config = response?.config;
  const watch = config?.watch ?? {};
  const robots: ConfigRobotRow[] = Object.entries(config?.robots ?? {}).map(([id, robot]) => ({
    key: id,
    id,
    driver: robot.driver,
    config: robot.config ?? {}
  }));

  const columns: ColumnsType<ConfigRobotRow> = [
    {
      title: "Robot",
      dataIndex: "id",
      width: 140,
      render: (value: string) => <Typography.Text code>{value}</Typography.Text>
    },
    { title: "Driver", dataIndex: "driver", width: 200 },
    {
      title: "Config",
      dataIndex: "config",
      ellipsis: true,
      render: (value: Record<string, unknown>) => (
        <Space direction="vertical" size={4} className="full-width">
          <Typography.Text type="secondary" className="schema-summary">
            {formatObjectValue(value, "No config")}
          </Typography.Text>
          <RawJsonFallback label="Robot config" value={value} />
        </Space>
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
          <Typography.Text strong>Project Config (read-only)</Typography.Text>
        </Space>
      }
      extra={
        <Button
          size="small"
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={() => void load()}
          data-testid="config-refresh-button"
        >
          Refresh
        </Button>
      }
    >
      {error ? (
        <Alert type="warning" showIcon message="Config unavailable" description={error} />
      ) : (
        <Space direction="vertical" size={8} className="full-width">
          <Descriptions size="small" column={1} className="tight-descriptions">
            <Descriptions.Item label="Config file">
              <Typography.Text code>{response?.config_path ?? "-"}</Typography.Text>
            </Descriptions.Item>
            <Descriptions.Item label="Workspace">
              {config?.workspace?.path ?? "-"}{" "}
              <Tag color="blue">{config?.workspace?.backend ?? "-"}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Watch">
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
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No robots configured" />
          )}
          <Typography.Text type="secondary">
            This is the effective configuration watch loads at startup. To change existing
            entries, edit physical-agent.yaml and restart watch.
          </Typography.Text>
        </Space>
      )}
    </Card>
  );
}
