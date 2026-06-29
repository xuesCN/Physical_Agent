# Next Session Brief：P1.5 Tool Loop 接入

## 背景

P0 + P1 + D0 已完成：

- P0：冻结 agent/watch/driver 安全边界与验收口径。
- P1：新增 proposal-only OpenAI tool loop，支持 Chat Completions / Responses 工具调用形态。
- D0：`PhysicalDriver` 预留默认 no-op `heartbeat()` / `halt()`。

当前已有：

- proposal-only tool loop：`physical_agent/agent/tool_loop.py`。
- MCP safe tool specs：`PhysicalAgentMCP.tool_specs()` 只暴露提案类工具。
- 静态安全边界测试：扫描请求侧 import/call graph，防止 agent/llm/gui 导入 driver 或调用 `driver.execute`。
- driver heartbeat/halt no-op：为后续硬件 watchdog 预留 contract，不改变当前执行路径。

核心安全路径保持不变：

```text
proposal -> ACTIONS.md -> watch -> SafetyGate.validate() -> driver.execute(action)
```

## 本轮目标

把 `physical_agent/agent/tool_loop.py` 接入一个明确入口，但默认关闭。

优先选择最小改动入口：

- `ChatRuntime` 支持显式 planner/mode：`tool_loop` 或 `openai_tool_loop`。
- 或 CLI 增加显式选项/命令。

默认 planner/chat/CLI 行为必须保持不变。

## 必读清单

1. `docs/session-handoff-p0-p1-d0.zh-CN.md`
2. `HANDOFF.zh-CN.md`
3. `README.zh-CN.md` 中项目启动、Markdown workspace 协议、agent/watch/driver/safety 边界相关部分
4. `docs/architecture-boundaries.zh-CN.md`
5. `docs/optimization-spec.zh-CN.md` 的 §0、§3、§9、§10
6. `git status` / `git diff`

## 允许做

- 在 `ChatRuntime` 增加显式 `tool_loop` / `openai_tool_loop` planner 模式，或在 CLI 增加显式选项/命令。
- 为 `physical_agent_submit_task` / `physical_agent_propose_action` / `physical_agent_get_state` 做端到端工具循环测试。
- 为 `submit_task` 补测试：mock OpenAI 返回 tool call，agent/planner 只写 pending action，completed/cancelled 不变化，不触发 `driver.execute`。
- 对 Chat Completions / Responses tool loop 做最小兼容修复。

## 禁止做

- 不做 Agents SDK 迁移。
- 不引入 StateStore / SQLite。
- 不引入 FastAPI / React GUI。
- 不向 agent/tool 暴露任何 driver 或硬件 SDK 执行入口。
- 不绕过 watch，不改变 `ACTIONS.md -> watch -> SafetyGate -> driver.execute` 的执行路径。

## 验收标准

1. 默认 planner/chat/CLI 行为不变。
2. 显式 `tool_loop` / `openai_tool_loop` 模式可用。
3. tool loop 只 dispatch proposal-only 工具：
   - `physical_agent_submit_task`
   - `physical_agent_propose_action`
   - `physical_agent_get_state`
4. `submit_task` tool 有端到端测试：
   - mock OpenAI 返回 `submit_task` tool call。
   - agent/planner 只写 pending action。
   - completed/cancelled 不变化。
   - 不触发 `driver.execute`。
5. `propose_action` / `get_state` 现有 tool loop 测试仍通过。
6. Chat Completions / Responses 双模式仍通过。
7. 静态安全边界测试仍通过。
8. 全量 `pytest` 通过。
