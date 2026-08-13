# Physical Agent 当前架构：安全义务主链与历史决策

日期：2026-07-16

范围：本文只描述当前代码、已执行的设计决策与明确冻结的候选范围。安全宪法以 `SPEC.zh-CN.md` §0 为准；用户保留的 `current-architecture-audit.md/.html` 与 `system-summary.zh-CN.md` 是阶段快照，不属于本文的 current-doc contract，也不在 R8 修改或重新生成。

## 文档身份与同步边界

本文件由两类内容组成，同步规则不同。修改任何一节前先确认它属于哪一类。

**living contract —— §0、§1、§2、§3、§4、§5、§7、§10，以及 §9 的 VNext-1 / 2 / 3B1 子节**

描述当前代码的契约与行为，随代码同步，**以代码为准**。发现本文与代码不符时，改本文，不改代码。这几节是硬化轮次实际会碰到的部分，复核触发规则见 `AGENTS.md`「收工时」。

**frozen registry —— §6、§8，以及 §9 的 VNext-3A / 3B2 / 4 / 5 / 6 子节**

记录刻意未建之物、其重启条件与当时的决策依据，**不随代码演进**。代码不朝这些方向移动，因此它们不会因代码变更而过时；常规文档同步不得调整这些部分。

§9 是混合节：其 VNext-1、VNext-2、VNext-3B1 子节的行为描述属 living contract，其余五个子节属 frozen registry。各子节标题下另有标注。

本文件同时被 `SPEC.zh-CN.md` §4 引用为冻结项的权威出处（VNext-1、VNext-2、VNext-2b、VNext-3、VNext-4 各行的归属列）。因此 frozen registry 部分的任何修改都需经解冻流程——即 SPEC §4 明确解除冻结并完成对应评审——不得在常规同步中调整。

## 0. 结论：当前唯一架构主链

**主链图与 rule/LLM chat 主路径的分支说明以 `SPEC.zh-CN.md` §1「系统与产品框架」为准**，本节不再复述。原先此处的链路图与说明段与 SPEC §1 重复（说明段逐字相同，链路图是 SPEC 版本的严格子集），已于 2026-08-13 删除以消除两处维护。SPEC §1 另有本节从未覆盖的内容：运行态投影链路（`SQLite Action Board + structured feedback → output_projection → materialized current AgentOutput → 下一认知轮次`）、三入口自主档位（档位 0-3）与分工恒定条款。

本节保留的是 SPEC §1 未表述的部分：

这条链的其余当前约束是：reply 只承载用户可读文本，不生产或解析 `action-draft` 机器协议；可操作 Draft 只来自 compiler-owned `AgentOutput`。Add 只创建 pending action，不等同于 approve 或 execute。审批只决定是否等待人，SafetyGate 仍在执行边界逐次校验 `SAFETY.md`；只有 watch 调用 `driver.execute()`。SQLite Action Board/feedback 是运行事实，`application.output_projection` 生成 current `AgentOutput`，React Dashboard 是唯一 GUI。

`AgentOutput + PlanCompiler + task DAG`、结构化 Gate feedback、materialized current projection、proposal action batch 原子提交和 workspace singleton watch lease 均已落地。独立 task engine、Run/Turn/Event、registry/read-model 扩张、world freshness、W4/W6.2 与 F6 均未实现且继续冻结；这些只是历史候选，不是默认开发路线，R8 后也不会自动恢复。

## 1. 不可改变的信任边界

- LLM、Chat、API、CLI、MCP 和 GUI 都属于提案侧，只能产生不可信决策或 action intent。
- `PlanCompiler` 属于可信 application 层。它根据后端事实补齐安全义务，不能接受 caller 自带的 Gate 任务作为权威输入。
- 每个物理 Action 必须且只能对应一个 mandatory、watch-owned `SafetyGateTask`。
- `SafetyGateTask` 不是 Action，不进入 driver capability，也不是可被模型调用的 tool。
- 模型可以提供 advisory `SafetyIntent`，例如 hazards、assumptions、requested evidence、mitigations；它不能创建、删除、标记完成或绕过 `SafetyGateTask`。
- 审批只解决“是否等待人”。即使 `ApprovalTask` 已完成，`SafetyGateTask` 仍必须执行。
- `metadata.expected` / F4 只解决执行后的意图验证。`VerificationTask` 不能替代执行前 SafetyGate。
- `SAFETY.md` 继续是安全规则文件真源；认知侧、AgentOutput caller 和 API metadata 都不能修改其裁决语义。
- 只有 watch 执行链可以调用 `driver.execute()`；模拟器也走同一 Gate/watch 管线。
- reconnect 不重放旧动作；执行状态未知时按失败或未知收口。

## 2. 当前代码状态与真实缺口

### 2.1 已经具备的地基

本轮此前已经完成：

- `ProposalService` 收拢主要 task/action 提案入口；
- planner 构造集中到 `planner_factory.py`；
- action metadata 有版本化 typed view、可信 provenance 和后端审批归一化；
- `ChatRuntime` 不再加载或推进 watch；
- driver coding 只做静态校验，不在认知侧调用候选 driver；
- robot 以显式 `execution_mode: simulation | hardware` 表达实例运行模式，默认 `hardware`；
- watch 仍是唯一的 SafetyGate 与执行所有者。

这些修改收敛了入口和执行边界，但 `ProposalService` 仍不等于 Agent runtime。

### 2.2 本轮已落地的 assurance-first 闭环

本轮已经完成并通过定向测试：

- `protocol/agent_output.py` 定义 `AgentOutput`、`AgentTask`、安全检查说明和任务图不变量；
- `protocol/actions.py` 增加 advisory `SafetyIntent`，LLM schema 与 prompt 明确其非权威性质；
- trusted `PlanCompiler` 为每个 Action 编译唯一 mandatory、watch-owned `SafetyGateTask`，并组合可选 Approval、PhysicalAction 与 Verification 依赖；
- `ProposalService`、API、MCP、`AgentRuntime`、rule/LLM Chat draft 与显式 tool_loop submitted turn 均已接入 compiled `AgentOutput`；前者保持 `lifecycle=draft`，后者只经 proposal-only tools 形成 pending；
- `application/output_projection.py` 以 compiled topology 为骨架，将 Action Board、Gate feedback 与 expectation feedback materialize 成当前 `AgentOutput`；即使普通 chat 覆盖 singleton `ChatPlan`，active actions 也能重建当前义务；
- materializer 将 `in_progress` 映射为 `checking`，Gate reject 会把 PhysicalAction/Verification 投影为 `skipped`，动作完成后有 expected 时保持 verification `checking`，直到 `expectation_check` 给出 verified/violated/skipped；
- `AgentRuntime` 等待 required verification 后才把 output 判为 completed，不再把“driver 已完成”误作“任务验证已完成”；
- watch 对 SafetyGate pass/reject 均写入带 checks、稳定 code 与 digest 的结构化 feedback，SQLite `append_feedback_event` 在事务中原子追加，避免并发 writer 丢事件；
- SQLite claim 已改为跳过 dependency 未完成、robot 已有 in-progress action 或本 watch 标记为 degraded/halted 的 action；Gate 仍保留 defense-in-depth 检查；
- impossible/已取消 dependency 会级联 terminalize 下游 pending action，并写 Gate/action feedback；有 expected 时再写 verification skipped，不再永久悬挂；
- Gate 与 driver 现在使用同一 effective timeout：capability override 优先，否则使用 watch default；SafetyGate 会对这个实际执行预算应用 `max_action_timeout_s`；
- watch step/API 以 `processed/gate_decisions/state_changed` 暴露“发生 Gate 裁决但未执行 driver”的状态变化，TUI 会据此刷新；
- React 与 TUI 已展示 materialized 任务图，并用结构化 feedback 覆盖 Gate task 的最近状态；
- context-aware planner path 会读取 SAFETY、结构化 feedback 与 previous AgentOutput；feedback 受事件数/字符预算约束，超限时保留近期结构化摘要，避免上下文无界增长。
- `append_pending_actions()` 已让一个 proposal 的多条 actions 在 SQLite 单事务内全有或全无；ProposalService 不再逐条 append；
- workspace 增加唯一 `watch-executor` runtime lease：每次 setup 生成唯一 owner，领取 action 时写入同一 `claim_owner`，完成/取消使用 owner CAS；失租是 fatal stop，活跃 lease 会阻止 workspace reset。

这完成的是**可重建、可 materialize 的兼容式 assurance loop**，不是完整 task runtime：Action Board 与原子 feedback 是运行事实，compiled graph 提供 topology，materializer 组合当前视图；actions batch 已原子，但尚无独立 task table、持久化 task graph 与 actions 的同一事务或 Run/Turn/Event ledger。workspace lease 提供软件执行者唯一性，但尚无 driver/hardware 能校验的 fencing token。

### 2.3 历史链路为何需要收敛

R0 前的真实主链曾是：

```text
planner -> Action[] -> pending action board -> approval? -> watch claim
        -> SafetyGate -> execute -> feedback -> expected check
```

它在执行安全上是保守的，但公开心智模型仍以 Action 为中心。SafetyGate 只存在于 watch 实现细节，不在 Agent 输出中成为可观察义务；approval、Gate、execution、expected 又分散在 metadata、action 状态和 feedback 里。这正是 R0-R8 收敛为当前唯一主链的历史原因；本节不是仍可并存的运行路径。

## 3. 核心协议：RawDecision 与 AgentOutput 必须分开

### 3.1 Raw model decision

模型输出只表达认知意图，例如：

```text
RawDecision
├── decision            reply / ask / propose / wait / refuse / stop
├── message
├── action_intents[]    仅当 propose
└── safety_intent?      advisory only
```

这里不能出现可信 Gate 结果、`approved=true`、`gate=passed` 或由模型指定的系统任务完成状态。所有来自模型或 caller 的这些字段都必须被忽略或覆盖。

### 3.2 Trusted PlanCompiler

`PlanCompiler` 是 raw decision 与公开 Agent 输出之间的唯一可信编译边界，职责包括：

- 归一化 action id、依赖和可信 correlation；
- 根据后端 policy/robot/capability 事实决定是否注入 `ApprovalTask`；
- 为每个 Action 无条件注入一个 `SafetyGateTask`；
- 让 `PhysicalActionTask` 依赖自己的 Gate；
- 让下游 Action 的 Gate 同时依赖上游 `PhysicalActionTask`，避免依赖未完成时被抢先校验或执行；
- 仅在存在 F4 expected 时注入 `VerificationTask`；
- 校验 task id 唯一、引用有效和 DAG 无环；
- 对 draft 使用 `not_scheduled`，明确“可见”不等于“已经提交执行队列”。

`PlanCompiler` 不读取或执行 driver，也不替代 watch 的最终裁决。它编译的是必须完成的义务，不是预先宣判 Gate 通过。

### 3.3 AgentOutput task DAG

单动作的最小输出：

```text
SafetyGateTask(action-1, owner=watch, mandatory=true)
  -> PhysicalActionTask(action-1, owner=watch)
```

需要审批且带 expected 的动作：

```text
ApprovalTask(action-1, owner=human)
  -> SafetyGateTask(action-1, owner=watch, mandatory=true)
  -> PhysicalActionTask(action-1, owner=watch)
  -> VerificationTask(action-1, owner=watch)
```

有 Action 依赖时：

```text
SafetyGateTask(A) -> PhysicalActionTask(A)
                           |
                           v
ApprovalTask(B)? ------> SafetyGateTask(B) -> PhysicalActionTask(B)
```

这条额外依赖很重要：B 的 Gate 必须在 A 完成后才成为 ready。SQLite claim 仍应直接跳过未满足 action dependency 的候选；Gate 再检查一次只是 defense in depth，不能靠“先 claim、再拒绝并取消”实现依赖等待。

### 3.4 SafetyGateTask 的公开内容

Gate task 可以在执行前公开稳定检查说明，例如：

- action id / dependency 完整性；
- robot 与 capability 是否存在；
- 当前 autonomy 与审批条件；
- capability params schema；
- bounds 等 constraints；
- timeout policy；
- `SAFETY.md` policy source。

这只是“将执行哪些检查”，不是模型可编辑的 checklist，也不是 pass 证明。实际 outcome 和 evidence 只能由 watch 产生。

## 4. Watch：最终裁决与结构化反馈

watch 对每个已满足前置条件的 action 执行最终 Gate，并写入独立结构化 feedback：

```text
SafetyGateFeedback
├── event               safety_gate
├── task_id / action_id / proposal_id
├── actor               watch
├── status              passed / rejected / error
├── decision            allow / deny
├── code
├── policy_source       SAFETY.md
└── checks[]
    ├── code
    ├── status
    ├── message
    └── evidence
```

要求：

- pass 与 reject 都可见，不能只在拒绝时落一条泛化的 “Action failed”；
- feedback 使用稳定 code，message 只用于人类阅读；
- Gate reject 后不得执行 driver；原 action 终态继续保留兼容语义；
- `VerificationTask` 只在动作完成并刷新 world 后运行；动作失败或观察失败时 expected 为 skipped；
- 后续认知轮次读取 Gate、action、observation 和 verification 结果，才能选择 reply、ask、replan、wait 或 stop；默认不自动重试。

执行调度在本轮进一步收紧：

- 单个 SQLite transaction 同时检查 pending candidate、completed dependencies 与每个 robot 的 in-progress 集合；因此多个 claimant 不会给同一 robot 同时 claim 两个 action，不同 robot 仍可分别领取；
- heartbeat 失败会把本进程中的 robot 标成 degraded，并在恢复前阻止新 claim；恢复成功后重新允许领取；
- capability timeout 与 watch default 合成为唯一 effective timeout，Gate 检查与 `driver.execute()` 使用相同值；
- dependency 已取消或已不可能满足时，下游 action 会被显式拒绝/取消并产生 verification skipped，而不是一直 pending；
- feedback event 使用 SQLite `BEGIN IMMEDIATE` 原子 read-append-write，解决多 writer 覆盖 history 的问题。

workspace 级执行 ownership 已在本轮落地：

- `watch-executor` runtime lease 在 driver connect 前获取，active lease 会拒绝第二个 WatchRuntime setup；owner 可续租或在过期/显式释放后由新 runtime 获取；
- Watch 在 connect、heartbeat、claim、idle observe 和 halt 等关键阶段续租/校验；失租抛出 fatal `WatchLeaseLostError`，API watch loop 停止重试；
- stale runtime shutdown 只断开自己的 transport，不再发送可能影响继任者的 halt；
- action claim 使用每次 setup 唯一 owner，完成/取消通过 `status=in_progress AND claim_owner=owner` CAS；旧执行结果无法覆盖已恢复/重领的 action；
- workspace reset 与 lease acquire/renew 串行，发现 active runtime lease 时 fail closed，API 返回冲突而不是抹掉 ownership。

边界仍需明确：这是 SQLite/workspace-level fencing，不是 driver/hardware-level fencing token。已经发出的设备命令不能被数据库 lease 撤销，设备也不会拒绝携带旧 epoch 的 I/O；若进程失联、存储隔离或 transport 已在阻塞调用中，软件 lease 只能阻止后续受检查的步骤。因此实机高可用接管仍需 driver/transport/设备层 epoch 或等价硬件 ownership 机制。

SAFETY 策略在执行前逐动作校验新鲜度：

- watch step 开始时建立 baseline snapshot，并用它的 typed `hard` 参与 claim；每领取一条 action 后、构造 Gate 前重新 `read_safety_snapshot()`；
- 比较 `identity_digest`（覆盖 revision、hard digest 与 guidance digest）：不一致则以稳定码 `safety.policy.changed` 在 `driver.execute` 前拒绝当前 action；解析失败或文件缺失以 `safety.policy.invalidated` 同样 fail closed；
- 这两种情况会连带取消**同一 `proposal_id`** 的剩余 pending actions，其他 proposal 留到下一 step 用新 baseline 处理；无 proposal correlation 的 legacy action 按单条处理；
- hardware profile 缺 Agent Guidance 一类的逐动作拒绝只拒当前 action，不取消同批；
- 策略拒绝走结构化 feedback 与稳定机器码，不调用 halt——halt 保留给设备异常或未知物理状态；
- `SafetyGate` 构造函数只接受当轮 fresh snapshot 的 typed `HardSafetyPolicy`，传入 dict 或整个 snapshot 会被拒绝，Gate 模块不读取 guidance。

已经在飞的前一条动作无法被文件更新撤销；本机制只保证其后的动作零执行。

## 5. 软件分层

当前实现形成以下边界；树中只列已经存在的模块，不把冻结候选伪装成待建默认结构：

```text
physical_agent/
├── protocol/
│   ├── actions.py          Action intent + advisory SafetyIntent
│   ├── agent_output.py     AgentOutput / AgentTask / check schemas
│   └── schemas.py          ChatPlan 与 API 共享协议
├── application/
│   ├── proposals.py        proposal use case
│   ├── plan_compiler.py    可信 task graph 编译
│   ├── output_projection.py board + feedback -> current AgentOutput
│   └── ports.py            application-facing state ports
├── agent/
│   ├── context_builder.py  只读上下文；hard/guidance 分离注入 safety 与 feedback
│   ├── chat_runtime.py     rule/LLM 产 structured draft；tool_loop 经 proposal-only tools 提交 pending
│   ├── planner.py          planner 协议
│   ├── rule_based.py       离线规则 planner
│   ├── llm_planner.py      LLM planner
│   └── planner_factory.py  各入口统一解析 planner
├── watch/
│   ├── safety.py           最终 Gate 决策与结构化证据
│   └── runtime.py          唯一执行、观察与 feedback 编排
├── state/
│   ├── sqlite.py           action/feedback 当前真源与原子事务
│   ├── sidecars.py         SAFETY/LOG 文件侧车与原子写
│   └── safety_policy.py    SAFETY 严格解析、typed HardSafetyPolicy/Snapshot 与 digest
└── api/
    ├── server.py           HTTP/OpenAPI 与 canonical response
    └── watch_service.py    API 到唯一 watch runtime 的适配
```

依赖方向：`protocol <- application <- agent/api/mcp`；watch 可以消费 protocol 和 state port，但 application/agent/API request handler 不得反向 import watch 或 driver。

### 5.1 Task graph 与 Action board 的关系

当前事实层级为：

```text
PlanCompiler 输出的 graph topology（不可由模型修改）
  + Action Board 的 pending/in_progress/completed/cancelled
  + watch feedback 的 safety_gate/expectation_check
  -> output_projection materialized current AgentOutput
```

`current_agent_output()` 会优先保留 active submitted actions，并在 chat-only plan 覆盖后从 Action Board 重编译这些义务；`project_chat_plan()` 把 materialized view 提供给 API/MCP/GUI/TUI。它解决的是“当前 active task 不被 presentation plan 隐藏”，不是历史任务持久化。

在 task graph 尚未持久化前要明确限制：重启后可以由 Action + metadata + feedback 重建 active/current graph，但已被后续 plan 覆盖的 terminal topology 并没有独立 task history。一个 proposal 的多条 actions 已由 `append_pending_actions()` 单事务提交；未完成的是把**持久化 task graph/obligation rows** 与该 action batch 放进同一事务，以及在事务内完成 server-side id allocation。Run/Event 与 persistent obligation 阶段再解决完整状态机、恢复和因果历史。

### 5.2 Skill、Tool、Capability 与 Task

- **Skill**：多步认知流程，没有物理执行特权。
- **Tool**：一次 application 操作，例如读状态、提交 task 或创建 proposal。
- **Capability**：driver 发布的物理能力，只能形成 Action intent，不能注册成 direct-execution LLM tool。
- **AgentTask**：可信 compiler 产生的计划义务，不是 tool，也不必等同于可调用函数。

尤其不能把 `SafetyGateTask` 注册为 LLM tool；否则模型会获得伪造调用或完成状态的表达空间。

## 6. Run / Turn / Event 的冻结候选位置

> **frozen registry**
> 冻结日期：2026-07-16（`c4da4f9`，本节由「正确位置」改写为「冻结候选位置」并加入本节末尾的重启条款）
> 解冻条件：「只有在 SPEC 重新激活对应条目、明确恢复与审计需求并完成独立设计评审后，才可重启；它不是 R8 之后的默认下一步。」
> 排序降级依据（回填自 `46c817e` §0，于 `c4da4f9` 从正文移除）：
> 「上一版路线把 `Run / Turn / Event` 当成 vNext 的第一块地基，这个顺序不正确。它能统一追踪与展示，却没有改变核心决策模型：模型仍像是在输出 `Action[]`，SafetyGate 只是动作被 watch 领取之后的一个隐式步骤。这样会导致三类问题：
> 1. Agent 的公开输出无法表达“这个物理动作在执行前必须完成哪些义务”。
> 2. 前端、TUI 和下一轮模型只能看到 action/feedback，难以区分等待审批、等待安全校验、正在执行和执行后验证。
> 3. 一旦先围绕 Run/Event 扩展，各入口仍会把同一组安全语义重复翻译，只是多了一层账本。」
> 同一处另有一句：「`Run / Turn / Event` 仍然重要，但它们是账本外壳，不是 Agent 的核心心智模型。」
> 冻结依据：未记载 —— 解冻评审时需重新论证。（上述论述支撑的是排序降级，不是不建设；本节正文另有一条约束「Event 是审计和恢复载体，不能成为绕开 state transaction 或 Gate 的第二执行通道」，同样不构成冻结依据。）

Run / Turn / Event 曾被记录为可能的外层账本模型：

```text
Run
└── Turn[]
    ├── input references
    ├── RawDecision
    ├── compiled AgentOutput
    └── Event range
```

- `Run` 表达一个用户目标及其总体状态。
- `Turn` 表达一次有边界的认知输入、决策和输出。
- `Event` 记录 proposal、task 状态、approval、Gate、execution、observation 与 verification 的因果时间线。

历史候选事件围绕真实闭环，而不是 UI 命名：

- `turn.decision_compiled`
- `task.status_changed`
- `approval.requested|approved|rejected`
- `safety_gate.passed|rejected|error`
- `action.claimed|completed|failed`
- `observation.recorded`
- `verification.verified|violated|skipped`

Event 是审计和恢复载体，不能成为绕开 state transaction 或 Gate 的第二执行通道。

当前代码没有 Run/Turn/Event ledger，本轮也不实现它。只有在 SPEC 重新激活对应条目、明确恢复与审计需求并完成独立设计评审后，才可重启；它不是 R8 之后的默认下一步。

## 7. API、流式协议与产品可见性

所有主要 proposal 入口都返回同一协议的 `AgentOutput`；R7 已删除与 `agent_output.actions` 重复的 proposal 顶层 `actions`/`action`/`draft_actions`，R8 又删除可陈旧的 `ChatPlan.actions` 第三份投影。plan consumer 只读 `plan.agent_output.actions`；运行 Action Board 仍读 `/api/state.actions`。typed OpenAPI 200-response schema 明确发布 proposal 与 mutation 的不同边界。包括：

- API task 与 manual proposal；
- MCP task 与 proposal；
- `AgentRuntime`；
- Chat tool loop；
- Chat draft（`lifecycle=draft`，任务全部 `not_scheduled`）。

React/TUI 已直接展示 task kind、owner、status、依赖、关联 action、Gate policy source，并消费服务端 materialized output。用户无需展开 raw JSON 即可回答“现在卡在哪里、下一步由谁做、Gate 是否真的执行过”。这仍是 read projection，不代表客户端或 plan 文档成为 Gate authority。

rule/LLM Chat draft 与 `ChatPlan` 已附上 `lifecycle=draft` 的 compiled `AgentOutput`；流式 chat 的 Draft 只从 SSE done/assistant metadata 的 canonical `AgentOutput` 创建。React/Web 可把它呈现为可操作卡片，TUI/CLI 只展示 structured draft。显式 tool_loop 则经 proposal-only tools 直接提交 pending，并返回 `lifecycle=submitted` 的 materialized output；它不 approve、不执行。reply 只作用户可读文本，即使包含旧 fence-like 内容也不得升级为卡片。旧 fence-only 历史消息仍可阅读，但不可再 Add；无需数据迁移层。

## 8. 冻结范围与重启条件

> **frozen registry**
> 冻结日期：2026-07-16（`c4da4f9`，本节由「与 world freshness、registry 和 F6 的关系」改写为「冻结范围与重启条件」，列表由推进顺序改为冻结候选清单）
> 解冻条件：「只有 SPEC §4 明确解除冻结、补齐依赖与正反验收并通过安全边界评审时，才能逐项重启；R8 不为它们预建模块、接口或兼容层。」
> 决策依据：仅第 4 项（F6 simulator 与 conformance）有记载 —— 「仿真可以帮助验证 action、world 与 UI 协议，但不能替代实机 SafetyGate 或证明 real-hardware policy 安全。」其余四项（registry/读模型、world freshness、W4 与 hardware-level fencing、Level 3 replan loop）未记载 —— 解冻评审时需重新论证。

以下均是冻结候选，不是默认开发路线：

1. registry、command/query 分离和共享 read model；
2. world freshness 的 `observed_at/revision/stale`；
3. W4 单 watch 多机器人并行 execute，以及 VNext-3B2/W6.2 hardware-level fencing；
4. F6 simulator 与 conformance；
5. Chat/Task 多轮自主 replan loop（Level 3）。

仿真可以帮助验证 action、world 与 UI 协议，但不能替代实机 SafetyGate 或证明 real-hardware policy 安全。

只有 SPEC §4 明确解除冻结、补齐依赖与正反验收并通过安全边界评审时，才能逐项重启；R8 不为它们预建模块、接口或兼容层。

## 9. 历史阶段结果与冻结候选

> **混合节 —— 见各子节标注**
> 本节不整体适用单一同步规则。VNext-1、VNext-2、VNext-3B1 的行为描述属 **living contract**（随代码同步）；VNext-3A、3B2、4、5、6 属 **frozen registry**（不随代码演进）。每个子节标题下另有标注。
>
> 以下元信息只适用于本节的 frozen registry 子节（VNext-3A、3B2、4、5、6）：
> 冻结日期：2026-07-16（`c4da4f9`，本节由「修正后的实施顺序与验收」改写为「历史阶段结果与冻结候选」，这五个子节标题由「未完成」改标为「冻结」）
> 解冻条件：本节未记载 —— 各冻结子节只列验收标准，未列解冻条件。
> 决策依据：未记载 —— 解冻评审时需重新论证。

### VNext-1：AgentOutput 与可信 PlanCompiler（本轮完成）

> **living contract** —— 前四条是对当前代码行为的陈述，随代码同步，以代码为准。末条「验收：…」是 2026-07-10 的当时验收记录，属历史记录，不随代码演进，不得作为当前行为的依据。

- 定义 raw decision 与 compiled output 的信任边界。
- 每个 Action 编译出唯一 mandatory watch-owned Gate task。
- approval、physical action dependency 和 optional verification 形成无环 DAG。
- API/MCP/AgentRuntime/Chat 返回同一输出结构，draft 与 submitted 明确区分。
- 验收：caller/LLM 无法伪造、删除或完成 Gate；每个可执行 Action 都能从输出找到 Gate 前置任务。

### VNext-2：结构化 Gate feedback 与 materialized current projection（本轮完成）

> **living contract** —— 前五条与末段「当前 obligation 状态通过…materialize」是对当前代码行为的陈述，随代码同步，以代码为准。「验收：…」一条与「以上已通过定向测试」一句是 2026-07-10 的当时验收记录，属历史记录，不随代码演进，不得作为当前行为的依据。

- watch 对 pass/reject 都输出 stable code、checks 与 evidence。
- output materializer 组合 compiled topology、Action Board 与 Gate/verification feedback，并能在 chat plan 覆盖后重建 active tasks。
- SQLite claim 跳过等待 dependency、busy/degraded robot；impossible dependency 显式 terminalize；Gate 保留二次防护。
- effective timeout 在 Gate 与 execute 之间一致；feedback append 跨 writer 原子。
- context-aware planner 读取 `SAFETY.md`、budgeted feedback 与 previous output；AgentRuntime 等待 verification。（SAFETY 现已按 hard/guidance 分 channel 投影注入，动作通道缺 guidance 会在调用 LLM 前 fail closed，见 §4 末段。）
- 验收：Gate reject 不触发 driver；active task 不因 chat plan 消失；同 robot 不重叠 claim；heartbeat degraded 暂停新动作并可恢复；UI/TUI 能解释当前状态。

以上已通过定向测试。当前 obligation 状态通过 compiled graph、Action Board 与 feedback materialize；不据此自动启动持久化 obligation engine。

### VNext-3A：持久化任务状态候选（冻结）

> **frozen registry** —— 冻结日期 2026-07-16（`c4da4f9`）；解冻条件见 §8。不随代码演进，常规同步不得调整。

- 明确 tasks 是持久化实体还是从 Action/feedback 可重建的 projection。
- 已完成：`append_pending_actions()` 单事务写入 proposal 的全部 actions，任何冲突回滚整个 batch。
- 未完成：在同一事务中持久化 task graph/obligation rows 与 action batch，并将 server-side action id 分配移入该事务；当前扫描编号的并发冲突会使整个 batch 失败，但不会产生半批 actions。
- 各入口已迁移到 `AgentOutput`，R7 已收缩旧 response 字段；本阶段不得重新引入 convenience payload。
- 验收：并发 proposal 不产生重复 id；持久化 graph 与 actions 不出现半份或不一致；当前已完成的 action batch all-or-nothing 必须保持。

### VNext-3B1：workspace watch runtime lease 与 action owner CAS（本轮完成）

> **living contract** —— 前三条是对当前代码行为的陈述，随代码同步，以代码为准。末条「验收已覆盖…」是 2026-07-10 的当时验收记录，属历史记录，不随代码演进，不得作为当前行为的依据。

- workspace 同时只有一个 active `watch-executor` owner；第二实例 setup fail closed。
- lease 在硬件阶段持续续租；失租产生 fatal stop，stale shutdown 不发送 halt。
- action terminal mutation 需要匹配唯一 `claim_owner`；active lease 阻止 destructive reset。
- 验收已覆盖 lease acquire/renew/release/expiry、双 WatchRuntime、stale completion CAS、fatal API watch stop 与 reset guard。

### VNext-3B2：driver/hardware-level fencing token（冻结）

> **frozen registry** —— 冻结日期 2026-07-16（`c4da4f9`）；解冻条件见 §8。不随代码演进，常规同步不得调整。

- 将 lease epoch/fencing token 下沉到 driver/transport/设备控制面，令设备或独占代理拒绝旧 owner 的后续 I/O。
- 明确 in-flight command、网络分区、存储不可达和接管前 fresh observe/halt 的故障模型。
- 验收：旧 owner 即使仍存活或旧 I/O 迟到，也不能对继任者控制的硬件产生副作用；接管绝不重放旧 action。

### VNext-4：Run / Turn / Event 账本（冻结）

> **frozen registry** —— 冻结日期 2026-07-16（`c4da4f9`）；解冻条件见 §8。排序降级依据见 §6，冻结依据未记载。不随代码演进，常规同步不得调整。

- additive 引入 Run/Turn 与带 sequence/cursor 的 Event envelope。
- correlation 扩展 run/turn/task/action。
- 从现有表与事件构建 timeline，不做一次性纯 event sourcing 重写。
- 验收：一次目标可追到每次 compiled output、义务状态、Gate evidence、执行与观察终态。

### VNext-5：Typed stream、registry 与 read model（冻结）

> **frozen registry** —— 冻结日期 2026-07-16（`c4da4f9`）；解冻条件见 §8。不随代码演进，常规同步不得调整。

- typed SSE、共享 reducer/类型；`action-draft` fence 已在 R7 完成兼容周期并退役。
- 统一 skill/tool/capability catalog；capability 永不成为 direct hardware tool。
- React/TUI 使用同一 read model。

### VNext-6：World freshness 与 F6（冻结）

> **frozen registry** —— 冻结日期 2026-07-16（`c4da4f9`）；解冻条件见 §8。不随代码演进，常规同步不得调整。

- 先落 `observed_at/revision/stale`，再评审多机器人并行执行。
- 按 F6.0 → F6.1 → F6.2 → F6.3 推进 simulator 与 conformance。

## 10. 当前明确未完成

完成状态必须以代码接线和测试为准。当前仍未完成：

- 独立 task table、持久化 obligation 状态机或完整 task event history；
- 持久化 task graph/obligation rows 与 action batch 的同一事务；actions batch 自身已是原子 all-or-nothing；
- 跨重启的 task status 恢复与并发状态推进；
- driver/transport/hardware-level fencing token 与 in-flight I/O 隔离；workspace watch runtime lease 与 claim-owner CAS 已完成；
- Run、Turn、Event 的持久化、恢复与 cursor；
- Chat/Task 的多轮自主 replan loop；
- typed stream、统一 registry/read model；
- world freshness、W4 并行执行和 F6。

准确表述应是：**Physical Agent 已能 materialize 当前安全义务，proposal action batch 已原子提交，并由 workspace singleton lease + unique claim owner CAS 保证软件执行者唯一性和 stale result fencing。它仍没有独立 task engine、持久化 task graph 与 actions 的同事务、Run/Event 账本或 driver/hardware-level fencing token。**
