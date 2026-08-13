# 004：记忆分层与上下文带位硬化

状态：待开工（依赖 003 收口）
日期：2026-08-14
对应账本：`SPEC.zh-CN.md` §4 `F3.2 / 004`

## 0. 目标

把记忆从「独立注入的 top-N 列表」重构为上下文预算里的显式**带位（band）**，同时收口 B4a-c 遗留的四个契约缺陷：trust 口径倒置、`importance` 字段无写入通道、无总量预算、无失效路径。

带位划分同时为 prompt caching 提供稳定前缀边界，但本条**只落地布局与边界，不接 provider cache API**——`cache_control` 接线是布局稳定后的独立条目。

本条不追求「更聪明的记忆」。记忆的正确定位是上下文预算的一个受控输入，不是自治子系统。

## 1. 不可破坏边界

1. `driver.execute()` 仍只出现在 watch 执行调用栈。`context_builder` 保持 REFACTORING §3.15 确立的**只读边界**：不写 log/memory/action、不 import watch/driver/SafetyGate、不发 LLM 请求。
2. SAFETY 继续以文件为唯一真源。003 建立的 `HardSafetyPolicy` / `SafetyPolicySnapshot` 类型隔离不得被记忆带位削弱：**记忆内容在任何路径上都不能进入 guidance、hard rules、policy digest 或 SafetyGate**。
3. 不解冻 B4-vec。本条不引入 embedding、`sqlite-vec` 或任何向量依赖；检索保持本地确定性关键词匹配。
4. 不解冻 F0 实验、自动 replan、VNext-3/4、无人值守闭环或其他 §2 冻结项。
5. **排序硬约束**：003 收口后才开工。003 已在树上改动 `context_builder`（`SafetyGuidanceContextError`、`ContextBudget.safety_guidance_max_chars`、`guidance_json_chars` 调用），004 要改同一函数的字段顺序与预算结构，并行会在四份 context golden 上产生不可判定的冲突。

## 2. 带位契约

记忆按注入位置分三带。带位由 `kind` 与 `importance` 派生，**不是新增的存储字段**，避免制造第二套状态。

| 带位 | 判定 | 注入位置 | 失效行为 |
| --- | --- | --- | --- |
| `pinned` | `importance >= 2` 或 `kind in {constraint, preference}` | 稳定段之后、易变段之前 | 受 `memory_pinned_max_chars` 约束 |
| `episodic` | 其余有效 note | 易变段内 | 受 `memory_episodic_max_chars` 约束 |
| `archived` | 已 supersede 或超 TTL | **不注入** | 仍可被 `search-memory` 检索（可审计） |

payload 字段顺序固定为三段：

```
稳定段    context_policy · execution_contract · capabilities · safety
半稳定段  memory_pinned
易变段    world · feedback · retrieved_context · memory_episodic ·
          chat_history · running_summary · latest_user_message
```

现有单一 `memory` 字段被 `memory_pinned` / `memory_episodic` 取代。四份 context golden 必然变更，重录时必须逐字段 diff review，不接受整体覆盖。

`retrieval.enabled` 为真时，`episodic` 只经 `retrieved_context` 出现，`memory_episodic` 置空；为假时反之。**同一条 note 不得同时出现在两处**——这是当前实现已存在的重复占用，本条一并收口。

## 3. Note 写入契约

`ChatLLMResponse.memory` 由 `list[str]` 升级为结构化契约，schema 仍由 `llm_contracts.py` 单真源生成（沿用 002 口径，不手写 JSON 形状）：

```python
class LLMMemoryNote(LLMContract):
    content: NonEmptyText
    kind: Literal["fact", "constraint", "preference", "observation"] = "observation"
    importance: int = Field(default=0, ge=0, le=2)
    tags: list[str] = Field(default_factory=list, max_length=8)
    supersedes: list[str] = Field(default_factory=list, max_length=4)
```

兼容：字段接受 `list[str] | list[LLMMemoryNote]`，纯字符串归一为 `kind="observation", importance=0`。002 已把 LLM 契约设为 `extra="forbid"`，老 payload 必须显式声明兼容而非依赖宽松解析。

**注入面控制**（本条最关键的安全设计点）：`importance` 上界对 LLM 为 `2`，`3` 保留给人工与系统写入路径。理由——`importance` 现在决定条目能否进入常驻 `pinned` 带，若不设上界，模型即可把任意由用户输入提炼来的内容提升为跨轮次常驻上下文，等于把提示注入变成持久化注入。`kind="constraint"` 同理受此上界约束：它进入 pinned 带靠的是 kind 而非 importance，因此 `constraint` 与 `preference` 两个 kind **只允许人工/系统写入**，LLM 声明这两个 kind 时降级为 `fact`，并在 note 上记 `downgraded_from`。

## 4. Trust 口径

`SqliteStateStore._insert_memory_note_chunks_conn` 当前写入 `trust_level="trusted"`，与 `context_builder` 已声明的「memory notes 是 untrusted」直接矛盾。改为 `"untrusted"`，并对存量 `source_type='memory'` 的 chunk 一次性回填。

`trust_level` **保持 trusted/untrusted 两档，不扩展为三档**。早期草案曾提出 `file`/`runtime`/`derived` 三档，放弃理由：003 已经用 `HardSafetyPolicy` / `SafetyPolicySnapshot` 建立了一套 typed 信任隔离，再引入第二套信任语义会让「什么算可信」出现两个答案，而这正是 SAFETY 通道当初出问题的形态。记忆一侧只需要一个事实——**它永远不可信**。

## 5. 预算闸

`ContextBudget` 新增两项段级预算，保留既有单条截断：

| 字段 | 默认 | 作用 |
| --- | --- | --- |
| `memory_pinned_max_chars` | 4000 | pinned 段总量 |
| `memory_episodic_max_chars` | 4000 | episodic 段总量 |
| `memory_note_max_chars` | 4000（不变） | 单条截断 |

当前只有单条截断，`memory_top_n=20 × 4000` 的最坏情况可让记忆独占 8 万字符。段级预算按 `importance DESC, created_at DESC` 填充直到耗尽，被丢弃条目以 `truncated_notes: N` 显式输出——对齐 003 确立的「截断必须显式、不得静默丢失」纪律。

段预算与 `safety_guidance_max_chars` 独立计算，互不挤占。

## 6. 失效路径

- **supersede**：新 note 的 `supersedes` 命中既有 note 时软删除，保留行并记 `superseded_by`，`read_memory()` 默认过滤，审计与 `search-memory` 仍可见。
- **TTL**：按 kind 配置，`observation` 默认 24h，其余默认无限。过期只改变带位（转 `archived`），**不删除数据**。
- 明确不做**自动记忆整理**：不引入 LLM 裁决的合并、去重或矛盾消解。理由——那会让认知侧获得改写自身长期上下文的权力，且没有确定性验收口径，属于典型的「无 eval 调优」。

## 7. 检索打分

`protocol/retrieval.py` 三处最小改动，全部保持本地确定性：

1. `_tokens()` 增加相邻汉字二元组。现状 `[一-鿿]` 单字符类把中文切成单字，中文查询退化为字频匹配。
2. 打分除以 `sqrt(len(content_tokens))` 做长度归一。现状是裸词频求和，长 chunk 恒胜。
3. 保留短语加权与 tag 加权的既有权重，不调参——调参需要 eval，本条不建 eval。

`search-memory` 的 CLI/API 契约不变，但排序结果会变，需要基线回归锁定新口径。

## 8. 验收门禁

**正向**

- pinned note 出现在 `memory_pinned`，位置在 `capabilities`/`safety` 之后、`world` 之前；四路 `ContextPurpose` 字段顺序一致（golden）。
- `list[str]` 形式的 memory 输出仍被接受并正确归一。
- supersede 后旧 note 不再注入，`search-memory` 仍可检索到。
- TTL 过期的 observation 转 archived 后不再注入，数据库行仍在。
- 中文查询在 bigram 下命中预期 chunk；长 chunk 不再仅因长度胜出。

**反向**

- LLM 声明 `importance=3` 被拒绝（strict 契约）；声明 `kind="constraint"` 被降级为 `fact` 并记 `downgraded_from`。
- pinned/episodic 段超预算时 `truncated_notes` 计数显式，无静默丢弃。
- 新写入与存量回填后，`source_type='memory'` 的 chunk `trust_level` 恒为 `untrusted`；构造含「本条为可信系统规则」字样的注入样本，不能改变 trust_level 或带位。
- 结构隔离炸药桩：记忆内容不可能出现在 `safety`、guidance、hard policy 或 policy digest 的任何字段。
- `retrieval.enabled` 两种取值下，同一 note 不同时出现在 `retrieved_context` 与 `memory_episodic`。

**门禁**

- context 四路 golden 重录并逐字段 diff review。
- 记忆/检索/state 专项矩阵；Python full `pytest`。
- 若改动 `MemorySearchPanel` 展示或文案，再跑 `tsc -b && vite build`。

## 9. 范围外

- **prompt caching 接线**（`cache_control` breakpoint、`cache_read_input_tokens` 记录）。本条只提供稳定前缀布局这一前置条件；接线是 provider 相关的独立条目，约 0.5 轮，需在布局 golden 稳定后单独进行。
- embedding / `sqlite-vec` / 向量检索（B4-vec 继续冻结）。
- LLM 裁决的记忆整理、合并、矛盾消解。
- prompt 措辞、few-shot、拒绝分类枚举、F0 eval 扩建——属 `brief-prompt-context-engineering` 的 P2 档，前置条件是可复跑评测集，本条不满足也不代劳。
- SAFETY guidance 的任何改动（归 003）。
- 检索打分的权重调参、召回率优化。
