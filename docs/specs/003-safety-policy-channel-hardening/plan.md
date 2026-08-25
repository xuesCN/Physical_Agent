# 003：执行计划

## 顺序总览

| 阶段 | 内容 | 门槛 |
| --- | --- | --- |
| 1 | 严格 SAFETY parser、typed snapshot、原子 sidecar | malformed/missing 全部 fail closed |
| 2 | state 初始化、模板、write/reset preserve、doctor | existing workspace 不自愈；clean init 可交付 |
| 3 | 四路 context guidance 与安全字段预算 | hardware 动作通道缺失/超限零产出 |
| 4 | SafetyGate typed hard-only 边界 | guidance 无法传入 Gate |
| 5 | Watch per-action fresh policy 与 proposal 批次取消 | 变化/损坏时零后续 execute、无 halt |
| 6 | API/前端口径、完整矩阵与文档收口 | 专项、全量、diff/review 全绿 |

## 实施口径

1. SAFETY 专用解析集中在 state policy 模块；公共 Markdown helper 保持兼容。
2. 先建立 typed hard/snapshot，再改 call sites，避免一段时间继续传裸 dict 给 Gate。
3. template path 由 state factory 显式解析；只有 fresh initialize 能创建 active 文件。
4. context 只消费 `read_safety()` 的公共投影；Watch 只消费 typed snapshot。
5. drift 比较 policy identity，审计同时保留 hard/guidance/revision；取消按 trusted proposal correlation。
6. 每阶段先跑最小专项，最后跑 sidecar/state/backend/context/watch/car/API/safety 矩阵和全量。

## 回滚

本条不含数据库 migration。代码按 parser/types、state lifecycle、context、Gate/Watch、car template/tests 分层，可整体回滚单提交；active SAFETY 仍是 Markdown v1，回滚不迁移或改写用户文件。新模板只是 fresh init 来源，不成为第二真源。
