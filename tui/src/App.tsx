import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, Text, useApp } from "ink";
import { ApiClient } from "./api/client.js";
import { COMMAND_HELP, parseCommand } from "./commands/parser.js";
import { ActionsPanel } from "./components/ActionsPanel.js";
import { ChatPanel } from "./components/ChatPanel.js";
import { CommandInput } from "./components/CommandInput.js";
import { StatusBar } from "./components/StatusBar.js";
import type { AgentState, ApiEvent, ChatMessage, HealthState, RuntimeStatus } from "./types.js";

interface AppProps {
  apiBase: string;
  pollIntervalMs: number;
  useSse: boolean;
}

export function App({ apiBase, pollIntervalMs, useSse }: AppProps) {
  const client = useMemo(() => new ApiClient(apiBase), [apiBase]);
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
  const [notice, setNotice] = useState<string | null>(COMMAND_HELP);
  const [error, setError] = useState<string | null>(null);
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
    client
      .events((event) => {
        setConnected(true);
        setMode("sse");
        applyEvent(event, setState);
        setLastRefresh(new Date().toLocaleTimeString());
      }, controller.signal)
      .catch((err) => {
        if (!controller.signal.aborted) {
          setMode("degraded");
          setConnected(false);
          setError(`SSE disconnected; polling fallback active. ${readError(err)}`);
        }
      });
    return () => controller.abort();
  }, [client, useSse]);

  const status: RuntimeStatus = {
    apiBase,
    connected,
    mode,
    lastRefresh,
    backend: state?.backend ?? health?.backend ?? "-",
    watch: state ? "snapshot" : "unknown",
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
    setStreaming(true);
    setStreamingText("");
    let content = "";
    await client.sendChatStream(text, (event) => {
      const payload = event.payload ?? {};
      if (event.type === "delta") {
        content += String(payload.delta ?? "");
        setStreamingText(content);
      }
      if (event.type === "done") {
        if (isAgentState(payload.state)) {
          setState(payload.state);
          setStreamingText("");
        } else {
          setStreamingText(String(payload.reply ?? content));
        }
      }
      if (event.type === "error") {
        setNotice(String(payload.message ?? "Streaming chat failed."));
      }
    });
    setStreaming(false);
  }

  const messages: ChatMessage[] = state?.chat?.messages ?? [];

  return (
    <Box flexDirection="column" gap={1}>
      <StatusBar status={status} busy={busy} />
      <Box flexDirection="row" gap={1}>
        <Box flexGrow={1} flexBasis={0}>
          <ChatPanel messages={messages} streamingText={streamingText} streaming={streaming} error={error} />
        </Box>
        <Box flexGrow={1} flexBasis={0}>
          <ActionsPanel state={state} error={error} />
        </Box>
      </Box>
      {notice ? <Box borderStyle="single" paddingX={1}><Text color="gray">{notice}</Text></Box> : null}
      <CommandInput value={input} onChange={setInput} onSubmit={handleSubmit} disabled={busy} />
    </Box>
  );
}

function applyEvent(event: ApiEvent, setState: (state: AgentState) => void) {
  const payload = event.payload ?? {};
  const nestedState = payload.state;
  if (isAgentState(nestedState)) {
    setState(nestedState);
  }
}

function isAgentState(value: unknown): value is AgentState {
  return Boolean(value && typeof value === "object" && "ready" in value);
}

function readError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
