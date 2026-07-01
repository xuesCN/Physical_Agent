import { RobotOutlined, StopOutlined, UserOutlined } from "@ant-design/icons";
import { Bubble, Sender } from "@ant-design/x";
import { Alert, Button, Card, Empty, Space, Typography } from "antd";
import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { ChatMessage } from "../types";

interface ChatPanelProps {
  messages: ChatMessage[];
  loading: boolean;
  error?: string | null;
  onSend: (message: string) => Promise<void>;
  onStop: () => void;
}

export function ChatPanel({ messages, loading, error, onSend, onStop }: ChatPanelProps) {
  const [draft, setDraft] = useState("");
  const items = useMemo(
    () =>
      messages.map((message, index) => ({
        key: `${message.role}-${message.created_at ?? index}`,
        role: message.role === "user" ? "user" : "assistant",
        content: (
          <div className="markdown-body">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        )
      })),
    [messages]
  );

  async function submit(value: string) {
    const text = value.trim();
    if (!text) {
      return;
    }
    await onSend(text);
    setDraft("");
  }

  return (
    <Card
      className="panel chat-panel"
      data-testid="chat-panel"
      title={
        <Space>
          <RobotOutlined />
          <Typography.Text strong>Chat</Typography.Text>
        </Space>
      }
    >
      <div className="bubble-stage">
        {items.length ? (
          <Bubble.List
            roles={{
              assistant: {
                placement: "start",
                avatar: { icon: <RobotOutlined /> }
              },
              user: {
                placement: "end",
                avatar: { icon: <UserOutlined /> }
              }
            }}
            items={items}
          />
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No messages" />
        )}
      </div>
      {error && (
        <Alert
          className="chat-stream-error"
          data-testid="chat-stream-error"
          type="error"
          showIcon
          message={error}
        />
      )}
      <div className="chat-input-row">
        <Sender
          className="chat-sender"
          value={draft}
          loading={loading}
          placeholder="Message the agent"
          submitType="enter"
          onChange={setDraft}
          onSubmit={submit}
        />
        <Button
          className="chat-stop-button"
          data-testid="stop-chat-stream"
          icon={<StopOutlined />}
          disabled={!loading}
          onClick={onStop}
        >
          Stop
        </Button>
      </div>
    </Card>
  );
}
