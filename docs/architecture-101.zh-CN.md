# Architecture 101：写给第一次看这个仓库的人

> 面向对象：聪明但对本仓库零上下文的开发者（比如实习生，比如三个月后的你自己）。
> 前置假设：会 React/TypeScript，Python 只需要能看懂。每个后端概念都配前端类比。
> 口径：R8/R8.1 收口后的代码现状（2026-07-17，二次重构已全量完成）。配图见 `docs/architecture.excalidraw`（excalidraw.com → Open 打开）。
> 更深的规范文档：`SPEC.zh-CN.md`（目标与账本）、`AGENTS.md`（贡献守则）、`REFACTORING.zh-CN.md`（历史）。

## 0. 三十秒版本

这是一个**物理世界 agent 运行时**：用户通过聊天/任务让 LLM 规划动作，动作经过安全校验后由真实硬件（机械臂、小车、ESP32 板子）执行。

整个架构只回答一个问题：**LLM 会犯错、会被骗，但电机转了就是转了，没有 Ctrl+Z——怎么办？**

答案是一条不可协商的管线：

```
不可信的 LLM 输出 → 可信编译器加上强制安全义务 → 存进数据库排队
→ 唯一的执行循环逐个领取 → 执行前校验(SafetyGate) → 硬件
```

LLM 永远只能"建议"，永远不能"动手"。动手的只有一个叫 watch 的循环，而且它动手前必须过闸。

## 1. 代码地图（先知道东西在哪）

```
physical_agent/
├── protocol/      1625 行  数据契约层：Action、AgentOutput 等 pydantic 模型
│                          （≈ 你前端 types.ts 的 Python 真源版）
├── agent/         6097 行  认知层：ChatRuntime、planner、context_builder
│                          （产出"不可信"的动作意图，最大但最外围）
├── application/   1205 行  可信编译层：ProposalService、PlanCompiler、
│                          output_projection（全仓细腰，最该精读）
├── state/         2908 行  状态层：SQLite 动作板/feedback/lease + SAFETY 文件
├── watch/         1620 行  执行层：唯一有权调 driver.execute 的循环 + SafetyGate
├── api/           2320 行  FastAPI HTTP/SSE（React 和 TUI 的服务端）
├── drivers/       2952 行  硬件适配：driver 契约 + WebSocket/串口 transport
├── mcp/            225 行  MCP 入口（把本系统暴露成 MCP 工具）
└── cli.py          671 行  typer 命令行

frontend/  React+AntD 仪表盘        tui/  Ink 终端界面   ← 你已经熟的部分
tests/     48 文件 ~439 个测试函数（全量 462 passed）← 架构决策的"可执行说明书"
```

五个入口（React / TUI / CLI / MCP / API）全是同一条提案管线的不同皮肤。React 和 TUI 走 HTTP/SSE；CLI 和 MCP 在进程内直接调用 ProposalService。

## 2. 涉及的 agent 概念（词汇表）

| 概念 | 在本仓库的含义 | 前端类比 |
| --- | --- | --- |
| **raw decision（不可信输出）** | LLM 返回的 JSON（回复文本 + 动作意图）。永远视为脏数据 | 用户表单输入——渲染前必须校验 |
| **proposal（提案）** | 动作进入系统的唯一方式：先排队，不直接执行 | PR 流程——提交≠合并 |
| **Action / Capability** | 动作意图 / 机器人声明的能力（含参数 schema、边界、是否需审批） | 函数调用 / 带类型签名的 API 定义 |
| **AgentOutput（安全义务图）** | 可信编译器产出的任务 DAG：每个物理动作绑一个强制的 Gate 任务，可选审批和验证任务 | 编译产物——源码（LLM 输出）没资格直接上线 |
| **SafetyGateTask** | watch 拥有的校验义务。模型无法创建/完成/绕过它 | 你没法在前端把服务端校验设成"已通过" |
| **SafetyGate** | 执行前的实际校验：schema、数值边界、能力/机器人存在性、SAFETY.md 规则、依赖完成 | 服务端表单校验（前端校验只是体验，服务端才是权威） |
| **watch 循环** | 唯一执行者。每 tick：领动作 → 过闸 → 执行 → 写反馈 | 独立的 worker 进程消费队列 |
| **自主档位** | 同一管线的四档人参与度：档0 手动表单 / 档1 聊天起草→人批 / 档2 任务一次规划 / 档3 闭环自主（未建） | Copilot 的"建议→自动补全→agent 模式"梯度 |
| **requires_approval / 审批** | 授权决定"要不要停下来等人"，永远不改变"要不要校验" | 需要 code review 的分支 vs 可直推的分支——但 CI 都得跑 |
| **feedback（运行账本）** | 每个动作的 Gate 决策、执行结果、期望比对，原子追加 | 不可变的事件日志（Redux DevTools 的 action 历史） |
| **expectation check（F4 闭环）** | 提案时声明预期 → 执行后**确定性比对**（不用 LLM 当裁判）→ 结果回灌下轮上下文 | 断言测试，不是"再问一遍 AI 对不对" |
| **output_projection（读模型）** | 从动作板+feedback 现算"当前任务图状态"，全部界面共用这一份解释 | Redux selector / useMemo——派生状态不入库 |
| **source of truth（真源）** | 每类数据唯一权威归属：运行事实=SQLite；安全规则=SAFETY.md 文件；当前视图=不落盘现算 | Redux 单一数据源原则 |
| **context engineering** | `context_builder` 按预算裁剪 SAFETY/world/feedback/记忆注入 prompt，超限自动摘要 | 就是 Anthropic 那篇 effective context engineering 的自研实现 |
| **lease / 心跳 / 看门狗** | 执行协调：唯一执行者租约、驱动心跳、连续失败自动停机 | 分布式锁 + 健康检查，但目标是"宁停不乱动" |
| **UNTRUSTED 标记** | 用户上传的文件内容注入任何 LLM 上下文时永远带不可信标签 | `dangerouslySetInnerHTML` 前的 sanitize 意识 |
| **MCP** | Model Context Protocol。本仓库两头都沾：`mcp/` 把系统暴露成工具给外部 agent；`xiaozhi_mcp` driver 把 MCP 设备当硬件 | 一种给 AI 用的标准化 API 协议 |
| **transport / driver** | transport 管字节怎么到设备（WS/串口）；driver 管语义（这个设备有什么能力、动作怎么翻译） | fetch 层 / API client 层的分离 |

## 3. 架构为什么长这样（设计原因）

### 3.1 一切从威胁模型出发

普通软件的 bug 可以回滚，物理动作不能。所以本仓库的第一性问题不是"怎么让 agent 更聪明"，而是"**聪明的 agent 犯错时，最坏会发生什么**"。由此推出两条"宪法"（`SPEC.zh-CN.md` §0.1，修改视同修宪）：

1. **执行权唯一**：`driver.execute` 只允许出现在 watch 循环的调用栈里。全仓生产代码它只有一个调用点（`watch/runtime.py`）。HTTP 处理器、LLM 调用链、CLI、MCP 工具——这些"提案侧"路径物理上不加载 driver。
2. **执行前校验不可绕过**：任何物理动作执行前必须过 SafetyGate；安全规则以 SAFETY.md 文件为真源，提案侧不存在写它的代码路径。

注意这两条不是写在文档里祈祷大家遵守——`tests/test_safety_boundaries.py` 用"炸药桩"强制：把 WatchRuntime 和 driver 的 execute/heartbeat/halt 换成一调用就爆炸的 stub，然后跑完整提案流程，证明请求侧碰不到它们。**文档会过期，测试不会。**

### 3.2 信任分层：不可信 → 编译 → 事实 → 执行

LLM 输出的动作意图要经过一次"可信编译"（PlanCompiler）：给每个物理动作注入强制的、watch 拥有的 SafetyGateTask；模型如果伪造"已审批"字段，编译器用可信的 capability 事实直接剥掉（有专项测试）。这借鉴的是编译器/验证器的思路：**不信输入，重建输出**。

### 3.3 为什么是 SQLite + 轮询，而不是消息队列 + 事件驱动

单机、单写者（watch）、需要原子领取——SQLite 的 `BEGIN IMMEDIATE` 事务恰好够用，且是 Python 标准库零依赖。watch 用 tick 轮询而非事件驱动是**刻意的**：每个 tick 天然融合租约复查、心跳、看门狗计数，执行时序确定、可审计。事件驱动执行器会让"执行权唯一"的验证复杂一个量级，而真正需要低延迟的场景（高频遥操作）在规范里走的是另一条预注册例外通道，不挤这个循环。

### 3.4 为什么安全规则放 Markdown 文件不放库

提案侧天然拥有数据库写路径（要写动作、聊天、记忆）。规则若在库里，一次 prompt 注入就可能改掉它。放文件则"提案侧改安全规则"这条路**物理上不存在**——不是有权限被拦，是根本没有这条代码路径。附赠：文件进 git，规则变更有 diff、有 blame、可回滚。`/etc/sudoers`、GitOps 的 YAML 仓库、你正在看的 CLAUDE.md 都是同一思路。SAFETY.md 还有双重身份：既进 prompt（软层，让模型知情拒绝）又被 Gate 强制（硬层，不听也拦）。

### 3.5 为什么应用层那么薄（1205 行）

它是全仓的"细腰"：四个入口全部收敛到 ProposalService（唯一动作写入口）→ PlanCompiler（唯一信任边界）→ output_projection（唯一状态解释权）。细腰就该薄——像 TCP/IP 的 IP 层。审批/重置等用例暂在 API 层直连 state，是已知的待收敛项，不是设计意图。

### 3.6 为什么刚做完一轮"减法"（R0-R8，即二次重构）

功能长出来的过程中积累了重复面：两套 GUI、新旧两种状态后端、聊天里文本协议和结构化协议双轨、响应里同一份动作数据出现在三个字段。R0-R8 从 07-10 立规格到 07-16 全量收口（07-17 又做了 R8.1 review 加固，独立终审 Critical=0），按原子门禁逐个退役：先审计 → 补齐替代 → 独立验证（真实浏览器 e2e + CI）→ 才删除 → 留救援路径。这叫 strangler fig（绞杀者无花果）模式：新枝长好并验证后，老干才被移除。**删除是有证据链的工程行为，不是"应该没人用了吧"。**

## 4. 需要知道哪些知识（按你的起点标注）

已经会的（跳过）：React/TS、SSE 消费、npm 生态、Ink。

**Python 侧（看懂即可，不用精通）**

- pydantic：就是 Python 版 zod——schema 校验 + 类型。看懂 `protocol/agent_output.py` 需要的全部知识 ≈ TS interface + zod.parse
- asyncio：`async/await` 语法和 JS 几乎一样；差异是 Python 事件循环不自动启动、阻塞调用会卡死整个循环（这就是为什么仓库有 W5 纪律："driver 里的阻塞 I/O 必须带超时或丢进 `asyncio.to_thread`"）
- FastAPI：Express + 自动 OpenAPI；typer：Commander.js
- 学到什么程度：能读 `application/` 三个文件不查语法，就够了

**SQLite / 并发（重点补，约半天）**

- 事务与 `BEGIN IMMEDIATE`：为什么"读一下再写"会撞车（TOCTOU），为什么领取动作要在一个事务里完成
- 概念词：原子性、租约（lease）、幂等。不需要会调优，需要会解释"为什么 claim 是原子的"

**架构概念（各花 20 分钟搜科普）**

- SSOT（单一事实来源）、CQRS-lite/读模型、strangler fig 重构、prompt injection、human-in-the-loop
- 你其实都间接会：Redux 单一数据源=SSOT，selector=读模型

**硬件侧（科普级即可）**

- 见 `docs/brief-hardware-connectivity-review.zh-CN.md`。一句话版：板子（ESP32）自带 WiFi，跑 WebSocket 服务；agent 连 WiFi 发高层指令；CAN 总线封在固件里，电脑侧永远看不见

## 5. 和常见做法有什么不一样（本仓库的"反常识"清单）

| # | 常见 agent 项目做法 | 本仓库做法 | 为什么 |
| --- | --- | --- | --- |
| 1 | tool call 直接执行（LangChain/AutoGPT 式：模型调 `move_arm()` 就真的动了） | 工具白名单只有提案类操作；执行在另一个循环里异步发生 | 物理世界没有 Ctrl+Z |
| 2 | 安全靠 prompt："请务必遵守以下规则" | prompt 是软层，SafetyGate 代码强制是硬层；规则文件模型摸不到 | 软层可被注入绕过，硬层不行 |
| 3 | 信任模型输出的 JSON，直接入库执行 | raw decision 经可信编译器重建；伪造的审批/状态被剥掉 | 编译器不信源码，验证器不信输入 |
| 4 | 状态随手写：agent 自由读写自己的记忆和任务 | 写路径唯一（ProposalService）、原子 batch、真源分配明确 | 并发踩踏和"谁改的"问题在物理系统里是安全问题 |
| 5 | 框架堆叠：LangChain + 向量库 + 消息队列 + Redis 起手 | 标准库偏执：sqlite3、自研 WebSocket、自研轮询；向量检索设计好了但主动延后 | 每个依赖都是审计面；"语料够了再上"|
| 6 | 界面各自拼状态（前端自己算"这个任务成没成功"） | 服务端 projection 是唯一解释权，前端/TUI 禁止二次推断（R2.1 教训：两端推断不一致出过安全级 bug） | 事实的解释权只能有一处 |
| 7 | 文档滞后于代码，重构靠记忆 | spec-coding：SPEC 矩阵是活账本，每轮开工读规范、收工回写；agent 贡献者也受 AGENTS.md 约束 | 本项目大量代码由 AI agent 编写，纪律必须机器可执行 |
| 8 | 重构=大爆炸重写 | strangler：补齐→双轨验证→有证据才删→留救援路径（连退役的 Markdown 后端都留了历史 commit 救援脚本并真实测过） | 删除是工程行为不是赌博 |
| 9 | 闭环靠"让 LLM 评价自己干得怎么样" | F4：提案时声明预期，执行后确定性比对，LLM 不当裁判 | 裁判和运动员不能是同一个不可信模型 |
| 10 | 观测=接个 LangSmith/Langfuse | 本地 JSONL trace，量级几十次调用不上平台 | 工具跟着量级走，不跟着潮流走 |

读懂这张表的每一行"为什么"，你对这个仓库的掌控度就超过 90% 的旁观者了。

## 6. 建议的上手路径（一周版）

1. **第 1-2 天**：读 `protocol/agent_output.py`（304 行，你写过它的 TS 版 type guard）→ `application/` 三件套（1200 行核心）。然后做"追子弹"练习：从 ChatPanel 的 Add to Actions 按钮出发，跨过 HTTP 追到 ProposalService → SQLite → watch claim → Gate → mock 执行 → feedback 回到 Events 面板
2. **第 3 天**：读 `watch/safety.py` + `watch/runtime.py` 的 step 循环（230-350 行区间）；把 `test_safety_boundaries.py`、`test_plan_compiler.py`、`test_output_projection.py` 当规格书读——测试名就是架构决策清单
3. **第 4 天**：跑起来看现场：`physical-agent api --watch` + Dashboard 提交任务，用 `physical-agent export-audit` 或 sqlite3 直接看 `state.db` 里 action 的状态翻转
4. **之后按需**：改 streaming 才看 `chat_runtime.py`（1776 行）；接硬件才看 `drivers/`（配合硬件 brief 和 `scripts/ws_connection_smoke.py`）

避坑：`docs/current-architecture-audit.md`（2026-07-11 口径）和 `system-summary.zh-CN.md`（2026-07-05 口径）是刻意保留的历史阶段快照——读演进历史可以，**别当现状读**；现状以 `SPEC.zh-CN.md` §4 矩阵和本文为准。

---

*本文档基于 2026-07-17 对代码的逐文件核查写成；行数、调用点等数字均为实测。发现与代码不符时，以代码为准并请顺手更新本文。*
