# 轮次 brief：VNext 实现核查 + 同步损坏恢复

日期：2026-07-10 · 执行者：Claude（Cowork 会话）· 性质：验证/事故恢复轮，**未修改任何业务代码**

## 范围

1. 评审 VNext-0/1/2/2b + W6.1（AgentOutput / PlanCompiler / SafetyGateTask / watch lease）方案与实现。
2. 处理 Codex 同步事故：工作区文件大面积损坏的诊断与恢复。
3. 不改 watch / SafetyGate / driver / API 任何行为；不动 SPEC 矩阵状态（本轮无新功能条目）。

## 一、方案评审结论：接受

核对代码后确认三个关键关切均已被设计解决：

- **TOCTOU**：SafetyGate 在 watch claim 之后同调用栈执行（claim → validate → 记录决策 → execute），关键步骤前均有 `_require_watch_lease` 续租检查；Gate 结论不存在"先验后用"时间窗。
- **DAG 恢复语义**：任务图不是持久化状态机，而是由 `output_projection` 从 Action board + structured feedback 投影而来，无第二真源可失步。SPEC 已明示"仍不是持久化 obligation engine"。
- **Verification 越权**：VerificationTask 仅在 `metadata.expected` 存在时生成、watch-owned、依赖 physical task，保持 F4 诊断属性（决策 #16）。

其余核实点：`AgentTask.origin` 锁死 `plan_compiler`；schema 强制每个物理 Action 恰好一个 mandatory、watch-owned、声明 SAFETY.md 的 Gate task + 规范 task id + 无环校验；PlanCompiler 零 watch/driver import；`append_pending_actions` 单事务 all-or-nothing；`runtime_leases` 单执行者租约 + claim_owner CAS；NaN/Inf/反向区间校验在 `watch/safety.py`；安全边界测试升级为 AST 扫描 + 显式 allowlist。

**架构判断**：两条宪法（执行权唯一、执行前校验不可绕过）实质未变——本轮是把 Gate 从 watch 隐式步骤升格为任务图上显式、不可伪造的义务节点，属于"显式化 + 硬化"，不是权力转移。

## 二、同步事故与恢复

**症状**：Codex 本地同步只把完整内容写入 git index，工作区文件损坏——25 个 Python 文件截断或含 null 字节（含 `watch/safety.py`、`api/server.py`、全部安全测试）、`tui/src/types.ts` 与 `tui/src/App.tsx` 截断、文件名 `upload.scenario` 截断为 `upload.scenar`、分支名截断为 `codex/age`。

**恢复过程**：

1. 全库 AST 语法扫描定位 25 个损坏 Python 文件；确认 git index 中 25/25 暂存副本完好。
2. 以 `git show :path` 从 index 恢复全部 206 个差异文件；`upload.scenario` 经 blob hash 直读恢复（52 行）。
3. 分支 HEAD 由 `codex/age` 改名为 `codex/agent-core-refactor`（`git symbolic-ref`）。
4. 用户本机收尾：`git reset` 清 index 残留（截断名 rename、tsconfig 假删除）→ `git restore .` 以完好 commit 覆写工作区。

**验收**：AST 扫描 0 错误；null 字节 0；commit `46c817e` 内容抽查通过（`safety.py` 478 行、`upload.scenario`/`tsconfig.json` 名称与内容正确、`server.py` 可解析）；用户本机 `pytest -q` **393 passed**（1 个既有 StarletteDeprecationWarning）；frontend build 与 tui test 由沙盒 Linux 环境重装依赖后执行（结果见本 brief 提交信息或会话记录）。

## 三、遗留与建议

- REFACTORING §1/§2 的 VNext 小节由实现方（Codex 轮）维护，本轮不代笔；本 brief 按惯例用完即删。
- **同步方式建议**：后续 Codex 产出改走 `git push` + 本地 `git fetch/switch`，避免文件级同步再次截断（本次连分支名和文件名都被截断，说明同步工具按字节流写入且无完整性校验）。
- 本机（Windows/autocrlf）与沙盒（Linux）对同一工作区的 CRLF/LF 视图差异会让一侧 `git status` 显示大量 modified——内容无实际差异，勿盲目 `git add -A`。
