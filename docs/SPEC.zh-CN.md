# SPEC：优化目标与追溯矩阵（活文档）

> 本文合并了原 optimization-spec（安全不变量）、plan-f（当前目标）与 traceability-matrix（账本），原件已删除、git 历史可查。历史过程见 `REFACTORING.zh-CN.md`。
> **维护规则**：每轮 session 收尾更新 §4 矩阵一行 → commit → push；里程碑拆分时拆行记录；状态以验收测试通过为准。
> 最后更新：2026-07-17

## 0. 安全边界（三层：宪法 / 授权策略 / 工程纪律）

### 0.1 宪法（仅两条；修改=修宪，需单独决策记录说明动机与放弃了什么）

1. **执行权唯一**：`driver.execute` 只允许出现在 watch 执行循环的调用栈里。一切提案/请求侧代码路径（HTTP 处理器、LLM 调用链、CLI 命令、MCP 工具）不得加载 driver、不得调用执行。约束对象是**代码路径**而非模块或进程——API 进程里跑 watch 后台服务不违宪，请求处理器直接执行才违宪（`test_safety_boundaries` 强制）。
2. **执行前校验不可绕过**：任何作用于物理世界的动作，执行前必须过执行侧校验（SafetyGate）；SAFETY 规则以文件为真源，提案侧无法修改。

**预注册例外**（用到时显式设计即可，不算破例）：急停/halt 类"去激活"指令可有提案侧直达通道——宪法管"让机器人动"，不管"让它停"；高频流式控制（遥操作/VLA 技能）按**会话粒度**过闸——gate 审"开启会话"，帧流走专用通道，急停与边界包络兜底。

### 0.2 授权策略（用户可配，决定人参与到什么程度）

人类参与度按能力分级：每次询问（ask）/ 一次放行（standing grant）/ 白名单全自动（auto）。**授权改变的是"要不要停下来等人"，永远不改变"要不要校验"**。当前载体：`requires_approval` + F1.3 审批流；档位 3 闭环是 auto 档的延伸，仍在管线内。

### 0.3 工程纪律（会演化，改动记入 REFACTORING 即可）

- 新能力默认关闭或向后兼容；每步小步可回滚。
- 校验清单内容随功能演化（当前 10 项非冻结数字），删减需谨慎评估。
- **每轮开工流程（对人和 agent 同等生效）**：读本节 → §4 找到条目 → 读 `PLAYBOOK.zh-CN.md` 同名条目 → 出轮次 brief → 实现+测试 → 更新 §4 与 REFACTORING。agent 执行者的完整守则见仓库根目录 `AGENTS.md`。

## 1. 系统与产品框架

```
用户 Chat → rule/LLM action intents → normalize + stable ID/dependency → trusted PlanCompiler → structured AgentOutput / ChatPlan.agent_output → API/SSE/assistant metadata → structured draft
  ├─ React/Web 可操作 Draft card → 用户 Add to Actions → pending action
  └─ TUI/CLI 结构化展示（无直接 Add 控制）
显式 tool_loop → proposal-only tool → pending action
task/manual/run proposal 路径 → pending action
pending action → approval（如需要）→ Watch SafetyGate → driver.execute → canonical feedback/read model
运行态投影：SQLite Action Board + structured feedback → output_projection → materialized current AgentOutput → 下一认知轮次
```

rule/LLM chat 主路径只产出 structured draft。React/Web 显示可操作 Draft card，并可由用户通过 Add to Actions 创建 pending action；TUI/CLI 只显示 structured draft，不提供从该 draft 直接 Add 的控制。显式 `tool_loop` 是例外：它可调用 proposal-only tool 直接提交 pending，但仍绝不 approve 或 execute；既有 task/manual/run proposal 路径也可直接创建 pending。

三入口 = 同一提案管线的自主档位：**档位0** 手动表单（jog）· **档位1** Chat 起草→人批 · **档位2** Task 一次规划 · **档位3** 闭环自主（未建）。
分工恒定：LLM 只起草 action intent 与 advisory `SafetyIntent`；可信 application 层为每个物理 Action 注入唯一、mandatory、watch-owned `SafetyGateTask`；人类只完成审批义务；watch 最终校验并执行；F4 expected 只做执行后诊断。`SafetyGateTask` 不是 Action/tool，模型不能创建、删除、完成或绕过。

## 2. 当前目标（R0-R8.1 已收口；T4 TUI 视觉刷新；Phase F 其余功能扩张冻结）

| 编号 | 内容 | 要点 |
| --- | --- | --- |
| **R0-R8.1** | 架构减法、兼容面退役与 review hardening（已完成主线） | 已完成 GUI parity→legacy GUI 退役→Markdown migration/完整 Workspace 退役→`auto_step` 退役→structured Chat 双轨→read-model/response 去重→全量与 review hardening 收口；历史证据见 §4 与 `REFACTORING.zh-CN.md` |
| **T4** | MOCE TUI 品牌与终端视觉层级 | 用户于 2026-07-17 在真实 Windows Terminal 体验后明确重启此展示条目；只改 Ink TUI 品牌、布局、finalized text 呈现与宽度兼容，不改 API、watch、driver、SafetyGate、命令或状态语义；设计见 `docs/superpowers/specs/2026-07-17-tui-moce-visual-refresh-design.md` |
| F0 | LLM planner 实验（后续暂停） | 已有实验与本地 JSONL trace 保留；R0-R8 期间不扩样本、不引观测平台、不据此新增 runtime 能力，收口后再按真实失败数据评审 |
| **B6（已完成历史收口项）** | 状态层收口 | 已删 `MarkdownStateStore`/factory 分支/config legacy backend 自动选择/矩阵测试 md 侧与 `test_e2e_markdown_loop`，但保留旧目录检测以 fail closed；当时承诺 `migrate-md-to-sqlite`/reader 保留一个版本周期。R0 已决定在 R3 提前退役该入口：先抽 SAFETY/LOG sidecar，再删 full Workspace，并用 `9072b4e` 独立 worktree 留历史救援路径；这不改变 SQLite-only runtime 的既有事实 |
| F1 | 提案卡片 + Add to Actions + 审批流（已完成） | chat draft 只从 compiler 生成的 draft `AgentOutput.actions` 创建；reply 永远是用户可读文本，不再承载或解析 `action-draft` 机器协议。旧 fence-only chat 升级后仍可阅读，但不会恢复为可操作 Draft；已经进入 Action Board 的 pending/approved action 不受影响。Chat 卡片的 Add to Actions 只创建 pending action，不等同执行审批。`requires_approval` 由后端按 robot/capability 计算；Actions 板的 Approve execution / Reject 才改变执行放行状态。watch claim 会原子跳过未批准动作但不阻塞后续 ready action；SafetyGate 仍照常校验 schema、bounds、capability、robot、SAFETY.md。 |
| F2 | 结构化信息可读化（全应用原则） | **通用原则：已知协议字段一律定制组件呈现，未知/raw 字段 JSON 树兜底（懒加载），`<pre>` 裸 JSON 逐步清零**。首批落地：feedback 时间线（status 灯/action 跳转/失败原因用 `message` 字段）、world objects 表格、capabilities/config/integration 结果的卡片化；协议 schema 由 pydantic 锁定，定制组件不会白写 |
| F3 | context_builder 解耦（已完成） | `context_builder` 统一 reply/proposal/planner/tool_loop 上下文；ContextBudget 收拢魔法数字；world/capabilities 超限摘要化；memory 按 importance 排序注入；golden-file 测试 |
| F4 | 闭环地基（已完成） | 提案带 expected 断言 → 执行后**确定性比对**（不用 LLM 当裁判）→ 写入 `expectation_check` feedback；violated/skipped 回灌 LLM 上下文，自动重试默认关 |
| VNext | Assurance-first Agent runtime（已落地部分保留，后续扩张暂停） | 已完成 compiled topology/current projection、verification/dependency/timeout 调度、atomic feedback、proposal actions batch 单事务，以及 workspace singleton watch lease + unique claim-owner CAS/reset guard。R0-R8 期间不新增独立 task table、持久化 task graph、Run/Turn/Event 或 registry/read-model；先删除重复兼容面，不把 current projection 表述成持久化 obligation engine |
| F5 | 硬件生态（条件触发，当前冻结） | R0-R8 期间即使设备条件满足也先不扩实现；收口后再按实机需求重启。原候选：F5.1 LeRobot motors、F5.2 ros_mcp、F5.3 感知语义层 |
| **T（独立线：Ink 终端 UI）** | 第五入口 | Node/TS/Ink 5 交互式终端工作台（`tui/` 目录，纯 API 客户端零核心改动）；T1 只读（状态+流式 chat+actions 实时）→ T2 交互（提交/审批/重置，审批依赖 F1.3）→ T3 补齐。typer CLI 保留管脚本化，Ink 管交互；选 Ink 而非 Textual 是为复用 dashboard 的 React 技能。与 F 主线无依赖（除 T2 审批），可随时穿插 |
| F6 | Demo Twin + BYO Simulator（冻结） | F6.0-F6.4 全部暂停；R0-R8 不以 demo、SceneView、remote_sim 或 conformance 为由扩大协议面。收口后若重启，仍需先做场景规格且不做通用仿真平台 |

**R0-R8 功能冻结（2026-07-10，R8.1 延续）**：VNext-3/4、W4/W5/W6.2、F0 后续实验、F5、F6、B4-vec、registry/read-model 新能力、自动 replan/无人值守档均暂停。R8.1 不解冻 VNext-3/4、W4/W5/W6.2、F0/F5/F6、B4-vec、registry/read-model 或自动 replan；只有出现可复现的真实需求并形成显式 SPEC 决策后，才可重启对应条目。

**其他挂起（明确不做）**：Langfuse 观测平台（2026-07-05 评估：F0 量级几十次调用，本地 JSONL 留痕足够；重启条件=F4 闭环自动调用量增大或 F6.2 批量评测需要打分 UI，届时优先 Cloud 免费档）、instructor / LiteLLM（等 F0 数据）、chat markdown **深度**渲染扩展（基础渲染已由用户以 react-markdown 落地于 ChatPanel；代码高亮/一键复制等扩展不排期）、通用 yaml 编辑器（lite 版已够）、schema 驱动表单库 rjsf/JSON Forms（2026-07-05 评估：产品无手写 JSON 需求——若将来出现高频结构化输入场景再评估，届时选 rjsf + @rjsf/antd）、**通用仿真平台**（2026-07-05 产品决定：只做 demo twin 与 BYO 接口，若 F6 解冻仍遵守）。

## 3. 已完成里程碑（速查）

P0/P1/D0/P1.5 安全边界+工具循环 · A3 上下文压缩 · B1-B3.8 状态存储全套（SQLite 默认/原子动作/lease/审计）· B4a-c 记忆摄入检索地基 · C1-C3.2 FastAPI+SSE+React 仪表盘 · D1-D3.1 传输层+心跳看门狗 · D4 实机文档 · A1.0-A1.6a 官方 SDK/流式/abort/设置/深思考 · B5 后端口径收口 · E0.1-E0.3 GUI 对齐（重置/硬件面板/配置注册）· W1 驱动调用超时保护 · B6 退役 MarkdownStateStore 后端 · F1 提案卡片与 action 级审批流 · F2 结构化信息可读化 · F3 context_builder 解耦/feedback budget · F4 expected 确定性比对与 AgentRuntime verification 等待 · W2 观察并发化与 observe 分频 · W3 transport 断线重连 · VNext-0 ProposalService/typed metadata/执行边界/execution_mode 地基 · VNext-1 AgentOutput/PlanCompiler 安全义务图 · VNext-2 materialized output/structured feedback/调度硬化 · VNext-2b atomic action batch · W6.1 workspace watch lease/claim-owner fencing。
逐项提交号与决策见 `REFACTORING.zh-CN.md` §1-§2。测试状态以本轮 CI/提交记录为准，不在此手工维护易过期的用例总数。

## 4. 待办矩阵（backlog，活账本）

> **每项的实现思路、关键文件、坑与验收见 `PLAYBOOK.zh-CN.md` 同名条目**；动工前按惯例出轮次 brief。
> 归属列图例：`§2` = 本文件第 2 节"当前目标"的对应行（不是外部文档）；其余为来源备注（W1 遗留 = REFACTORING §2 W1 小节；PLAYBOOK 同名条目 = 只在 PLAYBOOK 有详情）。

| 编号 | 内容 | 归属 | 状态 |
| --- | --- | --- | --- |
| **R0-R8** | 架构减法与兼容面退役 | `specs/001-architecture-simplification/` | ✅ 2026-07-16 完成：实现 closure commit `c4da4f9`，fork Push run `29476327424`、PR run `29476329954` 均成功；evidence closure `33b062b`，fork Push run `29477199756`、PR run `29477202468` 均成功。R8 已收口 current docs、Moce SQLite 示例、`ChatPlan.actions` 重复投影、typed OpenAPI、chat-side `executed=0` 残留及发布包；`AgentOutput`/`ChatPlan.agent_output` 是唯一 Draft 机器通道，`/api/state.actions` 仍是 board truth，approve/reject mutation `action`、pending/approval/SafetyGate 与 watch 唯一执行权保持。冻结项不自动恢复，仍按 §2 的重启条件重新评审 |
| **R8.1** | R-stage review hardening：LOG 多进程/安全收尾、Gate claim correlation、嵌套 OpenAPI 与证据闭环 | `specs/001-architecture-simplification/r8-1-review-hardening-plan.md` | ✅ 2026-07-17 完成：实现提交 `6d53db3`、`4c9c6a4` + `c38e3ec`、`89f84c8`，review follow-up `241fe8d`、`fc282cf`、`b2c93bb`；最终树本地门禁与独立终审已完成。最终本地证据（2026-07-17）：Python full `462 passed, 1 warning`；TUI typecheck/test/build `61 passed`；frontend `tsc -b && vite build` （3309 modules）与真实 Chromium `27 passed`；clean-wheel base/server-extra smoke 通过；多进程 LOG + halt + Gate owner + OpenAPI + Safety AST + docs/golden/Moce 专项 `71 passed`；受影响 state/projection/API/MCP/watch/safety `152 passed`；`git diff --check`、tracked dist、退役 production markers 与受保护 snapshot diff 均 clean；独立终审经四轮 fix/re-review 后 Critical=0、Important=0、Minor=0。远端 closure 证据（2026-07-17）：implementation/local closure `8438cb7`；fork Push run `29553985591`、PR run `29553987358` 均 completed success，headSha 均为 `8438cb7bf5f356021cb602908552a069e8227bc4`。PR 保持 OPEN + draft。R8.1 不解冻 VNext-3/4、W4/W5/W6.2、F0/F5/F6、B4-vec、registry/read-model 或自动 replan；只有出现可复现的真实需求并形成显式 SPEC 决策后，才可重启对应条目。 |
| F0 | LLM planner + 本地调用留痕 + 坏任务实验报告 | §2 | ⏸ R0-R8 冻结；既有第一轮 15 条结果保留：10 完成、5 无提案、0 Gate 拦截。**Review 复核（2026-07-06）**：trace 证实 bounds 在 prompt 内、拒绝为知情拒绝；不在本轮继续扩实验或功能 |
| B6 | 退役 Markdown runtime/migration（保留 SAFETY/LOG sidecar 与 fail-closed） | §2 | ✅ active backend 只剩 SQLite；R3 已删除当前 migrator、reader 与 full Workspace。当前版本不再提供迁移命令，只保留 SAFETY/LOG sidecar、legacy workspace fail-closed 检测和独立历史 checkout `9072b4e` 救援路径 |
| F1 | 提案卡片 + Add to Actions + 审批流 | §2 | ✅ 2026-07-07 完成：Chat draft 卡片只提交动作板；Actions 板审批才放行 `requires_approval`；approval required 后端计算，SQLite 原子 claim 跳过未批准动作；拒绝/审批元数据进 LOG/audit |
| F2 | feedback 时间线 + world 视图 + JSON 树 | §2 | ✅ 2026-07-07 完成：feedback/action approval/refusal_reason 时间线可读，world objects 表格化，capabilities/config/integration 轻量可读；raw JSON 改懒加载树兜底。提交 `58a75b0`。2026-07-08 补 `docs/current-architecture-audit.html` 静态审计阅读页，展示 `docs/current-architecture-audit.md` 内容 |
| F2.5 | State Overview 产品化收口 | §2/F2 后续收口 | ✅ 2026-07-08 完成：新增 `frontend/src/viewmodels/` formatter 层；Overview 首屏用 AntD Card/Statistic/Table/Descriptions/Tag/List 展示 system/robots/capabilities/environment/world objects；`RawDebug` 仅折叠展示 unknown/raw/backend private 字段。follow-up：非 RawDebug 的 params/schema/raw 展示统一为 Overview capability 风格的轻量摘要；RawDebug 也改为 AntD Collapse/Tree，移除 `react18-json-view` 依赖与 `json-view` chunk |
| F3 | context_builder 解耦 | §2 | ✅ 2026-07-07 完成 `9cbb540`：统一 chat reply/proposal/tool_loop 与 planner payload；2026-07-10 contextual planner path 补 SAFETY、feedback、previous AgentOutput，feedback 按事件数/字符预算裁剪并保留近期结构化摘要 |
| F4 | 期望-比对-回灌 | §2 | ✅ 2026-07-07 完成 expected 确定性比对；2026-07-10 materializer 将 verification 映射为 checking/passed/failed/skipped，Gate reject 时跳过 PhysicalAction/Verification，AgentRuntime 等 required `expectation_check` 后才判完整完成 |
| VNext-0 | Proposal application layer + typed metadata + execution boundary + execution_mode | §2/VNext | ✅ 2026-07-10 本轮完成：主要 task/action 入口复用 `ProposalService` 与统一 planner factory；metadata 增加 v1 typed view/correlation 且不能伪造审批；Chat 的旧自动推进参数曾降为兼容 no-op，并已在 R4 完整删除；driver coding 改静态校验；robot 显式区分 simulation/hardware，默认 hardware，hardware 按默认 SAFETY 策略要求审批。**尚不包含统一 Agent loop** |
| VNext-1 | AgentOutput + trusted PlanCompiler + assurance task DAG | `agent-architecture-vnext.zh-CN.md` | ✅ 2026-07-10 本轮完成：每个 Action 编译出唯一 mandatory、watch-owned Gate；Approval?/PhysicalAction/Verification? 形成无环依赖；advisory SafetyIntent 进入 schema/prompt；ProposalService、API、MCP、AgentRuntime、Chat draft/tool loop 与 ChatPlan 已接线，定向测试覆盖图不变量与伪造防护 |
| VNext-2 | materialized AgentOutput + structured feedback + scheduler hardening | `agent-architecture-vnext.zh-CN.md` | ✅ 2026-07-10 本轮完成：`output_projection` 合成当前状态并重建 active tasks；feedback 原子追加；dependency、heartbeat、effective timeout、per-robot claim 已硬化；AgentRuntime 等 verification；Web/TUI 展示 current projection。**这仍不是持久化 obligation engine** |
| VNext-2b | atomic proposal actions batch | `agent-architecture-vnext.zh-CN.md` | ✅ 2026-07-10 完成：StateStore 增加 `append_pending_actions()`，SQLite 用一个事务归一化并插入整个 batch；ProposalService 只调用 batch API；任一冲突回滚全部 actions，测试覆盖 all-or-nothing |
| VNext-3 | persistent task/obligation state + persisted graph/action transaction | `agent-architecture-vnext.zh-CN.md` | ⏸ R0-R8 冻结：当前 Action Board/feedback 继续作为运行事实，output projection 继续作为 current read model；只有收口后出现明确跨重启 terminal task 恢复需求才重启评审 |
| VNext-4 | Run/Turn/Event ledger + typed stream + registry/read model | `agent-architecture-vnext.zh-CN.md` | ⏸ R0-R8 冻结：避免在兼容字段与 read model 尚未去重时增加第二套账本/registry；不自动恢复 |
| W2 | 观察并发化（gather）+ 频率与 tick 解耦 | W1 欠账 | ✅ 2026-07-07 完成 `4e0f732`：`update_world()` 按 robot 并发 observe、按 `robot_id` 稳定 merge；`observe_interval_ms` 未配置时等价 `tick_ms`；长跑 watch/API watch 中 claim 仍按 tick，idle observe 分频，动作后 world refresh 仍立即服务 F4 expectation_check |
| W3 | transport 断线重连（backoff） | W1 欠账 | ✅ 2026-07-07 完成 `1d9a812`, `7762c0f`：`ReconnectPolicy` 默认关闭；Loopback/WebSocket/Serial 支持 connect retry 与运行中断连后台 backoff；reconnecting/disconnected execute fail-fast、不排队、不重放旧动作；driver 预留 reconnect hook，xiaozhi_mcp 重连后刷新 handshake/tool cache；关闭/取消中的迟到 open 会清理资源且不触发 hook；未做 W4 并行 execute/observed_at |
| W4 | world freshness + 多机器人并行执行 | W1 欠账 | ⏸ R0-R8 冻结：per-robot claim guard 只防同 robot overlap，**不代表 W4 完成**；本轮不加 freshness schema 或跨 robot 并行 execute |
| W5 | driver 编写守则：阻塞调用须带超时或走 to_thread（写进 driver 模板与生成规则） | 讨论产出 | ⏸ R0-R8 冻结；现有安全回归仍必须守住 timeout/to_thread 纪律 |
| W6.1 | workspace watch runtime lease + unique executor/claim-owner CAS | VNext 执行协调风险 | ✅ 2026-07-10 完成：active `watch-executor` lease 阻止第二 runtime；关键阶段续租，失租 fatal stop；action terminal mutation 校验 unique claim_owner；stale shutdown 不 halt；active lease 阻止 workspace reset |
| W6.2 | driver/transport/hardware-level fencing token | VNext 执行协调风险 | ⏸ R0-R8 冻结：数据库 lease 不能撤销 in-flight command 的风险说明保持；只有明确实机 HA/接管需求才重启 |
| F5.1-F5.3 | LeRobot motors / ros_mcp / 感知语义层 | §2 | ⏸ R0-R8 冻结；之后仍需设备条件触发 |
| F6.0 | 场景规格设计（arm 继承 mock_arm；car 能力词汇表从零定） | §2 | ⏸ R0-R8 冻结 |
| F6.1 | Hero Demo Twin：机械臂（公司产品）+ 通用 SceneView 面板 | §2 | ⏸ R0-R8 冻结 |
| F6.1b | 智能小车第二示例（使用指南） | §2 | ⏸ R0-R8 冻结 |
| F6.2 | remote_sim driver + BYO Simulator 协议（含 capabilities 发现；CoppeliaSim 参考适配器） | §2 | ⏸ R0-R8 冻结 |
| F6.3 | BYO conformance 测试套件（`sim-verify`） | §2 | ⏸ R0-R8 冻结 |
| F6.4 | 真臂 URDF 数字孪生 + 预演 Gate | §2 | ⏸ R0-R8 冻结/远期 |
| MuJoCo-harness | 无头批量评测（原 F6.2，降级为远期候选） | git 历史可查设计 | ⏸ |
| T1 | Ink 终端 UI 只读三面板（状态/chat/actions） | T 独立线 | ✅ 2026-07-07 完成：`tui/` 独立 Node/TS/Ink 包，状态/chat/actions 三面板，SSE 优先 + polling/degraded fallback，纯 HTTP API/SSE 客户端；2026-07-08 review fix：SSE clean EOF 降级轮询、真实 watch enabled/disabled/unknown 状态；2026-07-08 chat/actions 持久化修复：`/api/events` summary 不再覆盖完整 state，而是触发完整 `/api/state` 刷新；2026-07-08 LLM 状态显示：启动/`/refresh` 检查 LLM settings/test，显示模型、key 是否配置与短失败原因；2026-07-08 Windows/npm 启动参数兼容裸 API URL（`npm start -- http://127.0.0.1:8766`） |
| T2/T3 | Ink 交互（审批依赖 F1.3）与补齐 | T 独立线 | ✅ 2026-07-07 T2-lite 完成：chat、`/task`、`/approve`、`/reject`、`/reset true`、`/refresh`、`/help`、`/quit`；2026-07-08 review fix：chat stream 异常/AbortError 均清理 streaming/busy 状态；2026-07-08 交互改为更接近 Claude Code 的纵向 transcript；2026-07-08 取消单条 chat 220 字符硬截断并保留换行；2026-07-08 chat 历史改为 Ink `Static` append-only 输出，空闲 `watch_step` 不再触发 live 刷新；2026-07-08 T3 完成 config/robots/uploads 视图、`/view`/`/config`/`/robots`/`/robot`/`/capabilities`/`/upload`/`/ingest`/`/register-robot` 命令、API-only multipart 上传与 TUI 安全 grep；2026-07-08 command acceptance 收口：新增 `tui/tests/scenarios/*.scenario` 与 runner，覆盖全部用户命令、API offline、SSE error/EOF、polling fallback、缺参、非法命令、上传失败、reset confirmation failure，并生成 `docs/tui-command-matrix.md`；`cd tui && npm test` 场景纳入默认测试，`npm run build` 通过 |
| T4 | MOCE TUI 品牌与终端视觉刷新 | `PLAYBOOK` T4 + `superpowers/specs/2026-07-17-tui-moce-visual-refresh-design.md` | 🟡 2026-07-17：用户以真实终端截图明确要求重启，已批准“启动大 Logo + 常驻紧凑标题栏”的克制品牌化方案；书面设计已写入，等待规格复核与实现计划。范围只含 TUI 展示与对应测试，不改变 API/watch/driver/SafetyGate 或解冻其他功能 |
| C4 | 前端 zh/EN i18n | PLAYBOOK 同名条目 | ✅ 2026-07-07 完成：轻量字典 + AntD locale + Settings 切换 + localStorage；高频导航/状态/Actions/Chat/Settings/Hardware/Config 文案已抽取 |
| E3 | 暗色模式 + 首次引导 | PLAYBOOK 同名条目 | ✅ 2026-07-07 完成：AntD `darkAlgorithm` + CSS 变量暗色适配 + localStorage；首次 3 步 Tour 与 Settings 重开入口 |
| E0-e2e | Hardware/注册/DangerZone/ConfigPanel 的 Playwright 用例 | PLAYBOOK 同名条目 | ✅ 2026-07-07 完成：补 Danger Zone reset、Hardware scaffold→register→ConfigPanel、i18n、dark mode、Tour；dashboard e2e 18 passed |
| B4-vec | 真实向量 RAG（sqlite-vec + embedding） | 延后项；原设计见 git 历史 optimization-spec §4 | ⏸ |
| 基建 | CI（pytest 3.11/3.12 + 前端 build）；push 纪律；测试 env-scrub fixture | 流程欠账 | ✅ 当前 push 阻塞 Python safety smoke、frontend build/wheel 与 TUI；PR 额外阻塞 Python 3.12 full pytest 和真实 Chromium Playwright。Python 3.11/3.12 全量矩阵仍由 `workflow_dispatch full=true` 手动运行；细节以 `docs/CI.zh-CN.md` 为准 |

## 5. 验证环境备注

沙盒验证需：Python≥3.11（或 datetime.UTC shim）、清除代理环境变量、Linux 版 esbuild/rollup 原生二进制（与 lock 版本一致）。用户本机（Win + Py3.12）无需处理。唯一预期失败：doctor 在 Py3.10 沙盒正确拒绝版本。
