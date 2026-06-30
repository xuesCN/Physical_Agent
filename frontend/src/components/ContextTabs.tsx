import { AlertOutlined, CompassOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { Descriptions, Empty, Space, Tabs, Tag, Typography } from "antd";
import type { TabsProps } from "antd";
import type { AgentState } from "../types";
import { compactJson, oneLine } from "./utils";

interface ContextTabsProps {
  state: AgentState | null;
  defaultActiveKey?: "world" | "feedback" | "safety";
}

export function ContextTabs({ state, defaultActiveKey = "world" }: ContextTabsProps) {
  const latest = (state?.feedback?.latest ?? {}) as Record<string, unknown>;
  const history = (state?.feedback?.history ?? []) as Array<Record<string, unknown>>;
  const items: TabsProps["items"] = [
    {
      key: "world",
      label: (
        <Space size={6}>
          <CompassOutlined />
          World
        </Space>
      ),
      children: (
        <div className="tab-pane-grid">
          <Typography.Paragraph className="summary-text">
            {oneLine(state?.world?.summary, "No world summary")}
          </Typography.Paragraph>
          <Descriptions size="small" column={1} className="tight-descriptions">
            <Descriptions.Item label="Objects">
              <pre className="inline-pre">{compactJson(state?.world?.state, "{}")}</pre>
            </Descriptions.Item>
            <Descriptions.Item label="Environment">
              <pre className="inline-pre">{compactJson(state?.world?.environment, "{}")}</pre>
            </Descriptions.Item>
          </Descriptions>
        </div>
      )
    },
    {
      key: "feedback",
      label: (
        <Space size={6}>
          <AlertOutlined />
          Feedback
        </Space>
      ),
      children: Object.keys(latest).length ? (
        <div className="tab-pane-grid">
          <Descriptions size="small" column={1} className="tight-descriptions">
            <Descriptions.Item label="Status">
              <Tag color={latest.status === "completed" ? "green" : "default"}>
                {String(latest.status ?? "-")}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Action">
              {String(latest.action_id ?? "-")}
            </Descriptions.Item>
            <Descriptions.Item label="Message">
              {String(latest.message ?? "-")}
            </Descriptions.Item>
          </Descriptions>
          {history.length > 0 && (
            <pre className="inline-pre">{compactJson(history.slice(-5), "[]")}</pre>
          )}
        </div>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No feedback" />
      )
    },
    {
      key: "safety",
      label: (
        <Space size={6}>
          <SafetyCertificateOutlined />
          Safety
        </Space>
      ),
      children: <pre className="pre-block">{compactJson(state?.safety, "{}")}</pre>
    }
  ];

  return (
    <div className="panel context-tabs" data-testid="context-tabs">
      <Tabs defaultActiveKey={defaultActiveKey} items={items} />
    </div>
  );
}
