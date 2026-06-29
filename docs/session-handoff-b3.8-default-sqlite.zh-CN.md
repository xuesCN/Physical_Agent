# Session Handoff：B3.8 default SQLite switch

> 目的：记录本轮把新项目默认 StateStore backend 从 Markdown 切到 SQLite 的实际范围、兼容策略、回滚方式和验证结果。
>
> 结论：新生成 config 默认 `workspace.backend: sqlite`；显式 `backend: markdown` 的项目仍走 `MarkdownStateStore`。Markdown backend、Markdown parser / renderer、`migrate-md-to-sqlite`、`export-audit`、`state-check` 和 `SAFETY.md` 文件真源均保留。`watch` 仍是唯一 claim + `SafetyGate` + `driver.execute` 执行侧。

## 实际完成范围

- 新增本轮 brief：
  - `docs/next-session-b3.8-default-sqlite.zh-CN.md`
- 默认配置切换：
  - `WorkspaceConfig.backend` 默认值从 `markdown` 改为 `sqlite`。
  - `default_config_dict()` 写出的 `workspace.backend` 从 `markdown` 改为 `sqlite`。
  - `open_state_store()` 与 `state-check` 的空 backend fallback 同步为 `sqlite`。
- CLI / 文档提示：
  - 顶层 CLI help 不再称为 Markdown-native。
  - `migrate-md-to-sqlite` 仍不改 config，提示改为“如需使用 SQLite DB，请设置 `workspace.backend: sqlite`”。
  - `README.zh-CN.md`、`HANDOFF.zh-CN.md`、`docs/sqlite-readiness.zh-CN.md` 已更新默认 backend、Markdown 兼容和回滚说明。
- 测试更新：
  - 默认 backend 相关测试改为期望 `SqliteStateStore`。
  - Markdown loop / Markdown MCP 测试显式配置 `backend: markdown`。
  - 新增默认 `init` / `setup` / `state-check` 覆盖，确认 `state.db` 与 `SAFETY.md` 存在。

## 默认配置变更点

新生成配置现在为：

```yaml
workspace:
  path: ./workspace
  backend: sqlite
```

`physical-agent init` 和 `physical-agent setup` 默认创建 SQLite workspace，并保留 `workspace/SAFETY.md` 作为安全规则文件真源。

## 现有 Markdown 项目兼容方式

已有项目只要在 config 中显式保留：

```yaml
workspace:
  path: ./workspace
  backend: markdown
```

仍使用 `MarkdownStateStore`，Markdown workspace 文件仍是状态真源。Markdown backend、parser、renderer 这轮没有删除。

`migrate-md-to-sqlite` 仍只创建/覆盖 `workspace/state.db`，不会自动改已有 config。`export-audit` 仍只导出审计视图，不改 backend 或 action board。

## 回滚方式

单个项目回滚：

```yaml
workspace:
  path: ./workspace
  backend: markdown
```

代码级回滚：把 `physical_agent/config.py` 里的 `WorkspaceConfig.backend` 和 `default_config_dict()["workspace"]["backend"]` 改回 `markdown`。

## 测试命令和结果

相关集合：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_backend_matrix.py tests\test_state_store.py tests\test_mcp_server.py tests\test_watch_runtime.py tests\test_e2e_markdown_loop.py tests\test_e2e_sqlite_loop.py tests\test_quickstart_doctor.py tests\test_chat_runtime.py tests\test_code_skill.py tests\test_tool_loop.py tests\test_hardware_onboarding.py tests\test_safety_boundaries.py
```

结果：

```text
79 passed in 25.59s
```

全量测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
136 passed in 33.54s
```

## 未完成事项

- 未删除 Markdown backend / Markdown parser / renderer。
- 未做 Agents SDK。
- 未做 FastAPI / React / 常驻 watch 服务化。
- 未做文件上传摄入。
- 未做 sqlite-vec / RAG。
- 未新增任何 agent / tool / gui 侧硬件执行入口。
- 未在真实历史 workspace 集合上做人工迁移抽样。

## 下一步建议

1. B4 structured memory：在默认 SQLite 稳定后推进结构化记忆；不要引入 RAG 执行捷径。
2. C1 FastAPI：等默认 backend 与 action board 契约继续稳定后再接服务端 API，避免请求侧绕过 watch。
3. B4b 文件上传摄入：上传内容只作为不可信上下文进入提案侧，由其引出的 action 仍必须走 action board + watch + SafetyGate。
