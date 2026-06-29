# Next Session Brief：B3.7 SQLite default-readiness / backend matrix

## 背景

B2/B3/B3.5/B3.6 已完成：SQLite backend 已作为 opt-in 后端接入，并具备 Markdown -> SQLite 迁移、audit export、原子 action append/claim、SQLite action lease recovery，以及 watch 侧 driver 异常终态写入能力。

默认 backend 仍是 `markdown`；SQLite 仍需通过 `workspace.backend: sqlite` 显式启用。Markdown backend、Markdown parser/renderer 与 `SAFETY.md` 文件真源仍保留。

## 本轮目标

补齐 backend matrix / readiness 检查，为未来是否把默认 backend 切到 SQLite 提供证据。

本轮重点不是切默认，而是系统性验证 Markdown 与 SQLite backend 在核心用户路径上的行为等价性，并确认迁移、导出、回滚路径可操作：

- backend matrix 覆盖 `markdown` / `sqlite` 的 init、proposal append、MCP `propose_action`、ChatRuntime proposal、WatchRuntime 成功执行、SafetyGate 拒绝、driver exception、audit export。
- 迁移/readiness 覆盖 Markdown -> SQLite 后 task/capabilities/world/actions/feedback/chat running_summary/memory/log/audit export 可读。
- 验证旧 SQLite `state.db` 自动补齐 action lease columns。
- 验证 `migrate-md-to-sqlite` 不修改 config backend。
- 验证 `export-audit` 不修改 backend/action board。
- 形成 `docs/sqlite-readiness.zh-CN.md`，给出是否建议进入下一阶段默认 SQLite 切换的明确判断。

## 禁止做

- 不把默认 backend 切到 SQLite。
- 不删除 Markdown backend、Markdown parser 或 Markdown renderer。
- 不做 FastAPI/React。
- 不做 Agents SDK。
- 不做文件上传摄入。
- 不做 sqlite-vec/RAG。
- 不新增任何 agent/tool/gui 侧硬件执行入口。
- 不改变 OpenAI/tool_loop/rolling summary/audit export/action lease 既有行为。

## 安全红线

agent/tool/gui 只能提出动作意图或追加 pending action。`watch` 仍是唯一 claim action、运行 `SafetyGate.validate()`、调用 `driver.execute(action)` 的执行侧。

真实执行路径保持：

```text
proposal -> action board -> watch -> SafetyGate.validate() -> driver.execute(action)
```

本轮任何新增 CLI/doctor/state-check 都必须是只读/诊断性质：不执行 watch、不触碰硬件、不修改 backend、不 claim action。

## 验收标准

1. 默认 backend 仍是 `markdown`。
2. backend matrix 清楚覆盖 `markdown` / `sqlite` 的核心行为。
3. SQLite readiness 文档给出是否建议下一阶段默认切换的判断。
4. agent/tool/gui 不新增任何硬件执行入口。
5. `watch` 仍是唯一 claim + `SafetyGate` + `driver.execute` 侧。
6. safety boundary 测试通过。
7. 全量 `pytest` 通过。
8. 完成 `docs/session-handoff-b3.7-sqlite-readiness.zh-CN.md`，记录实际完成范围、矩阵覆盖、readiness 结论、新增 CLI/doctor/state-check 情况、测试结果、未完成事项与下一步建议。
