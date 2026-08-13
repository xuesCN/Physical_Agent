# Brief：把 Physical Agent 以 MCP 形式接大模型（如 Claude）—— 多维评估

> 评估日期：2026-08-10
> 输入：仓库现状（`physical_agent/mcp/server.py`、`car_agent/driver.py`、SPEC §0/§4）+ 用户提供的 `AGENT_INTEGRATION.md`（car_agent Level 0 设备说明书）
> 结论性质：**架构决策建议**，不是实施计划。落地前仍需按 `AGENTS.md` 出轮次 brief。

---

## 0. 结论先行 ✅

**方向对，但你可能高估了"改造"的分量、低估了"补偿"的分量。**

三句话：

1. 🟢 **不是新功能，是补一个已经画在架构图上但只有壳的入口。** `ARCHITECTURE.zh-CN.md` §三 已经把 MCP 写成"五个入口"之一，`physical_agent/mcp/server.py` 有完整的 facade 和 `tool_specs()`，`tests/test_mcp_server.py` 有测试。缺的只是**一层真正的 MCP transport**。这把工作量从"重构"降级成"接线"。
2. 🟢 **黑板模型天生适配 MCP，而且新版 MCP 反过来更适配你。** 宪法第 1 条本来就把"MCP 工具"列在提案侧白名单里。MCP 2026-07-28 规范把协议核心改成**无状态请求/响应**——状态在你的 SQLite 黑板里、不在连接里，这正好是你的设计。
3. 🔴 **但 MCP 化解决不了你当前的头号风险，还会削弱三样东西**：SAFETY.md 的软层注入、审批的可信度、trace 的完整性。而且**它和 `drive_for` 实机验收没有任何关系**——后者才是 §4 矩阵里唯一悬着的物理风险。

**建议：做 A 档（补实第五入口），不做 B 档（MCP 取代内置认知侧）。** 理由见 §7。

---

## 1. 先拆词：三种"MCP 化"完全不同，别混谈 🧩

用前端的话说，这是三个不同层的事：

| | 叫法 | 谁是 server / 谁是 client | 类比 | 仓库现状 |
|---|---|---|---|---|
| **A** | 北向·并列入口 | **你是 server**，Claude Desktop / Claude Code 是 client | 你把 `ProposalService` 暴露成一组 API，别人的 App 来调 | ⚠️ facade 有，transport 没有 |
| **B** | 北向·取代认知侧 | 同上，但同时**退役 `agent/` + `llm/`** | 把你自己写的 BFF 删掉，让别人的前端直连 | ❌ 未做，且成本远高于 A |
| **C** | 南向·设备即 MCP | **设备是 server**，你的 driver 是 client | 你去调别人的 SDK | ✅ `drivers/xiaozhi_mcp.py` 已有 |

你问的是 A / B。**C 已经跑通了**，且和 car_agent 无关（车走的是裸 TCP+NDJSON，不是 MCP）。

下文所有"MCP 化"默认指 A，B 单独讨论。

---

## 2. 仓库现状核查（事实层）🔍

| 项目 | 状态 | 证据 |
|---|---|---|
| MCP facade 类 | ✅ 存在 | `physical_agent/mcp/server.py::PhysicalAgentMCP` |
| 提案专用工具 | ✅ 3 个 | `submit_task` / `propose_action` / `get_state`（+ `list_robots` 未进 tool_specs） |
| OpenAI 风格 tool schema | ✅ 已写 | `tool_specs()`，含 `strict: true`、`EXPECTED_JSON_SCHEMA`、`SAFETY_INTENT_JSON_SCHEMA` |
| 真正的 MCP 协议实现 | ❌ **没有** | `pyproject.toml` 无 `mcp` 依赖；`cli.py` 无 `mcp` 子命令（grep 零命中） |
| 宪法合规 | ✅ 已合规 | 类注释明确"不加载 driver、不执行"；`test_safety_boundaries` 覆盖提案侧 |
| 测试 | ✅ 有 | `tests/test_mcp_server.py` |

**一句话**：这是个"写好了 handler、没挂路由"的状态。类比：`server.py` 是你的 controller 层，缺的是 `app.listen()`。

顺带一个观察 👀：`car_agent/physical-agent.yaml` 里 `agent.planner: llm` 但 `model: fake/local`——**小车项目目前实质上没有可用的认知侧**。这反而是 MCP 化最有说服力的论据：与其为小车再配一遍 OpenAI key + 调 prompt，不如直接把黑板挂给 Claude。

---

## 3. 设备说明书带来的硬约束 —— 这条决定了 MCP 的能力上限 ⏱️

这是整份评估里**最不能妥协的一节**。

### 3.1 时间预算对不上，差一到两个数量级

| 环节 | 量级 | 来源 |
|---|---|---|
| 设备指令看门狗超时 | **800 ms** | 说明书 §4.1 |
| 实际制动时延 | 800–850 ms | 说明书 §2.3 |
| TOF 采样周期（数据最旧滞后） | 100 ms | 说明书 §2.3 |
| driver 续租间隔 | 250 ms | `car_agent/driver.py::refresh_interval_ms` |
| driver 安全覆盖窗口 | 700 ms | `WATCHDOG_COVERAGE_S = 0.8 - 0.1` |
| watch tick | 250 ms | `physical-agent.yaml` |
| **MCP(stdio) 传输本身** | **< 5 ms** | 本地进程管道 |
| **MCP + LLM 一个完整工具轮次** | **2–15 s** | 模型推理主导，非传输主导 |

结论直白：**LLM 往返比设备看门狗慢 3–20 倍。** 任何"让 Claude 实时开车"的形态在物理上就不成立——车会在模型还在思考的时候就自己刹停了。

⚠️ 这不是 MCP 的锅，是**任何**云端 LLM 的锅。你现有的内置 planner 同样不能进控制回路。所以这不构成"MCP 更差"的论据，但**必须写进文档**，否则第一个把 MCP 装进 Claude Desktop 的人一定会试图手动打方向盘。

### 3.2 为什么你现在的 `drive_for` 设计恰好让 MCP 化是安全的 ✨

这点值得单独表扬。看 `_execute_drive_for()`：

```
提案侧交出的是一个「有界动作」：{speed, duration_ms}
      ↓（跨过 SafetyGate，进入 watch）
watch 内部自己跑 250ms 循环续租看门狗，跑满 duration_ms，然后主动刹停
```

也就是说：**实时性被完整封装在 watch 进程内，提案侧只需要在秒级作出一次决策。** 认知侧再慢也不影响物理安全。

如果当初设计的是"提案侧下发 drive、提案侧负责续租"，那 MCP 化会是**灾难性**的。现在不是。这条设计恰好把 MCP 化的风险从"红线级"降到"文档级"。

### 3.3 但有两个设备事实会被 MCP 放大 🔴

| 设备事实 | 说明书 | MCP 化后的放大效应 |
|---|---|---|
| **Level 0 无本地避障兜底**，避障 100% 在 Agent 侧 | §4.5 | 你现有 `context_builder` 把 `tof_mm` / `tof_valid` 塞进 prompt 是**确定性**的；MCP 下变成"Claude 要不要调 `get_state`"——**不确定**。模型可能不看 TOF 就提 drive。 |
| **协议无任何认证**，同网段任意主机可控电机 | §4.5 | 台架网段必须隔离。若 MCP server 走 Streamable HTTP 暴露到别的机器，就多了一跳攻击面。**建议只用 stdio。** |

第一条是 §5.1 的核心，必须补偿。

---

## 4. 多维评分表 📊

基线 = 现状（内置 LLM planner + React/TUI/CLI/API）。`↑` 改善 / `=` 不变 / `↓` 劣化。

| # | 维度 | A 档（并列 MCP 入口） | B 档（MCP 取代认知侧） | 备注 |
|---|---|---|---|---|
| 1 | **认知质量** | ↑↑ | ↑↑ | 直接吃 Claude 最强模型；不用自己维护 `openai_compatible.py` 的 strict→json_object→纯文本降级链 |
| 2 | **接入门槛 / 演示力** | ↑↑ | ↑↑ | 用户不配 key、不跑前端，Claude Desktop 加一条 config 就能"跟小车对话"。对 F0 招人/demo 价值极高 |
| 3 | **安全 · 硬层（SafetyGate）** | = | = | Gate 在 watch，完全不受影响。宪法第 2 条不动 |
| 4 | **安全 · 软层（SAFETY.md 进 prompt）** | ↓ | ↓↓ | **最大损失项**，见 §5.1 |
| 5 | **审批可信度** | =（前提：不暴露 approve） | ↓↓ | 见 §5.2 |
| 6 | **实时性 / 控制回路** | = | = | 本来就不在认知侧，见 §3.2 |
| 7 | **可观测 / 审计完整性** | ↓ | ↓↓ | 见 §5.3 |
| 8 | **离线 / 内网可用性** | =（GUI 仍在） | ↓↓ | 台架实验室常隔离网；B 档等于把系统绑死在有网 + 有 Claude 订阅 |
| 9 | **供应商锁定** | =（多一个可选入口） | ↓↓ | B 档把认知侧外包给单一 host |
| 10 | **维护面 / 接口宽度** | ≈（补实已有入口，非新增） | ↑（可删 `agent/`+`llm/`） | A 档不扩张架构面——五入口的图不用改 |
| 11 | **与 SPEC 冻结纪律的关系** | 需 §4 新增条目 | **接近修宪** | 见 §7 |

**加权直觉**：A 档在 11 项里 6 项持平、3 项显著改善、2 项需补偿。B 档收益不比 A 高多少，代价却是 4 项显著劣化。

---

## 5. 会被削弱的三样东西（反方证据，重点看）🔴

### 5.1 SAFETY.md 的"软层"注入从确定变成不确定

现在的机制（`ARCHITECTURE.zh-CN.md` §二）：SAFETY.md **双重身份**——既进 prompt（软层：让模型知情拒绝），又被 Gate 强制（硬层：不听也拦）。软层由 `context_builder` **无条件注入**。

MCP 下，你只能：
- 放进 `resources` → host 读不读、什么时候读，**你说了不算**
- 放进 tool description → 每次工具列表都带上，但会被长上下文稀释
- 放进**每次工具调用的返回值** → ✅ 这是唯一确定的通道

**必须做的补偿**：把 SAFETY 摘要 + 当前 robot 的 bounds + 最近一次 `tof_mm`/`tof_valid` **强制塞进 `submit_task` / `propose_action` 的返回体**，无论调用成功还是失败。相当于把"上下文注入"改成"回执注入"。

> 前端类比：以前是全局 Provider 注入 context，现在只能靠每个 API response 带回来。能做，但要主动做，而且要写测试锁住。

### 5.2 审批绝对不能做成 MCP tool ⛔

MCP 2026-07-28 引入了 **MRTR（Multi Round-Trip Requests）**，server 可以返回 `resultType: "input_required"` 让 client 补齐输入——看起来很适合做"人工批准"。同时该版本**弃用了 sampling / roots / logging**（保留至少 12 个月兼容）。

**不要用它做物理动作审批。** 理由：

- MRTR 的 `inputResponses` 由 **host 应用**决定怎么填。你无法在协议层区分"人真的点了批准"和"模型自己填了 yes"。
- 你的 F1.3 审批流的全部价值就在于"**人**在环"。把它交给一个你不控制的 host，等于自愿放弃这个价值。
- `car_agent` 的 `drive_for` 是 `requires_approval=True`（driver 里写死的）。这是当前唯一的运动能力。审批一旦被绕过，说明书 §0 的"车轮架空"约束就失去了最后一道人工闸门。

**设计红线建议（应写进 SPEC §0.3）**：
> MCP 入口只暴露 `get_state` / `list_robots` / `submit_task` / `propose_action`。
> `approve` / `reject` / `reset` **永不**作为 MCP tool 暴露；审批只经 React / TUI。

### 5.3 观测断链

现状你有：`llm/openai_compatible.py` 的本地 JSONL trace（F0 实验的数据源）+ A1.3b 的 `thought` SSE 事件。

MCP 化后，**推理过程发生在 Claude 侧，你的 LOG/audit 只能看到"某时刻有人调了 propose_action"**。F0 的"坏任务实验"（15 条：10 完成 / 5 无提案 / 0 Gate 拦截）这类分析在 MCP 路径上做不了。

不致命（SPEC 里 F0 本来就 ⏸ 冻结），但要接受：**MCP 入口是一条观测能力较弱的通道**。补偿手段是把 `proposed_by="mcp"` 的审计做厚一点（已有 `append_log(actor="mcp")` 地基）。

---

## 6. 重构工作量拆解 🛠️

按你的轮次粒度（1 轮 ≈ 一个 SPEC 条目 + brief + 实现 + 测试 + 门禁）。

### A 档（推荐）

| 任务 | 内容 | 量级 | 轮次 |
|---|---|---|---|
| **A-1** | 加 `mcp` SDK 依赖（`[project.optional-dependencies] mcp`），把 `PhysicalAgentMCP` 包成 stdio server，加 `physical-agent mcp` CLI 子命令 | ~200–350 行，无核心改动 | **0.5–1 轮** |
| **A-2** | 工具返回体强制回灌 SAFETY 摘要 + bounds + TOF 新鲜度（§5.1 补偿），加 golden 测试锁住 | ~150 行 + 测试 | **1 轮** |
| **A-3** | 进程守卫：MCP server 进程**禁止**持 watch lease；误配时 fail-closed 报错。补双语接入文档（Claude Desktop config 示例 + "不能实时开车"的显式警告） | ~80 行 + 文档 | **0.5 轮** |
| **A-4** | 安全边界测试扩面：把 MCP 入口纳入 `test_safety_boundaries` 的"炸药桩"矩阵，证明 MCP 路径碰不到 driver | 测试为主 | **0.5 轮** |
| | **合计** | | **≈ 2.5–3 轮** |

### B 档（不推荐现在做）

在 A 档之上，额外：

| 任务 | 量级 | 轮次 |
|---|---|---|
| 退役 `agent/`（15 个模块）+ `llm/`（3 个模块） | 大 | 3–5 轮 |
| 前端 chat 页（8 页导航的主入口）改造或退役 | 大，牵动 C6/C7 刚收口的成果 | 2–3 轮 |
| TUI transcript / thought 事件相应退役 | 中，牵动刚验收的 T4.x | 1–2 轮 |
| SPEC 决策记录（改动接近宪法层的信任模型） | — | — |
| | **额外合计** | **≈ 6–10 轮** |

⚠️ B 档会**直接冲销** C5/C6/C6.1/C7 和 T4/T4.1/T4.2 刚刚收口的全部前端与 TUI 工作。以你 SPEC 的记录密度看，那是 2026-07 整月的产出。

---

## 7. 建议路线 & 与冻结纪律的关系 🧭

### 优先级排序（重要）

`SPEC §4` 里唯一带物理风险的悬空项是：

> **F5.0 · `drive_for` 运动未验收** —— 待轮空标定 `max_abs_speed` / `max_duration_ms` 包络。

MCP 化**不推进这一项、不降低这一项的风险、也不被这一项阻塞**。它们正交。

所以诚实的排序是：

1. 🔴 **先做**：`drive_for` 轮空台架标定与验收（唯一的物理风险出口）
2. 🟢 **再做**：A 档 MCP 接线（低风险、高演示价值，可穿插）
3. ⚪ **不做**：B 档

如果你的实际动机是"演示/招人/降低他人试用门槛"，A 档是性价比最高的一步；如果动机是"让规划更聪明"，那 A 档也够——因为 A 档已经能让 Claude 直接驱动黑板。**没有一个动机需要 B 档。**

### 与 SPEC §2 冻结的关系

- A 档**不在** §4 现有矩阵里，属新增条目 → 按 §0.3 走：读 §0 → 加 §4 一行 → 写 `PLAYBOOK` 同名条目 → 出轮次 brief。
- A 档不触碰任何冻结项（不解冻 F5.1–F5.3、F6、VNext-3/4、W4/W5/W6.2）。
- A 档不改宪法：`driver.execute` 仍只在 watch，SafetyGate 仍不可绕过，SAFETY.md 仍是文件真源。**§0.1 里"MCP 工具"本来就在提案侧列举中，等于早就预留了这个口子。**
- B 档改变的是"认知侧由谁提供"这一信任模型的基本假设 → 需要独立决策记录，量级接近修宪。

---

## 8. 需要你拍板的三个岔口 ❓

| # | 岔口 | 建议 | 影响 |
|---|---|---|---|
| 1 | **stdio 还是 Streamable HTTP？** | **stdio** | 设备协议无认证（§4.5），HTTP 会多一跳暴露面。stdio 天然限制在同一台机器，且 Claude Desktop 原生支持 |
| 2 | **`propose_action` 要不要暴露给 MCP？** | 要，但保留 | `submit_task` 是自然语言、走你的 PlanCompiler，更安全；`propose_action` 是结构化直投，绕过了 planner 的语义层（但**不绕过 Gate**）。建议两个都留，文档里推荐前者 |
| 3 | **`agent/` + `llm/` 保留还是退役？** | **保留** | 见 §6 B 档成本。保留 = MCP 是"可选的更强大脑"，退役 = MCP 是"唯一的大脑"。前者可回滚，后者不可 |

---

## 附：一句话给不看长文的人 📌

> 把 Physical Agent 做成 MCP server 接 Claude，**在架构上是免费的**（黑板模型和无状态 MCP 天生对齐，宪法早就预留了口子，代码只差一层 transport，约 2.5–3 轮）；
> **在安全上是中性的**（SafetyGate 在 watch，一步不退）；
> **代价是三个补偿动作**（SAFETY 回执注入、审批绝不外包、接受 trace 变薄）；
> **但它不解决当前唯一的物理风险**——`drive_for` 还没在轮空台架上验收过。先做那个。

---

## Sources

- [MCP Transports 规范](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [The 2026-07-28 Specification（无状态核心 / MRTR / sampling 弃用）](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- [The 2026 MCP Roadmap](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/)
