# UI 设计规格（可执行版）

> 日期：2026-07-21。配套可视化：`dashboard-ia-redesign.html`（浏览器直接打开，可点击）。
> 本文是**给实现者看的规格**，不是提案讨论。诊断依据见 `../brief-frontend-optimization-review.zh-CN.md`。
> 分两部分：**A 部分**服务前端重排轮次；**B 部分**服务 ACP/思考链轮次（`../brief-acp-concepts-and-reasoning-trace.zh-CN.md`）。两部分可独立实施。

---

# A 部分：信息架构重排

## A.1 导航结构变更

```
现状 9 项                    目标 8 项
─────────────────────────────────────────────
概览  ┐                      对话      ← 新增
动作  │                      概览      ← 瘦身
世界  ├─ 合并 ──→            动作      ← 不变
机器人│                      状态      ← 吸收「世界」「安全」
硬件  │                      硬件      ← 吸收「机器人」
记忆  │                      记忆      ← 不变
安全  ┘                      事件      ← 不变
事件                         设置      ← 不变
设置
```

侧栏顺序即上表顺序。「对话」排第一（主工作流）。

## A.2 各页组件组成（`renderPageContent` 的目标形态）

| 页面 key | 组件 | 相对现状 |
| --- | --- | --- |
| `chat` | `ChatPanel` | **新页**，组件从 overview 迁出 |
| `overview` | `StateOverviewPanel` + `AgentTaskGraphCard` + `RobotsPanel` | 移除 `ActionBoard`、`ChatPanel`、`ContextTabs` |
| `actions` | `ActionBoard` + `ContextTabs`(默认 feedback) | 不变 |
| `state` | `ContextTabs`(四页签：world/feedback/safety/capabilities) | **新 key**，替代原 `world` 与 `safety` |
| `hardware` | `HardwarePanel` + `ConfigPanel` + `RobotsPanel` | 不变（原 `robots` 页取消，其内容此处已有） |
| `memory` | `UploadPanel` + `MemorySearchPanel` | 不变 |
| `events` | `EventsPanel` + `RawDebug` | 不变 |
| `settings` | `SettingsPanel` + `RawDebug` | 不变 |

**退役的 page key**：`world`、`safety`、`robots`。三者的内容均已在 `state` / `hardware` 页覆盖，不存在能力丢失。

## A.3 ContextTabs 的行为收敛（消除导航冲突）

**问题**：现状 `world` / `safety` / `actions` 三个页面都渲染同一个 `ContextTabs`，且它永远显示全部四个页签。用户在「世界」页点页签切到「安全」，内容变了但侧栏高亮不变——两套导航互不同步。

**规则**：

- 在 `state` 页：显示全部四个页签，页签是**唯一**的切换方式，默认 `world`。
- 在 `actions` 页：**不显示页签栏**，只渲染 feedback 面板（用 prop 控制，如 `tabsHidden` 或 `only="feedback"`）。
- 任何页面都不得出现"侧栏说 A、内容显示 B"的状态。

## A.4 提案栏（ProposalPanel）：常驻 → 按需

**现状**：`≥1080px` 时九个页面全部常驻约 370px；`<1080px` 已经会收成顶部「提案」按钮。

**目标**：把小屏已有的收起机制升级为**全尺寸默认行为**。

| 页面 | 提案栏默认状态 |
| --- | --- |
| `actions` | 展开（提案是该页主要动作） |
| 其余全部页面 | 收起为窄条 / 按钮，点击展开为抽屉或侧栏 |

- 收起态：右侧窄条（约 34px）或 header 按钮，标注「提案」。
- 展开态：与现状视觉一致，不改表单本身。
- 用户手动展开/收起的选择记入 `localStorage`，按页面记忆。

**附带收益**：`ProposalPanel` 在多数页面不再挂载，聊天流式输出时的整树重渲染问题随之消失（见诊断 brief §2）。这是本次改动**同时解决布局与性能**的关键点，不要只做一半。

## A.5 ActionBoard 折叠规则（安全相关，必须按状态判定）

`ActionBoard` 是审批入口——`requires_approval` 的动作卡在 pending 等人点批准。**不允许无条件默认折叠**，否则"有活等你批"的信号会被藏起来。

| 条件 | 表现 |
| --- | --- |
| 无任何动作 | 折叠成单行：`动作板` + 灰字「暂无待处理动作」 |
| 有 pending，但无一条 `metadata.approval.required` | 折叠，但**计数徽章可见**：`待处理 N`、`已完成 N` |
| **存在待审批动作** | **强制展开，且不可折叠**；标题行用 warning 底色 + 警示图标，文案「动作板 · N 条动作等待你审批」；直接列出待批条目与批准/拒绝按钮 |

- 折叠状态可记入 `localStorage`，但"待审批强制展开"**优先级高于用户偏好**。
- 待审批计数由前端遍历 pending 的 `metadata.approval.required` 得出，**不需要新增 API 字段**。

## A.6 其余视觉修正（低风险，可同轮做）

1. **`ActionBoard.tsx:73` 中英混排**：硬编码的 `` `Running ${n}` `` 改为走 `labels.actions.*`；`locales/zh.ts` / `en.ts` 补 `in_progress` 词条（中文「运行中」）。
2. **i18n 补齐**：7 个零 `labels` 引用的组件接入 i18n —— `ProposalPanel`（优先，常驻可见）、`FeedbackTimeline`、`CapabilityCard`、`EventsPanel`、`MemorySearchPanel`、`AgentTaskGraphCard`、`FeedbackStatusTag`/`JsonSummary`。约 53 处硬编码英文。
3. **空状态收缩**：空态卡片（如「No compiled AgentOutput」）从满尺寸卡改为单行提示，高度 ≤44px。
4. **Raw 摘要默认折叠**：`FeedbackTimeline` 的 `JsonSummaryLine` 默认收起，点击展开。
5. **历史状态徽章降饱和**：feedback 时间线里的历史 `pending` 徽章使用低饱和样式，避免与动作板当前状态混淆。
6. **表格列宽**：动作板给「依赖」「复核」两列设最小宽度，避免被挤到右缘。
7. **焦点样式**：全局补 `:focus-visible` 描边（当前 `:focus` 样式 0 处）。

## A.7 需要同步更新的测试

- Playwright：`data-testid="nav-*"` 与 `page-*` 断言随 page key 变更调整；新增 `nav-chat`、`nav-state`；移除 `nav-world`、`nav-safety`、`nav-robots`。
- 新增用例：提案栏收起态下点击展开；ActionBoard 三种折叠状态（尤其"待审批强制展开且不可折叠"）。
- TUI 若有对应视图命名，同步 `tui/tests/scenarios/`。

---

# B 部分：思考链展示（服务 ACP 轮次）

## B.1 位置与层级

推理摘要属于**次要信息**，不得抢正文视觉权重。

```
┌─ assistant 气泡 ─────────────────────┐
│  ▸ 模型推理摘要            ← 折叠行，默认收起
│  ─────────────────────────────────  │
│  正文回复（Markdown 渲染）            │
│  ─────────────────────────────────  │
│  [Draft 卡片，如有]                   │
└──────────────────────────────────────┘
```

- 折叠行位于正文**上方**（推理先于结论），但默认收起，收起时只占一行。
- 用 `--text-secondary` 级别的次要样式，字号比正文小一档。
- 展开后内容用等宽或普通正文样式均可，但**必须与正文有明确视觉区隔**（缩进 + 左侧竖线，或浅色底）。

## B.2 文案（必须传达"这不是决策依据"）

- 折叠行标题：**「模型推理摘要」**（英文 `Model reasoning summary`）。不要用「思考过程」「Thinking」——那会暗示这是完整且忠实的推理。
- 展开后顶部加一行灰字说明：**「由模型生成的推理摘要，仅供参考，不代表实际决策依据。动作是否放行以 SafetyGate 校验为准。」**

**理由**：human-in-the-loop 场景下，operator 可能因为"看起来想得很周到"而降低审批警惕。这行字是防御性设计，不可省略。

## B.3 流式行为

- `thought` 事件到达时，折叠行显示"推理中…"的轻量指示（不要 spinner 抢眼）。
- 用户可在流式过程中展开实时查看。
- 无 `thought` 事件时（非推理模型 / Chat Completions 模式）：**整行不渲染**，不显示空态、不显示"无推理"。

## B.4 TUI 对应

- 单独一行 role，前缀标记（如 `thought>`），默认折叠为一行摘要。
- 遵循 TUI 现有 append-only transcript 风格，不引入 live 刷新。

## B.5 不做的事

- 不展示 raw CoT（`A1.3a` 既有决定）。
- 不把推理摘要做成可复制/可编辑/可反馈的交互对象——它是只读的观测信息。
- 不在 Actions 板、feedback 时间线或任何审批界面展示推理摘要（避免它被误当作审批依据）。
