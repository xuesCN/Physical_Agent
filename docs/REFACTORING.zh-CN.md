# 重构过程

> 本文浓缩自原 33 份 session-handoff 与 22 份 brief（已删除，git 历史可查）。姊妹文档：`SPEC.zh-CN.md`（目标与待办矩阵）。
> 范围：基线 `8fa197a` → 当前。最后更新：2026-07-06。

## 0. 基线与纪律

起点是一个 Markdown 黑板协议的双进程原型（agent 写提案文件、watch 读文件执行）。全程冻结四条红线：**agent/llm/gui 只提案；watch 唯一执行；SafetyGate 不被绕过；新能力默认关闭或向后兼容**。每轮 session 遵循 brief → 实现 → 测试 → REFACTORING 收口，小步可回滚。

## 1. 阶段速查表

| 阶段 | 里程碑 | 提交 |
| --- | --- | --- |
| P | 安全边界冻结 + 工具循环 + driver 钩子预留 | `8261e93` |
| A3 | rolling summary 上下文压缩 | `0a67ebb` |
| B1-B3 | StateStore 抽象 → SQLite 后端 → audit export | `b193321` `f9728e4` `d3be149` |
| B3.5-B3.8 | 原子动作 → lease 恢复 → 就绪矩阵 → 默认切 SQLite | `4698fa0` `46f4079` `1a3c3a4` `2d33bb4` |
| B4a-c | 结构化记忆 → 文件摄入 → 检索地基 | `5192bc8` `3c68d94` `35c0058` |
| C1-C2 | FastAPI 后端 → 常驻 watch + SSE | `3cca4bd` `c7a366e` `77d550a` |
| C3-C3.2 | React 仪表盘 → e2e → QA 硬化 | `4a496ae` `8c6a5cc` `0832c0a` |
| D1-D2 | Transport 抽象 + WS → Serial/Loopback | `55addad` `7b1706a` |
| D3-D4 | 心跳/halt 挂入循环 → watchdog 策略 → 实机回归与清单 | `14c9dcb` `bc12329` `9cb1978` `25c41e1` |
| A1 | 官方 SDK → 设置/chat 桥 → 流式/abort → B5 收口 → 深思考 | `9c25e90` `affbda7` `605015c` `b5b6071` `3a807e7` |
| E0 | GUI 功能对齐（重置/硬件面板/配置注册） | E0 提交 + `29fb512` |
| W1 | 驱动调用超时保护 | `2f00615` |
| F0 | LLM planner 启用实验 + 本地 JSONL trace + 坏任务报告 | `d39e8f6` `caa4fa0` |
| B6 | 退役 MarkdownStateStore 后端 | `9072b4e` |

## 2. 分阶段过程记录

### P：安全边界冻结 + 工具循环地基

动机：在动任何大结构前，先把"什么不能变"写死。过程：把安全边界固化为验收测试（`test_safety_boundaries` 用 monkeypatch 断言 API/agent 侧永不实例化 WatchRuntime、永不调 `driver.execute`）；新增 `agent/tool_loop.py` 的 `OpenAIToolLoop`——同时支持 Chat Completions tool calls 与 Responses function calls，但**工具白名单只含提案类操作**（submit_task/propose_action/读状态），dispatch 层物理上没有执行路径；`drivers/base.py` 契约预留 no-op `heartbeat()`/`halt()`，为 D 阶段占位且不破坏现有 driver。真实执行路径保持：提案 → 动作板 → watch → SafetyGate → execute。

### A3：上下文压缩

动机：CHAT 无限增长会撑爆 LLM 上下文。过程：`protocol/chat_summary.py` 实现 rolling summary——保留最近 12 条原文，超过 24 条阈值时把更早消息压成 `running_summary` 字段（simple 模式，不依赖 LLM，确定性可测）；CHAT 协议文档扩展 summary 字段；LLM/tool_loop 的上下文组装统一改读"summary + 近期原文"。

### B1-B3：状态存储从文件到 SQLite

动机：Markdown 文件作状态真源没有原子性，并发读写会踩踏。过程分三步走：**B1** 先抽象——定义 `StateStore` Protocol + `open_state_store()` 工厂，把核心 runtime 全部改为经工厂取存储，默认仍是 Markdown（行为零变化，纯重构）；**B2** 再实现——标准库 sqlite3 的 `SqliteStateStore`（不引重依赖），payload 存 JSON，配 `migrate-md-to-sqlite` 迁移命令，**SAFETY.md 刻意保留文件真源**（安全规则不进库，防 API 侧篡改）；**B3** 补可读性——`state/audit.py` 给两种后端实现 `export_human_view()`：把全部状态导出为稳定排序的 pretty JSON + SAFETY 副本，弥补 SQLite 牺牲的"肉眼可读"（CLI `export-audit`）。

### B3.5-B3.8：并发与恢复硬化（spec 一句话拆成四轮）

原 spec 只写了"WAL + 原子领取"，实做拆成四轮：**B3.5** 动作板原子契约——`append_pending_action` / `claim_next_ready_action` / `mark_completed|cancelled` 四个原子 API，SQLite 用 `BEGIN IMMEDIATE` 单事务领取（pending→内部 in_progress），所有提案入口（AgentRuntime/ChatRuntime/MCP）统一改走 append，watch 统一改走 claim；**B3.6** lease 与失败恢复——actions 表加 `claimed_at/claim_owner/attempts` 列（含旧库 ALTER 兼容），领取写 300s lease，`recover_stale_actions()` 把超时 in_progress 放回 pending，driver 执行抛异常时写终态+失败反馈，保证不留永久 in_progress；**B3.7** 用 backend 矩阵测试（同一套用例跑两种后端）+ 只读 `state-check` 诊断固化行为差异；**B3.8** 才把新项目默认后端切到 sqlite——切换放在最后一步，前面三轮都是在 opt-in 状态下淬火。

### B4a-c：记忆、摄入与检索（地基化，主动降级）

**B4a** MEMORY 升级结构化：kind/tags/importance 字段 + 可过滤 `read_memory()`；**B4b** 文件摄入：`ingest-file` CLI + 上传元数据审计，小文本摘录进记忆，**内容一律标记不可信（UNTRUSTED）**——prompt injection 防御从这里成为一等公民；**B4c** 检索：先落契约（chunk 存储/查询接口、gated `retrieved_context`、`search-memory` CLI），实现用**本地确定性关键词匹配**，默认关闭——sqlite-vec + embedding 按"语料够了再上"原则主动延后，留成填空题而非改架构题。

### C1-C2：HTTP 后端与常驻 watch

**C1** 可选依赖的 FastAPI（`[server]` extra），把状态/动作板/记忆/上传/审计暴露为 proposal-only REST；关键纪律：`api/server.py` 顶层 import 不得出现 watch runtime 或 drivers loader（有测试盯着）。**C2** 常驻 watch——`ApiWatchService` 在 FastAPI lifespan 里以后台任务懒加载 WatchRuntime，`--watch` 显式开启（默认不跑）；`/api/events` SSE 由线程安全的 `ApiEventBroker` 推增量事件；顺手修了并发 proposal 时 LOG 镜像写踩踏（进程内文件锁）+ SQLite 并发测试。

### C3-C3.2：React 仪表盘

**C3** 用 React+AntD+@ant-design/x 全量重写 GUI（替代旧内联 HTML），FastAPI 托管 `frontend/dist`，加浏览器上传（≤5MB 仅文本）；**C3.1** 稳定侧栏导航重设计（Overview/Actions/World/Robots/Memory/Safety/Events/Settings）+ StatusBar + 提案面板，补 Playwright e2e；**C3.2** QA 硬化：空 workspace、真实上传、SSE 断线可见、表单错误稳定呈现。⚠️ 本阶段最大失误：重写时没做旧 GUI 功能清单，**reset 与硬件接入面板静默丢失**，直到事后审计才发现，E0 整阶段在还这笔账。

### D1-D2：传输层

**D1** 定义 `Transport` 抽象 + 标准库实现的 `WebSocketTransport`，重构 xiaozhi_mcp 的 ws 模式复用之——先用已有 driver 验证抽象合理性再扩面；**D2** 补 `LoopbackTransport`（测试用）与可选 pyserial 的 `SerialTransport`——**读写自带传输层超时**（这个决定在 W1 时被证明是先见之明：同步阻塞 I/O 靠它兜底）。舵机协议层（ServoBus）识别为重活主动延后（后由 LeRobot motors 方案接管，见 SPEC F5.1）。

### D3-D4：看门狗与实机

**D3** 把 heartbeat/halt 从 no-op 钩子接入 WatchRuntime 常驻循环（每 tick 心跳、关停 halt，`heartbeat_enabled`/`halt_on_shutdown` 开关）；**D3.1** 软件看门狗策略：连续心跳失败计数、达阈值 best-effort halt、恢复时写审计事件；**实机回归** 用 moce 臂真机跑通接入-执行-回报全链路；**D4** 收口实机准备清单文档。

### A1 系列：官方 SDK 与聊天体验（重构后期补做）

A1 最初被跳过（工具循环建在自研 urllib 客户端上"够用"），后按计划补齐五轮：**A1.0/A1.1** 官方 openai SDK 替换（`[llm]` extra；base_url 按 API root 原样传递修掉拼接坑；strict json_schema 失败自动降级 JSON mode + 本地 jsonschema 校验；错误归一 + key 脱敏）；**A1.6a** `workspace/.llm.json` 本地设置（CLI/GUI/watch 共用一份，gitignore）+ Settings 表单 + 测试连接 + API chat 改走 ChatRuntime（API-safe flags 关闭 code skills/硬件接入）；**A1.2/A1.4** 流式：SDK stream 封装 `stream_chat_text()`、`/api/chat/stream` SSE + `/api/chat/abort/{id}`、前端乐观气泡 + Stop 按钮、会话重置（A1.7a）；**B5** 收口后端口径（state-check 加 backend 语义字段）；**A1.3a** 默认开 reasoning 请求参数（不展示 raw CoT）。

### E0：GUI 功能对齐（还 C3 的账）

**E0.1** 工作区级重置：`POST /api/workspace/reset`（confirm 必填）+ Settings Danger Zone。关键偏离：不复用 `setup(force=True)`——它会实例化 WatchRuntime，撞 P0 冻结的不变量测试；改纯 state 侧 `initialize(overwrite=True)`，副产品是不覆盖用户 yaml、保留 .llm.json。**E0.2** 硬件面板：`POST /api/integrate` 复用既有 onboarding/driver_coder + Hardware 导航页 + RobotsPanel 补 Health/Endpoint/Mode 列。**E0.3-lite** 配置可视：`GET /api/config`（watch 实际加载的规范化视图）+ `POST /api/config/robots`（注册新 robot 写回 yaml，校验不过不落盘，重复 409）+ ConfigPanel 只读卡片 + 生成后按 config_schema 渲染注册表单——刻意不做通用 yaml 编辑器。用户随后自做前端懒加载拆包与 QA 硬化（`191f8b5` `9bf3510`）。

### W1：驱动调用超时保护

动机：五类 driver 调用均为裸 await，单事件循环下任一挂死 = watch 连同心跳看门狗整体瘫痪（mock 永不阻塞故此前不可见）。过程：WatchConfig 加 4 个超时预算（action 30s / observe 10s / heartbeat 5s / halt 5s）；`_call_with_timeout()` 统一包装；execute 超时优先取 capability 自声明的 `timeout_s`，超时后**best-effort halt 该机器人**（协程被取消但物理动作可能仍在进行）；observe 超时仅记 log（防 tick 频率刷 feedback），持续故障由心跳看门狗升级；heartbeat 超时复用既有计数→watchdog 路径；disconnect 补异常隔离。4 个挂死回归测试 + 全量 246 用例通过。

### F0：LLM planner 实验

动机：把认知侧从 rule_based 切到真实 LLM planner，用坏任务压测"planner 只提案 → watch 唯一执行 → SafetyGate 执行前校验"这条安全链。过程三步：**F0.a** 本地 ignored 的 `physical-agent.yaml` 已切 `agent.planner: llm`，`agent.model: fake/local` 和 `config.py` 默认 `rule_based` 不动（CI/新项目仍离线可跑）；**F0.b** `OpenAICompatibleClient` 在 Chat Completions / Responses / stream 三条出口追加 best-effort JSONL trace 到 `workspace/llm-trace/YYYYMMDD.jsonl`，字段含 surface/model/messages/response/usage/latency/error，`PA_LLM_TRACE=0` 可关，测试覆盖非流式、structured_json、stream 与零写入；**F0.c** 新增 `scripts/f0_bad_task_experiment.py`，固定 15 条 mock_arm 坏任务（越界/幻觉能力/中文/多步/模糊各 3 条），每条独立 workspace，先预览同一套 SafetyGate 判定，再驱动 watch step，生成 `docs/f0-report.zh-CN.md`。

补测结果：后续按用户要求以项目 `.env` 的 `GPT_URL/GPT_KEY/GPT_MODEL` 作为测试源，并用空 settings workspace 避免旧 `workspace/.llm.json` 覆盖；provider 连通后暴露出当前模型不支持 `response_format` 的 `json_schema/json_object`，因此 `structured_json()` 增加第三档无 `response_format` 的 JSON-only prompt fallback，仍由本地 `jsonschema` 做最终校验。补测 15 条：10 条完成、5 条无提案、0 条 planner 异常、0 条 Gate 拦截。结论要改写为：LLM planner 已能产出中文/多步合法提案，但越界与部分幻觉能力被 planner 直接拒绝为无提案，没有形成 Gate 拒绝样本；模糊指令会激进规约成 pick/place，F1/F3/F4 仍需围绕"不确定性展示、上下文解耦、执行后断言"继续排。

### B6：退役 MarkdownStateStore 后端

动机：B3.8 后 SQLite 已是默认且经原子动作/lease/audit 硬化；F1.3 审批流即将扩展 action 元数据，继续维护 MarkdownStateStore 会让新审批字段为死后端重复实现。过程：删除 active backend 的 `state/markdown.py` 与 factory markdown 分支，`load_config()` 不再自动探测 legacy Markdown workspace；显式 `workspace.backend: markdown` 或省略 backend 但存在完整旧 Markdown workspace 时均报清晰迁移指引。`migrate-md-to-sqlite` 保留一个版本周期，但改走 `LegacyMarkdownWorkspaceReader` 迁移专用只读路径，不实现 `StateStore`，避免运行态绕回旧后端。测试侧删除 markdown e2e 与 backend 矩阵 md 侧，保留 SQLite 的原子领取、lease recovery、并发 proposal、SAFETY 文件真源、LOG 镜像、audit export 与迁移回归。文档同步：`state-backends` 改为 SQLite-only，`sqlite-readiness` 并入删除，bring-up 与 xiaozhi 教程改成 SQLite 黑板口径，旧独立 handoff 删除。

## 3. 关键决策与偏离（跨阶段汇总）

1. **A1 曾被"替代"后补做**——教训：spec 状态要回写，不能只散落在 handoff。
2. **SAFETY 永远是文件真源**（B2 起）：安全规则不进数据库，API 物理上改不了。
3. **默认切换永远放在硬化之后**（B3.8 模式）：原子→恢复→矩阵测试→才切默认。
4. **上传内容全程标记不可信**（B4b 起）：注入到任何 LLM 上下文都带 untrusted 政策。
5. **API 顶层 import 不得触及 watch/drivers**（C1 起，有测试强制）。
6. **重置不碰 watch**（E0.1）：宁可偏离 plan 原文也不破 P0 不变量。
7. **超时即 halt**（W1）：执行超时后硬件状态未知，fail-safe 优先。
8. **审批目前是死胡同**：requires_approval 只会拒绝，无放行通道——SPEC F1.3 待办。
9. **项目根 `physical-agent.yaml` 是 ignored 本地运行配置**（F0）：本轮按要求切到 `planner: llm` 但不强行纳入版本库；共享默认仍以 `config.py` 的 `rule_based` 与模板为准。
10. **F0 补测凭据源固定为 `.env`**：真实 provider 测试使用项目 `.env`，实验命令用空 settings workspace 避免旧 `workspace/.llm.json` 覆盖；GUI/runtime 的本地设置机制暂不重构，留给后续配置收口。
11. **退役 active backend 与保留迁移 reader 分离**（B6）：运行态只支持 SQLite；旧 Markdown 文件只作为迁移输入读取，迁移 reader 不实现 `StateStore`，不进入 factory，也不承担新功能字段。

## 4. 经验教训（流程侧）

- **重写必须先做旧功能 parity checklist**：C3 的静默丢失靠事后审计才发现。
- **快照式文档过期极快**：REFACTOR-LOG/system-summary 写完次日即失真；解法是活账本（SPEC §4）+ 每轮更新一行。
- **git/CI 基建要跟上纪律**：长期单分支不 push、无 CI、测试对宿主环境敏感（代理变量/Python 版本），均记为工程欠账。
- **mock 测不出阻塞类缺陷**（W1 的教训）：凡是"永不失败"的测试替身，都在掩盖一类真实故障模式；需要故意注入挂死/超时的对抗性测试。
- **LLM 实验先固定凭据源与 provider 能力，再谈 planner 质量**（F0 的教训）：同一个 OpenAI-compatible 入口可能不支持 `response_format`/JSON mode；批量实验要先用 `.env` 连通、记录模型能力，再靠本地 schema 校验兜底，否则会把 provider 兼容问题误读成 planner/Gate 问题。
- **后端退役要同时保迁移旁路与清 UI 口径**（B6 的教训）：删除 factory 分支不够，CLI 迁移、state-check、前端说明、e2e mock、操作手册和旧 handoff 都可能继续暴露退役后端。

*新一轮工作完成后：§1 表格加一行，§2 追加小节，决策/教训有则补记。*
