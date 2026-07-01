# Session Handoff: A1.0/A1.1 OpenAI SDK Chat

> 目标：只完成 A1.0 + A1.1 的最小实现，用官方 OpenAI Python SDK 替换手写 urllib 客户端，并保持真实 CLI / ChatRuntime 的 LLM chat 路径可用。未 push，未开 PR。

## 起始状态

- 分支：`codex/openai-tool-loop-foundation`
- 起始 HEAD：`25c41e1 Add hardware bringup checklist docs`
- 开始前 tracked worktree 干净；存在未跟踪 `.tmp/` 测试产物，以及本轮输入上下文已有的未跟踪文档。

## 修改范围

- `pyproject.toml`
  - 新增可选 extra：`llm = ["openai>=1.40"]`。
  - `openai` 未加入基础必装依赖，quickstart 仍保持无 LLM key / 无 SDK 的轻量路径。
- `.env.example`
  - 新增火山方舟 Doubao 示例：
    - `GPT_URL=https://ark.cn-beijing.volces.com/api/v3`
    - `GPT_KEY=<ark key>`
    - `GPT_MODEL=doubao-seed-2.1-pro`
  - 注明推理接入点可填 `ep-xxxx`，不包含真实 key。
- `physical_agent/llm/openai_compatible.py`
  - 用官方 `openai.OpenAI(api_key=..., base_url=..., timeout=...)` 替换 urllib POST。
  - 保留既有公开方法：`chat()`、`structured_json()`、`chat_completion_create()`、`responses_create()`、`responses_create_input()`、`test_connection()`。
  - 低层 SDK 返回对象会转成普通 `dict`，以保持 `ChatRuntime`、`LLMPlanner`、`OpenAIToolLoop`、`DriverCodingAgent`、`CodeRuntime` 的调用契约。
- `tests/test_openai_compatible.py`
  - 改为 SDK mock 测试，不真实访问外网。
- `tests/test_tool_loop.py`
  - 改为 SDK mock 测试，同时保留 chat_completions / responses 双模式和 proposal-only allowlist 断言。

## SDK 替换方式

- `OpenAICompatibleClient` 初始化时创建 SDK client。
- `chat_completion_create()` 调用 `client.chat.completions.create(**payload)`。
- `responses_create_input()` 调用 `client.responses.create(**payload)`。
- 未安装 `openai` 时，只在实际初始化 LLM client 时抛 `OpenAICompatibleError`，不会影响无 LLM quickstart。
- SDK 常见异常会映射为 `OpenAICompatibleError`，包括 rate limit、timeout、connection、bad request、status error；错误消息会脱敏 API key / bearer token。

## base_url 策略

- `base_url` 被视为兼容 API root，原样传给 SDK。
- `https://ark.cn-beijing.volces.com/api/v3` 会作为 root 使用，不再拼成 `/api/v3/v1/chat/completions`。
- `public_summary()` 仍显示推导出的 chat/responses endpoint，便于 `llm-test` 和 GUI 状态查看。
- 若用户传入完整 endpoint，例如以 `/chat/completions` 或 `/responses` 结尾，settings validation 会明确报错，提示改填 API root。

## structured_json 降级策略

- 默认先走 strict `json_schema`。
- Chat Completions 使用：
  - `response_format={"type":"json_schema","json_schema":{"name":...,"strict":true,"schema":...}}`
- Responses 使用：
  - `text={"format":{"type":"json_schema","name":...,"strict":true,"schema":...}}`
- 如果 strict schema 返回 BadRequest / HTTP 400：
  - 自动降级到 JSON mode。
  - Chat Completions 使用 `response_format={"type":"json_object"}`。
  - Responses 使用 `text.format={"type":"json_object"}`。
  - 降级时会在 system/instructions 中追加明确 JSON 输出要求和 JSON Schema。
- strict 成功和降级成功都会本地 `json.loads()`，并用 `jsonschema.validate()` 校验 schema；不符合 schema 时抛 `OpenAICompatibleError`。

## 安全边界

- 未修改 watch / driver 执行链。
- 未新增 API / GUI / agent 直接调用 `driver.execute` / `heartbeat` / `halt` 的路径。
- LLM chat 仍只写 proposal / memory / chat；硬件执行仍必须经过 action board -> watch -> SafetyGate -> driver。
- tool loop 仍只 dispatch allowlist proposal tools。
- 默认 `agent.planner` 未改成 `auto`，quickstart 默认行为不变。

## 测试命令和结果

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_openai_compatible.py tests\test_chat_runtime.py tests\test_tool_loop.py tests\test_safety_boundaries.py
```

结果：

```text
29 passed in 4.51s
```

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,llm]"
```

结果：

```text
Successfully installed physical-agent-0.1.0
openai 2.44.0 already satisfied/installed
```

备注：第一次安装时本地 `physical-agent api --port 8766` 进程占用 `.venv\Scripts\physical-agent.exe`，停止该无 `--watch` 的 API wrapper 后重试成功。pip 仍提示 `.venv` 内有一次失败卸载留下的 `~hysical-agent` warning，不影响源码和测试。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
201 passed, 1 warning in 33.23s
```

warning：FastAPI / Starlette TestClient 对当前 `httpx` 的 deprecation 提示，非本轮新增。

## 未做事项

- 未做 streaming。
- 未做 abort。
- 未做 reasoning UI / 深度思考展示。
- 未做 PDF。
- 未做 Settings 面板。
- 未做 reset。
- 未做多模态。
- 未做 Agents SDK。
- 未做 FastAPI / React GUI 改造。

## 下一步建议

1. 下一轮可做 Settings / API chat：把 `.env` 手工配置升级为本地 UI/API 配置入口，但仍不要让 API/GUI 直接执行硬件。
2. 再下一轮可做 streaming：只流式自然语言 reply，结构化 action proposal 仍走非流式 schema/JSON。
3. 若要支持 Doubao reasoning 参数，可在 SDK payload 中通过 provider-specific `extra_body` 做显式配置开关，默认关闭。
4. 可单独清理 `.venv` 里 pip 失败卸载留下的 `~hysical-agent` warning，不需要提交源码改动。
