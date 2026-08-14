# 003：SAFETY 策略通道硬化

状态：已完成
日期：2026-08-12；收口：2026-08-14
对应账本：`SPEC.zh-CN.md` §4 `F3.1b / 003`

## 0. 目标

修复 SAFETY 文件真源在硬层解析和软层传递上的两个通道缺陷：任何缺失、残缺或类型错误的硬策略都必须 fail closed；设备安全语义只从受控的 `## Agent Guidance` 节进入 reply/proposal/planner/tool_loop 上下文。硬规则与 guidance 在类型、摘要、digest 和调用路径上隔离，确保 guidance 在结构上不可能进入或放宽 SafetyGate。

## 1. 不可破坏边界

1. `driver.execute()` 仍只出现在 watch 执行调用栈；请求、提案、LLM、context 和初始化路径不加载或执行 driver。
2. 每个物理 action 执行前仍必须经过 watch-owned SafetyGate；SAFETY 继续以 workspace 文件为唯一真源，不迁入数据库。
3. 本条不新增通用 TOF 语义 Gate，不把 prompt 描述成落地避障保障。Level 0 小车继续限定车轮架空；常态落地仍等待 Level 1 设备侧硬联锁。
4. 不改 prompt 措辞、few-shot、caching、LLM schema、F0 eval、自动 replan、无人值守或任何冻结项。

## 2. 策略文件合同

SAFETY v1 的合法结构固定为：

````markdown
---
schema: physical-agent/safety/v1
owner: human
revision: 1
---

# SAFETY

## Rules

```yaml
allow_autonomous_execution: true
require_human_approval_for_real_hardware: true
max_action_timeout_s: 30
forbid_duplicate_action_ids: true
```

## Agent Guidance

受控的设备安全语义。
````

硬层解析必须校验 exact schema、owner、正整数 revision、唯一且节内的 Rules YAML mapping，以及四个已知 key 的严格类型/范围。未知 Rules key 一律拒绝：理由是 Gate 不执行未知键，容忍它会制造“规则已生效”的错误安全感。通用 Markdown parser 不因此收紧；SAFETY 使用专用 parser。

`Agent Guidance` 只允许收紧认知行为，不能授予能力、关闭审批、改写 hard rules 或 execution contract。仅精确读取该节，不读取任意散文、示例或后续 YAML。

## 3. 类型与结构隔离

内部定义两个不可变类型：

- `HardSafetyPolicy`：仅含 revision、validated rules、hard digest。
- `SafetyPolicySnapshot`：含 metadata、`hard`、可选 guidance、guidance digest、identity digest。

SafetyGate 构造函数只接受 `HardSafetyPolicy`，不接受 dict 或 `SafetyPolicySnapshot`；该模块不能读取、访问或解释 guidance。现有 `policy_digest` 继续表示 Gate 实际执行的 hard rules，另记 guidance/identity digest，禁止把软层混入 hard digest 冒充强制执行。

公共 `read_safety()` 保持 dict 兼容，返回 metadata、rules、agent_guidance 和三类 digest；Watch 使用 typed `read_safety_snapshot()`。

## 4. 生命周期与 fail-closed

- 普通 read 不创建 SAFETY；缺文件、缺 Rules、错 schema/owner/revision、错类型、未知 key 都抛稳定 policy error。
- 只有全新 workspace 的显式初始化可从默认或已验证模板创建 SAFETY。已有数据库/runtime 启动不得静默修复被删文件。
- SAFETY 写入采用同目录临时文件、flush/fsync、原子 replace，避免逐动作读取撞见半文件。
- 普通 `write_safety(rules)` 保留 guidance，并递增 revision；workspace reset 恢复 hard defaults、保留 guidance并递增 revision。清除 guidance 不复用普通 reset，本条不增加隐式清除入口。
- reset 必须先解析并保留策略，再破坏数据库状态；解析失败时整个 reset 不得开始。

## 5. Guidance 执行策略

- 任一 hardware profile 缺 guidance、guidance 空白或超出动作通道预算：proposal/planner/tool_loop 不调用 LLM、不追加 action；Watch 在 Gate 前结构化拒绝，driver 零执行。
- 纯 simulation 缺 guidance 维持兼容放行，但 doctor/诊断明确警告。
- reply 是非动作通道，可在固定上限内截断，并显式输出 `truncated: true`；不得静默丢失。
- 四个 `ContextPurpose` 合约都注入同一 budgeted safety 结构；实际 planner 路径另有集成测试。
- guidance 使用独立配额，不占用 world/capabilities 的单项预算。world 摘要必须保留 `tof_available/tof_valid/tof_mm/moving/motor_cmd/bench_only/watchdog_tripped`；capability 摘要保留 execution_mode、constraints/bounds。

## 6. Watch 策略新鲜度

Watch 在 step 开始建立 baseline，并在每条 action claim 后、Gate 前 fresh-read。比较 revision + hard digest + guidance digest：任一变化或解析失败均在 driver.execute 前拒绝当前 action，并取消同一可信 `proposal_id` 的剩余 pending actions；其他 proposal 留给下一 step 使用新 baseline。legacy 无 proposal correlation 按单 action 处理。

同 proposal 的 current claimed action 与 pending siblings 必须在一个 SQLite transaction 内失效，proposal correlation 从 claimed row 的持久化 metadata 派生；事务失败整体回滚，不能留下半批。新鲜度线性化点定义为 claim 后读取的 snapshot 通过 Gate：此后该 action 视为 in-flight，文件更新从下一条 action 生效；这不是 writer/execute 共锁，也不声称能撤销已越过该点的设备命令。

这一定义“批次”为一个 trusted proposal，而不是整个 watch step：一个 step 可包含多个独立 proposal，取消全部会误伤无关用户工作。

策略变化使用稳定机器码，不调用 halt；halt 保留给设备异常或未知物理状态。已经在飞的前一动作无法由文件更新撤销，本条只保证其后的动作零执行。claimed action 的 terminalization 不得重新依赖当前已损坏的 SAFETY 解析。

## 7. Car 模板与交付

新增 tracked `car_agent/SAFETY.template.md`。State factory 从 config 所在目录显式传入 sibling 模板，只在 fresh workspace 初始化时验证并复制；不得从被 `.gitignore` 忽略的 active workspace 反推模板。

模板至少覆盖：Level 0 仅轮空、人工值守与可立即断电、无本地避障、TOF 仅在 available+valid 时可解释、无效读数等于未知而非空旷、派生 status 优先、speed 是开环 PWM、watchdog 不是避障或急停保证。

clean-checkout 测试必须证明模板可交付、初始化后进入四个 context purpose，且默认禁运动配置不变。

## 8. 验收门禁

- parser/sidecar：正例 round-trip；所有缺失/残缺/错类型/跨节/未知 key 反例 fail closed；原子写和 guidance preserve。
- state/backend/reset/doctor：existing workspace 缺策略零修复；hardware 缺 guidance fail；simulation warning；reset preserve；legacy fail-closed 矩阵。
- SafetyGate：只接受 typed hard policy；guidance 不能进入 Gate；hard digest 语义不变。
- context：四 purpose + 真实 planner route；独立 budget；安全字段摘要保留；动作通道超限零 LLM/零 action。
- watch：逐 action fresh-read；revision 变、hard/guidance digest 变、malformed 均零后续 `driver.execute`；只取消同 proposal；批次失效单事务；不 halt；审计包含 old/new identity。
- car：tracked template + clean initialization；Level 0 约束完整；不连接真机。
- 全量 `pytest`；若修改 frontend 源码或文案，再跑 `tsc -b && vite build`。

## 9. 范围外

动态 world freshness、TOF 阈值标定、落地运动授权、Level 1 interlock、prompt/eval/caching、provider/model 选择、SAFETY v2 或通用 policy language。
