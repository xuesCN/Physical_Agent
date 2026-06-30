import {
  ApiOutlined,
  CloudSyncOutlined,
  DatabaseOutlined,
  ReloadOutlined,
  SafetyOutlined
} from "@ant-design/icons";
import { Badge, Button, Space, Tag, Typography } from "antd";
import type { AgentState, HealthState } from "../types";

interface StatusBarProps {
  health: HealthState | null;
  state: AgentState | null;
  sseConnected: boolean;
  watchEnabled: boolean | null;
  loading: boolean;
  onRefresh: () => void;
}

export function StatusBar({
  health,
  state,
  sseConnected,
  watchEnabled,
  loading,
  onRefresh
}: StatusBarProps) {
  const backend = state?.backend || health?.backend || "-";
  const ready = Boolean(state?.ready ?? health?.ready);

  return (
    <div className="status-bar">
      <div className="status-title">
        <Typography.Title level={1}>Physical Agent</Typography.Title>
        <Tag icon={<SafetyOutlined />} color="blue">
          Proposal only
        </Tag>
      </div>
      <Space size={8} wrap>
        <Tag icon={<DatabaseOutlined />} color="default">
          backend {backend}
        </Tag>
        <Tag icon={<ApiOutlined />} color={ready ? "green" : "gold"}>
          workspace {ready ? "ready" : "not ready"}
        </Tag>
        <Tag icon={<CloudSyncOutlined />} color={watchEnabled ? "cyan" : "default"}>
          watch {watchEnabled ? "enabled" : "off"}
        </Tag>
        <Badge
          status={sseConnected ? "processing" : "default"}
          text={sseConnected ? "SSE connected" : "SSE disconnected"}
        />
        <Button
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={onRefresh}
          size="small"
        >
          Refresh
        </Button>
      </Space>
    </div>
  );
}
