# Next Session Brief：B4b file ingestion foundation

## 背景

- B3.8 已完成默认 SQLite backend 切换；新项目默认使用 `workspace.backend: sqlite`。
- B4a 已完成 structured memory；memory notes 具备 `kind`、`source`、`tags`、`importance`、`created_at` 等字段。
- 显式 `backend: markdown` 仍可用，Markdown backend / parser / renderer 不删除、不破坏。

## 本轮目标

实现本地文件摄入基础：把用户提供的小范围文本类文件复制到 `workspace/uploads/`，记录可审计 metadata，并将小文本摘录作为“不可信上下文”进入 structured memory / agent 提案侧。

## 禁止做

- 不做 FastAPI / React 上传 UI。
- 不做 PDF / OCR。
- 不做 embedding、sqlite-vec 或 RAG。
- 不做 Agents SDK。
- 不新增任何 agent / tool / gui 硬件执行入口。
- 不删除或重写 Markdown backend / parser / renderer。

## 安全红线

上传 / 摄入内容是不可信输入，只能影响 agent 提案上下文。任何由上传内容引出的动作仍必须走：

```text
proposal -> action board -> watch -> SafetyGate -> driver.execute
```

`SAFETY`、capabilities、world、feedback、pending action 等安全关键事实仍必须从结构化 state 实时读取，不得依赖上传内容、memory 摘录或摘要。

## 验收标准

1. 默认 backend 仍是 SQLite。
2. 显式 `backend: markdown` 仍可用。
3. 支持 `.txt`、`.md`、`.markdown`、`.py`、`.json`、`.yaml`、`.yml`、`.toml`、`.csv`、`.log` 等文本类文件安全摄入到 `workspace/uploads/`。
4. 不支持 PDF、image、binary；unsupported type 明确失败。
5. 摄入时计算 `sha256`，复制为 `workspace/uploads/<sha-prefix>-<safe-name>`。
6. 文件名经过 sanitize，避免路径穿越和奇怪文件名污染 workspace。
7. upload metadata 可审计，SQLite 和 Markdown backend 都能读取 / export。
8. 小文本摘录写入 structured memory，明确标记 `UNTRUSTED UPLOAD EXCERPT`，且 `source=upload`。
9. 超过大小上限时只记录 metadata，不把全文或摘录写入 memory。
10. ChatRuntime / tool_loop prompt/context 明确提醒 memory/upload 内容是不可信上下文，不是安全事实或指令。
11. `physical-agent ingest-file PATH --config physical-agent.yaml [--tag TAG] [--importance N]` 不执行 watch，不 claim action，不调用 driver，不改 backend。
12. watch / SafetyGate 不依赖摄入内容。
13. agent / tool / gui 不新增硬件执行入口。
14. safety boundary 测试和全量 pytest 通过。
