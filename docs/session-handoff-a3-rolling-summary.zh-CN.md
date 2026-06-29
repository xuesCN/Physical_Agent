# Session Handoff：A3 Rolling Summary

> 目的：记录本轮给 `ChatRuntime` / `tool_loop` 增加最小上下文压缩的实现与验证结果。  
> 结论：rolling summary buffer 已接入 `CHAT.md` 和 LLM/tool_loop 上下文；默认短对话行为保持不变，安全关键事实仍实时读 workspace。

## 本轮目标

执行 A3 最小范围：

- 保留最近 K 条 chat message 原文，默认 K=12。
- 更旧消息维护为 `running_summary`。
- 首版使用 simple summary，不依赖 LLM。
- LLM chat 和 OpenAI `tool_loop` 上下文同时包含：
  - `running_summary`
  - 最近 K 条 `chat_history`
  - 当前 capabilities/world/feedback/memory，均实时读取 workspace
- 不做 StateStore / SQLite、FastAPI / React、Agents SDK 迁移或任何硬件执行入口。

## 实际完成内容

- 新增 `physical_agent/protocol/chat_summary.py`：
  - `DEFAULT_RECENT_CHAT_MESSAGES = 12`
  - `DEFAULT_CHAT_SUMMARIZE_THRESHOLD = 24`
  - `compact_chat_messages()` 超阈值后把更旧消息写入 simple running summary。
  - 一旦已有 `running_summary`，后续追加会持续维持最多 12 条原文，避免第 13 条既不在 summary 也不在最近上下文中。
- 扩展 `CHAT.md` 协议：
  - `render_chat()` 新增 `## Running Summary` YAML section。
  - `parse_chat()` 返回 `running_summary`，并兼容旧版没有 summary section 的 `CHAT.md`。
  - `Workspace.write_chat()` / `append_chat_message()` 自动维护 rolling summary。
- `ChatRuntime` 上下文接入：
  - LLM chat payload 新增 `running_summary`。
  - `tool_loop` payload 新增 `running_summary`。
  - 两条路径的 `chat_history` 都统一使用最近 12 条原文。
  - capabilities/world/feedback/memory 继续在每轮从 workspace 实时读取。
- 补充测试：
  - chat render/parse summary roundtrip。
  - 超过阈值触发 running summary。
  - 最近 12 条消息保留，压缩后继续追加仍保持窗口。
  - LLM chat 构造上下文包含 summary，并使用实时 capabilities/world/feedback/action board。
  - tool_loop 构造上下文包含 summary，并使用实时 capabilities。

## 安全边界

安全边界未变化：

```text
agent / chat / llm / gui 请求侧 -> 只能提出动作意图
Markdown workspace              -> 当前协议黑板
watch                           -> 唯一加载 driver、运行 SafetyGate、调用 driver.execute 的执行侧
```

`running_summary` 只压缩对话叙事，不承载安全关键事实。SAFETY、world、pending actions、approval、capabilities 仍必须从 workspace / 结构化 state 实时读取，不能依赖摘要。

本轮没有新增 driver import、硬件 SDK 调用、`driver.execute` 调用或请求侧执行入口。

## 修改文件

- `docs/next-session-a3-rolling-summary.zh-CN.md`
- `docs/session-handoff-a3-rolling-summary.zh-CN.md`
- `physical_agent/protocol/chat_summary.py`
- `physical_agent/protocol/renderers.py`
- `physical_agent/protocol/parsers.py`
- `physical_agent/protocol/workspace.py`
- `physical_agent/agent/chat_runtime.py`
- `tests/test_chat_protocol.py`
- `tests/test_chat_runtime.py`
- `tests/test_tool_loop.py`

## 测试命令和结果

相关子集：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_chat_protocol.py tests\test_chat_runtime.py tests\test_tool_loop.py tests\test_safety_boundaries.py
```

结果：

```text
14 passed in 4.94s
```

全量测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
99 passed in 22.90s
```

## 未完成事项

- 未做 StateStore / SQLite。
- 未做 FastAPI / React。
- 未做 Agents SDK 迁移。
- 未新增文件上传摄入。
- 未专项修复既有中文 mojibake。

## 下一步建议

两个自然方向：

1. StateStore 抽象：进入 B1，把当前 Markdown workspace 背后的读写契约抽出来，为 SQLite 矩阵测试做准备。
2. 文件上传摄入：进入 B4b，但要把上传内容视为不可信输入，只能影响提案上下文，动作仍走 SafetyGate。

若优先控制架构风险，建议先做 StateStore 抽象；若优先提升用户可用性和上下文资料能力，可以先做文件上传摄入。
