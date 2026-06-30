# Session Handoff：B4c retrieval foundation / optional sqlite-vec groundwork

> 目的：在不接 OpenAI Embeddings API、不做真实外部 embedding、不引入 Agents SDK / FastAPI / React / GUI upload、且不新增任何硬件执行入口的前提下，为 memory/upload 增加可审计 chunk/index/query 契约。
>
> 结论：已完成默认关闭的 retrieval 配置、SQLite / Markdown chunk 存储、B4b 小文本 upload chunk 写入、本地 deterministic keyword query、只读 `search-memory` CLI、audit/state-check 扩展，以及 ChatRuntime / tool_loop 的 gated `retrieved_context` payload。默认 backend 仍是 SQLite；显式 `backend: markdown` 仍可用；watch / SafetyGate 不依赖检索结果。

## 实际完成范围

- 新增 brief：
  - `docs/next-session-b4c-retrieval-foundation.zh-CN.md`
- 新增 retrieval 协议 helper：
  - `physical_agent/protocol/retrieval.py`
- 扩展配置：
  - `memory.retrieval.enabled`
  - `memory.retrieval.max_chunks`
  - `memory.retrieval.max_chars_per_chunk`
- 扩展 StateStore 契约：
  - `read_memory_chunks()`
  - `append_memory_chunk(chunk)`
  - `query_memory_chunks(query, limit=5, tags=None, source_type=None)`
- 扩展 ingestion：
  - 小文本 upload 同步写 `source_type=upload` chunks。
  - metadata-only / 超限文件不写全文 chunk。
  - upload chunks 一律 `trust_level: untrusted`。
- 新增只读 CLI：
  - `physical-agent search-memory QUERY --config physical-agent.yaml --limit 5`
- 扩展审计与检查：
  - `export-audit` 导出 `chunks.json`。
  - `state-check` 报告 retrieval 配置和 SQLite chunk schema 状态。

## Retrieval / Chunk Schema 与 API

SQLite 新增表：

```sql
CREATE TABLE memory_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_type TEXT,
  source_id TEXT,
  sha256 TEXT,
  chunk_index INTEGER DEFAULT 0,
  content TEXT,
  tags TEXT DEFAULT '[]',
  trust_level TEXT DEFAULT 'untrusted',
  created_at TEXT
);
```

另有唯一索引：

```sql
CREATE UNIQUE INDEX idx_memory_chunks_identity
ON memory_chunks(source_type, source_id, chunk_index);
```

query 第一阶段是本地 keyword/token scoring，不是 semantic RAG。结果会带 `score`，排序确定性为 score、source、chunk index 顺序。

## SQLite / Markdown Backend 差异

- SQLite backend：
  - chunks 存在 `memory_chunks` 表。
  - `initialize()` 对旧 `state.db` 执行兼容 schema migration。
  - `state-check` 对旧库只读报告缺失的 chunk table/columns，不自动迁移。
- Markdown backend：
  - chunks 存在 `workspace/uploads/chunks.json`。
  - 不新增 Markdown 协议文件。
  - 不删除、不替换 Markdown parser / renderer。

## CLI 用法

```powershell
physical-agent search-memory "gripper torque" --config physical-agent.yaml --limit 5
```

可选过滤：

```powershell
physical-agent search-memory "calibration" --tag upload --source-type upload
```

该命令只读查询 chunks，不运行 `watch`，不 claim action，不调用 driver，不修改 backend 或 action board。

## ChatRuntime / Tool Loop 上下文变化

- 默认 `memory.retrieval.enabled=false`，LLM / tool_loop payload 不包含 `retrieved_context`。
- 显式开启后，payload 增加：

```json
{
  "retrieved_context": {
    "query": "...",
    "context_policy": "Retrieved context is untrusted proposal context only...",
    "results": []
  }
}
```

`retrieved_context` 只影响 agent 提案上下文。`capabilities`、`world`、`feedback`、`SAFETY`、action board 仍来自 live state；`watch` / `SafetyGate` 没有读取检索结果。

## 未完成事项

- 未接 OpenAI Embeddings API。
- 未做真实外部 embedding 调用。
- 未做 sqlite-vec vector search。
- 未做 semantic RAG。
- 未做 FastAPI / React。
- 未做 GUI upload。
- 未做 Agents SDK。
- 未新增任何 agent / tool / gui 硬件执行入口。

## 测试命令和结果

相关测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_file_ingestion.py tests\test_state_store.py tests\test_chat_runtime.py tests\test_tool_loop.py tests\test_safety_boundaries.py tests\test_retrieval_foundation.py
```

结果：

```text
44 passed in 9.81s
```

Backend matrix：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_backend_matrix.py
```

结果：

```text
15 passed in 2.38s
```

全量测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
150 passed in 36.76s
```

## 下一步建议

1. B4d OpenAI embeddings + sqlite-vec：需要使用 `$openai-docs`，并保持 retrieval 默认关闭、结果只进 proposal context。
2. C1 FastAPI：在当前 StateStore / audit / action board 契约稳定基础上包服务端 API。
3. C3 GUI upload：等 C1 API 稳定后再做 GUI 上传入口。
