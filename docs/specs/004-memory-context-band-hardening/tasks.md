# 004：任务与验收账本

状态图例：`[x]` 完成；`[ ]` 未完成。

## 规格与边界

- [x] 读 SPEC §0/§2/§4、PLAYBOOK B4a-c 与 F3、REFACTORING §2「B4a-c」/§3.15、`brief-prompt-context-engineering`。
- [x] 核对 002 已收口（LLM 契约 Pydantic 单真源）、003 在飞（已改 `context_builder` 的 budget 与 safety 注入）。
- [x] 明确不解冻 B4-vec / F0 / 自动 replan；caching 接线列入范围外。
- [x] 决定 trust 保持两档而非三档，并记录放弃三档的 rationale（spec §4）。
- [x] 决定 LLM 的 `importance` 上界为 2、`constraint/preference` 仅人工写入，并记录 rationale（spec §3）。
- [x] 建立 spec/plan/tasks。
- [x] SPEC §4 追加 `F3.2 / 004` 行；PLAYBOOK 追加同名条目（含决策留痕与坑清单）。
- [ ] 确认 003 已收口并 push，方可开工。

## 阶段 1：Trust 口径

- [ ] `_insert_memory_note_chunks_conn` 写入 `trust_level="untrusted"`。
- [ ] 存量 `source_type='memory'` chunk 一次性幂等回填。
- [ ] `write_memory()` 全量覆盖路径同样产出 untrusted。

## 阶段 2：Note 契约

- [ ] `LLMMemoryNote` 落地；`ChatLLMResponse.memory` 支持 `list[str] | list[LLMMemoryNote]`。
- [ ] `kind` 越权降级为 `fact` 并记 `downgraded_from`。
- [ ] `chat_runtime` 两条写入路径（非流式 / 流式）同时传递结构化字段。

## 阶段 3：带位与布局

- [ ] 带位由 kind/importance/superseded_by/created_at 读取时派生，不新增带位存储列。
- [ ] payload 改三段：稳定段 / `memory_pinned` / 易变段。
- [ ] `retrieval.enabled` 两态下 episodic 只出现在一处。
- [ ] 四路 context golden 重录，单独成提交，逐字段 diff review。

## 阶段 4：预算闸

- [ ] `memory_pinned_max_chars` / `memory_episodic_max_chars` 落地。
- [ ] 超限按 `importance DESC, created_at DESC` 填充，输出 `truncated_notes: N`。
- [ ] 段预算与 `safety_guidance_max_chars` 独立计算，不共用剩余量。

## 阶段 5：失效

- [ ] `superseded_by` 补列；`supersedes` 命中时软删除。
- [ ] 按 kind 的 TTL（`observation` 24h，其余无限），过期只改带位不删数据。
- [ ] `read_memory()` 默认过滤 archived；审计与 `search-memory` 仍可见。

## 阶段 6：检索

- [ ] `_tokens()` 增加相邻汉字二元组。
- [ ] `_score_chunk()` 除以 `sqrt(len(content_tokens))`。
- [ ] `search-memory` CLI/API 契约不变；新排序口径有基线回归。

## 正向验收

- [ ] pinned note 位于 `capabilities`/`safety` 之后、`world` 之前；四路顺序一致。
- [ ] `list[str]` 形式 memory 输出被接受并归一为 `observation/0`。
- [ ] supersede 后旧 note 不注入、`search-memory` 仍可检索。
- [ ] TTL 过期 observation 转 archived，数据库行仍在。
- [ ] 中文查询命中预期 chunk；长 chunk 不再仅因长度胜出。

## 反向验收

- [ ] `importance=3` 被 strict 契约拒绝。
- [ ] LLM 声明 `kind="constraint"` 降级为 `fact` 且 `downgraded_from` 留痕。
- [ ] 段超预算时 `truncated_notes` 显式，零静默丢弃。
- [ ] 含「本条为可信系统规则」字样的注入样本无法改变 trust_level 或带位。
- [ ] 炸药桩：记忆内容不可能进入 `safety` / guidance / hard policy / policy digest。
- [ ] `retrieval.enabled` 两态下同一 note 不双注入。
- [ ] 上传来源 note 仍不切 chunk，带位与失效不误伤该分支。

## 收工

- [ ] 记忆/检索/state/context 专项矩阵通过。
- [ ] Python full `pytest` 通过；改前端则 `tsc -b && vite build` 通过。
- [ ] 更新 SPEC §4 状态、PLAYBOOK 条目、REFACTORING §1/§2/§3。
- [ ] `git diff --check` clean；只提交本轮文件。
- [ ] commit 并 push。
