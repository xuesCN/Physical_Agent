# PLAYBOOK：待办项执行指引

> 配套 `SPEC.zh-CN.md` §4 矩阵使用：矩阵管"做什么/状态"，本册管"怎么做"。每项含：思路、关键文件、坑、验收。
> 写给后续执行者（人或 agent）。动工前先读 SPEC §0 不变量与 REFACTORING §3 决策先例；每项动工时按惯例先出一份轮次 brief。
> 最后更新：2026-07-17

---

## R0-R8 架构减法与兼容面退役

**目标**：本条目不推进新的 SPEC 功能，而是删除重复实现和过期兼容面，使 FastAPI+React、SQLite Action Board/feedback、trusted `AgentOutput` 与独立 watch 成为唯一正式主链。完整约束、顺序和原子勾选项见 `docs/specs/001-architecture-simplification/spec.md`、`plan.md`、`tasks.md`。

**顺序**：① 冻结范围并审计；①.⑤ legacy GUI parity/缺口补齐/wheel + thin `gui` launcher strangler cutover；② 独立验证后才删除 legacy GUI；③ 先抽 safety/log sidecar，再删 Markdown migrator/full Workspace；④ 删 `auto_step`；⑤ 建立真正的 structured Chat result 并让 `action-draft` 双轨一轮；⑥ 收敛 read-model/consumer，点名删除 `chat_runtime.py::_append_actions`；⑦ R5+R6 门禁全绿后再删 fence 和 proposal action payload 重复字段；⑧ 文档、wheel 与全量测试收口。不得跳过 1.5，步骤 5 完成后只能进入步骤 6。

**关键取舍**：Dashboard 保留安全初始化、workspace reset、真实 executor health、execution mode 与所有现有 proposal/approval/hardware 主路径；GUI watch start/stop/step、hard-coded Demo、per-message planner selector、browser code skill/raw doctor 有意退役，替代分别是正式 watch 生命周期、`setup --smoke-test`、Dashboard 固定 auto + CLI `chat --planner`、CLI `chat --show-code-result`、operator `doctor`。Markdown migration 不再保留版本周期，但 `SAFETY.md`/`LOG.md`、legacy workspace fail-closed 检测必须保留；旧用户在独立 worktree checkout `9072b4e` 先迁移。`/api/state.actions` 是 Action Board 真值，永不作为“重复 response 字段”删除。

**冻结**：R0-R8 已完成，但 R8.1 只做 review hardening，不是功能解冻轮次。R8.1 不解冻 VNext-3/4、W4/W5/W6.2、F0/F5/F6、B4-vec、registry/read-model 或自动 replan；只有出现可复现的真实需求并形成显式 SPEC 决策后，才可重启对应条目。

**验收**：每个删除项都有前置正反测试或替代入口；双轨有独立一轮证据；wheel 安装后能启动同一 React Dashboard；全量 pytest、frontend build/e2e、TUI build/test、安全扫描与 docs/CLI grep 全绿。R0 已完成；R1.5 正式栈补缺、thin launcher 与 clean-wheel smoke 经 draft PR #1 / `2d5e909` 独立验证，真实 Chromium 25/25。R2 随后删除 legacy controller/server/static/tests/package-data 与 safety allowlist 例外，保留 `physical-agent gui` 命令作为正式 FastAPI + React launcher。

**当前进度**：R3-R8 的删除与双轨门禁均已完成并有提交/远端 CI 证据。R8 已完成收口：正式 current docs 与示例统一到 SQLite/structured `AgentOutput`/独立 watch 主链；删除可陈旧的 `ChatPlan.actions` 第三份投影和 chat-side `executed=0` 心智残留；proposal/chat/task 与 approve/reject 的 200 响应写入 typed OpenAPI；wheel clean-install、真实 Chromium、TUI、Python full、Safety AST/grep 与文档 golden 均通过。实现 closure commit `c4da4f9`，fork Push run `29476327424`、PR run `29476329954` 均成功；evidence closure `33b062b`，fork Push run `29477199756`、PR run `29477202468` 均成功。旧 fence-only chat 只显示普通文本，Action Board、approve/reject mutation、pending/approval/SafetyGate 与 watch 唯一执行权保持不变；冻结项不自动恢复。

**R8.1 review hardening（已完成）**：只关闭阶段 review 发现的 LOG 多进程 mirror/安全收尾、in-progress Gate evidence 与 claim owner 关联、`ChatPlan.agent_output` 嵌套 OpenAPI 及证据账本缺口。实现提交为 `6d53db3`、`4c9c6a4` + `c38e3ec`、`89f84c8`，review follow-up 为 `241fe8d` terminal final owner、`fc282cf` newest raw owner Gate validation + real dependency path、`b2c93bb` denial-only fallback。早期定向/阶段证据保留：Task 1 focused `60 passed`、group `177 passed`、阶段 full `439 passed`，Task 2 combined `127 passed`，Task 3 focused `78 passed + 78 passed`。最终本地证据（2026-07-17）：Python full `462 passed, 1 warning`；TUI typecheck/test/build `61 passed`；frontend `tsc -b && vite build` （3309 modules）与真实 Chromium `27 passed`；clean-wheel base/server-extra smoke 通过；多进程 LOG + halt + Gate owner + OpenAPI + Safety AST + docs/golden/Moce 专项 `71 passed`；受影响 state/projection/API/MCP/watch/safety `152 passed`；`git diff --check`、tracked dist、退役 production markers 与受保护 snapshot diff 均 clean；独立终审经四轮 fix/re-review 后 Critical=0、Important=0、Minor=0。远端 closure 证据（2026-07-17）：implementation/local closure `8438cb7`；fork Push run `29553985591`、PR run `29553987358` 均 completed success，headSha 均为 `8438cb7bf5f356021cb602908552a069e8227bc4`。PR 保持 OPEN + draft。

## F0 LLM planner 实验

**思路**：三件事互相独立、并行推进。① 启用：项目 `physical-agent.yaml` 改 `agent.planner: llm`（代码默认值 rule_based 不动）；`agent.model` 保持 `fake/local` 即可——它是"此处未配置"的哨兵值，planner 会转而读 `workspace/.llm.json`（GUI 里配好的模型与 key）。② **本地调用留痕**：在 `openai_compatible` 的调用出口（chat/structured/stream 共用点）加薄封装，每次调用追加一行 JSONL 到 `workspace/llm-trace/`（gitignore）：ts / surface（复用 `metadata.physical_agent_surface`）/ model / messages / 响应 / usage / 延迟 / 错误。约 30 行，零新依赖；环境变量 `PA_LLM_TRACE=0` 可关。③ 实验：固定任务集写成脚本（越界坐标/不存在能力/中文/多步/模糊指令各≥3 条），逐条经 `/api/tasks/submit` 提交 + watch step，记录提案 JSON、gate 判定、feedback。
**坑**：trace 含 prompt 明文，留在 workspace 别提交；实验用 mock_arm 即可，别等仿真。Langfuse 已挂起（重启条件见 SPEC 挂起清单）——别在 F0 引入。
**验收**：llm-trace 里能对出三条调用路径的完整记录；产出 `docs/f0-report.zh-CN.md`（失败模式分类 + 对 F1/F3/F4 的排序建议）。

## B6 退役 markdown 后端（已完成，维护约束）

**完成状态**：`MarkdownStateStore`、当前 migrator/reader 与 full Workspace protocol 均已退役；active backend 只支持 SQLite。`workspace.backend: markdown` 和"省略 backend 但存在完整 legacy Markdown workspace"都必须 fail closed，不能静默打开旧后端或叠加 `state.db`。
**保留边界**：`SAFETY.md` 文件真源与 SQLite 的 `LOG.md` 人类可读镜像已经由聚焦 sidecar 承接；audit export 仍复制 SAFETY。它们是正式安全/可审计能力，不属于旧 workspace protocol。
**历史救援**：需要迁移旧 workspace 的用户只能使用 `9072b4e` 独立 worktree 的旧 package/CLI，手动切换 config 后回当前版本执行非 force init/state-check；当前 executable 不再提供迁移入口。
**维护检查**：新增状态字段时只改 SQLite 与审计导出；全仓 grep `LegacyMarkdownWorkspaceReader`、`MarkdownStateStore`、`physical_agent.protocol.workspace`、`workspace.backend: markdown`，确认 production/tests 为零，剩余引用只属于历史/救援说明。

## F1 提案卡片 + Approve + 审批流

**实现口径（2026-07-16 更新）**：① Draft 结构化（F1.1/R5-R7）：rule/LLM chat 主路径先形成 typed Chat Turn；proposal actions 只分配一次 draft IDs，经 trusted compiler 得到 draft `AgentOutput`。SSE done、`ChatPlan.agent_output`、assistant `metadata.agent_output` 是唯一机器通道；正文只按普通 Markdown 显示，任何 fence-like 文本都不能升级为 Draft。② 呈现分支（F1.2）：React/Web 显示可操作 Draft card；其中 `ChatPanel` 对照“任务原文 vs 提案动作”，展示 robot/capability/params/reason，**Add to Actions** 只调用既有 `proposeAction()` 创建 pending action，Edit 回填 `ProposalPanel`。TUI/CLI 只显示 structured draft，不提供从该 draft 直接 Add 的控制，也不为此新增功能。③ 提交例外：普通 rule/LLM chat 主路径不直接写动作板；显式 `tool_loop` 可调用 proposal-only tool 直接提交 pending，但仍绝不 approve 或 execute；既有 task/manual/run proposal 路径也可直接创建 pending。④ 审批流（F1.3）：不新增 runtime backend 状态机状态，approval 放在 action metadata；Actions 板的 **Approve execution / Reject** 才是执行审批。`approval.required` 由后端按 robot/capability 的 `requires_approval` 与 SAFETY 文件真源计算，不能信任 LLM、前端或 API caller；`claim_next_ready_action()` 在 SQLite 事务里跳过 `required && status != approved` 的 pending action，不阻塞后续 ready action。`POST /api/actions/{id}/approve|reject` 做幂等和非法终态保护，reject 写原因并转 cancelled。
**坑**：两个 Approve 语义必须分开：Chat draft 是"提交到动作板"，Actions 板是"放行执行"。审批≠免检，SafetyGate 只把 `requires_approval` 从"等待人"推进到"继续校验"，schema、bounds、capability、robot、SAFETY.md 仍照跑；approved action 后续被 Gate 拒绝时，保留 approval 记录并记录 safety rejected feedback/log。B6 后只维护 SQLite，不恢复 `MarkdownStateStore`、markdown backend 矩阵或 legacy runtime backend。
**F0 实验追加的两个子项**：① **planner 拒绝理由透出**——结构化输出加可选 `refusal_reason`，无提案时 GUI 展示"为什么没方案"，旧调用方缺字段仍兼容。② **Gate 直击组**——绕 planner 直接 propose 越界/幻觉动作，留下 LLM 时代 Gate 拦截审计样本，证明 planner 没产出时 Gate 仍能拦。
**验收**：chat 起草→Add to Actions→Actions 板 Approve execution→watch 执行→feedback 全程 GUI；非 `requires_approval` 不被审批流程阻塞；`requires_approval` 未 approved 不被 claim，approved 后仍经过 SafetyGate；队首未批准动作不阻塞后续 ready action；拒绝动作进 cancelled 并带原因；approval/source/refusal_reason 进入 LOG 镜像与 audit export；全量 pytest 与前端 build 通过。

**退役结果（R5/R7）**：R5 已用一轮双轨证明 structured output 与旧客户端 fallback；R7 随后停产并删除 fence、parser、provenance 与 React fallback。旧 fence-only chat 消息只保留为普通可读历史文本，不再恢复 Add/Edit；不实现新的兼容迁移层。已经写入 Action Board 的 pending/approved action 不受 chat 展示变化影响。

## F2 结构化信息可读化（全应用原则）

**原则**：只做"读"。已知协议字段（pydantic schema 锁定）写定制组件；未知/raw/driver 私有字段用 JSON 树兜底；全应用 `<pre>` 裸 JSON 逐步清零。**不引表单库**（rjsf/JSON Forms 已挂起，见 SPEC 挂起清单）——产品没有手写 JSON 的需求，数据来源是 SDK 文件和 yaml。
**首批落地**（改 `ContextTabs.tsx` 为主）：① feedback 时间线：antd Timeline/Table，`status` 红绿灯 Tag，**失败原因读 `message` 字段**（不是 detail），`action_id` 点击跳 Actions 页（复用 setActivePage），事件类条目（`event: driver_*`）用不同图标；② world：objects 转表格（id/type/location/pose），environment 用 Descriptions，summary 置顶；③ raw 兜底：使用 AntD 原生折叠/Tree 或 `JsonSummaryLine` 摘要，继续只服务 unknown/raw/private 字段，不把 JSON viewer 当产品组件。
**实现口径（2026-07-07 已落地，2026-07-08 收口）**：`ContextTabs` 拆出 world/feedback/safety/capabilities 四个可读 tab；`FeedbackTimeline` 合并 feedback history、action approval/source metadata 与 chat `refusal_reason`；`WorldObjectsTable` 展示 objects/environment/robots/artifacts，未知 object 字段折叠进 raw。首轮曾用 `react18-json-view` 做懒加载 raw tree；F2.5 后续已改为 AntD 原生 RawDebug，非 RawDebug 展示统一为 `JsonSummaryLine`，`ActionBoard`、`ChatPanel`、`ConfigPanel`、`SettingsPanel`、`RawDebug` 均不再用裸 `<pre>` 或第三方 JSON viewer 展示状态 JSON。
**实现经验**：status 颜色映射、pose/location/schema 摘要应集中在 formatter，避免各面板各写一套；JSON tree 只作为折叠兜底，首屏仍优先放人能直接读的 message、action、robot、capability、approval 与 world summary；Playwright mocked 场景比 live workspace 更适合锁 UI 可读性，live smoke 继续覆盖真实 API 拼接。
**后续批次**：integration 结果与 state-check 可继续补更细的诊断分组；audit 导出内容的 Dashboard 页内预览仍远期；2026-07-08 已先以 `docs/current-architecture-audit.html` 落一版 current architecture audit 静态展示；若 F6 SceneView 落地，world 表格可与图形视图联动但不替代 raw 兜底。
**验收**：mock 跑 demo 全程不点 Raw Debug 能看懂发生了什么；坏任务拒绝原因在时间线直接可读；全应用 `<pre>` 出现次数下降可统计。

## F3 context_builder 解耦

**思路**：新建 `agent/context_builder.py`：`build_context(store, message, *, purpose: Literal["reply","proposal","tool_loop"], budget: ContextBudget) -> ContextBundle`（含 system 文案与 payload）。`ContextBudget` dataclass 收拢：recent_messages=12、summary 阈值 24、memory_top_n=20、world_max_chars、每 note 截断长度、max_tokens。替换 `chat_runtime.py` 三处重复（约 500/800/945 行区域）与 `llm_planner.py` 一处。world 超预算时降级：objects 仅留 id/location/status，raw 丢弃；memory 按 `importance DESC, created_at DESC` 取 top-N（B4a 字段终于用上）。
**坑**：三处 system 文案有故意的措辞差异（reply vs proposal）——用 purpose 参数化，别硬统一；先写 golden-file 快照测试锁住现有 payload 再动手，重构后 diff 应只有预期变化。
**验收**：golden 测试通过；chat/planner/tool_loop 行为回归全绿；魔法数字 grep 不再散落。

## F4 期望-比对-回灌

**实现口径（2026-07-07 已落地）**：`Action.metadata.expected` 进入 chat draft、LLM planner、MCP proposal 与 API proposal 的可选 metadata；实际归一化和比对集中在 `physical_agent/protocol/expectations.py`，避免 API/state 顶层 import watch 或 driver。断言形如 `{"path": "world.objects[id=red_block].location", "op": "eq", "value": "tray"}`，op 支持 `eq/ne/in/range`，路径支持点号、数组索引和简单 selector。watch 仅在 SafetyGate 通过、driver 返回 completed、并且 `update_world()` 成功后运行 `evaluate_expected()`；动作失败或 world 刷新失败时，只要原 action 有 expected，就写 `skipped` 的 `expectation_check`。SafetyGate 拒绝仍只写安全失败，不跑 expected。
**状态聚合**：一条 action 可带多条 check；任一 check 为 `violated` 则总事件 `violated`，否则任一 check 为 `skipped` 则总事件 `skipped`，全部 `verified` 才是 `verified`。每条 check 保留自己的 `status/message/expected/actual/path/op`；总事件的 `message` 摘要第一条 violated/skipped，方便 F2 时间线直接读。`expected` 为空或缺失时不产生 `expectation_check`。
**归一化边界**：`expected` 是执行后诊断，不是 SafetyGate，也不是 action schema 本体；坏 expected 不能让原本合法的 action 提交失败。写入 action metadata 时只做轻量规范化：单个对象转 list；非 list/object、条目非 object、字段缺失、未知 op、路径不可解析等都保留为后续 `skipped`；条数限制为 20，序列化大小限制为 8 KiB，超限写入截断说明；actual 用稳定 JSON 排序，避免快照抖动。
**回灌与可见性**：`expectation_check` 进入 feedback history；context_builder 在后续 chat/planner 上下文注入 expectation feedback，让 LLM 看到期望、实测与 message，但不自动重试。前端不大改流程：Chat draft 卡片与 Actions 表格显示 expected 摘要，raw expected 作为折叠兜底，避免模型生成的“自证”完全隐形。
**验收**：pick/place 带正确断言产生 verified；错误断言产生 violated；坏路径/坏格式/动作失败产生 skipped；缺失 expected 不产事件；多 check 聚合规则固定；expected 在提交前或动作详情可见；全量 pytest 与前端 build 通过。

## VNext-1 AgentOutput + trusted PlanCompiler

**目标**：把 Agent 的公开心智模型从 `Action[]` 改为可信编译的任务 DAG：`raw model decision → PlanCompiler → AgentOutput`。模型只提交 action intent 与 advisory `SafetyIntent`；compiler 按后端事实为每个物理 Action 注入唯一 mandatory、watch-owned `SafetyGateTask`，按需注入 `ApprovalTask` 与 `VerificationTask`，并让 `PhysicalActionTask` 依赖 Gate。下游 Action 的 Gate 还必须依赖上游 `PhysicalActionTask`。

**边界**：`SafetyGateTask` 不是 Action、capability 或 LLM tool；caller/模型提供的 Gate task、`safety_gate=passed`、approval/provenance 都不可信。compiler 只描述义务，不预判 Gate outcome，也不 import watch/driver。approval 只决定是否等待人；F4 expected 只产生执行后 Verification。

**兼容策略**：首轮保留 Action board 作为执行队列真源，旧 `actions` response 字段保留；`AgentOutput.tasks` 先作为可信计划投影。Chat draft 可返回 `lifecycle=draft` 与 `not_scheduled` tasks，避免把“展示草稿”误写成已排队。在 task graph 未持久化或实现可验证重建前，不宣称拥有完整 task runtime。

**验收**：task/action id 唯一且 DAG 无环；每个 Action 恰有一个 Gate 和一个 PhysicalAction task；physical task 必须依赖 Gate；需要审批时 Gate 依赖 Approval；有 Action dependency 时下游 Gate 依赖上游 PhysicalAction；caller 无法删除/完成 Gate；API、MCP、AgentRuntime、Chat draft/tool loop 输出一致；全量 Python/React/TUI 回归通过。

**实现口径（2026-07-10 已落地）**：`protocol/agent_output.py` 与 trusted `application/plan_compiler.py` 实现协议、任务 ID、检查说明与图不变量；`SafetyIntent` 进入 action metadata、LLM schema 与 prompt，但只作为 advisory details。ProposalService、API task/manual proposal、MCP、AgentRuntime、Chat draft/tool loop 与 ChatPlan 已接线；定向测试覆盖 DAG、caller Gate 伪造/删除、draft lifecycle、refused/unavailable 和各入口 wire schema。

## VNext-2 Materialized AgentOutput + structured feedback + scheduler hardening

**目标**：watch 对 Gate pass/reject/error 都写独立结构化 feedback；application 以 compiled topology、Action Board 和 Gate/Verification feedback materialize 当前 AgentOutput。后续认知轮次和 React/TUI 消费同一 projection，能回答“正在等谁、Gate 是否执行、动作/验证走到哪里”，chat-only plan 不能隐藏 active physical obligations。

**关键修复**：① materializer 将 in-progress 映射 checking，Gate reject 将 PhysicalAction/Verification 映射 skipped，有 expected 时等待 expectation event；② SQLite claim 跳过等待 dependency、busy robot 与本 watch degraded/halted robot，不可能依赖显式 terminalize；③ capability override/watch default 形成 Gate/execute 共用的 effective timeout；④ feedback event 原子 append；⑤ watch step 用 `processed/gate_decisions/state_changed` 表达 Gate-only 变化；⑥ context-aware planner 读取 SAFETY、budgeted feedback 与 previous output，AgentRuntime 等 required verification。

**验收**：Gate pass/reject 均有结构化记录且 reject 永不调用 driver；active tasks 在 ChatPlan 被覆盖后仍可重建；verification 状态与 AgentRuntime 终态一致；同 robot 不重叠 claim，不同 robot 可分别 claim；heartbeat degraded 暂停新动作并在恢复后放行；waiting dependency 保持 pending，impossible dependency 级联终态；并发 feedback 不丢事件；反馈超限后仍保留近期 code/check 摘要；默认不自动重试。

**实现口径（2026-07-10 已落地）**：新增 `application/output_projection.py` 的 `materialize_agent_output/current_agent_output/project_chat_plan`；API/MCP/GUI/TUI 读取服务端 current projection。watch 为 pass/reject 写 checks/code/evidence/digest；SQLite 原子 feedback append、per-robot claim serialization、dependency cascade，heartbeat block/recovery 与 effective timeout 已接线。context_builder 增加 feedback event/char budget，contextual planner 收到 SAFETY/feedback/previous output；AgentRuntime 等 verification。定向测试覆盖上述状态映射、竞态与边界。

## VNext-3 Persistent obligation state + atomic transaction

**目标**：在兼容 projection 稳定后，决定并实现独立 task table 或同等可证明的持久化 obligation 模型；让持久化 task graph/obligation rows 与 actions 在一个事务中提交，并支持跨重启恢复、并发推进和完整 task history。

**当前边界**：`append_pending_actions()` 已让一个 proposal 的多条 actions 在 SQLite 单事务内全有或全无，ProposalService 已切换为 batch append；冲突会回滚整批。仍未实现的是独立 task rows 及其与 action batch 的同事务提交；AgentOutput graph 仍是派生/plan 数据。server-side action id 也仍在事务外按 snapshot 编号，并发冲突会整批失败而不是产生半批。Run/Turn/Event ledger 排在此后。

**验收**：保持当前 actions batch all-or-nothing；并发 proposal 的 id 在事务内分配或可安全重试；持久化 graph 与 actions 不产生半份或不一致；approval/Gate/action/verification 状态可恢复；迁移保持旧 actions response 和 Action Board 兼容；新表/API 不能绕过 watch Gate。

## W2 观察并发化 + 频率解耦

**落地**（2026-07-07，`4e0f732`）：`update_world()` 对不同 robot 的 observe 使用 `asyncio.gather(..., return_exceptions=True)` 并发执行，timeout/异常逐 robot log-only 隔离；成功观测按 `robot_id` 稳定 merge，失败时以前一份 world 为底覆盖成功结果，避免单 robot 故障清空全局 world。
**频率**：`WatchConfig.observe_interval_ms` 为可选正整数；未配置或模板为 `null` 时运行时使用 `tick_ms`。`step()` 维持单步入口的 idle refresh 直觉；`tick()`/`run_forever`/API watch 用 observe interval 控制 idle observe，action claim/execute 仍按 tick，动作后的 `update_world()` 不受分频限制，继续给 F4 expectation_check 提供新鲜 world。
**验收**：并发启动、稳定 merge、单 robot observe exception 隔离、observe interval 默认/校验/分频、F4 post-action expected 回归均有测试；全量 `pytest` 277 passed。

## W3 transport 断线重连

**落地口径（2026-07-07）**：`drivers/transport/base.py` 增加 `ReconnectPolicy` 与 `connected/disconnected/reconnecting` 状态语义，policy 默认关闭；`WebSocketTransport` / `SerialTransport` 在初始 connect 失败时按 `delay = min(cap, base * 2 ** attempt)` 退避重试，运行中读写发现断连时丢弃旧资源并启动后台重连。Loopback 扩展了连接失败次数、运行中断连和后台重连模拟，供单测使用。
**执行语义**：reconnecting/disconnected 期间 `write/read/request` 立即抛 `TransportReconnecting` / `TransportDisconnected` / `TransportReconnectFailed`，watch 把 action 标 failed 并写人可读 feedback；不排队命令、不自动 retry action、不重放旧 execute。执行中 peer close/OSError 视为 execution state unknown，以现有 failed/cancelled 语义收口。
**driver hook**：`PhysicalDriver.on_transport_reconnected()` 默认 no-op；transport 可通过 `on_reconnected` 回调通知 owner driver。`xiaozhi_mcp` 在 WebSocket 重连成功后标记待刷新，下一次 health/observe/execute 前重新 initialize 与 tools/list（fire-and-forget 模式刷新工具映射）。
**边界**：W3 不改 SafetyGate、F1 approval、F4 expected 语义；不做 W4 多机器人并行 execute，也不扩 `observed_at` schema。reconnect success 只说明通信恢复，不代表机器人状态安全，后续仍以 observe/health 的世界事实为准。
**验收**：Loopback 覆盖 connect retry、max retries exhausted、reconnecting fail-fast、hook；WebSocket 本地 fake server 覆盖 server 主动断开后重连并再次 read/write；Serial fake 覆盖 open retry 与 OSError 断连；watch 覆盖 fail-fast feedback、执行中断连 unknown failed、reconnect exhausted feedback。全量 `pytest` 294 passed。

## W4 多机器人并行执行 + observed_at

**当前边界（2026-07-10）**：SQLite claim transaction 禁止同 robot 同时存在两条 in-progress action，并允许不同 robot 被分别领取；workspace `watch-executor` lease 同时只允许一个 WatchRuntime owner。单个 WatchRuntime 仍未用 `gather` 并行 execute，也没有 `observed_at/revision/stale`，因此 W4 仍未完成。
**思路**：step() 领取后按 robot 分组，不同 robot 的动作 `asyncio.gather` 并行执行（同 robot 内保持串行）；`Observation` schema 加 `observed_at: datetime`（driver 基类默认填 now，driver 可覆盖）。
**坑**：并行后 feedback 写入是共享 store；`append_feedback_event()` 已能防 lost update，但跨 robot 事件顺序仍不确定，测试断言不能依赖顺序。workspace lease 已防第二 WatchRuntime 同时工作；若目标包含崩溃接管或分区容错，仍须完成 W6.2 hardware fencing，不能把数据库 lease 当作设备 epoch。
**验收**：双机器人各一动作时一次 step 双执行；world 里能看到各机器人观察时间。

## W5 driver 编写守则

**思路**：三处落笔：`drivers/templates.py` 生成的 driver 模板注释里加"阻塞调用须带超时或 `asyncio.to_thread`"；`agent/driver_coder.py` 的 LLM 生成 prompt 加同样规则；`hardware-bringup-checklist.zh-CN.md` 加检查项。
**验收**：`integrate` 生成的新 scaffold 里能看到该注释；driver_coder 生成的代码不出现裸阻塞 I/O（抽查）。

## W6 Workspace watch lease 与 hardware fencing

**W6.1 实现口径（2026-07-10 已落地）**：SQLite `runtime_leases` 提供 named `watch-executor` lease；Watch 在 driver connect 前获取，每次 setup 生成 unique owner，并按最长 operation budget 设置/续租 TTL。第二 WatchRuntime 在 active lease 下 setup fail closed。claim 使用同一 owner，completed/cancelled 写入以 `in_progress + claim_owner` CAS；旧 owner 的迟到结果失败并触发 fatal watch error。lease 丢失后 API watch loop 停止，stale shutdown 只 disconnect 自身 transport、不发送 halt。workspace reset 用 exclusive transaction 检查 active lease，HTTP reset 返回冲突。测试覆盖 acquire/renew/release/expiry、双 runtime、stale completion、fatal stop 与 reset guard。

**W6.1 边界**：这是 workspace/SQLite-level singleton executor 和 stale-result fencing。它能阻止后续受 lease 检查的软件步骤，不能撤销已经发出的 driver call；失去数据库连接、网络分区或阻塞中的 transport 仍可能留下 in-flight physical effect。

**W6.2 未完成**：将 epoch/fencing token 下沉到 driver/transport/设备或独占硬件代理，让控制面拒绝旧 owner I/O；定义 owner 崩溃、存储不可达、命令在途、接管前 fresh observe/fail-safe halt 的语义。验收要求旧 owner 即使仍存活、迟到 I/O 也不能影响继任者，接管绝不重放旧 action。

## F5.1 LeRobot motors（触发：舵机臂到手）

**思路**：`feetech-servo-sdk` 进 `[servo]` extra；新 driver `feetech_arm`——初始化 FeetechMotorsBus（端口/波特率/舵机 id 表进 config_schema），observe 轮询 Present_Position/Load/Temperature/Voltage，execute 的 move_to 走 sync write 目标位置，halt 写 Torque_Enable=0。参考 LeRobot `src/lerobot/motors/feetech/`。
**坑**：所有总线读写是阻塞串口——全部 `to_thread`（W5）；先做标定流程（限位/零位存 config）再谈动作。

## F5.2 ros_mcp driver（触发：有 ROS 设备）

**思路**：仿 `xiaozhi_mcp.py` 结构；经 rosbridge websocket 订阅指定 topic 集合→observe 组装，execute 映射到 service/action 调用；topic/service 白名单写进 config_schema。**不采用让 LLM 直连 ros-mcp-server 的用法**——一切过 gate。

## F5.3 感知补语义（触发：小车+摄像头）

**思路**：做成 observe-only driver（无 execute 能力）：抓帧→检测模型（ultralytics 或小 VLM）→物体列表进 `Observation.objects`，原始帧路径进 artifacts。模型推理进程外跑或 to_thread。

## F6.0 场景规格设计（F6.1 前置，纯设计轮）

**思路**：每个 demo 一份场景规格文档（建议 `docs/scenarios/<name>.zh-CN.md` + 对应 yaml）：①能力词汇表（capability 名/params_schema/constraints/requires_approval）；②初始对象表（id/type/pose/状态字段）；③SAFETY 边界（bounds 与场地对齐）；④演示任务集（正例 + 必须被拦的反例，即 F0 坏任务的场景版）。**arm**：直接继承 mock_arm 的四能力和 schema，只需补对象状态字段（末端位置/持有物）；**car**：从零设计——`move_to(x,y)`/`stop`/`dock`/`patrol(zone)`，场地 bounds、障碍与充电桩对象、电量字段。
**验收**：两份规格评审通过后 F6.1 才动代码——规格即 driver 的验收标准。

## F6.1 Hero Demo Twin：机械臂（公司产品）+ 通用 SceneView

**产品定位**（2026-07-05 修订）：机械臂是公司产品，hero 归它；小车降为第二示例（F6.1b，使用指南性质）。**统一技术路线：渲染只做一个通用 SceneView 面板**——canvas 顶视图读 `world.objects`，按对象 `type` 映射图标（末端/方块/托盘/车/障碍/dock），新增 demo = 新 driver + 新图标 + 场景 yaml，面板零改动。任务级演示 2D 顶视图足够（demo 讲的是命令→审批→执行→断言闭环，不是运动学）。观众零安装、浏览器五分钟闭环、可随 demo 站部署。
**思路**：① `sim_arm` driver（纯 Python）：继承 mock_arm 能力 schema，加运动插值（末端 pose 随自身时钟连续变化而非瞬移，SceneView 上看得到"在动"）与持有物状态；② 通用 `SceneViewPanel`：懒加载 canvas，SSE 驱动，图标注册表按 type 扩展；③ F6.1b `sim_car` driver 随后复用面板：pose(x,y,θ)/速度/电量，运动学积分在 driver 自身时钟内做，halt=速度清零，碰撞判定在 driver（撞上→failed+人话 message，喂 F2 时间线与 F4 断言）。
**坑**：对象 pose 的坐标系约定要写进 F6.0 规格并与 SAFETY bounds 对齐，让"越界被 Gate 拦"在画面上可解释；插值状态是 driver 内部的，observe 只报快照——别把渲染帧率需求压到 watch tick 上。
**验收**：arm——`pick the red block and place it on the tray` 在 SceneView 上连续可见，断言 verified；car——"go to charging dock" 车开过去、"drive to x 999" 被拦画面不动；新增第三个 demo 不改面板代码。

## F6.2 remote_sim driver + BYO Simulator 协议

**定位**：Physical Agent 不内置仿真引擎，提供"把你自己的仿真器接成一台虚拟硬件"的协议。行业先例：VDA5050（AGV 主控↔车辆的 JSON 标准，MQTT 承载）证明这类"命令/状态协议"是成熟模式；我们不用 MQTT（省 broker），用**已有的 WebSocketTransport + JSON**。
**思路**：新 driver `remote_sim`（config：endpoint/token/capability 超时）。协议消息**镜像现有 driver 契约**：连接握手时对端必须先发 `capabilities` 声明（含 params_schema/constraints）——**没有它 Gate 无从校验，直接拒连**（这是对外部方案最重要的修正：只给 observe/execute/health/halt 四件套不够）。随后 `{op: observe|execute|health|halt, ...}` 请求-响应，负载对齐 Observation/ActionResult 的 pydantic schema。W1 超时全覆盖。**参考适配器**：一个独立 Python 脚本把 CoppeliaSim 的 ZMQ API 包成本协议 ws 服务——一石二鸟：验证协议可用性 + 提供机械臂 3D 体验（本地开发用）。
**明确不做**：通用建模器、拍照生成场景、统一物理语义、"仿真通过=真实安全"的等价承诺。
**验收**：用参考适配器接 CoppeliaSim 跑通 pick/place；断掉适配器时 watch 按 W1 超时降级不挂死。

## F6.3 conformance 测试套件

**思路**：CLI `physical-agent sim-verify <endpoint>`——按序验证：握手带 capabilities → observe 返回合法 Observation → execute（observe 能力）语义正确 → 故意超时场景 → halt 立即生效。复用 `test_driver_contract` 的断言逻辑。通过才算合格 BYO endpoint。

## F6.4 远期路标

真臂 URDF 数字孪生（浏览器 urdf-loader/Three.js 生态成熟，可网页端渲染，与 F5.1 会师）；预演 Gate（难点仍是"用当前 world 快照初始化仿真场景"的状态同步）。MuJoCo 无头评测 harness 降级为远期候选（设计见 git 历史）。

## T 系列：Ink 终端 UI（独立线，与 F 主线无依赖）

**定位**：第五个入口——交互式终端工作台（SSH/无 GUI 场景 + 开发者日常），与 typer CLI 分工：typer 管脚本化/自动化命令，Ink 管交互。**纯 API 客户端，零核心改动**，复用 FastAPI 全部端点与 SSE。
**思路**：新目录 `tui/`（Node 20+ / TypeScript / Ink 5 + React 18）。依赖：`ink`、`ink-text-input`、`ink-spinner`、SSE 用原生 fetch 流式解析（复用 dashboard `api.ts` 的 parseSseBlock 逻辑翻译成 Node 版）。三档递进：**T1** 只读——StatusBar（health/backend/watch）+ chat 流式对话 + actions 列表实时刷（SSE）；**T2** 交互——提交 task、approve/reject（依赖 F1.3 端点）、workspace reset；**T3** 补齐——config/robots 视图、上传。入口 `npm start -- --api http://127.0.0.1:8766`。
**坑**：Ink 是 Node 生态——引入了第二运行时依赖，若在意可改用 Python 的 Textual（同语言零新增依赖），**决策记录：选 Ink 是因为技能与 dashboard 的 React 复用 + Claude Code 同款生态**；SSE 断线要做和 dashboard 一样的降级轮询；终端宽度自适应用 Ink 的 flexbox，别写死列宽。
**验收**：T1 三面板可用、chat 流式不卡顿；`ink-testing-library` 覆盖核心组件渲染。
**实现口径（2026-07-07）**：已落 `tui/` 独立包，包含 API client、SSE parser、command parser 与 StatusBar/ChatPanel/ActionsPanel/CommandInput。TUI 只调用 HTTP API/SSE，不读 SQLite/workspace，不 import Python/watch/driver。T2-lite 已含 chat、`/task`、`/approve`、`/reject`、`/reset true`、`/refresh`、`/help`、`/quit`；`/execute`、`/driver`、`/hardware-control` 明确拒绝。T3 的 config/robots/uploads 已在 2026-07-08 完成，具体契约见下一段。
**实现口径（2026-07-08 T3）**：补 view/page 概念，默认仍是 chat transcript + actions 的纵向终端体验；`/view status|chat|actions|robots|config|uploads` 可切单主视图，StatusBar 与 CommandInput 常驻。`/config` 复用 `GET /api/config` 展示 workspace/watch/agent/robots 摘要并过滤 `api_key`/secret/token；`/robots`、`/robot <id>`、`/capabilities <id>` 合并 config、world、capabilities 展示 driver/mode/endpoint/health、requires_approval、params_schema 与 constraints 摘要。`/upload <path>` 与 `/ingest <path>` 只用本地文件构造 multipart `POST /api/upload` 请求，沿用 dashboard 的文本后缀与 5MB 限制，前置拒绝目录、过大、明显二进制或非 UTF-8 文件；上传内容不直接注入 LLM，视图只显示 filename/size/sha/id/untrusted/chunks 元数据。`/register-robot <json>` 仅调用既有 `POST /api/config/robots`，不做 YAML 编辑器、不直接写 `physical-agent.yaml`。Windows Terminal / PowerShell 下推荐用 `cd tui; npm start -- --api http://127.0.0.1:8766` 启动；带空格路径用引号传给 `/upload`。
**验证**：2026-07-07：`cd tui && npm run build` 通过；`cd tui && npm test` 13 passed。2026-07-08 T3：`cd tui && npm test` 44 passed；`cd tui && npm run build` 通过；TUI 安全 grep 覆盖无 `driver.execute`、无 `physical_agent.watch`/`physical_agent.drivers` import、无 SQLite 直接访问。2026-07-08 command acceptance：新增 `tui/tests/scenarios/{basic,chat,actions,config,robots,upload,error}.scenario` 与 `tests/scenario-runner.test.tsx`，按真实 Ink 输入驱动 `App`，mock API/SSE 响应并断言终端输出、API 调用次数和 state/config 变化；覆盖 `/help`、`/view *`、`/task`、`/approve`、`/reject`、`/reset`、`/config`、`/robots`、`/robot`、`/capabilities`、`/upload`、`/refresh`、`/quit` 及 API offline、SSE error/EOF、polling fallback、缺参、非法命令、上传失败、reset confirmation failure；矩阵见 `docs/tui-command-matrix.md`。

### T4 MOCE TUI 品牌与终端视觉刷新

**重启依据**：2026-07-17 用户在真实 Windows Terminal 体验后，以截图明确指出现有 TUI 缺少视觉层级，并批准“启动大 Logo + 常驻紧凑标题栏”的 MOCE 暗蓝方案。这是 R8.1 后的独立显式 SPEC 决策，只重启 TUI 展示层。

**思路**：保持纵向 append-only transcript 与纯 HTTP API/SSE 边界；新增集中 theme token、一次性 `BrandBanner`、紧凑 MOCE `StatusBar`、统一 `SectionTitle`、角色轨道和 round-border `CommandInput`。宽终端使用暗蓝 `#1D4ED8` 块字 Logo，小字号品牌元素使用更亮的 `#3B82F6`；低于 58 列或宽度未知时用 compact fallback。finalized assistant 文本只做 heading/list/bold/inline-code 的轻量呈现，streaming partial 保持纯文本，避免未闭合 token 闪烁；不引入完整 Markdown 依赖。

**关键文件**：`tui/src/App.tsx`、`components/{BrandBanner,StatusBar,SectionTitle,Transcript,CommandInput}.tsx`、各 view panel、`tui/src/theme.ts`、`components/render.test.tsx`、`tests/scenario-runner.test.tsx`。详细设计见 `docs/superpowers/specs/2026-07-17-tui-moce-visual-refresh-design.md`。

**坑**：Ink 只保留一个持续挂载的 Static feed，Logo 作为首个稳定 item 与 finalized transcript 共用该 feed，不能因 health/SSE rerender 或 view 切换重复打印；Ink stdout columns 在非 TTY 可缺失，必须 fallback；暗蓝不能用于黑底小字或成为唯一状态表达；现有 scenario 固定 100 列且剥离 ANSI，需要补 48/100/未定义列宽行为断言；formatter 对 fenced code、未配对/嵌套标记与旧 `action-draft` 必须原样保真；外部 PowerShell `WindowTitle` 红字属于启动命令转义问题，不要把 shell 管理塞进 TUI。测试 stdin 被读取、React 接收输入与 stdout 物理写入是三个边界：先等待测试 stdin 的真实消费，再发送 Enter，结果继续等待 Enter 后命令专属完成标记。Ink v5 在 `isInCi && debug:false` 时只即时写 Static、动态 frame 延迟到 unmount；物理 stdout 契约的 harness 模拟 `isTTY=true`，因此测试 runner 只对子测试进程设 `CI=false` 以选择 Ink 非 CI 动态渲染分支，不能把 GitHub 的非交互输出策略误当该 harness 的目标路径。

**验收**：先 RED 后 GREEN；覆盖宽/窄/未知列宽 Banner、单一 Static feed 且只打印一次、48 列完整 App 无固定超宽行、紧凑标题栏、角色轨道、轻量 finalized Markdown 正反例、输入框与既有命令不变；完整 `npm run typecheck && npm test && npm run build`、scenario matrix 与 TUI 安全扫描全绿；真实 Windows Terminal 确认暗蓝 Logo 与小字强调色可读、无折行/重复 Logo，并用文档化命令手工确认无外部启动红字。API、watch、driver、SafetyGate、Action Board 与审批语义零改动。

**实现口径（2026-07-17 T4）**：新增集中式 MOCE theme token，启动 Banner 在有限且不少于 58 列时显示暗蓝 `#1D4ED8` 块字，窄屏、未知或非有限宽度统一使用 compact 标识，小字强调使用可读性更高的 `#3B82F6`。Banner 与 finalized transcript 共用唯一持久 `Static` feed；Logo 是首个稳定 item，health/SSE、`/view` 与 `/refresh` 重绘不会再次物理打印。角色轨道统一为 `you ›`、`moce │`、`draft ◇`，StatusBar、SectionTitle 与 round-border CommandInput 共用视觉层级。只有 finalized assistant 文本进入 heading/list/bold/inline-code 轻量格式化；streaming、其他角色、fence/link/table、嵌套或畸形标记整条保真降级，不引入 Markdown runtime dependency。TUI 继续只经 HTTP API/SSE，不新增命令、状态写入或硬件控制路径。

**验证（2026-07-18 最终本地门禁）**：`npm.cmd run typecheck`、render `30 passed`、scenario `16 passed`、API-only safety `1 passed`、`npm.cmd test` `84 passed`、`npm.cmd run build` 全绿；100/48/未知列宽与 `debug: false`、`rows=10000` 的 raw stdout 验证 full/compact Logo 均只物理打印一次，命令验收按 post-Enter 的 `View: status`、`View: chat`、`Snapshot refreshed.` 语义标记有界同步。Python safety `2 passed`，full `463 passed, 1 warning`；`git diff --check` clean；独立 spec/quality 终审 Critical=0、Important=0、Minor=0。首次 exact-head `038c1c6` 的 Push run `29629559330`、PR run `29629560483` 均于 Enter 前失败，`a8deeac` 改为等待测试 stdin 的真实消费；第二次 exact-head `7d380f9` 的 Push run `29630023334`、PR run `29630024721` 均推进到 Enter 后失败，确认根因是 Ink v5 的 `isInCi && debug:false` 非交互输出策略，而不是产品命令未完成。两轮 Push 中 safety、frontend+wheel 成功且条件型 Python full/Playwright skipped；两轮 PR 中 Python full/safety、frontend+wheel 与真实 Chromium Playwright 成功。`647ce53` 只在 `npm test` spawned child 中设 `CI=false`，不改变 typecheck/build 或产品 runtime；`CI=true npm.cmd test` 已完成 82/84 RED → 84/84 GREEN，typecheck/build 全绿，独立代码复核 Critical=0、Important=0、Minor=1（未来若新增 CI 专属行为，须用独立保留 `CI=true` 的子进程覆盖）。最终远端 closure：implementation/docs head `9c50067` 的 Push run `29630361521`、PR run `29630363135` 均 completed success，headSha 均为 `9c50067964e5ea184803e83526121388078862f9`；PR 中 Python 3.12 full/safety、Ink TUI、frontend+wheel 与真实 Chromium Playwright 全部成功。phase-B evidence-only 提交只回写这组既有成功证据。Windows 启动使用子进程内 `$Host.UI.RawUI.WindowTitle` 与 `npm.cmd`，不再把成员赋值误当外部 PowerShell 命令。

**T4.1 follow-up（2026-07-19）**：`Static` auto-width 曾让正文预算没有扣除角色轨道、间隔与 padding，原始 48 列 RED 因而产出 49-cell 物理行；`f81b134` 让 finalized/streaming 共用可收缩的 `MessageRow`，用户 `>` 使用 success green、MOCE `⏺` 使用 brand blue，draft 保留 warning `draft ◇`。`216a0b9`、`8139d24`、`c2f8c7c` 只从 canonical Action Board 把本 TUI 会话中新 terminal transition 以自有不可变 snapshot 追加到同一 append-only feed，并让单项 clone failure 不丢弃同批有效项；cancelled 在匹配 action-result 到达前不固化，历史终态、draft、Gate/expectation feedback 与重复 snapshot 不冒充 terminal action。`e0215cb` 完成 App 集成及响应式 pending approval 只读提示，仅展示既有 `/approve`、`/reject` 命令并明确批准后仍过 watch SafetyGate；FastAPI、SQLite、action/feedback wire、watch、driver、SafetyGate、SAFETY.md、parser/审批、时间戳和冻结状态均未修改，也未新增 y/n/a 或 session grant。

**验证（2026-07-20 T4.1 最终门禁）**：controller 在 `e0215cb` fresh gate 中得到 TUI typecheck exit 0、full `108/108`、build exit 0、activity/render/scenario 专项 `70/70`；Python safety `27/27`，full `463 passed` 且仅 1 条已知 Starlette `TestClient` deprecation warning；`git diff --check` 与禁止 TUI driver/watch/sqlite import 扫描均 clean。逐任务终审和整体验收均为 Critical=0、Important=0、Minor=0，整体结论 Ready to merge=Yes。implementation/docs exact head `357a4898fc19704179e15c1614f49e49f794263f` 的 Push run `29695566978`、draft-PR run `29695568726` 均于 attempt 1 completed success：Push 的 Ink TUI、frontend+wheel、Python safety 成功且 PR-only jobs skipped；PR 的 Ink TUI、frontend+wheel、Python 3.12 full、Python safety 与真实 Chromium Playwright 成功，generic matrix job skipped。

**T4.2 block Markdown renderer（2026-07-20，已完成）**：真实终端截图证明 LLM 常见的缩进嵌套列表会触发当前 `FinalizedText` whole-message fallback，使同一回复内本来合法的 heading、bold 和 inline code 也全部暴露原始标记。采用无新依赖的 block scanner + 受控 inline parser：heading、paragraph、最多三层 mixed list 与普通闭合 fenced code 分块渲染，不支持或畸形结构只让所在 block literal；list/code 使用独立 prefix 列和可收缩正文列保持 display-width 悬挂缩进。streaming/user/draft/unknown role 保持 literal，`action-draft` fence 连标记逐字保留且绝不升级为 Draft。详细设计见 `docs/superpowers/specs/2026-07-20-tui-block-markdown-renderer-design.md`。

**T4.2 关键文件与坑**：主改 `tui/src/components/FinalizedText.tsx`、render/physical-width/scenario tests；必要时新增只服务 block 的 hanging-row primitive，不复制角色 `MessageRow`。scanner 先以 list-like grammar 把带空格或 tab 的连续 marker 行收成 candidate run，再用严格 ASCII-space item grammar 整体验证；indentation stack 的任意增量只推进一级（`0 → 8` 合法），第四个 distinct depth 或未知 dedent 才整块 literal。顶层 fence 的 opener/closer、ASCII language token、`action-draft` casefold 与 consume-to-closer/EOF 范围以设计文档的精确 grammar 为准；普通 fence 只是 presentation，不能读取 metadata、Action Board 或调用 proposal/parser。Paragraph grouping 只限定 fallback domain，源换行仍逐行保留。

**T4.2 验收**：截图等价回复不再显示合法 `##`/`**`/inline-code 标记；24/48/100 列下 nested list/code 物理行不超宽且续行对齐正文；unsupported block 不拖累相邻合法 block；streaming、user、draft、`action-draft` 与畸形输入仍逐字；TUI typecheck/定向/full/build、禁止 import 扫描、Python safety/full、diff check 与独立 review 全绿，随后记录 exact-head Push/PR CI。API、SQLite、watch、driver、SafetyGate、SAFETY.md、审批与其他冻结项零改动。

**T4.2 实现与本地验收（2026-07-20）**：`3b17ec6` 增加无依赖 block scanner，`7c0a239` 接入 finalized assistant renderer，`25f20c4` 完成 `HangingRow`、App/scenario 与 24/48/100 列物理输出；broad review 后以 `499487c` 修复最小表格 delimiter、空 fence、竖向 code rail、Unicode/两位有序项覆盖，以 `8d578be` 收紧 literal table 邻接，以 `fe0b477` 保留 active table 中的 pipe-bearing list-like row。两轮最终 spec/quality re-review 各自均为 Critical=0、Important=0、Minor=0。controller fresh gate：TUI typecheck/build exit 0，parser+renderer `53/53`、scenario `24/24`、full `127/127`；Python safety `27/27`、full `463 passed, 1 warning`，唯一警告为已知 Starlette `TestClient`/`httpx` deprecation；禁止 TUI driver/watch/sqlite import 扫描无匹配，package dependency diff、`git diff --check` 均 clean。live smoke 前只读确认唯一 driver 为 `mock_arm`、SQLite `pending/in_progress=0`、API `ready=True` 且 unsafe action=0；Windows 应用自动化安全规则禁止控制 Terminal，故未冒充已观察到 LLM 长回复，权威验收仍由 deterministic scenario 与 physical-width tests 提供。

**T4.2 历史门禁偏离（不作 closure 证据）**：Task 3 执行者在独立 review 前提前 push 了 `25f20c48eb8bd9ac4d40aa9bcce120ae42acf7a0`；其 Push run `29723405783` 与 draft-PR run `29723407703` 虽均为 attempt 1 completed success，但该 head 随后被三笔 review repair supersede，因此不得复用或概括为 T4.2 完成证据。SPEC 保持 🟡，直到 reviewed implementation/docs exact head 的 Push 与 draft-PR workflows 都成功。

**T4.2 历史 exact-head CI（2026-07-20，当时有效、现已 supersede）**：implementation/docs head `d72e187d340a2517d0dd005830977dd1b2babb0c` 的 Push run `29725427128` 与 draft-PR run `29725429981` 均为 attempt 1 completed success，且 `headSha` 精确匹配；evidence-only head `a89be0658a05f03ae20a9e2b707f6966363a2131` 的 Push run `29725619311` 与 draft-PR run `29725622285` 也均 attempt 1 completed success。它们证明当时 reviewed tree 的交付，但 final whole-branch review 后新增 `f1ed6c7`，所以这两代 run 不再是新 final head 的 closure 证据；早推 `25f20c4` 的两次 run 仍保持更早的门禁偏离身份。

**T4.2 final-review repair 本地重开（2026-07-20）**：`f1ed6c773cebac930fd11578b6ef653e259cf6fa` 修复 matching shortcut/image shortcut reference：scanner 先在整个文档收集 0–3 个 ASCII leading spaces 的单行 definition label，trim 并折叠内部 ASCII space/tab、casefold 后匹配；收集时复用 `parseFence()` 跳过普通、reserved、invalid 与 unclosed fence range，避免把 code presentation 当文档结构。匹配 shortcut/image shortcut 与 definition block 都走既有 block-local literal fallback，完整保留 `!`、`[]`、`**`，不解析或渲染 destination；unmatched bracket prose 与相邻 supported block 仍格式化。严格 RED/GREEN 与 exact-commit 报告得到 parser+renderer `60/60`、full TUI `134/134`、typecheck/build exit 0、Python full `463 passed, 1 warning`；closure controller fresh docs+safety `24/24`、targeted safety `27/27`，boundary/package/diff clean。最终 re-review Critical=0、Important=0、Minor=1；唯一 Minor 是计划已允许、且因 Terminal 自动化禁令继续接受的非阻塞 live smoke omission。标题“已完成”表示能力与 final repair 已实现；本地证据提交阶段 SPEC 曾保持 🟡，直到下述新 exact-head workflows 成功。

**T4.2 final-review repair exact-head CI（2026-07-20）**：implementation/docs head `6631f35b22eba6c6e57394c07fec3a26254aa686` 的 Push run `29728361574` 与 draft-PR run `29728365131` 均 attempt 1 completed success，`head_sha` 精确匹配。Push 的 frontend+wheel job `88306648770`、Python safety `88306648802`、Ink TUI `88306648860` 成功，generic matrix `88306649425`、PR-only Python full `88306649629`、Playwright `88306674380` skipped；draft-PR 的 Python safety `88306659766`、frontend+wheel `88306659770`、Python 3.12 full `88306659816`、Ink TUI `88306659823`、Playwright `88306659927` 成功，generic matrix `88306660569` skipped。只有这一代包含 `f1ed6c7` 与 living-doc repair 的 reviewed exact head 支持 final repair closure。

## C4 i18n / E3 视觉打磨

**思路**：C4：antd `ConfigProvider locale` + 文案抽到 `locales/{zh,en}.ts` 键值表（不上 i18next，工程量不值），默认跟浏览器语言，切换存 localStorage。E3：暗色模式用 antd `theme.darkAlgorithm` token 切换 + localStorage；首次引导用 antd Tour 组件串 setup→watch→demo 三步。
**实现口径（2026-07-07）**：新增 `frontend/src/locales/`，`App.tsx` 统一接 `ConfigProvider locale`、`MessagesProvider`、theme mode 与 Tour 状态。高频导航、StatusBar、Actions、Chat、Settings、Hardware、Config、RawDebug、Robots 等文案已抽取；Settings 提供语言、主题与重新显示 Tour。暗色模式使用 AntD `darkAlgorithm` + `body[data-theme]` CSS 变量，覆盖页面背景、侧栏、卡片、JSON fallback、chat draft、drawer 等明显浅色区域。
**验证（2026-07-07）**：`cd frontend && npm run build` 通过；Playwright 覆盖语言切换写 localStorage、dark mode 写 localStorage/body 状态、首次 Tour 关闭与 Settings 重开。

## E0-e2e 补课

**思路**：`frontend/e2e/dashboard.spec.ts` 追加：hardware 页生成 scaffold（用临时 SDK 目录 fixture）→注册表单提交→ConfigPanel 出现新 robot；Settings danger zone 确认流；每个新 testid 都已埋好（`register-robot-*`、`reset-workspace-*`、`config-panel`）。
**实现口径（2026-07-07）**：在现有 dashboard e2e 中补 mocked API 场景，固定默认测试态为 English/light/Tour dismissed，避免新 Tour 遮挡旧流程。新增覆盖：reset confirm 错误请求不执行 + GUI Popconfirm 成功 reset、Hardware scaffold→Register to config→ConfigPanel 出现新 robot、i18n、dark mode、Tour 首次打开/关闭/重开。
**验证（2026-07-07）**：`frontend/playwright.config.ts` 默认使用 `.tmp/e2e/physical-agent.yaml` 临时 workspace，避免覆盖根目录本地配置；`cd frontend && npx playwright test` 18 passed。

## 基建：CI

**思路**：`.github/workflows/ci.yml` 三 job：① pytest（matrix 3.11/3.12，`pip install -e .[dev,server,llm]`，**env 里清空代理变量**）；② 前端 `npm ci && tsc -b && vite build`；③ e2e smoke（Playwright chromium，只跑 overview 用例）。触发 push+PR。
**坑**：测试内建 env-scrub fixture（`tests/conftest.py` 里 monkeypatch 删代理变量）比在 CI yaml 里清更治本——两处都做。
**实现口径（2026-07-07）**：新增 `.github/workflows/ci.yml`，包含 Python 3.11/3.12 pytest、frontend `npm ci` + build、TUI `npm ci` + build/test、Playwright Chromium e2e。`frontend/playwright.config.ts` 的 webServer 命令改为 Windows/Linux 分支，先初始化 `.tmp/e2e` 临时 workspace，再启动 API，并允许 `PA_E2E_API_COMMAND` / `PA_E2E_DEV_COMMAND` 覆盖。
**实现口径（2026-07-08）**：按“宽松但守底线”调整 CI：默认阻塞项只保留 Python safety smoke 与 frontend build；TUI 和 dashboard e2e 改为 `continue-on-error` advisory；Python 3.11/3.12 全量 pytest 矩阵改为 `workflow_dispatch` + `full=true` 手动触发；CI 策略、失败处理与本地复现写入 `docs/CI.zh-CN.md`。
