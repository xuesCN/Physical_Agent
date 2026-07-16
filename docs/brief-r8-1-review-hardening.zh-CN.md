# R8.1 阶段 review 修复 brief

日期：2026-07-16

## 范围

- 修复 SQLite 多进程 writer 下 `LOG.md` mirror 丢更新、revision 分叉和非原子写入。
- 让 LOG mirror 失败保持可诊断，但绝不阻断 execute timeout 后的 halt、成功执行后的 expectation check，或已提交 API mutation 的成功响应。
- 让 current `AgentOutput` 只接受与当前 action claim owner 匹配的 in-progress SafetyGate evidence；不新增 task table、attempt ledger 或 VNext-3 能力。
- 让 OpenAPI 中 `ChatPlan.agent_output` 明确引用 canonical `AgentOutput` schema，同时保持现有 JSON wire。
- 修正 R8 spec/plan/evidence matrix/PLAYBOOK/REFACTORING 与 PR 元数据，记录 R5/R6 顺序和 R6/R7 rollback 粒度的历史偏离。
- 重跑 Python full、真实 Chromium、TUI、frontend build、clean-wheel、多进程专项与安全边界；完成独立终审。

## 验收

1. 跨进程并发 append 后 SQLite 与 `LOG.md` 条目、revision 一致；mirror 使用原子替换，下一次成功同步可修复先前 stale mirror。
2. mirror 写失败时 SQLite 日志仍提交、doctor 报 stale；watch timeout 仍先 halt，正常执行仍产生 expectation check，API 不出现“状态已提交但因 mirror 返回 500”。
3. recovered action 被 successor claim 后，旧 owner 的 Gate pass 在 fresh Gate 写入前不能满足 current Gate；matching owner evidence 正常 materialize。
4. OpenAPI `ChatPlan.agent_output` 指向 `AgentOutput`，并继续禁止 `ChatPlan.actions`。
5. 正式文档、证据矩阵和 PR 元数据一致；冻结项保持冻结。
6. 全量门禁与独立 review 通过，Critical/Important 清零。

## 范围外

- 不实现 VNext-3/4、W4/W5/W6.2、F0 后续、F5/F6、B4-vec、registry/read-model、自动 replan。
- 不改变 SafetyGate、审批语义、Action Board truth 或 watch 唯一执行权。
- 不修改或暂存 `docs/brief-hardware-connectivity-review.zh-CN.md`、`docs/brief-vnext-review-sync-recovery.zh-CN.md`。
- 不修改 `docs/current-architecture-audit.md`、`docs/current-architecture-audit.html`、`docs/system-summary.zh-CN.md`。
