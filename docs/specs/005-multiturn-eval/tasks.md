# 005：任务与验收账本

## 规格与边界

- [x] 读取 SPEC §0/§4、PLAYBOOK F0、prompt/context brief §6–§8 与 REFACTORING §3/§4。
- [x] 记录 F0.1 显式重启：只建多轮 eval/baseline，不改 prompt，不解冻自动 replan/F6/VNext-3/4。
- [x] 锁定 simulation-only、proposal-only、deterministic hard grading 与脱敏产物。

## 实现

- [x] V1 十个多轮场景按 dev/holdout/adversarial 固定，suite SHA=`c767ba5dbbf9070f1e647531d688b68704a83efdd28035a9e23878b4fbe564cd`。
- [x] ChatRuntime runner 每场景隔离、每轮共享状态并持续落盘结果。
- [x] scorer 覆盖通用 hard checks 与场景 semantic checks。
- [x] provider/structured error 单场景隔离且结果可继续生成。
- [x] pytest 不访问网络、不读取真实密钥。

## Baseline

- [x] 经用户明确授权，用项目根 `.env` 与空 settings workspace 运行真实 provider：stream smoke + nonstream 10 场景/20 轮诊断。
- [x] 输出 ignored workspace 脱敏 JSON 原始结果与仓库内中文汇总报告。
- [x] 对失败逐项归因：`15 memory + 1 clarification + 2 linear dependency`；旧 grader 2 个假红已移除。
- [x] baseline 前后 system prompt 零改动；运行内 prompt SHA 一致，版本控制无 prompt 文件 diff。

## 验收

- [x] `pytest tests/test_f0_multiturn_eval.py`：29 passed。
- [x] 安全边界/ChatRuntime/context/state/docs 受影响专项：148 passed。
- [x] 全量 `pytest`：668 passed。
- [x] `git diff --cached --check` clean。
- [x] SPEC §4、PLAYBOOK、REFACTORING §1/§2/§3/§4 与本账本同步；本轮未触发 vnext 分层复核章节。
- [ ] commit 并 push，且不纳入既有用户未跟踪文件。
