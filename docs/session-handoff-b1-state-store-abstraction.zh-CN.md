# Session Handoff：B1 StateStore Abstraction

> 目的：记录本轮把 workspace 读写契约抽象为 `StateStore` 的第一阶段实现与验证结果。
>
> 结论：核心 runtime 已通过 factory 获取状态存储；默认和唯一实现仍是 Markdown workspace，文件格式、rolling summary、tool_loop 和 watch 执行边界保持不变。

## 实际完成范围

- 新增 `physical_agent/state/` 层：
  - `StateStore` Protocol 覆盖当前 `Workspace` 的核心读写、初始化、路径和日志接口。
  - `MarkdownStateStore` 薄包装既有 `Workspace`，所有 Markdown parser/renderers 和 revision 行为继续复用原实现。
  - `open_state_store()` factory 支持传入 `PhysicalAgentConfig + base_dir` 或 `config_path`。
- 扩展配置：
  - `workspace.backend` 默认值为 `markdown`。
  - 默认生成的 `physical-agent.yaml` 会写出 `workspace.backend: markdown`。
  - 非 `markdown` backend 会明确报错；`sqlite` 暂未实现。
- 核心入口改为通过 factory 打开 store：
  - `AgentRuntime`
  - `ChatRuntime`
  - `WatchRuntime`
  - `PhysicalAgentMCP`
  - GUI controller
  - `quickstart`
  - `doctor`
  - CLI `init` / `inspect`
- 保留 `Workspace` 类和既有协议测试直接使用方式，确保 Markdown 协议仍是当前兼容锚点。

## 修改文件

- `docs/next-session-b1-state-store-abstraction.zh-CN.md`
- `docs/session-handoff-b1-state-store-abstraction.zh-CN.md`
- `physical_agent/state/__init__.py`
- `physical_agent/state/base.py`
- `physical_agent/state/markdown.py`
- `physical_agent/state/factory.py`
- `physical_agent/config.py`
- `physical_agent/agent/runtime.py`
- `physical_agent/agent/chat_runtime.py`
- `physical_agent/watch/runtime.py`
- `physical_agent/mcp/server.py`
- `physical_agent/gui/server.py`
- `physical_agent/quickstart.py`
- `physical_agent/doctor.py`
- `physical_agent/cli.py`
- `tests/test_state_store.py`

## StateStore 设计

`StateStore` 目前只抽象现有 Markdown workspace 的读写契约，不引入新的状态模型。接口包含：

- `path` / `artifacts_path` / `file()`，供 watch 和 doctor 保持现有路径行为。
- `initialize()` / `exists()`。
- `read_*` / `write_*`：task、capabilities、world、actions、feedback、safety、chat、plan、memory。
- `append_chat_message()`、`append_memory_note()`、`append_log()`。

`MarkdownStateStore` 持有一个内部 `Workspace` 实例并逐项委托调用，因此：

- Markdown 文件格式不变。
- `CHAT.md` running summary 行为不变。
- `tool_loop` 写 pending action 的路径不变。
- parser/renderers 未删除、未替换。

`open_state_store()` 的 backend 选择逻辑：

- `markdown`：返回 `MarkdownStateStore`。
- 其他值：抛出 `ValueError`，消息明确说明 B1 只支持 Markdown，SQLite 未实现。

## 入口切换情况

已切到 factory：

- `physical_agent/agent/runtime.py`
- `physical_agent/agent/chat_runtime.py`
- `physical_agent/watch/runtime.py`
- `physical_agent/mcp/server.py`
- `physical_agent/gui/server.py`
- `physical_agent/quickstart.py`
- `physical_agent/doctor.py`
- `physical_agent/cli.py` 的 `init` / `inspect`

仍直接使用 `Workspace`：

- `physical_agent/state/markdown.py`：这是 Markdown backend 实现本身，必须包装 `Workspace`。
- `physical_agent/protocol/__init__.py`：继续导出 `Workspace` 以保持协议层兼容。
- `physical_agent/agent/driver_coder.py`：只在临时目录中创建 mock-mode validation workspace，用于验证生成 driver 可加载；它不是用户请求侧执行入口。
- 多个 protocol / driver / runtime 测试仍直接使用 `Workspace` 作为 Markdown fixture，刻意保留以验证旧协议不变。

## 安全边界

本轮未新增 driver import、硬件 SDK 调用或 agent/tool 侧执行入口。真实执行路径仍是：

```text
proposal -> ACTIONS.md -> watch -> SafetyGate.validate() -> driver.execute(action)
```

`agent` / `llm` / `gui` 仍不导入 `physical_agent.drivers.*`，也不调用 `driver.execute`。`watch` 仍是唯一加载 driver、运行 `SafetyGate`、调用 `driver.execute` 的执行侧。

## 测试命令和结果

相关测试集：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_state_store.py tests\test_e2e_markdown_loop.py tests\test_chat_runtime.py tests\test_watch_runtime.py tests\test_tool_loop.py tests\test_mcp_server.py tests\test_safety_boundaries.py
```

结果：

```text
18 passed in 5.04s
```

全量测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
102 passed in 24.96s
```

## 下一步建议

优先级可以在两条路线中选择：

1. **B2 SqliteStateStore**：在当前 factory 后面新增 SQLite backend、后端矩阵测试和迁移命令。适合优先降低状态真源和并发风险。
2. **B4b 文件上传摄入**：把上传内容作为不可信输入接入提案上下文，动作仍必须走 pending action + SafetyGate。适合优先提升上下文资料能力。

若继续控制架构风险，建议先做 B2；若优先提升用户可用性，可以做 B4b，但需要严格继承 §0 的 prompt-injection 和安全边界约束。
