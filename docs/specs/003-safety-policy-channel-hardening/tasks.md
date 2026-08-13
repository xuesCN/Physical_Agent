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
- [ ] Python full `pytest` 通过；若前端变更则 build 通过。
- [ ] 更新 SPEC 状态、REFACTORING §1/§2/§3/§4 和本 tasks 证据。
- [ ] 独立 review 无 Critical/Important。
- [ ] 精确 staging，排除用户已有 dirty 变更；commit 并 push。
