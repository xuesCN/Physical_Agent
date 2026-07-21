import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  DownOutlined,
  RightOutlined,
  StopOutlined,
  SafetyCertificateOutlined,
  WarningOutlined
} from "@ant-design/icons";
import { Button, Card, Popconfirm, Segmented, Space, Table, Tag, Typography } from "antd";
import { useMemo, useState } from "react";
import { useMessages } from "../locales/context";
import type { ActionItem, AgentState } from "../types";
import { JsonSummaryLine } from "./JsonSummary";
import {
  expectedSummary,
  formatObjectValue
} from "./readableFormatters";

type BoardKey = "pending" | "in_progress" | "completed" | "cancelled";

const STATUS_ICON = {
  pending: <ClockCircleOutlined />,
  in_progress: <ClockCircleOutlined spin />,
  completed: <CheckCircleOutlined />,
  cancelled: <StopOutlined />
};

const STATUS_COLOR = {
  pending: "gold",
  in_progress: "blue",
  completed: "green",
  cancelled: "red"
};

const ACTION_BOARD_COLLAPSED_STORAGE_KEY = "physical-agent-action-board-collapsed:v1";

interface ActionBoardProps {
  actions: AgentState["actions"] | undefined;
  loading?: boolean;
  onApprove?: (actionId: string) => Promise<void>;
  onReject?: (actionId: string, reason: string) => Promise<void>;
}

export function ActionBoard({
  actions,
  loading = false,
  onApprove,
  onReject
}: ActionBoardProps) {
  const labels = useMessages();
  const [active, setActive] = useState<BoardKey>("pending");
  const [collapsedPreference, setCollapsedPreference] = useState(
    readActionBoardCollapsedPreference
  );
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const approvalRequiredCount = (actions?.pending ?? []).filter(
    (action) => action.metadata?.approval?.required
  ).length;
  const totalActions = totalActionCount(actions);
  const approvalForcesOpen = approvalRequiredCount > 0;
  const collapsed = approvalForcesOpen ? false : collapsedPreference;
  const visibleActive: BoardKey = approvalForcesOpen ? "pending" : active;
  const rows = actions?.[visibleActive] ?? [];
  const data = useMemo(
    () => rows.map((item) => ({ ...item, key: item.id })),
    [rows]
  );

  function toggleCollapsed() {
    if (approvalForcesOpen) {
      return;
    }
    setCollapsedPreference((current) => {
      const next = !current;
      writeActionBoardCollapsedPreference(next);
      return next;
    });
  }

  return (
    <Card
      className={`panel action-board${
        approvalForcesOpen ? " action-board-approval-required" : ""
      }`}
      data-testid="action-board"
      title={
        <Space wrap data-testid="action-board-summary">
          {approvalForcesOpen && <WarningOutlined className="action-board-warning-icon" />}
          <Typography.Text strong>{labels.actions.title}</Typography.Text>
          {approvalForcesOpen ? (
            <Typography.Text className="action-board-warning-copy">
              {approvalRequiredCount === 1
                ? labels.actions.waitingApprovalOne.replace(
                    "{count}",
                    String(approvalRequiredCount)
                  )
                : labels.actions.waitingApprovalMany.replace(
                    "{count}",
                    String(approvalRequiredCount)
                  )}
            </Typography.Text>
          ) : totalActions === 0 ? (
            <Typography.Text type="secondary">{labels.actions.noPendingActions}</Typography.Text>
          ) : null}
          {totalActions > 0 && (
            <>
              <Tag icon={STATUS_ICON.pending} color={STATUS_COLOR.pending}>
                {labels.actions.pending} {actions?.pending?.length ?? 0}
              </Tag>
              <Tag icon={STATUS_ICON.completed} color={STATUS_COLOR.completed}>
                {labels.actions.completed} {actions?.completed?.length ?? 0}
              </Tag>
            </>
          )}
        </Space>
      }
      extra={
        approvalForcesOpen ? null : (
          <Button
            data-testid="action-board-toggle"
            size="small"
            type="text"
            aria-expanded={!collapsed}
            aria-label={collapsed ? labels.actions.expandBoard : labels.actions.collapseBoard}
            icon={collapsed ? <RightOutlined /> : <DownOutlined />}
            onClick={toggleCollapsed}
          />
        )
      }
    >
      {!collapsed && (
        <div data-testid="action-board-body" className="action-board-body">
          <Segmented
            size="small"
            value={visibleActive}
            disabled={approvalForcesOpen}
            options={[
              { label: `${labels.actions.pending} ${actions?.pending?.length ?? 0}`, value: "pending" },
              { label: `Running ${actions?.in_progress?.length ?? 0}`, value: "in_progress" },
              { label: `${labels.actions.completed} ${actions?.completed?.length ?? 0}`, value: "completed" },
              { label: `${labels.actions.cancelled} ${actions?.cancelled?.length ?? 0}`, value: "cancelled" }
            ]}
            onChange={(value) => setActive(value as BoardKey)}
          />
          <Table<ActionItem & { key: string }>
        size="small"
        pagination={false}
        dataSource={data}
        tableLayout="fixed"
        scroll={{ x: 1520, y: 260 }}
        locale={{
          emptyText: labels.actions.noActions.replace(
            "{status}",
            visibleActive === "in_progress" ? "running" : labels.actions[visibleActive]
          )
        }}
        columns={[
          {
            title: labels.actions.id,
            dataIndex: "id",
            width: 120,
            render: (value: string) => <Typography.Text code>{value}</Typography.Text>
          },
          {
            title: labels.actions.target,
            key: "target",
            width: 180,
            ellipsis: true,
            render: (_, record) => `${record.robot}.${record.capability}`
          },
          {
            title: labels.actions.params,
            dataIndex: "params",
            width: 300,
            render: (value) => (
              <JsonSummaryLine
                label={labels.actions.params}
                value={value}
                fallback={labels.actions.noParams}
              />
            )
          },
          {
            title: labels.actions.depends,
            dataIndex: "depends_on",
            width: 120,
            ellipsis: true,
            render: (value?: string[]) => value?.join(", ") || "-"
          },
          {
            title: labels.actions.approval,
            key: "approval",
            width: 170,
            render: (_, record) => <ApprovalBadge action={record} labels={labels.actions} />
          },
          {
            title: labels.actions.expected,
            key: "expected",
            width: 260,
            ellipsis: true,
            render: (_, record) => {
              const expected = record.metadata?.expected;
              const summary = expectedSummary(expected);
              if (!summary) {
                return <Typography.Text type="secondary">-</Typography.Text>;
              }
              return (
                <JsonSummaryLine label={labels.actions.expected} text={summary} />
              );
            }
          },
          {
            title: labels.actions.source,
            key: "source",
            width: 180,
            ellipsis: true,
            render: (_, record) => (
              <Typography.Text className="source-cell">
                {sourceText(record)}
              </Typography.Text>
            )
          },
          {
            title: labels.actions.review,
            key: "review",
            width: 190,
            fixed: "right",
            render: (_, record) => {
              if (visibleActive !== "pending") {
                return rejectedReason(record);
              }
              return (
                <ActionApprovalControls
                  action={record}
                  loading={loading || busyAction === record.id}
                  disabled={Boolean(busyAction && busyAction !== record.id)}
                  onApprove={
                    onApprove
                      ? async () => {
                          setBusyAction(record.id);
                          try {
                            await onApprove(record.id);
                          } finally {
                            setBusyAction(null);
                          }
                        }
                      : undefined
                  }
                  onReject={
                    onReject
                      ? async () => {
                          setBusyAction(record.id);
                          try {
                            await onReject(record.id, "Rejected from Actions board.");
                          } finally {
                            setBusyAction(null);
                          }
                        }
                      : undefined
                  }
                />
              );
            }
          }
        ]}
          />
        </div>
      )}
    </Card>
  );
}

function totalActionCount(actions: AgentState["actions"] | undefined): number {
  return (
    (actions?.pending?.length ?? 0) +
    (actions?.in_progress?.length ?? 0) +
    (actions?.completed?.length ?? 0) +
    (actions?.cancelled?.length ?? 0)
  );
}

function readActionBoardCollapsedPreference(): boolean {
  try {
    const stored = localStorage.getItem(ACTION_BOARD_COLLAPSED_STORAGE_KEY);
    return stored === null ? true : stored !== "false";
  } catch {
    return true;
  }
}

function writeActionBoardCollapsedPreference(collapsed: boolean) {
  try {
    localStorage.setItem(ACTION_BOARD_COLLAPSED_STORAGE_KEY, String(collapsed));
  } catch {
    // UI preferences are best-effort when storage is unavailable.
  }
}

function ApprovalBadge({
  action,
  labels
}: {
  action: ActionItem;
  labels: ReturnType<typeof useMessages>["actions"];
}) {
  const approval = action.metadata?.approval;
  if (approval?.status === "rejected") {
    return <Tag color="red">{labels.approvalRejected}</Tag>;
  }
  if (approval?.required) {
    if (approval.status === "approved") {
      return <Tag color="green">{labels.executionApproved}</Tag>;
    }
    return <Tag color="gold">{labels.approvalRequired}</Tag>;
  }
  return <Tag>{labels.approvalNotRequired}</Tag>;
}

interface ActionApprovalControlsProps {
  action: ActionItem;
  loading: boolean;
  disabled: boolean;
  onApprove?: () => Promise<void>;
  onReject?: () => Promise<void>;
}

function ActionApprovalControls({
  action,
  loading,
  disabled,
  onApprove,
  onReject
}: ActionApprovalControlsProps) {
  const labels = useMessages().actions;
  const approval = action.metadata?.approval;
  const needsApproval = Boolean(approval?.required && approval.status !== "approved");
  return (
    <Space wrap size={6}>
      {needsApproval && (
        <Button
          size="small"
          type="primary"
          icon={<SafetyCertificateOutlined />}
          loading={loading}
          disabled={disabled || !onApprove}
          onClick={() => void onApprove?.()}
        >
          {labels.approveExecution}
        </Button>
      )}
      <Popconfirm
        title={labels.rejectTitle}
        description={labels.rejectDescription}
        okText={labels.rejectOk}
        cancelText={labels.rejectCancel}
        onConfirm={() => void onReject?.()}
      >
        <Button
          size="small"
          danger
          icon={<StopOutlined />}
          loading={loading}
          disabled={disabled || !onReject}
        >
          {labels.reject}
        </Button>
      </Popconfirm>
    </Space>
  );
}

function sourceText(action: ActionItem): string {
  const metadata = action.metadata;
  if (!metadata) {
    return "-";
  }
  return [
    metadata.source,
    metadata.user_message ?? metadata.original_task
  ].filter(Boolean).join(" · ") || "-";
}

function rejectedReason(action: ActionItem) {
  const reason = action.metadata?.approval?.reason;
  return reason ? <Typography.Text>{reason}</Typography.Text> : <Typography.Text type="secondary">-</Typography.Text>;
}
