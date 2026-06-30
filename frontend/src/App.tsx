import { App as AntApp, ConfigProvider, Layout, theme } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchHealth,
  fetchState,
  proposeAction,
  sendChat,
  submitTask
} from "./api";
import { ActionBoard } from "./components/ActionBoard";
import { ChatPanel } from "./components/ChatPanel";
import { EventsPanel } from "./components/EventsPanel";
import { MemorySearchPanel } from "./components/MemorySearchPanel";
import { ProposalPanel } from "./components/ProposalPanel";
import { RawDebug } from "./components/RawDebug";
import { StateSummary } from "./components/StateSummary";
import { StatusBar } from "./components/StatusBar";
import { UploadPanel } from "./components/UploadPanel";
import type { ActionItem, AgentState, ApiEvent, HealthState, UploadResponse } from "./types";

type BusyKey = "refresh" | "chat" | "proposal" | null;

export default function App() {
  return (
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          borderRadius: 8,
          colorPrimary: "#2563eb",
          fontFamily:
            "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
        },
        components: {
          Card: {
            headerHeight: 40,
            paddingLG: 14
          },
          Table: {
            cellPaddingBlockSM: 7,
            cellPaddingInlineSM: 8
          }
        }
      }}
    >
      <AntApp>
        <Dashboard />
      </AntApp>
    </ConfigProvider>
  );
}

function Dashboard() {
  const { message } = AntApp.useApp();
  const [health, setHealth] = useState<HealthState | null>(null);
  const [state, setState] = useState<AgentState | null>(null);
  const [events, setEvents] = useState<ApiEvent[]>([]);
  const [sseConnected, setSseConnected] = useState(false);
  const [watchEnabled, setWatchEnabled] = useState<boolean | null>(null);
  const [busy, setBusy] = useState<BusyKey>("refresh");

  const chatMessages = useMemo(
    () => state?.chat?.messages ?? [],
    [state?.chat?.messages]
  );

  const loadSnapshot = useCallback(async () => {
    setBusy((current) => current ?? "refresh");
    try {
      const [nextHealth, nextState] = await Promise.all([fetchHealth(), fetchState()]);
      setHealth(nextHealth);
      setState(nextState);
    } catch (error) {
      showError(message, error);
    } finally {
      setBusy((current) => (current === "refresh" ? null : current));
    }
  }, [message]);

  useEffect(() => {
    void loadSnapshot();
  }, [loadSnapshot]);

  useEffect(() => {
    const source = new EventSource("/api/events");
    const eventTypes = ["hello", "state", "watch_step", "error"];

    source.onopen = () => {
      setSseConnected(true);
    };
    source.onerror = () => {
      setSseConnected(false);
    };

    const listener = (event: Event) => {
      const parsed = parseApiEvent(event as MessageEvent<string>);
      if (!parsed) {
        return;
      }
      setEvents((current) => [parsed, ...current].slice(0, 30));
      if (parsed.type === "hello") {
        setWatchEnabled(Boolean(parsed.payload.watch_enabled));
      }
      if (parsed.type === "state" || parsed.type === "watch_step") {
        void loadSnapshot();
      }
      if (parsed.type === "error") {
        message.warning(String(parsed.payload.message ?? "API event error"));
      }
    };

    eventTypes.forEach((type) => source.addEventListener(type, listener));
    return () => {
      eventTypes.forEach((type) => source.removeEventListener(type, listener));
      source.close();
    };
  }, [loadSnapshot, message]);

  useEffect(() => {
    if (sseConnected) {
      return undefined;
    }
    const poller = window.setInterval(() => {
      void loadSnapshot();
    }, 5000);
    return () => window.clearInterval(poller);
  }, [loadSnapshot, sseConnected]);

  async function handleChat(text: string) {
    setBusy("chat");
    try {
      const response = await sendChat(text);
      setState(response.state);
    } catch (error) {
      showError(message, error);
    } finally {
      setBusy(null);
    }
  }

  async function handleTask(task: string) {
    setBusy("proposal");
    try {
      const response = await submitTask(task);
      setState(response.state);
      message.success(response.message);
    } catch (error) {
      showError(message, error);
    } finally {
      setBusy(null);
    }
  }

  async function handleAction(action: ActionItem) {
    setBusy("proposal");
    try {
      const response = await proposeAction(action);
      setState(response.state);
      message.success(response.message);
    } catch (error) {
      showError(message, error);
    } finally {
      setBusy(null);
    }
  }

  function handleUploaded(nextState: AgentState, response: UploadResponse) {
    setState(nextState);
    message.success(`${response.filename} uploaded`);
  }

  return (
    <Layout className="app-shell">
      <Layout.Header className="app-header">
        <StatusBar
          health={health}
          state={state}
          sseConnected={sseConnected}
          watchEnabled={watchEnabled}
          loading={busy === "refresh"}
          onRefresh={() => void loadSnapshot()}
        />
      </Layout.Header>
      <Layout.Content className="app-content">
        <div className="dashboard-grid">
          <div className="main-column">
            <ActionBoard actions={state?.actions} />
            <ChatPanel messages={chatMessages} loading={busy === "chat"} onSend={handleChat} />
          </div>
          <div className="side-column">
            <StateSummary state={state} />
          </div>
          <div className="tool-column">
            <ProposalPanel
              state={state}
              loading={busy === "proposal"}
              onSubmitTask={handleTask}
              onProposeAction={handleAction}
            />
            <UploadPanel onUploaded={handleUploaded} onError={(error) => showError(message, error)} />
            <MemorySearchPanel onError={(error) => showError(message, error)} />
            <EventsPanel events={events} />
            <RawDebug state={state} />
          </div>
        </div>
      </Layout.Content>
    </Layout>
  );
}

function parseApiEvent(event: MessageEvent<string>): ApiEvent | null {
  try {
    return JSON.parse(event.data) as ApiEvent;
  } catch {
    return null;
  }
}

function showError(messageApi: ReturnType<typeof AntApp.useApp>["message"], error: unknown) {
  const text = error instanceof Error ? error.message : String(error);
  messageApi.error(text);
}
