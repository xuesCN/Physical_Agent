# Next Session：B3.8 default SQLite switch

## 背景

B3.7 readiness 结论支持进入默认 SQLite 切换。上一轮已补齐 backend matrix、迁移/readiness 验证和只读 `state-check`，结论是 SQLite backend 已具备作为新项目默认后端的条件。

## 本轮目标

本轮只用一个小而可回滚的变更，把新项目默认 `workspace.backend` 从 `markdown` 切到 `sqlite`。已有显式配置 `backend: markdown` 的项目行为不变。

继续保留：

- Markdown backend；
- Markdown parser / renderer；
- `migrate-md-to-sqlite`；
- `export-audit`；
- `state-check`；
- 清晰的回滚说明。

## 禁止做

- 删除 Markdown backend、parser 或 renderer；
- FastAPI / React；
- Agents SDK；
- 文件上传摄入；
- sqlite-vec / RAG；
- 任何 agent / tool / gui 侧硬件执行入口；
- 改动 OpenAI tool loop、rolling summary、action lease 或 audit export 的执行逻辑。

## 安全红线

agent / tool / gui 仍只能提出动作意图或写入 pending action。`watch` 仍是唯一 claim action、运行 `SafetyGate`、调用 `driver.execute(action)` 的执行侧。

执行路径保持：

```text
proposal -> action board -> watch -> SafetyGate.validate() -> driver.execute(action)
```

`SAFETY.md` 仍是文件真源。

## 回滚策略

代码级回滚：把 `physical_agent/config.py` 中默认配置里的 `workspace.backend` 改回 `markdown`。

单个项目回滚：

```yaml
workspace:
  path: ./workspace
  backend: markdown
```

## 验收标准

1. 新生成 config 默认 `workspace.backend` 为 `sqlite`。
2. `physical-agent init` / `physical-agent setup` 默认创建 SQLite workspace，`workspace/state.db` 存在。
3. `SAFETY.md` 仍存在且仍是文件真源。
4. 显式 `backend: markdown` 的项目仍走 `MarkdownStateStore`。
5. backend matrix 继续覆盖 `markdown` / `sqlite`。
6. `migrate-md-to-sqlite` 不自动改已有 config。
7. `export-audit` 不改 backend / action board。
8. `state-check` 默认 SQLite 路径可用，且仍是只读诊断。
9. watch 仍是唯一 claim + `SafetyGate` + `driver.execute` 侧。
10. safety boundary 测试通过。
11. 全量 `pytest` 通过。
