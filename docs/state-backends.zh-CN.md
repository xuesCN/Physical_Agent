# State Backends

## 结论

Physical Agent 的状态层是：

```text
StateStore Protocol -> exactly one active backend
```

当前支持两个 backend：

- `sqlite`：推荐/default backend。`workspace/state.db` 是状态真源，SQLite 表内 payload 使用 JSON。
- `markdown`：legacy 兼容 backend。显式配置后，`workspace/*.md` 是状态真源，可人工编辑。

项目没有 `JsonStateStore`，也没有 “JSON backend”。JSON 是 SQLite payload、API 传输和 GUI 渲染的数据格式。

## SQLite Backend

默认配置：

```yaml
workspace:
  path: ./workspace
  backend: sqlite
```

SQLite backend 把 task、capabilities、world、actions、feedback、chat、plan、memory、uploads、log 等动态状态写入 `workspace/state.db`。action board 使用 SQLite 行来支持 append、claim 和 terminal mark。`SAFETY.md` 不迁入 SQLite，仍是 watch 执行前读取的文件真源。

## Markdown Backend

显式配置：

```yaml
workspace:
  path: ./workspace
  backend: markdown
```

Markdown backend 作为 legacy 兼容路径保留。此时 `TASK.md`、`CAPABILITIES.md`、`WORLD.md`、`ACTIONS.md`、`FEEDBACK.md`、`CHAT.md`、`PLAN.md`、`MEMORY.md`、`LOG.md` 等文件是状态真源，`SAFETY.md` 仍是安全规则文件真源。

## Migration And Audit

`migrate-md-to-sqlite` 只做 Markdown -> SQLite 迁移：

```powershell
.\.venv\Scripts\python.exe -m physical_agent.cli migrate-md-to-sqlite --config physical-agent.yaml
```

如果 `workspace/state.db` 已存在，命令默认拒绝覆盖。只有确认不会丢失用户状态时，才应显式使用 `--overwrite`。迁移命令不会自动修改 `physical-agent.yaml`。

`export-audit` 从当前 active backend 导出人类可读审计视图：

```powershell
.\.venv\Scripts\python.exe -m physical_agent.cli export-audit --config physical-agent.yaml
```

导出的 `workspace/audit/` 是视图，不是新的真源。它不修改 backend，不修改 action board，也不做 SQLite -> Markdown 反向迁移。

## Switching Model

切 backend 是配置 + 重启的运维动作：

1. 修改 `physical-agent.yaml` 的 `workspace.backend`。
2. 重启 CLI/API/GUI/watch 相关进程。
3. 用 `state-check` 或 `GET /api/state-check` 验证 active backend。

GUI 只显示当前 backend、workspace、state-check 摘要和 audit export 能力，不提供 backend select、切换按钮、运行时 active backend 切换，或“迁移并自动切换”API。
