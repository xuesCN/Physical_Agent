# Physical Agent 架构安全边界

本文冻结当前优化阶段的安全边界。后续 StateStore、FastAPI、GUI、传输层或记忆系统迁移时，除非另行设计并补测试，否则这些不变量保持不变。

## 核心不变量

```text
agent / chat / llm / gui 请求侧 -> 只能提出动作意图
Markdown workspace              -> 保留为当前协议黑板
watch                           -> 唯一加载 driver、运行 SafetyGate、调用 driver.execute 的执行侧
driver                          -> 只由 watch 持有，不调用 agent runtime，不解析 agent 对话
```

现阶段继续保留 `TASK.md`、`CAPABILITIES.md`、`WORLD.md`、`ACTIONS.md`、`FEEDBACK.md`、`SAFETY.md`、`LOG.md`、`CHAT.md`、`PLAN.md`、`MEMORY.md` 这组 Markdown workspace 协议文件。agent、LLM planner、OpenAI tool loop、GUI 请求处理器都只能写入任务或 action proposal；真实执行路径仍是：

```text
proposal -> ACTIONS.md -> watch -> SafetyGate.validate() -> driver.execute(action)
```

## OpenAI 工具循环边界

`physical_agent/agent/tool_loop.py` 只允许调用 `PhysicalAgentMCP` 暴露的白名单工具：

- `physical_agent_submit_task`
- `physical_agent_propose_action`
- `physical_agent_get_state`

这些工具只能读取 workspace 或写入 pending action。它们不导入 `physical_agent.drivers`、不调用硬件 SDK、不执行动作。模型请求任何非白名单工具时，工具循环必须拒绝。

## 静态边界测试

`tests/test_safety_boundaries.py` 扫描 `physical_agent/agent`、`physical_agent/llm`、`physical_agent/gui`：

- 不允许直接 import `physical_agent.drivers.*`。
- 不允许调用 `driver.execute` 或 `*.driver.execute`。

当前允许的例外必须写在测试 allowlist 中并附理由：

- `agent/onboarding.py` 可 import `physical_agent.drivers.templates`，因为它只复用 driver scaffold 文本模板，不加载或执行硬件。
- `agent/driver_coder.py` 可 import `physical_agent.drivers.loader`，因为它在临时目录中验证候选 driver。
- `agent/driver_coder.py` 可调用 `loaded.driver.execute`，但仅限 mock-mode validation 的 observe action，用于证明生成 driver 可加载；这不是请求侧执行路径。

## D0 driver contract

`PhysicalDriver` 预留默认 no-op：

```python
async def heartbeat(self) -> None: ...
async def halt(self) -> None: ...
```

现阶段 watch 不强制启用硬件 watchdog，也不向 agent 暴露 E-stop 工具。后续 D3 若接入常驻 watch/硬件心跳，仍必须保持调用方向为 `watch -> driver -> hardware`。
