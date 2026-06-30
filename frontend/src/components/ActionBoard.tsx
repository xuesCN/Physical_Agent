import { CheckCircleOutlined, ClockCircleOutlined, StopOutlined } from "@ant-design/icons";
import { Card, Segmented, Space, Table, Tag, Typography } from "antd";
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
}

export function ActionBoard({ actions }: ActionBoardProps) {
  const [active, setActive] = useState<BoardKey>("pending");
  const rows = actions?.[active] ?? [];
  const data = useMemo(
    () => rows.map((item) => ({ ...item, key: item.id })),
    [rows]
  );

  return (
    <Card
      className="panel action-board"
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
        scroll={{ x: true, y: 280 }}
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
            render: (_, record) => `${record.robot}.${record.capability}`
          },
          {
            title: "Params",
            dataIndex: "params",
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
            render: (value?: string[]) => value?.join(", ") || "-"
          }
        ]}
      />
    </Card>
  );
}
