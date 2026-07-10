# 001：架构减法与兼容面退役

状态：执行中（R0 完成；R1.5 cutover 已实现、浏览器门禁待补；R2 删除 No-Go）

日期：2026-07-10

对应账本：`SPEC.zh-CN.md` §4 `R0-R8`

## 0. 目标

本条目不是继续实现 W4、W6.2、F6 或 VNext-3/4，而是在已经落地的 assurance-first 心智模型上做一次结构减法：让产品只保留一套正式 Dashboard、一套 SQLite 运行态、一套公开 `AgentOutput` 契约和一条 watch 执行链，并按可验证的兼容窗口退役旧入口与重复字段。

完成后的系统仍遵循：

```text
不可信 raw decision
  -> trusted PlanCompiler
  -> AgentOutput（公开的安全义务图）
  -> SQLite Action Board + structured feedback（运行事实）
  -> watch（唯一 Gate / execute owner）
  -> output_projection（current AgentOutput）
  -> React / TUI / API / MCP
```

R1.5 只完成正式栈补缺与 strangler cutover，不删除 legacy 实现。只有当前提交的真实浏览器验收和独立 cutover 验证都通过后，才允许进入 R2 删除。

## 1. 不可破坏的边界

1. `driver.execute()` 只允许出现在 watch 执行调用栈。
2. 任何物理动作执行前必须经过 watch-owned `SafetyGateTask` 与 `SAFETY.md` 文件真源；审批、兼容层和 UI 都不能绕过。
3. Action Board 与 structured feedback 是当前运行事实；`AgentOutput` 是对外心智模型和 materialized read model；`ChatPlan` 只做 presentation singleton，不成为第二运行真源。
4. 删除或迁移必须先有枚举清单、正反验收和回滚/救援路径。未列出的旧能力不得被推定为“不重要”。
5. `action-draft` 文本 fence 在结构化 streaming 主链验证完成前必须保留；同一轮双轨写出，下一轮才允许删除旧轨。
6. `SAFETY.md` 与 `LOG.md` sidecar 是正式能力，不属于“旧 Markdown workspace”退役范围。

## 2. 已定决策

### 2.1 正式 GUI 只保留 FastAPI + React

- 删除 `physical_agent/gui/` 的 controller、标准库 HTTP server 和静态页面。
- 保留 `physical-agent gui` 这个用户命令，但把它改成启动 FastAPI + packaged React Dashboard 的薄 composition root；默认等价于正式 app factory 的 embedded watch 模式，以保留单命令体验，并提供显式 `--no-watch` 观察模式。它不再拥有另一套 controller、API 或 WatchRuntime。
- 删除前必须完成 legacy GUI parity checklist。缺失的正式用户主路径先补齐；明显违背新边界的旧能力必须显式登记为“有意退役”并给出替代入口，不能静默消失。
- React build 必须进入 Python wheel，不能只在源码 checkout 的 `frontend/dist` 中可用。

理由：两套 GUI 同时拥有 API、状态拼装和 watch 生命周期，是当前最大的重复面；保留命令兼容而删除实现重复，可以减少用户迁移成本而不保留第二套架构。

### 2.2 GUI 能力取舍

保留或补齐：

- 安全的首次初始化入口；
- workspace reset（清状态、保留 `physical-agent.yaml`、活动 lease 时 fail closed）；
- 实际 watch runtime health，而不是只展示 `api --watch` 启动参数；
- 未连接 watch 时仍可见的 `hardware | simulation` 配置；
- chat、task/manual proposal、draft → Add to Actions、审批、状态/反馈、安全、硬件 scaffold/LLM draft、robot 注册、上传、memory、audit、LLM settings。

有意退役：

- 浏览器覆写 `physical-agent.yaml` 的 factory reset，替代为安全 workspace reset；需要恢复默认配置时使用 CLI `physical-agent setup --force`；
- GUI 内 start/stop/manual step watch，替代为受运维生命周期管理的 `physical-agent watch` 或 `physical-agent api --watch`；Dashboard 只观察真实 health；
- hard-coded pick/place Demo，替代为 `physical-agent setup --smoke-test`；
- per-message planner selector；Dashboard chat 固定 `auto`，Settings 只配置 LLM provider/model，调试 override 使用 `physical-agent chat --planner auto|llm|rule_based`；
- browser code skill，代码修改不从 Dashboard chat 发起；需要查看 CLI code skill 结构化结果时使用 `physical-agent chat --show-code-result`；
- raw doctor 面板，运维诊断使用 `physical-agent doctor`，Dashboard 保留 state-check 与可读 health。

理由：parity 的单位是仍被支持的用户任务，不是把旧 GUI 中与 proposal-only Dashboard 冲突的执行耦合逐字复制。

### 2.3 立即退役旧 Markdown workspace 迁移入口

- 删除 `migrate-md-to-sqlite`、`LegacyMarkdownWorkspaceReader`、迁移函数、迁移专用 parser/renderer、测试和当前文档承诺，不再保留一个版本周期。
- 删除前先把 SQLite 正在使用的 safety/log 文件操作抽成聚焦的 sidecar adapter，再缩减旧 `Workspace`/Markdown 协议。
- 保留显式 `workspace.backend: markdown` 拒绝，以及省略 backend 但检测到完整 legacy workspace 时的拒绝，避免在旧目录旁静默创建 `state.db` 形成双真源。
- 错误信息改为历史救援指针：需要迁移旧 workspace 的用户，在独立 worktree checkout `9072b4e`（或迁移入口删除提交之前的版本）并安装/调用该 checkout 的旧 `physical-agent`，运行 `migrate-md-to-sqlite`；手工把原 config 改为 `workspace.backend: sqlite` 后回当前版本，运行不带 `--force` 的 `physical-agent init`，随后运行 `physical-agent state-check`。不得误调用已经升级的当前 executable 充当旧 migrator。

理由：运行态早已 SQLite-only，继续维护一次性 reader 会拖住协议收口；但 safety/log sidecar 和 legacy 检测解决的是当前安全与双真源风险，不能随迁移入口一起删除。

### 2.4 退役 `auto_step`

- 删除 API/ChatRuntime 的兼容参数、CLI `--auto-step` 以及 CLI 内嵌的一次性 WatchRuntime composition。
- agent/chat/task 只表达 proposal、等待条件和 `needs_watch`；执行由独立 watch 生命周期承担。

理由：`auto_step` 已在 ChatRuntime 内成为 no-op，却仍让 CLI 和旧 GUI 保留“认知请求顺便推进执行”的旧心智模型。

### 2.5 结构化 streaming 先双轨，后删除 `action-draft`

- 先让 streaming `done` 事件携带 compiler 生成的 `agent_output`，并让 React 优先消费结构化字段、文本 fence 仅作 fallback。可信的是 compiler 注入的 topology/owner/Gate 义务；其中 draft actions 仍是不可信 proposal intents，不代表已通过 SafetyGate 或可直接执行。
- 双轨期间后端仍写 fence；验证 streaming chat → draft card → Add to Actions → pending Action Board 全链路，以及旧客户端 fallback。
- 经过至少一轮独立验证后，才删除 fence 生产、parser、fixture 和文案。

理由：当前 streaming 是 reply-only，F1 主链靠 fence 传 draft；直接删 fence 会造成无报错的功能断链。

### 2.6 删除公开 proposal action payload duplication

- 正式客户端迁移到 `agent_output.actions` 与 `agent_output.tasks`。
- `/api/state.actions` 永久保留，它是 Action Board 的运行事实，不属于重复 response 字段。
- task/chat/manual proposal response 顶层的 `actions`/`action`/`draft_actions` 只作为临时兼容字段；结构化客户端完成迁移且双轨验证通过后删除。
- `message`、`proposal_status`、`proposal_id`、`refusal_reason` 等 envelope/status/correlation 字段本条目保留；`ProposalResult.actions` 等 application 内部 typed command result 也不在公开 wire 去重范围。若要继续删，必须另做消费者审计。
- Web 与 TUI 可以保留各自的 formatter/viewmodel；统一的是后端契约与状态解释，不强求两个表现层共享渲染代码。

理由：删除 wire duplication 可以减少分叉；强行共享浏览器与终端 presentation code 反而会制造抽象泄漏。

### 2.7 暂停功能扩张

R0-R8 期间暂停 VNext-3、VNext-4、W4、W5、W6.2、F0 后续实验、F5、F6、B4-vec、自动 replan、registry/read-model 扩展等功能项。只有为本条目验收、安全回归或去重所需的改动可以进入。

重启条件：R8 全量验证完成、运行主链和发布形态收口后，再依据真实恢复/硬件/产品需求重新排序，而不是自动恢复旧排期。

理由：继续叠加 task table、Event ledger、仿真和硬件 HA 会放大当前重复契约与兼容层，降低“做减法”的可验证性。

## 3. 目标软件边界

| 层 | 保留职责 | 不再承担 |
| --- | --- | --- |
| `protocol` | `Action` intent、`AgentOutput`、structured feedback、最小 safety/log sidecar 格式 | 完整 legacy workspace 文档协议、UI response duplication |
| `application` | `ProposalService`、trusted `PlanCompiler`、唯一 current output projection | watch 生命周期、driver、presentation formatting |
| `agent` | raw decision、context、planner/chat orchestration | watch step、driver load、持久化 read-model 拼装 |
| `state` | SQLite Action Board/feedback/runtime lease 真源；safety/log sidecar | Markdown runtime/migration reader |
| `watch` | lease、Gate、claim、execute、observe、feedback | HTTP/UI 请求处理 |
| `api` | commands、queries、typed stream、正式 Dashboard 托管 | legacy GUI controller、重复状态规则 |
| React/TUI | 消费同一结构化协议，各自 presentation | 推断 Gate 状态、写回 task truth |

## 4. 范围外

- 不新增 persistent task table、Run/Turn/Event ledger 或自动重规划。
- 不实现 W4 多机器人并行、W6.2 hardware fencing、F6 simulator。
- 不修改两条安全宪法，不把 `SAFETY.md` 移入 SQLite。
- 不把 React/TUI 合并成同一 UI 包。
- 不以“代码更少”为由删除仍无替代或无验收的用户能力。

## 5. 总体验收

1. wheel 安装后，`physical-agent gui` 与 `physical-agent api` 能托管同一 React Dashboard；仓库不存在 legacy GUI server/controller/static。
2. Dashboard 首次初始化、reset、runtime health、hardware/simulation 可见性和现有核心路径有 e2e；被退役 GUI 能力均有明确替代说明。
3. 当前版本不存在 Markdown migration 命令/reader/full-workspace parser；`SAFETY.md`、`LOG.md`、doctor、audit 和 legacy 双真源拒绝仍通过回归。
4. 仓库不存在 `auto_step` 执行语义或兼容参数。
5. streaming 结构化 draft 主链通过独立一轮双轨验证后，仓库不再生产或解析 `action-draft` fence。
6. proposal response 的 action payload 只以 `agent_output.actions` 表达；envelope/status/correlation 字段保留，`/api/state.actions` 继续表达 board truth。
7. `_append_actions` 等死代码和重复 read-model/compatibility wrapper 已删除，API/MCP/React/TUI 对 owner/status/Gate 的解释来自同一 application projection。
8. Python 全量测试、frontend build/e2e、TUI build/test、wheel smoke 和安全边界扫描通过；SPEC/PLAYBOOK/REFACTORING/README/CLI help 口径一致。
