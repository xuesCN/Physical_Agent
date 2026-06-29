# Session Handoff：P1.5 Tool Loop 接入

> 目的：记录本轮把 proposal-only OpenAI tool loop 接入明确入口的实现与验证结果。  
> 结论：显式 `tool_loop` / `openai_tool_loop` chat planner 可用，默认 planner/chat/CLI 行为保持不变。

## 本轮目标

执行 P1.5/P2 的最小范围：

- 将 `physical_agent/agent/tool_loop.py` 接入一个明确入口。
- 默认关闭，不改变 `auto` / `llm` / `rule_based` chat 行为。
- tool loop 只能 dispatch proposal-only MCP 工具：
  - `physical_agent_submit_task`
  - `physical_agent_propose_action`
  - `physical_agent_get_state`
- 补 `submit_task` tool 端到端测试，确认只写 pending action，不改变 completed/cancelled，不触发 `driver.execute`。
- 保持 Chat Completions / Responses 双模式和静态安全边界测试通过。

## 实际完成内容

- `ChatRuntime` 新增显式 `tool_loop` / `openai_tool_loop` planner 模式。
- CLI `chat --planner` 复用现有参数作为显式入口，只更新 help 文案。
- `PhysicalAgentMCP.submit_task()` 改为只追加 pending actions，并保留既有 pending/completed/cancelled action board。
- `submit_task` tool 增加端到端测试：
  - mock OpenAI 返回 `physical_agent_submit_task` tool call。
  - 经过 `ChatRuntime(planner_name="tool_loop")` / `ChatRuntime(planner_name="openai_tool_loop")`。
  - planner 生成 `observe` pending action。
  - completed/cancelled 保持原样。
  - monkeypatch `MockArmDriver.execute`，确认未被调用。
- 复核 OpenAI 官方 docs 后维持当前最小兼容：
  - Chat Completions 使用 `tools: [{type:"function", function:{...}}]`。
  - Responses 使用扁平 function tool spec，并通过 `function_call_output` + `call_id` 回传结果。

## 修改文件

本轮新增/修改的主要文件：

- `docs/next-session-p1.5-tool-loop.zh-CN.md`
- `docs/session-handoff-p1.5-tool-loop.zh-CN.md`
- `physical_agent/agent/chat_runtime.py`
- `physical_agent/cli.py`
- `physical_agent/mcp/server.py`
- `tests/test_tool_loop.py`

工作树仍包含上一轮已有未提交改动/新增文件，不要回滚：

- `physical_agent/agent/tool_loop.py`
- `physical_agent/llm/openai_compatible.py`
- `physical_agent/mcp/server.py` 中 P1 safe tool specs
- `tests/test_safety_boundaries.py`
- `tests/test_mcp_server.py`
- `tests/test_driver_contract.py`
- `tests/test_openai_compatible.py`
- `docs/session-handoff-p0-p1-d0.zh-CN.md`
- `docs/architecture-boundaries.zh-CN.md`
- `docs/optimization-spec.zh-CN.md`

## 入口设计

入口选择：`ChatRuntime` 显式 planner 模式。

用法：

```powershell
.\.venv\Scripts\physical-agent.exe chat --planner tool_loop --message "look around"
.\.venv\Scripts\physical-agent.exe chat --planner openai_tool_loop --message "look around"
```

行为：

1. `ChatRuntime.respond()` 仍先保留既有 code/integration 路由。
2. 仅当 `_mode()` 解析到 `tool_loop` 时调用 `OpenAIToolLoop`。
3. `OpenAIToolLoop` 读取 `PhysicalAgentMCP.tool_specs()`，只暴露 proposal-only 白名单工具。
4. 工具执行后，`ChatRuntime` 读取新增 pending actions，写入 `PLAN.md` 和 assistant chat message。
5. 默认不执行；只有用户显式传 `auto_step=True` 时才沿用既有 watch step 路径。

默认行为：

- `--planner auto` 仍是默认。
- `auto` 仍只尝试 LLM，否则回退 `rule_based`。
- `llm` / `rule_based` 既有行为不变。
- CLI `run` 未接入 tool loop。

## 安全边界

安全边界未变化。

仍然保持：

```text
agent / chat / llm / gui 请求侧 -> 只能提出动作意图
Markdown workspace              -> 当前协议黑板
watch                           -> 唯一加载 driver、运行 SafetyGate、调用 driver.execute 的执行侧
```

真实执行路径仍是：

```text
proposal -> ACTIONS.md -> watch -> SafetyGate.validate() -> driver.execute(action)
```

`tool_loop` 只 dispatch：

- `physical_agent_submit_task`
- `physical_agent_propose_action`
- `physical_agent_get_state`

没有新增 driver import、硬件 SDK 调用或 agent/tool 侧执行入口。

## 测试命令和结果

相关子集：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_tool_loop.py
```

结果：

```text
5 passed in 3.96s
```

安全/工具/OpenAI/chat 子集：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_safety_boundaries.py tests\test_tool_loop.py tests\test_mcp_server.py tests\test_openai_compatible.py tests\test_chat_runtime.py
```

结果：

```text
19 passed in 6.40s
```

全量测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
97 passed in 25.57s
```

## 未完成事项

- 未做 Agents SDK 迁移。
- 未引入 StateStore / SQLite。
- 未引入 FastAPI / React GUI。
- 未改变 `AgentRuntime.run_task()` 的默认 CLI `run` 行为；本轮只让 MCP `submit_task` 在 tool loop 路径中追加 pending 并保留 action board。
- 未专项修复既有中文 mojibake。

## 下一步建议

建议优先做 A3 rolling summary。

理由：

- P1.5 已把 proposal-only tool loop 接到显式入口，A3 可以继续沿 agent/chat 上下文方向做轻量增强。
- StateStore 抽象属于 B1，会牵动 workspace 读写接口和测试矩阵，范围明显更大。
- 做 A3 时仍要遵守 §0：摘要不能承载 safety/world/pending/approval 等安全关键事实，这些必须继续从结构化 state 实时读取。
