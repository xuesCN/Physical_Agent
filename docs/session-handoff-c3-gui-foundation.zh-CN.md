# Session Handoff: C3 React GUI foundation + browser upload

> 目标：在 C1/C2 FastAPI proposal-only 后端上增加 React + AntD + `@ant-design/x` dashboard，并补齐浏览器 multipart upload。请求侧仍然只写 proposal / state / memory / chunks，不执行硬件。

## 已完成范围

- 新增 brief：
  - `docs/next-session-c3-gui-foundation.zh-CN.md`
- 新增浏览器上传 API：
  - `POST /api/upload`
  - `multipart/form-data` 字段：`file`、可选 `tags`、可选 `importance`
  - 默认大小上限：5MB
  - 仅支持当前文本后缀：`.txt`, `.md`, `.markdown`, `.py`, `.json`, `.yaml`, `.yml`, `.toml`, `.csv`, `.log`
  - PDF / OCR / 图片本轮不做，返回清晰错误
- 更新 server extra：
  - `python-multipart>=0.0.9`
- FastAPI 静态托管：
  - `frontend/dist/index.html` 存在时，`GET /` 返回 React GUI
  - `frontend/dist/assets/` 存在时挂载为 `/assets`
  - build 不存在时，`GET /` 返回可读提示
- 新增前端工程：
  - `frontend/`
  - Vite + React + TypeScript
  - AntD + `@ant-design/icons` + `@ant-design/x`
  - `react-markdown`
  - 已提交 `package.json` 和 `package-lock.json`
- 更新 `.gitignore`：
  - `frontend/node_modules/`
  - `frontend/dist/`
  - `frontend/.vite/`

## GUI 消费的 API

- `GET /api/health`
- `GET /api/state`
- `GET /api/events`
- `POST /api/chat`
- `POST /api/tasks/submit`
- `POST /api/actions/propose`
- `POST /api/upload`
- `POST /api/search-memory`

`/api/events` 使用 `EventSource` 连接；收到 `state` 或 `watch_step` 事件后刷新完整 `/api/state`。SSE 断开时前端保留手动 refresh，并启用轻量轮询 fallback。

## 前端视图

- 顶部状态栏：backend、workspace ready、watch enabled、SSE connected。
- Action Board：pending / completed / cancelled 表格。
- World / Feedback / Safety 摘要。
- Chat：`@ant-design/x` `Bubble.List` + `Sender`，发送到 `POST /api/chat`。
- Task / Action proposal：任务写入 `POST /api/tasks/submit`；简单 action 写入 `POST /api/actions/propose`。
- Upload：AntD `Upload.Dragger` 调 `POST /api/upload`。
- Memory / Search：调用 `POST /api/search-memory`。
- Events：显示最近 SSE events。
- Raw Debug：折叠 JSON state。

## `/api/upload` 安全限制

- 不接受浏览器传入的任意本地路径。
- 上传文件名会 sanitize。
- 内容先写入 API 控制的 `workspace/uploads/.incoming/` 临时目录，再复用现有 `ingest_file()`。
- 成功摄入后，最终文件进入 `workspace/uploads/`。
- 小文本写入：
  - upload metadata
  - `UNTRUSTED UPLOAD EXCERPT` memory note
  - `trust_level: untrusted` memory chunks
- 上传 / retrieval 内容只作为 proposal context，不是 safety fact。
- `/api/upload` 不调用 `WatchRuntime`、`SafetyGate`、`driver.execute`。
- `physical_agent.api.server` 顶层仍不导入 watch runtime 或 drivers。

## 安装前端依赖

```powershell
cd frontend
npm install
```

## 构建前端

```powershell
cd frontend
npm run build
```

`dist/` 不提交；构建后 FastAPI 会在本地服务它。

## 启动后端

默认不启动 watch：

```powershell
physical-agent api --config physical-agent.yaml --host 127.0.0.1 --port 8766
```

需要同进程 watch 时显式开启：

```powershell
physical-agent api --config physical-agent.yaml --host 127.0.0.1 --port 8766 --watch
```

访问：

```text
http://127.0.0.1:8766/
```

## 验证结果

已运行：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,server]"
.\.venv\Scripts\python.exe -m pytest -q tests\test_api_server.py tests\test_api_watch_events.py tests\test_safety_boundaries.py
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm install
npm run build
```

结果：

```text
targeted API/watch/safety pytest: 16 passed, 1 warning
full pytest: 165 passed, 1 warning
npm run build: passed
```

warning：

- Python warning 来自当前 FastAPI / Starlette TestClient 对 `httpx` 的 deprecation 提示。
- 前端 build 通过；Vite 对 AntD/React bundle 输出 chunk-size warning，功能构建成功。

## 下一步建议

1. C3.1 GUI polish / e2e：用浏览器端 e2e 覆盖 dashboard load、chat、task proposal、upload、SSE reconnect。
2. C3.1 API client hardening：为前端 API client 增加单测或 MSW fixture。
3. D1 transport：等 GUI 基础稳定后，再进入 transport 抽象；不要从 GUI 暴露直接执行硬件的控制入口。
