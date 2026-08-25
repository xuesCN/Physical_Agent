# 005：执行计划

## 顺序总览

1. 锁定场景、hard/semantic 判定和脱敏输出格式。
2. 提取独立、可单测的多轮 eval 数据模型与 scorer。
3. 实现真实 ChatRuntime runner；每场景独立 workspace、轮次内共享状态。
4. 用 fake responder 覆盖 scorer 正反例、异常隔离与请求侧零 Action Board 变化。
5. 运行真实 provider baseline，按规格归因，不改 prompt。
6. 跑专项/full pytest，更新 SPEC、REFACTORING 与本账本，提交并 push。

## 实施口径

- runner 放在 `scripts/f0_multiturn_eval.py`，场景放在 `evals/moce_multiturn/scenarios.yaml`；保持一个显式入口，不增加生产 API。
- scoring 只消费公开 `ChatRuntime.respond()` 结果和 StateStore public reads；不得调用私有 provider 解析器来“修正”模型答案。
- 场景初始化用 `write_default_config()` + SQLite StateStore public writes 写入冻结的 simulation capabilities/world；不进入 watch、driver loader/instance 或 execute 路径。聊天阶段使用 API-safe flags 禁用 code/hardware integration skill routing。
- `agent_output.actions` 是 draft 真源；Action Board 是运行真源。两者分别评分，不从 reply 文本反解析动作。
- 自动 capability/schema/Gate-task checks 对所有 action 生效；场景特定期望只描述允许/禁止 capability、动作数、refusal/memory 和 reply 语义。
- 单个场景/provider 异常记录为失败并继续后续场景；不得让一次异常丢失已完成结果。

## 关键文件

| 层 | 文件 | 用途 |
| --- | --- | --- |
| eval | `scripts/f0_multiturn_eval.py` | 场景、runner、scorer、JSON/report 输出与 CLI |
| cases | `evals/moce_multiturn/scenarios.yaml` | 冻结的 dev/holdout/adversarial 多轮输入与期望 |
| test | `tests/test_f0_multiturn_eval.py` | scorer、异常隔离、状态边界与场景合同 |
| context | `physical_agent/agent/context_builder.py` | 只读被测对象；本轮不修改 |
| chat | `physical_agent/agent/chat_runtime.py` | 真实被测入口；本轮原则上不修改 |
| docs | `docs/f0-multiturn-eval-report.zh-CN.md` | 脱敏 baseline 与失败归因 |

## 回滚

eval 是旁路工具，无生产接线。回滚只需删除脚本、测试、005 文档和对应 SPEC/REFACTORING 记录；不会迁移数据库或改变 runtime 默认值。
