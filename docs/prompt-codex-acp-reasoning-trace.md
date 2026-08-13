# Codex 新 session 执行 prompt（ACP 概念借鉴 + 思考链暴露）

> 用法：复制下面分隔线之间的全部内容，粘贴进新开的 Codex session。

---

在 Physical_agent 仓库执行「借鉴 ACP 事件模型 + 暴露 agent 推理摘要」这一轮。

## 开工前必读（按顺序，读完再动代码）

1. `AGENTS.md` —— 本仓库 agent 执行守则，全程适用。
2. `docs/SPEC.zh-CN.md` §0 安全边界 —— 两条宪法不可破。
3. `docs/brief-acp-concepts-and-reasoning-trace.zh-CN.md` —— **本轮的完整方案，已经过讨论定稿，按它执行，不要重新设计**。
4. `docs/design/ui-redesign-spec.zh-CN.md` 的 **B 部分** —— 思考链的 UI 规格（位置、层级、文案、流式行为、TUI 对应）。**A 部分不属于本轮，不要实施**。
5. `docs/PLAYBOOK.zh-CN.md` —— 确认没有同名条目冲突。

## 本轮范围（已定，不要扩大）

只做两件事：

- 把 chat 流式输出从 `Iterator[str]` 改成带类型的 chunk（`message` / `thought`）；
- 接住已经在请求、但一直没被提取的 provider reasoning summary，并在 React / TUI 上默认折叠展示。

## 第 0 步：先写 SPEC 决策，这是硬前置

`SPEC.zh-CN.md` §4 的 VNext-4 条目包含「typed stream」且状态为冻结 ⏸。本轮字面上落在其措辞内，因此**必须先在 SPEC §4 新增一条显式决策再动代码**，内容需说明：

- 本轮只在既有 chat SSE 上新增一个事件类型，属于 UI 可观测性改进；
- **不新增任何数据库表**，推理摘要只进 chat metadata；
- **不引入 Run/Turn/Event ledger、不引入 registry/read model**，VNext-4 其余部分保持冻结；
- 重启条件与 R8 收口时定的规矩一致。

不要跳过这步直接改代码——用小改动悄悄启动冻结条目，正是 R0-R8 要治的病。

## 关键实现位点（已核实，可直接定位）

- `physical_agent/llm/openai_compatible.py:56` 已有 `reasoning_summary: "auto"`，`:934` 已把 `"summary"` 发进请求 —— 请求侧不用改。
- `_extract_responses_text()`（约 :1050）遍历 `output` 只取 `item["content"][*]["text"]`；推理项是 `type=="reasoning"` 且内容在 `item["summary"][*]["text"]`，结构不同，需要新增独立提取函数，**不要把它塞进现有函数**。
- 流式路径（约 :640）目前只处理 `response.output_text.delta`，需要追加 `response.reasoning_summary_text.delta`。
- `stream_chat_text()`（约 :210）签名 `-> Iterator[str]` 是本轮核心改动点。
- chat stream 现有 SSE 事件：`start` / `delta` / `done` / `aborted` / `error`，本轮新增 `thought`。

## UI 要点（完整规格见 design 文档 B 部分，以下为不可改动的三条）

1. 折叠行标题固定为**「模型推理摘要」**（英文 `Model reasoning summary`）。**不要用**「思考过程」「Thinking」——那会暗示这是完整且忠实的推理。
2. 展开后顶部必须有一行灰字免责说明：「由模型生成的推理摘要，仅供参考，不代表实际决策依据。动作是否放行以 SafetyGate 校验为准。」**这行不可省略**——防止 operator 因为"看起来想得很周到"而降低审批警惕。
3. 无 `thought` 事件时整行不渲染，不显示空态。推理摘要**不得**出现在 Actions 板、feedback 时间线或任何审批界面。

## 不可妥协的边界

1. `driver.execute` 只允许出现在 watch 调用栈；SafetyGate 不可绕过；SAFETY.md 保持文件真源。本轮**不碰 watch / SafetyGate / driver 任何一行**。
2. **推理摘要是不可信模型输出**：不得进入 PlanCompiler、不得影响 Gate、不得作为审批依据、不得回灌进 LLM 上下文。仅供人阅读。
3. `done` 事件的 `agent_output` / `ChatPlan` 契约**保持不变**，R5/R7 建立的结构化主链不受影响。
4. 非推理模型 / Chat Completions 模式下**静默降级**：无 `thought` 事件，正文行为与现状逐字节一致。
5. 不实现 ACP 协议本体、不新增第六入口、不展示 raw CoT（`A1.3a` 既有决定继续有效）。

## 验收（全绿才算完成）

- SPEC §4 决策条目已写入；
- 推理模型下 chat 流出现 `thought` 事件，React 与 TUI 均默认折叠可见，并标注为「模型推理摘要」而非决策依据；
- 非推理模型回归：无 `thought`，正文与现状一致；
- abort 中途：thought 与 message 一并停止，无残留持久化；
- 负用例证明推理摘要不出现在 PlanCompiler 输入、不进 Action Board / feedback；
- Python 全量 pytest、Safety smoke、frontend `tsc -b && vite build`、真实 Chromium Playwright、TUI typecheck/test/build、clean-wheel smoke 全绿；
- `git diff --check` clean。

## 收工（缺一不算完成）

1. 更新 `SPEC.zh-CN.md` §4 对应行状态；
2. `REFACTORING.zh-CN.md` §1 表格追加一行，实现要点并入 §2，新决策/教训补 §3/§4；
3. 不写独立 handoff 文档；本轮 brief（`brief-acp-concepts-and-reasoning-trace.zh-CN.md`）用完即删；
4. commit 全部改动并 push。

## 遇到分歧时

方案已定稿，如果实现中发现 brief 里的判断与代码实际不符，**先停下来说明冲突点**，不要自行改设计。特别是：如果发现 typed chunk 的改动面比预期大（比如波及 tool_loop 或 MCP），先报告再决定是否缩小范围。

---
