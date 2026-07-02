# Physical Agent 系统汇总（按子系统：职责 · 现状 · 欠账）

> 整理时间：2026-07-01 · 对照 HEAD `25c41e1`
> 组织方式：按**子系统/分层**而非单个 .py 文件平铺——这样能同时看到"是什么、现在怎样、缺什么"。
> 状态图例：✅ 稳定 · 🟢 重构新增 · 🟡 部分/降级 · ⚠️ 有缺口

---

## 0. 一句话地图

```
入口层(CLI/API/GUI/MCP) → 认知侧 Agent(只提案) → 状态·协议黑板(StateStore)
                                                        │ 安全边界
                                            执行侧 Watch(唯一碰硬件) → 驱动+传输 → 硬件
```
认知与执行是两个互不引用的进程，只通过黑板通信。

---

## 1. 入口层（Entry）

| 模块 | 职责 | 状态 |
| --- | --- | --- |
| `cli.py`（typer） | 15+ 命令：init/setup/doctor/state-check/gui/api/watch/run/chat/inspect/llm-test/integrate/driver new/export-audit/migrate-md-to-sqlite/ingest-file/search-memory | ✅ |
| `api/server.py`（FastAPI） | proposal-only REST + `/api/chat(/stream/reset/abort)` + settings/llm + upload + events | 🟢 |
| `api/watch_service.py` | 常驻后台 watch + SSE 事件 broker（`--watch` opt-in） | 🟢 |
| `gui/server.py`（旧内联 GUI） | ThreadingHTTPServer + 单文件 HTML，有 Reset / 硬件接入面板 | ✅（旧） |
| `frontend/`（React+AntD+@ant-design/x） | 新仪表盘：Chat/Actions/World/Robots/Memory/Events/Settings/Upload | 🟢 |
| `mcp/server.py` | MCP 形状 facade：submit_task/get_state/list_robots/propose_action/tool_specs（提案专用） | ✅ |

**缺口**：新 React GUI **缺 reset**（→计划 A1.7）、**缺硬件接入面板 + 连接信息**（→A1.8）。

## 2. 认知侧 Agent（只提案，不碰 driver）

| 模块 | 职责 | 状态 |
| --- | --- | --- |
| `agent/runtime.py` | `run_task()`：读能力/世界→planner→写 pending action | ✅ |
| `agent/chat_runtime.py` | chat 主入口：路由 code/接入/planner，写 CHAT/PLAN | ✅ |
| `agent/planner.py`·`rule_based.py`·`llm_planner.py` | 规则 / LLM 结构化 planner | ✅ |
| `agent/tool_loop.py` | OpenAI 工具调用循环（proposal-only 工具白名单） | 🟢 |
| `agent/skills.py`·`code_runtime.py`·`code_router.py`·`code_patch.py`·`code_memory.py` | 代码技能：改文件/跑测试/记 lessons | ✅ |
| `agent/onboarding.py`·`driver_coder.py` | 硬件接入助手：脚手架 / LLM driver 草稿 | ✅（后端在，新 GUI 未接线 → A1.8） |

## 3. LLM 接入

| 模块 | 职责 | 状态 |
| --- | --- | --- |
| `llm/openai_compatible.py` | OpenAI 兼容客户端（**仍 urllib，未换官方 SDK**）+ 结构化输出 + responses 模式 | 🟡（A1 欠账） |
| `llm/settings.py`·`env.py` | 从 `.env` 读 GPT_URL/KEY/MODEL 等 | ✅ |

**缺口**：官方 SDK（A1）、流式、深度思考、多模态、base-url 拼接坑 → 全在计划 A1.0–A1.4。

## 4. 状态 · 协议层（黑板 = 认知↔执行唯一通道）

| 模块 | 职责 | 状态 |
| --- | --- | --- |
| `state/base.py`·`factory.py` | `StateStore` 抽象 + `open_state_store()` | 🟢 |
| `state/sqlite.py` | 默认后端（原子动作/lease/恢复） | 🟢 |
| `state/markdown.py` | Markdown 兼容后端 | ✅ |
| `state/audit.py`·`check.py` | 人类可读导出 / 只读诊断 | 🟢 |
| `protocol/schemas.py` | Action/Observation/Capability/... pydantic 模型 | ✅ |
| `protocol/workspace.py`·`markdown.py`·`parsers.py`·`renderers.py` | Markdown 协议读写（Markdown 后端用） | ✅ |
| `protocol/chat_summary.py` | rolling summary 上下文压缩 | 🟢 |

## 5. 摄入 · 记忆 · 检索

| 模块 | 职责 | 状态 |
| --- | --- | --- |
| `ingest/files.py` | 文本类文件摄入（`ingest-file`/`/api/upload`） | 🟡（**仅文本，PDF 未做**） |
| `protocol/memory.py` | 结构化记忆（kind/tags/importance/过滤） | 🟢 |
| `protocol/retrieval.py` | chunk 存储/查询契约 + **本地确定性关键词检索** | 🟡（**sqlite-vec/embedding 未做**，默认关） |

## 6. 执行侧 Watch（唯一加载 driver / 跑 SafetyGate / 执行）

| 模块 | 职责 | 状态 |
| --- | --- | --- |
| `watch/runtime.py` | setup/step/run_forever：领动作→校验→execute→回写→update_world；心跳/看门狗 | ✅ 🟢(watchdog) |
| `watch/safety.py` | SafetyGate 执行前校验（robot/能力/schema/constraints/依赖/审批/重复） | ✅ |
| `watch/action_watcher.py` | 依赖就绪判断 | ✅ |

## 7. 驱动 + 传输（真正碰硬件的地方）

| 模块 | 职责 | 状态 |
| --- | --- | --- |
| `drivers/base.py` | `PhysicalDriver` 契约（connect/observe/execute/capabilities + no-op heartbeat/halt） | ✅ 🟢(hooks) |
| `drivers/loader.py`·`registry.py`·`manifest.py`·`templates.py` | 加载内置/本地 driver、读 `physical_driver.yaml`、生成模板 | ✅ |
| `drivers/mock_arm.py`·`mock_rover.py` | 仿真 driver | ✅ |
| `drivers/xiaozhi_mcp.py` | 小智 MCP 设备（网络协议客户端） | ✅ |
| `drivers/transport/{base,websocket,serial,loopback}.py` | 传输层抽象 + 串口/WS/回环 | 🟢 |

**缺口**：**ServoBus（Feetech/Dynamixel 舵机协议层）未做**；串口 driver 仍靠厂商 SDK（moce）。→ Phase D2b。

## 8. 配置（yaml）

| 文件 | 位置 | 作用 | 读取方 |
| --- | --- | --- | --- |
| `physical-agent.yaml` | 项目根 | 主配置：workspace/watch/agent/**robots(driver+config, 含 serial_port/endpoint)** | `config.load_config` → 几乎所有模块 |
| `physical_driver.yaml` | 本地 driver 目录 | driver 清单 + config_schema | `manifest.py`→loader→watch |
| 厂商 runtime yaml | 仓库外 | 厂商 SDK 硬件配置 | 仅该 driver + SDK |

**缺口**：`physical-agent.yaml` 未在 GUI 暴露（port/endpoint 藏在这里）→ A1.8c。

## 9. 支撑 / 文档 / 测试

| 项 | 状态 |
| --- | --- |
| `quickstart.py`·`doctor.py`·`scripts/bootstrap.*` | ✅ |
| `tests/`（35 个测试文件：矩阵/传输/工具循环/API/检索/安全边界…） | 🟢 |
| `docs/`（spec / 重构日志 / README 审核 / 各轮 handoff / 本汇总 / A1 计划） | 🟢 |

---

## 10. 欠账总表（跨模块，供排期）

| # | 欠账 | 涉及子系统 | 归属计划 |
| --- | --- | --- | --- |
| 1 | 官方 OpenAI SDK 未换 + base-url 拼接坑 | LLM 接入 | A1.0 |
| 2 | chat 流式 / 深度思考 / abort / 异常分类 | LLM+API+前端 | A1.2–A1.4 |
| 3 | PDF 摄入（现仅文本） | 摄入 | A1.5 |
| 4 | 工作台 LLM 配置（URL/key） | API+前端 | A1.6 |
| 5 | 会话/工作区重置（新 GUI 缺失） | API+前端 | A1.7 |
| 6 | 硬件接入面板 + 机器人连接信息 + 配置面板 | API+前端 | **A1.8** |
| 7 | 真实向量 RAG（sqlite-vec+embedding） | 记忆检索 | spec §4（延后） |
| 8 | ServoBus 舵机协议层 | 驱动传输 | Phase D2b（延后） |
| 9 | 多模态输入 | LLM+摄入 | 延后探索 |
| 10 | C4 独立 zh/EN 切换核实 | 前端 | 待核实 |

---

## 11. 组织方式说明

比起按 60 个 .py 文件平铺，本汇总按**子系统分层**组织，原因：①和架构图/安全边界一一对应，②能把"职责 + 现状 + 欠账"三件事并排看，③欠账能直接映射到计划里程碑（§10）。若需要，也可再出一份"按 CLI 命令 / 按 API 端点"的视图，但那更偏操作手册，不如子系统视图适合看全局。

*本汇总基于源码实扫；欠账以 spec / 重构日志 / A1 计划为准。*
