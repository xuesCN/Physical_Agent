import { ApiOutlined, CodeOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  Select,
  Space,
  Tag,
  Typography
} from "antd";
import { useState } from "react";
import { integrateHardware } from "../api";
import type { AgentState, IntegrateResult } from "../types";

interface HardwarePanelProps {
  onStateChange: (state: AgentState) => void;
  onError: (error: Error) => void;
}

interface HardwareFormValues {
  source: string;
  name?: string;
  output?: string;
  mode: "scaffold" | "llm";
  model?: string;
}

export function HardwarePanel({ onStateChange, onError }: HardwarePanelProps) {
  const [form] = Form.useForm<HardwareFormValues>();
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; text: string } | null>(
    null
  );
  const [result, setResult] = useState<IntegrateResult | null>(null);
  const mode = Form.useWatch("mode", form) ?? "scaffold";

  async function handleFinish(values: HardwareFormValues) {
    setLoading(true);
    setFeedback(null);
    setResult(null);
    try {
      const response = await integrateHardware({
        source: values.source,
        name: values.name?.trim() || undefined,
        output: values.output?.trim() || undefined,
        llm: values.mode === "llm",
        model: values.mode === "llm" ? values.model?.trim() || undefined : undefined
      });
      setResult(response.result);
      setFeedback({ type: "success", text: response.message });
      onStateChange(response.state);
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      setFeedback({ type: "error", text: err.message });
      onError(err);
    } finally {
      setLoading(false);
    }
  }

  const profile = result?.source ?? result?.integration?.source ?? null;
  const generatedFiles =
    result?.generated_files ?? result?.integration?.generated_files ?? [];
  const nextSteps = result?.next_steps ?? profile?.next_steps ?? [];
  const validation = result?.validation ?? null;

  return (
    <Card
      className="panel"
      data-testid="hardware-panel"
      title={
        <Space>
          <ApiOutlined />
          <Typography.Text strong>Hardware Integration</Typography.Text>
        </Space>
      }
    >
      <Alert
        type="info"
        showIcon
        message="Proposal-side only"
        description="Generates driver files and validates them in mock mode. Watch remains the only runtime that loads drivers and touches hardware."
      />
      <div className="panel-divider" />
      <Form
        form={form}
        layout="vertical"
        initialValues={{ mode: "scaffold" }}
        onFinish={handleFinish}
      >
        <Form.Item
          label="Source (SDK folder, repo path, or URL)"
          name="source"
          rules={[{ required: true, message: "Source is required" }]}
        >
          <Input
            placeholder="e.g. ./vendor_sdk or https://github.com/vendor/robot-sdk"
            data-testid="integrate-source-input"
          />
        </Form.Item>
        <div className="two-col">
          <Form.Item label="Driver name (optional)" name="name">
            <Input placeholder="my_arm_driver" data-testid="integrate-name-input" />
          </Form.Item>
          <Form.Item label="Output directory (optional)" name="output">
            <Input placeholder="my_hardware/my_arm_driver" />
          </Form.Item>
        </div>
        <div className="two-col">
          <Form.Item label="Mode" name="mode">
            <Select
              data-testid="integrate-mode-select"
              options={[
                { value: "scaffold", label: "Scaffold (offline, safe template)" },
                { value: "llm", label: "LLM draft (uses configured LLM)" }
              ]}
            />
          </Form.Item>
          {mode === "llm" && (
            <Form.Item label="Model override (optional)" name="model">
              <Input placeholder="Leave blank to use configured model" />
            </Form.Item>
          )}
        </div>
        <Button
          type="primary"
          htmlType="submit"
          loading={loading}
          icon={<CodeOutlined />}
          data-testid="integrate-submit-button"
        >
          Generate driver
        </Button>
      </Form>
      {feedback && (
        <>
          <div className="panel-divider" />
          <Alert
            data-testid="integrate-feedback"
            type={feedback.type}
            showIcon
            message={feedback.text}
          />
        </>
      )}
      {result && (
        <>
          <div className="panel-divider" />
          <Space direction="vertical" size={8} className="full-width" data-testid="integrate-result">
            <Space wrap>
              <Typography.Text strong>Result</Typography.Text>
              {result.llm_used != null && (
                <Tag color={result.llm_used ? "green" : "gold"}>
                  {result.llm_used ? "LLM draft" : "scaffold"}
                </Tag>
              )}
              {validation && (
                <Tag color={validation.ok ? "green" : "red"}>
                  validation {validation.ok ? "passed" : "failed"}
                </Tag>
              )}
            </Space>
            <Descriptions size="small" column={1} className="tight-descriptions">
              <Descriptions.Item label="Output path">
                <Typography.Text code>
                  {result.output_path ?? result.integration?.output_path ?? "-"}
                </Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="Detected transport">
                {profile?.transport ?? "-"}
              </Descriptions.Item>
              <Descriptions.Item label="Robot kind">{profile?.robot_kind ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="Title">{profile?.title ?? "-"}</Descriptions.Item>
            </Descriptions>
            {generatedFiles.length > 0 && (
              <Space size={5} wrap>
                {generatedFiles.map((file) => (
                  <Tag key={file}>{file}</Tag>
                ))}
              </Space>
            )}
            {result.llm_error && (
              <Alert type="warning" showIcon message="LLM coding issue" description={result.llm_error} />
            )}
            {validation?.checks && validation.checks.length > 0 && (
              <Typography.Text type="secondary">
                Checks: {validation.checks.join(" · ")}
              </Typography.Text>
            )}
            {validation?.errors && validation.errors.length > 0 && (
              <Alert
                type="error"
                showIcon
                message="Validation errors"
                description={validation.errors.join("; ")}
              />
            )}
            {nextSteps.length > 0 && (
              <Typography.Text type="secondary">
                Next steps: {nextSteps.join(" · ")}
              </Typography.Text>
            )}
          </Space>
        </>
      )}
    </Card>
  );
}
