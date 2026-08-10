# 002：执行计划

## 顺序总览

| 步骤 | 内容 | 状态 | 门槛 |
| --- | --- | --- | --- |
| 1 | 建立规格、核对历史/冻结边界 | ✅ | spec/plan/tasks 齐全；明确 A1.1b 维护例外 |
| 2 | Pydantic 单真源与 provider strict 预检 | ✅ | chat/planner schema 无手写双真源；兼容/不兼容正测 |
| 3 | 非流式有界修复、typed error、validation trace | ✅ | retry success/exhausted/schema bug/trace 正反用例 |
| 4 | API/stream fail-closed 收口 | ✅ | HTTP typed status；stream 不二次调用、不落 Draft/Action |
| 5 | 全量验证、文档收口、commit/push | 进行中 | pytest、safety、diff-check 全绿并更新账本 |

## 实施口径

1. Pydantic model 是 schema 和本地字段验证的唯一来源；现有 public/persistence models 不为此收紧兼容面。
2. structured runner 只捕获明确标记为 retryable 的输出语法/字段错误，最多一次；schema 自身错误立即失败。
3. repair prompt 携带上次 raw output 与精简 issues，明确“只修格式、不改变意图、不新增动作”。每次 provider 调用仍独立 trace；失败另写 validation-stage trace。
4. streaming 继续一次 authoritative stream：可在完整响应到齐后验证，但任何已产出 byte 后的失败只落 error/partial，不修复重调。
5. API 把 structured-output exhaustion 映射为稳定 code/status；explicit/auto chat 都对 structured exhaustion fail closed，避免 fallback 偷产 Draft。只有非结构化 provider 可用性错误保留既有 auto rule fallback；provider refusal 始终转成 reply-only refusal turn。

## 回滚

代码按新 contract module、adapter runner、call-site/API、tests/docs 分层，可整体回退本条目提交；不含 SQLite migration、配置格式或外部数据变更。
