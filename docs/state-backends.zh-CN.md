# State Backend

## 当前结论

Physical Agent 只有一个 active state backend：

```text
StateStore Protocol -> SqliteStateStore -> workspace/state.db
```

SQLite 保存 task、capabilities、world、actions、feedback、chat、plan、memory、uploads、retrieval chunks 与 log entries。JSON 只是 SQLite payload、API 传输和 UI 渲染格式，不是第二个 backend。

文件 sidecar 只剩两个正式职责：

- `SAFETY.md` 是人类拥有的安全规则真源，watch 每次执行前读取并运行 SafetyGate。
- `LOG.md` 是人类可读镜像；SQLite `log_entries` 才是运行态日志真源。

`export-audit` 从 SQLite 导出 `workspace/audit/` 可读视图并复制 SAFETY；该目录不是 backend，也不能写回运行态。

## 配置与日常诊断

默认配置：

```yaml
workspace:
  path: ./workspace
  backend: sqlite
```

初始化与只读检查：

```powershell
physical-agent init --config physical-agent.yaml
physical-agent state-check --config physical-agent.yaml
physical-agent doctor --config physical-agent.yaml
physical-agent export-audit --config physical-agent.yaml
```

普通 `init` 不覆盖已有状态或人工 SAFETY；只有明确要求重置时才使用 `--force`。

## 旧 Markdown workspace 的 fail-closed 边界

当前版本已经删除 runtime Markdown backend、迁移命令、legacy reader 和 full Workspace parser。以下两种情况都会被拒绝：

- 显式配置 `workspace.backend: markdown`。
- 配置省略 backend，但目标目录存在完整 legacy Markdown 文件集合。

拒绝是防双真源门禁：当前进程不会在旧目录旁静默创建 `state.db`，也没有 GUI/API backend switch 或自动迁移入口。

## 历史救援流程

只有确实需要抢救旧 workspace 时才使用以下流程。迁移必须由独立历史 checkout 完成，不能调用当前 executable：

```powershell
git worktree add --detach ..\Physical_Agent-legacy 9072b4e9fb600e505668aeb6076eb6cb85e5ff82
cd ..\Physical_Agent-legacy
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m physical_agent.cli migrate-md-to-sqlite --config <旧项目的physical-agent.yaml>
```

历史命令不会自动修改 config。迁移完成后：

1. 先备份旧 workspace 和新生成的 `state.db`；已有 DB 时不要轻率使用历史 `--overwrite`。
2. 手动把项目配置设为 `workspace.backend: sqlite`。
3. 回到当前版本。
4. 不带 `--force` 运行 `physical-agent init --config physical-agent.yaml`，让当前版本补齐 schema，同时保留 SAFETY/LOG。
5. 运行 `physical-agent state-check --config physical-agent.yaml`，再用 `export-audit` 核对数据。

仓库的 `scripts/smoke_legacy_workspace_rescue.py` 持续验证旧/新解释器隔离、十一类数据面、SAFETY/LOG 保留和已有 DB 拒绝。

## 不再支持的兼容面

- 当前 CLI 中不存在 `migrate-md-to-sqlite`。
- 不支持 SQLite 到旧 Markdown workspace 的反向迁移。
- 不支持 live backend switch。
- 不把 audit JSON 或 `LOG.md` 当成可写状态真源。
