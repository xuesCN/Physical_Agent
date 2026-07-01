export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export interface HealthState {
  ok: boolean;
  ready: boolean;
  message: string;
  backend?: string;
  config_path?: string;
  workspace_path?: string;
  config_exists?: boolean;
  workspace_exists?: boolean;
}

export interface ActionItem {
  id: string;
  robot: string;
  capability: string;
  params?: Record<string, unknown>;
  reason?: string | null;
  depends_on?: string[];
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  created_at?: string | null;
  metadata?: Record<string, unknown>;
}

export interface MemoryChunk {
  id?: number;
  source_type?: string;
  source_id?: string;
  sha256?: string;
  chunk_index?: number;
  content?: string;
  tags?: string[];
  trust_level?: string;
  created_at?: string;
  score?: number;
}

export interface UploadMetadata {
  original_name?: string;
  stored_name?: string;
  sha256?: string;
  size_bytes?: number;
  content_type?: string;
  suffix?: string;
  status?: string;
  tags?: string[];
  importance?: number;
  error?: string;
}

export interface AgentState {
  ok: boolean;
  ready: boolean;
  message: string;
  backend?: string;
  config_path?: string;
  workspace_path?: string;
  task?: Record<string, unknown>;
  capabilities?: {
    robots?: Record<string, RobotInfo>;
    [key: string]: unknown;
  };
  world?: Record<string, unknown>;
  actions?: {
    pending?: ActionItem[];
    completed?: ActionItem[];
    cancelled?: ActionItem[];
  };
  feedback?: Record<string, unknown>;
  safety?: Record<string, unknown>;
  chat?: {
    messages?: ChatMessage[];
    running_summary?: string;
    [key: string]: unknown;
  };
  plan?: Record<string, unknown>;
  memory?: {
    notes?: Array<Record<string, unknown>>;
    [key: string]: unknown;
  };
  uploads?: {
    uploads?: UploadMetadata[];
    [key: string]: unknown;
  };
  chunks?: {
    chunks?: MemoryChunk[];
    [key: string]: unknown;
  };
}

export interface RobotInfo {
  kind?: string;
  driver?: string;
  status?: string;
  capabilities?: Array<{
    name?: string;
    description?: string;
    params_schema?: Record<string, unknown>;
    requires_approval?: boolean;
  }>;
}

export interface ApiEvent {
  id: number;
  type: "hello" | "state" | "watch_step" | "error" | string;
  ts: string;
  payload: Record<string, unknown>;
}

export interface SearchResponse {
  ok: boolean;
  query: string;
  results: MemoryChunk[];
}

export interface UploadResponse {
  ok: boolean;
  message: string;
  filename: string;
  size_bytes: number;
  result: Record<string, unknown>;
  state: AgentState;
}

export interface LLMSettingsSummary {
  base_url: string;
  model: string;
  api_mode: string;
  has_api_key: boolean;
  masked_api_key: string;
  settings_path?: string;
}

export interface LLMSettingsResponse extends LLMSettingsSummary {
  ok: boolean;
  message?: string;
  result?: Record<string, unknown>;
  settings?: LLMSettingsSummary;
}

export interface LLMSettingsPayload {
  base_url?: string;
  api_key?: string;
  model?: string;
  api_mode?: string;
}
