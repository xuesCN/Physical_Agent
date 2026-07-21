import { FormOutlined, LeftOutlined, RightOutlined } from "@ant-design/icons";
import { Alert, App as AntApp, Button, ConfigProvider, Drawer, Layout, Spin, Tour, theme } from "antd";
import {
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore
} from "react";
import {
  abortChatStream,
  approveAction,
  fetchHealth,
  fetchConfig,
  fetchState,
  initializeProject,
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
import { RawDebug } from "./components/RawDebug";
import { RobotsPanel } from "./components/RobotsPanel";
import { SidebarNav } from "./components/SidebarNav";
import { StateOverviewPanel } from "./components/StateOverviewPanel";
import { StatusBar } from "./components/StatusBar";
import {
  LANGUAGE_STORAGE_KEY,
  THEME_STORAGE_KEY,
  TOUR_STORAGE_KEY,
  antdLocale,
  messages,
  resolveInitialLanguage,
  resolveInitialTheme
} from "./locales";
import { MessagesProvider } from "./locales/context";
import type { Language, Messages, ThemeMode } from "./locales";
import { PAGE_KEYS, usePageNavigation } from "./navigation";
import type { PageKey } from "./navigation";
import type {
  ActionItem,
  AgentState,
  ApiEvent,
  ChatMessage,
  ConfigResponse,
  ExecutorProjection,
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
const SettingsPanel = lazy(() =>
  import("./components/SettingsPanel").then((m) => ({ default: m.SettingsPanel }))
);
const ConfigPanel = lazy(() =>
  import("./components/ConfigPanel").then((m) => ({ default: m.ConfigPanel }))
);

type BusyKey = "refresh" | "initialize" | "chat" | "proposal" | null;
type ProposalPagePreferences = Partial<Record<PageKey, boolean>>;

const PROPOSAL_PAGES_STORAGE_KEY = "physical-agent-proposal-pages:v1";
const COMPACT_PROPOSAL_QUERY = "(max-width: 1080px)";

export default function App() {
  const [language, setLanguage] = useState<Language>(() => resolveInitialLanguage());
  const [themeMode, setThemeMode] = useState<ThemeMode>(() => resolveInitialTheme());
  const labels = messages[language];

  useEffect(() => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
    document.body.dataset.locale = language;
  }, [language]);

  useEffect(() => {
    localStorage.setItem(THEME_STORAGE_KEY, themeMode);
    document.body.dataset.theme = themeMode;
    document.body.dataset.themeMode = themeMode;
  }, [themeMode]);

  return (
    <ConfigProvider
      locale={antdLocale(language)}
      theme={{
        algorithm: themeMode === "dark" ? theme.darkAlgorithm : theme.defaultAlgorithm,
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
      <MessagesProvider value={labels}>
        <AntApp>
          <Dashboard
            labels={labels}
            language={language}
            themeMode={themeMode}
            onLanguageChange={setLanguage}
            onThemeChange={setThemeMode}
          />
        </AntApp>
      </MessagesProvider>
    </ConfigProvider>
  );
}

interface DashboardProps {
  labels: Messages;
  language: Language;
  themeMode: ThemeMode;
  onLanguageChange: (language: Language) => void;
  onThemeChange: (mode: ThemeMode) => void;
}

function Dashboard({
  labels,
  language,
  themeMode,
  onLanguageChange,
  onThemeChange
}: DashboardProps) {
  const { message } = AntApp.useApp();
  const [health, setHealth] = useState<HealthState | null>(null);
  const [state, setState] = useState<AgentState | null>(null);
  const [events, setEvents] = useState<ApiEvent[]>([]);
  const [sseConnected, setSseConnected] = useState(false);
  const [executor, setExecutor] = useState<ExecutorProjection | null>(null);
  const [configResponse, setConfigResponse] = useState<ConfigResponse | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [configLoading, setConfigLoading] = useState(false);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [streamMessages, setStreamMessages] = useState<ChatMessage[] | null>(null);
  const [chatStreamError, setChatStreamError] = useState<string | null>(null);
  const [busy, setBusy] = useState<BusyKey>("refresh");
  const [activePage, navigatePage] = usePageNavigation();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [proposalPages, setProposalPages] = useState<ProposalPagePreferences>(
    readProposalPagePreferences
  );
  const [tourOpen, setTourOpen] = useState(() => localStorage.getItem(TOUR_STORAGE_KEY) !== "1");
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
  const compactProposalLayout = useCompactProposalLayout();
  const proposalExpanded = proposalPages[activePage] ?? activePage === "actions";
  const compactApprovalPriority =
    compactProposalLayout &&
    activePage === "actions" &&
    (state?.actions?.pending ?? []).some((action) => action.metadata?.approval?.required);
  const visibleProposalExpanded = proposalExpanded && !compactApprovalPriority;

  const setActiveProposalExpanded = useCallback(
    (expanded: boolean) => {
      setProposalPages((current) => {
        const next = { ...current, [activePage]: expanded };
        writeProposalPagePreferences(next);
        return next;
      });
    },
    [activePage]
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
      setExecutor(nextState.executor ?? nextHealth.executor ?? null);
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

  const loadConfiguration = useCallback(async () => {
    setConfigLoading(true);
    try {
      setConfigResponse(await fetchConfig());
      setConfigError(null);
    } catch (error) {
      setConfigError(error instanceof Error ? error.message : String(error));
    } finally {
      setConfigLoading(false);
    }
  }, []);

  useEffect(() => {
    // Starts alongside the health/state snapshot request; Robots can therefore
    // render YAML configuration even when no executor has published capabilities.
    void loadConfiguration();
  }, [loadConfiguration]);

  useEffect(() => {
    const source = new EventSource("/api/events");
    const eventTypes = ["hello", "executor", "state", "watch_step", "error"];

    source.onopen = () => {
      setSseConnected(true);
      chatSseDisconnectNotifiedRef.current = false;
    };
    source.onerror = () => {
      setSseConnected(false);
      if (busyRef.current === "chat" && !chatSseDisconnectNotifiedRef.current) {
        chatSseDisconnectNotifiedRef.current = true;
        message.error(labels.chat.sseDisconnected);
      }
    };

    const listener = (event: Event) => {
      const parsed = parseApiEvent(event as MessageEvent<string>);
      if (!parsed) {
        return;
      }
      if (parsed.type !== "executor") {
        setEvents((current) => [parsed, ...current].slice(0, 30));
      }
      const nextExecutor = executorFromEventPayload(parsed.payload);
      if (nextExecutor) {
        setExecutor(nextExecutor);
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
        void loadSnapshot();
      }
    };

    eventTypes.forEach((type) => source.addEventListener(type, listener));
    return () => {
      eventTypes.forEach((type) => source.removeEventListener(type, listener));
      source.close();
    };
  }, [labels.chat.sseDisconnected, loadSnapshot, message]);

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
    let reasoningSummary = "";

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
          if (event.type === "thought") {
            streamStarted = true;
            reasoningSummary += String(payload.delta ?? "");
            setStreamMessages((current) =>
              updateStreamingAssistant(current, assistantKey, assistantContent, {
                stream_status: "streaming",
                reasoning_summary: reasoningSummary
              })
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
                  String(payload.reply ?? assistantContent),
                  {
                    stream_status: "completed",
                    agent_output: payload.agent_output ?? null,
                    plan: payload.plan ?? null
                  }
                )
              );
            }
            return;
          }
          if (event.type === "aborted") {
            streamFinished = true;
            setChatStreamError(labels.chat.stopped);
            if (isAgentState(payload.state)) {
              setState(payload.state);
              setStreamMessages(null);
            }
            return;
          }
          if (event.type === "error") {
            streamFinished = true;
            const text = String(payload.message ?? labels.chat.streamFailed);
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
        setChatStreamError(labels.chat.endedEarly);
      }
    } catch (error) {
      if (isAbortError(error)) {
        setChatStreamError(labels.chat.stopped);
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

  async function handleInitialize() {
    setBusy("initialize");
    try {
      const response = await initializeProject();
      setState(response.state);
      setExecutor(response.state.executor ?? null);
      await Promise.all([loadSnapshot(), loadConfiguration()]);
      message.success(response.message || labels.initialization.success);
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
    setActiveProposalExpanded(true);
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
    void loadConfiguration();
  }

  function handleOpenAction(actionId: string) {
    navigatePage("actions");
    if (actionId) {
      message.info(`Opened Actions for ${actionId}`);
    }
  }

  return (
    <Layout className="app-shell" data-testid="dashboard-shell">
      <SidebarNav
        activePage={activePage}
        collapsed={sidebarCollapsed}
        labels={labels.nav}
        onChange={navigatePage}
        onCollapse={setSidebarCollapsed}
      />
      <Layout className="workspace-layout">
        <Layout.Header className="app-header">
          <StatusBar
            health={health}
            state={state}
            sseConnected={sseConnected}
            executor={executor}
            loading={busy === "refresh"}
            activePageLabel={labels.nav[activePage]}
            labels={labels}
            onRefresh={() => void loadSnapshot()}
            proposalDisabled={compactApprovalPriority}
            onOpenInspector={() => setActiveProposalExpanded(true)}
          />
        </Layout.Header>
        <Layout.Content className="app-content">
          <div
            className={`workspace-frame ${
              visibleProposalExpanded ? "proposal-expanded" : "proposal-collapsed"
            }`}
          >
            <main className="workspace-main" data-testid={`page-${activePage}`}>
              <WorkspaceNotice
                error={snapshotError}
                loading={busy === "refresh"}
                health={health}
                state={state}
                initializing={busy === "initialize"}
                labels={labels}
                onInitialize={() => void handleInitialize()}
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
                  configResponse,
                  configError,
                  configLoading,
                  onRefreshConfig: () => void loadConfiguration(),
                  onOpenAction: handleOpenAction,
                  labels,
                  language,
                  themeMode,
                  onLanguageChange,
                  onThemeChange,
                  onShowTour: () => setTourOpen(true),
                  onError: (error) => showError(message, error)
                })}
              </Suspense>
            </main>
            <aside
              className={`inspector-column ${
                visibleProposalExpanded
                  ? "inspector-column-expanded"
                  : "inspector-column-collapsed"
              }`}
            >
              <Button
                className="proposal-panel-toggle"
                data-testid="proposal-panel-toggle"
                type="text"
                aria-label={
                  visibleProposalExpanded ? labels.drawer.collapse : labels.drawer.open
                }
                icon={visibleProposalExpanded ? <RightOutlined /> : <LeftOutlined />}
                onClick={() => setActiveProposalExpanded(!proposalExpanded)}
              >
                {!visibleProposalExpanded && (
                  <span className="proposal-rail-label">
                    <FormOutlined />
                    <span className="proposal-rail-text" data-testid="proposal-rail-text">
                      {labels.app.propose}
                    </span>
                  </span>
                )}
              </Button>
              {!compactProposalLayout && visibleProposalExpanded && (
                <ProposalPanel
                  state={state}
                  loading={busy === "proposal"}
                  onSubmitTask={handleTask}
                  onProposeAction={handleAction}
                  prefillAction={prefillAction}
                  prefillVersion={prefillVersion}
                />
              )}
            </aside>
          </div>
        </Layout.Content>
      </Layout>
      <Drawer
        title={labels.drawer.title}
        className="proposal-drawer"
        width={420}
        placement="right"
        open={compactProposalLayout && visibleProposalExpanded}
        onClose={() => setActiveProposalExpanded(false)}
      >
        {compactProposalLayout && visibleProposalExpanded && (
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
      <Tour
        open={tourOpen}
        onClose={() => {
          localStorage.setItem(TOUR_STORAGE_KEY, "1");
          setTourOpen(false);
        }}
        steps={buildTourSteps(labels)}
        mask={false}
        rootClassName="onboarding-tour"
      />
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
  configResponse: ConfigResponse | null;
  configError: string | null;
  configLoading: boolean;
  onRefreshConfig: () => void;
  onOpenAction: (actionId: string) => void;
  labels: Messages;
  language: Language;
  themeMode: ThemeMode;
  onLanguageChange: (language: Language) => void;
  onThemeChange: (mode: ThemeMode) => void;
  onShowTour: () => void;
  onError: (error: Error) => void;
}

interface WorkspaceNoticeProps {
  error: string | null;
  loading: boolean;
  health: HealthState | null;
  state: AgentState | null;
  initializing: boolean;
  labels: Messages;
  onInitialize: () => void;
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

function WorkspaceNotice({
  error,
  loading,
  health,
  state,
  initializing,
  labels,
  onInitialize
}: WorkspaceNoticeProps) {
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
        message={labels.initialization.title}
        description={snapshot.message || labels.initialization.description}
        action={
          <Button
            data-testid="initialize-project-button"
            type="primary"
            size="small"
            loading={initializing}
            onClick={onInitialize}
          >
            {labels.initialization.action}
          </Button>
        }
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
  configResponse,
  configError,
  configLoading,
  onRefreshConfig,
  onOpenAction,
  labels,
  language,
  themeMode,
  onLanguageChange,
  onThemeChange,
  onShowTour,
  onError
}: RenderPageProps) {
  if (activePage === "chat") {
    return (
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
    );
  }

  if (activePage === "actions") {
    return (
      <div className="page-stack">
        <ActionBoard
          actions={state?.actions}
          loading={busy === "proposal"}
          onApprove={onApproveAction}
          onReject={onRejectAction}
        />
        <ContextTabs state={state} only="feedback" onOpenAction={onOpenAction} />
      </div>
    );
  }

  if (activePage === "state") {
    return (
      <div className="page-stack">
        <ContextTabs state={state} defaultActiveKey="world" onOpenAction={onOpenAction} />
      </div>
    );
  }

  if (activePage === "hardware") {
    return (
      <div className="page-stack">
        <HardwarePanel
          onStateChange={onStateChange}
          onError={onError}
          onRobotRegistered={onRobotRegistered}
        />
        <ConfigPanel
          response={configResponse}
          error={configError}
          loading={configLoading}
          onRefresh={onRefreshConfig}
        />
        <RobotsPanel state={state} config={configResponse} />
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
        <SettingsPanel
          health={health}
          state={state}
          labels={labels}
          language={language}
          themeMode={themeMode}
          onLanguageChange={onLanguageChange}
          onThemeChange={onThemeChange}
          onShowTour={onShowTour}
          onWorkspaceReset={onWorkspaceReset}
        />
        <RawDebug state={state} />
      </div>
    );
  }

  return (
    <div className="page-stack overview-grid">
      <StateOverviewPanel state={state} health={health} />
      <RobotsPanel state={state} config={configResponse} />
    </div>
  );
}

function readProposalPagePreferences(): ProposalPagePreferences {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    const raw = localStorage.getItem(PROPOSAL_PAGES_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {};
    }
    const source = parsed as Record<string, unknown>;
    return PAGE_KEYS.reduce<ProposalPagePreferences>((preferences, page) => {
      if (typeof source[page] === "boolean") {
        preferences[page] = source[page];
      }
      return preferences;
    }, {});
  } catch {
    return {};
  }
}

function writeProposalPagePreferences(preferences: ProposalPagePreferences) {
  try {
    localStorage.setItem(PROPOSAL_PAGES_STORAGE_KEY, JSON.stringify(preferences));
  } catch {
    // UI preferences are best-effort when storage is unavailable.
  }
}

function subscribeCompactProposalLayout(listener: () => void) {
  const media = window.matchMedia(COMPACT_PROPOSAL_QUERY);
  const handleChange = () => listener();
  media.addEventListener("change", handleChange);
  return () => media.removeEventListener("change", handleChange);
}

function compactProposalLayoutSnapshot() {
  return window.matchMedia(COMPACT_PROPOSAL_QUERY).matches;
}

function useCompactProposalLayout() {
  return useSyncExternalStore(
    subscribeCompactProposalLayout,
    compactProposalLayoutSnapshot,
    () => false
  );
}

function buildTourSteps(labels: Messages) {
  return [
    {
      title: labels.tour.setupTitle,
      description: labels.tour.setupDescription,
      target: () => queryTourTarget('[data-testid="nav-settings"]')
    },
    {
      title: labels.tour.actionsTitle,
      description: labels.tour.actionsDescription,
      target: () => queryTourTarget('[data-testid="nav-actions"]')
    },
    {
      title: labels.tour.chatTitle,
      description: labels.tour.chatDescription,
      target: () => queryTourTarget('[data-testid="nav-chat"]')
    }
  ];
}

function queryTourTarget(selector: string): HTMLElement {
  return (document.querySelector(selector) as HTMLElement | null) ?? document.body;
}

function parseApiEvent(event: MessageEvent<string>): ApiEvent | null {
  try {
    return JSON.parse(event.data) as ApiEvent;
  } catch {
    return null;
  }
}

function executorFromEventPayload(payload: Record<string, unknown>): ExecutorProjection | null {
  const direct = asExecutorProjection(payload.executor);
  if (direct) {
    return direct;
  }

  // Compatibility only: watch_enabled is configuration, not evidence that an
  // executor owns the workspace lease or is running.
  if (typeof payload.watch_enabled === "boolean") {
    return {
      mode: "none",
      status: "unknown",
      embedded_enabled: payload.watch_enabled,
      legacy_watch_configured: payload.watch_enabled
    };
  }
  return null;
}

function asExecutorProjection(value: unknown): ExecutorProjection | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const candidate = value as Record<string, unknown>;
  if (!["waiting_for_init", "embedded", "external", "none"].includes(String(candidate.mode))) {
    return null;
  }
  return candidate as unknown as ExecutorProjection;
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
  content: string,
  metadata: Record<string, unknown> = { stream_status: "streaming" }
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
        ...metadata
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
