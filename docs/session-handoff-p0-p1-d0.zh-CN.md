# Session Handoff：P0 + P1 + D0

> 目的：给下一轮 Codex session 提供上一轮优化工作的交接上下文。  
> 适用下一步：P1.5/P2，将 proposal-only OpenAI tool loop 接入明确入口，默认关闭。

## 本轮完成范围

上一轮已完成 P0 + P1 + D0，没有做 Agents SDK 迁移，也没有引入 StateStore/SQLite/FastAPI/React 大迁移。

- P0：冻结安全边界与验收。
- P1：新增 proposal-only OpenAI tool loop，并扩展 OpenAI-compatible 客户端。
- D0：给 `PhysicalDriver` 预留默认 no-op `heartbeat()` / `halt()`。

核心边界仍然是：

```text
agent / llm / gui 请求侧 -> 只能提出动作意图
Markdown workspace       -> 当前协议黑板，继续保留
watch                    -> 唯一加载 driver、运行 SafetyGate、调用 driver.execute 的执行侧
```

真实执行路径仍是：

```text
proposal -> ACTIONS.md -> watch -> SafetyGate.validate() -> driver.execute(action)
```

## 主要改动文件

- `physical_agent/agent/tool_loop.py`
  - 新增 `OpenAIToolLoop`。
  - 支持 Chat Completions tool calls 和 Responses API function calls。
  - 只 dispatch proposal-only 工具。

- `physical_agent/llm/openai_compatible.py`
  - 保留 Chat Completions / Responses 双模式。
  - 支持 structured JSON。
  - 增加 tool-loop 需要的底层 create 方法。

- `physical_agent/mcp/server.py`
  - 增加 `propose_action()`。
  - `run_action()` 保留为 `propose_action()` 的兼容别名。
  - `tool_specs()` 暴露 proposal-only tools。
  - 增加 `physical_agent_get_state` 工具。

- `physical_agent/drivers/base.py`
  - `PhysicalDriver` 增加默认 no-op：
    - `heartbeat()`
    - `halt()`

- `docs/architecture-boundaries.zh-CN.md`
  - 记录当前安全边界、tool loop 白名单、静态测试 allowlist、D0 contract。

- 新增测试：
  - `tests/test_safety_boundaries.py`
  - `tests/test_tool_loop.py`
  - `tests/test_driver_contract.py`
  - `tests/test_mcp_server.py`

## Tool Loop 白名单

`OpenAIToolLoop` 只允许这些工具名：

- `physical_agent_submit_task`
- `physical_agent_propose_action`
- `physical_agent_get_state`

这些工具只能读 workspace 或写 pending action。它们不得导入 driver，不得调用硬件 SDK，不得执行硬件动作。

## 当前静态边界 allowlist

`tests/test_safety_boundaries.py` 扫描 `physical_agent/agent`、`physical_agent/llm`、`physical_agent/gui`。

当前允许的例外：

- `physical_agent/agent/onboarding.py`
  - 可 import `physical_agent.drivers.templates`
  - 原因：只复用 inert driver scaffold 模板，不加载或执行硬件。

- `physical_agent/agent/driver_coder.py`
  - 可 import `physical_agent.drivers.loader`
  - 原因：只在临时目录中验证候选 driver。

- `physical_agent/agent/driver_coder.py`
  - 可调用 `loaded.driver.execute`
  - 原因：只执行 mock-mode validation 的 observe action，不属于 agent 请求执行路径。

后续如果要收紧边界，优先把 driver validation 抽到更合适的 validation/watch-side helper。

## 已验证

上一轮汇报的全量测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
95 passed in 23.11s
```

本交接补充复核过新增/相关测试子集：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_safety_boundaries.py tests\test_tool_loop.py tests\test_driver_contract.py tests\test_mcp_server.py tests\test_openai_compatible.py
```

结果：

```text
14 passed
```

## 当前注意事项

- 工作树不是干净基线，下一轮必须先看 `git status` 和 `git diff`。
- 不要回滚已有未提交改动。
- `physical_agent/agent/__init__.py` 之前显示 modified，但内容 diff 为空，疑似行尾/stat 变化。
- 下一轮不应做 Agents SDK 迁移。
- 下一轮不应做 StateStore/SQLite/FastAPI/React 大迁移。
- 下一轮应保持默认 planner/chat/CLI 行为不变。

## 建议下一轮：P1.5/P2

目标：把 `physical_agent/agent/tool_loop.py` 接入一个明确入口，但默认关闭。

优先入口：

- `ChatRuntime` 显式 planner/mode：`tool_loop` 或 `openai_tool_loop`。
- 或 CLI 显式命令/选项。

验收重点：

- 默认 planner/chat/CLI 行为不变。
- 显式 `tool_loop` / `openai_tool_loop` 模式可用。
- `submit_task` tool 有端到端测试。
- pending action 写入正常。
- completed/cancelled 不变化。
- 不触发 `driver.execute`。
- Chat Completions / Responses 双模式仍通过。
- 静态安全边界测试仍通过。
- 全量 pytest 通过。

## 下一轮结束时必须写交接

下一轮完成后，请新增或更新：

```text
docs/session-handoff-p1.5-tool-loop.zh-CN.md
```

内容应包含：

- 本轮目标和实际完成内容。
- 修改文件。
- 入口设计。
- 安全边界是否变化。
- 测试命令和结果。
- 未完成事项。
- 下一步建议：A3 rolling summary 还是 StateStore 抽象。
