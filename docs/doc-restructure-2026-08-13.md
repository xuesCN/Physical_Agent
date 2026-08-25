# 文档元结构整理（2026-08-13）

对象：`docs/agent-architecture-vnext.zh-CN.md`
目标：划清身份边界、消除与 `SPEC.zh-CN.md` 的重复面、把同步动作固化进收工流程。

本轮**不做内容核查**，未修正任何技术描述是否与代码相符。疑似不符只记录，见文末。

## 执行状态

| 步骤 | 内容 | 状态 |
| --- | --- | --- |
| 一 | 身份分区 | ✅ 完成（含两处收尾：§9 身份细分、§6 依据回填） |
| 二 | 削减 §0 与 SPEC §1 的重复面 | ✅ 完成 |
| 三 | AGENTS.md 按层触发同步规则 | ✅ 完成 |
| 四（追加） | 按新规则执行首次内容同步 | ✅ 完成（改 4 处，触发但无需改动 3 处） |

> 步骤一至三为**元结构整理**，明确约束「不做内容核查」。步骤四是规则落地后的**首次内容同步**，事实基准为当前工作树（含 003 未提交改动），SPEC 为被校准的一方。

净改动（对 `HEAD` `820664f`）：

| 文件 | 改动 |
| --- | --- |
| `docs/agent-architecture-vnext.zh-CN.md` | +56 / -20 |
| `AGENTS.md` | +13 / -1 |
| `docs/doc-restructure-2026-08-13.md` | 新增（本报告） |

未改动产品代码、测试、配置，未反向修改 `SPEC.zh-CN.md`。

---

## 步骤一：身份分区

### 1.1 头部身份声明区块

`agent-architecture-vnext.zh-CN.md:7`（范围段之后、§0 之前）新增 14 行「文档身份与同步边界」：

- living contract（随代码同步，以代码为准）：§0、§1、§2、§3、§4、§5、§7、§10
- frozen registry（不随代码演进，常规同步不得调整）：§6、§8、§9
- 声明本文件被 `SPEC.zh-CN.md` §4 引用为冻结项权威出处（VNext-1/2/2b/3/4 各行归属列），frozen registry 的修改需经解冻流程

### 1.2 三节 frozen registry 元信息

冻结日期三节同取 **2026-07-16（`c4da4f9`）**。已排除行号漂移假阳性：`git log -L` 对三段行区间回溯均止于该 commit，且 `git show c4da4f9` 证实它正是把三节从路线图改写为冻结登记的那次——§6 标题 `正确位置`→`冻结候选位置`、§8 `与 world freshness、registry 和 F6 的关系`→`冻结范围与重启条件`、§9 `修正后的实施顺序与验收`→`历史阶段结果与冻结候选`，并新增各条重启条款。该文件全部历史仅 3 个 commit（`46c817e` 2026-07-10、`9ba44af` 2026-07-15、`c4da4f9` 2026-07-16）。

| 节 | 解冻条件 | 决策依据 |
| --- | --- | --- |
| §6 | 原文引用节末条款 | 见下方 2.2（本轮已回填为「排序降级依据」） |
| §8 | 原文引用节末条款 | **部分记载**：仅第 4 项 F6 有原文依据；registry/读模型、world freshness、W4 与 hardware fencing、Level 3 replan loop 四项标为「未记载 —— 解冻评审时需重新论证」 |
| §9 | **未记载** —— 各冻结子节只列验收标准，未列解冻条件 | **未记载** |

---

## 本轮收尾一：§9 身份细分

### 判定结果

对 VNext-1 / VNext-2 / VNext-3B1 逐子节判定属 (a) 还是 (b)。**三个子节的判定一致：主体为 (a)，但每个子节内部都夹带一条 (b)**。因此未统一取值到子节层，而是在每个子节的标注里把 (a) 与 (b) 的边界写到具体行。

| 子节 | 判定 | 判定依据（该子节的实际写法） |
| --- | --- | --- |
| VNext-1 | (a) living contract，末条除外 | 前 4 条是无时态的行为陈述，主语是系统当前如何工作——「每个 Action 编译出唯一 mandatory watch-owned Gate task」「API/MCP/AgentRuntime/Chat 返回同一输出结构」。末条以「验收：」起头，陈述的是当时验了什么 |
| VNext-2 | (a) living contract，两处除外 | 前 5 条同为当前行为陈述（「watch 对 pass/reject 都输出 stable code」「effective timeout 在 Gate 与 execute 之间一致」）。末段「当前 obligation 状态通过 compiled graph、Action Board 与 feedback materialize」以「当前」明确自指现状，亦为 (a)。「验收：」一条与「以上已通过定向测试」一句为 (b) |
| VNext-3B1 | (a) living contract，末条除外 | 前 3 条是当前行为陈述（「workspace 同时只有一个 active `watch-executor` owner」）。末条「验收已覆盖…」为 (b) |

判定标准：陈述句主语是「系统现在如何」→ (a)；陈述句主语是「当时验了什么/测了什么」→ (b)。「本轮完成」出现在标题里，但标题是阶段归属标记，不改变正文各行的时态性质。

### 落地标注

八个子节标题下各加一行标注（纯插入，未动正文）：

| 位置 | 子节 | 标注 |
| --- | --- | --- |
| `:373` | VNext-1 | **living contract** + 末条「验收：…」标为 2026-07-10 历史记录，声明「不得作为当前行为的依据」 |
| `:383` | VNext-2 | **living contract** + 「验收：…」与「以上已通过定向测试」标为 2026-07-10 历史记录，同上声明 |
| `:406` | VNext-3B1 | **living contract** + 末条「验收已覆盖…」标为 2026-07-10 历史记录，同上声明 |
| `:396` | VNext-3A | **frozen registry**，冻结日期 + 解冻条件指向 §8 |
| `:415` | VNext-3B2 | 同上 |
| `:423` | VNext-4 | 同上，另指向 §6 的排序降级依据并注明冻结依据未记载 |
| `:432` | VNext-5 | 同上 |
| `:440` | VNext-6 | 同上 |

历史记录日期戳取 **2026-07-10**：`git show 46c817e:docs/agent-architecture-vnext.zh-CN.md` 确认八个 VNext 子节在该 commit（2026-07-10）已全部存在，VNext-1/2/3B1 当时即标注「本轮完成」。与 `SPEC.zh-CN.md` §4 中 VNext-1/2/2b 与 W6.1 的完成日期 2026-07-10 一致。

### §9 头部元信息块修正

`:363` 起，整节 frozen registry 标注改为 **「混合节 —— 见各子节标注」**，并显式限定：其下的冻结日期/解冻条件/决策依据三行「只适用于本节的 frozen registry 子节（VNext-3A、3B2、4、5、6）」。

---

## 本轮收尾二：§6 决策依据回填

### 回填原文

来源 `46c817e` §0「结论：先修心智模型，再补运行账本」，于 `c4da4f9` 从正文移除。原文引用，未改写、未概括：

> 上一版路线把 `Run / Turn / Event` 当成 vNext 的第一块地基，这个顺序不正确。它能统一追踪与展示，却没有改变核心决策模型：模型仍像是在输出 `Action[]`，SafetyGate 只是动作被 watch 领取之后的一个隐式步骤。这样会导致三类问题：
> 1. Agent 的公开输出无法表达“这个物理动作在执行前必须完成哪些义务”。
> 2. 前端、TUI 和下一轮模型只能看到 action/feedback，难以区分等待审批、等待安全校验、正在执行和执行后验证。
> 3. 一旦先围绕 Run/Event 扩展，各入口仍会把同一组安全语义重复翻译，只是多了一层账本。

同一处另引一句：

> `Run / Turn / Event` 仍然重要，但它们是账本外壳，不是 Agent 的核心心智模型。

### 支撑层级判定：排序降级，非冻结

字段写作 **「排序降级依据」**，并另起一行 **「冻结依据：未记载 —— 解冻评审时需重新论证」**。

判定理由（按要求只写在报告，不写进文档）：

1. **论述自述的对象是顺序。** 首句即「这个**顺序**不正确」，落点是「因此演进**顺序**必须改为」，不是「不应建设」。
2. **同一处把 R/T/E 保留在序列内。** `46c817e` §0 的六步顺序中，第 5 步明写「再用 `Run / Turn / Event` 包住上述闭环，承担恢复、审计和时间线」。被排在第 5 位是降级，不是排除。
3. **同一处明确肯定其价值。** 「`Run / Turn / Event` 仍然重要」——这句话与「不应建设」直接矛盾，若据此推出冻结依据即属曲解。
4. **三条问题陈述指向的是「先做它会怎样」。** 第 3 条「一旦**先**围绕 Run/Event 扩展…只是多了一层账本」是典型的次序论证，不是对该能力本身的否定。
5. **真正的冻结是后来另一次决策。** 冻结发生在 `c4da4f9`（2026-07-16）的 R0-R8 功能冻结语境下，与 2026-07-10 这段排序论述不同源、不同时。把前者的依据记到后者名下会制造虚假的决策留痕。

因此 §6 的冻结依据仍为未记载。这不是文档缺陷的掩盖，而是如实反映：**当初有充分理由不先做它，但没有留下不做它的理由。**

### 未回填的条目（只记指针）

按约定，仅在 git 历史中找到同等明确的原始论述才回填。以下为本轮扫描到的疑似指针，**均未回填**：

| 目标字段 | 疑似出处 | 为何未回填 |
| --- | --- | --- |
| §8 前四项的冻结依据 | `c4da4f9` 删除的 `46c817e` §8「Assurance loop 稳定后再推进：1. registry…2. command/query 分离…3. world 增加 `observed_at/revision/stale`…4. W4…5. F6」 | 该段是推进顺序清单，逐条只说「稳定后再推进」，与 §6 情形同类——支撑排序，不支撑冻结。且措辞不及 §6 那段明确（无论证、只有排序），未达「同等明确」门槛 |
| §9 各冻结子节的解冻条件 | `46c817e` §9 各子节的「验收：」行 | 验收标准不等于解冻条件。把验收标准当解冻条件写入会制造新语义，属新编 |
| §9 整节的决策依据 | 未找到 | `46c817e` §9 标题为「修正后的实施顺序与验收」，通篇是顺序与验收，无冻结论证 |

---

## 步骤二：削减 §0 与 SPEC §1 的重复面

### 逐句判定

对比对象：`agent-architecture-vnext.zh-CN.md` §0（原 :9-31）与 `SPEC.zh-CN.md` §1（:26-41）。

| §0 的组成 | 判定 | 依据 |
| --- | --- | --- |
| 主链代码块（原 :9-25） | **重复** | 节点级比对：把两侧按 `→`/`->` 拆成节点、去空白后排序比对，vnext 的 18 个节点全部出现在 SPEC 的 24 个节点中，是**严格子集**。SPEC 另有 `运行态投影：SQLite Action Board + structured feedback`、`output_projection`、`materialized current AgentOutput`、`下一认知轮次` 四个节点 |
| 散文段「rule/LLM chat 主路径只产出 structured draft。…也可直接创建 pending。」（原 :27） | **重复** | `diff` 比对 vnext :41 与 SPEC :38，**逐字完全相同**，无一字符差异 |
| 「这条链的其余当前约束是：reply 只承载用户可读文本…React Dashboard 是唯一 GUI。」（原 :29） | **§0 独有** | SPEC §1 范围内无对应表述 |
| 「`AgentOutput + PlanCompiler + task DAG`、结构化 Gate feedback…R8 后也不会自动恢复。」（原 :31） | **§0 独有** | SPEC §1 范围内无对应表述 |

### 落地

`agent-architecture-vnext.zh-CN.md:23`：删除主链代码块与散文段（-19 行），替换为指向 `SPEC.zh-CN.md` §1 的引用（+3 行）。引用中写明：说明段逐字相同、链路图是 SPEC 版严格子集、删除日期，并列出 SPEC §1 独有而本节从未覆盖的四项内容，避免读者误以为 SPEC §1 只是本节的复制品。

两段独有内容**原样保留、措辞未动**，其上加一行「本节保留的是 SPEC §1 未表述的部分：」作为衔接。

`SPEC.zh-CN.md` 未被反向修改（其工作树 diff 是会话开始前既有的 003 行新增与 F5.0 真机验收更新，非本轮所为）。

### 判定不确定、保留待人工决定的句子

**无。** 四个组成部分的判定均有可复现的机械依据（节点集合比对 / `diff` 逐字比对 / SPEC §1 全文检索），无落入灰区者。

一处备注，不构成不确定判定：被保留的「这条链的其余当前约束是…reply 只承载用户可读文本，不生产或解析 `action-draft` 机器协议」与 `SPEC.zh-CN.md` §2 的 F1 行「reply 永远是用户可读文本，不再承载或解析 `action-draft` 机器协议」语义相近、措辞不同。因本步骤的对比对象被限定为 SPEC **§1**，相对 §1 它确属独有，故保留。若你希望把去重范围扩到 SPEC 全文，这句是下一个候选。

---

## 步骤三：AGENTS.md 按层触发的同步规则

`AGENTS.md`「收工时」新增第 3 项，原第 3、4 项顺延为 4、5（仅编号变化，正文未动）。

| 本轮改动涉及 | 复核 |
| --- | --- |
| `physical_agent/watch/` | vnext §4 |
| `physical_agent/state/` | vnext §5、§5.1 |
| `physical_agent/protocol/` | vnext §3 |
| `physical_agent/api/`，或任何改变对外 API/SSE wire 契约的改动 | vnext §7 |

并写明两条边界：**只复核被触发的章节，不做全文核查；一处都没触发就不复核**；frozen registry 部分（§6、§8，以及 §9 的 VNext-3A/3B2/4/5/6 子节）**不在本规则覆盖范围内**。

### 路径前缀说明

原规则文本写的是裸目录 `watch/`、`state/`、`protocol/`。实测仓库根目录下**这四个裸路径均不存在**，实际路径带 `physical_agent/` 前缀：

```
OK   physical_agent/watch      MISS watch
OK   physical_agent/state      MISS state
OK   physical_agent/protocol   MISS protocol
OK   physical_agent/api        MISS api
```

已按仓库实际目录改为 `physical_agent/` 前缀写入。第四项「API / wire」在仓库中无单一对应目录，落为 `physical_agent/api/` 并补一句「或任何改变对外 API/SSE wire 契约的改动」，以覆盖 wire 契约变更发生在 `protocol/schemas.py` 等处的情形。

---

## 步骤四（追加轮）：按新规则执行的首次内容同步

元结构三步完成后，用刚写进 `AGENTS.md` 的规则跑了第一遍。003 的工作树改动触及 `physical_agent/watch/`、`state/`、`protocol/`、`api/`，四条触发线全部命中，因此复核 §4、§5、§5.1、§3、§7。

**事实基准**：当前工作树（含 003 未提交改动）。SPEC 是被校准的一方，未修改任何代码或测试。

### 已改动（4 处）

| 位置 | 原内容 | 新内容 | 依据 |
| --- | --- | --- | --- |
| §4 末尾 | 无逐动作策略新鲜度描述 | 新增「SAFETY 策略在执行前逐动作校验新鲜度」六条 + 一句在飞动作说明 | `watch/runtime.py:269`（baseline typed hard 参与 claim）、`:276`（claim 后 Gate 前 `read_safety_snapshot()`）、`:292-305`（比 `identity_digest`，`safety.policy.changed` / `safety.policy.invalidated`）、`:679-682`（`cancel_pending_actions_by_proposal`）、`:307-322`（guidance 拒绝 `cancel_proposal=False`）、`:333-335`（Gate 用当轮 fresh `current_policy.hard`）、`watch/safety.py:36-46`（ctor `isinstance` 拒 dict/snapshot） |
| §5 模块树 `state/` | 只有 `sqlite.py`、`sidecars.py` | 增列 `safety_policy.py`；`sidecars.py` 描述补「与原子写」 | `state/safety_policy.py:93`（`HardSafetyPolicy`）、`:118`（`SafetyPolicySnapshot`）、`state/sidecars.py:170-177`（tmp + `fsync` + `os.replace`） |
| §5 模块树 `agent/` | `*_planner.py 产生 raw decision/action intent` | 展开为 `planner.py` / `rule_based.py` / `llm_planner.py` / `planner_factory.py` 四行；`context_builder.py` 描述改为 hard/guidance 分离注入 | 通配符不覆盖 `rule_based.py`（该文件不以 `_planner.py` 结尾）；`agent/context_builder.py:498`（`"""Project the public SAFETY snapshot into isolated hard/guidance channels."""`） |
| §9 VNext-2 第 5 条 | 「context-aware planner 读取 `SAFETY.md`、budgeted feedback 与 previous output」 | 原句保留，句末补一括注：SAFETY 现按 hard/guidance 分 channel 投影注入，动作通道缺 guidance 在调用 LLM 前 fail closed，指向 §4 末段 | `agent/context_builder.py:522-525`（`purpose in ACTION_CONTEXT_PURPOSES and hardware` 且 guidance 缺失 → `raise SafetyGuidanceContextError`） |

第 4 处采取「保留原句 + 括注」而非改写：该子节是 VNext-2 阶段交付记录，把 003 的行为直接写进去会混淆两轮交付的归属。括注使其不再有误导性，细节的家仍在 §4。

### 触发但复核后无需改动（3 处）

| 章节 | 触发原因 | 复核结论 |
| --- | --- | --- |
| §3 | `physical_agent/protocol/` 有改动 | 改动是 `protocol/markdown.py` 新增独立解析原语 `extract_markdown_sections`（该函数 docstring 明写不改变既有 `extract_yaml_block_after_heading` 行为）。§3 的对象是 RawDecision 与 AgentOutput 的分离，涉及 `actions.py`/`agent_output.py`，两者本轮未改。无需改动 |
| §5.1 | `physical_agent/state/` 有改动 | 003 新增 `cancel_pending_actions_by_proposal()`（`state/base.py:84`、`sqlite.py:680`）。§5.1 的断言是「`append_pending_actions()` 单事务提交」与「持久化 task graph 与 action batch 同事务未完成」，两条仍然成立。新 API 不改变 §5.1 的任何论断。无需改动 |
| §7 | `physical_agent/api/` 有改动 | `api/server.py` 本轮仅 3 行变动，未触及 proposal response 契约或 SSE 事件集。§7 的 wire 去重与 `lifecycle=draft/submitted` 论断不受影响。无需改动 |

### 规则本身的第一次体检

四条触发线全部命中，说明粒度合适（不是永不触发的摆设）；其中 §3、§5.1、§7 三条触发后判定无需改动，说明规则不会把「触发」等同于「必须改」。§9 VNext-2 的处理暴露出一个边界：**living contract 标注落在阶段交付记录里时，正确做法是加括注而不是改写**，否则会篡改历史归属。这条经验值得在下次遇到时复用。

---

## 自检

- **是否修改了 §4/§5/§5.1 的技术内容**：否。全部 hunk 锚点（原文件行号）为 4-30 区间的 §0/头部、271、318、332、334、342、353、361、368、374、381、387，§4（170-214）与 §5/§5.1（216-271）无任何锚点落入。
- **是否修改了 §6/§9 正文**：否。§6 只改元信息块内的一个字段；§9 只改头部元信息块并在八个子节标题下各插入一行标注，正文条目一字未动。步骤二删除的是 §0 的内容，不涉及 §6/§9。
- **冻结日期/解冻条件/决策依据是否有编造成分**：无。冻结日期有 `git log -L` + `git show` 双重佐证；解冻条件为原文引用；决策依据凡无出处一律写「未记载」，§6 的回填标明来源 commit 与移除 commit；§8 的部分记载明确区分了「仅第 4 项有」与「其余四项未记载」。
- **步骤二是否改写了独有内容的措辞**：否。两段独有内容逐字保留，只在其上加了一行衔接句。
- **是否反向修改了 SPEC.zh-CN.md**：否。其工作树 diff（F3.1b/003 行新增、F5.0 行真机验收更新）在本会话开始前即存在。
- **是否改动了文档与 AGENTS.md 以外的文件**：否。改动集为 `docs/agent-architecture-vnext.zh-CN.md`、`AGENTS.md`、新增本报告。工作树中的代码/测试改动是 003 在飞的既有内容，本轮未碰。
- **步骤一遗留的头尾不一致是否已消除**：是。头部区块已改为 living contract 含 §9 的 VNext-1/2/3B1、frozen registry 含 §6/§8 与 §9 的 VNext-3A/3B2/4/5/6，并补一句说明 §9 是混合节。与 §9 头部及八个子节标注一致。
