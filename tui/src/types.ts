export interface HealthState {
  ok?: boolean;
  ready?: boolean;
  message?: string;
  backend?: string;
  workspace_path?: string;
  config_path?: string;
}

export interface AgentState extends HealthState {
  actions?: ActionBoardState;
  chat?: { messages?: ChatMessage[] };
}

export interface ActionItem {
  id: string;
  robot: string;
  capability: string;
  params?: Record<string, unknown>;
  reason?: string | null;
  status?: string;
  metadata?: Record<string, unknown>;
}

export interface ActionBoardState {
  pending?: ActionItem[];
  completed?: ActionItem[];
  cancelled?: ActionItem[];
}

export interface ChatMessage {
  role: "user" | "assistant" | "system" | string;
  content: string;
  created_at?: string;
  metadata?: Record<string, unknown>;
}

export interface TranscriptEntry {
  id: string;
  role: string;
  content: string;
  created_at?: string;
}

export interface ApiEvent {
  id?: number;
  type: string;
  ts?: string;
  payload?: Record<string, unknown>;
}

export interface RuntimeStatus {
  apiBase: string;
  connected: boolean;
  mode: "sse" | "polling" | "degraded";
  lastRefresh: string | null;
  backend: string;
  watch: WatchStatus;
  llm: LlmRuntimeStatus;
  message: string;
}

export type WatchStatus = "enabled" | "disabled" | "unknown";

export interface LLMSettingsSummary {
  base_url?: string;
  model?: string;
  api_mode?: string;
  has_api_key?: boolean;
  masked_api_key?: string;
  settings_path?: string;
}

export interface LLMSettingsResponse extends LLMSettingsSummary {
  ok: boolean;
  message?: string;
  result?: Record<string, unknown>;
  settings?: LLMSettingsSummary;
}

export interface LlmRuntimeStatus {
  state: "unknown" | "checking" | "ok" | "failed" | "unavailable";
  model: string;
  hasApiKey: boolean | null;
  message?: string;
}

export type ParsedCommand =
  | { type: "chat"; text: string }
  | { type: "task"; text: string }
  | { type: "approve"; actionId: string }
  | { type: "reject"; actionId: string; reason: string }
  | { type: "reset"; confirm: string }
  | { type: "refresh" }
  | { type: "help" }
  | { type: "quit" }
  | { type: "unknown"; input: string; message: string };
