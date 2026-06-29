# Next Session：A3 Rolling Summary

> 背景：P1.5 tool_loop 已接入 `ChatRuntime` 显式入口，且默认关闭；默认 `auto` / `llm` / `rule_based` chat 行为应保持不变。

## 本轮目标

实现最小 rolling summary buffer：

- 默认保留最近 12 条 chat message 原文。
- 更旧消息维护为 `running_summary`。
- 首版使用 simple summary，不强依赖 LLM。
- LLM chat 与 `tool_loop` 构造上下文时同时包含 `running_summary`、最近 K 条消息，以及实时读取的 capabilities/world/feedback/memory。

## 禁止做

- 不做 StateStore / SQLite。
- 不做 FastAPI / React。
- 不做 Agents SDK 迁移。
- 不新增任何硬件执行入口。

## 安全红线

`running_summary` 只用于对话叙事压缩。SAFETY、world、pending actions、approval、capabilities 必须实时读取 workspace 或结构化状态，不能依赖摘要。

## 验收标准

1. 默认短对话行为不变。
2. 长对话超过阈值后触发 rolling summary。
3. 最近 K 条 chat message 原文仍保留。
4. safety/world/capabilities/action board/feedback 仍实时读 workspace。
5. `tool_loop` / LLM chat 构造上下文时包含 `running_summary`。
6. 静态安全边界测试通过。
7. 全量 `pytest` 通过。
