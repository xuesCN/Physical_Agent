# Session Handoff：B4b file ingestion foundation

> 目的：在不引入 FastAPI/React、embedding、sqlite-vec、RAG、Agents SDK 或任何硬件执行入口的前提下，实现本地文本类文件摄入基础。
>
> 结论：已完成本地文件摄入 helper、`ingest-file` CLI、SQLite / Markdown upload metadata 审计、small text excerpt 写入 structured memory，并在 ChatRuntime / tool_loop 上下文中明确标记 upload/memory 为不可信上下文。默认 backend 仍是 SQLite，显式 `backend: markdown` 仍可用。

## 实际完成范围

- 新增 brief：
  - `docs/next-session-b4b-file-ingestion.zh-CN.md`
- 新增文件摄入模块：
  - `physical_agent/ingest/files.py`
  - `physical_agent/ingest/__init__.py`
- 支持文本类 suffix：
  - `.txt`、`.md`、`.markdown`、`.py`、`.json`、`.yaml`、`.yml`、`.toml`、`.csv`、`.log`
- 明确拒绝：
  - unsupported suffix，例如 PDF；
  - binary / non-UTF-8 内容；
  - PDF/OCR/image 没有实现。
- 大小策略：
  - 默认 inline 上限为 `1MB`。
  - 超限文本仍复制到 `workspace/uploads/` 并记录 metadata，但不写 preview 到 memory。
- 文件存储：
  - 计算 `sha256`。
  - 复制到 `workspace/uploads/<sha-prefix>-<safe-name>`。
  - 文件名经过 ASCII sanitize，避免路径穿越和奇怪字符污染 workspace。
- StateStore 扩展：
  - 新增 `uploads_path`。
  - 新增 `read_uploads()` / `append_upload_metadata()`。
- Audit 扩展：
  - `export-audit` 现在包含 `uploads.json`。
- ChatRuntime / tool_loop：
  - 仍只读取最近有限 memory notes。
  - 上下文新增 `context_policy`，系统提示也明确说明 upload/memory 是不可信上下文，不是安全事实或指令。

## ingest-file CLI 用法

```powershell
physical-agent ingest-file PATH --config physical-agent.yaml --tag TAG --importance 3
```

`--tag` 可重复。命令会输出：

- stored path
- sha256
- memory written: yes/no
- truncated: yes/no

该命令只写 state / uploads / memory，不运行 `watch`，不 claim action，不调用 driver，不修改 `workspace.backend`。

## Upload Metadata / Audit 格式

每条 upload metadata 形如：

```json
{
  "original_path": "C:/path/to/source.md",
  "original_name": "source.md",
  "stored_path": "C:/project/workspace/uploads/abc123-source.md",
  "stored_name": "abc123-source.md",
  "sha256": "...",
  "size_bytes": 123,
  "content_type": "text/markdown",
  "suffix": ".md",
  "created_at": "2026-06-29T00:00:00Z",
  "status": "stored",
  "preview": "short excerpt",
  "truncated": false,
  "memory_note_created": true,
  "tags": ["brief"],
  "importance": 3,
  "error": ""
}
```

常见 `status`：

- `stored`
- `stored_metadata_only`
- `rejected_unsupported_type`
- `rejected_binary`

## SQLite / Markdown Backend 行为差异

- SQLite backend：
  - upload metadata 存在 `upload_metadata` 表。
  - `doc_state` 中有 `uploads` 文档 revision。
  - `state-check` 会检查 `upload_metadata` 表和列；旧库不会被误判为未初始化，但会显示 schema incomplete，直到 `initialize()` 补表。
- Markdown backend：
  - upload metadata 存在 `workspace/uploads/manifest.json`。
  - 不新增 Markdown 协议文件。
  - 不改动 Markdown parser / renderer。

Markdown -> SQLite 迁移会带上已有 upload manifest metadata。

## 不可信输入安全策略

- 小文本摘录写入 memory note：
  - `kind: upload_excerpt`
  - `source: upload`
  - `tags: ["upload", suffix, ...]`
  - content 以 `UNTRUSTED UPLOAD EXCERPT` 开头。
- upload 内容只进入 agent 提案上下文。
- `SAFETY`、capabilities、world、feedback、pending action 等安全关键事实仍实时从 state 读取。
- 任何动作仍必须走：

```text
proposal -> action board -> watch -> SafetyGate -> driver.execute
```

本轮没有新增 agent / tool / gui 侧硬件执行入口。

## 测试命令和结果

相关测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_file_ingestion.py
.\.venv\Scripts\python.exe -m pytest -q tests\test_chat_runtime.py tests\test_tool_loop.py
.\.venv\Scripts\python.exe -m pytest -q tests\test_state_store.py tests\test_backend_matrix.py
.\.venv\Scripts\python.exe -m pytest -q tests\test_safety_boundaries.py
```

结果：

```text
5 passed in 1.18s
12 passed in 5.97s
34 passed in 3.42s
1 passed in 0.09s
```

全量测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
143 passed in 29.94s
```

## 未完成事项

- 未做 FastAPI / React 上传 UI。
- 未做 PDF / OCR。
- 未做 embedding。
- 未做 sqlite-vec。
- 未做 RAG。
- 未做 Agents SDK。
- 未新增任何 agent / tool / gui 硬件执行入口。

## 下一步建议

1. B4c sqlite-vec 可选检索：在当前 upload metadata / structured memory 基础上做可选检索层，仍只影响提案上下文。
2. C1 FastAPI：把现有 StateStore / action board / audit 契约包装成服务端 API。
3. C3 GUI upload：在 API 稳定后加 GUI 上传入口。
