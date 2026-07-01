# Session Handoff：B5 State Backend Realignment

> 目标：收口原始 spec 里“JSON 为准的 StateStore + SQLite + 人类视图”的口径，明确当前实现是 `StateStore` Protocol 打开一个 active backend：SQLite 推荐/default，Markdown legacy 兼容，audit export 是人类可读视图。

## 本轮结论

- 本地 `physical-agent.yaml` 已显式设置：

```yaml
workspace:
  path: ./workspace
  backend: sqlite
```

- `workspace/state.db` 已存在且包含结构化 chat/memory/upload/log 状态；`migrate-md-to-sqlite --config physical-agent.yaml` 默认拒绝覆盖，因此本轮没有使用 `--overwrite`，避免误删用户状态。
- SQLite backend 是当前项目状态真源；SQLite 表内 payload 是 JSON。
- `SAFETY.md` 仍是文件真源，不迁入 SQLite。
- Markdown backend、SQLite backend、Markdown parser / renderer、`migrate-md-to-sqlite`、`export-audit` 均保留。
- 没有新增 `JsonStateStore`，没有 GUI backend 热切换，没有运行时 active backend 切换，没有 SQLite -> Markdown 反向迁移。

## 后端/API

- `state-check` 结构化结果新增 backend 语义字段：
  - `backend_role`: `recommended` / `legacy`
  - `source_of_truth`
  - `payload_format`
  - `safety_source`
  - `runtime_switch_supported`
  - `switching_model`
  - `recommendation`
- 新增只读 endpoint：

```text
GET /api/state-check
```

- `POST /api/export-audit` 保持只导出 audit view，并补充返回：
  - `backend`
  - `workspace_path`
  - `out_dir`
  - `manifest`
- HTTP 请求侧仍不实例化 `WatchRuntime`，不调用 `driver.execute` / `heartbeat` / `halt`。

## GUI

Settings 面板新增只读状态后端可视化：

- active backend
- workspace path
- state-check 摘要
- source of truth
- payload format
- safety source
- SQLite schema 状态
- audit export 按钮

Markdown backend 文案说明它是 legacy backend，需要通过 CLI `migrate-md-to-sqlite`、改配置并重启。SQLite backend 文案说明 `state.db is source of truth`，`SAFETY.md remains file source`。没有 backend select 或切换按钮。

## 文档口径

- `README.zh-CN.md`、`HANDOFF.zh-CN.md`、`docs/sqlite-readiness.zh-CN.md`、`docs/optimization-spec.zh-CN.md` 已改为：
  - exactly one active backend
  - Markdown = legacy compatibility backend
  - SQLite = recommended/default source of truth
  - SQLite payload = JSON
  - API/GUI JSON = transport/rendering view
  - `export-audit` = human-readable audit view
  - no `JsonStateStore`
  - no GUI live backend switch
  - switching = config + restart
- 新增 `docs/state-backends.zh-CN.md` 专门说明 backend、迁移、audit 和切换模型。

## 验证记录

```powershell
.\.venv\Scripts\python.exe -m physical_agent.cli migrate-md-to-sqlite --config physical-agent.yaml
# 结果：拒绝覆盖已有 workspace/state.db；未使用 --overwrite。

.\.venv\Scripts\python.exe -m physical_agent.cli setup --config physical-agent.yaml
# 结果：成功发布 mock_arm capabilities/world 到 SQLite；未执行 action。

.\.venv\Scripts\python.exe -m physical_agent.cli state-check --config physical-agent.yaml
# 结果：Backend sqlite；Backend role recommended；SQLite schema complete yes；audit export writable yes。

.\.venv\Scripts\python.exe -m physical_agent.cli inspect --config physical-agent.yaml
# 结果：Backend sqlite；arm_1 via mock_arm；world summary 正常；pending actions none。

.\.venv\Scripts\python.exe -m physical_agent.cli export-audit --config physical-agent.yaml
# 结果：导出 workspace/audit/manifest.json，backend sqlite。

.\.venv\Scripts\python.exe -m pytest -q tests\test_state_store.py tests\test_backend_matrix.py tests\test_api_server.py tests\test_safety_boundaries.py
# 结果：58 passed, 1 warning。

.\.venv\Scripts\python.exe -m pytest -q
# 结果：223 passed, 1 warning。

cd frontend; npm.cmd run build
# 结果：通过。

cd frontend; npm.cmd run test:e2e
# 结果：13 passed。
```

真实 Ark smoke 已补做，使用 `.env` 中的 Ark 配置，不打印 key：

```powershell
.\.venv\Scripts\python.exe -m physical_agent.cli llm-test --env-file .env
# 结果：base_url=https://ark.cn-beijing.volces.com/api/v3，
# api_mode=chat_completions，
# model=doubao-seed-2-1-pro-260628，
# LLM API test passed，Response: pong。
```

API smoke 使用 FastAPI TestClient 调用真实 endpoint，无 mock / monkeypatch：

```text
POST /api/chat
payload: {"message": "Reply with exactly: api-pong", "planner": "llm", "auto_step": false}
结果：HTTP 200，ok=true，mode=llm，executed=0，reply=api-pong，actions_count=0。

POST /api/chat/stream
payload: {"message": "Reply with exactly: stream-pong", "planner": "llm", "auto_step": false}
结果：HTTP 200，收到事件 start、delta、delta、delta、done；done payload mode=llm，reply=stream-pong。
```

结论：Ark base_url/model/key/network 均可用；未发现 sandbox 网络限制、provider 兼容问题或本轮代码改动导致的 LLM/API 回归。

## 下一步建议

1. A1.3 reasoning UI：展示 planner/tool-loop reasoning 状态，但请求侧仍只写 proposal。
2. A1.5 PDF upload：作为不可信上下文摄入，不进入 watch 执行捷径。
3. 统一前端体验优化：继续整理 Settings、Memory、Events 的密度、错误态和响应式表现。
