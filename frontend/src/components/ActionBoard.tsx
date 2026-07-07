import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  StopOutlined,
  SafetyCertificateOutlined
} from "@ant-design/icons";
import { Button, Card, Popconfirm, Segmented, Space, Table, Tag, Typography } from "antd";
import { useMemo, useState } from "react";
import type { ActionItem, AgentState } from "../types";
import { compactJson } from "./utils";

type BoardKey = "pending" | "completed" | "cancelled";

const STATUS_ICON = {
  pending: <ClockCircleOutlined />,
  completed: <CheckCircleOutlined />,
  cancelled: <StopOutlined />
};

const STATUS_COLOR = {
  pending: "gold",
  completed: "green",
  cancelled: "red"
};

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
  const [active, setActive] = useState<BoardKey>("pending");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const rows = actions?.[active] ?? [];
  const data = useMemo(
    () => rows.map((item) => ({ ...item, key: item.id })),
    [rows]
  );

  return (
    <Card
      className="panel action-board"
      data-testid="action-board"
      title={
        <Space>
          <Typography.Text strong>Action Board</Typography.Text>
          <Tag icon={STATUS_ICON[active]} color={STATUS_COLOR[active]}>
            {rows.length}
          </Tag>
        </Space>
      }
      extra={
        <Segmented
          size="small"
          value={active}
          options={[
            { label: `Pending ${actions?.pending?.length ?? 0}`, value: "pending" },
            { label: `Completed ${actions?.completed?.length ?? 0}`, value: "completed" },
            { label: `Cancelled ${actions?.cancelled?.length ?? 0}`, value: "cancelled" }
          ]}
          onChange={(value) => setActive(value as BoardKey)}
        />
      }
    >
      <Table<ActionItem & { key: string }>
        size="small"
        pagination={false}
        dataSource={data}
        tableLayout="fixed"
        scroll={{ x: 1260, y: 260 }}
        locale={{ emptyText: `No ${active} actions` }}
        columns={[
          {
            title: "ID",
            dataIndex: "id",
            width: 120,
            render: (value: string) => <Typography.Text code>{value}</Typography.Text>
          },
          {
            title: "Target",
            key: "target",
            width: 180,
            ellipsis: true,
            render: (_, record) => `${record.robot}.${record.capability}`
          },
          {
            title: "Params",
            dataIndex: "params",
            width: 300,
            render: (value) => (
              <Typography.Text className="mono-cell">
                {compactJson(value, "{}")}
              </Typography.Text>
            )
          },
          {
            title: "Depends",
            dataIndex: "depends_on",
            width: 120,
            ellipsis: true,
            render: (value?: string[]) => value?.join(", ") || "-"
          },
          {
            title: "Approval",
            key: "approval",
            width: 170,
            render: (_, record) => <ApprovalBadge action={record} />
          },
          {
            title: "Source",
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
            title: "Review",
            key: "review",
            width: 190,
            fixed: "right",
            render: (_, record) => {
              if (active !== "pending") {
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
    </Card>
  );
}

function ApprovalBadge({ action }: { action: ActionItem }) {
  const approval = action.metadata?.approval;
  if (approval?.status === "rejected") {
    return <Tag color="red">Rejected</Tag>;
  }
  if (approval?.required) {
    if (approval.status === "approved") {
      return <Tag color="green">Execution approved</Tag>;
    }
    return <Tag color="gold">Needs execution approval</Tag>;
  }
  return <Tag>No approval needed</Tag>;
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
          Approve execution
        </Button>
      )}
      <Popconfirm
        title="Reject this action?"
        description="It will move to Cancelled with a rejection reason."
        okText="Reject"
        cancelText="Keep"
        onConfirm={() => void onReject?.()}
      >
        <Button
          size="small"
          danger
          icon={<StopOutlined />}
          loading={loading}
          disabled={disabled || !onReject}
        >
          Reject
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
