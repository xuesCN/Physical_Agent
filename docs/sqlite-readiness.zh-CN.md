# SQLite Default Readiness

## 结论

B3.7 的矩阵验证表明 SQLite backend 已具备进入“默认切换”的条件。B3.8 已完成这个小步切换：新生成的 `physical-agent.yaml` 默认写出 `workspace.backend: sqlite`，`WorkspaceConfig.backend` 默认值也已切到 `sqlite`。

本次切换没有删除 Markdown backend、Markdown parser / renderer、`migrate-md-to-sqlite`、`export-audit` 或 `state-check`。已有项目只要显式配置 `workspace.backend: markdown`，仍继续使用 Markdown workspace 作为状态真源。

## 当前状态

- 新项目默认 backend 是 `sqlite`。
- `StateStore` 工厂仍可根据配置打开 `MarkdownStateStore` 或 `SqliteStateStore`。
- 显式 `workspace.backend: markdown` 的项目行为不变。
- SQLite backend 已覆盖 task、capabilities、world、actions、feedback、safety、chat、plan、memory、log 的基础读写。
- SQLite action board 具备原子 append、claim、terminal mark。
- SQLite action lease columns `claimed_at`、`claim_owner`、`attempts` 支持旧库自动迁移。
- SQLite stale lease recovery 已覆盖超时 `in_progress` 恢复为 pending。
- Markdown 与 SQLite 均支持 `export_human_view()` 和 CLI `export-audit`。
- `migrate-md-to-sqlite` 可把 Markdown workspace 迁移到 `workspace/state.db`，且不修改 config backend。
- `export-audit` 不修改 backend，也不修改 action board。
- `physical-agent state-check --config physical-agent.yaml` 仍是只读诊断命令，输出 backend、workspace initialized、SQLite schema complete、audit export writable。

## 保留项

默认切换后继续保留：

- Markdown backend；
- Markdown parser / renderer；
- `migrate-md-to-sqlite`；
- `export-audit`；
- `state-check`；
- `SAFETY.md` 文件真源；
- 明确的回滚说明。

## 默认切换风险

- 真实用户 workspace 可能包含手写 Markdown 边界格式；迁移到 SQLite 前仍建议先运行 `migrate-md-to-sqlite` 并核对 audit view。
- 默认 SQLite 后，人类直接编辑 Markdown 状态文件不再改变 SQLite 真源；应通过 CLI/API 写入状态，并用 `export-audit` 查看可读审计视图。
- SQLite `state.db`、`-wal`、`-shm` 文件需要被正确纳入或排除版本控制策略。
- 如果后续 C1/C2 服务化引入更多并发写入，需要继续扩大多进程/长时间运行测试。

## 回滚方式

单个项目回滚：

```yaml
workspace:
  path: ./workspace
  backend: markdown
```

代码级回滚：

- 将默认配置从 `sqlite` 改回 `markdown`。
- 保留 `migrate-md-to-sqlite` 和 `export-audit`，避免已迁移 workspace 失去审计和转换路径。
- 不删除 Markdown backend，直到真实 workspace 迁移窗口结束。

数据级回滚：

- 对显式 `backend: markdown` 的项目，Markdown 文件仍是原状态源。
- 对已切换到 SQLite 的项目，先运行 `physical-agent export-audit --config physical-agent.yaml` 导出可读视图，再把 config backend 改回 `markdown`；如需完全恢复 Markdown 真源，应以导出的 audit JSON/Markdown 原文件人工核对。

## 建议下一步

1. 继续观察默认 SQLite 下的真实项目使用情况，优先验证迁移、audit export、state-check 和回滚体验。
2. B4 structured memory 可以在默认切换稳定后推进，但不要引入 RAG 执行捷径。
3. C1 FastAPI 应在默认切换和 action board 契约稳定后再做，避免请求侧绕过 watch。
4. B4b 文件上传摄入如需推进，上传内容必须作为不可信输入，只进入提案上下文。
