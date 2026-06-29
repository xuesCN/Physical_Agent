# 下一轮 Brief：B2 SqliteStateStore Opt-in 第一阶段

## 背景

B1 已完成 `StateStore` 抽象，核心 runtime 已通过 `open_state_store()` 获取状态存储。当前默认且唯一可用实现是 `MarkdownStateStore`，它继续包装既有 Markdown workspace、parser、renderer 和 rolling summary 行为。

## 本轮目标

新增 opt-in 的 `SqliteStateStore` 后端和 Markdown -> SQLite 迁移命令。默认 backend 仍保持 `markdown`，SQLite 只在 `workspace.backend=sqlite` 时显式启用。

## 禁止做

- 不把默认真源切到 SQLite。
- 不删除 Markdown parser/renderers。
- 不做 FastAPI/React。
- 不做 Agents SDK。
- 不做文件上传摄入。
- 不新增任何 agent/tool 硬件执行入口。

## 安全红线

`watch` 仍是唯一 driver / `SafetyGate` / `execute` 侧。SQLite 只替换状态存储实现，不改变执行路径：

```text
proposal -> action board -> watch -> SafetyGate.validate() -> driver.execute(action)
```

`SAFETY.md` 继续作为安全规则文件真源，不改为只依赖摘要、缓存或非审计状态。

## 验收标准

1. 默认配置仍是 `markdown`，现有 Markdown 行为不变。
2. `workspace.backend=sqlite` 可显式启用，并通过 `open_state_store()` 返回 `SqliteStateStore`。
3. unsupported backend 继续明确报错。
4. SQLite schema 第一阶段最小可用，覆盖 task/capabilities/world/actions/feedback/chat/plan/memory/log，并保留 `SAFETY.md` 文件真源。
5. Markdown -> SQLite 迁移命令可用，且迁移后不偷偷切换配置。
6. SQLite backend 下 pending/completed/cancelled action board 行为正确。
7. SQLite backend 下 e2e loop、rolling summary、tool_loop proposal-only 覆盖可用或不破坏 Markdown 默认。
8. safety boundary 测试通过，watch 仍是唯一执行侧。
9. 全量 `pytest` 通过。

