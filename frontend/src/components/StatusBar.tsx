import {
  ApiOutlined,
  CloudSyncOutlined,
  DatabaseOutlined,
  FormOutlined,
  ReloadOutlined,
  SafetyOutlined
} from "@ant-design/icons";
import { Badge, Breadcrumb, Button, Space, Tag, Typography } from "antd";
import type { Messages } from "../locales";
import type { AgentState, ExecutorProjection, HealthState } from "../types";

interface StatusBarProps {
  health: HealthState | null;
  state: AgentState | null;
  sseConnected: boolean;
  executor: ExecutorProjection | null;
  loading: boolean;
  activePageLabel: string;
  labels: Messages;
  onRefresh: () => void;
  onOpenInspector: () => void;
}

export function StatusBar({
  health,
  state,
  sseConnected,
  executor,
  loading,
  activePageLabel,
  labels,
  onRefresh,
  onOpenInspector
}: StatusBarProps) {
  const backend = state?.backend || health?.backend || "-";
  const ready = Boolean(state?.ready ?? health?.ready);
  const executorView = describeExecutor(executor, labels);

  return (
    <div className="status-bar" data-testid="status-bar">
      <div className="status-title">
        <div>
          <Typography.Title level={1}>{labels.app.name}</Typography.Title>
          <Breadcrumb
            items={[
              { title: labels.app.workbench },
              { title: activePageLabel }
            ]}
          />
        </div>
        <Tag icon={<SafetyOutlined />} color="blue" className="proposal-tag">
          {labels.app.proposalOnly}
        </Tag>
      </div>
      <Space size={8} wrap>
        <Tag icon={<DatabaseOutlined />} color="default">
          {labels.status.backend} {backend}
        </Tag>
        <Tag icon={<ApiOutlined />} color={ready ? "green" : "gold"}>
          {labels.status.workspace} {ready ? labels.status.ready : labels.status.notReady}
        </Tag>
        <Tag
          data-testid="executor-status"
          icon={<CloudSyncOutlined />}
          color={executorView.color}
          title={executorView.detail}
        >
          {labels.status.executor} {executorView.label}
        </Tag>
        <span data-testid="sse-status">
          <Badge
            status={sseConnected ? "processing" : "warning"}
            text={sseConnected ? labels.status.sseConnected : labels.status.sseDisconnected}
          />
        </span>
        <Button
          className="mobile-inspector-button"
          data-testid="open-proposal-drawer"
          icon={<FormOutlined />}
          size="small"
          onClick={onOpenInspector}
        >
          {labels.app.propose}
        </Button>
        <Button
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={onRefresh}
          size="small"
        >
          {labels.app.refresh}
        </Button>
      </Space>
    </div>
  );
}

function describeExecutor(
  executor: ExecutorProjection | null,
  labels: Messages
): { label: string; detail: string; color: string } {
  if (!executor) {
    return {
      label: labels.status.executorUnknown,
      detail: labels.status.executorUnknown,
      color: "default"
    };
  }

  const status = (executor.status ?? "").trim().toLowerCase();
  const failed = ["degraded", "error", "failed", "fatal"].includes(status);
  const active = ["active", "running", "ready"].includes(status);
  const base =
    executor.mode === "waiting_for_init"
      ? labels.status.executorWaiting
      : executor.mode === "embedded"
        ? labels.status.executorEmbedded
        : executor.mode === "external"
          ? labels.status.executorExternal
          : executor.legacy_watch_configured
            ? labels.status.executorUnknown
            : labels.status.executorNone;
  const showStatus =
    Boolean(status) &&
    executor.mode !== "waiting_for_init" &&
    !(executor.mode === "none" && ["stopped", "disabled", "inactive"].includes(status));
  const label = `${base}${showStatus ? ` · ${status}` : ""}`;

  const error = readExecutorError(executor.last_error);
  const lease = executor.lease;
  const leaseDetail = lease?.active
    ? `Lease active${lease.expires_at ? ` until ${lease.expires_at}` : ""}.`
    : "No active executor lease.";
  return {
    label,
    detail: [leaseDetail, error ? `Last error: ${error}` : ""].filter(Boolean).join(" "),
    color:
      executor.mode === "waiting_for_init"
        ? "gold"
        : failed
          ? "red"
          : active || executor.mode === "external"
            ? "cyan"
            : "default"
  };
}

function readExecutorError(value: ExecutorProjection["last_error"]): string {
  if (typeof value === "string") {
    return value;
  }
  return value?.message ?? value?.error_type ?? "";
}
