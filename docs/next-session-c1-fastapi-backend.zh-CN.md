# Next Session Brief: C1 FastAPI backend

> 目标：实现 optional FastAPI backend，把现有 StateStore / action board / memory / uploads / retrieval / audit 契约暴露为安全 HTTP API。请求侧只能读状态或写 pending proposal、chat/memory/upload/chunk/audit，不执行 watch，不运行 SafetyGate，不调用 driver.execute。

## 本轮范围

- 增加 `server` optional dependency：`fastapi>=0.110`、`uvicorn>=0.29`。
- 新增 `physical_agent/api/server.py`，提供 `create_app(config_path)`。
- FastAPI / uvicorn 必须是 guarded import：未安装时给出清晰安装提示，普通 CLI / 测试 / Markdown backend 不受影响。
- 新增 CLI：

```powershell
physical-agent api --config physical-agent.yaml --host 127.0.0.1 --port 8766
```

- 新增端点：
  - `GET /api/health`
  - `GET /api/state`
  - `POST /api/actions/propose`
  - `POST /api/tasks/submit`
  - `POST /api/chat`
  - `POST /api/search-memory`
  - `POST /api/ingest-file`
  - `POST /api/export-audit`

## 安全边界

- API 模块导入不得启动 watch、加载 driver、打开硬件。
- API 请求处理器不得调用 `WatchRuntime.step()` / `run_forever()`。
- API 请求处理器不得实例化或运行 `SafetyGate`。
- API 请求处理器不得调用 `driver.execute`。
- `/api/actions/propose` 只追加 pending action。
- `/api/tasks/submit` 只写 task，并用安全 proposal helper 生成 pending action；不等待反馈，不执行动作。
- `/api/chat` 只写 chat / memory / pending action；不得进入 code skill、hardware integration、Agents SDK 或 auto-step。
- `/api/search-memory` 只读 retrieval chunks。
- `/api/ingest-file` 本轮只支持本地路径 ingest，只写 uploads / memory / chunks。
- `/api/export-audit` 只导出 audit view。

## 明确不做

- 不做 React / AntD。
- 不做 SSE / WebSocket / event stream。
- 不做常驻 watch。
- 不做 Agents SDK。
- 不做 OpenAI embeddings / sqlite-vec。
- 不做 multipart upload；因此不加 `python-multipart`。
- 不删除或替换 Markdown backend。

## 验收

- 默认 backend 仍为 SQLite。
- FastAPI 是 optional extra，未安装不影响普通测试。
- API 请求侧不能执行硬件。
- `tests/test_safety_boundaries.py` 扫描 `physical_agent/api`。
- 新增 `tests/test_api_server.py` 覆盖 endpoint 与安全边界。
- 全量 `pytest -q` 通过。
