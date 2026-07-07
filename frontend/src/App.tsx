import { Alert, App as AntApp, ConfigProvider, Drawer, Layout, Spin, theme } from "antd";
import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  abortChatStream,
  approveAction,
  fetchHealth,
  fetchState,
  proposeAction,
  rejectAction,
  resetChat,
  sendChat,
  sendChatStream,
  submitTask
} from "./api";
import { ActionBoard } from "./components/ActionBoard";
import { ChatPanel } from "./components/ChatPanel";
import { ContextTabs } from "./components/ContextTabs";
import { ProposalPanel } from "./components/ProposalPanel";
import { RobotsPanel } from "./components/RobotsPanel";
import { PAGE_LABELS, SidebarNav } from "./components/SidebarNav";
import type { PageKey } from "./components/SidebarNav";
import { StatusBar } from "./components/StatusBar";
import type {
  ActionItem,
  AgentState,
  ApiEvent,
  ChatMessage,
  HealthState,
  UploadResponse
} from "./types";

// Secondary-page panels are loaded on demand so their bundles (and the antd
// widgets only they use — Upload/Collapse/List/InputNumber) stay out of the
// initial download. The overview page keeps its panels eager.
const HardwarePanel = lazy(() =>
  import("./components/HardwarePanel").then((m) => ({ default: m.HardwarePanel }))
);
const MemorySearchPanel = lazy(() =>
  import("./components/MemorySearchPanel").then((m) => ({ default: m.MemorySearchPanel }))
);
const UploadPanel = lazy(() =>
  import("./components/UploadPanel").then((m) => ({ default: m.UploadPanel }))
);
const EventsPanel = lazy(() =>
  import("./components/EventsPanel").then((m) => ({ default: m.EventsPanel }))
);
const RawDebug = lazy(() =>
  import("./components/RawDebug").then((m) => ({ default: m.RawDebug }))
);
const SettingsPanel = lazy(() =>
  import("./components/SettingsPanel").then((m) => ({ default: m.SettingsPanel }))
);
const ConfigPanel = lazy(() =>
  import("./components/ConfigPanel").then((m) => ({ default: m.ConfigPanel }))
);

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
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [streamMessages, setStreamMessages] = useState<ChatMessage[] | null>(null);
  const [chatStreamError, setChatStreamError] = useState<string | null>(null);
  const [busy, setBusy] = useState<BusyKey>("refresh");
  const [activePage, setActivePage] = useState<PageKey>("overview");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [configVersion, setConfigVersion] = useState(0);
  const [prefillAction, setPrefillAction] = useState<ActionItem | null>(null);
  const [prefillVersion, setPrefillVersion] = useState(0);
  const busyRef = useRef<BusyKey>("refresh");
  const lastEventSummaryRef = useRef<string | null>(null);
  const chatSseDisconnectNotifiedRef = useRef(false);
  const chatAbortControllerRef = useRef<AbortController | null>(null);
  const chatStreamIdRef = useRef<string | null>(null);

  const chatMessages = useMemo(
    () => streamMessages ?? state?.chat?.messages ?? [],
    [state?.chat?.messages, streamMessages]
  );

  useEffect(() => {
    busyRef.current = busy;
  }, [busy]);

  const loadSnapshot = useCallback(async () => {
    setBusy((current) => current ?? "refresh");
    try {
      const [nextHealth, nextState] = await Promise.all([fetchHealth(), fetchState()]);
      setHealth(nextHealth);
      setState(nextState);
      setSnapshotError(null);
    } catch (error) {
      setSnapshotError(error instanceof Error ? error.message : String(error));
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
      chatSseDisconnectNotifiedRef.current = false;
    };
    source.onerror = () => {
      setSseConnected(false);
      if (busyRef.current === "chat" && !chatSseDisconnectNotifiedRef.current) {
        chatSseDisconnectNotifiedRef.current = true;
        message.error("SSE disconnected while chat was in progress.");
      }
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
        // The watch loop publishes a watch_step every tick (watch.tick_ms,
        // default 500ms) even when nothing ran; skip the snapshot refetch on
        // idle ticks whose state summary matches the last one we saw.
        const summary = JSON.stringify(parsed.payload.state ?? null);
        const idleWatchTick =
          parsed.type === "watch_step" &&
          !Number(parsed.payload.executed ?? 0) &&
          summary === lastEventSummaryRef.current;
        lastEventSummaryRef.current = summary;
        if (!idleWatchTick) {
          void loadSnapshot();
        }
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

  async function handleChat(text: string) {
    setBusy("chat");
    chatSseDisconnectNotifiedRef.current = false;
    setChatStreamError(null);
    const baseMessages = state?.chat?.messages ?? [];
    const assistantKey = `assistant-stream-${Date.now()}`;
    setStreamMessages([
      ...baseMessages,
      localChatMessage("user", text),
      localChatMessage("assistant", "", {
        local_key: assistantKey,
        stream_status: "streaming"
      })
    ]);

    const abortController = new AbortController();
    const streamId = `chat-${Date.now()}`;
    chatAbortControllerRef.current = abortController;
    chatStreamIdRef.current = streamId;
    let streamStarted = false;
    let streamFinished = false;
    let assistantContent = "";

    try {
      await sendChatStream(text, {
        streamId,
        requestId: streamId,
        signal: abortController.signal,
        onEvent: (event) => {
          const payload = event.payload ?? {};
          if (event.type === "start") {
            streamStarted = true;
            return;
          }
          if (event.type === "delta") {
            streamStarted = true;
            assistantContent += String(payload.delta ?? "");
            setStreamMessages((current) =>
              updateStreamingAssistant(current, assistantKey, assistantContent)
            );
            return;
          }
          if (event.type === "done") {
            streamFinished = true;
            if (isAgentState(payload.state)) {
              setState(payload.state);
              setStreamMessages(null);
            } else {
              setStreamMessages((current) =>
                updateStreamingAssistant(
                  current,
                  assistantKey,
                  String(payload.reply ?? assistantContent)
                )
              );
            }
            return;
          }
          if (event.type === "aborted") {
            streamFinished = true;
            setChatStreamError("Chat stream stopped.");
            if (isAgentState(payload.state)) {
              setState(payload.state);
              setStreamMessages(null);
            }
            return;
          }
          if (event.type === "error") {
            streamFinished = true;
            const text = String(payload.message ?? "Streaming chat failed.");
            setChatStreamError(text);
            if (isAgentState(payload.state)) {
              setState(payload.state);
              setStreamMessages(null);
              return;
            }
            if (!assistantContent) {
              setStreamMessages((current) =>
                updateStreamingAssistant(current, assistantKey, text)
              );
            }
          }
        }
      });
      if (streamStarted && !streamFinished) {
        setChatStreamError("Chat stream ended before completion.");
      }
    } catch (error) {
      if (isAbortError(error)) {
        setChatStreamError("Chat stream stopped.");
        streamFinished = true;
      } else if (!streamStarted) {
        try {
          const response = await sendChat(text);
          setState(response.state);
          setStreamMessages(null);
        } catch (fallbackError) {
          showError(message, fallbackError);
          setChatStreamError(fallbackError instanceof Error ? fallbackError.message : String(fallbackError));
        }
      } else {
        const text = error instanceof Error ? error.message : String(error);
        setChatStreamError(text);
        showError(message, error);
      }
    } finally {
      chatAbortControllerRef.current = null;
      chatStreamIdRef.current = null;
      setBusy(null);
    }
  }

  function handleStopChat() {
    const streamId = chatStreamIdRef.current;
    if (streamId) {
      void abortChatStream(streamId).catch(() => undefined);
    }
    chatAbortControllerRef.current?.abort();
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
      setPrefillAction(null);
      message.success(response.message);
    } catch (error) {
      showError(message, error);
    } finally {
      setBusy(null);
    }
  }

  async function handleApproveAction(actionId: string) {
    setBusy("proposal");
    try {
      const response = await approveAction(actionId, "Approved from Actions board.");
      setState(response.state);
      message.success(response.message);
    } catch (error) {
      showError(message, error);
    } finally {
      setBusy(null);
    }
  }

  async function handleRejectAction(actionId: string, reason: string) {
    setBusy("proposal");
    try {
      const response = await rejectAction(actionId, reason);
      setState(response.state);
      message.success(response.message);
    } catch (error) {
      showError(message, error);
    } finally {
      setBusy(null);
    }
  }

  function handleEditDraft(action: ActionItem) {
    setPrefillAction(action);
    setPrefillVersion((current) => current + 1);
    setInspectorOpen(true);
  }

  async function handleResetChat() {
    setBusy("chat");
    try {
      const response = await resetChat();
      setStreamMessages(null);
      setChatStreamError(null);
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

  function handleStateChange(nextState: AgentState) {
    setState(nextState);
  }

  function handleWorkspaceReset(nextState: AgentState, text: string) {
    setStreamMessages(null);
    setChatStreamError(null);
    setState(nextState);
    message.success(text);
  }

  function handleRobotRegistered() {
    setConfigVersion((current) => current + 1);
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
              <WorkspaceNotice
                error={snapshotError}
                loading={busy === "refresh"}
                health={health}
                state={state}
              />
              <Suspense fallback={<PageFallback />}>
                {renderPageContent({
                  activePage,
                  state,
                  health,
                  events,
                  chatMessages,
                  busy,
                  onChat: handleChat,
                  onStopChat: handleStopChat,
                  onResetChat: handleResetChat,
                  onProposeAction: handleAction,
                  onEditDraft: handleEditDraft,
                  onApproveAction: handleApproveAction,
                  onRejectAction: handleRejectAction,
                  chatError: chatStreamError,
                  onUploaded: handleUploaded,
                  onStateChange: handleStateChange,
                  onWorkspaceReset: handleWorkspaceReset,
                  onRobotRegistered: handleRobotRegistered,
                  configVersion,
                  onError: (error) => showError(message, error)
                })}
              </Suspense>
            </main>
            <aside className="inspector-column">
              <ProposalPanel
                state={state}
                loading={busy === "proposal"}
                onSubmitTask={handleTask}
                onProposeAction={handleAction}
                prefillAction={prefillAction}
                prefillVersion={prefillVersion}
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
            prefillAction={prefillAction}
            prefillVersion={prefillVersion}
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
  onStopChat: () => void;
  onResetChat: () => Promise<void>;
  onProposeAction: (action: ActionItem) => Promise<void>;
  onEditDraft: (action: ActionItem) => void;
  onApproveAction: (actionId: string) => Promise<void>;
  onRejectAction: (actionId: string, reason: string) => Promise<void>;
  chatError: string | null;
  onUploaded: (state: AgentState, response: UploadResponse) => void;
  onStateChange: (state: AgentState) => void;
  onWorkspaceReset: (state: AgentState, message: string) => void;
  onRobotRegistered: () => void;
  configVersion: number;
  onError: (error: Error) => void;
}

interface WorkspaceNoticeProps {
  error: string | null;
  loading: boolean;
  health: HealthState | null;
  state: AgentState | null;
}

function PageFallback() {
  return (
    <div
      role="status"
      aria-live="polite"
      style={{ display: "flex", justifyContent: "center", padding: "48px 0" }}
    >
      <Spin />
    </div>
  );
}

function WorkspaceNotice({ error, loading, health, state }: WorkspaceNoticeProps) {
  if (error) {
    return (
      <Alert
        className="workspace-notice"
        data-testid="workspace-notice"
        type="error"
        showIcon
        message="API snapshot unavailable"
        description={error}
      />
    );
  }

  if (loading && !health && !state) {
    return (
      <Alert
        className="workspace-notice"
        data-testid="workspace-notice"
        type="info"
        showIcon
        message="Loading workspace status"
        description="Connecting to the Physical Agent API."
      />
    );
  }

  const snapshot = state ?? health;
  if (snapshot && !snapshot.ready) {
    return (
      <Alert
        className="workspace-notice"
        data-testid="workspace-notice"
        type="warning"
        showIcon
        message="Workspace is not ready"
        description={snapshot.message || "Initialize the workspace before proposing work."}
      />
    );
  }

  return null;
}

function renderPageContent({
  activePage,
  state,
  health,
  events,
  chatMessages,
  busy,
  onChat,
  onStopChat,
  onResetChat,
  onProposeAction,
  onEditDraft,
  onApproveAction,
  onRejectAction,
  chatError,
  onUploaded,
  onStateChange,
  onWorkspaceReset,
  onRobotRegistered,
  configVersion,
  onError
}: RenderPageProps) {
  if (activePage === "actions") {
    return (
      <div className="page-stack">
        <ActionBoard
          actions={state?.actions}
          loading={busy === "proposal"}
          onApprove={onApproveAction}
          onReject={onRejectAction}
        />
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

  if (activePage === "hardware") {
    return (
      <div className="page-stack">
        <HardwarePanel
          onStateChange={onStateChange}
          onError={onError}
          onRobotRegistered={onRobotRegistered}
        />
        <ConfigPanel refreshToken={configVersion} />
        <RobotsPanel state={state} />
      </div>
    );
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
        <SettingsPanel health={health} state={state} onWorkspaceReset={onWorkspaceReset} />
        <RawDebug state={state} />
      </div>
    );
  }

  return (
    <div className="overview-grid">
      <div className="main-column">
        <ActionBoard
          actions={state?.actions}
          loading={busy === "proposal"}
          onApprove={onApproveAction}
          onReject={onRejectAction}
        />
        <ChatPanel
          messages={chatMessages}
          loading={busy === "chat"}
          error={chatError}
          onSend={onChat}
          onStop={onStopChat}
          onReset={onResetChat}
          onAddDraft={onProposeAction}
          onEditDraft={onEditDraft}
          actionLoading={busy === "proposal"}
        />
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

function localChatMessage(
  role: ChatMessage["role"],
  content: string,
  metadata: Record<string, unknown> = {}
): ChatMessage {
  return {
    role,
    content,
    created_at: new Date().toISOString(),
    metadata
  };
}

function updateStreamingAssistant(
  messages: ChatMessage[] | null,
  localKey: string,
  content: string
): ChatMessage[] | null {
  if (!messages) {
    return messages;
  }
  return messages.map((item) => {
    if (item.metadata?.local_key !== localKey) {
      return item;
    }
    return {
      ...item,
      content,
      metadata: {
        ...item.metadata,
        stream_status: "streaming"
      }
    };
  });
}

function isAgentState(value: unknown): value is AgentState {
  return Boolean(value && typeof value === "object" && "ready" in value);
}

function isAbortError(error: unknown): boolean {
  return (
    (error instanceof DOMException || error instanceof Error) &&
    error.name === "AbortError"
  );
}
