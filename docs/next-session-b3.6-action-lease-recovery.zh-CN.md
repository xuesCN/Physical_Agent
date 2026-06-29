# 下一轮 Brief：B3.6 Action Lease / Failure Recovery

## 背景

B3.5 已经为 `StateStore` action board 增加 `append_pending_action()` / `claim_next_ready_action()` / `mark_action_completed()` / `mark_action_cancelled()` 原子 API。SQLite backend 内部使用 `in_progress` 状态防止多个 watch 重复领取同一条 pending action；`read_actions()` 对外仍只暴露 pending / completed / cancelled 三栏。

当前缺口是：action 被 claim 后，如果 watch 或 driver 在执行路径抛异常，SQLite 内部的 `in_progress` 可能永久卡住，既不再出现在 pending，也不会进入 completed / cancelled。

## 本轮目标

- 为 SQLite `in_progress` action 增加 lease / stale recovery 机制。
- 为 actions 表补充最小 claim 元数据，例如 `claimed_at`、`claim_owner`、`attempts`，并兼容旧 `state.db` schema migration。
- 让 `WatchRuntime` 在 `driver.execute(action)` 抛异常时写入终态和反馈/log，避免 action 永久停在 `in_progress`。
- 保持 Markdown backend、默认配置、audit export 和安全边界不变。

## 禁止做

- 不把默认 backend 切到 SQLite。
- 不删除 Markdown backend / Markdown workspace 协议。
- 不做 FastAPI / React。
- 不做 Agents SDK。
- 不做文件上传摄入。
- 不做 sqlite-vec / RAG。
- 不新增任何 agent / tool / gui 侧硬件执行入口。

## 安全红线

- agent / tool / gui 只能 append pending action。
- 只有 watch 能 claim action、运行 `SafetyGate`、调用 `driver.execute(action)`。
- 失败恢复不得绕过 `SafetyGate`。
- 失败恢复不得重放 completed / cancelled action。
- SQLite 内部 `in_progress` 不得泄漏给现有 UI / audit 的 pending / completed / cancelled 三栏视图。

## 验收标准

1. 默认 backend 仍是 `markdown`。
2. SQLite backend 的 `in_progress` action 有明确恢复机制。
3. 旧 `state.db` 缺少新增 claim 列时，`initialize()` / `exists()` / `claim_next_ready_action()` 可用。
4. SQLite claim 在单事务内写入 `claimed_at` / `claim_owner` / `attempts`，重复 claim 不会拿到同一 action。
5. stale `in_progress` 超时后可以恢复为 pending 或被重新 claim；未超时的不应被重复领取。
6. `driver.execute(action)` 抛异常时，watch 会 mark cancelled，写入 failed feedback/log，并继续或安全退出，不留下永久 `in_progress`。
7. SafetyGate 拒绝路径继续 mark cancelled。
8. Markdown backend 现有 append / claim / mark 行为继续通过。
9. audit export 行为不被破坏。
10. safety boundary 测试继续通过。
11. agent / tool / gui 不新增任何硬件执行入口。
12. 全量 `pytest` 通过。
