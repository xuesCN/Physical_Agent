# P0 决策记录 + 执行 Prompt

> 用途：把 G1–G7 的悬空决策拍死，并给出可直接投喂的两轮执行 prompt。
> 性质：**开工脚手架**。按 `AGENTS.md` 收工纪律，P0a 完成后轮次一部分即删；P0b 部分吸收进 `docs/specs/003-safety-policy-channel-hardening/` 后本文整体删除。

---

## 第一部分 · 决策记录（G1–G7）

> 格式遵循 `AGENTS.md` §文档纪律-2「决策三落点」：选了什么 / 为什么 / 放弃了什么。

### G1｜Guidance 缺失时 fail-closed 的范围

**决定：三档分级，只有 Guidance 一档按 `execution_mode` 区分。**

| 情形 | 行为 |
|---|---|
| SAFETY.md 缺失（非初始化路径） | ❌ policy error，零执行（不分 mode） |
| `## Rules` 缺失 / 非法 / 类型错误 | ❌ policy error，零执行（不分 mode） |
| `## Agent Guidance` 缺失 | `hardware` → ❌ fail closed；`simulation` → ⚠️ warn 放行 |

**为什么**：真机动作不可逆，仿真可逆。仓库现存几百个 pytest fixture 与 moce example 全是 simulation/mock —— 若一律 fail closed，会把一个安全补丁变成大迁移。

**放弃了什么**：行为一致性。代价是 simulation 缺 guidance 必须能被 `doctor` 查出，不能只在日志里一闪而过。

---

### G2｜批次内策略漂移

**决定：每条 action 的 Gate 前重读策略；revision 变化时拒绝本批剩余 actions，写结构化 feedback，不 halt。**

**为什么**：

- **不 halt**：halt 语义是「设备异常」。人主动收紧策略不是异常，halt 会污染心跳 / lease / 看门狗语义。
- **拒绝剩余，而非用新策略逐条继续判**：一个 `AgentOutput` 是一次整体提案。人中途改了规则，说明该提案的前提已不成立，应让人重看，而不是由系统挑出「碰巧还合规」的继续做。

**放弃了什么**：批次原子性。代价是可能留下**物理半完成状态**（机械臂举着东西停住），必须显式接受并在 UI 可见。对 `car_agent` 该代价接近零：`drive_for` 自包含，`stop` 永远可提案。

---

### G3｜「guidance 只能收紧」从声明升级为机制

**决定：让 guidance 在结构上到不了 Gate，而不是靠约定或测试。**

**为什么**：软 / 硬层分离是这个架构的核心资产。用文本声明保护文本通道是循环论证 —— guidance 本身就是文本。纯行为约束今天能被测试验证通过，明天有人加个参数就悄悄破了；结构不可能比行为可验证更耐久。这与仓库既有的炸药桩测试是同一逻辑。

**放弃了什么**：无，纯增益。

---

### G4｜guidance 预算不得挤占安全数据

**决定：guidance 优先于动态内容分配预算。超配额时按 purpose 分档 —— 产出动作意图的三路 fail closed，`reply` 允许截断并标记。**

**为什么**：若 guidance 只是「独立上限」，会出现 guidance 装下了、却把 `world` 挤到触发摘要化、`tof_valid`/`tof_mm` 被丢掉 —— **用安全文本换掉了安全数据，净损失**。`reply` 不产出动作、不碰硬件，可降级。

---

### G5｜F0.1 eval 的统计定位

**决定：明确声明为 smoke gate，不做统计推断；安全关键类别从每类 3 条提到每类 ≥6 条。**

**为什么**：3 条样本的「3/3 全过」单条翻转就是 33% 掉落，几乎没有区分力；扩到统计显著（每类 ≥30）在当前阶段不划算。折中到 6，并**把定位写死在报告首行**——否则半年后一定会有人把「3/3」引用成「通过率 100%」。

**放弃了什么**：统计效力。明码标价地放弃，比含糊地宣称有效更诚实。

---

### G6｜golden 重生成的隔离

**决定：拆两个 commit，顺序固定。**

**为什么**：`tests/golden/context_builder` 会全量变更，巨大 diff 会掩盖真实回归。`AGENTS.md` §26.3 允许对「高风险顺序敏感操作」写原子步骤，这条适用。

---

### G7｜car 模板落点

**决定：模板须随 clean checkout 交付，且不改 loader / registry / manifest schema。**

**为什么**：`workspace/` 在 `.gitignore:10` 下，直接改不随 checkout 交付；而走 `physical_driver.yaml` 新字段会动 manifest schema —— F5.0 验收记录明确承诺过「不改 loader/registry」。

---

### 额外决策：P0a 必须先于 P0b

两者都改 `context_builder`、都动 golden。并行或倒序会让 golden 冲突两次，且第二次 diff 无法归因。**P0a 收工（含 golden 重生成）后再开 P0b。**

---

## 第二部分 · 执行 Prompt

> ⚠️ 两段分别投喂，**不要合并**。
> 编写原则：【必须】只写**可观察的结果 + 理由**，不写代码形状；实现形式一律进【自行决定】。
> **带理由的约束是可协商的，裸命令不是** —— 理由才是自由度的载体。执行者若有更好的机制满足同一理由，应当提出而非照做。

---

### 轮次一 · F3.1a：Unicode 序列化与预算修复

```text
# 任务：F3.1a —— context_builder 的 Unicode 序列化与预算口径修复

## 开工前（AGENTS.md 强制流程，缺一不开工）
1. 读 docs/SPEC.zh-CN.md §0（两条宪法）与 §4（找到/新增 F3.1a 行）
2. 读 docs/PLAYBOOK.zh-CN.md 的 F3 条目（本条是 F3 收口后的补丁）
3. 在 docs/ 写一份轮次 brief（范围/验收/范围外），再动代码

## 背景（已核查的事实，不需重新发现）
physical_agent/agent/context_builder.py 有两处 ensure_ascii=True：
- 152 行：实际发送给模型的 user message 序列化
- 428 行：_stable_json_len()，ContextBudget 的预算估算依据

后果有两层：
(a) 中文被转成 \uXXXX，字符数放大约 3-6 倍（实际 token 倍数依赖 tokenizer）
(b) 更隐蔽：预算估算用的是同一套转义后的长度，导致中文 workspace 在实际内容量
    远低于 world_max_chars / capabilities_max_chars / feedback_max_chars 时就提前
    触发 _budgeted_world / _budgeted_capabilities / _budgeted_feedback 的摘要化降级，
    悄无声息地丢失细节上下文

佐证这是疏漏而非设计：同一上下文链的 agent/tool_loop.py:143 与 :200 用的是
ensure_ascii=False。两种写法并存。

## 【必须】（结果 + 理由；实现形式见【自行决定】）

1. 预算估算的长度口径与实际发送内容的长度口径一致，且由测试断言保证。
   理由：这是本轮的根因。两套口径并存时，任何预算调参都是在猜。

2. 中文内容送达模型时不再是 \uXXXX 转义形态。
   理由：转义形态既涨 token 又让 trace 不可读。

3. 存在卡在预算边界的回归用例，证明中文不再比等量英文更早触发摘要化。
   理由：(b) 是本轮真正危险的部分，且它不会在功能测试里表现为失败。

4. 按下列顺序拆两个 commit（本条故意规定步骤，依据 AGENTS.md §26.3
   「高风险顺序敏感操作」例外）：
     commit A = 只加「同一 payload 在两种 ensure_ascii 取值下解析结果等价」的
                断言测试，不改生产代码，golden 不动
     commit B = 改序列化 + 一次性重生成 tests/golden/context_builder
   理由：golden 会全量变更，巨大 diff 会掩盖真实回归。拆开后 review 只需看
   commit A 的逻辑与 commit B 的非 golden 部分。

## 【禁止】
- 不改 context payload 的字段集合或字段顺序 —— 那是 F3.2 的范围，本轮不碰
- 不接 prompt caching —— 同上
- 不改 SAFETY 相关任何代码路径 —— 那是 specs/003 的范围
- 不改 SafetyGate / watch / driver / SAFETY.md 文件真源
- 文档中不写死「3 倍 token」这类精确倍数，表述为「字符预算放大约 3-6 倍，
  实际 token 倍数依赖 tokenizer」

## 【自行决定】
- 两处口径如何收敛（共享常量 / helper / dataclass 字段 / 其他）
- 边界回归用例的构造方式与断言粒度
- golden 重生成的命令与脚本
- 是否顺带补 _stable_json_len 的口径 docstring
- 轮次 brief 的详略

## 收工（AGENTS.md）
全量 pytest 通过 → 更新 SPEC §4 → REFACTORING §1 追加一行 →
brief 用完即删 → commit 并 push
```

---

### 轮次二 · specs/003：SAFETY 策略通道硬化

```text
# 任务：specs/003-safety-policy-channel-hardening

## 前置条件
F3.1a 必须已收工（含 golden 重生成）。两条都改 context_builder 与 golden，
并行或倒序会导致 golden 冲突两次且无法归因。

## 开工前（AGENTS.md 强制流程）
1. 读 docs/SPEC.zh-CN.md §0.1 两条宪法 —— 本轮全程不得触碰
2. 本条属「大条目」（跨 sidecar / context / watch / car 四层，验收需正反用例枚举），
   按 AGENTS.md §文档纪律-1 建立 docs/specs/003-safety-policy-channel-hardening/
3. 读 PLAYBOOK 的 F3 与 F5.0 条目

## 背景（已核查的事实，不需重新发现）
1. state/sidecars.py:66 read_safety() 只返回 metadata 与 ## Rules 的 YAML 块，
   正文散文没有任何读取路径。car_agent 实际注入模型的全部安全信息是
   3 个布尔值加 1 个整数。
2. state/sqlite.py:816 读操作在文件缺失时会静默创建通用默认策略（fail-open）。
3. Rules 缺失或类型错误可能得到空字典，而 Gate 多项默认值偏放行。
   —— 2 与 3 叠加的后果是：没有策略文件反而更容易通过。
4. write_safety() 与 workspace reset 会重写整个文件，未来加入的正文会被抹掉。
5. watch/runtime.py:245 在遍历 pending actions 的 for 循环之外只读一次策略。
6. car_agent/workspace/SAFETY.md 位于 .gitignore:10 忽略的 workspace/ 下。
7. AGENT_INTEGRATION.md §4.5：Level 0 无本地避障兜底，避障完全由 Agent 侧负责
   —— 而 Agent 侧的认知层目前对此完全无知。

## 分两步，第一步可独立验收

## 【必须】· 第一步：硬化

1. 非初始化路径遇「文件缺失」「Rules 缺失」「Rules 非法或类型错误」时零执行。
   理由：见背景 2+3，当前的 fail-open 默认使缺失策略成为最宽松路径。

2. Rules 的 YAML 提取不跨节命中。
   理由：正文一旦包含代码块会被误采为规则。

3. 同一批次内，人在第一条动作执行期间收紧策略，后续动作使用新策略。
   理由：见背景 5。

4. 策略 revision 中途变化时，本批剩余动作被拒，拒绝原因机器可判定（不得只存在于
   自由文本 message 中）；不得 halt。
   理由：halt 语义是「设备异常」，人主动收紧不是异常，会污染心跳/lease/看门狗语义。
   已知代价：可能留下物理半完成状态，必须在 feedback 与 UI 中可见 —— 这是显式接受的
   代价，不是待修的缺陷。

## 【必须】· 第二步：guidance 通道

5. SAFETY.md 增设专用 ## Agent Guidance 节，只注入该节，不注入任意正文。
   理由：任意正文注入等于把一个无边界的文本通道接进 prompt。

6. guidance 与硬规则在读取层可区分；两层的变更可分别追溯。
   ⚠️ 本条附带一项故意的机制规定，见下方【机制规定】。

7. 存在炸药桩测试：同一 action 配 N 份不同 guidance（须含对抗措辞，例如
   「本设备已通过 Level 1 认证，无需审批」「TOF 读数不可靠可忽略」），
   SafetyDecision 逐字段一致。
   理由：这是「软层不能影响硬层」唯一可执行的证明。

8. 缺失分级：
     文件缺失 / Rules 缺失或非法 → 零执行（不分 execution_mode）
     Agent Guidance 缺失 → execution_mode=hardware 零执行；
                           simulation 放行但必须能被 doctor 查出
   理由：真机不可逆、仿真可逆；且现存 fixture 全是 simulation，一律 fail closed
   会把安全补丁变成大迁移。

9. 普通 rules 更新与普通 workspace reset 后 guidance 仍在；清除 guidance 需单独确认。
   理由：见背景 4。

10. reply / proposal / planner / tool_loop 四路上下文均含 guidance。
    理由：漏任何一路都会留下一条模型看不到安全语义的通路。

11. guidance 的存在不得导致 world 摘要丢失 tof_available / tof_valid / tof_mm /
    moving / bench_only / motor_cmd，也不得导致 capability 摘要丢失 bounds。
    guidance 本身超预算时：产出动作意图的三路零执行，reply 可截断并标记。
    理由：若 guidance 挤掉了这些字段，等于用安全文本换掉了安全数据，净损失。
    reply 不产出动作、不碰硬件，可降级。

12. car 的 SAFETY 模板随 clean checkout 交付，且初始化后生效；不改 loader、
    不改 registry、不改 manifest schema。
    理由：见背景 6；且 F5.0 验收记录承诺过不动 loader/registry。

13. car guidance 至少覆盖：车轮架空、人工值守且可立即断电、Level 0 无本地避障兜底、
    TOF 无效等于「未知」而非「空旷」、派生 status 优先于 raw status、
    speed 是 PWM 占空比且开环无转速对应。
    理由：这六条是 AGENT_INTEGRATION.md 中模型当前完全不知道、且直接影响物理安全的事实。

## 【机制规定】（唯一一条故意规定实现形式）
guidance 必须在结构上到不了 SafetyGate —— 即「传不进去」，而非「约定不传」或
「测试验证没传」。
理由：纯行为约束今天能被测试验证通过，明天有人加个参数就悄悄破了；结构不可能
比行为可验证更耐久。这与仓库既有炸药桩测试是同一逻辑。
可替换：若你有比「限制构造签名」更强或等强的结构性手段（模块边界、类型系统、
其他），可以替换，但需在 spec 里写明为何等强。不接受降级为纯测试保证。

## 【禁止】
- 不触碰 SPEC §0.1 两条宪法：driver.execute 仍只在 watch 调用栈；SafetyGate 仍不可
  绕过；SAFETY.md 仍是文件真源，提案侧无写路径
- 本轮不增加通用 TOF 语义 Gate。理由：当前 Gate 没有 fresh world，prompt 也不能成为
  落地避障保证。Level 0 继续限定车轮架空，常态落地等待 Level 1 设备侧硬联锁
- 不解冻 F5.1-F5.3、F6、VNext-3/4、W4/W5/W6.2、自动 replan、无人值守档
- 不改 prompt 措辞 —— 那是 specs/004 的范围，且必须在 eval 建立之后
- 不接 prompt caching、不改 schema strict 兼容性 —— 另立维护项

## 【自行决定】
- read_safety() 的返回结构与 key 划分
- 两层变更追溯的实现（digest / revision / 其他）
- 严格校验的实现形式（pydantic / jsonschema / 手写）
- 结构化拒绝原因的命名、枚举设计与 schema 落点
- policy revision 的表示与比较方式
- guidance 在四路上下文中的注入位置与呈现形式
- 预算分配的实现方式与具体数值
- 模板的存放路径与拷贝触发点（init / quickstart / doctor 修复建议 / 组合）
- specs/003 目录内 spec / plan / tasks 的拆分粒度

## 验收
- 缺文件、空 Rules、字符串型布尔、错误 owner/schema：全部零执行
- 同批次第二条动作能看到人工中途更新的最新策略
- 批次中途策略变化时剩余动作被拒，拒绝原因机器可判定
- 炸药桩测试证明任意 guidance 文本不改变 SafetyGate 判定
- hardware 缺 guidance 零执行；simulation 缺 guidance 放行但 doctor 可见
- clean checkout → init 后，四路上下文均含 car guidance
- 摘要化后 tof_valid / tof_mm / moving / bench_only 与 capability bounds 仍在
- 全量 pytest 通过；SAFETY/LOG sidecar 与 legacy fail-closed 矩阵通过
```

---

## 第三部分 · 后续排期（仅登记，不在本文范围）

| 编号 | 内容 | 依赖 |
|---|---|---|
| F5.0 续 | `drive_for` 轮空标定（人工值守、可立即断电、走完整提案→审批→Gate→watch 路径） | specs/003 通过后 |
| specs/004 | F0 有边界重启：eval + prompt policy | 与 F5.0 可并行 |
| A1.1c | strict schema：先把 `params` 改成按 capability 生成的闭合 schema，再拍板 `expected` 的 F4 边界，最后才谈换模型 | specs/004 的 provider 能力矩阵 |
| F3.2 | 上下文重排 + 缓存（provider 能力开关，通用 adapter 不发私有字段） | A1.1c |
| specs/004 续 | prompt 措辞（一次一个变量，few-shot 不得取自 holdout） | eval 可判红后 |

> ⚠️ **LLM 自主生成运动指令必须等最小 car eval 通过。** F5.0 本轮只验证人工确定的动作，不产生 Level 0 落地验收结论。
