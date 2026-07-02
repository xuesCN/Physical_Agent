# Physical Agent 重构日志（对照 optimization-spec 的完成度评估）

> 整理时间：2026-07-01
> 提交范围：`8fa197a`（重构前基线）→ `25c41e1`（当前 HEAD）
> 对照基准：`docs/optimization-spec.zh-CN.md` v0.3 的 §10 里程碑
> 数据来源：docs 下 26 份 `session-handoff-*` 记录 + git 提交历史 + 源码实测

---

## 1. 总览结论

本轮重构**按 spec 的分阶段顺序（A→B→C→D）落地，且严格遵守了 spec 的两条纪律**：每步小步可回滚、默认关闭/向后兼容、安全边界全程冻结（agent/llm/gui 只提案，watch 唯一执行，SafetyGate 不被绕过）。

完成度速览（详见 §3 矩阵）：

- **已完成**：A2、A3、B1、B2、B3、B4a、B4b(上传摄入)、C1、C2、C3、D0、D1、D2、D3。
- **超出 spec 额外做的**：B3.5 原子动作、B3.6 lease/失败恢复、B3.7 readiness 矩阵、B3.8 默认切 SQLite、C3.1 e2e、C3.2 QA 硬化、D3.1 watchdog 策略、D4 实机文档。
- **部分完成 / 降级实现**：B4（记忆检索——只做了确定性关键词检索地基，**sqlite-vec + 真实 embedding 未做**，默认关闭）、上传摄入（**仅文本类，PDF 未做**）。
- **未做 / 偏离 spec**：**A1 官方 OpenAI SDK 替换（未换，仍用 urllib 客户端）**、**D2b ServoBus（Feetech/Dynamixel 舵机协议层未做）**、C4 显式 zh/EN i18n（mojibake 已随 React 重写消除，独立语言切换待核实）。

一句话：**主干（状态存储 JSON/SQLite、工具循环、上下文压缩、FastAPI 后端、React/AntD 前端、传输层与硬件看门狗）全部落地并加固；两处"重活"（真实向量 RAG、舵机总线协议）按 spec 的"渐进、别过早堆"原则留成了地基；一处（官方 SDK 替换）用现有客户端 + 工具循环替代了。**

---

## 2. 分步重构过程（按提交时间顺序）

| # | 提交 | 阶段 | 做了什么 | 关键产物 |
| --- | --- | --- | --- | --- |
| 1 | `8261e93` | P0/P1/D0 + P1.5 | 冻结安全边界与验收；新增 proposal-only OpenAI tool loop 并接入显式入口；给 `PhysicalDriver` 预留 no-op `heartbeat()`/`halt()` | `agent/tool_loop.py`；`drivers/base.py` 契约扩展 |
| 2 | `0a67ebb` | A3 | 最小上下文压缩：保留最近 K=12 条原文 + `running_summary`（simple，不依赖 LLM），接入 LLM/tool_loop 上下文 | `protocol/chat_summary.py`；扩展 `CHAT.md` |
| 3 | `b193321` | B1 | 抽象 `StateStore` 层，核心 runtime 改经 factory 取状态存储；默认仍 Markdown | `state/`（base/markdown/factory） |
| 4 | `f9728e4` | B2 | opt-in `SqliteStateStore`（标准库 sqlite3）+ `migrate-md-to-sqlite`；`SAFETY.md` 保持文件真源 | `state/sqlite.py` |
| 5 | `d3be149` | B3 | 两 backend 的人类可读 audit export（稳定 pretty JSON + SAFETY 复制）+ `export-audit` | `state/audit.py` |
| 6 | `4698fa0` | B3.5 | action board 原子契约：`append_pending_action` / `claim_next_ready_action` / mark completed/cancelled（SQLite 用 `BEGIN IMMEDIATE`） | `state/*`；`AgentRuntime` 接入 |
| 7 | `46f4079` | B3.6 | SQLite `in_progress` lease + stale recovery；watch 执行异常写终态+反馈，不留永久 in_progress | `SqliteStateStore`；`WatchRuntime.step()` |
| 8 | `1a3c3a4` | B3.7 | backend matrix 测试 + 只读 `state-check` 诊断 + readiness 文档 | `tests/test_backend_matrix.py`；`state/check.py` |
| 9 | `2d33bb4` | B3.8 | 新项目默认 backend 从 markdown 切到 **sqlite**；显式 markdown 仍可用，全套迁移/审计/回滚保留 | `config.py` 默认值 |
| 10 | `5192bc8` | B4a | `MEMORY` 升级为结构化：`kind`/`tags`/`importance` + 可过滤 `read_memory()` | `protocol/memory.py` |
| 11 | `3c68d94` | B4b | 本地文本文件摄入地基：`ingest-file` CLI、upload 元数据审计、小文本 excerpt 写入结构化记忆、标记为不可信上下文 | `ingest/files.py` |
| 12 | `35c0058` | B4c | 检索地基：默认关闭的 retrieval 配置、chunk 存储/查询契约、**本地确定性关键词查询**、`search-memory` CLI、gated `retrieved_context` | `protocol/retrieval.py` |
| 13 | `3cca4bd` | C1 | optional FastAPI 后端，把 StateStore/动作板/记忆/上传/检索/审计暴露为**proposal-only** API；`api` CLI | `api/server.py` |
| 14 | `c7a366e` | C1.1 | 补 API TestClient 测试依赖（`httpx`）与 skip 语义 | `pyproject.toml`；`tests/test_api_server.py` |
| 15 | `77d550a` | C2 | 显式开启的后台常驻 watch（lifespan 懒加载）+ `/api/events` SSE 增量事件 + SQLite 并发测试 | `api/watch_service.py` |
| 16 | `4a496ae` | C3 | React + AntD + `@ant-design/x` dashboard + 浏览器 `POST /api/upload`（≤5MB，仅文本后缀）；FastAPI 托管 `frontend/dist` | `frontend/`；`/api/upload` |
| 17 | `8c6a5cc` | C3.1 | 保留并稳定用户重设计：侧栏导航（Overview/Actions/World/Robots/Memory/Safety/Events/Settings）+ StatusBar + proposal inspector；Playwright e2e | `frontend/e2e/` |
| 18 | `0832c0a` | C3.2 | GUI QA/边界硬化：空/未初始化 workspace、真实上传、SSE 断线可见、上传/表单错误稳定呈现 | `frontend/` |
| 19 | `55addad` | D1 | watch/driver 侧 `Transport` 抽象 + 标准库 `WebSocketTransport`，重构 `xiaozhi_mcp` ws 模式复用 | `drivers/transport/{base,websocket}.py` |
| 20 | `7b1706a` | D2 | `LoopbackTransport` + 可选 `SerialTransport(pyserial)`，为串口 driver 与 ServoBus 打地基 | `drivers/transport/{serial,loopback}.py` |
| 21 | `14c9dcb` | D3 | 把 `heartbeat()`/`halt()` 接入 `WatchRuntime` 常驻循环与关停收尾（`heartbeat_enabled`/`halt_on_shutdown`） | `watch/runtime.py` |
| 22 | `bc12329` | D3.1 | 软件 watchdog 策略：连续 heartbeat 失败计数、阈值触发 best-effort halt、恢复审计 | `watch` 配置 + runtime |
| 23 | `9cb1978` | — | 实机 bring-up 回归 handoff | `docs/session-handoff-hardware-bringup` |
| 24 | `25c41e1` | D4 | 实机准备清单文档收口（不改功能） | `docs/hardware-bringup-checklist.zh-CN.md` |

**贯穿全程的纪律**（与 spec §0/§9 一致）：每步都新增 brief + handoff + 测试；安全边界四条硬约束未被打破；新能力（tool loop、SQLite、上传、检索、常驻 watch、串口）**一律默认关闭或向后兼容**。

---

## 3. 对照 spec §10 里程碑的完成度矩阵

| 里程碑 | 目标 | 状态 | 证据 / 说明 |
| --- | --- | --- | --- |
| **A1** | urllib → 官方 `openai` SDK（行为不变） | ❌ 未做（替代） | `llm/openai_compatible.py` 仍用 `urllib.request`；`openai` 不在依赖里。"完善 agent 运行机制"改由 A2 工具循环在现有客户端上实现 |
| **A2** | tool_loop 工具循环 + import 静态检查 | ✅ 完成 | `agent/tool_loop.py`，显式 `tool_loop`/`openai_tool_loop`；只 dispatch proposal-only 工具；端到端测试确认不触发 `driver.execute` |
| **A3** | 最简上下文压缩（rolling summary） | ✅ 完成 | `protocol/chat_summary.py`，K=12/阈值 24，simple 模式 |
| **B1** | StateStore 抽象，Workspace 改接口实现 | ✅ 完成 | `state/` 层 + factory；核心入口全改经 factory |
| **B2** | SqliteStateStore（JSON 为准）+ 迁移命令 | ✅ 完成 | `state/sqlite.py`（标准库）+ `migrate-md-to-sqlite`；SAFETY 保持文件 |
| **B3** | audit 人类视图 + audit_export | ✅ 完成 | `state/audit.py` + `export-audit`，两 backend 均支持 |
| **B4** | sqlite-vec 记忆分层 + 检索 | 🟡 部分 | 结构化记忆（B4a）+ 检索契约/存储/查询（B4c）已做，但**检索是确定性关键词、默认关闭；sqlite-vec 与真实 embedding 未实现**（源码零 `vec0`/`embedding` 痕迹）——按 spec"先结构化、语料够再开 embedding"留成地基 |
| **B4b** | 文件上传摄入（inline/ingest 两档） | 🟡 大部分 | `ingest/files.py` + `/api/upload` + 浏览器上传已完成；**仅文本后缀，PDF 明确拒绝**（spec 提到的 PDF→抽文本未做） |
| **C1** | FastAPI 端点与旧 server 对等 | ✅ 完成 | `api/server.py`，proposal-only；`api` CLI；未装 server extra 有提示 |
| **C2** | 常驻 watch + WS/SSE 增量推送 + 并发测试 | ✅ 完成 | `api/watch_service.py` + `/api/events` SSE + SQLite 并发测试；`--watch` opt-in |
| **C3** | React + AntD + @ant-design/x 仪表盘 | ✅ 完成（+增强） | `frontend/` 全套；侧栏导航、StatusBar、proposal inspector、上传；Playwright e2e + QA 硬化（C3.1/C3.2） |
| **C4** | 前端 i18n / mojibake 修复 | 🟡 大部分 | 旧内联 HTML 的 `涓枃` mojibake 随 React 全量重写消除；**独立 zh/EN 语言切换是否实现待核实** |
| **D0** | driver contract 预留 heartbeat/halt no-op | ✅ 完成 | `drivers/base.py`，默认 no-op，不影响现有 mock/测试 |
| **D1** | Transport 抽象 + 重构 xiaozhi 复用 WS | ✅ 完成 | `transport/{base,websocket}.py`，xiaozhi ws 模式已复用 |
| **D2** | SerialTransport(pyserial) + 串口 driver 骨架 + Loopback | 🟡 大部分 | `transport/{serial,loopback}.py` 完成；**串口 driver 骨架为"地基"，尚无接入真实串口设备的 driver**（moce 仍走厂商 SDK） |
| **D2b** | ServoBus 薄层（Feetech/Dynamixel） | ❌ 未做 | 源码零 `ServoBus`/`feetech`/`dynamixel` 痕迹；留待后续 |
| **D3** | 看门狗/心跳 + E-stop（挂常驻循环） | ✅ 完成（+D3.1） | `WatchRuntime` 每轮 heartbeat + 关停 halt；D3.1 补失败阈值/触发 halt/恢复审计 |

图例：✅ 完成 · 🟡 部分/降级 · ❌ 未做

**量化**：spec §10 共 18 条里程碑（含 D2b）。完全完成 12 条，部分/降级 4 条（B4、B4b、C4、D2），未做 2 条（A1、D2b）。若按"主干功能可用"口径，完成度约 **83%**（15/18 达到可用），其中两处"重活"（真实向量 RAG、舵机协议）为主动延后。

---

## 4. 偏离与延后项（需要你拍板的欠账）

1. **A1 官方 OpenAI SDK 未替换**：仍是手写 urllib 的 `OpenAICompatibleClient`。工具循环建在它之上，功能上够用；但 spec 里"换官方 SDK"这条没做。若第三方网关兼容性够稳，可维持现状；要标准化再排一轮 A1。
2. **B4 真实向量 RAG（sqlite-vec + embedding）未做**：目前检索是本地确定性关键词、默认关闭。契约/存储/查询/CLI/审计都已就位，接 embedding 是"填实现"而非"改架构"。符合 spec"别过早堆重 RAG"。
3. **上传仅文本、PDF 未做**：`ingest/files.py` 明确拒绝 PDF/二进制。要吃手册类 PDF 需补抽文本。
4. **D2b ServoBus 未做**：只有 Transport 层（serial/loopback/websocket），没有舵机协议薄层，也没有用 SerialTransport 接真实舵机臂的 driver。接标准舵机臂目前仍需像 moce 那样自带厂商 SDK。
5. **C4 独立 zh/EN 切换待核实**：mojibake 已消除，但语言切换开关是否落地建议核对 `frontend/src`。

---

## 5. 亮点：超出 spec 的加固

spec 原本把并发/恢复只写成一句"WAL + 原子领取"，实际重构把它拆成了 **B3.5→B3.6→B3.7→B3.8** 四轮硬化（原子动作 → lease/失败恢复 → readiness 矩阵 → 默认切 SQLite），并配了 `state-check` 诊断与 backend 矩阵测试——这部分**比 spec 更扎实**。GUI 侧也多做了 C3.1 e2e + C3.2 边界硬化，硬件侧多做了 D3.1 watchdog 策略与 D4 实机清单。整体体现了 spec §9"验收先写、每步测试、渐进冻结"的纪律。

---

*本日志基于 docs 下 session-handoff 记录与源码实测整理；完成度判断以 `optimization-spec.zh-CN.md` v0.3 §10 为基准。*
