import { RobotOutlined } from "@ant-design/icons";
import { Card, Empty, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { AgentState } from "../types";

interface RobotRow {
  key: string;
  id: string;
  kind: string;
  driver: string;
  status: string;
  capabilities: string[];
}

interface RobotsPanelProps {
  state: AgentState | null;
}

export function RobotsPanel({ state }: RobotsPanelProps) {
  const rows: RobotRow[] = Object.entries(state?.capabilities?.robots ?? {}).map(
    ([id, robot]) => ({
      key: id,
      id,
      kind: robot.kind ?? "robot",
      driver: robot.driver ?? "-",
      status: robot.status ?? "unknown",
      capabilities: robot.capabilities?.map((capability) => capability.name ?? "").filter(Boolean) ?? []
    })
  );

  const columns: ColumnsType<RobotRow> = [
    {
      title: "Robot",
      dataIndex: "id",
      width: 160,
      render: (value: string) => <Typography.Text code>{value}</Typography.Text>
    },
    { title: "Kind", dataIndex: "kind", width: 110 },
    { title: "Driver", dataIndex: "driver", width: 150 },
    {
      title: "Status",
      dataIndex: "status",
      width: 110,
      render: (value: string) => (
        <Tag color={value === "connected" ? "green" : "default"}>{value}</Tag>
      )
    },
    {
      title: "Capabilities",
      dataIndex: "capabilities",
      render: (items: string[]) => (
        <Space size={5} wrap>
          {items.length ? items.map((item) => <Tag key={item}>{item}</Tag>) : "-"}
        </Space>
      )
    }
  ];

  return (
    <Card
      className="panel"
      data-testid="robots-panel"
      title={
        <Space>
          <RobotOutlined />
          <Typography.Text strong>Robots</Typography.Text>
        </Space>
      }
    >
      {rows.length ? (
        <Table
          size="small"
          pagination={false}
          dataSource={rows}
          columns={columns}
          scroll={{ x: 680 }}
        />
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No robots" />
      )}
    </Card>
  );
}
