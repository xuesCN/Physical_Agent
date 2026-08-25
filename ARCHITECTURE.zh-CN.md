# Physical Agent · 架构与设计说明

> 安全的物理世界 agent 运行时：**认知侧只提案，watch 唯一执行，SafetyGate 执行前校验。**
> 本文围绕仓库里的两张架构图展开，介绍设计思路、梳理模块、并如实汇总未完成事项。
> 更细的规范见 `docs/SPEC.zh-CN.md`（目标与账本）、`docs/architecture-101.zh-CN.md`（新人向）、`AGENTS.md`（贡献守则）。

---

## 配套两张图（建议对照阅读）

这两张 Excalidraw 图互补——一张回答「系统由哪些层组成」，一张回答「一次请求怎么流动、为什么要这么分」。打开方式：[excalidraw.com](https://excalidraw.com) → 左上 **Open** → 选文件。

| 图 | 文件 | 视角 | 看什么 |
| --- | --- | --- | --- |
| 图一 · 分层数据流全景 | [`docs/architecture.excalidraw`](docs/architecture.excalidraw) | **纵向分层** | 入口层 → API → 认知层 → 应用层(可信) → 状态层(SQLite) → 执行层(watch) → 驱动层 → 硬件(ESP32→CAN→电机)；蓝=提案下行 / 绿=反馈上行 / 橙=安全规则与 LLM 往返 |
| 图二 · 黑板模型工作流 | [`agent工作流-黑板模型.excalidraw`](agent工作流-黑板模型.excalidraw) | **以黑板为中枢** | 认知侧「只写」→ SQLite 黑板(含看板式动作板：待处理/已占用/已完成/已取消) → 执行侧「只读+执行」；编号 ①–⑦ 走完一次提案到执行；SAFETY.md 双层(软层进 prompt / 硬层被闸门强制) |

一句话：**图一是「系统的解剖」，图二是「数据的流动」。** 两张图共同的红线是——`driver.execute` 全仓唯一调用点，Gate 先于执行、不可绕过。

---

## 一、这是什么，为什么这么设计

这是一个**物理世界 agent 运行时**：用户用自然语言下指令，LLM 规划动作，动作经安全校验后由真实硬件（机械臂、小车、ESP32 板子）执行。

整个架构只回答一个第一性问题：**LLM 会犯错、会被 prompt 注入骗，但电机转过去了没有 Ctrl+Z——怎么办？**

答案是一条不可协商的管线，也是全仓的两条「宪法」（`SPEC.zh-CN.md` §0.1，修改视同修宪）：

1. **执行权唯一**：`driver.execute` 只允许出现在 watch 执行循环的调用栈里。一切提案/请求侧路径（HTTP 处理器、LLM 调用链、CLI、MCP 工具）不加载 driver、不调用执行。
2. **执行前校验不可绕过**：任何作用于物理世界的动作，执行前必过 SafetyGate；安全规则以 `SAFETY.md` 文件为真源，提案侧没有修改它的代码路径。

这两条不是写在文档里祈祷大家遵守——`tests/test_safety_boundaries.py` 用「炸药桩」强制：把 watch 与 driver 的 execute/heartbeat/halt 换成「一调用就爆炸」的 stub，跑完整提案流程证明请求侧碰不到它们。**文档会过期，测试不会。**

---

## 二、核心设计思路

**信任分层：不可信 → 编译 → 事实 → 执行。**
LLM 输出的动作意图一律当「脏数据」。可信编译器（PlanCompiler）为每个物理动作重建一张任务图，强挂一个 watch 拥有的、强制的安全校验节点；模型即使伪造「已审批」字段，也会被可信的 capability 事实剥掉。思路借鉴编译器/验证器：**不信输入，重建输出。**

**提案与执行分离（黑板模型）。**
认知侧和执行侧**从不直接互相调用**，只通过一块共享的 SQLite 状态（黑板）读写。认知侧只往黑板写「提案」，执行侧（watch）只从黑板读、执行、再把结果写回。这块黑板就是「想」和「做」能彻底解耦的物理原因（见图二）。其中的**动作板是看板式的**——待处理 / 已占用 / 已完成 / 已取消 四列，worker 轮询 + 原子领取。这套机制在工业界很常见：等价于「数据库支撑的工作队列 + 原子 claim」（对标 Oban / Solid Queue / `SELECT … FOR UPDATE SKIP LOCKED`），而「声明意图 + 独立循环执行结果回写」的形态又类似 Kubernetes 的 reconcile loop（etcd=黑板、controller=watch）。

**单写者 + 原子领取。**
watch 是唯一执行者，领取动作用 SQLite `BEGIN IMMEDIATE` 事务把「选一个 ready + 标记已占用」一步做完，杜绝两个执行者抢同一个（TOCTOU）；配租约（lease）+ 心跳 + 看门狗，连续失败自动停机，宁停不乱动。

**安全规则放文件，不放库。**
提案侧天然有数据库写权限（要写动作、聊天、记忆）。规则若在库里，一次注入就可能改掉它；放 `SAFETY.md` 文件则「提案侧改安全规则」这条路**物理上不存在**，还进 git 有 diff/blame。文件双重身份：既进 prompt（软层，让模型知情拒绝），又被 Gate 强制（硬层，不听也拦）。

**读模型（output_projection）。**
「当前任务图状态」从动作板 + feedback **现算**、不落盘，所有界面共用这一份解释（≈ Redux selector），避免同一份数据出现多种互相打架的解释。

**结构化输出编排。**
认知侧对 LLM 的调用统一收敛到一个 OpenAI SDK 封装：强制结构化输出（非流式用 strict `json_schema`，流式用 `json_object` + 本地 JSON Schema 校验），带「strict → json_object → 纯文本」降级链、reasoning 回退、错误归一化、key 脱敏与本地 trace（详见 `llm/openai_compatible.py`）。

**自主档位。** 同一条提案管线分四档人参与度：档0 手动表单 · 档1 Chat 起草→人批 · 档2 Task 一次规划 · **档3 闭环自主（未建）**。授权只改变「要不要停下等人」，永远不改变「要不要校验」。

---

## 三、模块梳理

按信任流向从「不可信」到「执行」排列：

| 目录 / 文件 | 层 | 职责 | 关键点 |
| --- | --- | --- | --- |
| `protocol/` | 契约 | pydantic 数据模型：Action、AgentOutput、ChatMessage 等，是全仓的「types.ts 真源」 | 还含上下文压缩(`chat_summary`)、记忆(`memory`)、确定性检索(`retrieval`)、期望(`expectations`)、安全检查规格 |
| `agent/` | 认知（不可信） | 产出动作意图：`ChatRuntime`(chat 主入口，流式 respond_stream)、`planner`(规则/LLM 双 planner)、`context_builder`(按预算裁剪+摘要注入)、`tool_loop`(proposal-only 工具循环) | 最大但最外围；产出永远视为脏数据 |
| `llm/` | 认知 | OpenAI SDK 封装 `openai_compatible.py` | chat/responses 双模式、结构化输出+降级链、reasoning、流式+abort、脱敏、trace |
| `application/` | 可信编译（细腰） | `ProposalService`(唯一动作写入口) → `PlanCompiler`(唯一信任边界) → `output_projection`(唯一状态解释权) | 全仓最该精读的一层；四入口都收敛到这里 |
| `state/` | 状态（黑板） | `sqlite.py` 唯一后端(WAL/原子动作/lease/审计)；SAFETY/LOG 以文件 sidecar 为真源 | 动作板 + feedback + chat + memory + leases；`BEGIN IMMEDIATE` 原子 claim |
| `watch/` | 执行（唯一动手） | `runtime.py` tick 循环 + `safety.py` 的 `SafetyGate`(执行前 10 项检查) | 全仓唯一 `driver.execute` 调用点；lease/心跳/看门狗/超时保护 |
| `drivers/` | 驱动 | `PhysicalDriver` 契约(connect/observe/execute/capabilities/health/heartbeat/halt) + transport(WS/串口/loopback) | mock_arm/mock_rover、xiaozhi_mcp；driver 只返回结果，**不碰黑板**，写库归 watch |
| `api/` | 入口 | FastAPI：proposal-only REST + chat stream/abort + SSE + `watch_service`(opt-in 常驻 watch) | React/TUI 的服务端 |
| `mcp/` | 入口 | MCP facade：submit_task/propose_action/get_state/list_robots（提案专用） | 把本系统暴露成工具给外部 agent |
| `cli.py` | 入口 | typer 命令行：init/setup/doctor/api/watch/run/chat/inspect… | CLI/MCP 在进程内直调 ProposalService |
| `frontend/` | 界面 | React + AntD 仪表盘(9 页面)：SSE 流式聊天、动作板、世界、硬件、记忆、安全 | 懒加载分包、viewmodels 读模型 |
| `tui/` | 界面 | Ink 终端 UI（纯 API 客户端，零核心改动） | 第五入口 |

五个入口（React / TUI / CLI / MCP / API）是同一条提案管线的不同「皮肤」：React/TUI 走 HTTP/SSE，CLI/MCP 在进程内直调。

---

## 四、一次请求的生命周期（对照图二）

1. **组装上下文**：从黑板读齐能力、世界状态、动作反馈、安全规则、记忆，拼成 LLM 上下文；对话过长滚动摘要。
2. **结构化提案**：调 OpenAI SDK，强制结构化输出，产出「一段人读回复 + 一串动作意图」（不可信）。流式一边生成一边把回复增量推到前端。
3. **信任编译**：动作意图当脏数据，重编译成任务图，每个物理动作强挂「执行前安全检查」节点、危险的加「人工批准」节点。
4. **写入黑板**：提案进动作板「待处理」列排队。认知侧到此结束——它只会写板，碰不到硬件。
5. **原子领取**：watch 循环（独立、与聊天解耦）从板上原子领取一个 ready 动作（待处理→已占用）。
6. **过闸**：SafetyGate 跑 10 项检查（参数 schema / 数值物理限位 / 机器在线 / 依赖完成 / 档位 / 批准…），任一不过直接拒、不执行。
7. **执行 + 回写**：全过才调 `driver.execute`（唯一调用点、带超时保护），driver 只返回结果；watch 把结果写回黑板（反馈日志 + 完成/取消 + 刷新世界），若声明了预期再做**确定性比对**，最后回灌下一轮上下文形成闭环。

---

## 五、未完成事项 / 已知边界

> 权威账本见 `SPEC.zh-CN.md` §4；下面按「对上真机的影响」排序，如实标注。

### 5.1 硬件连接协议未明确（重点）

现状：**传输层**（WebSocket / 串口 / loopback）已就绪，`PhysicalDriver` 契约已定，mock 驱动（mock_arm / mock_rover）和一个通用 MCP 设备驱动（xiaozhi_mcp）能跑。但图一里 `ESP32 → CAN → 电机` 这条**真实电机/舵机的控制协议层还没落地**——即「能把字节发到设备」有了，「标准化的机器人动作 ↔ 硬件指令语义」这一层没定。相关条目 F5.1（原计划接 LeRobot motors）在 R0-R8 期间**冻结**，收口后按实机需求重启。

影响：目前只能对接 mock 与通用 MCP 设备；接一台具体的真实机械臂，还需要先补这层协议。

### 5.2 缺少实机测试（重点）

现状：测试数量可观（数百用例，含安全边界「炸药桩」、backend 矩阵、传输、超时回归、API、前端 e2e），但**全部跑在 mock / 仿真 / monkeypatch 上**（mock_arm/rover、loopback transport）。`docs/hardware-bringup-checklist.zh-CN.md` 是实机上电手册，但**没有真实硬件端到端的验证记录**。

影响：安全边界、状态一致性在软件层被严格证明了，但「LLM → 提案 → Gate → 真电机」这条链没在真实硬件上跑通过。这是接真机前的头号风险点。

### 5.3 其他已知边界（如实列出）

- **认知侧偏单薄**：默认是单次结构化提案（模型提案前看不到状态、不迭代自纠）。多步工具循环 `tool_loop` 存在但非默认、放行工具少（submit_task/propose_action/get_state）；**档3 闭环自主未建**。加厚的最小杠杆是把 tool_loop 设默认 + 补只读/自省工具（如「干跑 SafetyGate」）。
- **仿真 Twin 未建**：F6（Demo Twin + BYO Simulator）冻结，暂无可视化仿真环境替代真机做回归。
- **持久化任务状态未做**：VNext-3/4（跨重启的持久化 task graph、Run/Turn/Event 账本、registry/read-model）冻结；当前 Action Board + output_projection 作为运行事实与 current 读模型，不是持久化 obligation engine。
- **观察侧欠账**：W4/W5（并行 execute、observed_at 时间戳）未做。
- **观测平台未接**：Langfuse 等未接，靠本地 JSONL trace 兜底（F0 量级下够用）。
- **检索/摄入**：向量 RAG 未做（用确定性关键词检索，默认关闭）；PDF 摄入暂拒绝。
- **工程基建**：无 CI，目前以本地门禁为主。

---

## 六、怎么继续读

| 想了解 | 去看 |
| --- | --- |
| 新人快速上手（前端视角类比） | `docs/architecture-101.zh-CN.md` |
| 目标、安全边界、待办账本 | `docs/SPEC.zh-CN.md`（§0 宪法 / §4 backlog） |
| 每个待办的实现思路与验收 | `docs/PLAYBOOK.zh-CN.md` |
| 重构历史与决策链 | `docs/REFACTORING.zh-CN.md` |
| agent / 人的贡献守则 | `AGENTS.md`（根目录） |
| 子系统现状快照 | `docs/system-summary.zh-CN.md` |

---

*本文口径对照 SPEC（更新至 2026-07-21）与两张架构图核查。未完成事项以 `SPEC.zh-CN.md` §4 活账本为准，过时后按本结构重扫即可。*
