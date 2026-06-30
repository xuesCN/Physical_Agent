# Session Handoff: C1 FastAPI backend

> 目标：实现 optional FastAPI backend，把 StateStore / action board / memory / uploads / retrieval / audit 契约暴露为安全 API。请求侧只读状态或写 pending proposal / chat / memory / uploads / chunks / audit，不执行 watch，不运行 SafetyGate，不调用 driver.execute。

## 已完成范围

- 新增 brief：
  - `docs/next-session-c1-fastapi-backend.zh-CN.md`
- 新增 API package：
  - `physical_agent/api/__init__.py`
  - `physical_agent/api/server.py`
- 新增 optional dependency：
  - `server = ["fastapi>=0.110", "uvicorn>=0.29"]`
- 新增 CLI：

```powershell
physical-agent api --config physical-agent.yaml --host 127.0.0.1 --port 8766
```

未安装 server extra 时会提示安装：

```powershell
pip install -e .[server]
```

## API endpoints

- `GET /api/health`
  - 读取配置和 workspace readiness。
- `GET /api/state`
  - 读取 task / capabilities / world / actions / feedback / safety / chat / plan / memory / uploads / chunks。
- `POST /api/actions/propose`
  - 追加一个 pending `Action`，不执行。
- `POST /api/tasks/submit`
  - 写 task，并用 API 本地 `SafeProposalPlanner` 生成 pending action proposal。
- `POST /api/chat`
  - 写 user/assistant chat；可写 memory；可写 pending action proposal；强制 `executed=0`。
- `POST /api/search-memory`
  - 只读本地 keyword chunks。
- `POST /api/ingest-file`
  - 本轮只支持本地路径 ingest；写 uploads / memory / chunks。
- `POST /api/export-audit`
  - 只导出 audit view。

## 安全边界

- `physical_agent.api.server` 顶层导入不依赖 FastAPI，也不导入 `physical_agent.watch.runtime` 或 `physical_agent.drivers.loader`。
- API 没有复用 `GuiController`、`PhysicalAgentMCP.submit_task` 或 `ChatRuntime.respond`，避免请求侧进入 watch、code skill、hardware integration 或 auto-step 路径。
- API 本地 `SafeProposalPlanner` 只返回 `Action` 数据对象，由 StateStore 写入 pending board。
- 请求处理器不调用：
  - `WatchRuntime.step()`
  - `WatchRuntime.run_forever()`
  - `SafetyGate`
  - `driver.execute`
- `tests/test_safety_boundaries.py` 已扩展扫描 `physical_agent/api`。

## 未完成 / 留给 C2-C3

- C2：常驻 watch、后台任务、并发/租约压测。
- C2：SSE / WebSocket / incremental events。
- C3：React / AntD / @ant-design/x GUI。
- C3：GUI upload / multipart upload。
- B4d：OpenAI embeddings、sqlite-vec、semantic RAG。
- Agents SDK 集成未做。

## 测试结果

当前环境未安装 FastAPI，所以 TestClient endpoint 用例按设计 skip；controller 契约测试和 CLI 缺依赖提示仍会运行。

```text
tests/test_api_server.py tests/test_safety_boundaries.py
3 passed, 2 skipped
```

全量：

```text
152 passed, 2 skipped
```
