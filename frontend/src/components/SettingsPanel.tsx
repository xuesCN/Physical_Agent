import { ApiOutlined, SaveOutlined, SettingOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Descriptions, Form, Input, Select, Space, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { fetchLLMSettings, saveLLMSettings, testLLMSettings } from "../api";
import type { AgentState, HealthState, LLMSettingsSummary } from "../types";
import { compactJson, oneLine } from "./utils";

interface SettingsPanelProps {
  health: HealthState | null;
  state: AgentState | null;
}

interface LLMSettingsFormValues {
  base_url: string;
  api_key?: string;
  model: string;
  api_mode: string;
}

export function SettingsPanel({ health, state }: SettingsPanelProps) {
  const ready = Boolean(state?.ready ?? health?.ready);
  const [form] = Form.useForm<LLMSettingsFormValues>();
  const [llmSettings, setLlmSettings] = useState<LLMSettingsSummary | null>(null);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; text: string } | null>(
    null
  );
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchLLMSettings()
      .then((response) => {
        if (cancelled) {
          return;
        }
        const settings = response.settings ?? response;
        setLlmSettings(settings);
        form.setFieldsValue({
          base_url: settings.base_url,
          model: settings.model,
          api_mode: settings.api_mode
        });
      })
      .catch((error) => {
        if (!cancelled) {
          setFeedback({ type: "error", text: error instanceof Error ? error.message : String(error) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [form]);

  async function handleSave(values: LLMSettingsFormValues) {
    setLoading(true);
    setFeedback(null);
    try {
      const response = await saveLLMSettings({
        base_url: values.base_url,
        api_key: values.api_key ?? "",
        model: values.model,
        api_mode: values.api_mode
      });
      const settings = response.settings ?? response;
      setLlmSettings(settings);
      form.setFieldsValue({ api_key: "" });
      setFeedback({ type: "success", text: response.message ?? "LLM settings saved." });
    } catch (error) {
      setFeedback({ type: "error", text: error instanceof Error ? error.message : String(error) });
    } finally {
      setLoading(false);
    }
  }

  async function handleTest() {
    setTesting(true);
    setFeedback(null);
    try {
      const response = await testLLMSettings();
      const settings = response.settings ?? response;
      setLlmSettings(settings);
      setFeedback({
        type: response.ok ? "success" : "error",
        text: response.message ?? (response.ok ? "LLM connection test passed." : "LLM test failed.")
      });
    } catch (error) {
      setFeedback({ type: "error", text: error instanceof Error ? error.message : String(error) });
    } finally {
      setTesting(false);
    }
  }

  return (
    <Card
      className="panel settings-panel"
      data-testid="settings-panel"
      title={
        <Space>
          <SettingOutlined />
          <Typography.Text strong>Settings</Typography.Text>
        </Space>
      }
    >
      <Descriptions size="small" column={1} className="tight-descriptions">
        <Descriptions.Item label="Backend">
          <Tag>{state?.backend ?? health?.backend ?? "-"}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Workspace">
          <Tag color={ready ? "green" : "gold"}>{ready ? "ready" : "not ready"}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Config">
          {state?.config_path ?? health?.config_path ?? "-"}
        </Descriptions.Item>
        <Descriptions.Item label="Workspace path">
          {state?.workspace_path ?? health?.workspace_path ?? "-"}
        </Descriptions.Item>
        <Descriptions.Item label="Message">
          {state?.message ?? health?.message ?? "-"}
        </Descriptions.Item>
        <Descriptions.Item label="Task">
          {oneLine(state?.task?.body ?? state?.task?.task ?? state?.task, "-")}
        </Descriptions.Item>
      </Descriptions>
      <div className="panel-divider" />
      <Space direction="vertical" size={8} className="full-width">
        <Space wrap>
          <Typography.Text strong>LLM</Typography.Text>
          <Tag color={llmSettings?.has_api_key ? "green" : "gold"}>
            {llmSettings?.has_api_key ? `key ${llmSettings.masked_api_key}` : "no key"}
          </Tag>
        </Space>
        <Form
          form={form}
          layout="vertical"
          className="llm-settings-form"
          initialValues={{ api_mode: "chat_completions" }}
          onFinish={handleSave}
        >
          <Form.Item label="Base URL" name="base_url">
            <Input placeholder="https://api.openai.com/v1" />
          </Form.Item>
          <Form.Item label="API key" name="api_key">
            <Input.Password autoComplete="new-password" placeholder="Leave blank to keep existing key" />
          </Form.Item>
          <div className="two-col">
            <Form.Item label="Model" name="model">
              <Input placeholder="gpt-5.4" />
            </Form.Item>
            <Form.Item label="API mode" name="api_mode">
              <Select
                options={[
                  { value: "chat_completions", label: "chat_completions" },
                  { value: "responses", label: "responses" }
                ]}
              />
            </Form.Item>
          </div>
          <Space wrap>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              icon={<SaveOutlined />}
              data-testid="save-llm-settings"
            >
              Save
            </Button>
            <Button
              onClick={handleTest}
              loading={testing}
              icon={<ApiOutlined />}
              data-testid="test-llm-settings"
            >
              Test connection
            </Button>
          </Space>
        </Form>
        {feedback && (
          <Alert
            data-testid="llm-settings-feedback"
            type={feedback.type}
            showIcon
            message={feedback.text}
          />
        )}
      </Space>
      <div className="panel-divider" />
      <Typography.Text strong>Plan</Typography.Text>
      <pre className="pre-block settings-pre">{compactJson(state?.plan, "{}")}</pre>
    </Card>
  );
}
