# Next Session Brief: C3 React GUI foundation + browser upload

> 目标：在 C1/C2 FastAPI proposal-only 后端上，增加 React + AntD + @ant-design/x 仪表盘基础界面，并补齐浏览器 multipart upload API。请求侧继续只写 state / memory / chunks / pending proposal，不执行硬件。

## 本轮范围

- 新增 `frontend/`，使用 Vite + React + TypeScript。
- 前端首屏就是操作台 dashboard，不做 marketing landing page。
- GUI 消费现有 FastAPI：
  - `GET /api/health`
  - `GET /api/state`
  - `GET /api/events`
  - `POST /api/chat`
  - `POST /api/tasks/submit`
  - `POST /api/actions/propose`
  - `POST /api/search-memory`
  - 新增 `POST /api/upload`
- FastAPI 在 `frontend/dist/index.html` 存在时托管 GUI；不存在时 `GET /` 返回清晰提示。
- 保留 `POST /api/ingest-file` 本地路径摄入接口，不删除旧 Markdown backend。

## 明确不做

- 不接 Agents SDK。
- 不接 OpenAI embeddings。
- 不接 sqlite-vec / semantic RAG。
- 不做 D1/D2 transport。
- 不暴露任何直接 execute / driver / hardware 控制按钮。

## 后端设计

- `POST /api/upload` 使用 `multipart/form-data`：
  - `file` 必填。
  - `tags` 可选，支持逗号分隔或重复字段语义的文本输入。
  - `importance` 可选，默认 `0`。
- 依赖：`server` extra 增加 `python-multipart>=0.0.9`。
- 不接受浏览器传入的任意本地路径。
- 上传内容先写入 API 控制的临时摄入文件，再复用 `physical_agent.ingest.files.ingest_file()`。
- 最终文件进入 `workspace/uploads/`，并写入 upload metadata、untrusted memory excerpt、untrusted chunks、audit 可导出状态。
- 默认大小上限：5MB。超过直接 413，不写 driver，不执行 watch。
- 支持已有文本类型：`.txt`, `.md`, `.markdown`, `.py`, `.json`, `.yaml`, `.yml`, `.toml`, `.csv`, `.log`。
- PDF / OCR / 图片本轮明确返回 unsupported type。

## 安全边界

- `/api/upload` 只写 uploads / memory / chunks / state event。
- `/api/upload` 不调用 `WatchRuntime`、`SafetyGate`、`driver.execute`。
- upload / retrieval 内容一律是 untrusted proposal context，不是 safety fact。
- `physical_agent.api.server` 顶层仍不得 import `physical_agent.watch.runtime` 或 `physical_agent.drivers.loader`。
- 默认 API 不启动 watch；只有 `physical-agent api --watch` 显式启用。

## 前端视图

- 顶部状态栏：backend、workspace ready、watch enabled、SSE connected。
- Action Board：pending / completed / cancelled。
- World / Feedback / Safety 摘要。
- Chat：使用 `@ant-design/x` Bubble / Sender，发送到 `POST /api/chat`。
- Task / Action proposal：任务提交到 `POST /api/tasks/submit`，并提供简单 action proposal 表单到 `POST /api/actions/propose`。
- Upload：AntD `Upload.Dragger` 调 `POST /api/upload`。
- Memory/Search：调用 `POST /api/search-memory`。
- Events：使用 `EventSource('/api/events')` 实时刷新；断开时显示 disconnected，并保留手动 refresh / 轮询 fallback。
- Raw Debug：折叠 JSON state。

## 工程与验收

- `.gitignore` 忽略：
  - `frontend/node_modules/`
  - `frontend/dist/`
  - `frontend/.vite/`
- 提交 `frontend/package.json`、lockfile、源码，不提交 `node_modules/` 或 `dist/`。
- 后端测试增加 `/api/upload` 成功、unsupported type、过大文件、untrusted metadata/chunks/audit 覆盖。
- 验证命令：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,server]"
.\.venv\Scripts\python.exe -m pytest -q tests\test_api_server.py tests\test_api_watch_events.py tests\test_safety_boundaries.py
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm install
npm run build
cd ..
git diff --check
```

## 交付文档

- 新增 `docs/session-handoff-c3-gui-foundation.zh-CN.md`。
- 写清前端依赖安装、构建、后端启动、GUI 消费的 API、`/api/upload` 安全限制、下一步建议。
