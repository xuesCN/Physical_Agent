# 003：任务与验收账本

状态图例：`[x]` 完成；`[ ]` 未完成。

## 规格与边界

- [x] 读 SPEC §0/§4、PLAYBOOK、REFACTORING SAFETY/F3/F5.0 先例。
- [x] 明确不增加 TOF Gate、不调 prompt/caching、不解冻冻结项。
- [x] 决定 proposal_id 批次与 unknown Rules strict reject，并记录 rationale。
- [x] 建立 spec/plan/tasks。

## Parser / State / Sidecar

- [ ] SAFETY 专用 strict parser、typed hard/snapshot、稳定错误码与 digest。
- [ ] 缺文件 read fail closed；fresh init/template 创建；runtime 不自愈。
- [ ] 原子 write、普通 write/reset preserve guidance + revision。
- [ ] state/backend/doctor/reset/legacy 正反矩阵。

## Context

- [ ] 四 ContextPurpose 注入受控 guidance 与 digest。
- [ ] hardware 缺失/超限动作通道 fail closed；simulation 兼容警告。
- [ ] guidance 独立预算；reply 显式截断。
- [ ] world/capability 摘要保留安全关键字段/bounds。
- [ ] context golden、真实 planner/chat/tool-loop 回归。

## Gate / Watch

- [ ] SafetyGate 只接受 `HardSafetyPolicy`，炸药桩证明 guidance 不可传。
- [ ] 每 action claim 后、Gate 前 fresh-read policy。
- [ ] revision/digest/malformed 取消当前与同 proposal 剩余；其他 proposal 保留。
- [ ] drift 不 halt；claimed terminalization 不依赖损坏策略；driver 零后续调用。
- [ ] feedback 记录 revision、hard/guidance/identity digest 与 old/new 证据。

## Car / 交付

- [ ] tracked car SAFETY template 含 Level 0 完整 guidance。
- [ ] clean-checkout/fresh-init 测试证明模板进入 active workspace 与四路 context。
- [ ] 默认禁运动、轮空边界与无真机连接保持。

## 收工

- [ ] 专项矩阵通过。
- [x] Python full `pytest` 通过；若前端变更则 build 通过。

  2026-08-14 全量 `619 passed, 1 warning`（唯一警告是既有的 Starlette `TestClient`/`httpx` deprecation）。此前的 6 条失败已定性并修复：

  | 失败 | 定性 | 处理 |
  | --- | --- | --- |
  | `test_car_agent_driver::test_watch_safety_gate_rejects_out_of_bounds_car_motion_before_driver` | 夹具账，非安全回归 | `car_1` 是 hardware profile，本条的 Gate 前 guidance 拒绝正是 spec §5 的设计意图（`gate_decisions` 因此为 0）。夹具补 Agent Guidance 后动作才走到 Gate 的 bounds 检查，原断言语义不变 |
  | `test_markdown_protocol::test_extract_markdown_sections_does_not_treat_info_fence_as_closer` | 实现缺陷 | `extract_markdown_sections` 原先把已开启 fence 内的 info fence 当无操作，导致内层 ``` 关掉外层、暴露其后所有标题。改为嵌套深度计数：info fence 只能开不能关，在已开启 fence 内计为嵌套 |
  | `test_retrieval_foundation::test_sqlite_initialize_migrates_memory_chunk_schema` | 夹具账 | 手搓 legacy DB 的 workspace 缺 SAFETY；已有 workspace 不自愈是 spec §4 的正确行为，夹具补 SAFETY 文件 |
  | `test_retrieval_foundation::test_chat_runtime_retrieval_enabled_adds_untrusted_context_without_overrides` | 夹具账 | 同上，补 Agent Guidance 清除 hardware 动作通道前置条件 |
  | `test_current_docs` ×2 | 文档契约随主动去重漂移 | vnext §0 的主链图与 SPEC §1 逐字重复，已于 2026-08-13 主动删除并改为引用。断言改为校验「委托到 SPEC §1」与新增的 living contract / frozen registry 身份边界，不回滚文档 |
- [ ] 更新 SPEC 状态、REFACTORING §1/§2/§3/§4 和本 tasks 证据。
- [ ] 独立 review 无 Critical/Important。
- [ ] 精确 staging，排除用户已有 dirty 变更；commit 并 push。
