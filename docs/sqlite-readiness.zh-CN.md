# SQLite Default Readiness

## 结论

B3.7 的矩阵验证表明：SQLite backend 已具备进入下一阶段“默认切换”工作的条件，但不应在本轮直接切默认。

建议下一阶段用一个单独变更把默认 backend 从 `markdown` 切到 `sqlite`，同时保留 Markdown backend、`migrate-md-to-sqlite`、`export-audit` 和回滚说明。若默认切换后出现真实 workspace 兼容问题，可立即把 `workspace.backend` 改回 `markdown`，继续使用原 Markdown workspace 文件。

## 已满足项

- 默认 backend 本轮仍是 `markdown`，SQLite 仍需 `workspace.backend: sqlite` opt-in。
- `StateStore` 工厂已可根据配置打开 `MarkdownStateStore` 或 `SqliteStateStore`。
- SQLite backend 已覆盖 task、capabilities、world、actions、feedback、safety、chat、plan、memory、log 的基础读写。
- SQLite action board 已具备原子 append、claim、terminal mark。
- SQLite action lease columns `claimed_at`、`claim_owner`、`attempts` 已支持旧库自动迁移。
- SQLite stale lease recovery 已覆盖超时 `in_progress` 恢复为 pending。
- Markdown 与 SQLite 均支持 `export_human_view()` 和 CLI `export-audit`。
- `migrate-md-to-sqlite` 可把 Markdown workspace 迁移到 `workspace/state.db`，且不修改 config backend。
- `export-audit` 不修改 backend，也不修改 action board。
- 新增 backend matrix 覆盖：
  - init；
  - proposal append；
  - MCP `propose_action`；
  - ChatRuntime proposal；
  - WatchRuntime 成功执行；
  - SafetyGate 拒绝；
  - driver exception；
  - audit export。
- 新增 `physical-agent state-check --config physical-agent.yaml` 作为只读诊断命令，输出 backend、workspace initialized、SQLite schema complete、audit export writable。

## 未满足项

- 默认 backend 尚未切换，本轮没有改变 `WorkspaceConfig.backend` 或 `default_config_dict()`。
- 尚未在一组真实历史 workspace 上做人工抽样迁移和回滚演练。
- 尚未删除 Markdown parser/renderer；下一阶段默认切换也不建议删除。
- 尚未做 FastAPI/React、常驻 watch 服务化、文件上传摄入、sqlite-vec/RAG。
- 尚未验证服务化后的多进程 watch 长时间并发行为；当前只验证了 SQLite 原子 claim 与 backend 行为矩阵。

## 默认切换风险

- 真实用户 workspace 可能包含手写 Markdown 边界格式，迁移后需要确认 SQLite 读出的 JSON 视图符合预期。
- 默认 SQLite 后，人类直接编辑 Markdown 状态文件将不再改变 SQLite 真源；需要通过 `export-audit` 提供可读审计视图，并在文档中说明编辑入口。
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

- 对未切换配置的项目，Markdown 文件仍是原状态源。
- 对已切换到 SQLite 的项目，先运行 `physical-agent export-audit --config physical-agent.yaml` 导出可读视图，再把 config backend 改回 `markdown`；如需完全恢复 Markdown 真源，应以导出的 audit JSON/Markdown 原文件人工核对。

## 建议下一步

1. 进入下一阶段默认 SQLite 切换：单独提交，改默认值和最小文档，不混入 FastAPI/React/RAG。
2. 切换提交继续跑 backend matrix、safety boundary、全量 pytest。
3. 保留 Markdown backend 至少一个迁移周期。
4. B4 structured memory 可以在默认切换稳定后继续推进，但不要引入 RAG 执行捷径。
5. C1 FastAPI 应在默认切换和 action board 契约稳定后再做。
