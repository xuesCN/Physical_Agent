import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, Text, useApp } from "ink";
import { ApiClient } from "./api/client.js";
import { COMMAND_HELP, parseCommand } from "./commands/parser.js";
import { ActionsPanel } from "./components/ActionsPanel.js";
import { ChatPanel } from "./components/ChatPanel.js";
import { CommandInput } from "./components/CommandInput.js";
import { StatusBar } from "./components/StatusBar.js";
import type { AgentState, ApiEvent, ChatMessage, HealthState, RuntimeStatus, WatchStatus } from "./types.js";

export interface TuiClient {
  health(): Promise<HealthState>;
  state(): Promise<AgentState>;
  submitTask(task: string): Promise<{ ok: boolean; message: string; state: AgentState }>;
  approveAction(actionId: string): Promise<{ ok: boolean; message: string; state: AgentState }>;
  rejectAction(actionId: string, reason: string): Promise<{ ok: boolean; message: string; state: AgentState }>;
  resetWorkspace(confirm: string): Promise<{ ok: boolean; message: string; state: AgentState }>;
  sendChatStream(message: string, onEvent: (event: ApiEvent) => void, signal?: AbortSignal): Promise<void>;
  events(onEvent: (event: ApiEvent) => void, signal?: AbortSignal): Promise<void>;
}

interface AppProps {
  apiBase: string;
  pollIntervalMs: number;
  useSse: boolean;
  client?: TuiClient;
}

export function App({ apiBase, pollIntervalMs, useSse, client: injectedClient }: AppProps) {
  const client = useMemo<TuiClient>(() => injectedClient ?? new ApiClient(apiBase), [apiBase, injectedClient]);
  const { exit } = useApp();
  const [health, setHealth] = useState<HealthState | null>(null);
  const [state, setState] = useState<AgentState | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [mode, setMode] = useState<RuntimeStatus["mode"]>(useSse ? "sse" : "polling");
  const [connected, setConnected] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>("Type /help for commands. Enter text to chat.");
  const [error, setError] = useState<string | null>(null);
  const [watchStatus, setWatchStatus] = useState<WatchStatus>("unknown");
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [nextHealth, nextState] = await Promise.all([client.health(), client.state()]);
      setHealth(nextHealth);
      setState(nextState);
      setConnected(true);
      setError(null);
      setLastRefresh(new Date().toLocaleTimeString());
    } catch (err) {
      setConnected(false);
      setError(readError(err));
    }
  }, [client]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
    }
    if (!useSse || mode !== "sse") {
      pollingRef.current = setInterval(() => void refresh(), pollIntervalMs);
    }
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, [mode, pollIntervalMs, refresh, useSse]);

  useEffect(() => {
    if (!useSse) {
      setMode("polling");
      return;
    }
    const controller = new AbortController();
    const enterPollingFallback = (reason: string) => {
      setMode("degraded");
      setConnected(false);
      setError(reason);
    };
    client
      .events((event) => {
        setConnected(true);
        setMode("sse");
        const nextWatchStatus = watchStatusFromEvent(event);
        if (nextWatchStatus) {
          setWatchStatus(nextWatchStatus);
        }
        const applyResult = applyEvent(event, setState);
        if (applyResult === "summary") {
          void refresh();
        }
        setLastRefresh(new Date().toLocaleTimeString());
      }, controller.signal)
      .then(() => {
        if (shouldFallbackAfterSseClose(controller.signal)) {
          enterPollingFallback(sseClosedFallbackMessage());
        }
      })
      .catch((err) => {
        if (shouldFallbackAfterSseClose(controller.signal)) {
          enterPollingFallback(sseErrorFallbackMessage(err));
        }
      });
    return () => controller.abort();
  }, [client, refresh, useSse]);

  const status: RuntimeStatus = {
    apiBase,
    connected,
    mode,
    lastRefresh,
    backend: state?.backend ?? health?.backend ?? "-",
    watch: watchStatus,
    message: state?.message ?? health?.message ?? (error ? "API unavailable" : "Loading")
  };

  async function handleSubmit(value: string) {
    const command = parseCommand(value);
    setInput("");
    setNotice(null);
    if (command.type === "unknown") {
      setNotice(command.message);
      return;
    }
    if (command.type === "help") {
      setNotice(COMMAND_HELP);
      return;
    }
    if (command.type === "quit") {
      exit();
      return;
    }
    setBusy(true);
    try {
      if (command.type === "refresh") {
        await refresh();
        setNotice("Snapshot refreshed.");
      } else if (command.type === "task") {
        const response = await client.submitTask(command.text);
        setState(response.state);
        setNotice(response.message);
      } else if (command.type === "approve") {
        const response = await client.approveAction(command.actionId);
        setState(response.state);
        setNotice(response.message);
      } else if (command.type === "reject") {
        const response = await client.rejectAction(command.actionId, command.reason);
        setState(response.state);
        setNotice(response.message);
      } else if (command.type === "reset") {
        const response = await client.resetWorkspace(command.confirm);
        setState(response.state);
        setNotice(response.message);
      } else if (command.type === "chat") {
        await runChat(command.text);
      }
    } catch (err) {
      setNotice(readError(err));
    } finally {
      setBusy(false);
    }
  }

  async function runChat(text: string) {
    await runTuiChatStream(client, text, {
      setStreaming,
      setStreamingText,
      setState,
      setNotice
    });
  }

  const messages: ChatMessage[] = state?.chat?.messages ?? [];

  return (
    <Box flexDirection="column" gap={1}>
      <StatusBar status={status} busy={busy || streaming} />
      <ChatPanel messages={messages} streamingText={streamingText} streaming={streaming} error={error} />
      <ActionsPanel state={state} error={error} />
      {notice ? <Box paddingX={1}><Text color="gray">{notice}</Text></Box> : null}
      <CommandInput value={input} onChange={setInput} onSubmit={handleSubmit} disabled={busy} />
    </Box>
  );
}

export type EventStateApplyResult = "full" | "summary" | "ignored";

export function applyEvent(event: ApiEvent, setState: (state: AgentState) => void): EventStateApplyResult {
  const payload = event.payload ?? {};
  const nestedState = payload.state;
  if (isFullAgentState(nestedState)) {
    setState(nestedState);
    return "full";
  }
  if (isAgentStateSummary(nestedState)) {
    return "summary";
  }
  return "ignored";
}

export function watchStatusFromEvent(event: ApiEvent): WatchStatus | null {
  const value = event.payload?.watch_enabled;
  if (value === true) {
    return "enabled";
  }
  if (value === false) {
    return "disabled";
  }
  return null;
}

export function shouldFallbackAfterSseClose(signal: AbortSignal): boolean {
  return !signal.aborted;
}

export function sseClosedFallbackMessage(): string {
  return "SSE stream closed; using polling fallback.";
}

export function sseErrorFallbackMessage(error: unknown): string {
  return `SSE disconnected; polling fallback active. ${readError(error)}`;
}

interface ChatStreamHandlers {
  setStreaming: (value: boolean) => void;
  setStreamingText: (value: string) => void;
  setState: (state: AgentState) => void;
  setNotice: (message: string) => void;
}

export async function runTuiChatStream(
  client: Pick<TuiClient, "sendChatStream">,
  text: string,
  handlers: ChatStreamHandlers
): Promise<void> {
  handlers.setStreaming(true);
  handlers.setStreamingText("");
  let content = "";
  try {
    await client.sendChatStream(text, (event) => {
      const payload = event.payload ?? {};
      if (event.type === "delta") {
        content += String(payload.delta ?? "");
        handlers.setStreamingText(content);
      }
      if (event.type === "done") {
        if (isFullAgentState(payload.state)) {
          handlers.setState(payload.state);
          handlers.setStreamingText("");
        } else {
          handlers.setStreamingText(String(payload.reply ?? content));
        }
      }
      if (event.type === "error") {
        handlers.setNotice(String(payload.message ?? "Streaming chat failed."));
      }
    });
  } catch (err) {
    if (!isAbortError(err)) {
      handlers.setNotice(`Streaming chat failed. ${readError(err)}`);
    }
  } finally {
    handlers.setStreaming(false);
  }
}

function isFullAgentState(value: unknown): value is AgentState {
  return isRecord(value) && "ready" in value && (
    "actions" in value ||
    "chat" in value ||
    "world" in value ||
    "capabilities" in value ||
    "feedback" in value
  );
}

function isAgentStateSummary(value: unknown): boolean {
  return isRecord(value) && "ready" in value && (
    "chat_messages" in value ||
    "pending_actions" in value ||
    "completed_count" in value ||
    "cancelled_count" in value ||
    "memory_notes" in value
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object");
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException
    ? error.name === "AbortError"
    : error instanceof Error && error.name === "AbortError";
}

function readError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
