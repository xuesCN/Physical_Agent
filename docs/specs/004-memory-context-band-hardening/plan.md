# 004：执行计划

## 顺序总览

| 阶段 | 内容 | 门槛 |
| --- | --- | --- |
| 0 | 等 003 收口 | `specs/003` tasks 全绿并 push；`context_builder` 的 safety/budget 代码不再变动 |
| 1 | trust 口径修复 + 存量回填 | memory chunk `trust_level` 恒为 `untrusted`，注入样本无法提升 |
| 2 | note 结构化契约 + 降级规则 | `list[str]` 兼容；`importance>2` 拒绝；`constraint/preference` 降级并留痕 |
| 3 | 带位划分 + payload 三段重排 | 四路 golden 重录并逐字段 review；同一 note 不双注入 |
| 4 | 段级预算闸 + 显式截断计数 | 超限零静默丢弃 |
| 5 | supersede / TTL 失效 | archived 不注入、数据保留、仍可检索 |
| 6 | 检索 bigram + 长度归一 | 中文命中基线；长 chunk 不再仅因长度胜出 |
| 7 | 矩阵、文档与账本收口 | 专项 + 全量 + diff/review 全绿 |

阶段 1 与 2 互不依赖，可并行；阶段 3 必须在 2 之后（带位判定依赖 kind/importance 的可信来源）；阶段 4 必须在 3 之后（预算按段计算）。

## 实施口径

1. **带位是派生量，不是存储列。** `pinned/episodic/archived` 由 `kind`、`importance`、`superseded_by`、`created_at` 在读取时计算。新增存储列只有失效需要的 `superseded_by`，不为带位建表或加索引。
2. **契约升级先于布局重排。** 先让 `importance`/`kind` 有可信写入通道，再让它决定注入位置。顺序颠倒会出现一个只有默认值可用的带位系统——正是当前 `importance` 恒为 0 的成因。
3. **降级要留痕，不要静默。** LLM 声明越权 `kind` 时降级并记 `downgraded_from`，不抛错。理由：这是常规交互，不是安全事件；fail closed 留给能影响执行的路径。
4. **golden 重录必须逐字段 diff。** 四份 context golden 会整体变化，整体覆盖会让真正的回归混在噪音里。重录提交与实现提交分开。
5. **存量回填是一次性 UPDATE，不是 migration。** `trust_level` 回填不改 schema、不加版本号；`superseded_by` 走既有 `_ensure_columns` 补列路径。
6. **每阶段先跑最小专项**，阶段 3/4 之后各跑一次 context 矩阵，阶段 7 跑记忆/检索/state/context/API/safety 矩阵与全量。

## 关键文件

| 层 | 文件 | 改动 |
| --- | --- | --- |
| 契约 | `agent/llm_contracts.py` | 新增 `LLMMemoryNote`；`ChatLLMResponse.memory` 改 union |
| 协议 | `protocol/memory.py` | `normalize_memory_note` 支持 kind 降级、`supersedes`、TTL 判定 |
| 协议 | `protocol/retrieval.py` | `_tokens` bigram；`_score_chunk` 长度归一 |
| 状态 | `state/sqlite.py` | `trust_level` 修正 + 回填；`superseded_by` 列；`read_memory` 过滤 |
| 状态 | `state/base.py` | 协议签名同步 |
| 认知 | `agent/context_builder.py` | 带位划分、payload 三段重排、段级预算、`truncated_notes` |
| 认知 | `agent/chat_runtime.py` | 两处 `append_memory_note` 传递结构化字段 |

## 坑

- **`chat_runtime` 有两条写入路径**（非流式 `:270`、流式 `:665`），历史上改一处漏一处。两处必须同时改，且各自有回归。
- **`filter_memory_notes` 的 `limit` 取尾部 N 条**（`normalized[-count:]`），而 `_top_memory_notes` 按 importance 排序。带位划分后要确认两者语义不再互相抵消。
- **`write_memory()` 是全量覆盖**，会 `DELETE FROM memory_chunks WHERE source_type='memory'` 再重建。trust 回填必须同时覆盖这条路径，否则一次全量写入会把回填结果冲掉。
- **上传 note 不切 chunk**（`_insert_memory_note_chunks_conn` 对 `source == "upload"` 直接 return），带位与失效逻辑不要误伤这条分支。
- **`memory_chunks` 的 UNIQUE 是 `(source_type, source_id, chunk_index)`**，而 note 的 `source_id` 是含 `created_at` 的哈希——同内容不同时间写入会产生两条 chunk。本条不修这个重复（属检索去重，范围外），但 supersede 生效后要确认旧 chunk 不再被召回为「当前事实」。
- **003 的 guidance 预算是独立配额**，段级预算实现时不要复用同一个剩余量计算器，否则会出现记忆挤占安全 guidance 的路径。
- **记忆测试夹具必须跟上 003 的策略生命周期。** 2026-08-14 在 003 未收口的树上跑全量（`613 passed, 6 failed`），失败项里有两条属于记忆检索：`test_retrieval_foundation.py::test_sqlite_initialize_migrates_memory_chunk_schema` 抛 `SafetyPolicyError: Missing SAFETY policy file`，`::test_chat_runtime_retrieval_enabled_adds_untrusted_context_without_overrides` 抛 `SafetyGuidanceContextError: Agent Guidance is required before producing hardware action intents`。成因是这两个夹具建 workspace 时不写 SAFETY/guidance，而记忆与检索路径现在要过策略校验。**影响 004 的判断口径**：开工前这两条就是红的，若不先归因，004 的第一次跑分会把它们误读成带位重构引入的回归。新增用例必须显式准备合法 SAFETY + guidance，或声明 simulation 走兼容放行路径。

## 回滚

本条不含数据库 migration。`superseded_by` 是可空补列，`trust_level` 回填是幂等 UPDATE，两者回滚后旧代码仍可读。代码按 trust/契约、带位布局、预算、失效、检索五层分提交，可整体或分层回滚。golden 重录单独成提交，回滚布局时一并回滚。
