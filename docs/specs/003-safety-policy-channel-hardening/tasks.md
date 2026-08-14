# 003：任务与验收账本

状态图例：`[x]` 完成；`[ ]` 未完成。

## 规格与边界

- [x] 读 SPEC §0/§4、PLAYBOOK、REFACTORING SAFETY/F3/F5.0 先例。
- [x] 明确不增加 TOF Gate、不调 prompt/caching、不解冻冻结项。
- [x] 决定 proposal_id 批次与 unknown Rules strict reject，并记录 rationale。
- [x] 建立 spec/plan/tasks。

## Parser / State / Sidecar

- [x] SAFETY 专用 strict parser、typed hard/snapshot、稳定错误码与 digest。
- [x] 缺文件 read fail closed；fresh init/template 创建；runtime 不自愈。
- [x] 原子 write、普通 write/reset preserve guidance + revision。
- [x] state/backend/doctor/reset/legacy 正反矩阵。

## Context

- [x] 四 ContextPurpose 注入受控 guidance 与 digest。
- [x] hardware 缺失/超限动作通道 fail closed；simulation 兼容警告。
- [x] guidance 独立预算；reply 显式截断。
- [x] world/capability 摘要保留安全关键字段/bounds。
- [x] context golden、真实 planner/chat/tool-loop 回归。

## Gate / Watch

- [x] SafetyGate 只接受 `HardSafetyPolicy`，炸药桩证明 guidance 不可传。
- [x] 每 action claim 后、Gate 前 fresh-read policy。
- [x] revision/hard digest/guidance digest/malformed 取消当前与同 proposal 剩余；其他 proposal 保留。
- [x] drift 不 halt；claimed terminalization 不依赖损坏策略；`driver.execute` 零后续调用。
- [x] feedback 记录 revision、hard/guidance/identity digest 与 old/new 证据。

## Car / 交付

- [x] tracked car SAFETY template 含 Level 0 完整 guidance。
- [x] clean-checkout/fresh-init 测试证明模板进入 active workspace 与四路 context。
- [x] 默认禁运动、轮空边界与无真机连接保持。

### 逐项核查证据（2026-08-14）

| 行 | 结论与可重复证据 |
| --- | --- |
| 14 | `state/safety_policy.py` 专用 unique-key front matter/Rules loader、frozen typed policy/snapshot 与三类 digest；`test_sidecar_behavior.py` 覆盖 duplicate/missing/ambiguous/cross-section/schema/owner/revision/type/range/unknown/unreadable 反例 |
| 15 | `sqlite.initialize()` 只在 fresh DB 前创建/验证模板，existing DB 先读策略；missing/malformed template、runtime 不自愈与零 `state.db` 反例已覆盖 |
| 16 | SAFETY 同目录 temp + flush/fsync + replace；write/reset preserve guidance/revision；replace failure 保旧文件、malformed reset 保 DB 证据已覆盖 |
| 17 | backend/state-check/API health/doctor/reset/legacy 矩阵覆盖 missing、malformed、hardware missing/over-budget、simulation warning 与旧 workspace fail-closed |
| 21–25 | `context_builder` 四 purpose 参数化 golden；真实 `LLMPlanner`、ProposalService、chat 非流/流式/tool-loop 覆盖零 provider/零 action，独立 guidance budget 与 TOF/motion/bounds 摘要字段 |
| 29 | `SafetyGate` runtime type check；hostile guidance Snapshot 与 dict 均拒绝，只传 `.hard` 后 Gate 无 guidance 属性 |
| 30 | Watch 顺序锁定 baseline → claim → fresh snapshot → Gate；legacy 测试在第二次读取变更策略并证明 execute 前拒绝 |
| 31 | revision、无 revision hard digest、guidance digest、malformed 四组；current claimed + persisted same-proposal siblings 单 SQLite transaction，trigger 注入失败整批 rollback；other correlated proposal 保留、legacy 单 action |
| 32 | drift 后零后续 `driver.execute`、零 halt；malformed 时批次 terminalization 不读 SAFETY，owner CAS 仍生效 |
| 33 | policy preflight feedback 精确断言 top-level/baseline/current 的 revision 与 hard/guidance/identity digest，以及 malformed `current=null` + stable policy error |
| 37–39 | tracked `car_agent/SAFETY.template.md` 内容矩阵、clean fresh init 四路 context、缺 motion limits 不发布运动；socket 测试只连本机 fake server，无真机连接 |

## 收工

- [x] 专项矩阵通过。

  2026-08-14 closure 专项：sidecar/backend/state/SafetyGate/context/planner/proposal/chat/tool-loop/Watch/car/API/Markdown/retrieval/current-docs 共 `443 passed, 1 warning`，耗时 132.99s。

- [x] Python full `pytest` 通过；若前端变更则 build 通过。

  2026-08-14 closure 最终全量：`639 passed, 1 warning`，耗时 200.02s；唯一警告仍为既有 Starlette `TestClient`/`httpx` deprecation。本轮未改 frontend 源码或文案，按 AGENTS 门禁无需本地 frontend build。

  实施阶段提交 `9a25d0c` 的全量为 `619 passed, 1 warning`。当时的 6 条失败已定性并修复：

  | 失败 | 定性 | 处理 |
  | --- | --- | --- |
  | `test_car_agent_driver::test_watch_safety_gate_rejects_out_of_bounds_car_motion_before_driver` | 夹具账，非安全回归 | `car_1` 是 hardware profile，本条的 Gate 前 guidance 拒绝正是 spec §5 的设计意图（`gate_decisions` 因此为 0）。夹具补 Agent Guidance 后动作才走到 Gate 的 bounds 检查，原断言语义不变 |
  | `test_markdown_protocol::test_extract_markdown_sections_does_not_treat_info_fence_as_closer` | 实现缺陷 | `extract_markdown_sections` 原先把已开启 fence 内的 info fence 当无操作，导致内层 ``` 关掉外层、暴露其后所有标题。改为嵌套深度计数：info fence 只能开不能关，在已开启 fence 内计为嵌套 |
  | `test_retrieval_foundation::test_sqlite_initialize_migrates_memory_chunk_schema` | 夹具账 | 手搓 legacy DB 的 workspace 缺 SAFETY；已有 workspace 不自愈是 spec §4 的正确行为，夹具补 SAFETY 文件 |
  | `test_retrieval_foundation::test_chat_runtime_retrieval_enabled_adds_untrusted_context_without_overrides` | 夹具账 | 同上，补 Agent Guidance 清除 hardware 动作通道前置条件 |
  | `test_current_docs` ×2 | 文档契约随主动去重漂移 | vnext §0 的主链图与 SPEC §1 逐字重复，已于 2026-08-13 主动删除并改为引用。断言改为校验「委托到 SPEC §1」与新增的 living contract / frozen registry 身份边界，不回滚文档 |
- [x] 更新 SPEC 状态、REFACTORING §1/§2/§3/§4 和本 tasks 证据；按触发层复核 vnext §3/§4/§5/§5.1/§7。
- [x] 独立 review 无 Critical/Important。

  2026-08-14 三路独立终审覆盖实现现实、文档一致性与安全风险，结论均为 Ready，合计 Critical 0 / Important 0；提出的尾随空格、Watch 死变量与 caller metadata 防回归三个 Minor 已在提交前处理。

- [ ] 精确 staging，排除用户已有 dirty 变更；commit 并 push。
