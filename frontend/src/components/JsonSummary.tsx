import { Space, Typography } from "antd";
import type { ReactNode } from "react";
import { formatObjectValue } from "./readableFormatters";

interface JsonSummaryLineProps {
  label: string;
  value?: unknown;
  text?: string;
  fallback?: string;
  icon?: ReactNode;
  className?: string;
  collapsible?: boolean;
}

export function JsonSummaryLine({
  label,
  value,
  text,
  fallback = "-",
  icon,
  className,
  collapsible = false
}: JsonSummaryLineProps) {
  const summary = text ?? formatObjectValue(value, fallback);
  if (collapsible) {
    return (
      <details className="json-summary-collapsible">
        <summary className="json-summary-toggle">
          {icon}
          {label}:
        </summary>
        <Typography.Text className={className ?? "schema-summary json-summary-line"}>
          {summary}
        </Typography.Text>
      </details>
    );
  }
  return (
    <Typography.Text className={className ?? "schema-summary json-summary-line"}>
      {icon}
      {label}: {summary}
    </Typography.Text>
  );
}

interface JsonSummaryStackProps {
  items: Array<{
    key: string;
    label: string;
    value?: unknown;
    text?: string;
    fallback?: string;
  }>;
  className?: string;
}

export function JsonSummaryStack({ items, className }: JsonSummaryStackProps) {
  const visible = items.filter((item) => {
    const text = item.text ?? formatObjectValue(item.value, "");
    return text !== "";
  });
  if (!visible.length) {
    return null;
  }
  return (
    <Space direction="vertical" size={2} className={className ?? "full-width"}>
      {visible.map((item) => (
        <JsonSummaryLine
          key={item.key}
          label={item.label}
          value={item.value}
          text={item.text}
          fallback={item.fallback}
        />
      ))}
    </Space>
  );
}
