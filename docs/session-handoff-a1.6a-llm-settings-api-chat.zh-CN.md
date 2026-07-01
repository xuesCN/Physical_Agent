# Session Handoff: A1.6a LLM Settings + API Chat Bridge

> 分支：`codex/openai-tool-loop-foundation`  
> 起始 HEAD：`9c25e90 Use OpenAI SDK for compatible chat client`  
> 本轮范围：只做本地 LLM settings 与非流式 API chat bridge。未 push，未开 PR。

## 修改范围

- 新增 `physical_agent/llm/settings.py`，负责本地 `workspace/.llm.json` 读写、合并 `.env`、生成脱敏摘要。
- 扩展 `OpenAICompatibleSettings.from_env()`：读取优先级为显式 `model` override > `workspace/.llm.json` > `.env` / 环境变量 > 默认值。
- 新增 FastAPI 端点：
  - `GET /api/settings/llm`
  - `POST /api/settings/llm`
  - `POST /api/settings/llm/test`
- 将 FastAPI `POST /api/chat` 从 API 内部 rule-based 实现改为调用 `ChatRuntime`，仍强制 proposal-only。
- 为 `ChatRuntime` 增加 API-safe flags：
  - `enable_code_skills=True`
  - `enable_hardware_integration=True`
  - API 使用 `False / False`。
- 在 React `SettingsPanel` 增加 LLM settings 表单和连接测试按钮。
- 更新 `.gitignore`，忽略 `**/.llm.json`。

## `.llm.json` 存储策略

- 文件位置：当前 config 指向的 workspace 下，即 `workspace/.llm.json`。
- 典型字段：

```json
{
  "api_key": "...",
  "api_mode": "chat_completions",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-5.4"
}
```

- `api_mode` 默认是 `chat_completions`，也保留 `responses` 兼容。
- 保存时如果 API key 输入为空，默认保留已有 key；`clear_api_key=true` 可显式清空。
- `.llm.json` 不进入 git；不写入 `state.db`；不在 audit export 的文档集合中；API 日志只记录 settings/chat 操作，不记录 key。

## Key 脱敏策略

- GET/POST/test settings 响应只返回：
  - `base_url`
  - `model`
  - `api_mode`
  - `has_api_key`
  - `masked_api_key`，形如 `****1234`
- 不返回完整 key。
- 连接测试失败会对完整 key、Bearer token、`api_key=` 风格片段做替换。

## API Chat Proposal-Only 边界

- `/api/chat` 懒加载 `ChatRuntime`，避免 `physical_agent.api.server` 顶层导入 watch/driver。
- API 创建 runtime 时固定：
  - `planner_name="auto"`，除非请求显式限制为 `llm` 或 `rule_based`
  - `auto_step=False`
  - `enable_code_skills=False`
  - `enable_hardware_integration=False`
- API 不提前 append user message，避免 ChatRuntime 重复写 chat。
- API chat 不实例化 `WatchRuntime`，不调用 `driver.execute` / `heartbeat` / `halt`。
- LLM chat 仍只会写 chat、memory、plan 和 pending action proposal；真实动作执行仍必须走 `watch -> SafetyGate -> driver.execute`。
- 没有 key 或 LLM 不可用时，`auto` 自动 fallback 到 rule-based chat，前端仍可用。

## 测试命令和结果

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_openai_compatible.py tests\test_chat_runtime.py tests\test_api_server.py tests\test_safety_boundaries.py
```

结果：`41 passed, 1 warning`。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：`210 passed, 1 warning`。

```powershell
cd frontend
npm.cmd run build
```

结果：通过。

```powershell
cd frontend
npm.cmd run test:e2e
```

结果：`9 passed`。

```powershell
git diff --check
```

结果：通过；仅有 Windows `LF will be replaced by CRLF` 行尾提示。

## 未做事项

- streaming
- abort / stop button
- reasoning UI / reasoning 参数面板
- PDF 上传 / OCR
- reset
- 多模态
- Agents SDK
- 真实外网自动测试
- watch / driver 执行链改造

## 下一步建议

下一阶段可以进入 `streaming + abort`：只流式输出自然语言 reply，结构化 action proposal 仍走非流式 JSON/schema。另一个可选方向是 PDF 文本摄入，但应继续明确上传内容是不可信 proposal context。
