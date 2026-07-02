# 原 README 功能兼容性审核（重构后逐条判断）

> 检查清单来源：`git show 8fa197a:README.zh-CN.md`（重构前原始中文 README，427 行）
> 对照对象：当前 HEAD `25c41e1` 的实际代码
> 图例：✅ 仍可实现（未变） · ⚠️ 有变化但仍可实现 · ❌ 不再可实现
> 说明：标 ⚠️ 的绝大多数是"默认值变了但功能保留"，非功能删除。

---

## 0. 总结论

**原 README 描述的功能，重构后基本全部保留，没有硬回归。** 唯一的实质性变化是**状态存储默认从 Markdown 切成 SQLite**（原 README 自称"Markdown 原生运行时"）——但 Markdown backend、Markdown 协议、`test_e2e_markdown_loop` 都保留，显式 `workspace.backend: markdown` 即可回到原行为。其余命令、driver、安全边界、planner、chat、MCP、硬件接入助手全部在位，且多为增强。

> 有一项无法在本环境运行时验证：quickstart smoke test（本沙箱 Python 3.10，项目需 ≥3.11）。判断依据为代码在位 + 重构各轮 handoff 记录测试通过。

---

## 1. 核心原则 / 硬边界

| 原 README 语句 | 判断 | 依据 |
| --- | --- | --- |
| "Agent can propose actions. Watch decides whether/how they touch the physical world." | ✅ | 这是重构全程冻结的不变量（P0）；`agent` 仍不 import driver |
| agent 不导入 driver / 不调硬件 SDK / driver 不解析 Markdown / driver 不调 agent | ✅ | 有专门的 import 静态边界测试 `test_safety_boundaries.py` |
| watch 是唯一执行物理动作的路径；safety gate 在 watch 侧 | ✅ | `watch/runtime.py` + `watch/safety.py` 未变；claim/execute 仍只在 watch |

## 2. 核心架构（双进程）

| 语句 | 判断 | 依据 |
| --- | --- | --- |
| `physical-agent watch` 物理侧守护：读 yaml、初始化 workspace、加载 driver、发布 CAPABILITIES、更新 WORLD、监听 ACTIONS、safety gate、execute、写 FEEDBACK、追加 LOG | ✅ | `watch` 命令在；流程未变（现走 StateStore，行为等价） |
| `physical-agent run` / `chat` 认知侧：读 workspace、理解任务、写 ACTIONS | ✅ | `run` / `chat` 命令在 |
| chat 自动识别代码类请求（改文件/写测试/修 bug/接 SDK），在仓库内改文件、跑测试、记 lessons | ✅ | `agent/code_runtime.py` / `skills.py` / `code_router.py` 均在 |

## 3. 快速开始

| 语句 | 判断 | 依据 |
| --- | --- | --- |
| `python scripts/bootstrap.py` 一键装配 | ✅ | `scripts/bootstrap.py`（及 .ps1/.sh）在 |
| `pip install -e .[dev]` + `physical-agent setup --smoke-test` | ✅ | `[dev]` extra 在；`setup --smoke-test` 命令在（运行时未在本环境验证，见 §0） |
| 默认 quickstart 用内置 `mock_arm`，不需硬件/不需 key | ✅ | 默认 config 仍是 `arm_1: mock_arm` |
| `physical-agent gui` 默认 `http://127.0.0.1:8765` | ✅ | `gui` 命令在，默认端口 8765 |
| GUI 能：setup/reset/start watch/run step/demo/chat/切换 English 中文/查看 robots·world·actions·feedback/输入 SDK 生成 driver/选脚手架或 LLM 草稿 | ⚠️ | **旧 GUI（`physical-agent gui`）全部保留**；重构另加了新的 React 仪表盘（`physical-agent api`），但新 GUI **缺 reset**（见 `readme` 无关的重置欠账）。原 README 指向的旧 GUI 功能不受影响 |
| `physical-agent gui --no-open` | ✅ | 参数在 |
| 双终端：`watch` + `run --task "..."` + `inspect` | ✅ | 三命令均在 |

## 4. Workspace 协议

| 语句 | 判断 | 依据 |
| --- | --- | --- |
| `workspace/*.md` 是 v1 核心通信协议（TASK/CAPABILITIES/WORLD/ACTIONS/FEEDBACK/SAFETY/LOG/CHAT/PLAN/MEMORY + artifacts） | ⚠️ | **默认改为 SQLite `state.db`**；这些"文档"作为 StateStore 的逻辑单元保留，`export-audit` 可导出人类可读视图；`workspace.backend: markdown` 可回到原生 `*.md` |
| 每个协议文件用 YAML front matter，正文自然语言 + fenced YAML | ⚠️ | 仅在 `backend: markdown` 下成立；SQLite 下等价语义以 JSON 存储 |
| 静态配置放 `physical-agent.yaml`，动态状态放 workspace | ✅ | 未变（动态状态现默认在 `state.db`） |
| `SAFETY.md` 人类拥有、watch 强制执行 | ✅ | 即便 SQLite backend，`SAFETY.md` 仍作为文件真源保留 |

## 5. Driver Contract

| 语句 | 判断 | 依据 |
| --- | --- | --- |
| 接入只需 `physical_driver.yaml` + `driver.py`（实现 `PhysicalDriver`） | ✅ | `drivers/base.py` 契约在（新增 no-op `heartbeat/halt`，向后兼容） |
| `physical-agent driver new my_arm_driver` 生成空模板 | ✅ | `driver` 子命令 + `new`（`create_driver_template`）在 |
| `physical-agent.yaml` 用本地 driver：`driver: ./my_arm_driver` | ✅ | loader 支持本地目录 driver，未变 |
| driver 只和 watch 交互 / 不解析 Markdown / 不调 agent | ✅ | 边界未变 |

## 6. 硬件接入助手

| 语句 | 判断 | 依据 |
| --- | --- | --- |
| `integrate ./sdk` / `integrate https://github.com/...` 确定性脚手架 | ✅ | `integrate` 命令 + `agent/onboarding.py` 在 |
| `chat --message "帮我接入 ./vendor_sdk"` | ✅ | chat 的接入意图路由在（`_looks_like_integration_request`） |
| 生成 `physical_driver.yaml/driver.py/README/integration-report.md` | ✅ | onboarding 生成物未变 |
| `--llm` LLM coding：读 SDK 上下文写 driver、mock 验证、生成 `llm-coding-report.md` | ✅ | `agent/driver_coder.py` 在 |
| 小智 MCP 示例与教程链接 | ✅ | `examples/xiaozhi_mcp_hardware` + `docs/xiaozhi-driver-tutorial` 在 |

## 7. 内置 Drivers

| 语句 | 判断 | 依据 |
| --- | --- | --- |
| `mock_arm` 支持 observe/move_to/pick/place | ✅ | `drivers/mock_arm.py` 在，能力未变 |
| 任务 "pick the red block and place it on the tray" → pick+place，`red_block.location=tray` | ✅ | 默认 objects 未变（rule_based demo 逻辑在） |
| `mock_rover` 支持 observe/move_to | ✅ | `drivers/mock_rover.py` 在 |

## 8. Safety Gate

| 语句 | 判断 | 依据 |
| --- | --- | --- |
| 执行前校验 robot/capability/params schema/constraints/safety rules/human approval/重复 id/depends_on | ✅ | `watch/safety.py` + `test_safety.py` 未变 |
| 校验失败不调 driver，写 feedback、追加日志、移出 pending | ✅ | 未变（重构还补了失败恢复 B3.6，更强） |

## 9. Rule-Based Planner

| 语句 | 判断 | 依据 |
| --- | --- | --- |
| observe/move/pick/place 关键词映射；无 key 也能跑通完整 loop | ✅ | `agent/rule_based.py` 在；默认 planner 仍是 rule_based |

## 10. OpenAI 兼容 API 和 Chat Agent

| 语句 | 判断 | 依据 |
| --- | --- | --- |
| 用 OpenAI-compatible Chat Completions 规划/对话，边界不变 | ✅ | `llm/openai_compatible.py` 在（仍 urllib，官方 SDK 未换，功能等价） |
| `.env`：`GPT_URL/GPT_KEY/GPT_MODEL`，兼容 `OPENAI_*` | ✅ | `from_env()` 变量名未变 |
| `physical-agent llm-test [--model ...]` | ✅ | `llm-test` 命令在 |
| `physical-agent chat` / `chat --message` / `chat --planner llm --auto-step` | ✅ | chat 命令与参数在 |
| `--planner auto` 优先 LLM、失败回退 rule-based；错误分类提示 | ✅ | `_mode()` + fallback 逻辑在 |
| `physical-agent.yaml` 设 `agent.planner: llm` / `model` | ✅ | 配置项在（新增 `tool_loop` 选项） |

## 11. MCP 扩展点

| 语句 | 判断 | 依据 |
| --- | --- | --- |
| `physical_agent/mcp/server.py` 轻量 facade：`submit_task/get_state/list_robots/run_action` | ✅ | 四方法均在（另加 `propose_action`/`tool_specs`；`submit_task` 现为 proposal-only，语义更安全） |
| v1 不把完整 MCP 依赖放进核心 loop | ✅ | 仍是 dependency-free facade |

## 12. 开发和测试

| 语句 | 判断 | 依据 |
| --- | --- | --- |
| `pip install -e .[dev]` / `pytest -q` | ✅ | `[dev]` extra 在（新增 `httpx`）；测试从 ~85 扩到 35 个测试文件 |
| 覆盖：协议 parser/renderer、workspace revision、driver manifest/loader、接入助手、LLM driver coding、safety gate 拒绝、mock arm、rule-based、watch step、端到端 loop、doctor、GUI endpoints、chat memory/action/auto-step | ✅ | 对应测试文件均在，且新增 backend 矩阵/传输/工具循环/API/检索测试 |

## 13. Clean-Room 声明

| 语句 | 判断 | 依据 |
| --- | --- | --- |
| 独立实现声明 | ✅ | 文档性声明，不受重构影响 |

---

## 14. 需要更新原 README 的地方（表述已过时，非功能缺失）

1. **"Markdown 原生运行时" / "workspace/*.md 是核心协议"**：默认已是 SQLite。建议改为"默认 SQLite 状态存储，Markdown 协议向后兼容（`workspace.backend: markdown`）"。（当前仓库的 `README.zh-CN.md` 已在 B3.8 部分更新，可核对是否到位。）
2. **GUI 段落**：可补充新增的 `physical-agent api` React 仪表盘 + `/api/upload` + SSE；并标注新 GUI 暂缺 reset（欠账，见计划 A1.7）。
3. **可选能力**：`.[server]`（FastAPI）、`.[serial]`（pyserial）、记忆检索、文件摄入等新命令（`api/export-audit/state-check/migrate-md-to-sqlite/ingest-file/search-memory`）原 README 未提。

---

## 15. 结论

- **功能层面：原 README 的每一条都仍可实现**，无删除。
- **默认行为层面：仅"状态存储默认 Markdown → SQLite"一处变化**，且可显式回退。
- **文档层面：原 README 有 3 处表述过时**（§14），建议同步。
- **未运行时验证项：quickstart smoke test**（受本环境 Python 版本限制），建议你在本机 `py scripts/bootstrap.py` 复核一次。

*本审核以代码在位性 + 边界保持性为主，逐条对照原 README 语句；运行时行为以本机 bootstrap 为准。*
