import { App as AntApp, ConfigProvider, Drawer, Layout, theme } from "antd";
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
import { ContextTabs } from "./components/ContextTabs";
import { EventsPanel } from "./components/EventsPanel";
import { MemorySearchPanel } from "./components/MemorySearchPanel";
import { ProposalPanel } from "./components/ProposalPanel";
import { RawDebug } from "./components/RawDebug";
import { RobotsPanel } from "./components/RobotsPanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { PAGE_LABELS, SidebarNav } from "./components/SidebarNav";
import type { PageKey } from "./components/SidebarNav";
import { StatusBar } from "./components/StatusBar";
import { UploadPanel } from "./components/UploadPanel";
import type {
  ActionItem,
  AgentState,
  ApiEvent,
  ChatMessage,
  HealthState,
  UploadResponse
} from "./types";

type BusyKey = "refresh" | "chat" | "proposal" | null;

export default function App() {
  return (
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          borderRadius: 6,
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
  const [activePage, setActivePage] = useState<PageKey>("overview");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);

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
    <Layout className="app-shell" data-testid="dashboard-shell">
      <SidebarNav
        activePage={activePage}
        collapsed={sidebarCollapsed}
        onChange={setActivePage}
        onCollapse={setSidebarCollapsed}
      />
      <Layout className="workspace-layout">
        <Layout.Header className="app-header">
          <StatusBar
            health={health}
            state={state}
            sseConnected={sseConnected}
            watchEnabled={watchEnabled}
            loading={busy === "refresh"}
            activePageLabel={PAGE_LABELS[activePage]}
            onRefresh={() => void loadSnapshot()}
            onOpenInspector={() => setInspectorOpen(true)}
          />
        </Layout.Header>
        <Layout.Content className="app-content">
          <div className="workspace-frame">
            <main className="workspace-main" data-testid={`page-${activePage}`}>
              {renderPageContent({
                activePage,
                state,
                health,
                events,
                chatMessages,
                busy,
                onChat: handleChat,
                onUploaded: handleUploaded,
                onError: (error) => showError(message, error)
              })}
            </main>
            <aside className="inspector-column">
              <ProposalPanel
                state={state}
                loading={busy === "proposal"}
                onSubmitTask={handleTask}
                onProposeAction={handleAction}
              />
            </aside>
          </div>
        </Layout.Content>
      </Layout>
      <Drawer
        title="Task / Action Proposal"
        className="proposal-drawer"
        width={420}
        placement="right"
        open={inspectorOpen}
        onClose={() => setInspectorOpen(false)}
      >
        {inspectorOpen && (
          <ProposalPanel
            state={state}
            loading={busy === "proposal"}
            onSubmitTask={handleTask}
            onProposeAction={handleAction}
          />
        )}
      </Drawer>
    </Layout>
  );
}

interface RenderPageProps {
  activePage: PageKey;
  state: AgentState | null;
  health: HealthState | null;
  events: ApiEvent[];
  chatMessages: ChatMessage[];
  busy: BusyKey;
  onChat: (message: string) => Promise<void>;
  onUploaded: (state: AgentState, response: UploadResponse) => void;
  onError: (error: Error) => void;
}

function renderPageContent({
  activePage,
  state,
  health,
  events,
  chatMessages,
  busy,
  onChat,
  onUploaded,
  onError
}: RenderPageProps) {
  if (activePage === "actions") {
    return (
      <div className="page-stack">
        <ActionBoard actions={state?.actions} />
        <ContextTabs state={state} defaultActiveKey="feedback" />
      </div>
    );
  }

  if (activePage === "world") {
    return (
      <div className="page-stack">
        <ContextTabs state={state} defaultActiveKey="world" />
      </div>
    );
  }

  if (activePage === "robots") {
    return <RobotsPanel state={state} />;
  }

  if (activePage === "memory") {
    return (
      <div className="two-panel-page">
        <UploadPanel onUploaded={onUploaded} onError={onError} />
        <MemorySearchPanel onError={onError} />
      </div>
    );
  }

  if (activePage === "safety") {
    return (
      <div className="page-stack">
        <ContextTabs state={state} defaultActiveKey="safety" />
      </div>
    );
  }

  if (activePage === "events") {
    return (
      <div className="two-panel-page events-page">
        <EventsPanel events={events} />
        <RawDebug state={state} />
      </div>
    );
  }

  if (activePage === "settings") {
    return (
      <div className="two-panel-page">
        <SettingsPanel health={health} state={state} />
        <RawDebug state={state} />
      </div>
    );
  }

  return (
    <div className="overview-grid">
      <div className="main-column">
        <ActionBoard actions={state?.actions} />
        <ChatPanel messages={chatMessages} loading={busy === "chat"} onSend={onChat} />
      </div>
      <div className="context-column">
        <ContextTabs state={state} />
        <RobotsPanel state={state} />
      </div>
    </div>
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
