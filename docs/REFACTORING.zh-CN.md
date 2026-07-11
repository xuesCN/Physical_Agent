# 重构过程

> 本文浓缩自原 33 份 session-handoff 与 22 份 brief（已删除，git 历史可查）。姊妹文档：`SPEC.zh-CN.md`（目标与待办矩阵）。
> 范围：基线 `8fa197a` → 当前。最后更新：2026-07-11。

## 0. 基线与纪律

起点是一个 Markdown 黑板协议的双进程原型（agent 写提案文件、watch 读文件执行）。全程冻结四条红线：**agent/llm/gui 只提案；watch 唯一执行；SafetyGate 不被绕过；新能力默认关闭或向后兼容**。每轮 session 遵循 brief → 实现 → 测试 → REFACTORING 收口，小步可回滚。

## 1. 阶段速查表

| 阶段 | 里程碑 | 提交 |
| --- | --- | --- |
| P | 安全边界冻结 + 工具循环 + driver 钩子预留 | `8261e93` |
| A3 | rolling summary 上下文压缩 | `0a67ebb` `c2e7e76` |
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
| F1 | 提案卡片 + Add to Actions + action 级审批流 | `0f49a3c` |
| F2 | 结构化信息可读化：feedback/world/capabilities + lazy JSON tree | `58a75b0` |
| F2.5 | State Overview 产品化收口：viewmodels + AntD schema components + scoped RawDebug | 本轮提交 |
| F2.5-json-style | 非 RawDebug JSON 展示统一为 Overview capability 摘要样式 | 本轮提交 |
| F2.5-raw-debug-antd | RawDebug 改为 AntD 原生 Collapse/Tree，移除 react18-json-view | 本轮提交 |
| Audit-doc-html | current architecture audit 静态 HTML 阅读页 | 本轮提交 |
| F3 | context_builder 解耦：reply/proposal/planner/tool_loop 上下文统一 | `9cbb540` |
| F4 | 期望-比对-回灌：expected 确定性比对、feedback 回灌、前端可见性 | `b5be3b7` |
| W2 | 观察并发化 + observe 频率与 tick 解耦 | `4e0f732` |
| W3 | transport 断线重连：可选 policy、fail-fast、driver reinit hook | `1d9a812`, `7762c0f` |
| VNext-0 | ProposalService + typed metadata + 执行边界 + execution_mode 地基 | 本轮提交 |
| VNext-1 | AgentOutput task DAG + trusted PlanCompiler | 本轮完成 |
| VNext-2 | materialized AgentOutput + structured feedback + 调度/上下文硬化 | 本轮完成 |
| VNext-2b | Proposal actions batch 单事务 all-or-nothing | 本轮完成 |
| W6.1 | workspace watch runtime lease + unique claim-owner CAS/reset guard | 本轮完成 |
| R0 | 架构减法规格 + GUI/Markdown/streaming 三份退役审计 | `e8750ca` |
| R1.5 | 正式 Dashboard parity 补缺 + packaged wheel + thin `gui` strangler cutover | `9f3880a`, `2d5e909` |
| R2 | 删除 legacy controller/server/static/tests/package-data 与 safety allowlist 例外 | `5764bac` |
| T/C4/E3 | 独立 Ink TUI + 前端 i18n/暗色/Tour + e2e/CI 收口 | 本轮提交 |
| CI-lite | 宽松 CI + CI 解释文档 | 本轮提交 |
| TUI-review-fix | 修复 Ink TUI stream 清理、SSE EOF 降级、真实 watch 状态 | 本轮提交 |
| TUI-api-arg-fix | 兼容 Windows/npm 启动时裸 API URL 参数 | 本轮提交 |
| TUI-chat-cli-fix | 修复 SSE summary 覆盖 chat/actions，并改成纵向 CLI transcript | 本轮提交 |
| TUI-llm-status-rendering | 取消 chat 硬截断，显示 LLM key/连接状态 | 本轮提交 |
| TUI-append-only-scroll | chat 历史改为 append-only scrollback，降低空闲 watch 重绘 | 本轮提交 |
| TUI-T3-config-robots-upload | 补齐 Ink TUI config/robots/uploads 视图、上传和注册命令 | 本轮提交 |
| TUI-command-acceptance | 增加 Ink TUI 用户命令场景验收与命令矩阵 | 本轮提交 |

## 2. 分阶段过程记录

### P：安全边界冻结 + 工具循环地基

动机：在动任何大结构前，先把"什么不能变"写死。过程：把安全边界固化为验收测试（`test_safety_boundaries` 用 monkeypatch 断言 API/agent 侧永不实例化 WatchRuntime、永不调 `driver.execute`）；新增 `agent/tool_loop.py` 的 `OpenAIToolLoop`——同时支持 Chat Completions tool calls 与 Responses function calls，但**工具白名单只含提案类操作**（submit_task/propose_action/读状态），dispatch 层物理上没有执行路径；`drivers/base.py` 契约预留 no-op `heartbeat()`/`halt()`，为 D 阶段占位且不破坏现有 driver。真实执行路径保持：提案 → 动作板 → watch → SafetyGate → execute。

### A3：上下文压缩

动机：CHAT 无限增长会撑爆 LLM 上下文。过程：`protocol/chat_summary.py` 实现 rolling summary——保留最近 12 条原文，超过 24 条阈值时把更早消息压成 `running_summary` 字段（simple 模式，不依赖 LLM，确定性可测）；CHAT 协议文档扩展 summary 字段；LLM/tool_loop 的上下文组装统一改读"summary + 近期原文"。后续补丁 `c2e7e76` 修复 `_trim_summary()` 在极小 `max_chars` 下因 `summary[-0:]` 返回全量文本而超预算的问题，并用单测锁住返回长度不超过预算。

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

动机：B3.8 后 SQLite 已是默认且经原子动作/lease/audit 硬化；F1.3 审批流即将扩展 action 元数据，继续维护 MarkdownStateStore 会让新审批字段为死后端重复实现。过程：删除 active backend 的 `state/markdown.py`、factory markdown 分支和自动选择/打开 legacy backend 的 fallback；`load_config()` 仍识别完整旧 Markdown 文件集合，但只用于 fail-closed 拒绝。显式 `workspace.backend: markdown` 或省略 backend 但存在完整旧 Markdown workspace 时均报清晰迁移指引。`migrate-md-to-sqlite` 保留一个版本周期，但改走 `LegacyMarkdownWorkspaceReader` 迁移专用只读路径，不实现 `StateStore`，不进入 factory，不承接新功能字段，避免运行态绕回旧后端。测试侧删除 markdown e2e 与 backend 矩阵 md 侧，保留 SQLite 的原子领取、lease recovery、并发 proposal、SAFETY 文件真源、LOG 镜像、audit export 与迁移回归；`protocol/markdown.py` 与 parsers/renderers 继续服务 SAFETY.md、LOG.md 人类可读镜像、audit export 和旧 workspace 迁移输入。文档同步：`state-backends` 改为 SQLite-only，`sqlite-readiness` 并入删除，bring-up 与 xiaozhi 教程改成 SQLite 黑板口径，旧独立 handoff 删除。

### F1：提案卡片 + Add to Actions + action 级审批流

动机：F0 证明 LLM planner 会把部分模糊任务激进规约成合法动作，也会在坏任务上拒绝不产出，单靠 planner 无法替代人对"是否想要这个动作"的确认；同时 `requires_approval` 之前只有拒绝没有放行通道，形成审批死胡同。过程：chat 侧把 draft 固化为 `action-draft` fence，`ChatPanel` 用纯函数解析并渲染 draft 卡片，展示任务原文、提案动作、robot/capability/params/reason；卡片按钮改为 Add to Actions，只创建 pending action，Edit 回填手动提案表单，坏 JSON 降级为普通 Markdown。后端把 action metadata 纳入协议与 SQLite 持久化，记录 source/original task/draft reason/approval；`approval.required` 永远由后端按 robot/capability `requires_approval` 和 SAFETY 文件真源计算，覆盖 caller 伪造值。新增 approve/reject API 与 Actions 板审批控件，approve 幂等、不重复写混乱日志，reject 只允许 pending 并写原因后转 cancelled。watch 的 `claim_next_ready_action()` 在 SQLite `BEGIN IMMEDIATE` 事务中扫描 pending action，跳过未批准的 required action 但继续领取后续 ready action；SafetyGate 从"requires_approval 直接拒绝"改为"检查后端计算的 approval 是否 approved"，审批只解除等人放行，schema、bounds、capability、robot、SAFETY.md 仍照常校验。F0 遗留一并收口：planner/chat 无提案透出 `refusal_reason`，并补 Gate 直击测试绕 planner 直接 propose 坏动作，留下 Gate 拦截审计样本。验证：全量 `pytest` 251 例通过，`frontend npm run build` 通过，浏览器 GUI smoke 覆盖 chat draft → Add to Actions。

### F2：结构化信息可读化

动机：F1 后 approval/source/refusal_reason 已进入状态与审计，但 GUI 仍要求用户点 Raw Debug 才能拼出"提了什么、是否审批、是否被 Gate 拦、world 里有什么"。过程：前端新增 `readableFormatters` 集中处理 status 颜色、pose/location、schema 摘要与安全取字段；`ContextTabs` 改成 world/feedback/safety/capabilities 四个可读 tab。`FeedbackTimeline` 用 AntD Timeline 合并 feedback history、action approval/source metadata 与 chat `refusal_reason`，失败原因优先读 `message`，`action_id` 可跳 Actions 页；driver heartbeat/watchdog/expectation 类事件有可读标题。`WorldObjectsTable` 把 world objects 转成 id/type/location/pose/status/relations 表格，environment/robots/artifacts 单独展示，未知字段保留 raw。`CapabilityCard` 展示 capability 名称、描述、params schema 摘要、constraints 与 approval 徽章；`ConfigPanel` 与 `HardwarePanel` 补配置/集成能力摘要。raw/debug 统一走 `JsonTreeLazy`，懒加载 `react18-json-view` 并在 Vite 中拆出 `json-view` chunk，`RawDebug`、Settings plan、Safety raw、Events payload 等均默认折叠。验证：`frontend npm run build` 通过且产物含独立 `json-view-*.js`；Playwright dashboard 14 例通过（含 F2 mocked readable context）；全量 `pytest -q` 251 passed；`frontend/src` 中 `<pre>` 从 6 处降至 0 处，`JSON.stringify` 从 19 处降至 18 处且剩余主要是 API 请求体/SSE 去重/表单初值/工具兜底。

### F2.5：State Overview 产品化收口

动机：F2 已把若干 Context tab 从裸 JSON 改成可读组件，但 Overview 首屏仍更像把状态 JSON tree 当主材料，用户需要来回点 tab/raw 才能回答系统 ready、backend、robot、capability、world objects 与 workspace bounds。过程：新增 `frontend/src/viewmodels/overview.ts`、`robot.ts`、`capability.ts`、`world.ts`、`environment.ts` 五个纯 formatter，把后端 state JSON 先转为 UI viewmodel，再交给 AntD 组件渲染。新增 `StateOverviewPanel`，首屏依次展示 `SystemStatusCard`（Card + Statistic + Tag）、`RobotsTable`（id/driver/mode/health/capability count）、`CapabilityCards`（Card/List，展示 name/description/params summary/requires approval）、`EnvironmentDescriptions`（x/y/z bounds）和 `WorldObjectsTable`（object id/type/location/pose/status）。Overview 保留 Actions/Chat 与原 ContextTabs，避免破坏既有工作流，但状态可读性入口前置到页面顶部。

RawDebug 收口：`RawDebug` 不再接收整份 state 并显示 `Full state JSON`，而是通过 `formatRawDebugFields()` 只收集 top-level unknown、backend private、world raw、environment unknown、object unknown、capability/robot unknown 字段；该轮仍由 `react18-json-view` 懒加载并默认折叠，后续 F2.5-raw-debug-antd 已继续收口为 AntD 原生 Tree。边界保持：未改 backend API、watch、SafetyGate、driver、SQLite；没有新增 UI 库。验证：`cd frontend && npm run build` 通过；`cd frontend && npx playwright test` 19 passed（新增 F2.5 mock state 验证 robots table、capability cards、environment descriptions、world table、RawDebug 默认折叠、无 `Full state JSON` 标题）；`.\.venv\Scripts\python.exe -m pytest` 304 passed（1 个既有 StarletteDeprecationWarning）。

### F2.5-json-style：JSON 展示样式统一

动机：Overview capability cards 的 `Params:` / `Constraints:` 摘要已经比 JSON tree 更适合首屏阅读，但 Actions、Chat draft、Config、World、Feedback、Events、Safety、Settings 等区域仍复用旧 `RawJsonFallback`，视觉上像回到了“折叠 JSON 是主展示”。过程：新增 `JsonSummaryLine` / `JsonSummaryStack`，复用 `schema-summary` 的轻量 monospace 摘要样式；把非 RawDebug 的 params/expected/config/plan/event payload/object raw/safety raw/feedback raw/capability raw 全部改为 `Label: key=value` 摘要。`RawJsonFallback` 与 `JsonTreeLazy` 只保留给 `RawDebug`，真正需要用户编辑的 ProposalPanel `Params JSON` 输入框保留 textarea，不把输入控件伪装成展示组件。

当轮边界：未改 backend API、watch、SafetyGate、driver、SQLite；未新增 UI 库；`react18-json-view` 当时仍懒加载且只作为 RawDebug fallback（后续见下一小节继续收口）。验证：`rg RawJsonFallback frontend/src/components frontend/src/App.tsx` 只剩 `RawDebug` 与 `JsonTreeLazy` 定义；`cd frontend && npm run build` 通过；`cd frontend && npx playwright test --grep "F2"` 2 passed；`cd frontend && npx playwright test` 19 passed；`.\.venv\Scripts\python.exe -m pytest` 304 passed（1 个既有 StarletteDeprecationWarning）。

### F2.5-raw-debug-antd：RawDebug 原生 AntD 收口

动机：用户确认 Overview capability 摘要风格可接受后，Raw Debug 中 `react18-json-view` 的树形视觉仍像旧 JSON viewer，容易被误认为产品主展示的一部分。过程：`RawDebug` 改为直接使用 AntD `Collapse + Tree + Tag + Typography` 渲染 unknown/raw/backend private 字段；默认仍折叠，展开后只显示 `formatRawDebugFields()` 收集的片段，不恢复整份 state JSON。删除 `JsonTreeLazy.tsx`、`.json-tree`/`.raw-json-*` CSS、`react18-json-view` npm 依赖与 Vite `json-view` chunk 规则，避免旧 viewer 留在构建路径里。

边界保持：未改 backend API、watch、SafetyGate、driver、SQLite；未新增 UI 库；RawDebug 的字段收集口径不变。验证：`cd frontend && npm run build` 通过且产物无 `json-view` chunk；`cd frontend && npx playwright test --grep "F2"` 2 passed，覆盖 RawDebug 默认折叠、展开后出现 AntD tree、页面无 `Full state JSON`。

### Audit-doc-html：current architecture audit 静态展示

动机：`docs/current-architecture-audit.md` 已经把当前架构、安全偏差和未来三轮路线梳理成一份长审计文档，但纯 Markdown 在浏览器里只能 raw 阅读，不利于快速扫描目录、表格和代码路径。过程：新增 `scripts/render_audit_html.py`，从该 Markdown 生成 `docs/current-architecture-audit.html`；HTML 内嵌源 Markdown 与 sha256，客户端用零依赖小渲染器处理标题、表格、列表、代码块和 inline code，并提供侧栏目录与搜索。设计上按 F2 原则只做“读”，把已知内容结构化展示，未知/raw 不变。

边界保持：未改 backend API、watch、SafetyGate、driver、SQLite，也未把页面接入 React dashboard 或 FastAPI 路由；该页是 docs 静态阅读器，直接打开即可。验证：新增 `tests/test_docs_audit_html.py` 校验 HTML 内嵌内容与 Markdown 一致、source hash 一致且不依赖 fetch/外部 URL；Playwright 直接加载 file URL 验证桌面/移动端渲染、目录、表格、代码块、搜索和无控制台错误，移动端无页面级横向溢出。

### F3：context_builder 解耦

动机：chat_runtime 内 reply-only stream、chat proposal、tool_loop 三处上下文组装长期重复，LLM planner 也单独拼一套 action-plan prompt；接实机前需要把"给模型看什么"变成可测、只读、可预算的单点。过程：新增 `physical_agent/agent/context_builder.py`，定义 `ContextBudget` 与 `ContextBundle`，`build_context()` 统一 reply/proposal/tool_loop/planner 四路 payload，`build_planner_context()` 服务 direct `LLMPlanner` 调用；planner 没有复用 chat proposal，而是保留独立 `purpose="planner"` 与结构化 action plan system 文案。`ContextBudget` 收拢 recent messages、memory top-N、world/capabilities 字符预算、note 截断与各路 max_tokens；world/capabilities 超预算时降级为稳定摘要，memory 改按 `importance DESC, created_at DESC` 注入并保留 upload/untrusted 标记。验证：新增 context_builder golden snapshot 覆盖四路 system/payload，read-only 测试禁止 write/append/claim/approve/reject 等副作用；chat/planner/tool_loop/retrieval 回归通过，安全边界测试仍证明请求侧不加载 driver、不调用 `driver.execute`。

### F4：期望-比对-回灌

动机：F0/F1 之后，模型已经能生成合法动作，但“动作执行后是否达成意图”仍只靠 driver 成败消息，缺少确定性闭环证据。过程：新增 `physical_agent/protocol/expectations.py`，定义 expected schema、轻量归一化、路径解析与 `evaluate_expected()`；放在 protocol 而不是 watch 包内，是为了让 API/state/agent 可复用 schema 与归一化，同时不触碰 C1 的“请求侧顶层 import 不得加载 watch/drivers”边界。SQLite 写入 action metadata 时规范化 `expected`：单对象转 list，坏形状保留为后续 skipped，条数与序列化大小受限，坏 expected 不影响 action 合法性。chat draft、LLM planner、MCP 与 API proposal 都接受 `metadata.expected`，context_builder 系统文案明确 expected 只是执行后检查，不是安全规则。

watch 侧只在 SafetyGate 通过、driver completed、并成功 `update_world()` 后跑 deterministic check；动作失败或 world 刷新失败时把 expected 标记为 skipped，SafetyGate 拒绝则不跑 expected。多条 check 的总状态固定为 violated > skipped > verified，每条 check 保留独立 `status/message/expected/actual`，总事件 `message` 摘第一条 violated/skipped，写入 `event: expectation_check` feedback。F2 时间线可直接读 feedback；F3 context_builder 在下一轮把 expectation feedback 回灌给 LLM，但自动重试仍默认关闭。前端在 Chat draft 与 Actions 表格补 expected 摘要/raw 折叠，防止模型生成的 expected 完全隐形。验证：新增 evaluator/SQLite/watch/chat/planner/MCP/API 覆盖，golden snapshot 更新，`pytest -q` 269 passed，`frontend npm run build` 通过。

### W2：观察并发化 + 频率解耦

动机：W1 把单个 driver 调用套上 timeout，但 `update_world()` 仍串行逐 robot observe；接多机或慢传感器时，一个慢 observe 会把整个 world refresh 拉长，同时 watch 长跑循环里 idle observe 与 action claim 绑定在同一 tick 上。过程：`WatchRuntime.update_world()` 改为按 `robot_id` 排序后对不同 robot 的 `observe()` 使用 `asyncio.gather(..., return_exceptions=True)` 并发执行，单 robot timeout/异常只写 watch log，不进入 feedback；gather 返回后稳定 merge robots/objects/environment/raw，artifact 保持确定性追加顺序。发生部分失败时，以当前 world 的 last known state 为底再覆盖成功观测，保证一个 robot 故障不会清空其他 robot 或全局 world；这不是 W4 的 ownership/observed_at 设计，只是 W2 的故障保守降级。

配置侧 `WatchConfig.observe_interval_ms` 为可选正整数，模板写 `null`；运行时未配置时取 `tick_ms`，保持旧配置节奏。新增 `tick()` 作为长跑循环入口：heartbeat/recover/claim/execute 仍每 tick 运行，只有无动作时的 idle `update_world()` 受 observe interval 控制；`step()` 继续作为测试/CLI 单步入口，默认无动作即刷新 world。API watch 后台服务改为优先调用 `tick()`，旧 fake runtime 仍可回退 `step(setup=False)`。F4 关键语义保持不变：动作 completed 后立即 `update_world()` 并基于动作后的 world 运行 expectation_check，不受 idle observe 分频影响；SafetyGate 拒绝和 action 执行失败路径仍按 F4 规则跳过/标记 expected。验证：新增并发启动、稳定 merge、单 robot exception 隔离、observe interval 默认/非正校验/分频、tick 下 expected 回归测试；`pytest` 277 passed。

### W3：transport 断线重连

动机：W1 解决了 driver 调用挂死，但真实 WebSocket/串口还有 connect 初始失败、运行中断连、端口被拔、server 主动 close 等故障；如果 transport 把旧命令排队到重连后再发，会破坏 watch 唯一执行与“动作状态未知即失败”的安全直觉。过程：`drivers/transport/base.py` 增加默认关闭的 `ReconnectPolicy`（`enabled/max_retries/backoff_base_ms/backoff_cap_ms/jitter_ms`）与 `connected/disconnected/reconnecting` 状态、`TransportDisconnected` / `TransportReconnecting` / `TransportReconnectFailed` 错误；退避公式固定为 `min(cap, base * 2 ** attempt)`，attempt 从 0 开始，测试用 fake sleeper 避免真实长 sleep。

`WebSocketTransport` 与 `SerialTransport` 保持同步 byte transport 接口：`open()` 初始失败时按 policy 同步重试；运行中读写发现 peer close、OSError、SerialException 或 port closed 时先丢弃旧 socket/handle，再启动后台重连线程。reconnecting 期间 `write/read/request` 立即失败，错误消息包含“command was not queued”，watch 捕获 transport 类异常后把 action 标 failed/cancelled 并写 feedback：reconnecting/disconnected 是 fail-fast，reconnect exhausted 明确说明耗尽，执行中 close/OSError 说明 execution state unknown 且不自动 retry。timeout 仍由 W1 的 watch-side timeout 与 transport 自身 timeout 兜底，不因 reconnect policy 绕过。

driver 层补 `PhysicalDriver.on_transport_reconnected()` 默认 no-op；transport 支持 `on_reconnected` 回调。`xiaozhi_mcp` 将 WebSocket reconnect callback 转为“待刷新”标记，下一次 health/observe/execute 前重新 `initialize` 与 `tools/list`（fire-and-forget 模式刷新本地工具映射），不在 transport 背景线程里重放旧动作。review 中补 `7762c0f`：后台重连的 `open_once()` 若在 close/cancel 后才成功，基类会立即清理刚打开的 socket/serial/loopback 资源，保持 disconnected，且不触发 reconnect hook。Loopback 扩展测试模拟连接第 N 次成功、运行中断连、后台重连、reconnecting fail-fast、hook 调用与取消后的迟到 open 清理；WebSocket fake server 覆盖首次连接成功、server 主动断开、client 重连后再次 read/write；Serial fake 覆盖 open 失败后重试成功、重试耗尽、读写 OSError 标记断连并可重新 open。

边界保持：SafetyGate / F1 approval / F4 expected / watch 执行权不变；W3 只让通信层恢复可用，不把 reconnect success 当作机器人位置或动作安全证明；不做 W4 的多机器人并行 execute 与 `observed_at` schema，不自动重放 execute、不自动重规划。验证：transport/watch/safety 定向测试、`tests -k "reconnect or transport or websocket or serial or disconnected"`、`tests -k "timeout or observe or expectation or expected"` 均通过；review fix 后全量 `pytest` 295 passed（1 个既有 StarletteDeprecationWarning）。

### T/C4/E3：独立 Ink TUI + 前端打磨 + e2e/CI 收口

动机：给 SSH/无 GUI/开发者日常场景一个交互式终端入口，同时把 GUI 的语言、暗色与首次引导补齐，并把 E0 遗留的 reset/hardware/config 主路径纳入 e2e。过程：新增 `tui/` 独立 Node/TypeScript/Ink 包，入口 `npm start -- --api http://127.0.0.1:8766`，只封装 HTTP API 与 SSE，状态/chat/actions 三面板 + polling fallback，T2-lite 命令覆盖 chat、task、approve/reject、reset/refresh/help/quit；直接硬件控制命令显式拒绝。React GUI 侧新增 `frontend/src/locales/`、`MessagesProvider`、AntD locale、`darkAlgorithm`、`body[data-theme]` 变量和 3 步 Tour；Settings 提供语言、主题、重开 Tour。e2e 先固定默认 English/light/Tour dismissed，避免新引导遮挡旧流程，再单独测试首次 Tour；Playwright webServer 先初始化 `.tmp/e2e` 临时 workspace，避免覆盖根目录本地配置。CI 新增 Python matrix、frontend build、Playwright e2e、tui build/test，并让 Playwright webServer 命令支持 Windows/Linux 与环境变量覆盖。legacy GUI server 同步去重为“HTTP/静态路由 + 复用 `gui.controller.GuiController`”，controller 通过 `open_state_store` 保持 markdown/sqlite 后端兼容。

边界保持：没有修改 `physical_agent/watch`、driver loader、SafetyGate 或 `driver.execute` 调用链；TUI 不读 SQLite/workspace，不 import Python backend/watch/driver，只通过 API 提案/审批。验证：`.\.venv\Scripts\python.exe -m pytest -q` 304 passed（1 个既有 StarletteDeprecationWarning）；`cd frontend && npm run build` 通过；`cd frontend && npx playwright test` 18 passed；`cd tui && npm run build` 通过；`cd tui && npm test` 13 passed。

### TUI-review-fix：stream 清理、SSE EOF 降级、watch 状态

动机：修复 review 指出的三个 TUI 可用性问题，不扩大到后端或 GUI。过程：把 chat stream 处理收敛到 `runTuiChatStream()`，确保 reject/AbortError/done 都在 `finally` 清理 `streaming`；`/api/events` SSE 正常 EOF 与异常断开统一进入 degraded/polling（组件清理触发的 abort 不降级）；从 hello 事件读取 `watch_enabled`，StatusBar 显示 `Watch: enabled/disabled/unknown`，不再把 snapshot 当 watch 状态。边界保持：TUI 仍只走 HTTP API/SSE，未改 watch、driver、SafetyGate、SQLite 或 Python CLI。验证：`cd tui && npm test` 20 passed；`cd tui && npm run build` 通过；`pytest -q tests/test_safety_boundaries.py` 2 passed。

### TUI-api-arg-fix：Windows/npm 启动参数兼容

动机：Windows Terminal / PowerShell 下用户按文档运行 `npm start -- --api http://127.0.0.1:8766` 时，实际落到 `tsx src/main.tsx http://127.0.0.1:8766`，`--api` 被 npm/tsx 链路吞掉，TUI 把裸 URL 当未知参数退出。过程：`parseArgs()` 在保留 `--api URL` 与 `--api=URL` 的同时，兼容 positional `http://`/`https://` API base；help text 同步给出 `npm start -- http://127.0.0.1:8766` 作为 Windows 友好启动方式。边界保持：TUI 仍只走 HTTP API/SSE，不读 workspace/SQLite，不改后端 API、watch、driver、SafetyGate 或 Python CLI。验证：新增 `tui/src/cli/args.test.ts` 覆盖默认值、两种 `--api` 写法、裸 URL 与非 URL 参数拒绝；`cd tui && npm test` 47 passed；`cd tui && npm run build` 通过。

### TUI-chat-cli-fix：chat/actions 持久化与纵向 CLI

动机：用户在实际运行中看到流式 chat 回答先出现、完成后立刻消失，Actions 也存在同类风险；同时左右双面板更像 dashboard，不像 Claude Code 式交互 CLI。根因是 `/api/events` 只推送 `summarize_state()` 轻量 summary（`chat_messages`、pending ids/count 等），TUI 用“含 ready 即 AgentState”的宽松判断把 summary 当完整 state 覆盖，导致 `state.chat.messages` 与 `state.actions` 被清空。过程：将 SSE state 识别拆成 `full/summary/ignored`，只有含 `actions/chat/world/capabilities/feedback` 的完整 state 才直接覆盖；summary 只触发一次完整 `/api/state` refresh，不再写入 UI state；stream `done` 若只带 summary，也保留当前可见 reply text。交互层把首屏大 help、边框双栏与空 actions 占位收起，改为状态行 + chat transcript + 有内容才显示 actions + 紧凑输入提示。边界保持：TUI 仍只走 HTTP API/SSE，未改 API、watch、driver、SafetyGate、SQLite 或 Python CLI。验证：`cd tui && npm test` 23 passed；`cd tui && npm run build` 通过；`pytest -q tests/test_safety_boundaries.py` 2 passed，TUI 侧 grep 未发现 `driver.execute`、watch/driver import、sqlite/fs 直接访问。

### TUI-llm-status-rendering：LLM 状态与 chat 全量显示

动机：用户发现 TUI chat 速度异常快且问答像固定模板，实际检查显示 LLM settings 指向 Ark/Doubao 但连接测试返回 401 `API key status is not active`，同时 TUI 单条 chat 被压成一行并硬截断到 220 字符。过程：TUI client 增加 `/api/settings/llm` 与 `/api/settings/llm/test` 读取，启动和用户 `/refresh` 时检查一次 LLM 状态，StatusBar 显示模型、`key set/missing` 与 `LLM connected/failed` 的短原因（401/key inactive 压缩为短文案，不显示 key 明文）；chat 渲染取消 `replace(/\s+/g, " ").slice(0, 220)`，保留换行与完整文本，只继续限制最近 10 条历史以免旧记录淹没终端。边界保持：TUI 仍只走 HTTP API，不读 `.llm.json`、SQLite 或 workspace 文件，不改后端 LLM fallback、安全链、watch、driver 或 Python CLI。验证：`cd tui && npm test` 25 passed；`cd tui && npm run build` 通过；`pytest -q tests/test_safety_boundaries.py` 2 passed；TUI 侧 grep 未发现 watch/driver import、sqlite/fs 直接访问。

### TUI-append-only-scroll：终端 scrollback 与空闲重绘

动机：用户实际使用 Windows Terminal 鼠标滚轮查看 TUI 输出时，Ink live frame 持续重绘会把视图拉回活动画面；尤其 watch 每 500ms 发空闲 `watch_step`，TUI 之前每次都更新 `lastRefresh` 并触发完整 refresh。过程：新增 `Transcript` 组件，用 Ink `Static` 把 chat 历史作为 append-only 输出写入终端 scrollback；live 区只保留 StatusBar、streaming/error、Actions、notice 和输入框。`state.chat.messages` 只追加未见过的新消息，用户输入先本地追加并在后端同内容消息回来时抵消，避免重复；stream `done` 若只有 summary，可把最终 assistant 文本追加到 transcript。SSE 空闲 `watch_step executed=0` 不再触发完整 `/api/state` refresh，也不更新 `lastRefresh`，只有 `state` 事件或执行过动作的 watch tick 才刷新 live 区。边界保持：TUI 仍只走 HTTP API/SSE，不读 SQLite/workspace，不改后端 API、watch、driver、SafetyGate 或 Python CLI。验证：`cd tui && npm test` 28 passed；`cd tui && npm run build` 通过；`pytest -q tests/test_safety_boundaries.py` 2 passed；TUI 侧 grep 未发现 watch/driver import、sqlite/fs 直接访问。

### TUI-T3-config-robots-upload：config/robots/uploads 补齐

动机：T1/T2-lite 已让 TUI 能聊天、提交任务、审批与重置，但无 GUI 时仍看不到有效配置、robot/capability 细节，也不能走现有上传摄入路径。过程：在 `tui/` 内补 `TuiView` 单主视图与命令 parser，默认保持 chat transcript + actions 体验，新增 `/view status|chat|actions|robots|config|uploads`、`/config`、`/robots`、`/robot <id>`、`/capabilities <id>`、`/upload`/`/ingest`、`/register-robot <json>`。API client 只复用既有 `GET /api/config`、`POST /api/config/robots`、`POST /api/upload`；新增 formatter 集中做 schema/constraints/endpoint/config 摘要与 secret key 过滤。ConfigPanel 展示 workspace/watch/agent/robots 与 capability schema 摘要，不显示 `api_key`/secret/token；RobotsPanel 与 RobotDetailPanel 合并 config、world、capabilities，显示 driver/mode/endpoint/health、capability 数、requires_approval、params_schema 与 constraints；UploadsPanel 只显示 filename/size/sha/id/status/untrusted/chunks 元数据，不显示正文 preview。

上传边界：TUI 本地读文件只为构造 multipart 请求，先拒绝目录、非允许文本后缀、超过 5MB、明显二进制或非 UTF-8 内容；所有落盘、memory/chunks、untrusted 标记仍由后端 `/api/upload` 完成。`/ingest` 在 TUI 中作为 `/upload` 别名，不走后端本机路径式 `/api/ingest-file`，避免把路径语义扩散到服务端。`/register-robot` 只接受 JSON object 并调用既有后端配置注册 API；TUI 不做通用 YAML 编辑器，也不直接写 `physical-agent.yaml`。边界保持：未改 watch、SafetyGate、driver、approval 或 claim 语义；TUI 仍不 import Python watch/drivers，不读写 SQLite，不新增 execute/driver/hardware-control 命令。验证：`cd tui && npm test` 44 passed；`cd tui && npm run build` 通过；TUI 安全 grep 覆盖无 `driver.execute`、无 `physical_agent.watch`/`physical_agent.drivers` import、无 SQLite 直接访问。

### TUI-command-acceptance：命令场景验收

动机：TUI 已有 parser、组件、SSE 和 upload 单元测试，但用户真实输入路径仍缺少“输入命令→mock API/SSE→终端输出→状态变化”的完整验收；这会让 README/帮助里新增命令时只测到解析，不测到实际交互。过程：新增 `tui/tests/scenarios/{basic,chat,actions,config,robots,upload,error}.scenario`，每个场景声明命令输入、API/SSE mock、输出断言、调用次数和 state/config 断言；新增 `tests/scenario-runner.test.tsx` 用自定义 Ink stdin/stdout harness 驱动真实 `App`，并把 `tests/**/*.test.tsx` 纳入 `npm test`。覆盖 `/help`、`/view status|chat|actions|config|robots|uploads`、`/task`、`/approve`、`/reject`、`/reset`、`/config`、`/robots`、`/robot`、`/capabilities`、`/upload`、`/ingest`、`/register-robot`、`/refresh`、`/quit`，以及 API offline、SSE error、SSE clean EOF、polling fallback、缺参、非法命令、上传失败和 reset confirmation failure。新增 `docs/tui-command-matrix.md` 把命令、用途、API endpoint、测试文件和覆盖状态对齐。边界保持：未改后端 API、watch、SafetyGate、driver 或 SQLite；TUI 仍是纯 API/SSE 客户端。验证：`node --import tsx --test tests/scenario-runner.test.tsx` 11 passed；`cd tui && npm test` 58 passed；`cd tui && npm run build` 通过。

### CI-lite：宽松 CI 与解释文档

动机：用户希望先理解并使用 CI，但担心测试过严会限制后续重构。过程：将 `.github/workflows/ci.yml` 从默认全量检查改成三层策略：默认阻塞 `Python safety smoke` 与 `Frontend build`；`Ink TUI advisory` 和 `Playwright dashboard advisory` 保留自动反馈但 `continue-on-error`，其中 dashboard e2e 只在 PR 或手动运行触发；Python 3.11/3.12 全量 `pytest` 矩阵改为 `workflow_dispatch` 的 `full=true` 手动触发。新增 `permissions: contents: read` 与 concurrency 取消同分支过期 run，继续在 workflow env 清代理变量与关闭 LLM trace。

边界保持：没有修改 watch、driver、SafetyGate、API 行为或任何测试断言；默认 smoke 仍覆盖 `test_safety_boundaries`、`test_safety`、API 请求侧不得实例化 watch/driver、HTTP auto-step 不启动 watch、SQLite 默认后端与 watch 单步执行。新增 `docs/CI.zh-CN.md` 解释 CI 概念、本仓库分层策略、本地复现命令、失败判断与“测试行为契约而不是内部实现”的写测原则。后续修复 GitHub Actions workflow 解析失败：`env:` map 不能同时声明 `HTTP_PROXY`/`http_proxy` 这类大小写变体，保留大写代理变量并在文档中说明。验证：workflow YAML 解析与 env key 大小写折叠重复检查通过；`.\.venv\Scripts\python.exe -m pytest -q` 304 passed（1 个既有 StarletteDeprecationWarning）；新 CI safety smoke 15 passed；`cd frontend && npm run build` 通过；`cd tui && npm run build` 与 `npm test` 13 passed。

### VNext-0：Proposal application layer、typed metadata 与执行边界

动机：current architecture audit 证明系统虽然已有安全的 proposal → action board → watch 主链，但 API task、AgentRuntime、MCP 与 manual proposal 仍分别负责 planner 构造、action 编号和 provenance；`Action.metadata` 的 approval/source/expected 也主要靠各调用方约定。同时 `ChatRuntime.auto_step` 和 driver coding 的动态 validation 让 agent 侧仍能加载 watch/driver，违背“提案侧不拥有执行依赖”的结构目标。最后，driver manifest 的 simulation 支持能力与当前 robot 实际运行模式没有明确分开，旧/第三方配置可能被错误理解。

过程分四部分：① 新增 `physical_agent/application/ports.py` 与 `proposals.py`，以 `PlannerPort`、`ProposalService`、`ProposalResult` 收拢主要 task/action 提案用例；统一完成 capability 可用性检查、planner 调用、action 重编号、组内 dependency 映射、pending 写入、refusal/unavailable/waiting 状态与 proposal correlation。`AgentRuntime`、API task/manual proposal、MCP task/action 已迁移，tool loop 继续通过 proposal-only MCP facade 复用；planner 构造集中到 `agent/planner_factory.py`。② 新增 `protocol/actions.py`：`ActionApproval`、`ActionCorrelation`、`ProposalContext`、`ActionMetadata` 与 `physical-agent/action-metadata/v1`。保持 `Action.metadata: dict` 和 SQLite JSON wire 兼容，但新入口经 typed view 写入可信 provenance；caller 提供的 approval/provenance 会被归一化，state store 仍是 approval authority。③ `ChatRuntime` 删除 `WatchRuntime` import，其 public `auto_step` 仅作兼容 no-op；tool loop 有 proposal 时只返回 `needs_watch=true`、`executed=0`，CLI `--auto-step` 则在 `cli.py` composition root 显式组合 watch step。`driver_coder` 改为 manifest/Python AST/接口表面静态校验，不再加载候选 driver 或调用 `execute()`，动态 conformance 留给未来 watch-side harness。安全扫描扩到 application/agent/llm/api/gui/mcp，对 API watch service 与 legacy GUI controller 只保留精确托管 allowlist。④ `RobotConfig` 与 `RobotRuntimeProfile` 增加显式 `execution_mode: simulation|hardware`；默认 `hardware`，模拟示例显式标注 simulation，hardware 实例不再因 manifest 支持 simulation 而绕过默认实机审批策略；manifest 的 `supports_simulation` 只表示 adapter 支持面，不再承担运行模式推断。

边界保持：没有改变 SafetyGate、watch claim/execute、expected 或 reconnect 语义；`ProposalService` 不 import watch/driver，也不是自动 Agent loop。普通 Chat Action Draft 仍保留文本 fence + 人手 Add to Actions，legacy GUI 仍是 watch-owning composition root。相关 ProposalService、approval anti-forgery、auto_step no-op、execution_mode 与安全边界回归已新增/更新；最终合并结果以本轮 CI 为准。

架构判断：VNext-0 只完成入口与边界地基，后续不能直接跳到 Run/Turn/Event；必须先把 SafetyGate 从 watch 内部的隐式步骤提升为 AgentOutput 中显式、不可删的系统义务。本轮随后完成的 VNext-1/VNext-2 已按这一 assurance-first 路线落地，但仍不是持久化 obligation engine 或统一 Agent runtime。

### VNext-1/VNext-2：AgentOutput 安全义务图与结构化 Gate 闭环

动机：VNext-0 虽然统一了 proposal 入口，却没有改变 `planner -> Action[] -> board` 的核心心智模型。SafetyGate 仍只在 watch 领取 action 后隐式出现，Agent 对外无法表达“执行前必须完成审批与 Gate、执行后才做 expected verification”，前端与下一轮模型也无法可靠判断当前义务的 owner/status。上一版方案把 Run/Turn/Event 排在最前，只会先统一账本，不能先修正这一领域模型。

本轮修正为 `raw model decision -> trusted PlanCompiler -> AgentOutput task DAG -> watch final Gate/execute -> structured feedback -> next turn`。模型只可提供 action intent 与 advisory `SafetyIntent`；可信 compiler 为每个物理 Action 注入唯一 mandatory、watch-owned `SafetyGateTask`，按后端事实可选注入 `ApprovalTask`，让 `PhysicalActionTask` 依赖 Gate，并仅在存在 F4 expected 时注入 `VerificationTask`。`SafetyGateTask` 不是 Action、capability 或 tool，模型/caller 不能创建、删除、完成或伪造 pass；approval 和 expected 都不能替代它。

实现分四部分：① `protocol/agent_output.py` 与 trusted `application/plan_compiler.py` 落地 AgentOutput/AgentTask、不变量和 DAG 编译；`protocol/actions.py` 增加 advisory `SafetyIntent`，LLM schema/prompt 明确 caller 不能伪造 Gate。② ProposalService、API、MCP、AgentRuntime、Chat draft/tool loop 与 ChatPlan 统一返回/保存 compiled AgentOutput；draft 使用 `not_scheduled`，submitted graph 表达真实等待义务。③ watch 对 SafetyGate pass/reject 写 `event=safety_gate` 的结构化 checks/code/evidence 与 action/policy digest；SQLite claim 先跳过未完成 dependency，Gate 继续二次防护；watch step 以 `processed/gate_decisions/state_changed` 暴露 Gate-only 变化，API 与 TUI 不再只看 executed 数。④ React/TUI 展示 task owner/status/dependency，并用 safety feedback 覆盖 Gate 的最新裁决；context_builder 注入 SAFETY 真源摘要、执行契约和结构化反馈供下一轮认知使用。定向测试覆盖 compiler 图不变量/伪造防护、各入口输出与 ChatPlan、Gate pass/reject、dependency scheduling、watch stats 及 Web/TUI 展示。

后续硬化把“客户端 overlay”收回 application read model：新增 `application/output_projection.py`，以 compiled topology 为骨架，将 Action Board 与 `safety_gate`/`expectation_check` feedback materialize 为 current AgentOutput。pending/in-progress/completed/cancelled 和 approval 决定当前 task status；`in_progress` 映射为 checking；Gate reject 令 PhysicalAction/Verification skipped；有 expected 的 completed action 在 expectation event 到来前仍处于 verification checking。`current_agent_output()` 会从 active board actions 重建义务，因此 chat-only plan 覆盖 singleton ChatPlan 后不会隐藏仍在等待/执行的物理任务；API/MCP/legacy GUI 通过 `project_chat_plan()` 读取同一 projection。AgentRuntime 同样 materialize output，并等待 required verification 终态后才报告 task completed。

认知闭环补了受控回灌：context-aware planner path 接收 live SAFETY、feedback 与 previous AgentOutput；`ContextBudget` 对 feedback 设事件数和字符上限，超限时保留近期 event/code/check 摘要，防止 watch history 无界挤占 prompt。普通 planner port 仍兼容旧 `plan()`，这不是自动 replan loop。

watch/state 侧同步修了六类竞态与卡死：① effective timeout 固定为 capability override 或 watch default，Gate 与 execute 使用同一预算；② heartbeat 失败将本地 profile 标 degraded 并阻止该 robot 新 claim，恢复后放行；③ SQLite 在同一 claim transaction 内检查 busy robot，允许不同 robot 分别领取但禁止同 robot 重叠；④ impossible、unknown 或已 cancelled dependency 使下游 action 显式 terminalize，写 Gate/action，并在有 expected 时写 verification skipped；⑤ `append_feedback_event()` 用 `BEGIN IMMEDIATE` 原子 read-append-write，避免多 writer 丢 history；⑥ ProposalService 在写 board 前验证 graph/external dependency，再调用 `append_pending_actions()` 以一个 SQLite 事务写完整 actions batch；任一 id 冲突会回滚整批，不再逐条 append。定向测试覆盖 materializer/ChatPlan 重建、verification 等待、context budget、heartbeat block/recovery、effective timeout、per-robot serialization、dependency cascade、并发 feedback append 与 proposal batch all-or-nothing。

执行者 ownership 随后由 W6.1 收口：SQLite 新增 named `runtime_leases`，Watch setup 在 connect driver 前竞争唯一 `watch-executor` lease，每次 setup 生成不可复用的 owner id。runtime 在 connect/heartbeat/claim/idle observe/halt 等关键阶段续租；失租抛带 `fatal_watch_error` 的 `WatchLeaseLostError`，API watch service 停止循环。action claim 写同一个 owner，completed/cancelled 通过 claim_owner CAS；旧 owner 的迟到结果不能覆盖已经 recovery/reclaim 的 action。失租后的 shutdown 仍断开本地 transport，但刻意不向继任者控制的硬件发送 stale halt。workspace reset 使用 exclusive transaction 检查 active lease 并 fail closed，HTTP 层返回 409。测试覆盖 lease acquire/renew/release/expiry、双 runtime 排他、stale completion、fatal service stop 与 reset guard。

状态边界：本轮任务图仍是由 trusted compiler、Action Board 和 feedback materialize 的 current projection；Action Board/feedback 仍是运行事实。actions batch 已原子 all-or-nothing，但尚未增加独立 task table，也没有把持久化 task graph/obligation rows 与 actions 放进同一事务；server-side action id 仍在事务外按 snapshot 计算，并发冲突会安全回滚整批而不是自动重试。Run/Turn/Event 与完整 terminal task history 未实现。W6.1 解决的是 workspace/SQLite 级唯一执行者与 stale result fencing，不是 driver/hardware token：已经发出的命令无法由数据库撤销，设备也不会识别 owner epoch。因此不把本轮描述成完整 task runtime 或硬件级 HA fencing。

边界保持：认知侧仍不 import watch/driver；compiler 只编译义务，不预判 Gate 通过；watch 保留最终裁决与唯一 execute 权；`SAFETY.md` 仍是文件真源；F4 expected 仍是执行后诊断。后续持久化、hardware fencing 与账本口径见 `SPEC.zh-CN.md` VNext-3/W6.2/VNext-4 和 `agent-architecture-vnext.zh-CN.md`。

### R0：架构减法规格与删除前审计

动机：VNext-1/2 已把 SafetyGate 升为 `AgentOutput` 中显式、不可伪造的义务，但仓库仍同时维护 legacy GUI/FastAPI+React 两套 Web 栈、一次性 Markdown migration/full Workspace 协议、`auto_step` 兼容形状、streaming fence 与结构化 output、proposal 顶层 actions 和 `agent_output.actions` 等重复面。继续实现 VNext-3/4、W4/W6.2 或 F6 会把这些分叉固化进更多 schema、客户端和测试。因此当前主线从“补功能”切成 `docs/specs/001-architecture-simplification/` 的 R0-R8 架构减法。

本轮只做规格和只读审计，没有删除生产代码。GUI parity 枚举了 legacy 的十个 HTTP 控制面和用户能力，确认 React/FastAPI 仍缺安全首次 Setup、真实 watch runtime health、未启动 watch 时的 execution mode 可见性，以及 wheel 内的 Dashboard 资源；FastAPI LLM hardware integration 和完整 streaming draft→Add to Actions e2e 也需先移植。GUI 内 watch start/stop/step、hard-coded Demo、per-message planner、browser code skill/raw doctor 决定有意退役：执行生命周期改由正式 watch 管理，Demo 用 `setup --smoke-test`，Dashboard chat 固定 auto 而调试 override 用 CLI `chat --planner`，code skill 结构化结果用 CLI `chat --show-code-result`，诊断用 operator doctor。workspace reset 采用保留 YAML、active lease fail closed 的更安全语义，不复制浏览器覆写硬件配置的旧 factory reset。

Markdown 审计确认 migrator、`LegacyMarkdownWorkspaceReader` 和 full Workspace helper/protocol 可以退役，但 `SqliteStateStore` 仍直接借 `protocol.workspace.Workspace` 读写 `SAFETY.md` 与镜像 `LOG.md`，doctor 也依赖最小 front matter。执行顺序因此固定为“先抽 safety/log sidecar 并锁行为，再删 migrator/full Workspace”；显式 markdown backend 和隐式旧文件集合仍必须 fail closed，避免 SQLite 在旧目录旁形成双真源。提前结束 B6 的一个版本迁移窗口时保留历史后路：需要迁移的用户在独立 worktree checkout `9072b4e`（或删除提交之前版本）完成迁移，再回当前版本运行不带 `--force` 的 `physical-agent init`，随后运行 `physical-agent state-check`。

streaming 审计进一步发现：当前 done item 虽已有 `agent_output`，它仍由完成后的文本 fence 反向解析而来，且 API SSE 转发时把该字段丢弃；React 又从正文第二次解析 fence，TUI 只看 state plan。R5 因此先建立 rule/LLM reply/proposal 共用的 typed Chat result，直接编译 draft `AgentOutput`，再由结构化 actions 生成兼容 fence；React structured-first/fence-fallback 双轨一轮，R6 完成官方 consumer migration 后才在 R7 删除 fence。R0 不预先锁死 transport 实现：正式方案必须同时保留一个 authoritative action set、真实首 token/delta 与中途 abort；若 provider-neutral client 无法兼得，暂停并单独做产品取舍，不能用完整结果的本地分块静默降级 streaming。

同时确认 `chat_runtime.py::_append_actions` 零调用，它重复了 ProposalService 已拥有的编号、dependency remap 和 batch append；已点名进入 R6，连同专属 `_normalize_depends_on` import 与 `_max_action_number()` 删除。`/api/state.actions` 明确保留为 Action Board 运行真值；只退役 task/chat/manual proposal response 的顶层 convenience `actions/action`。本轮边界保持：两条安全宪法、watch、SafetyGate、driver、SQLite schema 和运行 API 行为均未修改；当前仍是 GUI/迁移/fence 删除 No-Go。

### R1.5：正式 Dashboard 补缺与 legacy launcher strangler cutover

动机：R0 已证明不能直接删除 legacy GUI：正式 FastAPI/React 栈缺安全首次初始化、真实 executor health、watch 未运行时的 execution mode 和 wheel 内静态资源；LLM integration/model override 与 streaming draft → pending 也缺迁移证据。本轮只补正式栈并切入口，不删除 `physical_agent/gui/`，让下一轮仍有完整回退面。

后端新增 proposal-only 的 `POST /api/project/initialize`：只创建缺失的默认 config/workspace，不加载 `WatchRuntime`，重复调用幂等，invalid config fail closed。`write_default_config(overwrite=False)` 从 exists→`open('w')` 改成“完整临时文件 + exclusive hard link”原子发布，避免并发初始化截断用户刚创建的 config；controller 内再串行同 app 的初始化请求。SQLite 增加只读 runtime lease projection，health/state/SSE 暴露 `executor={mode,status,embedded_enabled,lease,last_error}`，以进程内 service phase 与 active `watch-executor` lease共同区分 waiting/embedded/external/none，`watch_enabled` 只保留配置兼容语义。no-watch API 每 5 秒推送 executor heartbeat，使外部 watch 启停可见；watch-step 摘要剔除续租时间戳，避免 500ms 空闲轮询。external lease 存在时 embedded service 安静 standby，释放后接管；真实 driver setup/connect 失败则 degraded fail-stop，不再每 0.5 秒重连硬件刷错。

入口侧把 `physical-agent gui` 改为正式 `create_app()` 的薄 launcher：默认 embedded watch，`--no-watch` 只关闭内嵌执行器，host/port/no-open 保留；CLI import 不再触碰 `physical_agent.gui`。自动开浏览器改为 daemon readiness waiter，只有 `/api/health` 2xx 后才打开，wildcard bind 地址映射到本机可访问 URL。`api` 与 `gui` 复用同一启动函数，缺 `[server]` 时给出可执行安装提示。

发布侧选择 `physical_agent/dashboard/dist` 作为唯一正式 package resource，Vite 直接输出该目录；`pyproject.toml` 打包 React build，FastAPI 首选 package-local path，源码 `frontend/dist` 只作过渡 fallback。由于 setuptools 增量 `build/lib` 会把旧 hashed chunk 带回 wheel，新增最小 build hook 在 `build_py` 前只清理目标 Dashboard dist，并用“source resource members == wheel members”测试锁住。clean-wheel smoke 在两个全新 venv 分别验证 base wheel 的 server-extra 提示，以及 wheel + `[server]` 下 `gui`、`api`、`/`、hashed asset 和 `/api/health`。

React/TUI 统一消费 executor projection，不再把 `watch_enabled` 染成“正在运行”。Config/Robots 从共享的 `/api/config` 读取 YAML，因此无 executor/capabilities 时仍显示 hardware/simulation；Dashboard 补首次初始化按钮，成功后并行刷新 state/config；Settings reset 明示清 workspace、保留 YAML/LLM、恢复 SAFETY，factory reset 指向 `physical-agent setup --force`。GUI watch start/stop/step、hard-coded Demo、逐消息 planner、browser code skill/raw doctor 不复制回正式栈，替代分别是正式 watch 生命周期、`setup --smoke-test`、CLI `chat --planner`、CLI `chat --show-code-result` 与 `doctor`；canonical routes 负用例固定旧控制面为 404。

测试迁移包括 FastAPI LLM driver model override/生成结果、无 watch 的 execution mode、初始化/executor/external lease/standby/fail-stop、thin launcher/browser readiness、wheel exact contents，以及 Playwright 的 mock stream fence → draft card → 真实 `/api/actions/propose` → 独立 `/api/state` pending 主链。最终本地证据：Python 3.12 `419 passed`（1 个既有 Starlette/httpx 弃用 warning），frontend production build 通过，TUI typecheck/test/build 通过（59 tests），clean-wheel 双 venv smoke 通过，Playwright 可发现 25 项。真实 Playwright 尚未运行：普通与放宽沙盒两次从官方 CDN 都得到 0 MiB 截断 Chromium zip。因此 cutover 可以提交，legacy GUI 仍保留且 R2 删除继续 No-Go，需 pushed commit 的 CI/可用浏览器环境补绿后再进入下一步。

R1.5 的独立门禁随后由 draft PR #1 补齐。第一轮真实 Chromium 已成功安装并跑出 22/25：它抓到 Gate reject 后 physical task 的过期 `failed` 预期（正式 projection 语义是 `skipped`），以及 missing-config 时两次预期 `/api/config` 404 被通用 console-error 断言误判；同轮还暴露 GitHub Python 3.12 runner 不再隐式提供 `setuptools`/`wheel`，而本项目的 `--no-isolation` wheel 测试需要完整 build-system 工具链。`2d5e909` 只修正这三类验收/环境契约，第二轮 CI run `29139972352` 的 Python full、Safety、TUI、frontend、clean-wheel 与真实 Chromium 25/25 全绿，R2 才由 No-Go 转为 Go。

### R2：删除 legacy GUI 实现

R2 没有再改 `physical-agent gui` 的用户入口：它继续复用正式 `create_app()`，默认 embedded watch，并保留 `--no-watch`/host/port/no-open。删除的是第二套实现与第二套事实来源：`physical_agent/gui/` 的 controller、标准库 HTTP server、static HTML/JS/CSS，全套 `test_gui_server.py`/`test_gui_static_contract.py`，以及 wheel 的 `physical_agent.gui` package-data。此前迁移到 FastAPI/React 的 LLM integrate、初始化、executor、execution mode、draft→pending、i18n、reset 和正式 route 负用例继续保留。

安全边界测试同步移除 legacy controller 对 `WatchRuntime` import 的 allowlist，扫描目录也不再包含不存在的 GUI package；正式 API 只剩 `ApiWatchService` 这个显式 lazy watch composition root。`current-architecture-audit.md/html` 同步重生成，不再把旧 GUI 描述为现行入口。回滚单位仍是整个 R2 删除提交，不需要回退已经独立验证的 R1.5 cutover。

第一次删除后全量回归的 wheel 负断言发现：setuptools 增量 staging 仍残留 `build/lib/physical_agent/gui`，即使源码与 package-data 已删，wheel 仍可能把旧 package 带回。R2 因此把现有 build hook 扩成同时清理陈旧 Dashboard hash 资产与 retired GUI staging，并把“wheel 中不存在 `physical_agent/gui/`”固定为发布负契约。本地最终证据为 Python 405 passed、Safety/API/docs 定向 66 passed、frontend build、TUI 59 tests/typecheck/build 与 clean-wheel smoke；pushed commit `5764bac` 在 draft PR #1 / CI run `29140290422` 上再次通过 Python full、Safety、TUI、frontend、packaged-wheel 与真实 Chromium 25/25，R2 正式完成。

## 3. 关键决策与偏离（跨阶段汇总）

1. **A1 曾被"替代"后补做**——教训：spec 状态要回写，不能只散落在 handoff。
2. **SAFETY 永远是文件真源**（B2 起）：安全规则不进数据库，API 物理上改不了。
3. **默认切换永远放在硬化之后**（B3.8 模式）：原子→恢复→矩阵测试→才切默认。
4. **上传内容全程标记不可信**（B4b 起）：注入到任何 LLM 上下文都带 untrusted 政策。
5. **API 顶层 import 不得触及 watch/drivers**（C1 起，有测试强制）。
6. **重置不碰 watch**（E0.1）：宁可偏离 plan 原文也不破 P0 不变量。
7. **超时即 halt**（W1）：执行超时后硬件状态未知，fail-safe 优先。
8. **审批死胡同在 F1 收口**：不新增 runtime backend 状态机状态，放行记录落在 action metadata；Actions 板审批改变"是否等人"，不改变 SafetyGate 校验链。
9. **项目根 `physical-agent.yaml` 是 ignored 本地运行配置**（F0）：本轮按要求切到 `planner: llm` 但不强行纳入版本库；共享默认仍以 `config.py` 的 `rule_based` 与模板为准。
10. **F0 补测凭据源固定为 `.env`**：真实 provider 测试使用项目 `.env`，实验命令用空 settings workspace 避免旧 `workspace/.llm.json` 覆盖；GUI/runtime 的本地设置机制暂不重构，留给后续配置收口。
11. **退役 active backend 与保留迁移 reader 分离**（B6）：运行态只支持 SQLite；旧 Markdown 文件只作为迁移输入读取，迁移 reader 不实现 `StateStore`，不进入 factory，也不承担新功能字段。
12. **两个 Approve 必须拆语义**（F1）：Chat draft 的按钮叫 Add to Actions，只代表"创建 action"；Actions 板的 Approve execution 才代表"放行 requires_approval action 被 watch claim/execute"。
13. **approval.required 不信任认知侧或 UI**（F1）：LLM draft、前端表单、API caller 都不能决定是否需要审批；后端每次写入/读取/claim 前按真实 robot/capability 重新归一化。
14. **raw/debug 是兜底，不是主界面**（F2/F2.5）：已知协议字段仍写定制组件；unknown/raw/private 字段可以折叠展示，但优先用 AntD 原生 Tree 或轻量摘要，避免把"漂亮 JSON"误当成可读产品。
15. **上下文组装是只读边界**（F3）：`context_builder` 只读 StateStore，不写 log/memory/action，不 import watch/driver/SafetyGate，不发 LLM 请求；planner purpose 保持独立，避免把结构化 action plan prompt 硬并进 chat proposal。
16. **expected 是诊断元数据，不是安全规则**（F4）：它可由 LLM 提出、可被 UI 展示、可回灌给 LLM，但永远不替代 SafetyGate；坏 expected 只能让 expectation check skipped，不能阻止或放行动作。
17. **可复用 schema 放 protocol，执行编排留 watch**（F4）：expected 的 schema/归一化/纯比对函数在 `protocol/expectations.py`，watch 只负责在唯一执行链路中决定何时调用；这样 API/state 顶层可处理 metadata，却不加载 watch/drivers。
18. **重连恢复通信，不恢复动作语义**（W3）：transport 可以后台重连，但旧 execute 永不排队、永不重放；断线中的 action 以 failed/unknown 收口，下一次世界事实仍要靠 observe/health。
19. **Typer CLI 与 Ink TUI 并存**（T）：Typer 继续管脚本化/自动化，Ink 管 SSH/无 GUI/开发者日常交互；TUI 是独立 Node 包，不塞进 Python CLI。
20. **TUI 是纯 API/SSE 客户端**（T）：TUI 不直接读写 SQLite/workspace，不 import watch/runtime/driver，不新增硬件控制命令；审批只解除“等人”，不改变 SafetyGate。
21. **前端偏好用轻量字典与 AntD token，不上重库**（C4/E3）：当前需求只需要高频文案和主题切换，i18next 与新 UI 库继续不引入。
22. **默认 CI 测安全契约，full run 手动收口**（CI-lite）：自动阻塞项只覆盖安全边界和主 GUI 构建；慢 e2e、TUI 与 Python 版本矩阵提供信号但不默认卡住日常重构。
23. **TUI upload 只通过 API**（T3）：本地文件读取只用于构造 multipart `POST /api/upload`，不直接写 workspace/uploads，不调用后端路径式 ingest 作为交互入口，untrusted/memory/chunks 仍以后端结果为准。
24. **TUI 不做 YAML 编辑器**（T3）：config 视图只读，robot 注册只调用既有 `POST /api/config/robots`；编辑已有 robot 或任意 yaml 字段继续由人手改配置并重启 watch。
25. **终端 raw fallback 只做摘要**（T3）：Ink 里没有 dashboard 的可折叠 JSON tree，默认展示已知字段与短 raw summary，避免把 config/robot/upload 视图退回整页 JSON。
26. **Overview 不把整份 state 交给 RawDebug**（F2.5）：已知 schema 先经 viewmodel 消费并定制渲染；RawDebug 只展示 unknown/raw/backend private 片段，避免“折叠全量 JSON”再次成为事实上的主界面。
27. **展示摘要与 JSON 输入要分开**（F2.5-json-style）：展示区统一用 `JsonSummaryLine` 摘要；仍需用户手写参数的 ProposalPanel 保持明确的 `Params JSON` textarea，避免把输入能力误删。
28. **RawDebug 也用 AntD 原生组件**（F2.5-raw-debug-antd）：unknown/raw 字段仍可展开调试，但视觉语言必须与 Overview 产品组件一致；因此移除 `react18-json-view`，避免 JSON viewer 成为新的事实主界面。
29. **TUI 启动参数接受裸 API URL**（TUI-api-arg-fix）：Windows/npm/tsx 链路可能吞掉 `--api` flag；CLI 入口兼容 positional URL，保持文档命令和实际落地命令都能启动，不改变 TUI 的 API-only 边界。
30. **TUI 命令验收以场景文件为真源**（TUI-command-acceptance）：命令级回归不只测 parser 或组件，而是用 `.scenario` 记录输入、mock API/SSE、输出与状态变化；新增命令必须更新场景和 `docs/tui-command-matrix.md`，避免 README/帮助与可测行为分叉。
31. **audit 文档展示先落静态 docs 页**（Audit-doc-html）：这轮目标是把已有审计内容呈现出来，不是把 audit export 接入 Dashboard；选择 `docs/current-architecture-audit.html` 可直接打开、零运行态依赖、零 SafetyGate/watch/API 触碰，Dashboard 内页预览继续留作 F2 远期后续。
32. **ProposalService 是 application use case，不是 Agent runtime**（VNext-0）：它只负责 task/action → proposal → pending board；Chat reply、审批、Gate、执行、观察与自动重规划不应继续塞入该类。
33. **typed metadata 先兼容 wire，再逐步升级消费者**（VNext-0）：`Action.metadata` 暂时保持 dict/JSON，已知字段经 v1 Pydantic 模型解析且未知扩展保留；不能因为有强类型 view 就声称 frontend/TUI 契约已经统一。
34. **execution_mode 以实例配置为真源，默认 hardware**（VNext-0）：manifest 只描述 driver 是否支持 simulation，不能替当前连接声明“这是模拟器”；新硬件注册默认 hardware，simulation 必须显式选择。
35. **ChatRuntime 永不推进 watch**（VNext-0）：`auto_step` 只保留兼容形状，不再有执行语义；driver 动态验证也必须进入未来显式的 watch-side conformance，而不是在 driver coding agent 内 allowlist `execute()`。
36. **AgentOutput 不是 raw model output**（VNext-1）：模型只能产生不可信 decision/action intent；只有 trusted `PlanCompiler` 可以注入系统任务、可信 owner/status 与 Gate 依赖。
37. **每个物理 Action 必有唯一 GateTask**（VNext-1）：`SafetyGateTask` mandatory、watch-owned，既不是 Action 也不是 tool；caller 提供的 `safety_gate=passed` 或自定义 task graph 不具权威性。
38. **approval、Gate 与 verification 是三个不同义务**（VNext-1）：approval 决定是否等人，Gate 在执行前裁决，F4 expected 在执行后诊断；三者不能合并成一个泛化 status。
39. **Run/Turn/Event 是闭环账本，不是心智模型起点**（VNext-1）：先稳定 compiled task DAG 与结构化 Gate feedback，再建立生命周期、恢复和 timeline，避免给旧的 Action[] 模型只套一层事件外壳。
40. **Gate pass 与 reject 都是 watch 事实**（VNext-2）：两者都写结构化 feedback/checks/digest；AgentOutput 只声明待履行的 Gate 义务，不能预填 outcome。
41. **task status 是 application materialized projection，不是执行权威**（VNext-2）：服务端用 Action Board、approval metadata 与 watch feedback 覆盖 compiled 初始状态；客户端只消费结果，不能写回 Gate 完成，也不能把 projection 冒充持久化 obligation engine。
42. **`executed=0` 不代表没有状态变化**（VNext-2）：Gate reject 会处理 action、写 feedback 和终态却不调用 driver；watch/API/TUI 以 `processed/gate_decisions/state_changed` 判断刷新。
43. **compiled topology 与 materialized state 分离**（VNext-2）：PlanCompiler 决定不可绕过的节点/边；output_projection 只把 board/feedback 事实映射为当前 status，不得修改 topology 或制造 Gate pass。
44. **ChatPlan 是 presentation singleton，不是 task truth**（VNext-2）：chat reply 可以覆盖 plan 文档，但 API/MCP/GUI 必须从 active Action Board 重建义务，不能让 pending action 因聊天消失。
45. **driver completed 不等于 Verification completed**（VNext-2/F4）：有 expected 时，AgentRuntime 必须等 `expectation_check` 终态；materializer 在间隙显示 verification checking。
46. **planner 回灌必须有事实优先级和预算**（VNext-2/F3）：contextual path 可见 SAFETY、feedback、previous output，但 feedback 只保留预算内近期结构化信息；这提供下一轮依据，不默认触发自动重试。
47. **Gate 必须检查实际执行 timeout**（VNext-2）：capability override 与 watch default 先求 effective timeout，SafetyGate 的 max policy 和 `driver.execute()` 共同使用，避免“未配置 capability timeout 就漏检 default”的缝隙。
48. **workspace runtime lease 是软件执行者真源**（W6.1）：per-robot busy check 只管 action overlap；Watch 必须先持有唯一 named lease 才可 connect/heartbeat/claim/observe/halt，第二实例 fail closed。
49. **不可能依赖必须终态化**（VNext-2）：waiting dependency 保持 pending；unknown/cancelled 或级联 impossible dependency 则显式 rejected/cancelled，并写 verification skipped，避免永久等待。
50. **feedback append 原子不等于 Event ledger**（VNext-2）：事务追加解决 lost update，但 history 仍是单文档列表，没有 sequence/cursor、独立事件表、保留策略或 Run correlation。
51. **actions batch 原子不等于 task graph 原子**（VNext-2b/VNext-3）：`append_pending_actions()` 保证多 action 全有或全无；AgentOutput graph 仍是派生/plan 数据，尚无持久化 task rows 可与 action batch 同事务提交。
52. **executor owner 必须贯穿 claim 与 terminal CAS**（W6.1）：每次 Watch setup 使用新 owner；过期 action 被 successor 重领后，旧 owner 的 completed/cancelled 写入必须返回失败并触发 fatal stop。
53. **失租后的旧 owner 不得善意 halt**（W6.1）：halt 本身也是物理副作用；successor 接管后，stale shutdown 只能断开自己的 transport，不能发送可能干扰新 owner 的 halt。
54. **reset 不能抹掉活跃 ownership**（W6.1）：workspace reset 与 lease acquire/renew 串行；active lease 时 fail closed，避免删表制造 split brain。
55. **数据库 lease 不是设备 fencing token**（W6.2）：它能阻止下一次受检查的软件操作，却无法撤销 in-flight I/O 或让硬件拒绝旧 epoch；实机 HA 接管仍需 driver/transport/device 层协议。
56. **先减兼容面，再扩 Agent runtime**（R0）：VNext-3/4、W4/W5/W6.2、F0 后续、F5/F6、B4-vec、registry/read-model 与自动 replan 在 R0-R8 期间冻结；收口后按真实需求重新排序，不自动恢复旧排期。
57. **legacy GUI 删除以用户任务 parity 为门禁**（R1.5/R2）：保留命令体验但只启动正式 FastAPI+React；仍支持的任务必须先覆盖并测试，违背 proposal-only 边界的旧能力则显式退役并给替代，不能静默消失，也不机械复制危险语义。
58. **迁移入口退役不等于删除 safety/log sidecar**（R3）：一次性 Markdown reader/full Workspace 可以删；`SAFETY.md` 文件真源、`LOG.md` 镜像和旧目录 fail-closed 检测属于当前生产安全边界，先抽聚焦 adapter。提前结束迁移窗口以 `9072b4e` 独立 worktree 作为救援指针。
59. **structured output 必须独立于 fence 生产**（R5/R7）：从 `action-draft` 反向解析出的 AgentOutput 不是新通道；先建立 typed Chat Turn，以 structured actions 生成兼容 fence并双轨验证，后续提交才可删 fence。
60. **Action Board truth 与 proposal action payload duplication 分开**（R6/R7）：`/api/state.actions`/SQLite board 永久保留；只删除已有 `agent_output.actions` 替代的 task/chat/manual proposal 顶层 `actions/action/draft_actions`，approve/reject mutation result、envelope/status/correlation 和内部 `ProposalResult.actions` 不在此列。
61. **统一协议，不强行统一 presentation**（R6）：React 与 TUI 可以保留不同 formatter/viewmodel；只统一后端 `AgentOutput`、projection 和 owner/status/Gate 解释，避免跨浏览器/终端的伪共享抽象。
62. **`watch_enabled` 不是 executor health**（R1.5）：真实执行者状态必须合成本进程 service phase 与 SQLite active lease；driver/hardware health 继续由 capabilities/runtime profile 单独表达。
63. **安全初始化用原子发布且不拥有 watch**（R1.5）：首次初始化 handler 只能创建 config/workspace；已有 config 不覆盖，并发创建不能被 TOCTOU 截断；执行器由 lifespan 自行等待和接管。
64. **保留 `gui` 命令，不保留第二 controller**（R1.5）：命令兼容通过正式 FastAPI app factory 实现；legacy 模块只在 R2 门禁通过前作为回退存在，不再是默认入口。
65. **真实 setup 失败不自动高频重连硬件**（R1.5）：missing init/external lease 可以安全轮询；driver connect/setup 错误 degraded fail-stop，交给显式进程生命周期重试。
66. **Dashboard 是 wheel package resource，hashed build 必须去陈旧化**（R1.5）：源码 cwd 只能做开发 fallback；增量 wheel 在复制前清目标 dist，并验证 wheel 资源集合与当前 Vite 输出严格相等。

## 4. 经验教训（流程侧）

- **重写必须先做旧功能 parity checklist**：C3 的静默丢失靠事后审计才发现。
- **快照式文档过期极快**：REFACTOR-LOG/system-summary 写完次日即失真；解法是活账本（SPEC §4）+ 每轮更新一行。
- **git/CI 基建要跟上纪律**：长期单分支不 push、无 CI、测试对宿主环境敏感（代理变量/Python 版本），均记为工程欠账。
- **mock 测不出阻塞类缺陷**（W1 的教训）：凡是"永不失败"的测试替身，都在掩盖一类真实故障模式；需要故意注入挂死/超时的对抗性测试。
- **LLM 实验先固定凭据源与 provider 能力，再谈 planner 质量**（F0 的教训）：同一个 OpenAI-compatible 入口可能不支持 `response_format`/JSON mode；批量实验要先用 `.env` 连通、记录模型能力，再靠本地 schema 校验兜底，否则会把 provider 兼容问题误读成 planner/Gate 问题。
- **后端退役要同时保迁移旁路与清 UI 口径**（B6 的教训）：删除 factory 分支不够，CLI 迁移、state-check、前端说明、e2e mock、操作手册和旧 handoff 都可能继续暴露退役后端。
- **同名产品动作要拆 UI 文案和数据语义**（F1 的教训）：draft 提交与执行审批都容易被叫 Approve；若文案不拆，用户会误以为点一次就放行执行，或误把提交动作板当成绕过审批。
- **模型自带的证明必须给人看见**（F4 的教训）：expected 不参与安全裁决，但它会影响后续诊断上下文；至少要在 draft/action 详情露出摘要或 raw，避免变成不可见的“模型自证”。
- **新增全局 UI 叠层先给 e2e 默认关闭路径**（E3 的教训）：首次 Tour 这类全局浮层会遮挡旧流程测试；默认测试态应显式写 localStorage 关闭，再单独测试首次打开/关闭/重开。
- **e2e webServer 不应复用用户本地配置**（T/C4/E3 的教训）：Playwright 启动 API 前先写 `.tmp/e2e/physical-agent.yaml` 与临时 workspace，避免 `--force` 初始化覆盖根目录 ignored 的个人运行配置。
- **CI 分层要写给人看**（CI-lite 的教训）：只在 yaml 里调 `continue-on-error` 不够；必须说明哪些检查阻塞、哪些只是信号、什么时候手动 full run，否则“宽松”会被误读成“可以忽略”。
- **同一能力多入口要复用同一后端边界**（T3 的教训）：dashboard 已有 `/api/upload`、`/api/config`、`/api/config/robots` 时，TUI 只补客户端和展示，不应另开路径或把本地文件/配置写入规则复制到终端侧。
- **Ink 交互测试要模拟 readable stdin，而不是只测组件快照**（TUI-command-acceptance 的教训）：Ink 5 通过 `stdin.read()` 和 `readable` 驱动输入，scenario runner 需要提供带 `ref/unref/read` 的测试流；命令粘贴与回车之间也要留给 React/Ink 一次状态更新，否则容易测到旧输入值。
- **可读性验收要锁“不开 raw 能否回答问题”**（F2.5 的教训）：只断言 JSON tree 折叠不够；Playwright 应直接检查用户问题对应的表格、卡片、Descriptions 是否存在，并确认 raw 内容默认不可见。
- **入口收敛不等于 Agent runtime 收口**（VNext-0 的教训）：共享 ProposalService 解决了重复用例，但没有自动产生安全义务图、统一 feedback 或闭环状态机；后续文档和产品文案必须区分“安全 proposal runtime”与“统一自主 Agent runtime”。
- **先做账本会掩盖错误的领域模型**（VNext-1 的教训）：Run/Event 能统一 correlation，却不会自动让隐式 SafetyGate 成为 Agent 的公开义务；演进顺序应先 assurance loop，后 ledger envelope。
- **把 status overlay 留在客户端会再次分叉**（VNext-2 的教训）：compiled graph、Action Board 与 feedback 的合成规则应集中在 application projection；Web/TUI 只渲染同一 materialized 输出。
- **软件 ownership 与硬件 fencing 要分层命名**（W6 的教训）：workspace runtime lease 已覆盖单数据库内的执行者排他、claim CAS 和 reset guard；不能因此声称 in-flight command 或设备控制权已被 epoch fence。
- **删除/迁移清单必须来自代码 surface，不只来自现有测试**（R0 的教训）：legacy GUI 的 setup/watch/doctor/task 多条路径没有直接测试，若只搬测试会再次漏功能；先枚举端点、用户任务、打包入口、文档和负用例，再决定覆盖或有意退役。
- **兼容字段存在不代表已经有独立新通道**（R0 的教训）：stream done 内部已有 `agent_output`，但它仍由 fence 反解析且 API 丢弃；判断迁移完成要追 producer→transport→consumer→persistence 的事实来源，而不是只看 schema 名称。
- **带 hash 的前端产物要防增量构建残留**（R1.5 的教训）：只让 Vite `emptyOutDir` 不够，setuptools 的 `build/lib` 仍可能保存旧 chunk；wheel 测试必须比较资源全集，而不是只断言“有 index 和任意 asset”。
- **浏览器验收不可用 discovery 冒充 runtime**（R1.5 的教训）：`playwright --list` 能抓语法/发现问题，但不能证明 route handler、SSE 与 DOM 交互实际成立；浏览器二进制不可用时应保留删除 No-Go，而不是为了收工勾绿。
- **源码删除不等于发布物删除**（R2 的教训）：setuptools 增量 staging 会保留已经从源码树移除的 package；退役模块必须增加 wheel member 负断言，并在 build hook 中清理对应 staging 目录。

*新一轮工作完成后：§1 表格加一行，§2 追加小节，决策/教训有则补记。*
