import type {
  ActionItem,
  AgentState,
  HealthState,
  LLMSettingsPayload,
  LLMSettingsResponse,
  SearchResponse,
  UploadResponse
} from "./types";

interface ApiJsonOptions {
  allowNotReadyBody?: boolean;
}

async function apiJson<T>(
  path: string,
  init: RequestInit = {},
  options: ApiJsonOptions = {}
): Promise<T> {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {})
    },
    ...init
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || (!options.allowNotReadyBody && data.ok === false)) {
    throw new Error(data.message || `Request failed: ${response.status}`);
  }
  return data as T;
}

export function fetchHealth(): Promise<HealthState> {
  return apiJson<HealthState>("/api/health", {}, { allowNotReadyBody: true });
}

export function fetchState(): Promise<AgentState> {
  return apiJson<AgentState>("/api/state", {}, { allowNotReadyBody: true });
}

export function sendChat(message: string): Promise<{
  ok: boolean;
  mode?: string;
  reply: string;
  executed: number;
  state: AgentState;
}> {
  return apiJson("/api/chat", {
    method: "POST",
    body: JSON.stringify({ message })
  });
}

export function fetchLLMSettings(): Promise<LLMSettingsResponse> {
  return apiJson<LLMSettingsResponse>("/api/settings/llm");
}

export function saveLLMSettings(
  payload: LLMSettingsPayload
): Promise<LLMSettingsResponse> {
  return apiJson<LLMSettingsResponse>("/api/settings/llm", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function testLLMSettings(): Promise<LLMSettingsResponse> {
  return apiJson<LLMSettingsResponse>(
    "/api/settings/llm/test",
    { method: "POST", body: JSON.stringify({}) },
    { allowNotReadyBody: true }
  );
}

export function submitTask(task: string): Promise<{
  ok: boolean;
  message: string;
  actions: ActionItem[];
  state: AgentState;
}> {
  return apiJson("/api/tasks/submit", {
    method: "POST",
    body: JSON.stringify({ task })
  });
}

export function proposeAction(action: ActionItem): Promise<{
  ok: boolean;
  message: string;
  action: ActionItem;
  state: AgentState;
}> {
  return apiJson("/api/actions/propose", {
    method: "POST",
    body: JSON.stringify(action)
  });
}

export function searchMemory(
  query: string,
  limit: number,
  tags?: string,
  sourceType?: string
): Promise<SearchResponse> {
  return apiJson("/api/search-memory", {
    method: "POST",
    body: JSON.stringify({
      query,
      limit,
      tags: tags ? tags.split(",").map((item) => item.trim()).filter(Boolean) : null,
      source_type: sourceType || null
    })
  });
}

export async function uploadBrowserFile(
  file: File,
  tags: string,
  importance: number
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  if (tags.trim()) {
    form.append("tags", tags);
  }
  form.append("importance", String(importance));

  const response = await fetch("/api/upload", {
    method: "POST",
    body: form
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) {
    throw new Error(data.message || `Upload failed: ${response.status}`);
  }
  return data as UploadResponse;
}
