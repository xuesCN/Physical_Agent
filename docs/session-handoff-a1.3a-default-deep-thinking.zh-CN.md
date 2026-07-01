# Session Handoff: A1.3a Default Deep Thinking for LLM Calls

> 目标：默认开启 LLM reasoning / deep-thinking 请求配置；不展示、不请求原始 chain-of-thought；不做前端 thinking UI。未 push，未开 PR。

## 起始确认

- 当前分支：`codex/openai-tool-loop-foundation`。
- 实际起始 HEAD：`b5b6071 Align state backend docs and project SQLite config`。
- 用户提示里的 `8c99055` 与当前 HEAD 标题相同，但不是祖先关系；差异只在 `docs/session-handoff-b5-state-backend-realignment.zh-CN.md` 追加了真实 Ark smoke 记录。
- `physical-agent.yaml` 当前为：

```yaml
workspace:
  path: ./workspace
  backend: sqlite
```

- 开工前已有未跟踪 `.tmp/`、`docs/REFACTOR-LOG.zh-CN.md`、`docs/current-architecture-overview.svg`、`docs/plan-a1-openai-sdk-chat.zh-CN.md`，本轮未纳入提交范围。
- 开工前 `.env.example` 已有本地改动；本轮因需要补 reasoning 示例而编辑它，并把看起来像真实 key 的值改回安全占位符。

## 官方文档核对

使用 OpenAI Docs MCP / OpenAPI spec 核对：

- `/v1/responses` request/response schema 包含 `reasoning` 对象，streaming response 也会携带 reasoning metadata。
- 官方 reasoning summaries 说明强调不暴露 raw chain-of-thought，只可使用 summaries。

本轮实现只传请求参数，不展示 reasoning 内容，不新增前端 reasoning 面板。

## 实现摘要

- `physical_agent/llm/settings.py`
  - 支持 `workspace/.llm.json` 与 `.env` / 环境变量解析：
    - `reasoning_enabled` 默认 `true`
    - `reasoning_effort` 默认 `medium`
    - `reasoning_summary` 默认 `auto`
    - `reasoning_extra_body` 可选 JSON object
  - 支持环境变量：
    - `OPENAI_REASONING_ENABLED` / `GPT_REASONING_ENABLED`
    - `OPENAI_REASONING_EFFORT` / `GPT_REASONING_EFFORT`
    - `OPENAI_REASONING_SUMMARY` / `GPT_REASONING_SUMMARY`
    - `OPENAI_REASONING_EXTRA_BODY` / `GPT_REASONING_EXTRA_BODY`
  - public summary 只暴露 `has_reasoning_extra_body`，不打印 extra_body 内容。

- `physical_agent/llm/openai_compatible.py`
  - `OpenAICompatibleSettings` 增加 reasoning 字段。
  - Responses API 非流式和流式默认传：

```python
reasoning={"effort": settings.reasoning_effort, "summary": settings.reasoning_summary}
```

  - Chat Completions 非流式和流式只在 `reasoning_extra_body` 非空时传：

```python
extra_body=settings.reasoning_extra_body
```

  - 不给 Chat Completions 硬塞 Responses-only `reasoning` 字段。
  - 如果首轮 400 明显是 `reasoning` / `thinking` / `extra_body` 不兼容，会自动重试一次不带 reasoning 参数，并在 retry request metadata 写入 `reasoning_fallback=true`；返回 dict 也会带 `physical_agent_metadata.reasoning_fallback=true`。
  - 错误消息继续脱敏 API key / Bearer token。

- `physical_agent/agent/tool_loop.py`
  - 默认 client 构造现在和 `ChatRuntime` 一样读取当前 config 的 workspace `.llm.json`，避免 tool-loop 漏掉本地 LLM settings / reasoning 配置。

- `physical_agent/api/server.py`
  - LLM settings API request/summary 支持 reasoning 字段。
  - 没有新增前端 settings UI reasoning 开关。

## 覆盖的 LLM 调用路径

- `OpenAICompatibleClient.chat()`。
- `OpenAICompatibleClient.structured_json()`，包括 strict schema -> JSON mode fallback。
- `OpenAICompatibleClient.responses_create()` / `responses_create_input()`。
- `OpenAICompatibleClient.stream_chat_text()` 的 Chat Completions 和 Responses 两种模式。
- `ChatRuntime` 非流式 LLM chat。
- `ChatRuntime` 流式 reply-only chat。
- `LLMPlanner`。
- `OpenAIToolLoop` 的 Chat Completions / Responses tool loop。
- CLI `llm-test`、API `/api/settings/llm/test`。
- `CodeRuntime` / `DriverCodingAgent` 仍复用同一个 client 类，因此继承同一 reasoning/fallback 行为。

## Ark / Doubao 真实 smoke

当前 `.env` 没有配置 reasoning extra_body；本轮真实 smoke 用进程级临时环境变量：

```powershell
$env:GPT_REASONING_EXTRA_BODY='{"thinking":{"type":"enabled"}}'
```

未写入 `.env`，未打印 key。

```powershell
.\.venv\Scripts\python.exe -m physical_agent.cli llm-test --env-file .env
```

结果：

- `base_url=https://ark.cn-beijing.volces.com/api/v3`
- `api_mode=chat_completions`
- `model=doubao-seed-2-1-pro-260628`
- `reasoning_enabled=true`
- `reasoning_extra_body=<set>`
- `LLM API test passed`
- `Response: pong`

直接 SDK smoke：

- prompt: `Reply with exactly: direct-pong`
- 结果：`ok=True`，`content=direct-pong`
- `reasoning_fallback=False`

结论：Ark 接受 `extra_body={"thinking":{"type":"enabled"}}`，未触发自动降级。

API smoke 使用 FastAPI TestClient 调用真实 endpoint：

```text
POST /api/chat
payload: {"message": "Reply with exactly: api-pong", "planner": "llm", "auto_step": false}
结果：HTTP 200，ok=true，mode=llm，executed=0，reply=api-pong，actions_count=0。

POST /api/chat/stream
payload: {"message": "Reply with exactly: stream-pong", "planner": "llm", "auto_step": false}
结果：HTTP 200，收到事件 start、delta、delta、delta、done；done payload mode=llm，reply=stream-pong。
```

## 验证结果

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_openai_compatible.py tests\test_chat_runtime.py tests\test_tool_loop.py tests\test_api_server.py tests\test_safety_boundaries.py
# 结果：71 passed, 1 warning

.\.venv\Scripts\python.exe -m pytest -q
# 结果：234 passed, 1 warning

cd frontend; npm.cmd run build
# 结果：通过

cd frontend; npm.cmd run test:e2e
# 结果：13 passed

git diff --check
# 结果：通过；仅 Windows LF -> CRLF warning

git diff --cached --check
# 结果：通过
```

warning 仍是既有 `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.`

## 未做事项

- 未做前端 reasoning UI / `ThoughtChain` 展示。
- 未做 Settings UI reasoning 开关。
- 未展示或请求 raw chain-of-thought。
- 未做 Agents SDK 迁移。
- 未做 PDF/OCR。
- 未改 backend，不新增 `JsonStateStore`。
- 未做 streaming tool calls。
- 未改 watch / driver / hardware 执行链。

## 下一步建议

1. 前端 reasoning 展示：只展示 provider/Responses 返回的 summaries，不展示 raw chain-of-thought。
2. PDF upload：继续作为不可信上下文摄入，不进入 watch 执行捷径。
3. 统一前端体验优化：整理 Settings、Memory、Events、Chat 的密度、错误态和响应式表现。
