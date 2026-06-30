import { ThunderboltOutlined } from "@ant-design/icons";
import { Card, Empty, List, Space, Tag, Typography } from "antd";
import type { ApiEvent } from "../types";
import { oneLine } from "./utils";

interface EventsPanelProps {
  events: ApiEvent[];
}

export function EventsPanel({ events }: EventsPanelProps) {
  return (
    <Card
      className="panel events-panel"
      data-testid="events-panel"
      title={
        <Space>
          <ThunderboltOutlined />
          <Typography.Text strong>Events</Typography.Text>
        </Space>
      }
    >
      {events.length ? (
        <List
          size="small"
          dataSource={events}
          renderItem={(event) => (
            <List.Item className="event-row">
              <Space direction="vertical" size={2} className="full-width">
                <Space size={6} wrap>
                  <Tag color={event.type === "error" ? "red" : "blue"}>{event.type}</Tag>
                  <Typography.Text type="secondary">#{event.id}</Typography.Text>
                  <Typography.Text type="secondary">{event.ts}</Typography.Text>
                </Space>
                <Typography.Text>{oneLine(event.payload)}</Typography.Text>
              </Space>
            </List.Item>
          )}
        />
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No events" />
      )}
    </Card>
  );
}
