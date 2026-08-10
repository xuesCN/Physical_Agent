# 002：LLM 结构化输出错误处理硬化

状态：收尾中

日期：2026-08-10

对应账本：`SPEC.zh-CN.md` §4 `A1.1b`

## 0. 目标

把 chat/planner 的 LLM-facing 输出契约收敛为 Pydantic 单真源；在 provider structured-output 能力、JSON/Pydantic 本地校验、有限格式修复和 API/trace 收口之间建立一条可测试的失败管线。任何失败都只能得到“无 Draft/无 Action”的 typed failure，不能扩大到执行、自动 replan 或安全决策。

## 1. 不可破坏的边界

1. `driver.execute()` 仍只出现在 watch 调用栈，本条目不 import 或加载 driver/watch。
2. 修复重试只处理尚未被接受的 JSON/字段契约；结果仍须经过 PlanCompiler、Action Board、审批、watch 和 SafetyGate。
3. 流式响应一旦向消费者产出任一 provider byte，不进行第二次 provider 决策调用，避免 reply/actions 跨 turn 拼接。
4. 不重试 provider refusal、业务不可满足、Gate reject、expected violation、动作失败或其他语义/安全结果。
5. 本条目是用户明确请求的 A1 维护例外；不解冻 F0 实验、自动 replan、VNext-4 ledger/registry 或无人值守闭环。

## 2. 范围与决策

- 新建封闭、strict 的 LLM contract models；chat/planner JSON Schema 只从这些模型生成，持久化协议模型保持兼容。
- provider strict schema 先做本地兼容性预检。兼容时使用 `json_schema`; 现有 `params`/`expected.value` 等自由 JSON 无法满足 OpenAI strict 的封闭对象要求时，直接走 JSON mode + 本地 Pydantic 强校验，不制造必然 400。
- 非流式格式失败默认只修复一次；错误反馈只包含稳定 path/code/message，提示不得改变意图或发明动作。
- 建立 structured-output 专用异常与 API 映射；validation-stage trace 记录 attempt/code，但不改变现有 transport trace。
- 不引入 Instructor/LangChain/PydanticAI 等新依赖，保留现有 OpenAI-compatible adapter。

## 3. 总体验收

- 第一次坏输出、第二次合法输出成功；两次均坏时返回 typed error。
- schema 编程错误、provider/transport 错误和 refusal 不进入格式修复循环。
- chat/planner 未知顶层或 action 字段 fail closed；历史合法 payload 保持可用。
- `/api/tasks/submit` 和显式 LLM `/api/chat` 不再把 output validation 暴露为裸 500；SSE 保持单 turn、脱敏且无 `agent_output`。
- 所有失败路径 pending actions 为 0，安全边界测试通过。
- 全量 `pytest` 通过；未改前端源码则不要求前端重建。

当前证据：专项 `143 passed, 1 warning`；Python full `555 passed, 1 warning`；独立终审无 P0/P1。commit/push 完成后关闭本规格。

## 4. 范围外

- tool-loop 参数自修复、动态 per-capability strict schema、自动 replan 与执行重试。
- approval、PlanCompiler、SafetyGate、SAFETY.md、expected evaluator 与 driver 行为变更。
- 新的 Run/Turn/Event 数据库、外部观测平台或 LLM 框架。
