# 001：执行计划

本计划故意把删除/迁移拆成顺序敏感的原子阶段。任何阶段的删除动作，都只能在该阶段的 Go gate 全绿后发生；No-Go 时修缺口，不跨阶段借债。

## 顺序总览

| 步骤 | 内容 | 当前状态 | 进入下一步的硬门槛 |
| --- | --- | --- | --- |
| 1 | 冻结范围、建立规格与退役清单 | ✅ 第一轮完成 | spec/plan/tasks、三份 surface 审计、SPEC/PLAYBOOK 登记完成 |
| 1.5 | legacy GUI parity + 缺口补齐 + launcher strangler cutover | ✅ PR #1 / `2d5e909` 验证完成 | 所有保留能力已覆盖；有意退役项有替代说明；thin launcher/wheel smoke + 当前提交 Playwright 全绿 |
| 2 | 验证 cutover 后删除 legacy GUI | ✅ `5764bac` / PR #1 全绿 | React/FastAPI 成为唯一 GUI；安全/主路径回归通过 |
| 2.1 | canonical projection 与删除门禁 review fix | ✅ `b20ad20` / PR #1 全绿 | React/TUI 不再二次推断 Gate；pending 不复用旧 passed Gate；PR e2e/wheel 负门禁阻塞 |
| 3 | 退役 Markdown migration，缩成 safety/log sidecar | ✅ sidecar cutover `a64be59`；R3 closure `a431c3b`，fork Push run `29233815375`、PR run `29233817630` 均成功 | 当前树与 wheel 均无 migrator/full Workspace；sidecar 等价；旧目录 fail closed；历史救援可执行 |
| 4 | 删除 `auto_step` 与 embedded watch composition | ✅ `da14064` 完成；下一步 R5 | proposal/chat 入口不拥有 watch；正式 `watch` 与 `api --watch` 保留并通过边界回归 |
| 5 | 结构化 Chat Turn + `action-draft` 双轨 | ✅ `d1ca53c3`；fork Push run `29321294713`、PR run `29321297674` 均成功 | 独立一轮验证 structured/fence 一致，F1 主链与旧 fallback 全绿 |
| 6 | 收敛 application/read-model 职责和官方消费者 | ✅ `0bb7807`；fork Push run `29312317707`、PR run `29312319687` 均成功 | `_append_actions` 等死代码为零；消费者只读 canonical projection/output |
| 7 | 切断旧 wire compatibility | ✅ `9ba44af`；fork Push run `29399978672`、PR run `29399982326` 均成功 | 停产/删除 fence；删除 proposal 顶层 `actions/action/draft_actions`，不动 state board |
| 8 | 文档、发布形态与全量验证收口 | ✅ implementation closure `c4da4f9`，fork Push run `29476327424`、PR run `29476329954` 均成功；evidence closure `33b062b`，fork Push run `29477199756`、PR run `29477202468` 均成功 | 全量测试、wheel、docs/CLI/README grep 和安全扫描全绿；实现与最终证据均已闭环 |
| 8.1 | 阶段 review hardening | ✅ implementation/local closure `8438cb7`；fork Push run `29553985591`、PR run `29553987358` 均 completed success，headSha 均为 `8438cb7bf5f356021cb602908552a069e8227bc4` | LOG 多进程与安全收尾、Gate claim correlation、嵌套 OpenAPI、证据/PR 元数据全部关闭；新功能继续冻结 |

## 1. 冻结范围、建立规格与退役清单

本步只允许文档、只读审计和验证，不删除生产代码。

1. 记录产品决策：legacy GUI 全退役、Markdown migration 提前退役、SPEC 功能扩张暂停。
2. 把执行顺序、正反验收、救援路径落到 `spec.md`、`plan.md`、`tasks.md`。
3. 枚举三类 surface：
   - legacy GUI 每个端点/用户功能/测试/打包入口；
   - Markdown migrator/full Workspace 与 safety/log 生产依赖；
   - streaming fence、`auto_step`、proposal response duplication 和死代码。
4. 在 SPEC §4 与 PLAYBOOK 建立同名条目；REFACTORING 只记录本轮完成的规格/审计事实，不把后续删除写成已完成。

Go：`tasks.md` 中 R0 清单全部完成，parity 表没有“未枚举”项。

Rollback：仅回退文档提交，不涉及运行态。

## 1.5 legacy GUI parity 与缺口补齐

这一步是步骤 2 的前置半步，不能合并到“删 GUI”提交里。

1. 补安全的首次初始化 API/UI：只创建默认 config/workspace，不启动 WatchRuntime。
2. 为 Dashboard 增加 read-only executor status projection：聚合本进程 `ApiWatchService` phase/error 与 SQLite `watch-executor` active lease/expiry，区分 embedded/external/none；`watch_enabled` 仅表示配置，不冒充 executor 或硬件连接健康。
3. 在 config/robot 视图展示 `execution_mode`，即使 watch 尚未发布 capabilities 也可见。
4. 固化 reset 新语义：只清 workspace、保留 YAML、活动 lease 返回 409；CLI 提供 factory reset 替代。
5. 把 React build 放进 Python package resource，补 wheel 安装后 `/` 和 assets smoke。
6. 在 legacy 实现仍可回退时，先把 `physical-agent gui` 切成正式 FastAPI app 的薄 launcher；保留 host/port/browser 体验，默认使用同一个 embedded `ApiWatchService`，提供 `--no-watch` 观察模式，不得调用 legacy controller。
7. 把 legacy-only 测试证据迁移到正式栈：
   - FastAPI LLM hardware integrate + model override；
   - hardware/simulation mode 可见性；
   - streaming draft → Add to Actions → pending ActionBoard e2e。
8. 在 README/CLI/Dashboard 明示有意退役项及替代：GUI watch controls/manual step、hard-coded Demo、planner selector（Dashboard 固定 auto，CLI `chat --planner` 调试）、browser code skill（CLI `chat --show-code-result`）、browser doctor。

Go：`tasks.md` GUI parity 表的每一行只能是“覆盖并验证”或“有意退役且替代已验证”；thin launcher 已完成 strangler cutover，React wheel smoke 与当前提交 Playwright 实际浏览器运行通过。

最终证据：draft PR #1 的 CI run `29139972352` 在 `2d5e909` 上完成 Python full、Safety、TUI、frontend build、clean-wheel 和真实 Chromium 25/25，R2 删除门禁已解除。

No-Go：Setup 死胡同、watch 假健康、wheel 缺静态资源、任一 legacy-only 主路径测试尚未迁移，或当前提交缺真实浏览器运行证据。

Rollback：本步只加正式栈能力，不动 legacy GUI，可直接回退新增端点/UI。

## 2. 验证 cutover 后删除 legacy GUI

1. R1.5 的 thin launcher/wheel/主路径必须先经过独立验证；legacy 模块此时仍在树中但已不再是默认入口。
2. 更新安全边界测试：删除 legacy controller allowlist，继续只允许 `ApiWatchService`/正式 watch composition 延迟加载 WatchRuntime。
3. 删除 `physical_agent/gui/`、legacy package-data、`test_gui_server.py` 与 `test_gui_static_contract.py`。
4. 删除 legacy API/static 文案和 docs 引用，确认 `rg "physical_agent\.gui|gui/static|GuiController|make_server"` 仅剩历史记录。

Go：同一 wheel 中 `physical-agent gui`/`api` 都托管同一 Dashboard；没有 legacy controller/static；安全边界与 e2e 全绿。

Rollback：回退整个步骤 2 提交即可恢复旧实现；步骤 1.5 新增能力保持可独立存在。

## 2.1 canonical projection 与删除门禁 review fix

本步只修 R2 阶段 review 暴露的既有架构偏差，不提前执行 R3-R7 的删除任务。

1. React 与 TUI 只呈现服务端 `output_projection` 给出的 `AgentTask.status`；删除从 raw feedback/Action Board 二次 materialize Gate/approval/physical task status 的逻辑。
2. 增加伪造或不完整 Gate feedback 负例，证明客户端不会把后端 fail-closed 的 task 改回 `passed`。
3. 对 recovered 后重新处于 `pending` 的 action 忽略旧 claim 留下的 canonical `passed/allow` Gate 事件；不新增 persistent attempt/obligation schema，watch 下一次 claim 仍重新执行 Gate。
4. PR Playwright 从 advisory 改为 blocking；clean-wheel smoke 自身检查 archive 不含 `physical_agent/gui/`，不只依赖 PR full pytest 的负断言。
5. 本轮不更新用户指定保留的阶段快照 `docs/current-architecture-audit.md/html` 与 `docs/system-summary.zh-CN.md`。

Go：backend forged/stale Gate 负例、React/TUI consumer 负例、frontend build/e2e、TUI test/build、Python projection/safety tests与 wheel smoke 全绿。

Rollback：客户端删减、projection 修正和 CI hardening 分层清晰；任何行为回归可单独回退对应提交，不影响 R2 已删除的 legacy GUI。

## 3. 退役 Markdown migration，缩成 safety/log sidecar

顺序不可交换：行为测试 → sidecar 接管 → 真实历史救援 smoke → migrator 删除 → fixture 改写/full Workspace 删除 → 文档收口。

1. 先以聚焦 behavior tests 锁定 SAFETY/LOG、doctor、audit、普通 init 与 overwrite/reset 现状，并定义 LOG mirror 失败时 SQLite 真源与 doctor 诊断口径。
2. 新建聚焦的 state sidecar adapter，承接：
   - `SAFETY.md` 默认/读取/写入/front matter/revision；
   - `LOG.md` 初始化/actor/timestamp/revision/并发追加；
   - doctor 所需的最小 front matter 校验。
3. `SqliteStateStore`、doctor、audit export 切到 sidecar；旧 migrator/full Workspace 暂留，证明生产路径已完成 strangler cutover。
4. 保留 legacy workspace detection 和显式 markdown backend 拒绝；错误文案改为 `9072b4e` 独立 worktree救援流程，并在删除前用实际旧 checkout/package 做 smoke：核验旧/新解释器来源，旧 migrator→手改 config 为 sqlite→回新版运行不带 `--force` 的 init→state-check，并逐项验证历史 migrator 覆盖的数据面。
5. rescue gate 全绿后，删除 CLI `migrate-md-to-sqlite`、`LegacyMarkdownWorkspaceReader`、SQLite migration function、迁移专用 audit reader、`allow_retired_markdown` 开关及只被 migrator 调用的 replace/revision helpers。
6. 先重写非迁移 fixture，再删除完整 `protocol.workspace` 以及 task/action/chat/capability/world/feedback/plan/memory 的 Markdown parser/renderer；保留或内收 safety/log 所需最小 Markdown 工具，不把仍有价值的 driver/onboarding/chat-summary 测试随 `Workspace` 一起删除。
7. 清 README/state-backends/hardware guide/example 等当前操作口径；REFACTORING 的 B6 历史事实不改写，只追加提前退役决定。用户指定保留的两份阶段快照不纳入本轮 current-doc 收口。

Go：当前版本不存在 migrator/full Workspace；safety/log/doctor/audit 行为等价；显式和隐式旧 workspace 都拒绝启动且给出可执行救援指针。

No-Go：任何改动让 `SAFETY.md` 进入数据库、LOG 镜像丢 actor/revision、旧目录旁静默创建 SQLite。

Rollback：至少拆成三个提交：sidecar 接管、migrator 删除、full Workspace/test fixture 删除；出现问题先恢复对应删除提交，保留已验证的 sidecar。

## 4. 删除 `auto_step` 与 embedded watch composition

1. 随 legacy GUI 删除其 checkbox/payload/controller 分支。
2. 删除 CLI `chat --auto-step`、`_run_chat_auto_step()`、相关输出和 README 示例。
3. 删除 `ChatRuntime.respond/respond_stream(auto_step=...)` 兼容参数。
4. 删除 `ChatRequest.auto_step` 和 API 侧显式 `False` 传参。
5. 把“传 auto_step 也不执行”的兼容测试改为更强的结构测试：proposal/request handlers 不 import/instantiate WatchRuntime，不调用 driver。
6. 保留正式 `physical-agent watch` 与 `physical-agent api --watch`；不得误删 CLI 为 watch 命令使用的 WatchRuntime import。

Go：`rg "auto_step|auto-step"` 仅剩历史记录；所有执行仍只发生在正式 watch 生命周期。

Rollback：单独提交，恢复参数不会改变 SQLite schema。

## 5. 结构化 Chat Turn 与双轨验证

### 5.1 生产路径先收口

R5 开工前，streaming 的 `AgentOutput` 是在完成后从 fence 反向解析出来的，不算独立结构化通道。该阶段先建立 typed Chat result，但不把 ChatRuntime 的不同语义硬塞成 draft：

1. 结果使用明确 variant/kind：普通 reply 的 `agent_output` 可选；只有 proposal variant 才有 draft lifecycle output；tool-loop 是 submitted proposal；CLI code/integration 路径继续是独立 typed variant。本步骤只收口 `/api/chat` 使用的 rule/LLM reply/proposal 主路径，不借机删除 CLI code/integration/tool-loop。
2. proposal variant 的 action intents 只分配一次稳定 draft IDs，再经 trusted `PlanCompiler` 得到 draft `AgentOutput`；done、ChatPlan、assistant metadata 与兼容 fence 的 action IDs/dependencies 必须一致。
3. `respond()` 返回 typed result；`respond_stream()` 只负责把同一 result 的 reply 发成 delta，并在 done 发送同一可选 `agent_output`/plan。
4. R5 开工先做受限 spike，比较 provider structured/tool events、单调用 structured stream 等方案；正式实现必须保留真实首 token/delta 与中途 abort 语义，不能把完整结果完成后的本地分块冒充 streaming。若现有 provider-neutral client 无法同时满足“一份 authoritative action set + 原生 streaming/abort”，停止并单独请求产品取舍，不在本规格里预授权回退。
5. 无论采用哪种实现，compile/persist/done 前必须再次检查 cancellation；已 abort 的 turn 不得持久化可提交 `AgentOutput` 或 assistant draft metadata，并补“structured producer 进行中 abort”专项测试。

理由：必须同时守住一个 authoritative action set 和现有 streaming 用户体验。两次调用可能产生 reply/action 不一致，provider-specific parser 会扩大兼容面，但这些工程成本不能靠静默取消首 token/中途停止来转嫁给用户。

### 5.2 双轨一轮

1. 后端从结构化 `agent_output.actions` 生成兼容 fence；禁止再从 fence 反推 AgentOutput。
2. API SSE `done` 转发 `agent_output`/plan，不再丢字段。
3. React 用 type guard 验证 `schema=physical-agent/agent-output/v1`、`lifecycle=draft`、`decision=propose` 和合法 action 数组后才消费 SSE/assistant metadata；历史消息在 structured output 缺失或不合法时 fallback 到 fence，新 structured 消息还必须由 compiler provenance 声明本轮存在 draft 才可 fallback；两者同时存在只显示 structured，冲突时 structured 胜出。
4. TUI 类型补 `AgentOutput.actions`，draft 与 Action Board 分开展示。
5. 完成一轮 backend/API/React/TUI/e2e 正反验证，保留证据后只允许进入步骤 6；步骤 7 还必须等待步骤 6 的官方 consumer migration 完成。

Go：structured-only、fence-only、两者一致、两者冲突、refresh 恢复、structured-call abort/error、Add to Actions 全部通过；draft IDs/dependencies 在四份表示中一致；draft 不直接进入 pending board；每个 draft action 仍有 mandatory Gate task。

Rollback：双轨期随时切回 fence consumer；producer 已结构化，不需要回退心智模型。

### 5.3 review-fix 门禁

R5 独立验收前先修复以下跨层缺口，不把它们推迟到 R6/R7：

1. terminal persistence 必须 exactly-once；consumer 在收到 `done` 后关闭 iterator 不得再追加 cancelled assistant 或把 answered plan 降级。
2. canonical `AgentOutput.message` 只保存 provider base reply；双轨 fence 只存在于兼容 wire reply，不能污染 compiler output。
3. R5 streaming 使用 provider JSON mode + 本地 JSON Schema 校验；不先发送与当前开放 schema 不兼容、注定 400 的 strict-schema 请求。format fallback 仍只允许在零 byte 阶段发生。
4. abort 除 cooperative flag 外，还要把 best-effort closer 注册到实际 SDK stream；API Stop 可主动关闭正在阻塞读取的 provider transport。
5. 新 structured turn 写显式 contract/provenance。只有 compiler 确认本轮存在 structured draft 时才允许 fence 作双轨灾备；新 reply-only turn 中模型自行输出的 fence 不得变成可点击卡片。没有版本标记的历史消息仍保留 R5 fallback。

Go：done-then-close、mid-delta abort、provider transport close、canonical message/fence 分离、new reply-only fence 负例与 historical/declared compatibility fallback 全部有回归证据；之后仍需独立 CI/真实 Chromium 才能关闭 R5。

## 6. 收敛 application/read-model 职责和官方消费者

1. 删除已确认无引用的 `physical_agent/agent/chat_runtime.py::_append_actions`。
2. 同时删除其专属 `_normalize_depends_on` import 与 `_max_action_number()`；action 编号、dependency remap、原子 batch 只属于 `ProposalService`/state transaction。
3. 官方 React/TUI/API/MCP/CLI `run/chat`/AgentRuntime 测试迁移到 `agent_output.actions`；此步仍暂留顶层 response compatibility 字段，便于验证新消费者。保留 `ProposalResult.actions` 等 application 内部 typed command result，不要求内部代码先序列化再从 AgentOutput 反读。
4. API/MCP 状态读取统一经 application projection/query；ChatPlan 可以保存最后一次 `agent_output` snapshot/presentation/correlation，但 current status 只能由 application projection 合成，不得在 ChatPlan 内自行 materialize Gate/task status。
5. 删除职责重复但已无消费者的 compatibility wrapper；保留 React/TUI 各自 formatter，不制造跨运行时 UI 抽象。
6. `rg "_append_actions|_max_action_number" physical_agent/agent/chat_runtime.py` 必须为零，并跑 ProposalService/chat/action batch/dependency 回归；`application/proposals.py` 的 canonical 编号 helper 保留。

Go：所有正式消费者已脱离 proposal 顶层 convenience fields；proposal 持久化只有 ProposalService + StateStore 路径；Gate/status 只有 application projection 解释。

Rollback：先迁 consumer 后删 dead code/wrapper，拆成可独立回退的提交。

## 7. 切断旧 wire compatibility

步骤 5 的双轨验证和步骤 6 的 consumer migration 都完成后才执行：

1. 停止产生 `action-draft` fence，删除 fence parser、fence 专用 fixtures/tests/prompt 约束；保留 structured Draft 卡片组件与 `.draft-action-card` 样式。
2. 删除 task/chat/manual proposal response、ChatRuntime result 与 assistant metadata 的顶层 `actions`/`action`/`draft_actions`；canonical action payload 为 `agent_output.actions`。
3. 保留 approve/reject mutation response 的 `action`，因为它不是 proposal duplication；保留 `/api/state.actions` 与 SQLite Action Board。
4. 删除 MCP/AgentRuntime/tool-loop 对等的公开 proposal action convenience fields，并更新 OpenAPI/schema/types、README/API 示例、breaking-change note、Playwright/TUI mocks、MCP/CLI tests；envelope/status/correlation 与 application 内部 `ProposalResult.actions` 保留。
5. 对历史 chat 的处理采用显式版本边界：升级后不承诺把旧 fence 恢复为可点击 draft；文本历史仍可读。该行为写入 release/upgrade note，不保留永久 parser。

Go：新旧字段 grep、API schema、官方客户端、旧负用例全部通过；Actions 板继续从 state truth 工作。

Rollback：fence 和 response 字段分两个提交；任一外部兼容问题可单独恢复一项。

## 8. 文档、发布形态与全量验证收口

1. 以当前实现收口正式 current docs。用户保留的 `current-architecture-audit.md`、`current-architecture-audit.html` 与 `system-summary.zh-CN.md` 是阶段快照，不属于 current-doc contract；不修改、不删除、不重新生成，也不据此阻塞 R8。
2. SPEC/PLAYBOOK/REFACTORING/README/README.zh-CN/state-backends/hardware guides/examples/CLI help/API/OpenAPI 统一口径。
3. 把 `agent-architecture-vnext` 收口为当前架构说明，不再把已暂停的 task table/Event ledger 写成默认下一步。
4. 执行 Python 全量测试、frontend build + Playwright、TUI build/test、wheel build/install smoke、安全 AST/grep 边界扫描。
5. 更新 `tasks.md` 删除证据矩阵、SPEC 状态和 REFACTORING 决策/教训；R8 最终没有创建独立 handoff 文档。

Closure：implementation closure `c4da4f9` 的 fork Push run `29476327424`、PR run `29476329954` 成功；随后 evidence closure `33b062b` 的 fork Push run `29477199756`、PR run `29477202468` 成功，R8 十二项全部闭环。

后续：重新评审冻结 backlog；没有真实需求证据的项继续挂起。

## 8.1 阶段 review hardening

R8 远端 closure 后的独立阶段 review 发现三个实现缺口和一组证据偏离。本步只做纠偏，不恢复任何冻结功能：

1. SQLite 继续作为 LOG 真源；`LOG.md` 改成跨进程序列化、原子替换、失败不阻断安全/业务控制流的可诊断镜像。
2. current projection 使用现有 claim owner 约束 in-progress Gate evidence，避免 successor claim 窗口复用旧 owner pass；不新增 task/attempt ledger。
3. `ChatPlan.agent_output` 在 OpenAPI 中引用 canonical `AgentOutput`，不改变 JSON wire。
4. 修复 spec/plan/matrix/PLAYBOOK/REFACTORING/PR 元数据，并如实记录 R5-browser 与 R6 顺序、R6/R7 rollback 粒度偏离。
5. 通过 Python full、真实 Chromium、TUI、clean-wheel、多进程/安全专项和独立终审后才可关闭；关闭也不自动解冻后续功能。

实现与定向证据（2026-07-16）：LOG 修复 `6d53db3`；Gate claim-owner correlation `4c9c6a4` 及 late-feedback fencing `c38e3ec`；nested OpenAPI `89f84c8`。Task 1 focused `60 passed`、group `177 passed`、阶段 full `439 passed`；Task 2 combined `127 passed`；Task 3 focused `78 passed + 78 passed`。后续 review follow-up 为 `241fe8d` terminal final owner、`fc282cf` newest raw owner Gate validation + real dependency path、`b2c93bb` denial-only fallback。最终本地证据（2026-07-17）：Python full `462 passed, 1 warning`；TUI typecheck/test/build `61 passed`；frontend `tsc -b && vite build` （3309 modules）与真实 Chromium `27 passed`；clean-wheel base/server-extra smoke 通过；多进程 LOG + halt + Gate owner + OpenAPI + Safety AST + docs/golden/Moce 专项 `71 passed`；受影响 state/projection/API/MCP/watch/safety `152 passed`；`git diff --check`、tracked dist、退役 production markers 与受保护 snapshot diff 均 clean；独立终审经四轮 fix/re-review 后 Critical=0、Important=0、Minor=0。远端 closure 证据（2026-07-17）：implementation/local closure `8438cb7`；fork Push run `29553985591`、PR run `29553987358` 均 completed success，headSha 均为 `8438cb7bf5f356021cb602908552a069e8227bc4`。PR 保持 OPEN + draft。

R8.1 不解冻 VNext-3/4、W4/W5/W6.2、F0/F5/F6、B4-vec、registry/read-model 或自动 replan；只有出现可复现的真实需求并形成显式 SPEC 决策后，才可重启对应条目。
