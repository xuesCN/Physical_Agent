# Prompt Engineering 系统指南

> 面向 agent 开发者的实操版本，不是 ChatGPT 用户技巧集。
> 整理日期：2026-08-12

---

## 0. 先划清概念边界

这个领域最大的混乱来自术语。三层从内到外：

| 层 | 管什么 | 典型产物 | 能不能测 |
| --- | --- | --- | --- |
| **Prompt Engineering**（狭义） | 单次调用内，指令怎么组织 | system prompt 文本、few-shot 示例、输出格式约束 | 能（对同一批输入比较输出） |
| **Context Engineering** | 单次调用时，模型手里有什么 | context builder、token 预算、检索、摘要、记忆注入 | 能（golden file 锁组装结果） |
| **编排 / Agent Architecture** | 多次调用之间怎么串 | prompt chain、路由、工具循环、子 agent 分工 | 能（端到端任务成功率） |

**边界争议**：prompt 编排（chaining）两边都认——Anthropic 官方 prompt engineering 文档里有 "Chain complex prompts" 一章，但 2026 的行业话语更倾向把它归到上下文/架构层。

**实用建议**：对外表述时别用「prompt engineering」这个总标签，用具体机制名。前者不可证伪，后者可以指到文件。

---

## 1. 权威资料清单（按可信度排序）

### 一手官方文档（必读）

| 来源 | 地址 | 特点 |
| --- | --- | --- |
| Anthropic Prompt Engineering | `docs.claude.com/en/docs/build-with-claude/prompt-engineering/overview` | 结构最清晰，按技法分章，每章有 before/after 对照。**首选** |
| Anthropic Claude Code Best Practices | Anthropic 官方 blog | 针对编码 agent 的上下文组织 |
| OpenAI GPT-4.1 Prompting Guide | OpenAI 官方（2025-04） | 基于内部大规模测试，指令遵循 / 长上下文 / agent 工作流三块最有价值 |
| Google Prompt Engineering Whitepaper | Google 官方 | 明确主张**总是给 few-shot**（不推荐 zero-shot）；具体问题放数据之后 |

### 社区系统教程

| 来源 | 特点 |
| --- | --- |
| DAIR.AI Prompt Engineering Guide (`promptingguide.ai`) | 社区驱动，覆盖理论 + 技法 + 论文索引，含多模态、推理、agent 架构模块。**广度第一** |
| Anthropic 官方 Prompt Engineering Interactive Tutorial（GitHub） | 带练习的分章教程，适合系统过一遍 |

### 需要警惕的

- 大量「2026 终极指南」类博客是二手汇编，技法过时（比如仍在教对 reasoning 模型强行 "think step by step"）
- 任何声称「万能 prompt 模板」的，跳过

---

## 2. 核心技法（按收益从高到低）

### 2.1 清晰直接 — 收益最高，最被低估

把模型当**刚入职、没有上下文但很聪明的同事**。它不知道你的隐含约定。

三个自检问题：

1. 把这段 prompt 给一个不了解项目的人，他能照做吗？
2. 有没有「你懂的」式的省略？
3. 顺序、格式、边界条件说清楚了吗？

**反例**：`分析这份数据`
**正例**：`按 region 分组统计 revenue 的中位数与 p95，用 markdown 表格输出，缺失值单独列一行标注数量，不要给结论。`

### 2.2 Few-shot（Multishot）— 3~5 个示例

Google 白皮书立场明确：**不推荐 zero-shot，总是给示例**。

关键不在数量，在**示例要覆盖边界情况**：

- 正常情况 ×1~2
- 边界 / 异常 ×1~2（空输入、冲突信息、超范围请求）
- 你不希望的行为，如果有必要，用反例明确标注

示例比任何形容词都有效。与其写「回复要简洁专业」，不如给两条你认可的回复。

### 2.3 Chain of Thought — 但要看模型

- **非 reasoning 模型**：让它在 `<thinking>` / `<scratchpad>` 里先推理再给结论，显著提升复杂任务准确率；需要时在后处理里剥掉思考段
- **reasoning 模型**：模型自带思考过程，**再强行加 "think step by step" 往往无益甚至有害**。改为描述「思考时应该考虑哪些维度」，而不是命令它思考

在 few-shot 示例里用 `<thinking>` 展示推理**模式**，模型会泛化这个风格。

### 2.4 XML 标签结构化

Claude 系列被专门训练识别层级化 XML 结构。

```xml
<instructions>...</instructions>
<context>...</context>
<examples>...</examples>
<constraints>...</constraints>
```

**没有「正确」的标签名**——用有语义的就行。核心价值是防止模型把指令、示例、数据混为一谈。长 prompt 尤其必要。

### 2.5 System Prompt / 角色设定

system prompt 放**稳定的、跨请求不变的**东西：角色、能力边界、输出契约、禁止事项。
user message 放**每次都变的**东西：具体任务、当前数据。

这个划分不只是整洁问题——**prompt caching 按前缀命中**，稳定内容前置能显著降本降延迟。

### 2.6 Prefill（预填响应）

预先填入模型回复的开头，强约束输出格式：

- 预填 `{` → 强制 JSON 开头，跳过寒暄
- 预填 `<thinking>` → 强制先推理
- 预填角色名 → 锁定人设

轻量但极有效，尤其在需要严格格式时。

### 2.7 Prompt Chaining（编排）

复杂任务拆成串联的小步，每步一次调用：

```
提取 → 校验 → 转换 → 汇总
```

**收益**：每步准确率更高、失败可定位、中间结果可测。
**代价**：延迟和成本线性增加。

判据：**如果一步里模型要同时干三件不相关的事，就该拆。**

### 2.8 长上下文组织

- 长文档 / 大段数据放**前面**，具体问题放**最后**（Google 与 Anthropic 都建议）
- 多文档用 XML 标签分隔并标注来源
- 要求引用原文（`先引用支持你结论的原文片段，再回答`）能显著降低幻觉

---

## 3. Agent 场景专属（通用教程通常不讲）

这一节是做 agent 和只写 prompt 的分水岭。

### 3.1 工具描述就是 prompt

最被低估的一点：**工具的 `description` 字段是模型唯一的判断依据**。工具选错，八成是描述写得烂，不是模型笨。

工具描述要写：**做什么 + 什么时候用 + 什么时候不要用**。最后一条最常被漏掉。

```
❌ "搜索数据库"
✅ "按订单号精确查询单条订单详情。仅在用户提供了完整订单号时使用；
   模糊查询或按时间范围检索请改用 search_orders。"
```

### 3.2 输出 schema 也是 prompt

用结构化输出（`json_schema` / JSON mode）时，schema 里的字段名和 `description` 会进入模型上下文。

- 字段名写成自解释的（`refusal_reason` 而不是 `r2`）
- 每个字段给 description，说明取值约束
- **枚举优于自由文本**——能用 enum 就别让模型自由发挥

### 3.3 分层约束：软层 + 硬层

单靠 prompt 约束 agent 行为是不够的，因为 prompt 可以被注入、可以被模型忽略。正确的做法是双层：

| 层 | 手段 | 作用 |
| --- | --- | --- |
| **软层** | 规则注入 prompt | 让模型**知情地**拒绝，给出可解释的理由 |
| **硬层** | 代码侧校验闸门 | 模型不听时**强制**拦截 |

软层负责体验（拒绝得体、可解释），硬层负责安全（不可绕过）。**只有硬层，用户体验差；只有软层，等于没有。**

### 3.4 渐进式披露（Progressive Disclosure）

别把所有能力说明一次性塞进 context。分级：

1. 一句话摘要常驻（模型知道「有这个能力」）
2. 触发后才加载完整说明（模型知道「怎么用」）
3. 大块参考资料放外部，按需检索

这是 Agent Skills 规范的核心设计思想，也是长会话不爆 context 的关键。

### 3.5 上下文预算

给每类内容分配 token 预算，超限自动降级：

```
完整内容 → 结构化摘要 → 计数统计 → 省略并标注
```

关键是**降级要显式告知模型**（`[已省略 47 条历史反馈]`），否则模型会误以为那些事没发生过。

---

## 4. 怎么把它从玄学变成工程

这一节决定了你能不能在面试里守住这个技能点。

### 4.1 建立可证伪的判据

**没有评估的 prompt 工作 = 玄学。** 最低要求：一批固定输入 + 明确的 pass/fail 判据。

分三档：

| 档 | 做法 | 成本 |
| --- | --- | --- |
| 最低 | 10~20 条固定测试输入，人工判定通过率，改动前后对比 | 半天 |
| 中等 | Golden file：锁定 context 组装结果，改动导致 diff 就报警 | 1~2 天 |
| 完整 | 分类判据自动打分 + 调用 trace 留痕 + 回归门禁进 CI | 一周 |

### 4.2 Golden File 的价值

Golden file 测的**不是模型输出**（那个不稳定），而是**你喂进去的东西**（那个必须稳定）。

这解决了 prompt 工作最大的痛点：改了一处摘要逻辑，另一条链路的上下文悄悄变了却没人发现。

### 4.3 Trace：验证「为什么」而不只是「是不是」

记录每次调用的完整输入输出（key 脱敏后）。价值在于回答：

> 模型这次拒绝，是因为**看到了**约束还是**碰巧**？

这两者结果一样，但一个是系统生效，一个是运气。只有 trace 能区分。**这是能把「我调了 prompt」升级成「我验证了 prompt 生效路径」的唯一手段。**

### 4.4 一次只改一处

模型输出有随机性。同时改三处，效果变好了你也不知道是哪处起作用——下次遇到类似问题依然没有可复用的经验。

---

## 5. 常见误区

| 误区 | 实际情况 |
| --- | --- |
| 「模型不听话，多说几遍」 | 重复不增强约束，只稀释上下文。改成结构化约束或硬层拦截 |
| 「prompt 越长越好」 | 长 prompt 的中段最容易被忽略。信息密度比长度重要 |
| 「给 reasoning 模型加 think step by step」 | 往往无效甚至有害，它自带思考 |
| 「用威胁 / 情绪化措辞提升效果」 | 早期模型上的偶然现象，现代模型不吃这套，且损害可维护性 |
| 「prompt 调好了就一劳永逸」 | 换模型版本要重测。没有回归测试的 prompt 一定会悄悄劣化 |
| 「靠 prompt 保证安全」 | prompt 是软约束，可被注入绕过。真正的安全边界必须在代码侧 |

---

## 6. 结合本仓库的落点

现有实现对应关系：

| 技法 | 本仓库位置 |
| --- | --- |
| 上下文统一组装 + 预算 | `physical_agent/agent/context_builder.py` |
| Golden file 回归 | `tests/golden/context_builder/` |
| 输出 schema 即 prompt | `physical_agent/agent/llm_contracts.py`、`protocol/schemas.py` |
| 结构化输出 + 降级链 | `physical_agent/llm/openai_compatible.py` |
| 软层 / 硬层双层约束 | `SAFETY.md` 进 prompt（软）+ `watch/safety.py` SafetyGate（硬） |
| 调用 trace | 本地 JSONL trace（`PA_LLM_TRACE`） |
| 渐进式披露 | `physical_agent/agent/skills.py` SkillRouter + `skills/*/SKILL.md` |
| 可证伪实验 | F0 坏任务实验（SPEC §4）——trace 复核确认拒绝为知情拒绝 |

可继续加强的方向：

1. **工具描述审计**——按 §3.1 标准重写 proposal-only 工具的 description，补「什么时候不要用」
2. **扩大 F0 样本**——当前 15 条偏少，扩到 50 条并把判据自动化，就能进 CI 当回归门禁
3. **上下文降级显式化**——检查裁剪时是否都向模型标注了省略，避免模型误判「没发生过」

---

## 参考来源

- Anthropic Prompt Engineering Overview — `docs.claude.com/en/docs/build-with-claude/prompt-engineering/overview`
- Anthropic: Use XML tags to structure your prompts — Claude Docs
- Anthropic: Chain complex prompts — Claude Docs
- OpenAI GPT-4.1 Prompting Guide（2025-04）
- Google Prompt Engineering Whitepaper
- DAIR.AI Prompt Engineering Guide — `promptingguide.ai`
