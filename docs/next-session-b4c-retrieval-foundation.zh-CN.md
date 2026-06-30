# Next Session Brief：B4c retrieval foundation / optional sqlite-vec groundwork

## 背景

- B3.8 已把新项目默认 StateStore backend 切到 SQLite；显式 `workspace.backend: markdown` 仍可用，Markdown backend / parser / renderer 不删除。
- B4a 已完成 structured memory：`memory_notes` 支持 `content/kind/source/tags/importance/created_at`，并保持可审计。
- B4b 已完成 file ingestion foundation：本地文本文件可摄入到 `workspace/uploads/`，upload metadata 可审计，小文本可写入 `upload_excerpt` memory note，上传内容明确是不可信上下文。

## 本轮目标

增加 memory/upload chunks 与确定性 query 契约，为后续 sqlite-vec / embedding RAG 打基础：

- 新增默认关闭的 `memory.retrieval` 配置。
- 增加 SQLite chunk schema 与兼容 migration。
- 为 Markdown backend 提供兼容的 chunks 存储或 no-op 行为，确保显式 Markdown 项目不坏。
- B4b 小文本摄入时同步创建 upload chunk；超限 metadata-only 文件不写全文 chunk。
- 增加本地、确定性、无外部依赖的 keyword/token query API，例如 `query_memory_chunks(query, limit=5, tags=None, source_type=None)`。
- 增加只读 CLI：`physical-agent search-memory QUERY --config physical-agent.yaml --limit 5`。
- 仅在 `memory.retrieval.enabled=true` 时，把 query 结果作为 `retrieved_context` 放入 ChatRuntime / tool_loop payload。

## 禁止做

- 不接 OpenAI Embeddings API。
- 不做真实外部 embedding 调用。
- 不做 Agents SDK。
- 不做 FastAPI / React。
- 不做 GUI upload。
- 不新增任何 agent / tool / gui 侧硬件执行入口。
- 不删除 Markdown backend / parser / renderer。

## 安全红线

- `retrieved_context` 是不可信提案上下文，只能辅助 agent 生成 proposal。
- `SAFETY`、world、capabilities、actions、feedback 仍实时从 state 读取，不能由检索结果覆盖。
- `watch` / `SafetyGate` 不依赖检索结果。
- 执行路径保持不变：`proposal -> action board -> watch -> SafetyGate -> driver.execute`。
- upload chunks 必须标记为 `trust_level: untrusted`。

## 验收标准

1. 默认 backend 仍是 SQLite。
2. retrieval 默认 disabled。
3. chunk/index/query 契约可用且可审计。
4. 不调用 OpenAI Embeddings API，不引入真实外部 embedding。
5. retrieved context 只影响 agent 提案上下文。
6. watch / SafetyGate 不依赖 retrieval。
7. agent / tool / gui 不新增硬件执行入口。
8. SQLite 旧 `state.db` 可通过 `initialize()` 兼容迁移 chunk schema。
9. Markdown backend 显式配置仍可用。
10. CLI `search-memory` 只读，不执行 watch，不 claim action，不调用 driver，不改 backend。
11. safety boundary 测试通过。
12. 相关测试和全量 `pytest` 通过。
