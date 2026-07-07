import { CodeOutlined } from "@ant-design/icons";
import { Collapse, Spin, Typography } from "antd";
import { Suspense, lazy } from "react";

const JsonView = lazy(() =>
  import("react18-json-view").then((module) => ({ default: module.default }))
);

interface JsonTreeLazyProps {
  value: unknown;
  className?: string;
}

interface RawJsonFallbackProps extends JsonTreeLazyProps {
  label?: string;
}

export function JsonTreeLazy({ value, className }: JsonTreeLazyProps) {
  return (
    <Suspense
      fallback={
        <div className="json-tree-loading">
          <Spin size="small" />
          <Typography.Text type="secondary">Loading raw JSON tree</Typography.Text>
        </div>
      }
    >
      <JsonView
        src={normalizeJsonRoot(value)}
        collapsed={2}
        collapseStringsAfterLength={120}
        enableClipboard
        displaySize="collapsed"
        theme="github"
        className={className ?? "json-tree"}
      />
    </Suspense>
  );
}

export function RawJsonFallback({ value, label = "Raw JSON", className }: RawJsonFallbackProps) {
  return (
    <Collapse
      ghost
      size="small"
      destroyOnHidden
      className="raw-json-collapse"
      items={[
        {
          key: "raw",
          label: (
            <span className="raw-json-label">
              <CodeOutlined />
              {label}
            </span>
          ),
          children: <JsonTreeLazy value={value} className={className} />
        }
      ]}
    />
  );
}

function normalizeJsonRoot(value: unknown): unknown {
  if (value === undefined) {
    return null;
  }
  if (value && typeof value === "object") {
    return value;
  }
  return { value };
}
