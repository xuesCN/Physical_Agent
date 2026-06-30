import { InboxOutlined } from "@ant-design/icons";
import { Card, Input, InputNumber, Space, Upload, Typography } from "antd";
import type { UploadProps } from "antd";
import { useState } from "react";
import { uploadBrowserFile } from "../api";
import type { AgentState, UploadResponse } from "../types";

interface UploadPanelProps {
  onUploaded: (state: AgentState, response: UploadResponse) => void;
  onError: (error: Error) => void;
}

const ACCEPTED_SUFFIXES = ".txt,.md,.markdown,.py,.json,.yaml,.yml,.toml,.csv,.log";

export function UploadPanel({ onUploaded, onError }: UploadPanelProps) {
  const [tags, setTags] = useState("");
  const [importance, setImportance] = useState(0);

  const uploadProps: UploadProps = {
    name: "file",
    multiple: false,
    accept: ACCEPTED_SUFFIXES,
    showUploadList: { showRemoveIcon: true },
    customRequest: async (options) => {
      try {
        const file = options.file as File;
        const response = await uploadBrowserFile(file, tags, importance);
        options.onSuccess?.(response, file);
        onUploaded(response.state, response);
      } catch (error) {
        const normalized = error instanceof Error ? error : new Error(String(error));
        options.onError?.(normalized);
        onError(normalized);
      }
    }
  };

  return (
    <Card
      className="panel"
      title={
        <Space>
          <InboxOutlined />
          <Typography.Text strong>Upload</Typography.Text>
        </Space>
      }
    >
      <div className="two-col">
        <Input
          value={tags}
          onChange={(event) => setTags(event.target.value)}
          placeholder="tags"
        />
        <InputNumber
          value={importance}
          min={0}
          max={10}
          onChange={(value) => setImportance(Number(value ?? 0))}
          className="full-width"
        />
      </div>
      <Upload.Dragger {...uploadProps} className="upload-drop">
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-text">Drop text files here</p>
        <p className="ant-upload-hint">5MB max</p>
      </Upload.Dragger>
    </Card>
  );
}
