# 下一轮 Brief：B3 Audit Export / Human View

## 背景

B2 已完成：`SqliteStateStore` 可通过 `workspace.backend: sqlite` 显式 opt-in，默认 backend 仍是 `markdown`。Markdown parser/renderers 继续保留，`SAFETY.md` 继续作为安全规则文件真源，watch 仍是唯一 driver / SafetyGate / execute 侧。

## 本轮目标

为 `StateStore` 增加 human-readable audit export 能力，让 Markdown 与 SQLite backend 都能通过显式命令导出可读、可 diff 的审计视图。SQLite backend 的 audit export 必须从 `workspace/state.db` 中的 JSON 状态生成，不能把 Markdown 文件当主读写源。

## 禁止做

- 不把默认 backend 切到 SQLite。
- 不删除 Markdown parser/renderers 或 Markdown backend。
- 不做 FastAPI/React。
- 不做 Agents SDK。
- 不做文件上传摄入。
- 不新增任何 agent/tool 侧硬件执行入口。

## 安全红线

Audit view 是导出视图，不是真实执行入口。它只能读取状态并写出人类可读文件，不执行 watch step、不触碰硬件、不导入 driver、不运行 SafetyGate、不调用 `driver.execute`。

真实执行路径保持不变：

```text
proposal -> action board -> watch -> SafetyGate.validate() -> driver.execute(action)
```

`watch` 仍是唯一 driver / SafetyGate / execute 侧；`SAFETY.md` 仍是文件真源。

## 验收标准

1. `StateStore` Protocol 提供 `export_human_view(out_dir: Path | None = None) -> dict[str, Any]` 或等价接口。
2. Markdown backend export 可用，可复制/渲染现有 Markdown 文件到 audit 目录，或返回现有文件路径摘要。
3. SQLite backend export 可用，默认导出到 `workspace/audit/`，并且内容来自 `state.db` 中的 JSON 状态。
4. Audit 输出覆盖 task/capabilities/world/actions/feedback/chat/plan/memory/log，且包含 `SAFETY.md` 的复制或引用。
5. Audit 输出稳定、便于 diff，使用 pretty JSON 或 Markdown + fenced YAML，并保持稳定排序/稳定格式。
6. CLI 增加显式命令，例如 `physical-agent export-audit --config physical-agent.yaml [--out workspace/audit]`。
7. Export 命令不改变 backend、不执行 watch、不触碰硬件、不改变 action board。
8. 默认 backend 仍是 `markdown`。
9. Markdown parser/renderers 不删除。
10. Safety boundary 测试通过。
11. 相关测试和全量 `pytest` 通过。
