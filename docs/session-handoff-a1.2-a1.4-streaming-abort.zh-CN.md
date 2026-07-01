# Session Handoff: A1.2 + A1.4 Streaming + Abort

> 分支：`codex/openai-tool-loop-foundation`
> 起始 HEAD：`affbda7 Add local LLM settings and API chat bridge`
> 本轮范围：只做 streaming + abort；未 push，未开 PR。

## 修改范围

- `OpenAICompatibleClient` 新增 `stream_chat_text(...)` 同步 iterator。
  - `chat_completions` 模式调用 SDK `client.chat.completions.create(..., stream=True)`，读取 `choices[].delta.content`。
  - `responses` 模式调用 SDK `client.responses.create(..., stream=True)`，读取 `response.output_text.delta`，处理 `response.completed`、`error`、`response.failed`。
  - 流式创建和迭代错误继续走现有 OpenAI-compatible 错误归一与 API key / Bearer token 脱敏。
- `ChatRuntime` 新增 `respond_stream(...)`。
  - 只做自然语言 assistant reply 流式，不做 streaming tool calls，不做 streaming structured action proposal。
  - API-safe flags 下不暴露 code skills / hardware integration。
  - 完成后写入完整 assistant message；取消时写入 partial assistant message，metadata 里标记 `stream_status="cancelled"`、`partial=true`。
  - 流式动作类请求只返回说明，不写 pending action，不启动 `WatchRuntime`。
- FastAPI 新增专用聊天流。
  - `POST /api/chat/stream` 返回 SSE，事件类型：`start`、`delta`、`done`、`error`、`aborted`。
  - `POST /api/chat/abort/{stream_id}` 设置服务端 abort flag；前端同时使用 `AbortController` 断开连接。
  - `/api/events` 未复用，仍只负责状态/watch 事件。
  - stream done/error/abort 会记录可读日志并发布 state summary，但 API chat 仍不实例化 watch，不调用 driver。
- React ChatPanel 接入流式体验。
  - send 优先调用 `/api/chat/stream`，本地乐观插入 user + assistant bubble，delta 增量更新 assistant。
  - Stop 按钮调用 abort endpoint 并 abort fetch。
  - stream endpoint 不可用时 fallback 到 `/api/chat`。
  - stream/model 错误显示在聊天面板 Alert，不触发 Vite overlay。
- 顺手修复上一轮 handoff 前两行 trailing whitespace。

## 官方文档核对

使用 OpenAI Docs MCP 核对了 streaming 语义：

- Chat Completions streaming 使用 incremental chunks，读取 `delta` 字段。
- Responses streaming 使用 typed events；文本流关注 `response.created`、`response.output_text.delta`、`response.completed`、`error`。

本实现只参考这些语义，不做真实 OpenAI/Ark 外网调用。

## 测试结果

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_openai_compatible.py tests\test_chat_runtime.py tests\test_api_server.py tests\test_safety_boundaries.py
```

结果：`52 passed, 1 warning`。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：`221 passed, 1 warning`。

```powershell
cd frontend
npm.cmd run build
```

结果：通过。

```powershell
cd frontend
npm.cmd run test:e2e
```

结果：`12 passed`。

```powershell
git diff --check
git diff --cached --check
```

结果：通过；`git diff --check` 仅输出 Windows `LF will be replaced by CRLF` 提示。

## Warning

- Python 测试仍有既有 warning：`StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.`
- 本地 e2e 可能复用旧 API server；测试已允许 `/api/chat/stream` 404 fallback，不把该预期 fallback 资源错误视作 Vite overlay / console regression。

## 未做事项

- 未做 Agents SDK 迁移。
- 未做 streaming tool calls。
- 未做 streaming structured output / action proposal。
- 未做 reasoning / deep thinking UI。
- 未做 PDF/OCR。
- 未做 reset workspace。
- 未做真实 OpenAI/Ark 外网测试。
- 未改 watch / driver / hardware 执行路径。

## 下一步建议

下一阶段可以进入 A1.3 reasoning UI / reasoning 参数；如果优先用户输入材料能力，也可以进入 PDF upload，但需要继续保持上传内容是 untrusted proposal context。
