import { SafetyCertificateOutlined } from "@ant-design/icons";
import { Card, Empty, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type {
  AgentOutputOverview,
  AgentTaskOverview
} from "../viewmodels/agentOutput";

interface AgentTaskGraphCardProps {
  output: AgentOutputOverview | null;
}

export function AgentTaskGraphCard({ output }: AgentTaskGraphCardProps) {
  return (
    <Card
      className="panel agent-task-graph-card"
      data-testid="agent-task-graph"
      title={
        <Space>
          <SafetyCertificateOutlined />
          <Typography.Text strong>Agent output tasks</Typography.Text>
        </Space>
      }
      extra={
        output ? (
          <Space size={4} wrap>
            <Tag>{humanize(output.lifecycle)}</Tag>
            <Tag color={statusColor(output.status)}>{humanize(output.status)}</Tag>
          </Space>
        ) : null
      }
    >
      {output ? <AgentOutputContent output={output} /> : <EmptyAgentOutput />}
    </Card>
  );
}

function AgentOutputContent({ output }: { output: AgentOutputOverview }) {
  return (
    <Space direction="vertical" size={10} className="full-width">
      <div className="agent-output-summary">
        <Space size={6} wrap>
          <Typography.Text type="secondary">Decision</Typography.Text>
          <Tag color="blue">{humanize(output.decision)}</Tag>
          {output.proposalId ? (
            <Typography.Text code>{output.proposalId}</Typography.Text>
          ) : null}
        </Space>
        {output.message ? <Typography.Text>{output.message}</Typography.Text> : null}
        <Typography.Text type="secondary">
          Safety gates are mandatory execution tasks compiled by the system and owned by watch.
        </Typography.Text>
      </div>
      {output.tasks.length ? (
        <Table<AgentTaskOverview>
          size="small"
          pagination={false}
          rowKey="key"
          dataSource={output.tasks}
          columns={agentTaskColumns}
          rowClassName={(task) =>
            task.kind === "safety_gate"
              ? "agent-task-row-safety"
              : `agent-task-row-${task.kind}`
          }
          scroll={{ x: 1100 }}
        />
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No compiled tasks" />
      )}
    </Space>
  );
}

function EmptyAgentOutput() {
  return (
    <Empty
      image={Empty.PRESENTED_IMAGE_SIMPLE}
      description="No compiled AgentOutput"
    />
  );
}

const agentTaskColumns: ColumnsType<AgentTaskOverview> = [
  {
    title: "Task",
    dataIndex: "label",
    width: 260,
    render: (_value: string, task) => (
      <Space direction="vertical" size={2}>
        <Space size={4} wrap>
          <Typography.Text strong={task.kind === "safety_gate"}>{task.label}</Typography.Text>
          {task.mandatory ? <Tag color="red">mandatory</Tag> : null}
        </Space>
        <Typography.Text code type="secondary">
          {task.id}
        </Typography.Text>
      </Space>
    )
  },
  {
    title: "Kind",
    dataIndex: "kind",
    width: 130,
    render: (kind: AgentTaskOverview["kind"]) => (
      <Tag color={kindColor(kind)}>{humanize(kind)}</Tag>
    )
  },
  {
    title: "Owner",
    dataIndex: "owner",
    width: 90,
    render: (owner: AgentTaskOverview["owner"]) => (
      <Tag color={owner === "watch" ? "purple" : "gold"}>{owner}</Tag>
    )
  },
  {
    title: "Status",
    dataIndex: "status",
    width: 120,
    render: (status: AgentTaskOverview["status"]) => (
      <Tag color={statusColor(status)}>{humanize(status)}</Tag>
    )
  },
  {
    title: "Action",
    dataIndex: "actionId",
    width: 140,
    render: (actionId: string) => <Typography.Text code>{actionId}</Typography.Text>
  },
  {
    title: "Depends on",
    dataIndex: "dependsOn",
    width: 250,
    render: (dependencies: string[]) =>
      dependencies.length ? (
        <Space size={[4, 4]} wrap>
          {dependencies.map((dependency) => (
            <Typography.Text key={dependency} code>
              {dependency}
            </Typography.Text>
          ))}
        </Space>
      ) : (
        <Typography.Text type="secondary">—</Typography.Text>
      )
  },
  {
    title: "Assurance",
    dataIndex: "policySource",
    width: 150,
    render: (_value: string, task) =>
      task.kind === "safety_gate" ? (
        <Space direction="vertical" size={2}>
          <Typography.Text code>{task.policySource || "SAFETY.md"}</Typography.Text>
          <Typography.Text type="secondary">{task.checkCount} checks</Typography.Text>
        </Space>
      ) : (
        <Typography.Text type="secondary">—</Typography.Text>
      )
  }
];

function kindColor(kind: string): string {
  if (kind === "safety_gate") {
    return "volcano";
  }
  if (kind === "approval") {
    return "gold";
  }
  if (kind === "physical_action") {
    return "blue";
  }
  return "cyan";
}

function statusColor(status: string): string {
  if (status === "passed" || status === "completed") {
    return "green";
  }
  if (status === "rejected" || status === "failed") {
    return "red";
  }
  if (status === "checking") {
    return "processing";
  }
  if (status === "queued" || status === "requested" || status.startsWith("waiting")) {
    return "gold";
  }
  return "default";
}

function humanize(value: string): string {
  return value.replace(/_/g, " ");
}
