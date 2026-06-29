# Next Session: B1 StateStore Abstraction

## 背景

P1.5 tool_loop 和 A3 rolling summary 已完成。当前系统已经具备显式 proposal-only OpenAI tool loop 入口，并在 `CHAT.md` 中维护 rolling summary 上下文。

安全边界保持不变：agent / chat / LLM / GUI 只能提出动作意图，真实执行路径仍是 `proposal -> ACTIONS.md -> watch -> SafetyGate.validate() -> driver.execute(action)`。

## 本轮目标

执行 B1 StateStore 抽象第一阶段：只抽象 workspace 读写契约，让核心 runtime 通过 `StateStore` / factory 获取状态存储对象。

Markdown workspace 仍是默认实现和当前唯一实现。现有 Markdown 文件协议、parser/renderers、rolling summary 行为和 tool_loop 行为必须保持不变。

## 禁止做

- 不实现 SQLite。
- 不迁移 SQLite 为真源。
- 不删除 Markdown parser/renderers。
- 不做 FastAPI / React GUI 迁移。
- 不做 Agents SDK 迁移。
- 不做文件上传摄入。
- 不新增任何 agent/tool 侧硬件执行入口。

## 安全红线

`watch` 仍是唯一加载 driver、运行 `SafetyGate`、调用 `driver.execute` 的执行侧。agent / llm / gui / mcp 侧不得导入硬件 driver，不得调用 `driver.execute`，不得绕过 pending action + SafetyGate 流程。

## 验收标准

1. 默认配置行为完全不变。
2. Markdown workspace 仍是默认协议和存储实现。
3. 核心 runtime 不再直接依赖具体 `Workspace` 构造，而通过 `StateStore` factory。
4. 不引入 SQLite。
5. 不删除 parser/renderers。
6. `agent` / `llm` / `gui` 仍不导入 driver、不调用 `driver.execute`。
7. `open_state_store` 默认返回 `MarkdownStateStore`，不支持的 backend 明确报错。
8. `AgentRuntime` / `ChatRuntime` / `WatchRuntime` 通过 store factory 仍跑通。
9. 现有 Markdown loop 测试和 safety boundary 测试仍通过。
10. 全量 `pytest` 通过。
