# 002：任务与验收账本

状态图例：`[x]` 已完成；`[ ]` 未完成。

## 规格与边界

- [x] 读取 SPEC §0/§4、PLAYBOOK F0、REFACTORING A1/R5/§3/§4。
- [x] 明确 A1.1b scoped maintenance exception，不解冻 F0/auto-replan/VNext-4。
- [x] 建立 spec/plan/tasks。

## 实现

- [x] 新增 chat/planner LLM Pydantic contracts，删除对应手写 schema 双真源。
- [x] strict schema 本地预检；兼容 schema 走 strict，不兼容 schema 直接 JSON mode。
- [x] structured-output typed error 与一次非流式 repair retry。
- [x] validation-stage trace 包含 attempt/code/issues。
- [x] task/chat API typed status；stream 保持单 turn fail closed。

## 正向验收

- [x] 首次合法输出一次完成。
- [x] 首次格式错误、第二次修复后成功。
- [x] Chat/Planner 合法 metadata/expected/safety_intent 保持 wire 兼容。
- [x] strict-compatible generic schema 仍发送 `strict=true`。

## 反向验收

- [x] 两次格式错误后 exhaustion，稳定 error code/issues/attempts。
- [x] schema 自身错误不重试；provider 429/timeout/refusal 不进入格式修复。
- [x] 未知顶层/action/metadata 字段被拒绝。
- [x] 流式校验失败不发起第二次 provider 调用，不产生 AgentOutput/pending action。
- [x] task/chat API 不返回裸 500，错误消息不泄露 key。
- [x] validation failure trace 可观测，trace 关闭时零写入。

## 收工

- [x] 专项测试通过：`143 passed, 1 warning`。
- [x] 全量 `pytest` 与 safety boundary 通过：`555 passed, 1 warning`。
- [x] 更新 SPEC §4、PLAYBOOK A1.1b、REFACTORING §1/§2/§3/§4。
- [x] `git diff --check` clean；只提交本轮文件，不吞并用户已有改动。
- [ ] commit 并 push。
